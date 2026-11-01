"""In-memory data-flow event log for the operator dashboard (dashboard/, Messages page).

Every chat turn, voice transcription, TTS synthesis and action confirmation is recorded with its
source (dashboard, or the phone app via core), the guardrail/scope verdict, the planner's steps and
each tool call with the downstream service it reached. ``GET /api/agent/events?after=<id>``
(admin only) returns new events so the dashboard can animate the flow.

Process-local and bounded (last 300 events); this is an observability aid, not an audit log.
"""

from __future__ import annotations

import itertools
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

MAX_EVENTS = 300
_EVENTS: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
_IDS = itertools.count(1)

# Per-request scratchpad the orchestrator fills (guardrail verdict, scope) for the router to log.
turn_meta: ContextVar[dict[str, Any] | None] = ContextVar("turn_meta", default=None)

# Which backend a tool call actually reaches (for drawing the flow).
TOOL_SERVICE: dict[str, str] = {
    "verify_citizen_location": "public_data",
    "reverse_geocode_coordinates": "public_data",
    "ask_clarification": "agent",
    "handoff_to_officer": "agent",
    "toggle_audio_preference": "agent",
    "handoff": "agent",
    "create_complaint": "complaint_module",
    "get_complaint_status": "complaint_module",
    "list_user_complaints": "complaint_module",
    "escalate_complaint_sla": "complaint_module",
    "reassign_worker": "complaint_module",
    "verify_photo_evidence": "complaint_module",
    "dispatch_emergency_team": "emergency_routing",
    "get_emergency_corridor": "emergency_routing",
    "override_traffic_signal": "emergency_routing",
    "get_nearest_hospital": "emergency_routing",
    "get_cctv_incident_feed": "emergency_routing",
    "broadcast_safety_alert": "agent",
    "get_active_alerts": "agent",
    "get_events": "core",
    "get_traffic_density": "agent",
    "fetch_weather_inundation": "emergency_routing",
    "get_air_quality_index": "public_data",
    "check_water_supply_schedule": "knowledge_corpus",
    "search_schemes": "knowledge_corpus",
    "get_ward_councillor_info": "knowledge_corpus",
    "query_municipal_by_laws": "knowledge_corpus",
    "get_waste_collection_route": "knowledge_corpus",
    "find_local_businesses": "core",
    "navigate_app": "app",
    "focus_map": "app",
    "set_app_preference": "app",
    "find_local_agent": "core",
    "get_govt_notices": "complaint_module",
    "get_city_incidents": "core",
}


def describe_source(header: str | None) -> str:
    """Normalise the X-CitySense-Source header into a short label."""
    value = (header or "").strip().lower()
    if value.startswith("core"):
        return "mobile_app"  # the phone app reaches the agent through core
    if value.startswith("dashboard"):
        return "dashboard"
    return "direct_api"


def record(kind: str, **data: Any) -> dict[str, Any]:
    event = {"id": next(_IDS), "ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **data}
    _EVENTS.append(event)
    return event


def since(after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    return [e for e in _EVENTS if e["id"] > after][-max(1, min(limit, MAX_EVENTS)):]


def short_user(user_id: str) -> str:
    return user_id if len(user_id) <= 12 else f"{user_id[:8]}…"
