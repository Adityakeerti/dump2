import asyncio
import hashlib
import json
from datetime import timedelta

from sqlalchemy import select

from src.config import settings
from src.knowledge.embeddings import get_embedder
from src.models import AnswerCache, utcnow


def evidence_signature(agent, hits, language: str, city: str, user_id: str = "") -> str:
    payload = {
        "user": user_id,
        "agent": agent.agent_id,
        "prompt": agent.system_prompt,
        "threshold": agent.min_similarity,
        "tenants": sorted(agent.tenants),
        "tools": sorted(agent.tools),
        "language": language,
        "city": city,
        "chunks": sorted(str(h.chunk_id) for h in hits),
        "embed_model": get_embedder().name,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def cached_answer(
    session, query: str, agent, hits, language: str, city: str, user_id: str = ""
) -> str | None:
    embedding = await asyncio.to_thread(get_embedder().embed, "query: " + query)
    signature = evidence_signature(agent, hits, language, city, user_id)
    result = await session.scalar(
        select(AnswerCache)
        .where(
            AnswerCache.agent_id == agent.agent_id,
            AnswerCache.created_at > utcnow() - timedelta(seconds=settings.cache_ttl_seconds),
            AnswerCache.q_embedding.cosine_distance(embedding) <= 0.05,
            AnswerCache.answer["signature"].astext == signature,
        )
        .order_by(AnswerCache.q_embedding.cosine_distance(embedding))
        .limit(1)
    )
    return result.answer.get("text") if result else None


async def store_answer(
    session, query: str, answer: str, agent, hits, language: str, city: str, user_id: str = ""
) -> None:
    vector = await asyncio.to_thread(get_embedder().embed, "query: " + query)
    session.add(
        AnswerCache(
            agent_id=agent.agent_id,
            q_embedding=vector,
            answer={
                "text": answer,
                "signature": evidence_signature(agent, hits, language, city, user_id),
            },
        )
    )
