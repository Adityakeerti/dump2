"""Complaint photos (stored, validated, sent on confirm) and local business recommendations."""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.agent import app_control, integrations as ix, media
from src.agent.offline import offline_chat, offline_confirm_action
from src.agent.schemas import ChatRequest
from src.auth.schemas import Principal
from src.config import settings
from src.main import app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
BUSINESSES = [
    {"name": "Test Bakery", "category": "bakery", "locality": "Rajpur Road / Jakhan", "description": "Fresh bread.",
     "latitude": 30.35, "longitude": 78.06, "distanceMeters": 1200.0},
    {"name": "Test Cafe", "category": "cafe", "locality": "Paltan Bazaar / Clock Tower", "description": "Coffee.",
     "latitude": 30.32, "longitude": 78.04, "distanceMeters": 2500.0},
]


def test_sniff_rejects_non_images():
    assert media.sniff(JPEG) == ("image/jpeg", "jpg")
    assert media.sniff(b"\x89PNG\r\n\x1a\n" + b"0" * 8) == ("image/png", "png")
    assert media.sniff(b"MZ\x90\x00 not an image") is None


async def test_sewage_draft_suggests_photo_and_confirm_sends_it(monkeypatch):
    monkeypatch.setattr(settings, "complaint_service_url", "http://complaint-module:8001")
    sent = {}

    async def fake_create(args, lat, lng, photo=None):
        sent["photo"] = photo
        return {"tracking_id": "CMP-2026-PHOTO1", "status": "WORKER_ASSIGNED", "assigned_worker": {"name": "R"}}

    monkeypatch.setattr(ix, "complaint_create", fake_create)
    who = Principal(user_id="photo-user")
    res = await offline_chat(who, ChatRequest(requestId=uuid4(), message=(
        "Please file a complaint: sewage overflowing from a manhole on Rajpur Road near Clock Tower")), time.monotonic())
    assert res.pendingAction and res.pendingAction.photoSuggested is True
    token = res.pendingAction.token
    with pytest.raises(Exception):  # someone else cannot attach to this draft
        await media.attach_photo(None, Principal(user_id="intruder"), token, JPEG)  # type: ignore[arg-type]
    out = await media.attach_photo(_NoDb(), who, token, JPEG)
    assert out["contentType"] == "image/jpeg"
    done = await offline_confirm_action(who, token)
    assert done.status == "executed" and done.result["photoAttached"] is True
    assert sent["photo"][1] == "image/jpeg" and sent["photo"][0] == JPEG


class _NoDb:
    """A session whose queries fail, like the offline engine without Postgres."""

    async def scalar(self, *a, **k):
        raise RuntimeError("no database")

    async def rollback(self):
        return None


async def test_business_recommendation_routes_to_knowledge_desk(monkeypatch):
    async def fake_businesses(lat, lng, **kw):
        return [b for b in BUSINESSES if not kw.get("category") or b["category"] == kw["category"]]

    monkeypatch.setattr(ix, "core_businesses", fake_businesses)
    assert ("data", (("kind", "businesses"),)) in [
        (i.kind, tuple(sorted(i.params.items()))) for i in app_control.parse("recommend a good bakery near me")]
    res = await offline_chat(Principal(user_id="biz"), ChatRequest(requestId=uuid4(), message="recommend a good bakery near me"),
                             time.monotonic())
    assert any(s.executor == "knowledge_specialist" and s.status == "completed" for s in res.plan)
    assert "Test Bakery" in res.answer and "Test Cafe" not in res.answer
    assert {"type": "navigate", "screen": "townhall"} in res.clientActions


def test_photo_endpoint_requires_auth_and_valid_image():
    with TestClient(app) as client:
        assert client.post("/api/agent/actions/x/photo", files={"file": ("a.jpg", JPEG, "image/jpeg")}).status_code == 401
        token = client.post("/api/auth/dev-token", json={"user_id": "u-photo"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        bad = client.post("/api/agent/actions/x/photo", headers=h, files={"file": ("a.jpg", b"not an image", "image/jpeg")})
        assert bad.status_code == 415
        missing = client.post("/api/agent/actions/unknown/photo", headers=h, files={"file": ("a.jpg", JPEG, "image/jpeg")})
        assert missing.status_code == 404
