"""Local area agents (persona + web search + LLM) and the main agent's map-tap briefing."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.agent import local_agent, web_search
from src.agent.local_agent import AvatarContext, LocalChatRequest, PlaceRequest, needs_main_agent
from src.agent.orchestrator import supervisor
from src.auth.schemas import Principal
from src.main import app

AVATAR = AvatarContext(handle="amit", name="Amit", title="Paltan Bazaar shopping guide", persona="TRANSIT",
                       intro="I help shoppers find their way around Paltan Bazaar.", latitude=30.3226, longitude=78.0436)


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    async def gen(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text="Paltan Bazaar opens around 10 AM [1].", provider="groq", fallback=False)

    monkeypatch.setattr(local_agent, "generate_with_failover", gen)
    return calls


@pytest.mark.parametrize("message,escalate", [
    ("Accident near Clock Tower, two people injured, send an ambulance", True),
    ("Please file a complaint about a pothole on Subhash Road", True),
    ("What are the best shops for woollens in Paltan Bazaar?", False),
    ("Is the market open on Sunday?", False),
])
def test_main_agent_keeps_emergencies_and_complaints(message, escalate):
    assert needs_main_agent(message) is escalate


async def test_local_agent_uses_area_prompt_web_search_and_cites(monkeypatch, fake_llm):
    async def search(query, max_results=5):
        assert "Paltan Bazaar" in query and "Dehradun" in query
        return [web_search.WebResult("Paltan Bazaar guide", "https://example.org/paltan", "Shops open 10am to 9pm.")]

    monkeypatch.setattr(web_search, "search", search)
    res = await local_agent.local_agent_answer(
        Principal(user_id="u1"), LocalChatRequest(message="When does the market open?", avatar=AVATAR)
    )
    system = fake_llm[0]["system"]
    assert "You are Amit, Paltan Bazaar shopping guide" in system
    assert "untrusted third-party text" in system and "[1] Paltan Bazaar guide" in system
    assert fake_llm[0]["context"] == []  # web text must not be labelled as verified municipal context
    assert res.agent.id == "local:amit" and res.sources[0].url == "https://example.org/paltan"
    assert [s.executor for s in res.plan] == ["local_agent"] * 3 and res.plan[1].status == "completed"
    assert res.toolCalls[0].tool == "web_search"


async def test_local_agent_without_web_results_still_answers(monkeypatch, fake_llm):
    async def search(query, max_results=5):
        return []

    monkeypatch.setattr(web_search, "search", search)
    res = await local_agent.local_agent_answer(Principal(user_id="u1"), LocalChatRequest(message="Any tips?", avatar=AVATAR))
    assert "No live web results" in fake_llm[0]["system"]
    assert res.plan[1].status == "failed" and res.answer


async def test_place_insight_delegates_and_composes(monkeypatch):
    seen = {}

    async def gen(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text="Clock Tower is the heart of Dehradun.", provider="groq", fallback=False)

    monkeypatch.setattr(local_agent, "generate_with_failover", gen)
    res = await local_agent.place_insight(Principal(user_id="u1"), PlaceRequest(latitude=30.3243, longitude=78.0418),
                                          supervisor)
    assert [s.executor for s in res.plan] == ["main_voice_agent", "city_pulse", "knowledge_specialist", "main_voice_agent"]
    assert res.actionData["place"]["label"] == "Clock Tower"
    callers = {c.tool: c.caller for c in res.toolCalls}
    assert callers["reverse_geocode_coordinates"] == "main_voice_agent"
    assert callers["get_ward_councillor_info"] == "knowledge_specialist"
    assert any(c.caller == "city_pulse" for c in res.toolCalls)
    assert "Clock Tower" in seen["context"][0]


def test_endpoints_require_auth_and_route(monkeypatch, fake_llm):
    async def search(query, max_results=5):
        return []

    monkeypatch.setattr(web_search, "search", search)
    with TestClient(app) as client:
        assert client.post("/api/agent/local-chat", json={"message": "hi", "avatar": AVATAR.model_dump()}).status_code == 401
        token = client.post("/api/auth/dev-token", json={"user_id": "u9"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/agent/local-chat", headers=h, json={"message": "Best chai nearby?", "avatar": AVATAR.model_dump()})
        assert r.status_code == 200 and r.json()["agent"]["id"] == "local:amit"
        r = client.post("/api/agent/local-chat", headers=h,
                        json={"message": "Accident here, people injured, send an ambulance now", "avatar": AVATAR.model_dump()})
        assert r.status_code == 200
        body = r.json()
        assert body["plan"][0]["executor"] == "local_agent" and "escalated" in body["plan"][0]["action"]
        assert any(s["executor"] == "emergency_traffic" for s in body["plan"])
        r = client.post("/api/agent/place", headers=h, json={"latitude": 30.3243, "longitude": 78.0418})
        assert r.status_code == 200 and r.json()["actionData"]["place"]["label"] == "Clock Tower"


def test_sample_sections_never_reach_the_llm():
    briefing = "# Pulse\n### 🌧️ Weather\n- clear\n### 🚨 Active City Alerts & Advisories (sample data)\n- fake alert\n" \
               "### 📅 Upcoming Civic & Community Events (sample data)\n- fake mela\n📊 2 alerts | 3 events"
    text, dropped = local_agent._without_sample_sections(briefing)
    assert dropped and "clear" in text and "fake" not in text and "📊" not in text


@pytest.mark.parametrize("title,expected", [
    ("Traffic warden, Kargi Chowk", "Kargi Chowk"),
    ("Graphic Era & Bell Road student guide", "Graphic Era & Bell Road"),
    ("Mindrolling Monastery & Clement Town heritage guide", "Mindrolling Monastery & Clement Town"),
    ("ISBT transit help desk", "ISBT"),
    ("Paltan Bazaar shopping guide", "Paltan Bazaar"),
    ("Ward grievance desk, Mohabbewala", "Mohabbewala"),
])
def test_place_hint_from_avatar_title(title, expected):
    assert local_agent.place_hint(title) == expected


def test_gazetteer_knows_the_new_agent_spots():
    from src.agent.integrations import gazetteer_nearest
    assert gazetteer_nearest(30.26802, 77.99612)[0] == "graphic era"
    assert gazetteer_nearest(30.28837, 78.02394)[0] == "kargi chowk"
