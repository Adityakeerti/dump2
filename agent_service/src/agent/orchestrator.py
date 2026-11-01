"""City Sense main voice agent: guardrails -> planner -> strict delegation -> merged answer.

Pipeline per turn
1. Input guardrail (prompt injection / jailbreak).
2. Scope classification + polite refusals for greetings and clearly off-topic requests.
3. ``VoiceAgentPlanner`` decomposes the utterance into ordered steps (planner lives only here).
4. Steps execute in order:
   - main-agent steps call ONLY cross-cutting tools the main agent owns (location resolution);
   - every domain step is delegated to exactly one specialist, which is the sole caller of its
     domain tools (enforced by ``tool_registry.call_tool``).
5. Specialist results are merged into one citizen-facing answer with the plan and tool trace.

Knowledge-only turns fall through to the retrieval + LLM pipeline in ``service.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.guardrails import (
    PoliteRefusalResult,
    QueryScope,
    check_input_safety,
    classify_scope,
    refuse_injection,
    refuse_out_of_scope,
    respond_civic_greeting,
)
import re

from src.agent import app_control
from src.agent.composer import compose
from src.agent.planner import ExecutionPlan, PlanStep, planner
from src.agent.schemas import ChatRequest, PendingActionView, PlanStepView, ToolCallView
from src.agent.subagents import (
    CityPulseSpecialist,
    CivicComplaintSpecialist,
    EmergencySpecialist,
    KnowledgeSpecialist,
    SubAgentResult,
)
from src.agent.subagents.complaint_agent import extract_location
from src.agent.tool_registry import COMPLAINT, EMERGENCY, KNOWLEDGE, MAIN, PULSE, ToolTrace, call_tool
from src.auth.schemas import Principal
from src.models import AgentConfig, ChatSession

logger = logging.getLogger("citysense.orchestrator")

COMPLAINT_CONTEXT_WORDS = ("complaint", "ticket", "grievance", "शिकायत")
COMPLAINT_FOLLOWUP_WORDS = (
    "active", "all", "show", "list", "check", "open", "pending", "status", "which are", "सक्रिय", "दिखाओ",
)
# Questions about City Sense itself or this conversation: answered by the LLM from history + catalog.
CAPABILITY_RE = re.compile(
    r"\bwhat\s+(?:all\s+)?(?:things\s+)?(?:can|could)\s+you\s+do\b|\bwhat\s+(?:all\s+)?(?:things\s+)?you\s+(?:can|could)\s+do\b|\\b(?:things|stuff)\\s+you\\s+(?:can|could)\\s+do\\b|\bwhat\s+(?:all\s+)?(?:things\s+)?(?:are\s+)?you\s+"
    r"(?:able|capable)\b|\bhow\s+can\s+you\s+help\b|\bwhat\s+do\s+you\s+do\b|\byour\s+(?:features|abilities|capabilities)\b"
    r"|तुम\s+क्या\s+(?:कर|कर\s+सकते)|आप\s+क्या\s+(?:कर|कर\s+सकते)|क्या\s+मदद",
    re.I,
)
CONVERSATION_RE = re.compile(
    r"\bwhat\s+did\s+(?:i|you)\s+(?:just\s+)?(?:ask|say|tell|mean)\b|\b(?:repeat|summari[sz]e)\s+(?:that|it|our|this|the\s+conversation)\b"
    r"|\bwho\s+are\s+you\b|\bwhat(?:'s|\s+is)\s+your\s+name\b|\bare\s+you\s+(?:a\s+)?(?:bot|human|ai|real)\b"
    r"|\b(?:thank\s*(?:s|\s+you)|ok(?:ay)?|cool|great|got\s+it)\b[\s!.]*$|मैंने\s+क्या\s+पूछा|तुम\s+कौन|आप\s+कौन|धन्यवाद",
    re.I,
)

STATUS_PRIORITY = ["ACTION_PENDING", "CLARIFICATION_REQUIRED", "HANDOFF_REQUIRED", "ANSWERED", "ABSTAINED", "UNAVAILABLE"]


@dataclass
class TurnOutcome:
    handled: bool
    status: str = ""
    answer: str = ""
    sources: list[Any] = field(default_factory=list)
    cta: str | None = None
    pending_action: PendingActionView | None = None
    plan: list[PlanStepView] | None = None
    tool_calls: list[ToolCallView] | None = None
    action_data: dict[str, Any] | None = None
    client_actions: list[dict[str, Any]] | None = None


def _refusal(result: PoliteRefusalResult, default_cta: str, composed: str | None = None) -> TurnOutcome:
    """Reply text from the LLM when available; the template is only the offline fallback."""
    return TurnOutcome(True, "ANSWERED", composed or result.message, [], result.suggested_cta or default_cta)


def _plan_view(plan: ExecutionPlan) -> list[PlanStepView]:
    return [
        PlanStepView(id=s.id, executor=s.executor, action=s.action, tools=s.tools, status=s.status, detail=s.detail)
        for s in plan.steps
    ]


def _trace_view(trace: ToolTrace) -> list[ToolCallView]:
    return [
        ToolCallView(tool=c.tool, caller=c.caller, served=c.served, ok=c.ok, durationMs=c.duration_ms)
        for c in trace.calls
    ]


def _is_complaint_followup(message: str, history: list[dict[str, Any]] | None) -> bool:
    if not history:
        return False
    # Only the citizen's own recent words count: the agent's replies mention complaints all the time.
    recent = " ".join(
        m.get("content", "") for m in history[-4:] if isinstance(m, dict) and m.get("role") == "user" and m.get("content")
    )
    recent = recent.lower()
    return any(w in recent for w in COMPLAINT_CONTEXT_WORDS) and any(
        w in message.lower() for w in COMPLAINT_FOLLOWUP_WORDS
    )


def finalize_plan(plan: list[PlanStepView] | None, status: str) -> list[PlanStepView] | None:
    """Close out steps answered downstream (knowledge fall-through) with the turn's real outcome."""
    for step in plan or []:
        if step.status == "planned":
            step.status = "failed" if status == "UNAVAILABLE" else "completed"
            step.detail = f"retrieval pipeline: {status}"
    return plan


class SupervisorOrchestrator:
    """Main voice agent: owns the planner and the cross-cutting tools; delegates everything else."""

    name = MAIN

    def __init__(self) -> None:
        self.complaint_agent = CivicComplaintSpecialist()
        self.emergency_agent = EmergencySpecialist()
        self.city_pulse_agent = CityPulseSpecialist()
        self.knowledge_agent = KnowledgeSpecialist()
        self.specialists = {
            COMPLAINT: self.complaint_agent,
            EMERGENCY: self.emergency_agent,
            PULSE: self.city_pulse_agent,
            KNOWLEDGE: self.knowledge_agent,
        }

    async def evaluate_turn(
        self,
        session: AsyncSession | None,
        principal: Principal,
        request: ChatRequest,
        chat_session: ChatSession,
        agent: AgentConfig,
        language: str,
        city: str,
        started: float,
        history: list[dict[str, Any]] | None = None,
    ) -> TurnOutcome:
        """Run guardrails, plan, and delegated execution.

        ``handled=False`` means the caller should continue with the retrieval + LLM pipeline;
        ``plan`` is still populated so that response can show it.
        """
        # 1. Input guardrail
        from src.agent.events import turn_meta

        meta = turn_meta.get()
        guard = check_input_safety(request.message)
        if meta is not None:
            meta["guard"] = {"safe": guard.is_safe, "risk": round(guard.risk_score, 2), "reason": guard.reason}
        if not guard.is_safe:
            logger.warning("Unsafe input from %s: reason=%s risk=%.2f", principal.user_id, guard.reason, guard.risk_score)
            # The unsafe text itself is never sent to the model.
            composed = await compose(intent="unsafe_request", message=None, language=language, history=history)
            return _refusal(refuse_injection(language=language), "explore_schemes", composed)

        # 2. Scope + polite refusals
        scope = classify_scope(request.message, language=language)
        if meta is not None:
            meta["scope"] = scope.scope.value
        if scope.scope == QueryScope.CIVIC_GREETING:
            composed = await compose(intent="greeting", message=request.message, language=language, history=history)
            return _refusal(respond_civic_greeting(language=language), "report_issue", composed)
        if scope.scope == QueryScope.OUT_OF_SCOPE and scope.detected_topic and scope.detected_topic not in (
            "non-civic general inquiry",
            "empty_query",
        ):
            composed = await compose(intent=f"off_topic:{scope.detected_topic}", message=request.message,
                                     language=language, history=history)
            return _refusal(refuse_out_of_scope(topic=scope.detected_topic, language=language), "explore_schemes",
                            composed)

        # 3. Plan
        ctx = request.context
        has_coords = ctx.latitude is not None and ctx.longitude is not None
        location = extract_location(request.message)
        plan = planner.plan(
            request.message,
            scope.scope,
            language,
            complaint_followup=_is_complaint_followup(request.message, history),
            location=location,
            has_coordinates=has_coords,
        )
        intents = app_control.parse(request.message)
        kinds = app_control.data_kinds(intents)
        if intents:
            # Data the app shows is still answered by its owning desk; the main agent adds navigation.
            if "complaints" in kinds and not plan.for_executor(COMPLAINT):
                plan.add(COMPLAINT, "List your complaints", ["list_user_complaints"])
            if "businesses" in kinds and not plan.for_executor(KNOWLEDGE):
                plan.add(KNOWLEDGE, "Recommend local businesses", ["find_local_businesses"])
            if kinds & {"notices", "events", "incidents"} and not plan.for_executor(PULSE):
                plan.add(PULSE, "Fetch " + ", ".join(sorted(kinds & {"notices", "events", "incidents"})),
                         ["get_govt_notices", "get_events", "get_city_incidents"])
            ui = [i for i in intents if i.kind != "data"]
            if ui:
                tools = sorted({{"navigate": "navigate_app", "focus_map": "focus_map", "find_agent": "find_local_agent",
                                 "preference": "set_app_preference"}[i.kind] for i in ui})
                plan.steps.insert(0, PlanStep(id=0, executor=MAIN, action="Control the app", tools=tools))
            for i, st in enumerate(plan.steps, 1):
                st.id = i
        if agent.agent_id == "municipal":
            # The municipal persona files complaints through its LLM tool loop in service.py.
            plan.steps = [s for s in plan.steps if s.executor != COMPLAINT]

        domain_steps = [s for s in plan.steps if s.executor not in (MAIN, KNOWLEDGE)]
        app_step = any(s.action == "Control the app" for s in plan.steps)
        if not domain_steps and not app_step:
            # About City Sense itself or this conversation: the main agent answers from history + catalog
            # instead of searching documents (which would abstain).
            meta = "capabilities" if CAPABILITY_RE.search(request.message) else (
                "conversation" if CONVERSATION_RE.search(request.message) else None)
            if meta:
                composed = await compose(intent=meta, message=request.message, language=language, history=history)
                if composed:
                    step = PlanStepView(id=1, executor=MAIN, action="Answer from conversation and capabilities",
                                        tools=["llm"], status="completed")
                    return TurnOutcome(True, "ANSWERED", composed, [], None, None, [step])
            return TurnOutcome(handled=False, plan=_plan_view(plan) if plan.steps else None)

        # 4. Execute
        trace = ToolTrace()
        resolved: dict[str, Any] = {"location": location}
        if has_coords:
            resolved.update(latitude=ctx.latitude, longitude=ctx.longitude)
        results: list[tuple[PlanStep, SubAgentResult]] = []
        client_actions: list[dict[str, Any]] = []
        app_lines: list[str] = []

        for step in plan.steps:
            step.status = "running"
            try:
                if step.executor == MAIN and step.action == "Control the app":
                    step.detail = await self._run_app_step(intents, principal, resolved, language, trace,
                                                           client_actions, app_lines)
                    step.status = "completed"
                    continue
                if step.executor == MAIN:
                    step.detail = await self._run_main_step(step, request, principal, resolved, trace)
                    step.status = "completed"
                    continue
                if step.executor == KNOWLEDGE and step.action == "Recommend local businesses":
                    result = await self.knowledge_agent.recommend_businesses(
                        request.message, principal, language, trace,
                        latitude=resolved.get("latitude"), longitude=resolved.get("longitude"),
                        area=resolved.get("location"),
                    )
                    results.append((step, result))
                    step.status = "completed"
                    step.detail = f"{len(result.metadata['card']['businesses'])} found"
                    continue
                if step.executor == KNOWLEDGE:
                    step.status = "skipped"
                    continue
                specialist = self.specialists[step.executor]
                result = await specialist.execute(
                    session=session,
                    principal=principal,
                    message=request.message,
                    context=ctx,
                    language=language,
                    history=history,
                    session_id=getattr(chat_session, "session_id", None),
                    location=resolved.get("location"),
                    latitude=resolved.get("latitude"),
                    longitude=resolved.get("longitude"),
                    trace=trace,
                    feeds=sorted(kinds & {"notices", "events", "incidents"}) if step.executor == PULSE else None,
                )
                results.append((step, result))
                step.status = "completed"
                step.detail = result.status
            except Exception:
                logger.exception("Plan step %s (%s) failed", step.id, step.executor)
                step.status = "failed"

        if not results and not app_lines:
            return TurnOutcome(handled=False, plan=_plan_view(plan), tool_calls=_trace_view(trace))
        if not results:
            composed = await compose(intent="app_action", message=request.message, language=language,
                                     history=history, facts=app_lines)
            return TurnOutcome(True, "ANSWERED", composed or "\n".join(app_lines), [], None, None, _plan_view(plan),
                               _trace_view(trace), None, client_actions or None)
        outcome = self._merge(plan, results, trace, resolved, language)
        template = ("\n".join(app_lines) + "\n\n" if app_lines else "") + outcome.answer
        # The main agent voices the desks' verified results; their templates are the fallback.
        desks = ",".join(sorted({st.executor for st, _ in results}))
        composed = await compose(
            intent=f"specialist_result:{desks}", message=request.message, language=language, history=history,
            facts=[*app_lines, *(r.response_text for _, r in results)],
        )
        outcome.answer = composed or template
        outcome.client_actions = client_actions or None
        return outcome

    async def _run_app_step(
        self,
        intents: list,
        principal: Principal,
        resolved: dict[str, Any],
        language: str,
        trace: ToolTrace,
        client_actions: list[dict[str, Any]],
        app_lines: list[str],
    ) -> str:
        """Main agent drives the app with its own control tools; the client executes the actions."""
        hi = language == "hi"
        names = app_control.SCREEN_NAMES["hi" if hi else "en"]
        done: list[str] = []
        for intent in intents:
            if intent.kind == "data":
                continue
            if intent.kind == "navigate":
                res = await call_tool(MAIN, "navigate_app", intent.params, principal.user_id, trace)
                if intent.params["screen"] == "complaint":
                    app_lines.append(f"खोल रहा हूँ: शिकायत #{intent.params['target_id']}" if hi
                                     else f"Opening complaint #{intent.params['target_id']}.")
                else:
                    app_lines.append(f"{names[intent.params['screen']]} खोल रहा हूँ।" if hi
                                     else f"Opening {names[intent.params['screen']]}.")
            elif intent.kind == "focus_map":
                res = await call_tool(MAIN, "focus_map", intent.params, principal.user_id, trace)
                label = res["client_action"].get("label") or intent.params["query"]
                app_lines.append(f"नक्शे पर {label} दिखा रहा हूँ।" if hi else f"Showing {label} on the map.")
                client_actions.append({"type": "navigate", "screen": "explore"})
            elif intent.kind == "find_agent":
                res = await call_tool(MAIN, "find_local_agent", intent.params, principal.user_id, trace,
                                      latitude=resolved.get("latitude"), longitude=resolved.get("longitude"))
                if res.get("found"):
                    av = res["avatar"]
                    app_lines.append(f"{av['name']} ({av.get('title', '')}) से जोड़ रहा हूँ।" if hi
                                     else f"Connecting you to {av['name']} — {av.get('title', '')}.")
                else:
                    app_lines.append(f"मुझे '{intent.params['name']}' नाम का कोई लोकल एजेंट नहीं मिला।" if hi
                                     else f"I couldn't find a local agent called '{intent.params['name']}'.")
            elif intent.kind == "preference":
                res = await call_tool(MAIN, "set_app_preference", intent.params, principal.user_id, trace)
                if "language" in intent.params:
                    app_lines.append("अब मैं हिंदी में जवाब दूँगा।" if intent.params["language"] == "hi"
                                     else "Switched to English.")
                if "voice_auto_play" in intent.params:
                    on = intent.params["voice_auto_play"]
                    app_lines.append(("आवाज़ चालू।" if on else "आवाज़ बंद — मैं केवल लिखकर जवाब दूँगा।") if hi
                                     else ("Voice replies on." if on else "Voice muted — I'll reply in text only."))
            else:
                continue
            if res.get("client_action"):
                client_actions.append(res["client_action"])
            done.append(intent.kind)
        return ", ".join(done) or "nothing to do"

    async def _run_main_step(
        self, step: PlanStep, request: ChatRequest, principal: Principal, resolved: dict[str, Any], trace: ToolTrace
    ) -> str:
        """Main agent executes only the cross-cutting tools it owns."""
        if "verify_citizen_location" in step.tools and resolved.get("location"):
            res = await call_tool(MAIN, "verify_citizen_location", {"query": resolved["location"]},
                                  principal.user_id, trace)
            data = res.get("data", res)
            if resolved.get("latitude") is None and data.get("lat") is not None:
                resolved.update(latitude=data["lat"], longitude=data["lng"])
            resolved["zone"] = data.get("zone")
            resolved["precision"] = data.get("precision")
            return f"{resolved['location']} → {data.get('lat')}, {data.get('lng')} ({data.get('precision')})"
        if "reverse_geocode_coordinates" in step.tools:
            res = await call_tool(MAIN, "reverse_geocode_coordinates",
                                  {"lat": resolved["latitude"], "lng": resolved["longitude"]}, principal.user_id, trace)
            data = res.get("data", res)
            resolved["location"] = data.get("nearest_landmark") or data.get("display_name")
            resolved["zone"] = data.get("zone")
            return f"GPS → near {resolved['location']}"
        return "nothing to resolve"

    @staticmethod
    def _merge(
        plan: ExecutionPlan,
        results: list[tuple[PlanStep, SubAgentResult]],
        trace: ToolTrace,
        resolved: dict[str, Any],
        language: str,
    ) -> TurnOutcome:
        statuses = [r.status for _, r in results]
        status = min(statuses, key=lambda s: STATUS_PRIORITY.index(s) if s in STATUS_PRIORITY else len(STATUS_PRIORITY))
        answer = "\n\n---\n\n".join(r.response_text for _, r in results if r.response_text)
        # Emergency CTA wins: life safety first.
        cta = next((r.cta for st, r in results if st.executor == EMERGENCY and r.cta), None) or next(
            (r.cta for _, r in results if r.cta), None
        )
        pending = None
        action_data: dict[str, Any] = {}
        sources: list[Any] = []
        for st, r in results:
            sources.extend(r.sources or [])
            if r.action and r.action.get("token") and pending is None:
                pending = PendingActionView(
                    token=r.action["token"],
                    summary=r.action["summary"],
                    expiresAt=r.action["expires_at"],
                    action_type=r.action.get("action_type", "create_complaint"),
                    photoSuggested=bool(r.action.get("photo_suggested")),
                )
            if st.executor == EMERGENCY and r.action:
                action_data["emergency"] = r.action
            if r.metadata.get("card"):
                action_data[st.executor] = r.metadata["card"]
        if resolved.get("location"):
            action_data["location"] = {
                k: resolved.get(k) for k in ("location", "latitude", "longitude", "zone", "precision")
            }
        return TurnOutcome(
            handled=True,
            status=status,
            answer=answer,
            sources=sources,
            cta=cta,
            pending_action=pending,
            plan=_plan_view(plan),
            tool_calls=_trace_view(trace),
            action_data=action_data or None,
        )


# Global supervisor instance
supervisor = SupervisorOrchestrator()
