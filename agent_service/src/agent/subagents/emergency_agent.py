"""Emergency specialist: sole caller of the emergency & public-safety tools.

SOP (critical incident reported):
  triage_severity -> dispatch_unit -> query_corridor -> preempt_signals -> generate_guidance
SOP (question / non-critical):
  triage_severity -> check_incident_feed -> generate_guidance

Dispatch only happens for a *report or request* of a life-safety incident ("accident happened,
send ambulance"), never for a question ("is there an accident on Rajpur Road?").
"""

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.subagents.base import BaseSubAgent, SubAgentResult
from src.agent.tool_registry import EMERGENCY, call_tool
from src.auth.schemas import Principal

CRITICAL_KEYWORDS = {
    "ambulance", "fire", "fire truck", "fire brigade", "accident", "crash", "collision", "casualty",
    "emergency", "hospital", "injured", "injury", "trapped", "collapsed", "bleeding", "unconscious",
    "gas leak", "fight", "assault", "heart attack",
    "आग", "दुर्घटना", "एम्बुलेंस", "दमकल", "हादसा", "गंभीर", "घायल", "बेहोश", "मारपीट",
}
# Signals that the citizen is reporting / requesting help rather than asking.
DISPATCH_SIGNAL_RE = re.compile(
    r"\b(send|need|dispatch|call|help|urgent|emergency|please come|happened|reported|right now|immediately)\b"
    r"|भेजो|भेजिए|चाहिए|मदद|तुरंत|हुआ है|हो गया|हो गई",
    re.IGNORECASE,
)
STRONG_HARM_RE = re.compile(
    r"\b(injured|casualt|bleeding|unconscious|trapped|burning|on fire)\w*|घायल|बेहोश|आग लगी",
    re.IGNORECASE,
)


def parse_origin_destination(text: str) -> tuple[str, str]:
    match = re.search(
        r"(?:from|से)\s+([A-Za-z0-9\s,.-]+?)\s+(?:to|तक|जाना)\s+([A-Za-z0-9\s,.-]+)",
        text,
        re.IGNORECASE,
    )
    if match:
        orig = match.group(1).strip()
        dest = match.group(2).strip()
        if len(orig) >= 3 and len(dest) >= 3:
            return orig, dest
    return "Clock Tower, Dehradun", "Doon Hospital, Dehradun"


def classify_incident(lower_msg: str) -> tuple[str, str]:
    """Return (incident_type for dispatch API, vehicle_type for the citizen card)."""
    if "fire" in lower_msg or "दमकल" in lower_msg or "आग" in lower_msg:
        return "fire", "fire_truck"
    if any(k in lower_msg for k in ("fight", "assault", "मारपीट", "झगड़ा")):
        return "feud", "police"
    if any(k in lower_msg for k in ("accident", "crash", "collision", "दुर्घटना", "हादसा")):
        return "accident", "ambulance"
    return "medical", "ambulance"


def wants_dispatch(message: str) -> bool:
    lower = message.lower()
    if not any(kw in lower for kw in CRITICAL_KEYWORDS):
        return False
    signal = bool(DISPATCH_SIGNAL_RE.search(message)) or bool(STRONG_HARM_RE.search(message))
    is_question = message.strip().endswith("?") or re.match(
        r"^\s*(is|are|any|was|were|kya|क्या)\b", lower
    )
    return signal and not (is_question and not DISPATCH_SIGNAL_RE.search(message))


class EmergencySpecialist(BaseSubAgent):
    name: str = EMERGENCY
    description: str = "Specialist for emergency dispatch, green-wave corridors, incident triage and safety guidance"

    async def execute(
        self,
        session: AsyncSession | None,
        principal: Principal,
        message: str,
        context: Any = None,
        language: str = "en",
        **kwargs: Any,
    ) -> SubAgentResult:
        trace = kwargs.get("trace")
        steps: list[str] = ["triage_severity"]
        lower_msg = message.lower()
        incident_type, vehicle_type = classify_incident(lower_msg)

        if not wants_dispatch(message):
            return await self._advisory(principal, language, steps, trace)

        # dispatch_unit
        steps.append("dispatch_unit")
        origin, dest = parse_origin_destination(message)
        scene = kwargs.get("location") or origin
        dispatch = await call_tool(
            EMERGENCY,
            "dispatch_emergency_team",
            {
                "incident_type": incident_type,
                "severity": "P0",
                "location": scene,
                "latitude": kwargs.get("latitude"),
                "longitude": kwargs.get("longitude"),
                "description": message[:2000],
            },
            principal.user_id,
            trace,
        )
        mission = dispatch.get("data") if dispatch.get("served") == "live" else dispatch

        # query_corridor: reuse the mission's planned route when the dispatcher computed one.
        steps.append("query_corridor")
        route = (mission or {}).get("route") or {}
        if route:
            corridor = {
                "corridor_id": mission.get("mission_id"),
                "origin": (mission.get("hospital") or {}).get("name", dest),
                "destination": scene,
                "estimated_travel_time_minutes": route.get("eta_minutes"),
                "normal_travel_time_minutes": route.get("nominal_minutes"),
                "signals_cleared": route.get("signals_preempted", []),
            }
        else:
            res = await call_tool(
                EMERGENCY, "get_emergency_corridor",
                {"origin": scene, "destination": dest, "vehicle_type": vehicle_type},
                principal.user_id, trace,
            )
            corridor = res.get("data") if res.get("served") == "live" else res

        # preempt_signals
        steps.append("preempt_signals")
        signals = [s for s in corridor.get("signals_cleared", []) if s][:20]
        preemption: dict[str, Any] = {}
        if signals:
            res = await call_tool(
                EMERGENCY, "override_traffic_signal",
                {"corridor_id": corridor.get("corridor_id"), "signals": signals},
                principal.user_id, trace,
            )
            preemption = res.get("data") if res.get("served") == "live" else res

        steps.append("generate_guidance")
        hospital = (mission or {}).get("hospital") or {}
        action = {
            "action_type": "emergency_dispatch",
            "tool": "dispatch_emergency_team",
            "severity": "CRITICAL",
            "incident_type": incident_type,
            "vehicle_type": vehicle_type,
            "mission_id": mission.get("mission_id"),
            "unit_id": mission.get("unit_id"),
            "status": mission.get("status", "DISPATCH_REQUESTED"),
            "hospital": hospital.get("name"),
            "corridor_id": corridor.get("corridor_id"),
            "origin": corridor.get("origin"),
            "destination": corridor.get("destination"),
            "eta_minutes": corridor.get("estimated_travel_time_minutes"),
            "signals_preempted": signals,
            "signal_override": preemption.get("status"),
            "simulated": bool(dispatch.get("simulated")),
            "network": mission.get("network"),
        }
        response_text = self._critical_text(action, language)
        return SubAgentResult(
            status="ACTION_PENDING",
            response_text=response_text,
            action=action,
            cta="dispatch_emergency",
            execution_steps=steps,
            metadata={"severity": "CRITICAL", "corridor_data": corridor, "action": action, "card": action},
        )

    async def _advisory(self, principal: Principal, language: str, steps: list[str], trace: Any) -> SubAgentResult:
        steps.append("check_incident_feed")
        feed = await call_tool(EMERGENCY, "get_cctv_incident_feed", {"limit": 5}, principal.user_id, trace)
        incidents = (feed.get("data") or feed).get("incidents", []) if isinstance(feed, dict) else []
        steps.append("generate_guidance")
        if language == "hi":
            lines = ["🚗 **ट्रैफिक एवं सुरक्षा सलाह (TRAFFIC ADVISORY)**", ""]
            lines.append(
                f"• **CCTV द्वारा पहचानी गई हालिया घटनाएँ:** {len(incidents)}"
                if incidents else "• CCTV फीड में अभी कोई सक्रिय घटना दर्ज नहीं है।"
            )
            for inc in incidents[:3]:
                lines.append(f"  – {inc.get('incident_type', '').upper()} @ {inc.get('location_label') or inc.get('camera_id')}")
            lines += ["", "🛡️ सुरक्षित दूरी बनाए रखें, जंक्शन बॉक्स को ब्लॉक न करें। आपात स्थिति में **112** पर कॉल करें।"]
        else:
            lines = ["🚗 **TRAFFIC & SAFETY ADVISORY**", ""]
            lines.append(
                f"• **Recent CCTV-detected incidents:** {len(incidents)}"
                if incidents else "• No active incidents in the CCTV feed right now."
            )
            for inc in incidents[:3]:
                lines.append(f"  – {inc.get('incident_type', '').upper()} @ {inc.get('location_label') or inc.get('camera_id')}")
            lines += ["", "🛡️ Keep a safe braking distance and do not block junction boxes. "
                          "If someone is hurt, say *\"send an ambulance\"* or call **112**."]
        return SubAgentResult(
            status="ANSWERED",
            response_text="\n".join(lines),
            action=None,
            cta="view_alternate_routes",
            execution_steps=steps,
            metadata={"severity": "ADVISORY", "incidents": incidents[:5]},
        )

    @staticmethod
    def _critical_text(a: dict[str, Any], language: str) -> str:
        eta = a.get("eta_minutes")
        eta_txt = f"{eta} min" if eta is not None else "being calculated"
        signals = ", ".join(a.get("signals_preempted") or []) or "—"
        sim = a.get("simulated") or a.get("network") == "demo-synthetic"
        if language == "hi":
            return (
                "🚨 **आपातकालीन डिस्पैच एवं ग्रीन कॉरिडोर (EMERGENCY DISPATCH)**\n\n"
                f"• **मिशन:** {a.get('mission_id') or '—'} — स्थिति: **{a.get('status')}**\n"
                f"• **यूनिट:** {a.get('vehicle_type', '').upper()} {a.get('unit_id') or ''}\n"
                f"• **अस्पताल:** {a.get('hospital') or 'निकटतम ट्रॉमा केंद्र'}\n"
                f"• **ग्रीन वेव:** सक्रिय (अनुमानित पहुंच: {eta_txt})\n"
                f"• **सिग्नल प्राथमिकता:** {signals}\n\n"
                "⚠️ **तुरंत करें:**\n"
                "1. घायल को न हिलाएं जब तक खतरा न हो; रक्तस्राव पर दबाव डालें।\n"
                "2. आपातकालीन वाहन के लिए बाईं लेन खाली रखें।\n"
                "3. हेल्पलाइन: **112** (आपातकाल), **108** (एम्बुलेंस), **101** (अग्निशमन)।"
                + ("\n\n*नोट: डिस्पैच सिमुलेशन नेटवर्क पर है — कृपया 112 पर भी कॉल करें।*" if sim else "")
            )
        return (
            "🚨 **EMERGENCY DISPATCH & GREEN WAVE CORRIDOR**\n\n"
            f"• **Mission:** {a.get('mission_id') or '—'} — status **{a.get('status')}**\n"
            f"• **Unit:** {a.get('vehicle_type', '').upper()} {a.get('unit_id') or ''}\n"
            f"• **Receiving hospital:** {a.get('hospital') or 'nearest trauma centre'}\n"
            f"• **Green Wave:** ACTIVE (ETA {eta_txt})\n"
            f"• **Signals pre-empted:** {signals}\n\n"
            "⚠️ **Do this now:**\n"
            "1. Don't move the injured unless there is immediate danger; apply pressure to bleeding.\n"
            "2. Keep the left lane clear for the approaching emergency vehicle.\n"
            "3. Helplines: **112** (Integrated Emergency), **108** (Ambulance), **101** (Fire)."
            + ("\n\n*Note: dispatch runs on the simulation network — please also call 112.*" if sim else "")
        )
