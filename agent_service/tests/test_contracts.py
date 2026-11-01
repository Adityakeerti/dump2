from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agent.schemas import ChatRequest
from src.agent.tools import ComplaintArgs, args_hash, tool_schemas
from src.auth.dependencies import _decode
from src.config import Settings, settings
from src.knowledge.embeddings import DeterministicEmbedder
from src.knowledge.schemas import DocumentMetadata
from src.main import app
from src.models import utcnow


def test_request_rejects_client_tenant_and_user():
    for extra in (
        {"tenant_id": "municipal"},
        {"user_id": "victim"},
        {"context": {"tenants": ["municipal"]}},
    ):
        with pytest.raises(ValidationError):
            ChatRequest(requestId=uuid4(), message="Hello", **extra)


def test_whitespace_and_language_validation():
    with pytest.raises(ValidationError):
        ChatRequest(requestId=uuid4(), message="   ")
    with pytest.raises(ValidationError):
        ChatRequest(requestId=uuid4(), message="Hello", language="xx")


def test_jwt_rejects_expiry_wrong_signature_and_missing_claims():
    for claims, key in [
        (
            {"sub": "alice", "iat": utcnow(), "exp": utcnow() - timedelta(seconds=10)},
            settings.jwt_secret.get_secret_value(),
        ),
        (
            {"sub": "alice", "iat": utcnow(), "exp": utcnow() + timedelta(hours=1)},
            "wrong-signature-key-at-least-32-characters",
        ),
        ({"sub": "alice"}, settings.jwt_secret.get_secret_value()),
    ]:
        token = jwt.encode(claims, key, algorithm="HS256")
        with pytest.raises(HTTPException) as error:
            _decode(token)
        assert error.value.status_code == 401


def test_auth_is_required_and_admin_is_enforced():
    with TestClient(app) as client:
        assert client.get("/api/agent/personas").status_code == 401
        token = client.post("/api/auth/dev-token", json={"user_id": "alice"}).json()["token"]
        assert (
            client.get(
                "/api/knowledge/docs", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 403
        )
        assert (
            client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
                "user_id"
            ]
            == "alice"
        )


def test_demo_hash_never_silently_enabled_for_production():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, demo_mode=False, use_sentence_transformer=False)
    query = DeterministicEmbedder().embed("query: identity documents")
    passage = DeterministicEmbedder().embed("passage: identity documents")
    assert query == passage
    assert len(query) == 384


def test_document_requires_timezone_and_valid_metadata():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            tenant_id="public",
            title="x",
            publisher="gov",
            jurisdiction="national",
            language="en",
            expires_at="2027-01-01T00:00:00",
        )


def test_action_hash_is_canonical_and_validated():
    assert args_hash({"a": 1, "b": 2}) == args_hash({"b": 2, "a": 1})
    with pytest.raises(ValidationError):
        ComplaintArgs(category="roads", location="", description="pothole")
    assert tool_schemas(["unknown_tool"]) == []


def test_openapi_has_all_service_routes():
    paths = app.openapi()["paths"]
    for path in (
        "/api/agent/chat",
        "/api/agent/voice",
        "/api/agent/personas",
        "/api/agent/sessions",
        "/api/knowledge/docs",
        "/api/admin/stats",
        "/api/agent/actions/{token}/confirm",
    ):
        assert path in paths
