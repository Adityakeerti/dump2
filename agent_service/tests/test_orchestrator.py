from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.agent import service
from src.agent.schemas import ChatRequest
from src.auth.schemas import Principal
from src.models import AgentConfig


@pytest.mark.asyncio
async def test_abstention_makes_zero_llm_calls(monkeypatch):
    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    agent = AgentConfig(
        agent_id="general",
        tier="general",
        display_name="City",
        system_prompt="verified only",
        tenants=["public"],
        tools=["handoff"],
        min_similarity=0.8,
    )
    monkeypatch.setattr(service, "get_agent", AsyncMock(return_value=agent))
    retrieve = AsyncMock(return_value=[])
    generate = AsyncMock()
    monkeypatch.setattr(service, "retrieve", retrieve)
    monkeypatch.setattr(service, "generate_with_failover", generate)
    response = await service.chat(
        session,
        Principal(user_id="alice"),
        ChatRequest(requestId=uuid4(), message="Unsupported question"),
    )
    assert response.status == "ABSTAINED"
    assert response.sources == []
    assert response.cta == "file_complaint"
    generate.assert_not_called()
    assert retrieve.call_args.args[2] == ["public"]


@pytest.mark.asyncio
async def test_request_replay_cannot_leak_another_users_response():
    from fastapi import HTTPException

    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=SimpleNamespace(session_id=uuid4()))
    session.get = AsyncMock(return_value=SimpleNamespace(user_id="victim"))
    with pytest.raises(HTTPException) as error:
        await service.chat(
            session,
            Principal(user_id="attacker"),
            ChatRequest(requestId=uuid4(), message="question"),
        )
    assert error.value.status_code == 409


def fake_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def retrieval_hit(tenant="public"):
    from src.knowledge.retrieval import RetrievalHit
    from src.models import utcnow

    return RetrievalHit(
        chunk_id=uuid4(),
        doc_id=uuid4(),
        tenant_id=tenant,
        text="Verified complaint instructions at Ward 2",
        section="How to file",
        vector_score=0.99,
        vector_rank=1,
        lexical_rank=1,
        fused_score=0.03,
        jurisdiction="national",
        verified=True,
        expires_at=None,
        title="Complaint procedure",
        source_url="https://example.gov.in/procedure",
        fetched_at=utcnow(),
    )


async def test_supported_answer_sources_are_from_chunks(monkeypatch):
    from src.models import MessageSource
    from src.providers.base import GeneratedText

    session = fake_session()
    agent = AgentConfig(
        agent_id="general",
        tier="general",
        display_name="City",
        system_prompt="verified only",
        tenants=["public"],
        tools=[],
        min_similarity=0.8,
    )
    hit = retrieval_hit()
    monkeypatch.setattr(service, "get_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "retrieve", AsyncMock(return_value=[hit]))
    monkeypatch.setattr(service, "cached_answer", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "store_answer", AsyncMock())
    monkeypatch.setattr(
        service,
        "generate_with_failover",
        AsyncMock(return_value=GeneratedText("A supported answer", "groq")),
    )
    response = await service.chat(
        session, Principal(user_id="alice"), ChatRequest(requestId=uuid4(), message="How to file?")
    )
    assert response.status == "ANSWERED"
    assert response.sources[0].docId == str(hit.doc_id)
    links = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], MessageSource)
    ]
    assert links[0].chunk_id == hit.chunk_id
    assert links[0].chunk_id != hit.doc_id


async def test_action_only_creates_pending_row(monkeypatch):
    import json

    from src.models import PendingAction
    from src.providers.base import GeneratedText

    session = fake_session()
    agent = AgentConfig(
        agent_id="municipal",
        tier="professional",
        display_name="Municipal",
        system_prompt="verified only",
        tenants=["public", "municipal"],
        tools=["create_complaint"],
        min_similarity=0.8,
    )
    args = {"category": "roads", "location": "Ward 2", "description": "Streetlight is broken"}
    call = {"id": "call1", "function": {"name": "create_complaint", "arguments": json.dumps(args)}}
    monkeypatch.setattr(service, "get_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "retrieve", AsyncMock(return_value=[retrieval_hit()]))
    monkeypatch.setattr(service, "cached_answer", AsyncMock(return_value=None))
    adapter = AsyncMock()
    monkeypatch.setattr(service, "execute_complaint", adapter)
    monkeypatch.setattr(
        service,
        "generate_with_failover",
        AsyncMock(return_value=GeneratedText("", "groq", False, [call])),
    )
    response = await service.chat(
        session,
        Principal(user_id="alice"),
        ChatRequest(requestId=uuid4(), agentId="municipal", message="File a complaint"),
    )
    assert response.status == "ACTION_PENDING"
    assert response.pendingAction.token
    assert any(isinstance(c.args[0], PendingAction) for c in session.add.call_args_list)
    adapter.assert_not_called()


async def test_unknown_tools_are_rejected_and_loop_is_capped(monkeypatch):
    from src.providers.base import GeneratedText

    session = fake_session()
    agent = AgentConfig(
        agent_id="general",
        tier="general",
        display_name="City",
        system_prompt="rules",
        tenants=["public"],
        tools=[],
        min_similarity=0.8,
    )
    monkeypatch.setattr(service, "get_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "retrieve", AsyncMock(return_value=[retrieval_hit()]))
    monkeypatch.setattr(service, "cached_answer", AsyncMock(return_value=None))
    generated = AsyncMock(
        return_value=GeneratedText(
            "",
            "groq",
            False,
            [{"id": "call1", "function": {"name": "delete_database", "arguments": "{}"}}],
        )
    )
    monkeypatch.setattr(service, "generate_with_failover", generated)
    adapter = AsyncMock()
    monkeypatch.setattr(service, "read_tool", adapter)
    response = await service.chat(
        session, Principal(user_id="alice"), ChatRequest(requestId=uuid4(), message="How to file?")
    )
    assert response.status == "UNAVAILABLE"
    assert generated.await_count == 3
    adapter.assert_not_called()


async def test_handoff_retrieves_again_in_target_tenant(monkeypatch):
    from src.providers.base import GeneratedText

    session = fake_session()
    general = AgentConfig(
        agent_id="general",
        tier="general",
        display_name="City",
        system_prompt="general",
        tenants=["public"],
        tools=["handoff"],
        min_similarity=0.8,
    )
    municipal = AgentConfig(
        agent_id="municipal",
        tier="professional",
        display_name="Municipal",
        system_prompt="specialist",
        tenants=["public", "municipal"],
        tools=[],
        min_similarity=0.8,
    )
    monkeypatch.setattr(service, "get_agent", AsyncMock(side_effect=[general, general, municipal]))
    public_hit, target_hit = retrieval_hit(), retrieval_hit("municipal")
    lookup = AsyncMock(side_effect=[[public_hit], [target_hit]])
    monkeypatch.setattr(service, "retrieve", lookup)
    monkeypatch.setattr(service, "cached_answer", AsyncMock(return_value=None))
    generated = AsyncMock(
        side_effect=[
            GeneratedText(
                "",
                "groq",
                False,
                [
                    {
                        "id": "handoff1",
                        "function": {"name": "handoff", "arguments": '{"agent_id":"municipal"}'},
                    }
                ],
            ),
            GeneratedText("Specialist answer", "groq"),
        ]
    )
    monkeypatch.setattr(service, "generate_with_failover", generated)
    response = await service.chat(
        session, Principal(user_id="alice"), ChatRequest(requestId=uuid4(), message="How to file?")
    )
    assert lookup.call_args_list[1].args[2] == ["public", "municipal"]
    assert generated.call_args_list[1].kwargs["context"] == [target_hit.text]
    assert response.sources[0].docId == str(target_hit.doc_id)
    assert response.handoff["agentId"] == "municipal"
