import json
import secrets
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.cache import cached_answer, store_answer
from src.agent.schemas import (
    AgentInfo,
    AgentResponse,
    ChatRequest,
    ConfirmResponse,
    PendingActionView,
    SessionView,
    Source,
)
from src.agent.tools import TOOL_MODELS, args_hash, execute_complaint, read_tool, tool_schemas
from src.auth.schemas import Principal
from src.config import settings
from src.knowledge.evidence import EvidenceHit, validate_evidence
from src.knowledge.retrieval import RetrievalHit, retrieve
from src.models import (
    AgentConfig,
    AuditLog,
    ChatMessage,
    ChatSession,
    MessageSource,
    PendingAction,
    utcnow,
)
from src.providers.registry import generate_with_failover


async def get_agent(session: AsyncSession, agent_id: str) -> AgentConfig:
    agent = await session.get(AgentConfig, agent_id)
    if not agent or not agent.active:
        raise HTTPException(404, "Unknown or inactive agent")
    return agent


async def create_session(
    session: AsyncSession, principal: Principal, agent_id: str, language: str | None
) -> SessionView:
    await get_agent(session, agent_id)
    item = ChatSession(user_id=principal.user_id, agent_id=agent_id, language=language)
    session.add(item)
    await session.commit()
    return SessionView(sessionId=item.session_id, agentId=item.agent_id, language=item.language)


def evidence_for(hits: list[RetrievalHit], threshold: float, city: str | None):
    return validate_evidence(
        [
            EvidenceHit(
                str(h.chunk_id),
                str(h.doc_id),
                h.tenant_id,
                h.text,
                h.vector_score,
                h.fused_score,
                h.verified,
                h.jurisdiction,
                h.expires_at,
                fetched_at=h.fetched_at,
            )
            for h in hits
        ],
        min_similarity=threshold,
        city_id=city,
        freshness_days=settings.source_freshness_days,
    )


def _as_sources(items: list) -> list[Source]:
    """Normalise specialist sources (dicts / Source / RetrievalHit) into response Sources."""
    out: list = []
    for item in items or []:
        if isinstance(item, (Source, RetrievalHit)):
            out.append(item)
        elif isinstance(item, dict):
            out.append(Source(
                docId=str(item.get("docId") or item.get("doc_id") or "DOC"),
                title=item.get("title", "Official Record"),
                url=item.get("url"),
                excerpt=(item.get("excerpt") or "")[:500],
                fetchedAt=item.get("fetchedAt") or utcnow(),
                stale=bool(item.get("stale", False)),
            ))
    return out


async def chat(session: AsyncSession, principal: Principal, request: ChatRequest) -> AgentResponse:
    started = time.monotonic()
    try:
        # Transaction-scoped advisory locks serialize request retries across connections.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": str(request.requestId)},
        )
    except Exception:
        # Fall back to verified grounded offline engine when PostgreSQL is offline
        from src.agent.offline import offline_chat
        return await offline_chat(principal, request, started)
    existing = await session.scalar(
        select(ChatMessage).where(ChatMessage.request_id == request.requestId)
    )
    if existing:
        owner = await session.get(ChatSession, existing.session_id)
        if not owner or owner.user_id != principal.user_id:
            raise HTTPException(409, "requestId is already in use")
        if existing.meta.get("request") != request.model_dump(mode="json"):
            raise HTTPException(409, "requestId payload does not match its original request")
        return AgentResponse.model_validate(existing.meta["response"])
    agent_id = request.agentId or "general"
    if request.sessionId:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": str(request.sessionId)},
        )
        chat_session = await session.get(ChatSession, request.sessionId)
        if chat_session and chat_session.user_id != principal.user_id:
            raise HTTPException(404, "Session not found")
        if not chat_session:
            # Gateways (core) may mint the session id before the agent has seen it: adopt it.
            await get_agent(session, agent_id)
            chat_session = ChatSession(
                session_id=request.sessionId,
                user_id=principal.user_id,
                agent_id=agent_id,
                language=request.language,
            )
            session.add(chat_session)
            await session.flush()
        if request.agentId and request.agentId != chat_session.agent_id:
            raise HTTPException(409, "Session persona cannot be changed by the request")
        agent_id = chat_session.agent_id
    else:
        await get_agent(session, agent_id)
        chat_session = ChatSession(
            user_id=principal.user_id, agent_id=agent_id, language=request.language
        )
        session.add(chat_session)
        await session.flush()
    agent = await get_agent(session, agent_id)
    language = (
        request.language
        or chat_session.language
        or ("hi" if any("\u0900" <= c <= "\u097f" for c in request.message) else "en")
    )
    city = request.context.cityId or settings.default_city_id
    chat_session.language = language

    from src.agent.orchestrator import supervisor

    try:  # history only sharpens follow-up routing; never fail a turn over it
        recent = (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == chat_session.session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(6)
            )
        ).all()
    except Exception:
        recent = []
    outcome = await supervisor.evaluate_turn(
        session=session,
        principal=principal,
        request=request,
        chat_session=chat_session,
        agent=agent,
        language=language,
        city=city,
        started=started,
        history=[{"role": m.role, "content": m.content[:1000]} for m in reversed(recent)],
    )
    # Every response from here on carries the main agent's plan and tool trace.
    from src.agent.orchestrator import finalize_plan

    async def persist(*args, **kwargs):
        # args[4] is the final status of the turn
        return await persist_turn(*args, **kwargs, plan=finalize_plan(outcome.plan, args[4]),
                                  tool_calls=outcome.tool_calls, action_data=outcome.action_data,
                                  client_actions=outcome.client_actions)
    if outcome.handled:
        served = "fallback" if outcome.tool_calls and all(c.served == "fallback" for c in outcome.tool_calls) else "live"
        return await persist(
            session,
            chat_session,
            request,
            agent,
            outcome.status,
            outcome.answer,
            _as_sources(outcome.sources),
            served,
            cta=outcome.cta,
            pending_action=outcome.pending_action,
            started=started,
        )

    hits = await retrieve(session, request.message, list(agent.tenants), limit=6)
    evidence = evidence_for(hits, agent.min_similarity, city)
    if evidence.abstain:
        from src.agent.composer import compose

        composed = await compose(
            intent="no_verified_info", message=request.message, language=language,
            history=[{"role": m.role, "content": m.content} for m in reversed(recent)],
        )
        answer = composed or (
            "इस प्रश्न के लिए मेरे पास सत्यापित जानकारी नहीं है।"
            if language == "hi"
            else "I do not have verified information for that question."
        )
        return await persist(
            session,
            chat_session,
            request,
            agent,
            "ABSTAINED",
            answer,
            [],
            "live",
            cta="file_complaint",
            started=started,
        )
    supported_ids = {h.chunk_id for h in evidence.usable_hits}
    hits = [h for h in hits if str(h.chunk_id) in supported_ids]
    # Use only six bounded history messages; no previous retrieval context is forwarded.
    prior = (
        await session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(6)
        )
    ).all()
    history = [
        {"role": m.role, "content": m.content[:1000]}
        for m in reversed(prior)
        if m.role in {"user", "assistant"}
    ]
    history.append({"role": "user", "content": request.message})
    if not prior:
        cached = await cached_answer(
            session, request.message, agent, hits, language, city, principal.user_id
        )
        if cached:
            return await persist(
                session,
                chat_session,
                request,
                agent,
                "ANSWERED",
                cached,
                hits,
                "cache",
                started=started,
            )
    handoff = None
    used_tool_fallback = False
    directory = (
        await session.scalars(select(AgentConfig).where(AgentConfig.active.is_(True)))
    ).all()
    directory_prompt = "\nActive personas: " + json.dumps(
        [{"id": item.agent_id, "name": item.display_name} for item in directory]
    )
    for step in range(3):
        try:
            from src.agent.composer import system_prompt as composer_prompt

            generated = await generate_with_failover(
                system=composer_prompt("knowledge_answer", language, []) + "\n\n" + agent.system_prompt + directory_prompt,
                user=request.message,
                context=[h.text for h in hits],
                language=language,
                tools=tool_schemas(agent.tools),
                history=history,
            )
        except RuntimeError:
            return await persist(
                session,
                chat_session,
                request,
                agent,
                "UNAVAILABLE",
                "The answer service is temporarily unavailable. Please try again later.",
                [],
                "fallback",
                started=started,
            )
        if not generated.tool_calls:
            if step == 0 and not prior and not generated.fallback:
                await store_answer(
                    session,
                    request.message,
                    generated.text,
                    agent,
                    hits,
                    language,
                    city,
                    principal.user_id,
                )
            return await persist(
                session,
                chat_session,
                request,
                agent,
                "ANSWERED",
                generated.text,
                hits,
                "fallback" if generated.fallback or used_tool_fallback else "live",
                provider=generated.provider,
                handoff=handoff,
                started=started,
            )
        if generated.provider == "local" and not settings.local_tools_enabled:
            return await persist(
                session,
                chat_session,
                request,
                agent,
                "UNAVAILABLE",
                "Local model tools are disabled.",
                [],
                "fallback",
                started=started,
            )
        history.append(
            {
                "role": "assistant",
                "content": generated.text or None,
                "tool_calls": generated.tool_calls,
            }
        )
        for call in generated.tool_calls:
            try:
                name = call["function"]["name"]
                if name not in agent.tools or name not in TOOL_MODELS:
                    raise ValueError("Tool is not allowed")
                raw = call["function"]["arguments"]
                args = (
                    TOOL_MODELS[name]
                    .model_validate(json.loads(raw) if isinstance(raw, str) else raw)
                    .model_dump()
                )
                session.add(
                    AuditLog(
                        actor=principal.user_id,
                        agent_id=agent.agent_id,
                        event="tool_requested",
                        detail={"tool": name},
                    )
                )
                if name == "ask_clarification":
                    return await persist(
                        session,
                        chat_session,
                        request,
                        agent,
                        "CLARIFICATION_REQUIRED",
                        args["question"],
                        [],
                        "live",
                        provider=generated.provider,
                        started=started,
                    )
                if name == "create_complaint":
                    token = secrets.token_urlsafe(32)
                    expires = utcnow() + timedelta(seconds=settings.action_ttl_seconds)
                    summary = f"Complaint ({args['category']}) at {args['location']}: {args['description']}"
                    session.add(
                        PendingAction(
                            token=token,
                            session_id=chat_session.session_id,
                            user_id=principal.user_id,
                            agent_id=agent.agent_id,
                            tool=name,
                            args=args,
                            args_hash=args_hash(args),
                            summary=summary,
                            expires_at=expires,
                        )
                    )
                    pending = PendingActionView(token=token, summary=summary, expiresAt=expires)
                    return await persist(
                        session,
                        chat_session,
                        request,
                        agent,
                        "ACTION_PENDING",
                        "Please review and confirm this complaint.",
                        hits,
                        "live",
                        pending_action=pending,
                        provider=generated.provider,
                        started=started,
                    )
                if name == "handoff":
                    target = await get_agent(session, args["agent_id"])
                    if target.agent_id == agent.agent_id or handoff:
                        raise ValueError("Repeated handoff is not allowed")
                    fresh = await retrieve(session, request.message, target.tenants)
                    verdict = evidence_for(fresh, target.min_similarity, city)
                    if verdict.abstain:
                        return await persist(
                            session,
                            chat_session,
                            request,
                            agent,
                            "ABSTAINED",
                            "No verified specialist information supports this question.",
                            [],
                            "live",
                            cta="file_complaint",
                            started=started,
                        )
                    agent = target
                    supported = {h.chunk_id for h in verdict.usable_hits}
                    hits = [h for h in fresh if str(h.chunk_id) in supported]
                    handoff = {"agentId": target.agent_id, "name": target.display_name}
                    chat_session.agent_id = target.agent_id
                    history = [{"role": "user", "content": request.message}]
                    break
                if name == "search_schemes":
                    found = await retrieve(session, args["query"] or request.message, agent.tenants)
                    verdict = evidence_for(found, agent.min_similarity, city)
                    if verdict.abstain:
                        result = {"error": "No verified scheme information supports this search"}
                    else:
                        ids = {h.chunk_id for h in verdict.usable_hits}
                        hits = [h for h in found if str(h.chunk_id) in ids]
                        result = {"passages": [h.text for h in hits]}
                else:
                    # Invariant 2: the LLM may *select* a domain tool, but it executes under the
                    # identity of its owning specialist, never as the main agent.
                    from src.agent.tool_registry import TOOL_OWNERS, call_tool

                    result = await call_tool(TOOL_OWNERS[name], name, args, principal.user_id)
                    used_tool_fallback = used_tool_fallback or result.get("served") == "fallback"
            except (ValueError, KeyError, TypeError, HTTPException) as exc:
                result = {"error": str(exc)}
            except Exception:
                used_tool_fallback = True
                result = {"error": "Tool temporarily unavailable"}
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", "unknown"),
                    "content": json.dumps(result, ensure_ascii=False)[:10000],
                }
            )
    return await persist(
        session,
        chat_session,
        request,
        agent,
        "UNAVAILABLE",
        "The tool-step limit was reached. Please simplify the request.",
        [],
        "fallback",
        started=started,
    )


async def persist_turn(
    session: AsyncSession,
    chat_session: ChatSession,
    request: ChatRequest,
    agent: AgentConfig,
    status: str,
    answer: str,
    hits: list[RetrievalHit],
    served: str,
    *,
    cta: str | None = None,
    provider: str | None = None,
    pending_action: PendingActionView | None = None,
    handoff: dict | None = None,
    started: float | None = None,
    plan: list | None = None,
    tool_calls: list | None = None,
    action_data: dict | None = None,
    client_actions: list | None = None,
) -> AgentResponse:
    sources = [
        h if isinstance(h, Source) else Source(
            docId=str(h.doc_id),
            title=h.title,
            url=h.source_url,
            excerpt=h.text[:500],
            fetchedAt=h.fetched_at,
            stale=(utcnow() - h.fetched_at).days >= settings.source_freshness_days,
        )
        for h in hits
    ]
    hits = [h for h in hits if not isinstance(h, Source)]
    message_id = uuid4()
    response = AgentResponse(
        sessionId=chat_session.session_id,
        messageId=message_id,
        status=status,
        answer=answer,
        agent=AgentInfo(id=agent.agent_id, name=agent.display_name),
        sources=sources,
        cta=cta,
        pendingAction=pending_action,
        handoff=handoff,
        served=served,
        plan=plan,
        toolCalls=tool_calls,
        actionData=action_data,
        clientActions=client_actions,
    )
    session.add(
        ChatMessage(
            session_id=chat_session.session_id,
            role="user",
            content=request.message,
            status="RECEIVED",
            request_id=None,
            meta={},
        )
    )
    await session.flush()
    session.add(
        ChatMessage(
            message_id=message_id,
            session_id=chat_session.session_id,
            role="assistant",
            content=answer,
            status=status,
            request_id=request.requestId,
            meta={
                "request": request.model_dump(mode="json"),
                "response": response.model_dump(mode="json"),
                "provider": provider,
                "latency_ms": round((time.monotonic() - (started or time.monotonic())) * 1000, 2),
                "vector_scores": [h.vector_score for h in hits],
            },
        )
    )
    await session.flush()
    for rank, hit in enumerate(hits, 1):
        session.add(
            MessageSource(
                message_id=message_id,
                chunk_id=hit.chunk_id,
                rank=rank,
                relevance_score=hit.vector_score,
                excerpt=hit.text[:500],
            )
        )
    chat_session.updated_at = utcnow()
    await session.commit()
    return response


async def confirm_action(
    session: AsyncSession, principal: Principal, token: str
) -> ConfirmResponse:
    try:
        result = await session.execute(
            update(PendingAction)
            .where(
                PendingAction.token == token,
                PendingAction.user_id == principal.user_id,
                PendingAction.status == "pending",
                PendingAction.expires_at > utcnow(),
            )
            .values(status="executing")
            .returning(PendingAction)
        )
        action = result.scalar_one_or_none()
        if not action:
            return ConfirmResponse(
                status="rejected", detail="Action is invalid, expired, or already used"
            )
        # Commit the claim before I/O; crashes cannot cause a second adapter invocation.
        await session.commit()
        try:
            agent = await get_agent(session, action.agent_id)
            if (
                action.tool != "create_complaint"
                or action.tool not in agent.tools
                or not secrets.compare_digest(args_hash(action.args), action.args_hash)
            ):
                raise ValueError("Action authorization or integrity check failed")
            from src.agent.media import photo_for

            result_data = await execute_complaint(action.args, token, principal.user_id, await photo_for(session, token))
            action.status = "executed"
            action.result_ref = str(result_data["trackingId"])
            result = ConfirmResponse(status="executed", result=result_data)
        except Exception:
            action.status = "failed"
            result = ConfirmResponse(
                status="failed",
                detail="Action could not be completed; it will not be retried automatically",
            )
        session.add(
            AuditLog(
                actor=principal.user_id,
                agent_id=action.agent_id,
                event=f"action_{action.status}",
                detail={"tool": action.tool, "token": token},
            )
        )
        await session.commit()
        return result
    except Exception:
        from src.agent.offline import offline_confirm_action
        return await offline_confirm_action(principal, token)


async def cancel_action(session: AsyncSession, principal: Principal, token: str) -> ConfirmResponse:
    try:
        result = await session.execute(
            update(PendingAction)
            .where(
                PendingAction.token == token,
                PendingAction.user_id == principal.user_id,
                PendingAction.status == "pending",
            )
            .values(status="cancelled")
            .returning(PendingAction.token)
        )
        if not result.scalar_one_or_none():
            return ConfirmResponse(status="rejected", detail="Action is invalid or already completed")
        session.add(
            AuditLog(actor=principal.user_id, event="action_cancelled", detail={"token": token})
        )
        await session.commit()
        return ConfirmResponse(status="cancelled", detail="Action cancelled")
    except Exception:
        from src.agent.offline import offline_cancel_action
        return offline_cancel_action(principal, token)
