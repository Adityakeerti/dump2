"""Run with TEST_DATABASE_URL pointing at a dedicated database named *_test.

These tests apply Alembic migrations and clear service tables in that test DB.
They never use the configured application database as an implicit fallback.
"""

import asyncio
import os
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.agent.schemas import ChatRequest
from src.agent.service import chat, confirm_action
from src.agent.tools import args_hash
from src.auth.schemas import Principal
from src.knowledge.embeddings import get_embedder
from src.knowledge.retrieval import retrieve
from src.models import (
    AgentConfig,
    ChatSession,
    KnowledgeChunk,
    KnowledgeDocument,
    PendingAction,
    utcnow,
)

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not URL, reason="TEST_DATABASE_URL is unset; PostgreSQL+pgvector is required"
)


@pytest_asyncio.fixture
async def factory():
    from sqlalchemy.engine import make_url

    assert make_url(URL).database.endswith("_test"), (
        "Tests require a dedicated database ending in _test"
    )
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": URL},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    engine = create_async_engine(URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE agent.message_source, agent.chat_message, agent.pending_action, agent.chat_session, agent.audit_log, agent.answer_cache, ai.knowledge_chunk, ai.knowledge_document, agent.agent_config CASCADE"
            )
        )
    yield factory
    await engine.dispose()


async def setup_agents(factory):
    async with factory() as session:
        session.add(
            AgentConfig(
                agent_id="general",
                tier="general",
                display_name="General",
                system_prompt="verified only",
                tenants=["public"],
                tools=["handoff"],
                min_similarity=0.1,
            )
        )
        session.add(
            AgentConfig(
                agent_id="municipal",
                tier="professional",
                display_name="Municipal",
                system_prompt="verified only",
                tenants=["public", "municipal"],
                tools=["create_complaint"],
                min_similarity=0.1,
            )
        )
        await session.commit()


async def test_sql_tenant_isolation_and_model_mapping(factory):
    await setup_agents(factory)
    async with factory() as session:
        for tenant in ("public", "municipal"):
            document = KnowledgeDocument(
                tenant_id=tenant,
                title=tenant,
                publisher="test",
                jurisdiction="national",
                language="en",
                verification_status="verified",
                ingestion_status="ready",
                content_hash=tenant.ljust(64, "0"),
            )
            session.add(document)
            await session.flush()
            session.add(
                KnowledgeChunk(
                    doc_id=document.doc_id,
                    tenant_id=tenant,
                    chunk_index=0,
                    text="identity required",
                    lang="en",
                    embedding=get_embedder().embed("passage: identity required"),
                    embed_model=get_embedder().name,
                )
            )
        await session.commit()
        results = await retrieve(session, "identity required", ["public"])
        assert results
        assert all(h.tenant_id == "public" for h in results)


async def test_action_integrity_expiry_owner_and_concurrent_confirm(factory):
    await setup_agents(factory)
    args = {"category": "roads", "location": "Ward 2", "description": "Streetlight is broken"}
    async with factory() as session:
        owner = ChatSession(user_id="alice", agent_id="municipal")
        session.add(owner)
        await session.flush()
        for token, user, expiry, digest in [
            ("valid", "alice", utcnow() + timedelta(minutes=5), args_hash(args)),
            ("expired", "alice", utcnow() - timedelta(seconds=1), args_hash(args)),
            ("tampered", "alice", utcnow() + timedelta(minutes=5), "0" * 64),
        ]:
            session.add(
                PendingAction(
                    token=token,
                    session_id=owner.session_id,
                    user_id=user,
                    agent_id="municipal",
                    tool="create_complaint",
                    args=args,
                    args_hash=digest,
                    summary="test",
                    expires_at=expiry,
                )
            )
        await session.commit()

    async def confirm(token, user="alice"):
        async with factory() as session:
            return await confirm_action(session, Principal(user_id=user), token)

    assert (await confirm("valid", "mallory")).status == "rejected"
    assert (await confirm("expired")).status == "rejected"
    assert (await confirm("tampered")).status == "failed"
    outcomes = await asyncio.gather(confirm("valid"), confirm("valid"))
    assert sorted(r.status for r in outcomes) == ["executed", "rejected"]


async def test_chat_idempotency_and_zero_llm_abstain(factory, monkeypatch):
    from unittest.mock import AsyncMock

    from src.agent import service

    await setup_agents(factory)
    generation = AsyncMock()
    monkeypatch.setattr(service, "generate_with_failover", generation)
    request = ChatRequest(requestId=uuid4(), message="Question without any evidence")
    async with factory() as session:
        first = await chat(session, Principal(user_id="alice"), request)
    async with factory() as session:
        second = await chat(session, Principal(user_id="alice"), request)
    assert first == second
    assert first.status == "ABSTAINED"
    generation.assert_not_called()


async def test_lexical_only_candidate_survives_rank_fusion(factory):
    await setup_agents(factory)
    async with factory() as session:
        document = KnowledgeDocument(tenant_id="public", title="Lexical fixture", publisher="test", jurisdiction="national", language="en", verification_status="verified", ingestion_status="ready", content_hash="a"*64)
        session.add(document)
        await session.flush()
        query_vector = get_embedder().embed("query: specialword")
        empty_index = next(i for i, value in enumerate(query_vector) if value == 0)
        orthogonal = [0.0]*384
        orthogonal[empty_index] = 1.0
        for index in range(25):
            session.add(KnowledgeChunk(doc_id=document.doc_id, tenant_id="public", chunk_index=index, text="ordinary filler", lang="en", embedding=query_vector, embed_model=get_embedder().name))
        target = KnowledgeChunk(doc_id=document.doc_id, tenant_id="public", chunk_index=25, text="specialword eligibility rule", lang="en", embedding=orthogonal, embed_model=get_embedder().name)
        session.add(target)
        await session.commit()
        hits = await retrieve(session, "specialword", ["public"])
        lexical_only = next(h for h in hits if h.chunk_id == target.chunk_id)
        assert lexical_only.lexical_rank == 1
        assert lexical_only.vector_rank is None


async def test_ingestion_is_tenant_scoped_idempotent_and_parse_failure_is_saved(factory, monkeypatch, tmp_path):
    from sqlalchemy import func

    from src.knowledge import ingestion
    monkeypatch.setattr(ingestion, "session_factory", factory)
    path = tmp_path / "source.txt"
    path.write_text("# Eligibility\n\nIdentity proof is required.", encoding="utf-8")
    async with factory() as session:
        first = await ingestion.ingest_file(session, path, tenant_id="public")
        second = await ingestion.ingest_file(session, path, tenant_id="public")
        municipal = await ingestion.ingest_file(session, path, tenant_id="municipal")
        assert first.doc_id == second.doc_id
        assert first.doc_id != municipal.doc_id
        assert first.ingestion_status == "ready"
        assert first.verification_status == "unverified"
        count = await session.scalar(select(func.count()).select_from(KnowledgeChunk).where(KnowledgeChunk.doc_id == first.doc_id))
        assert count == 1
        bad = tmp_path / "bad.txt"
        bad.write_bytes(b"\xff\xfe\xff")
        failed = await ingestion.ingest_file(session, bad, tenant_id="public")
        assert failed.ingestion_status == "failed"
        assert failed.ingestion_error
