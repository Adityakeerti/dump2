"""Dynamic execution planner for the main voice agent (Invariant 1: planner lives only here).

The planner decomposes one citizen utterance into ordered steps. Each step names exactly one
executor: the main voice agent (cross-cutting tools only) or one specialist sub-agent, which then
runs its own deterministic SOP and is the sole caller of its domain tools (Invariant 2).

Planning is rule-based on purpose: it is instant, deterministic, testable and works offline.
Ordering rule: resolve location first, then life-safety, then grievances, then information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from src.agent.guardrails import QueryScope
from src.agent.tool_registry import COMPLAINT, EMERGENCY, KNOWLEDGE, MAIN, PULSE

StepStatus = Literal["planned", "running", "completed", "failed", "skipped"]

# Life-threatening signals. Plain congestion ("traffic jam") is NOT an emergency.
EMERGENCY_RE = re.compile(
    r"\b(accident|crash|collision|injur(?:ed|y)|bleeding|unconscious|ambulance|fire(?!\s*works)|burning|"
    r"trapped|casualt(?:y|ies)|heart attack|stroke|gas leak|collapsed?|fight|assault|stabb|drown)\w*"
    r"|दुर्घटना|हादसा|घायल|एम्बुलेंस|एंबुलेंस|आग|दमकल|बेहोश|झगड़ा|मारपीट",
    re.IGNORECASE,
)
COMPLAINT_ISSUE_RE = re.compile(
    r"\b(pothole|crater|garbage|trash|waste dump|streetlights?|street light|sewage|sewer|drain|manhole|"
    r"water leak|pipeline|encroachment|stray|dead animal)\w*|गड्ढा|गड्ढे|कूड़ा|कचरा|स्ट्रीट लाइट|नाली|सीवर|मैनहोल",
    re.IGNORECASE,
)
COMPLAINT_VERB_RE = re.compile(
    r"\b(complain\w*|grievance|report|file|lodge|register|ticket|escalate|reassign|status of|track)\b"
    r"|शिकायत|दर्ज|रिपोर्ट",
    re.IGNORECASE,
)
TRACKING_RE = re.compile(r"\b(?:NND-\d{4}-\d{3,4}|CMP-\d{4}-[A-F0-9]{6}|MOCK-[A-F0-9]+)\b", re.IGNORECASE)
PULSE_RE = re.compile(
    r"\b(weather|rain\w*|flood\w*|waterlog\w*|underpass|aqi|air quality|pollution|pm2\.?5|traffic|jam|"
    r"congestion|alerts?|advisor(?:y|ies)|events?|festival|water supply|supply schedule)\b"
    r"|मौसम|बारिश|जलभराव|प्रदूषण|ट्रैफिक|जाम|अलर्ट|कार्यक्रम|पानी की आपूर्ति",
    re.IGNORECASE,
)
KNOWLEDGE_RE = re.compile(
    r"\b(scheme|yojana|pension|certificate|licen[cs]e|property tax|bye?-?laws?|councillor|parshad|ward|"
    r"helpline|how (?:do|can) i|procedure|documents? required|eligib\w*|waste collection)\b"
    r"|योजना|पेंशन|प्रमाण पत्र|संपत्ति कर|पार्षद|वार्ड",
    re.IGNORECASE,
)


QUESTION_RE = re.compile(
    r"^\s*(what|what's|whats|is|are|any|how|when|where|which|will|does|do|can|kya|क्या|कब|कहाँ|कैसे)\b", re.IGNORECASE
)


def is_question(text: str) -> bool:
    return text.strip().endswith("?") or bool(QUESTION_RE.match(text))


@dataclass
class PlanStep:
    id: int
    executor: str
    action: str
    tools: list[str]
    status: StepStatus = "planned"
    detail: str | None = None


@dataclass
class ExecutionPlan:
    steps: list[PlanStep] = field(default_factory=list)
    language: str = "en"

    def add(self, executor: str, action: str, tools: list[str]) -> PlanStep:
        step = PlanStep(id=len(self.steps) + 1, executor=executor, action=action, tools=tools)
        self.steps.append(step)
        return step

    @property
    def executors(self) -> list[str]:
        return [s.executor for s in self.steps]

    def for_executor(self, executor: str) -> PlanStep | None:
        return next((s for s in self.steps if s.executor == executor), None)


class VoiceAgentPlanner:
    """Turns (message, scope) into an ExecutionPlan. Owned exclusively by the main voice agent."""

    def plan(
        self,
        message: str,
        scope: QueryScope,
        language: str = "en",
        *,
        complaint_followup: bool = False,
        location: str | None = None,
        has_coordinates: bool = False,
    ) -> ExecutionPlan:
        plan = ExecutionPlan(language=language)
        text = message or ""

        wants_emergency = bool(EMERGENCY_RE.search(text))
        has_filing_intent = bool(COMPLAINT_VERB_RE.search(text))
        # An informational question ("any waterlogging at underpasses?") is not a grievance unless
        # the citizen also asks to report/track something.
        informational = is_question(text) and not has_filing_intent
        wants_complaint = (
            (scope == QueryScope.CIVIC_COMPLAINT and not informational)
            or complaint_followup
            or bool(TRACKING_RE.search(text))
            or (bool(COMPLAINT_ISSUE_RE.search(text)) and has_filing_intent)
        )
        # Pulse keywords inside a grievance being filed ("report waterlogging at ...") describe the
        # complaint; they are not a request for live data.
        filing_complaint = wants_complaint and has_filing_intent
        wants_pulse = scope == QueryScope.CIVIC_LIVE_DATA or (
            bool(PULSE_RE.search(text)) and not wants_emergency and not filing_complaint
        ) or (scope == QueryScope.CIVIC_COMPLAINT and informational)
        # The scope classifier may tag congestion as an emergency; without a life-safety signal it is
        # a City Pulse traffic question.
        if scope == QueryScope.CIVIC_EMERGENCY and not wants_emergency:
            wants_pulse = True
        wants_knowledge = scope == QueryScope.CIVIC_KNOWLEDGE or bool(KNOWLEDGE_RE.search(text))

        if location and (wants_emergency or wants_complaint):
            plan.add(MAIN, f"Resolve location '{location}' to coordinates", ["verify_citizen_location"])
        elif has_coordinates and (wants_emergency or wants_complaint):
            plan.add(MAIN, "Resolve your GPS position to a locality", ["reverse_geocode_coordinates"])
        if wants_emergency:
            plan.add(EMERGENCY, "Triage severity, dispatch nearest unit and clear a green corridor",
                     ["dispatch_emergency_team", "get_emergency_corridor", "override_traffic_signal"])
        if wants_complaint:
            plan.add(COMPLAINT, "Handle civic grievance (track / escalate / draft for confirmation)",
                     ["create_complaint", "get_complaint_status", "list_user_complaints"])
        if wants_pulse and not (wants_emergency and wants_complaint):
            plan.add(PULSE, "Fetch live city data (alerts, traffic, weather, air quality)",
                     ["get_active_alerts", "get_traffic_density", "fetch_weather_inundation"])
        if wants_knowledge and not plan.steps:
            plan.add(KNOWLEDGE, "Answer from verified municipal knowledge with citations", ["search_schemes"])
        return plan


planner = VoiceAgentPlanner()
