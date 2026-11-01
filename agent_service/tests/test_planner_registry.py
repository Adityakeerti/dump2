"""Planner decomposition, tool ownership (Invariant 2) and end-to-end delegation."""

import time
from uuid import uuid4

import pytest

from src.agent import integrations as ix
from src.agent.guardrails import QueryScope
from src.agent.offline import PENDING_ACTIONS, offline_chat, offline_confirm_action
from src.agent.planner import VoiceAgentPlanner
from src.agent.schemas import ChatRequest
from src.agent.tool_registry import (
    COMPLAINT,
    EMERGENCY,
    HANDLERS,
    KNOWLEDGE,
    MAIN,
    PULSE,
    TOOL_OWNERS,
    ToolOwnershipError,
    ToolTrace,
    call_tool,
    tools_owned_by,
)
from src.agent.tools import TOOL_MODELS
from src.auth.schemas import Principal
from src.config import settings

planner = VoiceAgentPlanner()


def test_catalog_every_tool_has_exactly_one_owner():
    assert set(TOOL_OWNERS) == set(TOOL_MODELS) == set(HANDLERS)
    assert len(TOOL_OWNERS) == 35  # 27 planned + legacy handoff + 4 app-control + 2 city feeds + directory
    assert tools_owned_by(MAIN) == sorted([
        "ask_clarification", "handoff", "handoff_to_officer", "reverse_geocode_coordinates",
        "toggle_audio_preference", "verify_citizen_location",
        "navigate_app", "focus_map", "set_app_preference", "find_local_agent",
    ])
    assert len(tools_owned_by(EMERGENCY)) == 6 and len(tools_owned_by(COMPLAINT)) == 6
    assert len(tools_owned_by(PULSE)) == 8 and len(tools_owned_by(KNOWLEDGE)) == 5


async def test_main_agent_cannot_call_domain_tools():
    with pytest.raises(ToolOwnershipError):
        await call_tool(MAIN, "dispatch_emergency_team", {"location": "Clock Tower"}, "u1")
    with pytest.raises(ToolOwnershipError):
        await call_tool(EMERGENCY, "create_complaint", {}, "u1")


async def test_call_tool_records_trace_and_falls_back_when_service_missing():
    trace = ToolTrace()
    res = await call_tool(EMERGENCY, "dispatch_emergency_team", {"location": "Clock Tower"}, "u1", trace)
    assert res["served"] == "fallback" and res["simulated"] is True
    assert trace.calls[0].tool == "dispatch_emergency_team" and trace.calls[0].caller == EMERGENCY


async def test_location_tool_uses_gazetteer_offline():
    res = await call_tool(MAIN, "verify_citizen_location", {"query": "near Clock Tower"}, "u1")
    assert res["matched"] == "Clock Tower" and res["precision"] == "approximate"
    assert res["zone"] == "Zone 1 (Central)"


@pytest.mark.parametrize(
    "message,scope,expected",
    [
        ("Accident near Clock Tower, send an ambulance now", QueryScope.CIVIC_EMERGENCY, [MAIN, EMERGENCY]),
        ("Please file a complaint about a pothole on Subhash Road", QueryScope.CIVIC_COMPLAINT, [MAIN, COMPLAINT]),
        ("Heavy traffic jam on Rajpur Road", QueryScope.CIVIC_EMERGENCY, [PULSE]),
        ("What is the AQI today?", QueryScope.CIVIC_LIVE_DATA, [PULSE]),
        ("How do I apply for old age pension?", QueryScope.CIVIC_KNOWLEDGE, [KNOWLEDGE]),
        # Classifier may tag waterlogging as a complaint; a pure question is a City Pulse lookup.
        ("Any waterlogging at underpasses today?", QueryScope.CIVIC_COMPLAINT, [PULSE]),
        ("Report waterlogging and a blocked drain at Paltan Bazaar", QueryScope.CIVIC_COMPLAINT, [MAIN, COMPLAINT]),
        (
            "Accident at Clock Tower, people injured, send ambulance. Also file a complaint about the pothole that caused it",
            QueryScope.CIVIC_EMERGENCY,
            [MAIN, EMERGENCY, COMPLAINT],
        ),
    ],
)
def test_planner_decomposition(message, scope, expected):
    from src.agent.subagents.complaint_agent import extract_location

    plan = planner.plan(message, scope, "en", location=extract_location(message))
    assert plan.executors == expected


async def test_end_to_end_emergency_turn_respects_delegation():
    started = time.monotonic()
    req = ChatRequest(requestId=uuid4(), message="Major accident near Clock Tower, two people injured, send ambulance")
    res = await offline_chat(Principal(user_id="citizen-1"), req, started)
    assert res.plan and [s.executor for s in res.plan] == [MAIN, EMERGENCY]
    assert all(s.status == "completed" for s in res.plan)
    callers = {c.tool: c.caller for c in res.toolCalls}
    assert callers["verify_citizen_location"] == MAIN
    assert callers["dispatch_emergency_team"] == EMERGENCY
    # Non-duplication: the main agent called nothing outside its own catalog.
    assert all(TOOL_OWNERS[c.tool] == c.caller for c in res.toolCalls)
    assert res.actionData["emergency"]["action_type"] == "emergency_dispatch"
    assert "112" in res.answer


async def test_complaint_confirm_files_into_complaint_service(monkeypatch):
    monkeypatch.setattr(settings, "complaint_service_url", "http://complaint-module:8001")

    async def fake_create(args, lat, lng, photo=None):
        assert args["category"] == "Potholes and Road Damage"
        return {"tracking_id": "CMP-2026-ABC123", "status": "WORKER_ASSIGNED", "assigned_worker": {"name": "R"}}

    monkeypatch.setattr(ix, "complaint_create", fake_create)
    principal = Principal(user_id="citizen-2")
    req = ChatRequest(
        requestId=uuid4(),
        message="Please file a complaint: deep pothole on Subhash Road near Clock Tower damaging vehicles",
    )
    res = await offline_chat(principal, req, time.monotonic())
    assert res.status == "ACTION_PENDING" and res.pendingAction
    # Another user cannot confirm this citizen's action.
    other = await offline_confirm_action(Principal(user_id="intruder"), res.pendingAction.token)
    assert other.status == "rejected"
    done = await offline_confirm_action(principal, res.pendingAction.token)
    assert done.status == "executed" and done.result["trackingId"] == "CMP-2026-ABC123"
    assert PENDING_ACTIONS[res.pendingAction.token]["status"] == "executed"
