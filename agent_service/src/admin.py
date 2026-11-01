from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.tools import TOOL_MODELS
from src.auth.dependencies import admin_principal
from src.auth.schemas import Principal
from src.database import get_session
from src.models import AgentConfig, ChatMessage, KnowledgeDocument

router = APIRouter(prefix="/api/admin", tags=["admin"])


class PersonaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tier: str = Field(pattern="^(general|professional)$")
    display_name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1, max_length=8000)
    tenants: list[
        Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$")]
    ] = Field(min_length=1, max_length=20)
    tools: list[str] = Field(default_factory=list, max_length=20)
    min_similarity: float = Field(ge=-1, le=1)
    active: bool = True

    @field_validator("tools")
    @classmethod
    def allowed_tools(cls, value):
        if any(name not in TOOL_MODELS for name in value):
            raise ValueError("Unknown tool name")
        return value


@router.post("/personas/{agent_id}", response_model=PersonaConfig)
async def configure_persona(
    agent_id: str,
    payload: PersonaConfig,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(admin_principal)],
):
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,99}", agent_id):
        raise HTTPException(422, "Invalid agent identifier")
    if payload.tier == "general" and (
        payload.tenants != ["public"] or "create_complaint" in payload.tools
    ):
        raise HTTPException(
            422, "General personas may only read public data and cannot create complaints"
        )
    agent = await session.get(AgentConfig, agent_id)
    if agent:
        for key, value in payload.model_dump().items():
            setattr(agent, key, value)
    else:
        session.add(AgentConfig(agent_id=agent_id, **payload.model_dump()))
    await session.commit()
    return payload


@router.get("/stats")
async def stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(admin_principal)],
):
    counts = dict(
        (
            await session.execute(
                select(ChatMessage.status, func.count())
                .where(ChatMessage.role == "assistant")
                .group_by(ChatMessage.status)
            )
        ).all()
    )
    total = sum(counts.values())
    recent = (
        await session.scalars(
            select(ChatMessage)
            .where(ChatMessage.role == "assistant")
            .order_by(ChatMessage.created_at.desc())
            .limit(1000)
        )
    ).all()
    timings = sorted(float(m.meta.get("latency_ms", 0)) for m in recent)
    providers: dict[str, int] = {}
    cached = 0
    for message in recent:
        name = message.meta.get("provider") or "none"
        providers[name] = providers.get(name, 0) + 1
        cached += message.meta.get("response", {}).get("served") == "cache"
    return {
        "turns": total,
        "statusCounts": counts,
        "abstainRate": counts.get("ABSTAINED", 0) / total if total else 0,
        "cacheHitRate": cached / len(recent) if recent else 0,
        "providerShare": {k: v / len(recent) for k, v in providers.items()},
        "latencyMs": {
            "p50": timings[int((len(timings) - 1) * 0.5)] if timings else None,
            "p95": timings[int((len(timings) - 1) * 0.95)] if timings else None,
        },
        "sampleSize": len(recent),
        "documents": await session.scalar(select(func.count()).select_from(KnowledgeDocument)),
    }
