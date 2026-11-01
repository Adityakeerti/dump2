"""Main agent controlling the citizen app: intent parsing and end-to-end client actions."""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.agent import app_control
from src.agent.offline import offline_chat
from src.agent.schemas import ChatRequest
from src.agent.tool_registry import TOOL_OWNERS
from src.auth.schemas import Principal
from src.main import app


def kinds(msg):
    return [(i.kind, tuple(sorted(i.params.items()))) for i in app_control.parse(msg)]


@pytest.mark.parametrize("msg,expected", [
    ("open settings", [("navigate", (("screen", "settings"),))]),
    ("show my saved avatars", [("navigate", (("screen", "saved"),))]),
    ("show my complaints", [("data", (("kind", "complaints"),)), ("navigate", (("screen", "townhall"),))]),
    ("latest notices please", [("data", (("kind", "notices"),)), ("navigate", (("screen", "updates"),))]),
    ("show Clock Tower on the map", [("focus_map", (("query", "Clock Tower"),))]),
    ("talk to Zoya", [("find_agent", (("name", "Zoya"),))]),
    ("switch to hindi", [("preference", (("language", "hi"),))]),
    ("mute", [("preference", (("voice_auto_play", False),))]),
    ("track CMP-2026-ABC123", [("navigate", (("screen", "complaint"), ("target_id", "CMP-2026-ABC123")))]),
])
def test_parse_app_intents(msg, expected):
    assert kinds(msg) == expected


def test_plain_civic_questions_are_not_app_commands():
    for msg in ["There is a pothole on Rajpur Road", "How do I apply for old age pension?", "Accident at Clock Tower"]:
        assert app_control.parse(msg) == []


async def chat(msg):
    return await offline_chat(Principal(user_id="citizen-app"), ChatRequest(requestId=uuid4(), message=msg), time.monotonic())


async def test_show_my_complaints_lists_and_navigates():
    res = await chat("show my complaints")
    assert [s.executor for s in res.plan][:2] == ["main_voice_agent", "civic_complaint"]
    assert {"type": "navigate", "screen": "townhall"} in res.clientActions
    assert all(TOOL_OWNERS[c.tool] == c.caller for c in res.toolCalls)


async def test_focus_map_and_preferences():
    res = await chat("show Clock Tower on the map")
    focus = next(a for a in res.clientActions if a["type"] == "focus_map")
    assert focus["label"] == "Clock Tower" and abs(focus["latitude"] - 30.3243) < 0.01
    assert "Showing Clock Tower on the map" in res.answer
    res = await chat("switch to hindi and mute")
    prefs = [a for a in res.clientActions if a["type"] == "set_preference"]
    assert {"type": "set_preference", "language": "hi"} in prefs
    assert {"type": "set_preference", "voiceAutoPlay": False} in prefs


async def test_notices_go_through_city_pulse():
    res = await chat("show the latest notices")
    pulse = next(s for s in res.plan if s.executor == "city_pulse")
    assert pulse.status == "completed"
    assert any(c.tool == "get_govt_notices" and c.caller == "city_pulse" for c in res.toolCalls)
    assert {"type": "navigate", "screen": "updates"} in res.clientActions


def test_assistant_endpoint_returns_client_actions():
    with TestClient(app) as client:
        assert client.post("/api/agent/assistant", json={"message": "open settings"}).status_code == 401
        token = client.post("/api/auth/dev-token", json={"user_id": "u-app"}).json()["token"]
        r = client.post("/api/agent/assistant", headers={"Authorization": f"Bearer {token}"},
                        json={"message": "open settings", "screen": "explore"})
        assert r.status_code == 200
        assert r.json()["clientActions"] == [{"type": "navigate", "screen": "settings"}]


def test_events_phrasings_route_to_city_pulse():
    from src.agent import app_control

    for msg in ("What is happening in Dehradun this month?", "any festivals coming up?", "what's on this weekend"):
        assert "events" in app_control.data_kinds(app_control.parse(msg)), msg


def test_core_events_are_normalised_for_the_briefing():
    from datetime import datetime, timedelta, timezone

    from src.agent.tool_registry import _core_event_item

    soon = datetime.now(timezone.utc) + timedelta(days=3)
    item = _core_event_item({"title": "Lit Fest", "startsAt": soon.isoformat(), "endsAt": (soon + timedelta(days=2)).isoformat(),
                             "venue": "Doon International School", "description": "Talks", "sourceUrl": "https://example.org"})
    assert item and item["location"] == "Doon International School" and " to " in item["date"]
    past = datetime.now(timezone.utc) - timedelta(days=5)
    assert _core_event_item({"title": "Old", "startsAt": past.isoformat()}) is None
