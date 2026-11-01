"""Tool registry: single-owner tool catalog with enforced delegation.

Invariant 2 of the CitySense architecture: every tool has exactly one owner. The main voice
agent may only call cross-cutting tools it owns; domain tools are executed exclusively by their
specialist sub-agent. ``call_tool`` enforces this at runtime (``ToolOwnershipError``) and records
every invocation in a per-turn ``ToolTrace`` so the planner can show what actually ran.

Handlers prefer live CitySense services (complaint module 8001, emergency routing 8002, core
8080, opt-in public APIs) and fall back to clearly-labelled sample data (``served="fallback"``,
``simulated=True``) when a service is not configured or unreachable.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from src.agent import integrations as ix
from src.agent.tools import TOOL_MODELS, read_tool

logger = logging.getLogger("citysense.tools")

MAIN = "main_voice_agent"
COMPLAINT = "civic_complaint"
EMERGENCY = "emergency_traffic"
PULSE = "city_pulse"
KNOWLEDGE = "knowledge_specialist"

TOOL_OWNERS: dict[str, str] = {
    # Group A — cross-cutting, owned by the main voice agent
    "verify_citizen_location": MAIN,
    "reverse_geocode_coordinates": MAIN,
    "ask_clarification": MAIN,
    "handoff_to_officer": MAIN,
    "toggle_audio_preference": MAIN,
    "handoff": MAIN,  # legacy persona handoff used by the LLM tool loop
    # App control: the main agent drives the citizen app (actions are executed by the client)
    "navigate_app": MAIN,
    "focus_map": MAIN,
    "set_app_preference": MAIN,
    "find_local_agent": MAIN,
    # Group B — civic grievances
    "create_complaint": COMPLAINT,
    "get_complaint_status": COMPLAINT,
    "list_user_complaints": COMPLAINT,
    "escalate_complaint_sla": COMPLAINT,
    "reassign_worker": COMPLAINT,
    "verify_photo_evidence": COMPLAINT,
    # Group C — emergency & public safety
    "dispatch_emergency_team": EMERGENCY,
    "get_emergency_corridor": EMERGENCY,
    "override_traffic_signal": EMERGENCY,
    "get_nearest_hospital": EMERGENCY,
    "get_cctv_incident_feed": EMERGENCY,
    "broadcast_safety_alert": EMERGENCY,
    # Group D — city pulse & environment
    "get_active_alerts": PULSE,
    "get_events": PULSE,
    "get_traffic_density": PULSE,
    "fetch_weather_inundation": PULSE,
    "get_air_quality_index": PULSE,
    "check_water_supply_schedule": PULSE,
    "get_govt_notices": PULSE,
    "get_city_incidents": PULSE,
    # Group E — municipal knowledge
    "search_schemes": KNOWLEDGE,
    "get_ward_councillor_info": KNOWLEDGE,
    "query_municipal_by_laws": KNOWLEDGE,
    "get_waste_collection_route": KNOWLEDGE,
    "find_local_businesses": KNOWLEDGE,
}

assert set(TOOL_OWNERS) == set(TOOL_MODELS), "every tool needs exactly one owner and one schema"


class ToolOwnershipError(PermissionError):
    """Raised when an agent calls a tool owned by another agent."""


@dataclass
class ToolCall:
    tool: str
    caller: str
    served: str
    ok: bool
    duration_ms: float
    error: str | None = None


@dataclass
class ToolTrace:
    calls: list[ToolCall] = field(default_factory=list)

    def by(self, caller: str) -> list[ToolCall]:
        return [c for c in self.calls if c.caller == caller]


# Per-user / process-local state for cross-cutting tools. Persisting these is a follow-up;
# they reset on restart, which is acceptable for preferences and queued officer reviews.
AUDIO_PREFERENCES: dict[str, dict[str, Any]] = {}
OFFICER_HANDOFFS: list[dict[str, Any]] = []
BROADCAST_QUEUE: list[dict[str, Any]] = []

Handler = Callable[[dict[str, Any], str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback(data: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    out = {"served": "fallback", "simulated": True, **data}
    if reason:
        out["fallback_reason"] = reason
    return out


def _live(data: Any) -> dict[str, Any]:
    return {"served": "live", "data": data}


# ── Group A: main voice agent ────────────────────────────────────────────────

async def _verify_location(args: dict, user_id: str, ctx: dict) -> dict:
    query = args["query"]
    try:
        hit = await ix.nominatim_search(query)
        if hit:
            near = ix.gazetteer_nearest(hit["lat"], hit["lng"])
            return _live({**hit, "zone": near[1]["zone"], "precision": "geocoded", "query": query})
    except (ix.IntegrationUnavailable, LookupError) as exc:
        reason = str(exc)
    else:
        reason = "no geocoder match"
    found = ix.gazetteer_lookup(query)
    if found:
        name, entry = found
        return _fallback({"query": query, "matched": name.title(), "lat": entry["lat"], "lng": entry["lng"],
                          "zone": entry["zone"], "precision": "approximate"}, reason)
    return _fallback({"query": query, "matched": None, **ix.CITY_CENTRE, "zone": None,
                      "precision": "city_centre"}, reason)


async def _reverse_geocode(args: dict, user_id: str, ctx: dict) -> dict:
    lat, lng = args["lat"], args["lng"]
    name, entry, km = ix.gazetteer_nearest(lat, lng)
    try:
        rev = await ix.nominatim_reverse(lat, lng)
        return _live({**rev, "nearest_landmark": name.title(), "zone": entry["zone"]})
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"nearest_landmark": name.title(), "distance_km": km, "zone": entry["zone"],
                          "precision": "approximate"}, str(exc))


async def _ask_clarification(args: dict, user_id: str, ctx: dict) -> dict:
    return {"served": "live", "question": args["question"]}


async def _handoff_to_officer(args: dict, user_id: str, ctx: dict) -> dict:
    ticket = {
        "handoff_id": f"HUMAN-{secrets.token_hex(3).upper()}",
        "user_id": user_id,
        "reason": args["reason"],
        "urgency": args["urgency"],
        "status": "QUEUED_FOR_OFFICER",
        "created_at": _now(),
        # From data/corpus/municipal/nnd_wards_directory_and_helplines.md
        "helpline": "1800-180-4151",
    }
    OFFICER_HANDOFFS.append(ticket)
    return {"served": "live", **ticket}


async def _toggle_audio(args: dict, user_id: str, ctx: dict) -> dict:
    prefs = {"auto_play": args["auto_play"], "preferred_speaker": args["preferred_speaker"], "updated_at": _now()}
    AUDIO_PREFERENCES[user_id] = prefs
    return {"served": "live", **prefs}


async def _persona_handoff(args: dict, user_id: str, ctx: dict) -> dict:
    # The LLM tool loop in service.py resolves persona handoffs itself; this keeps the schema owned.
    return {"served": "live", "agent_id": args["agent_id"]}


# ── Group B: civic complaints ────────────────────────────────────────────────

async def _complaint_status(args: dict, user_id: str, ctx: dict) -> dict:
    tid = args["tracking_id"]
    try:
        item = await ix.complaint_get(tid)
        return {"served": "live", "trackingId": tid, "status": item.get("status"), "data": item}
    except LookupError:
        pass  # not in the complaint module; may be a legacy/sample id
    except ix.IntegrationUnavailable:
        pass
    return await read_tool("get_complaint_status", args, user_id)


async def _list_complaints(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        items = await ix.complaint_list()
        complaints = [
            {
                "tracking_id": c.get("tracking_id"),
                "category": c.get("category"),
                "location": (c.get("location") or {}).get("address", ""),
                "description": c.get("description", ""),
                "status": c.get("status"),
                "priority": c.get("priority"),
                "assigned_worker": (c.get("assigned_worker") or {}).get("name", "Unassigned"),
                "created_at": c.get("created_at"),
            }
            for c in items
            if c.get("status") != "RESOLVED"
        ]
        return {"served": "live", "user_id": user_id, "complaints": complaints}
    except ix.IntegrationUnavailable:
        return await read_tool("list_user_complaints", args, user_id)


async def _escalate(args: dict, user_id: str, ctx: dict) -> dict:
    tid = args["tracking_id"]
    try:
        item = await ix.complaint_escalate(tid)
        authority = item.get("current_authority") or {}
        return _live({"tracking_id": tid, "status": item.get("status"), "warnings": item.get("warnings_count"),
                      "current_authority": authority.get("designation") or authority.get("name")})
    except LookupError:
        return {"served": "live", "tracking_id": tid, "status": "not_found"}
    except ix.IntegrationUnavailable as exc:
        return _fallback({"tracking_id": tid, "status": "ESCALATION_REQUESTED",
                          "current_authority": "Ward Supervisor"}, str(exc))


async def _reassign(args: dict, user_id: str, ctx: dict) -> dict:
    tid = args["tracking_id"]
    try:
        item = await ix.complaint_reassign(tid, args["reason"])
        return _live({"tracking_id": tid, "assigned_worker": item.get("assigned_worker"), "status": item.get("status")})
    except LookupError:
        return {"served": "live", "tracking_id": tid, "status": "not_found"}
    except ix.IntegrationUnavailable as exc:
        return _fallback({"tracking_id": tid, "assigned_worker": {"name": "Rapid Action Squad"},
                          "status": "REASSIGNMENT_REQUESTED"}, str(exc))


async def _verify_photo(args: dict, user_id: str, ctx: dict) -> dict:
    """Evidence check: a resolved ticket must carry a proof photo and a resolution note.

    This is a record-integrity check, not computer-vision verification of the image content.
    """
    tid = args["tracking_id"]
    try:
        item = await ix.complaint_get(tid)
    except LookupError:
        return {"served": "live", "tracking_id": tid, "verdict": "NOT_FOUND"}
    except ix.IntegrationUnavailable as exc:
        return _fallback({"tracking_id": tid, "verdict": "UNVERIFIABLE"}, str(exc))
    resolved = item.get("status") == "RESOLVED"
    proof = any(
        "proof" in (e.get("message", "") + e.get("action", "")).lower() for e in item.get("timeline", [])
    ) or bool(item.get("resolution_note"))
    verdict = "VERIFIED" if resolved and proof else ("PENDING_RESOLUTION" if not resolved else "MISSING_EVIDENCE")
    return _live({"tracking_id": tid, "verdict": verdict, "status": item.get("status"),
                  "before_photo": item.get("photo_url"), "resolution_note": item.get("resolution_note"),
                  "method": "record_integrity_check"})


async def _create_complaint(args: dict, user_id: str, ctx: dict) -> dict:
    # Creation is always propose -> confirm (see CivicComplaintSpecialist + service.confirm_action).
    return {"served": "live", "proposed": True, **args}


# ── Group C: emergency ───────────────────────────────────────────────────────

async def _dispatch(args: dict, user_id: str, ctx: dict) -> dict:
    payload = {
        "incident_type": args["incident_type"],
        "severity": args["severity"],
        "location_label": args["location"],
        "latitude": args.get("latitude"),
        "longitude": args.get("longitude"),
        "description": args["description"],
        "reported_by": f"citizen:{user_id}",
    }
    try:
        return _live(await ix.emergency_dispatch(payload))
    except ix.IntegrationUnavailable as exc:
        return _fallback({
            "mission_id": f"EMG-SIM-{secrets.token_hex(2).upper()}",
            "status": "DISPATCH_REQUESTED",
            "unit_type": "ambulance",
            "hospital": {"name": "Nearest trauma centre (pending live dispatch)"},
            "advice": "Call 108 (ambulance) / 112 (emergency) directly.",
        }, str(exc))


async def _corridor(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        return _live(await ix.emergency_corridor(args["origin"], args["destination"], args["vehicle_type"]))
    except (ix.IntegrationUnavailable, LookupError):
        return await read_tool("get_emergency_corridor", args, user_id)


async def _override_signal(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        return _live(await ix.emergency_signal_override(args))
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"status": "PREEMPTION_REQUESTED", "signals": args.get("signals", []),
                          "controller": "simulated"}, str(exc))


async def _nearest_hospital(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        return _live(await ix.emergency_nearest_hospital(args["location"], args.get("lat"), args.get("lng")))
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"hospital": {"name": "Government Doon Medical College Hospital",
                                       "note": "Sample; confirm with 108 control room"}}, str(exc))


async def _cctv_feed(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        return _live(await ix.emergency_incidents(args["limit"]))
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"incidents": [], "count": 0}, str(exc))


async def _broadcast(args: dict, user_id: str, ctx: dict) -> dict:
    # Citizen-initiated broadcasts are never auto-published: they queue for officer verification.
    item = {"broadcast_id": f"BRD-{secrets.token_hex(3).upper()}", "status": "PENDING_OFFICER_VERIFICATION",
            "requested_by": user_id, "created_at": _now(), **args}
    BROADCAST_QUEUE.append(item)
    return {"served": "live", **item}


# ── Group D: city pulse ──────────────────────────────────────────────────────

async def _alerts(args: dict, user_id: str, ctx: dict) -> dict:
    return await read_tool("get_active_alerts", args, user_id)


def _core_event_item(e: dict) -> dict | None:
    """Core city_events row -> the briefing shape (date, time, location), in city time (IST)."""
    from datetime import datetime, timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    try:
        start = datetime.fromisoformat(str(e["startsAt"]).replace("Z", "+00:00")).astimezone(ist)
        end = datetime.fromisoformat(str(e["endsAt"]).replace("Z", "+00:00")).astimezone(ist) if e.get("endsAt") else None
    except (KeyError, ValueError):
        return None
    if (end or start).date() < datetime.now(ist).date():
        return None  # already over
    fmt = lambda d: f"{d.day} {d:%b %Y}"  # noqa: E731
    date = f"{fmt(start)} to {fmt(end)}" if end and end.date() != start.date() else f"{start:%a} {fmt(start)}"
    return {
        "title": e.get("title") or "Event",
        "date": date,
        "time": "ongoing" if start.date() <= datetime.now(ist).date() else "all day",
        "location": e.get("venue") or "Dehradun",
        "description": e.get("description") or "",
        "organizer": e.get("organizer"),
        "source_url": e.get("sourceUrl"),
        "starts_at": start.isoformat(),
    }


async def _events(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        raw = await ix.core_city_events()
        items = sorted(filter(None, (_core_event_item(e) for e in raw or [])), key=lambda i: i["starts_at"])
        if items:
            return {"served": "live", "items": items}
    except (ix.IntegrationUnavailable, LookupError):
        pass
    return await read_tool("get_events", args, user_id)


async def _traffic(args: dict, user_id: str, ctx: dict) -> dict:
    return await read_tool("get_traffic_density", args, user_id)


async def _weather(args: dict, user_id: str, ctx: dict) -> dict:
    found = ix.gazetteer_lookup(args.get("area") or "")
    lat, lng = (found[1]["lat"], found[1]["lng"]) if found else (None, None)
    try:
        w = await ix.emergency_weather(lat, lng)
        depth = float(w.get("water_depth_cm_estimate") or 0)
        return _live({**w, "area": args.get("area") or "Dehradun",
                      "underpass_status": "DIVERT" if depth >= 25 else ("CAUTION" if depth >= 5 else "CLEAR")})
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"area": args.get("area") or "Dehradun", "precipitation_mm": None,
                          "water_depth_cm_estimate": None, "underpass_status": "UNKNOWN",
                          "advice": "Live weather unavailable; avoid underpasses during heavy rain."}, str(exc))


async def _aqi(args: dict, user_id: str, ctx: dict) -> dict:
    found = ix.gazetteer_lookup(args.get("area") or "")
    point = found[1] if found else ix.CITY_CENTRE
    try:
        cur = await ix.open_meteo_air_quality(point["lat"], point["lng"])
        return _live({"area": args.get("area") or "Dehradun", "us_aqi": cur.get("us_aqi"),
                      "pm2_5": cur.get("pm2_5"), "pm10": cur.get("pm10"), "source": "Open-Meteo"})
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"area": args.get("area") or "Dehradun", "us_aqi": None, "pm2_5": None, "pm10": None,
                          "advice": "Live AQI unavailable."}, str(exc))


def _corpus(query: str, language: str = "en", limit: int = 2) -> list[dict[str, Any]]:
    from src.agent.offline import offline_corpus

    return [
        {"doc_id": doc["doc_id"], "title": doc["title"], "url": doc["url"], "excerpt": excerpt}
        for doc, _score, excerpt in offline_corpus.search(query, language)[:limit]
    ]


async def _water(args: dict, user_id: str, ctx: dict) -> dict:
    passages = _corpus(f"water supply jal sansthan {args.get('area', '')}", ctx.get("language", "en"))
    return {"served": "live", "area": args.get("area") or "Dehradun", "passages": passages,
            "note": "Live release-hour telemetry is not integrated; guidance is from the verified corpus."}


# ── Group E: knowledge ───────────────────────────────────────────────────────

async def _search_schemes(args: dict, user_id: str, ctx: dict) -> dict:
    return {"served": "live", "passages": _corpus(args.get("query") or "scheme", ctx.get("language", "en"), 3)}


async def _ward_info(args: dict, user_id: str, ctx: dict) -> dict:
    found = ix.gazetteer_lookup(args.get("area") or "")
    return {"served": "live", "area": args.get("area"), "zone": found[1]["zone"] if found else None,
            "passages": _corpus("ward councillor zone helpline", ctx.get("language", "en"), 1)}


async def _bylaws(args: dict, user_id: str, ctx: dict) -> dict:
    return {"served": "live", "passages": _corpus(args.get("query") or "municipal rules", ctx.get("language", "en"), 2)}


async def _waste(args: dict, user_id: str, ctx: dict) -> dict:
    return {"served": "live", "area": args.get("area"),
            "passages": _corpus("solid waste collection door segregation", ctx.get("language", "en"), 1)}


# ── App control (main agent) ─────────────────────────────────────────────────

async def _navigate(args: dict, user_id: str, ctx: dict) -> dict:
    action = {"type": "navigate", "screen": args["screen"]}
    if args.get("target_id"):
        action["id"] = args["target_id"]
    return {"served": "live", "client_action": action}


async def _focus_map(args: dict, user_id: str, ctx: dict) -> dict:
    loc = await _verify_location({"query": args["query"]}, user_id, ctx)
    data = loc.get("data", loc)
    action = {"type": "focus_map", "latitude": data.get("lat"), "longitude": data.get("lng"),
              "label": data.get("matched") or args["query"]}
    return {"served": loc.get("served", "live"), "client_action": action, "precision": data.get("precision")}


async def _set_preference(args: dict, user_id: str, ctx: dict) -> dict:
    action: dict[str, Any] = {"type": "set_preference"}
    if args.get("language"):
        action["language"] = args["language"]
    if args.get("voice_auto_play") is not None:
        action["voiceAutoPlay"] = args["voice_auto_play"]
        prefs = AUDIO_PREFERENCES.setdefault(user_id, {"preferred_speaker": "aditya"})
        prefs.update(auto_play=args["voice_auto_play"], updated_at=_now())
    return {"served": "live", "client_action": action}


async def _find_local_agent(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        found = await ix.core_find_avatars(args["name"], ctx.get("latitude"), ctx.get("longitude"))
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"found": False}, str(exc))
    if not found:
        return {"served": "live", "found": False}
    a = found[0]
    return {"served": "live", "found": True, "avatar": {"id": a.get("id"), "name": a.get("name"), "title": a.get("title")},
            "client_action": {"type": "navigate", "screen": "avatar", "id": a.get("id")}}


# ── More city feeds (city pulse) ─────────────────────────────────────────────

async def _notices(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        rows = await ix.complaint_notices(args["limit"])
        return {"served": "live", "items": rows[: args["limit"]]}
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"items": []}, str(exc))


async def _incidents(args: dict, user_id: str, ctx: dict) -> dict:
    try:
        rows = await ix.core_incidents()
        return {"served": "live", "items": rows[: args["limit"]]}
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"items": []}, str(exc))


async def _businesses(args: dict, user_id: str, ctx: dict) -> dict:
    lat, lng = ctx.get("latitude"), ctx.get("longitude")
    found = ix.gazetteer_lookup(args.get("area") or "")
    if found:  # a named place wins over the citizen's own position
        lat, lng = found[1]["lat"], found[1]["lng"]
    try:
        rows = await ix.core_businesses(lat, lng, category=args.get("category"), limit=args["limit"])
        return {"served": "live", "items": rows}
    except (ix.IntegrationUnavailable, LookupError) as exc:
        return _fallback({"items": []}, str(exc))


HANDLERS: dict[str, Handler] = {
    "verify_citizen_location": _verify_location,
    "reverse_geocode_coordinates": _reverse_geocode,
    "ask_clarification": _ask_clarification,
    "handoff_to_officer": _handoff_to_officer,
    "toggle_audio_preference": _toggle_audio,
    "handoff": _persona_handoff,
    "create_complaint": _create_complaint,
    "get_complaint_status": _complaint_status,
    "list_user_complaints": _list_complaints,
    "escalate_complaint_sla": _escalate,
    "reassign_worker": _reassign,
    "verify_photo_evidence": _verify_photo,
    "dispatch_emergency_team": _dispatch,
    "get_emergency_corridor": _corridor,
    "override_traffic_signal": _override_signal,
    "get_nearest_hospital": _nearest_hospital,
    "get_cctv_incident_feed": _cctv_feed,
    "broadcast_safety_alert": _broadcast,
    "get_active_alerts": _alerts,
    "get_events": _events,
    "get_traffic_density": _traffic,
    "fetch_weather_inundation": _weather,
    "get_air_quality_index": _aqi,
    "check_water_supply_schedule": _water,
    "search_schemes": _search_schemes,
    "get_ward_councillor_info": _ward_info,
    "query_municipal_by_laws": _bylaws,
    "get_waste_collection_route": _waste,
    "find_local_businesses": _businesses,
    "navigate_app": _navigate,
    "focus_map": _focus_map,
    "set_app_preference": _set_preference,
    "find_local_agent": _find_local_agent,
    "get_govt_notices": _notices,
    "get_city_incidents": _incidents,
}

assert set(HANDLERS) == set(TOOL_OWNERS), "every registered tool needs a handler"


def tools_owned_by(owner: str) -> list[str]:
    return sorted(name for name, o in TOOL_OWNERS.items() if o == owner)


async def call_tool(
    caller: str,
    name: str,
    args: dict[str, Any],
    user_id: str,
    trace: ToolTrace | None = None,
    **ctx: Any,
) -> dict[str, Any]:
    """Validate ownership + arguments, run the handler, and record the call."""
    owner = TOOL_OWNERS.get(name)
    if owner is None:
        raise ValueError(f"Unknown tool: {name}")
    if owner != caller:
        raise ToolOwnershipError(f"{caller} may not call {name}; it is owned by {owner}")
    validated = TOOL_MODELS[name].model_validate(args).model_dump()
    started = time.monotonic()
    try:
        result = await HANDLERS[name](validated, user_id, ctx)
        ok, error = True, None
    except Exception as exc:  # handlers already degrade; this is the last line of defence
        logger.exception("Tool %s failed", name)
        result, ok, error = _fallback({"error": "tool_unavailable"}, exc.__class__.__name__), False, exc.__class__.__name__
    if trace is not None:
        trace.calls.append(ToolCall(name, caller, str(result.get("served", "live")), ok,
                                    round((time.monotonic() - started) * 1000, 1), error))
    return result


__all__ = [
    "MAIN", "COMPLAINT", "EMERGENCY", "PULSE", "KNOWLEDGE", "TOOL_OWNERS", "HANDLERS",
    "ToolOwnershipError", "ToolTrace", "ToolCall", "call_tool", "tools_owned_by",
    "AUDIO_PREFERENCES", "OFFICER_HANDOFFS", "BROADCAST_QUEUE",
]
