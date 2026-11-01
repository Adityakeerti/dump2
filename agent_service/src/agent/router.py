import asyncio
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import service
from src.agent.schemas import (
    AgentResponse,
    AudioPreference,
    ChatRequest,
    ConfirmResponse,
    PersonaView,
    SessionCreate,
    SessionView,
)
from src.agent import events
from src.auth.dependencies import admin_principal, current_principal
from src.auth.schemas import Principal
from src.config import settings
from src.database import get_session
from src.models import AgentConfig, ChatMessage, ChatSession, PendingAction, utcnow
from src.providers.speech import transcribe_with_fallback, synthesize_speech
from src.rate_limit import check_rate_limit

from src.agent.local_agent import LocalChatRequest, PlaceRequest  # noqa: E402

router = APIRouter(prefix="/api/agent", tags=["agent"])
Session = Annotated[AsyncSession, Depends(get_session)]
User = Annotated[Principal, Depends(current_principal)]
Admin = Annotated[Principal, Depends(admin_principal)]


def _source(request: Request) -> str:
    return events.describe_source(request.headers.get("x-citysense-source"))


@router.post("/chat", response_model=AgentResponse)
async def chat(payload: ChatRequest, request: Request, session: Session, principal: User):
    if not getattr(request.app.state, "embedder_ready", False):
        raise HTTPException(503, "EMBEDDER_UNAVAILABLE: check /ready")
    check_rate_limit(principal.user_id)
    if len(payload.message) > settings.max_message_length:
        raise HTTPException(422, "Message exceeds configured length limit")
    import time as _time

    meta: dict = {}
    token = events.turn_meta.set(meta)
    started = _time.monotonic()
    try:
        async with asyncio.timeout(settings.request_timeout_seconds):
            response = await service.chat(session, principal, payload)
    except TimeoutError as exc:
        await session.rollback()
        events.record("chat_error", source=_source(request), user=events.short_user(principal.user_id),
                      message=payload.message[:300], error="timeout")
        raise HTTPException(504, "Chat request timed out; retry with the same requestId") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        events.turn_meta.reset(token)
    _record_chat(request, principal, payload, response, meta, _time.monotonic() - started)
    if "text/event-stream" in request.headers.get("accept", ""):

        async def frames():
            yield f"data: {json.dumps({'t': 'token', 'v': response.answer}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'t': 'final', **response.model_dump(mode='json')}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return response


def _record_chat(request: Request, principal: Principal, payload: ChatRequest, response: AgentResponse,
                 meta: dict, elapsed: float) -> None:
    action = response.actionData or {}
    emergency = action.get("emergency") or {}
    events.record(
        "chat",
        source=_source(request),
        user=events.short_user(principal.user_id),
        sessionId=str(response.sessionId),
        message=payload.message[:300],
        language=payload.language or ("hi" if any("\u0900" <= c <= "\u097f" for c in payload.message) else "en"),
        guard=meta.get("guard"),
        scope=meta.get("scope"),
        plan=[s.model_dump() for s in (response.plan or [])],
        toolCalls=[
            {**t.model_dump(), "service": events.TOOL_SERVICE.get(t.tool, "agent")} for t in (response.toolCalls or [])
        ],
        status=response.status,
        served=response.served,
        answer=response.answer[:600],
        pendingAction=response.pendingAction.summary if response.pendingAction else None,
        missionId=emergency.get("mission_id"),
        location=(action.get("location") or {}).get("location"),
        durationMs=round(elapsed * 1000, 1),
    )


async def _main_agent_turn(request: Request, session: AsyncSession, principal: Principal, payload: ChatRequest):
    """Run one turn through the main voice agent (same path as /chat) and log it for the dashboard."""
    import time as _time

    if not getattr(request.app.state, "embedder_ready", False):
        raise HTTPException(503, "EMBEDDER_UNAVAILABLE: check /ready")
    from src.agent.request_context import user_bearer

    meta: dict = {}
    token = events.turn_meta.set(meta)
    bearer_token = user_bearer.set(request.headers.get("authorization"))
    started = _time.monotonic()
    try:
        async with asyncio.timeout(settings.request_timeout_seconds):
            response = await service.chat(session, principal, payload)
    except TimeoutError as exc:
        await session.rollback()
        raise HTTPException(504, "Request timed out; please retry") from exc
    finally:
        events.turn_meta.reset(token)
        user_bearer.reset(bearer_token)
    _record_chat(request, principal, payload, response, meta, _time.monotonic() - started)
    return response


class AssistantRequest(BaseModel):
    """The main avatar (island) in the citizen app: talks to the main agent, which can also drive the app."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}
    message: str
    sessionId: UUID | None = None
    language: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    screen: str | None = None


@router.post("/assistant", response_model=AgentResponse)
async def assistant(payload: AssistantRequest, request: Request, session: Session, principal: User):
    """Main agent for the in-app assistant island: full hierarchy + app control (clientActions)."""
    from uuid import uuid4

    from src.agent.schemas import ChatContext

    check_rate_limit(principal.user_id)
    if not payload.message or len(payload.message) > settings.max_message_length:
        raise HTTPException(422, "Message must be 1-4000 characters")
    chat_req = ChatRequest(
        requestId=uuid4(), sessionId=payload.sessionId, message=payload.message,
        language=payload.language if payload.language in ("hi", "en") else None,
        context=ChatContext(latitude=payload.latitude, longitude=payload.longitude),
    )
    return await _main_agent_turn(request, session, principal, chat_req)


@router.post("/local-chat", response_model=AgentResponse)
async def local_chat(payload: LocalChatRequest, request: Request, session: Session, principal: User):
    """A local area agent (map avatar): area persona + web search + cited LLM answer.

    Emergencies and civic complaints are escalated to the main agent, which stays on top of the hierarchy.
    """
    import time as _time
    from uuid import uuid4

    from src.agent.local_agent import local_agent_answer, needs_main_agent
    from src.agent.schemas import ChatContext, PlanStepView

    check_rate_limit(principal.user_id)
    av = payload.avatar
    if needs_main_agent(payload.message):
        chat_req = ChatRequest(
            requestId=uuid4(), sessionId=payload.sessionId, message=payload.message, language=payload.language,
            context=ChatContext(latitude=av.latitude, longitude=av.longitude),
        )
        response = await _main_agent_turn(request, session, principal, chat_req)
        escalation = PlanStepView(id=0, executor="local_agent", action=f"{av.name} escalated to City Sense (main agent)",
                                  tools=[], status="completed")
        response.plan = [escalation, *(response.plan or [])]
        return response
    started = _time.monotonic()
    response = await local_agent_answer(principal, payload)
    events.record(
        "chat", source=_source(request), user=events.short_user(principal.user_id), sessionId=str(response.sessionId),
        message=payload.message[:300], language=payload.language, scope="LOCAL_AGENT", guard={"safe": True},
        plan=[s.model_dump() for s in response.plan or []],
        toolCalls=[{**t.model_dump(), "service": "web_search"} for t in response.toolCalls or []],
        status=response.status, served=response.served, answer=response.answer[:600],
        location=(response.actionData or {}).get("area", {}).get("locality"), localAgent=av.name,
        durationMs=round((_time.monotonic() - started) * 1000, 1),
    )
    return response


@router.post("/place", response_model=AgentResponse)
async def place(payload: PlaceRequest, request: Request, session: Session, principal: User):
    """Main agent briefing for a tapped map point; with `question`, a follow-up through the full hierarchy."""
    import time as _time
    from uuid import uuid4

    from src.agent.local_agent import place_insight
    from src.agent.orchestrator import supervisor
    from src.agent.schemas import ChatContext

    check_rate_limit(principal.user_id)
    if payload.question:
        where = f" (near {payload.label})" if payload.label else ""
        chat_req = ChatRequest(
            requestId=uuid4(), sessionId=payload.sessionId, message=f"{payload.question}{where}"[:2000],
            language=payload.language, context=ChatContext(latitude=payload.latitude, longitude=payload.longitude),
        )
        return await _main_agent_turn(request, session, principal, chat_req)
    started = _time.monotonic()
    response = await place_insight(principal, payload, supervisor)
    events.record(
        "chat", source=_source(request), user=events.short_user(principal.user_id), sessionId=str(response.sessionId),
        message=f"[map tap] {(response.actionData or {}).get('place', {}).get('label', '')}", language=payload.language,
        scope="MAP_PLACE", guard={"safe": True}, plan=[s.model_dump() for s in response.plan or []],
        toolCalls=[{**t.model_dump(), "service": events.TOOL_SERVICE.get(t.tool, "agent")} for t in response.toolCalls or []],
        status=response.status, served=response.served, answer=response.answer[:600],
        location=(response.actionData or {}).get("place", {}).get("label"),
        durationMs=round((_time.monotonic() - started) * 1000, 1),
    )
    return response


@router.get("/events")
async def flow_events(principal: Admin, after: int = 0, limit: int = 100):
    """Data-flow events for the live demo dashboard (admin only: contains citizen messages)."""
    return {"events": events.since(after, limit)}


@router.get("/personas", response_model=list[PersonaView])
async def personas(session: Session, principal: User) -> list[PersonaView]:
    try:
        agents = (await session.scalars(select(AgentConfig).where(AgentConfig.active.is_(True)))).all()
        if agents:
            return [PersonaView(id=a.agent_id, name=a.display_name, tier=a.tier) for a in agents]
    except Exception:
        pass
    return [
        PersonaView(id="general", name="City Sense (AI Assistant)", tier="general"),
        PersonaView(id="municipal", name="Municipal Grievance Officer", tier="professional"),
    ]


@router.post("/sessions", response_model=SessionView, status_code=201)
async def create_session(payload: SessionCreate, session: Session, principal: User) -> SessionView:
    try:
        return await service.create_session(session, principal, payload.agentId, payload.language)
    except Exception:
        from uuid import uuid4
        return SessionView(sessionId=uuid4(), agentId=payload.agentId, language=payload.language)


@router.get("/sessions", response_model=list[SessionView])
async def sessions(
    session: Session, principal: User, offset: int = 0, limit: int = 50
) -> list[SessionView]:
    try:
        records = (
            await session.scalars(
                select(ChatSession)
                .where(ChatSession.user_id == principal.user_id)
                .order_by(ChatSession.updated_at.desc())
                .offset(max(offset, 0))
                .limit(min(max(limit, 1), 100))
            )
        ).all()
        return [
            SessionView(sessionId=s.session_id, agentId=s.agent_id, language=s.language)
            for s in records
        ]
    except Exception:
        return []


@router.get("/sessions/{session_id}/messages")
async def history(
    session_id: UUID, session: Session, principal: User, offset: int = 0, limit: int = 50
):
    try:
        owned = await session.scalar(
            select(ChatSession).where(
                ChatSession.session_id == session_id, ChatSession.user_id == principal.user_id
            )
        )
        if not owned:
            return []
        messages = (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
                .offset(max(offset, 0))
                .limit(min(max(limit, 1), 100))
            )
        ).all()
        return [
            {
                "messageId": m.message_id,
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "createdAt": m.created_at,
                "response": m.meta.get("response"),
            }
            for m in messages
        ]
    except Exception:
        return []


@router.post("/voice")
async def voice(
    request: Request,
    principal: User,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form()] = None,
):
    check_rate_limit(principal.user_id)
    if language not in {None, "en", "hi"}:
        raise HTTPException(422, "Language must be en or hi")
    from pathlib import Path

    if Path(file.filename or "").suffix.lower() not in {
        ".wav",
        ".mp3",
        ".mp4",
        ".m4a",
        ".mpeg",
        ".mpga",
        ".ogg",
        ".webm",
        ".flac",
    }:
        raise HTTPException(415, "Unsupported audio format")
    data = await file.read(settings.max_upload_bytes + 1)
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(
            413, "Audio must be nonempty and no larger than the configured upload limit"
        )
    import time as _time

    started = _time.monotonic()
    try:
        text, lang, provider = await transcribe_with_fallback(
            data, file.filename or "recording.wav", language
        )
    except Exception as exc:
        events.record("stt", source=_source(request), user=events.short_user(principal.user_id), ok=False,
                      bytes=len(data), durationMs=round((_time.monotonic() - started) * 1000, 1))
        raise HTTPException(503, "STT_UNAVAILABLE: use keyboard dictation") from exc
    events.record("stt", source=_source(request), user=events.short_user(principal.user_id), ok=True,
                  provider=provider, text=text[:300], lang=lang, bytes=len(data),
                  durationMs=round((_time.monotonic() - started) * 1000, 1))
    if not text.strip():
        raise HTTPException(503, "STT_UNAVAILABLE: use keyboard dictation")
    return {"text": text, "lang": lang}


class TTSRequest(BaseModel):
    text: str
    language: str | None = "hi"
    speaker: str | None = None


@router.post("/tts")
async def tts(payload: TTSRequest, principal: User, request: Request):
    """Synthesizes text to 24 kHz WAV via Sarvam bulbul:v3 (authenticated: it spends provider credits)."""
    return Response(content=await _synthesize(payload, principal, _source(request)), media_type="audio/wav")


async def _synthesize(payload: TTSRequest, principal: Principal, source: str = "direct_api") -> bytes:
    import time as _time

    started = _time.monotonic()
    try:
        audio = await _synthesize_inner(payload, principal)
    except HTTPException:
        events.record("tts", source=source, user=events.short_user(principal.user_id), ok=False,
                      chars=len(payload.text or ""))
        raise
    events.record("tts", source=source, user=events.short_user(principal.user_id), ok=True,
                  chars=len(payload.text), bytes=len(audio), durationMs=round((_time.monotonic() - started) * 1000, 1))
    return audio


async def _synthesize_inner(payload: TTSRequest, principal: Principal) -> bytes:
    check_rate_limit(principal.user_id)
    if not payload.text or not payload.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    from src.agent.tool_registry import AUDIO_PREFERENCES

    speaker = payload.speaker or AUDIO_PREFERENCES.get(principal.user_id, {}).get("preferred_speaker", "aditya")
    try:
        return await synthesize_speech(payload.text, payload.language or "hi", speaker)
    except Exception as exc:
        raise HTTPException(503, "TTS_UNAVAILABLE: speech synthesis is not available right now") from exc


# Short-lived TTS clips: lets native players stream reply audio from a plain URL. The 128-bit id is
# the capability (no auth header needed for playback); clips expire after CLIP_TTL seconds.
# Process-local: run the agent with a single worker (the default) or put a shared cache here.
CLIP_TTL = 300
_CLIPS: "dict[str, tuple[float, bytes]]" = {}


@router.post("/tts/clips", status_code=201)
async def create_tts_clip(payload: TTSRequest, principal: User, request: Request):
    import secrets as _secrets
    import time as _time

    audio = await _synthesize(payload, principal, _source(request))
    now = _time.monotonic()
    for key in [k for k, (exp, _) in _CLIPS.items() if exp < now]:
        _CLIPS.pop(key, None)
    while len(_CLIPS) >= 200:
        _CLIPS.pop(next(iter(_CLIPS)))
    clip_id = _secrets.token_urlsafe(16)
    _CLIPS[clip_id] = (now + CLIP_TTL, audio)
    return {"clipId": clip_id, "url": f"/api/agent/tts/clips/{clip_id}", "expiresInSeconds": CLIP_TTL}


@router.get("/tts/clips/{clip_id}")
async def get_tts_clip(clip_id: str):
    import time as _time

    item = _CLIPS.get(clip_id)
    if not item or item[0] < _time.monotonic():
        raise HTTPException(404, "Clip not found or expired")
    return Response(content=item[1], media_type="audio/wav", headers={"Cache-Control": "private, max-age=300"})


@router.get("/preferences/audio")
async def get_audio_preference(principal: User):
    from src.agent.tool_registry import AUDIO_PREFERENCES

    return AUDIO_PREFERENCES.get(principal.user_id, {"auto_play": True, "preferred_speaker": "aditya"})


@router.put("/preferences/audio")
async def set_audio_preference(payload: AudioPreference, principal: User):
    """Speaker mute/unmute toggle (Invariant 3); executed via the main agent's own tool."""
    from src.agent.tool_registry import MAIN, call_tool

    res = await call_tool(MAIN, "toggle_audio_preference", payload.model_dump(), principal.user_id)
    return {k: v for k, v in res.items() if k != "served"}


@router.get("/tools")
async def tool_catalog(principal: User):
    """The tool catalog with each tool's single owning agent."""
    from src.agent.tool_registry import TOOL_OWNERS
    from src.agent.tools import tool_schemas

    return [
        {"name": t["function"]["name"], "owner": TOOL_OWNERS[t["function"]["name"]],
         "description": t["function"]["description"]}
        for t in tool_schemas(sorted(TOOL_OWNERS))
    ]


@router.post("/actions/{token}/confirm", response_model=ConfirmResponse)
async def confirm(token: str, session: Session, principal: User, request: Request) -> ConfirmResponse:
    result = await service.confirm_action(session, principal, token)
    events.record("action_confirm", source=_source(request), user=events.short_user(principal.user_id),
                  status=result.status, trackingId=(result.result or {}).get("trackingId"),
                  worker=(result.result or {}).get("assignedWorker"), detail=result.detail)
    return result


@router.post("/actions/{token}/photo", status_code=201)
async def attach_action_photo(
    token: str, session: Session, principal: User, request: Request, file: Annotated[UploadFile, File()]
):
    """Attach a photo (stored in the database) to a drafted complaint before confirming it."""
    from src.agent.media import MAX_BYTES, attach_photo

    check_rate_limit(principal.user_id)
    data = await file.read(MAX_BYTES + 1)
    result = await attach_photo(session, principal, token, data)
    events.record("photo", source=_source(request), user=events.short_user(principal.user_id),
                  sizeBytes=result["sizeBytes"], contentType=result["contentType"])
    return result


@router.get("/media/{media_id}")
async def get_media(media_id: UUID, session: Session, principal: User):
    """A citizen's own uploaded photo."""
    from src.agent.media import get_owned

    media = await get_owned(session, principal, media_id)
    return Response(content=media.data, media_type=media.content_type, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/actions/{token}")
async def action_status(token: str, session: Session, principal: User):
    try:
        action = await session.scalar(select(PendingAction).where(PendingAction.token == token, PendingAction.user_id == principal.user_id))
        if action:
            state = "expired" if action.status == "pending" and action.expires_at <= utcnow() else action.status
            return {"status": state, "summary": action.summary, "expiresAt": action.expires_at, "resultRef": action.result_ref}
    except Exception:
        pass
    from src.agent.offline import offline_action_status
    status = offline_action_status(principal, token)
    if not status:
        raise HTTPException(404, "Action not found")
    return status


@router.post("/actions/{token}/cancel", response_model=ConfirmResponse)
async def cancel(token: str, session: Session, principal: User) -> ConfirmResponse:
    return await service.cancel_action(session, principal, token)
