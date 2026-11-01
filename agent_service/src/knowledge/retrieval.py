from asyncio import to_thread
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.knowledge.embeddings import get_embedder


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: UUID
    doc_id: UUID
    tenant_id: str
    text: str
    section: str | None
    vector_score: float
    vector_rank: int | None
    lexical_rank: int | None
    fused_score: float
    jurisdiction: str
    verified: bool
    expires_at: datetime | None
    title: str
    source_url: str | None
    fetched_at: datetime


HYBRID_SQL = text("""
WITH eligible AS MATERIALIZED (
 SELECT c.*, d.title, d.source_url, d.fetched_at, d.expires_at, d.jurisdiction
 FROM ai.knowledge_chunk c JOIN ai.knowledge_document d ON d.doc_id=c.doc_id
 WHERE c.tenant_id = ANY(CAST(:tenants AS text[]))
   AND d.tenant_id = ANY(CAST(:tenants AS text[]))
   AND d.verification_status='verified' AND d.ingestion_status='ready'
   AND (d.expires_at IS NULL OR d.expires_at > now())
   AND c.embed_model=:embed_model
), vector_leg AS (
 SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> CAST(:embedding AS vector), chunk_id) AS vector_rank
 FROM eligible ORDER BY embedding <=> CAST(:embedding AS vector), chunk_id LIMIT 20
), lexical_leg AS (
 SELECT chunk_id, row_number() OVER (ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :query)) DESC, chunk_id) AS lexical_rank
 FROM eligible WHERE tsv @@ plainto_tsquery('simple', :query)
 ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :query)) DESC, chunk_id LIMIT 20
), fused AS (
 SELECT COALESCE(v.chunk_id,l.chunk_id) AS chunk_id, v.vector_rank, l.lexical_rank,
 COALESCE(1.0/(60+v.vector_rank),0) + COALESCE(1.0/(60+l.lexical_rank),0) AS fused_score
 FROM vector_leg v FULL OUTER JOIN lexical_leg l ON v.chunk_id=l.chunk_id
)
SELECT e.chunk_id,e.doc_id,e.tenant_id,e.text,e.section,e.title,e.source_url,
 e.fetched_at,e.expires_at,e.jurisdiction,true AS verified,
 1-(e.embedding <=> CAST(:embedding AS vector)) AS vector_score,
 f.vector_rank,f.lexical_rank,f.fused_score::double precision
FROM fused f JOIN eligible e ON e.chunk_id=f.chunk_id
ORDER BY f.fused_score DESC,e.chunk_id LIMIT :limit
""")


async def retrieve(
    session: AsyncSession, query: str, tenants: list[str], limit: int = 6
) -> list[RetrievalHit]:
    if not tenants:
        return []
    embedder = await to_thread(get_embedder)
    embedding = await to_thread(embedder.embed, f"query: {query}")
    rows = (
        await session.execute(
            HYBRID_SQL,
            {
                "embedding": str(embedding),
                "query": query,
                "tenants": tenants,
                "limit": min(max(limit, 1), 20),
                "embed_model": embedder.name,
            },
        )
    ).mappings()
    return [RetrievalHit(**dict(row)) for row in rows]
