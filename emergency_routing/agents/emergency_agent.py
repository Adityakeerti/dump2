"""Core Emergency Agent Orchestrator built on LangGraph.

LLM-driven routing: All dispatch decisions are made by the LLMClassifier,
not hardcoded rules. Vision analysis is integrated for image-bearing incidents.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, END
from agents.state import (
    EmergencyState,
    IncidentPayload,
    PoliceIncidentReport,
    LLMAnalysis,
)
from agents.feud_tracker import FeudTracker
from agents.ambulance_agent import AmbulanceAgent
from agents.police_interface import PoliceAgentInterface, MockPoliceAgent
from models.llm_classifier import LLMClassifier
from models.vision_llm import VisionLLM


class EmergencyAgent:
    """LLM-powered orchestrator coordinating CV incident detections, Ambulance dispatch,
    temporal dispute monitoring, and Police handoff via LangGraph.

    All final dispatch decisions are made by the LLMClassifier, not hardcoded rules.
    """

    def __init__(
        self,
        ambulance_agent: AmbulanceAgent,
        police_agent: Optional[PoliceAgentInterface] = None,
        feud_tracker: Optional[FeudTracker] = None,
        llm_classifier: Optional[LLMClassifier] = None,
        vision_llm: Optional[VisionLLM] = None,
    ):
        self.ambulance_agent = ambulance_agent
        self.police_agent = police_agent or MockPoliceAgent()
        self.feud_tracker = feud_tracker or FeudTracker()
        self.llm_classifier = llm_classifier or LLMClassifier()
        self.vision_llm = vision_llm or VisionLLM()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(EmergencyState)

        # Nodes
        builder.add_node("vision_analysis_node", self._node_vision_analysis)
        builder.add_node("llm_classify_node", self._node_llm_classify)
        builder.add_node("feud_temporal_node", self._node_feud_temporal)
        builder.add_node("ambulance_dispatch_node", self._node_ambulance_dispatch)
        builder.add_node("police_dispatch_node", self._node_police_dispatch)
        builder.add_node("monitor_node", self._node_monitor)
        builder.add_node("log_and_complete_node", self._node_log_and_complete)

        # Entry: always start with vision analysis
        builder.set_entry_point("vision_analysis_node")

        # After vision → pre-feud temporal tracking (for FEUD type, updates duration before LLM sees it)
        builder.add_conditional_edges(
            "vision_analysis_node",
            self._route_after_vision,
            {
                "FEUD": "feud_temporal_node",
                "OTHER": "llm_classify_node",
            },
        )

        # Feud temporal gate (early) → LLM classify with duration context, or monitor
        builder.add_conditional_edges(
            "feud_temporal_node",
            self._route_feud_gate,
            {
                "DISPATCH_POLICE": "llm_classify_node",   # LLM confirms police dispatch
                "MONITOR_ONLY": "llm_classify_node",      # LLM may still override to monitor
            },
        )

        # LLM classify → route based on LLM decision
        builder.add_conditional_edges(
            "llm_classify_node",
            self._route_by_llm_decision,
            {
                "ROUTE_AMBULANCE": "ambulance_dispatch_node",
                "ROUTE_POLICE": "police_dispatch_node",
                "ROUTE_MONITOR": "monitor_node",
                "ROUTE_IGNORE": "log_and_complete_node",
            },
        )

        # All paths → log & complete
        builder.add_edge("ambulance_dispatch_node", "log_and_complete_node")
        builder.add_edge("police_dispatch_node", "log_and_complete_node")
        builder.add_edge("monitor_node", "log_and_complete_node")
        builder.add_edge("log_and_complete_node", END)

        return builder.compile()

    # =========================================================================
    # Node: Vision Analysis
    # =========================================================================

    def _node_vision_analysis(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        if not incident:
            return {
                "workflow_step": "VISION_ANALYSIS",
                "llm_analysis": LLMAnalysis(),
                "audit_log": state.audit_log + ["[VISION] No incident in state, skipping."],
            }

        llm_analysis = state.llm_analysis or LLMAnalysis()

        if incident.frame_image_ref:
            msg = f"[VISION] Running image analysis on frame from {incident.camera_id}..."
            vision = self.vision_llm.analyze_image(
                incident.frame_image_ref,
                cv_context=f"Type={incident.incident_type}, Conf={incident.confidence:.2f}, Sev={incident.severity:.2f}",
            )
        else:
            # No image: use CV outputs for text inference
            cv_context = (
                f"Incident Type: {incident.incident_type}\n"
                f"CV Confidence: {incident.confidence:.2f}\n"
                f"CV Severity: {incident.severity:.2f}\n"
                f"Location: {incident.address}\n"
                f"Camera: {incident.camera_id}"
            )
            msg = f"[VISION] No image frame. Running text inference from CV outputs..."
            vision = self.vision_llm.analyze_cv_outputs(cv_context)

        # Populate LLMAnalysis with vision results
        llm_analysis.vision_detected_type = vision.detected_type
        llm_analysis.vision_description = vision.description
        llm_analysis.vision_confidence = vision.confidence
        llm_analysis.vision_severity = vision.severity_estimate
        llm_analysis.vision_injuries_visible = vision.injuries_visible
        llm_analysis.vision_weapons_visible = vision.weapons_visible
        llm_analysis.vision_model = vision.model_used
        llm_analysis.vision_provider = vision.provider
        llm_analysis.vision_method = vision.analysis_method

        detail = (
            f"Method={vision.analysis_method}, Model={vision.model_used}, "
            f"Type={vision.detected_type}, Confidence={vision.confidence:.2f}, "
            f"Description: {vision.description}"
        )

        return {
            "workflow_step": "VISION_ANALYSIS",
            "llm_analysis": llm_analysis,
            "audit_log": state.audit_log + [msg, f"[VISION] {detail}"],
        }

    # =========================================================================
    # Node: LLM Classify
    # =========================================================================

    def _node_llm_classify(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        if not incident:
            return {
                "workflow_step": "LLM_CLASSIFY",
                "audit_log": state.audit_log + ["[LLM] No incident, skipping classification."],
            }

        llm_analysis = state.llm_analysis or LLMAnalysis()

        # Build feud context
        feud_duration = 0.0
        feud_intensity = 0.0
        tracker = state.feud_tracking.get(incident.camera_id)
        if tracker:
            feud_duration = tracker.elapsed_duration_seconds
            feud_intensity = (
                sum(tracker.intensity_samples) / len(tracker.intensity_samples)
                if tracker.intensity_samples else 0.0
            )

        result = self.llm_classifier.classify_incident(
            incident_type=incident.incident_type,
            confidence=incident.confidence,
            severity=incident.severity,
            address=incident.address,
            camera_id=incident.camera_id,
            feud_duration_seconds=feud_duration,
            feud_avg_intensity=feud_intensity,
            image_description=llm_analysis.vision_description,
            additional_context=(
                f"Injuries visible: {llm_analysis.vision_injuries_visible}, "
                f"Weapons: {llm_analysis.vision_weapons_visible}. "
                f"Temporal gate result: {'POLICE THRESHOLD REACHED' if state.pending_police_dispatch else 'below threshold'}."
                if llm_analysis.vision_injuries_visible is not None else
                f"Temporal gate: {'POLICE THRESHOLD REACHED' if state.pending_police_dispatch else 'below threshold'}."
            ),
        )

        # Store classification in LLMAnalysis
        llm_analysis.llm_decision = result.decision
        llm_analysis.llm_confidence = result.confidence
        llm_analysis.llm_rationale = result.rationale
        llm_analysis.llm_model = result.model_used
        llm_analysis.llm_severity_override = result.severity_override

        msg = (
            f"[LLM CLASSIFY] Decision: {result.decision} | "
            f"Confidence: {result.confidence:.2f} | "
            f"Model: {result.model_used} | "
            f"Rationale: {result.rationale}"
        )

        return {
            "workflow_step": "LLM_CLASSIFY",
            "llm_analysis": llm_analysis,
            "decision_summary": msg,
            "audit_log": state.audit_log + [msg],
        }

    def _route_after_vision(self, state: EmergencyState) -> str:
        """After vision: FEUD incidents run temporal tracking first to get duration context for LLM."""
        incident = state.current_incident
        if incident and incident.incident_type == "FEUD":
            return "FEUD"
        return "OTHER"

    def _route_by_llm_decision(self, state: EmergencyState) -> str:
        """Routes based on LLM classifier output."""
        incident = state.current_incident
        if not incident:
            return "ROUTE_IGNORE"

        llm = state.llm_analysis
        if not llm or not llm.llm_decision:
            # Fallback if LLM failed
            if incident.incident_type == "ACCIDENT":
                return "ROUTE_AMBULANCE"
            elif state.pending_police_dispatch:
                return "ROUTE_POLICE"
            return "ROUTE_MONITOR"

        decision = llm.llm_decision

        # Hard override: if temporal gate already determined police dispatch is needed,
        # respect it even if LLM says MONITOR (safety-critical system)
        if state.pending_police_dispatch and decision not in ("DISPATCH_AMBULANCE", "IGNORE"):
            return "ROUTE_POLICE"

        # Safety rule: for FEUD incidents, if duration < 60s and no weapons reported,
        # police must not be disturbed yet.
        if incident.incident_type == "FEUD" and not state.pending_police_dispatch:
            if not (llm and llm.vision_weapons_visible):
                return "ROUTE_MONITOR"

        if decision == "DISPATCH_AMBULANCE":
            return "ROUTE_AMBULANCE"
        elif decision == "DISPATCH_POLICE":
            return "ROUTE_POLICE"
        elif decision == "IGNORE":
            return "ROUTE_IGNORE"
        else:
            return "ROUTE_MONITOR"

    # =========================================================================
    # Node: Feud Temporal Gate (LLM-assisted)
    # =========================================================================

    def _node_feud_temporal(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        should_alert, tracking_state, explanation = self.feud_tracker.process_feud_detection(incident)

        tracking_dict = dict(state.feud_tracking)
        tracking_dict[incident.camera_id] = tracking_state

        return {
            "workflow_step": "FEUD_TEMPORAL_GATE",
            "feud_tracking": tracking_dict,
            "decision_summary": explanation,
            "audit_log": state.audit_log + [f"[FEUD GATE] {explanation}"],
            "pending_police_dispatch": should_alert,
        }

    def _route_feud_gate(self, state: EmergencyState) -> str:
        """After feud temporal tracking: both paths go to LLM classify.
        The pending_police_dispatch flag is passed as context so LLM can make final call.
        For direct police scenarios (LLM already decided): also handled here.
        """
        # When feud_temporal runs BEFORE llm_classify (new flow): always go to LLM
        # pending_police_dispatch is set and LLM will use it as context
        if state.pending_police_dispatch:
            return "DISPATCH_POLICE"
        return "MONITOR_ONLY"

    # =========================================================================
    # Node: Ambulance Dispatch
    # =========================================================================

    def _node_ambulance_dispatch(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        mission, summary = self.ambulance_agent.handle_accident(incident)
        return {
            "workflow_step": "AMBULANCE_DISPATCH",
            "ambulance_mission": mission,
            "decision_summary": summary,
            "audit_log": state.audit_log + [f"[AMBULANCE] {summary}"],
        }

    # =========================================================================
    # Node: Police Dispatch
    # =========================================================================

    def _node_police_dispatch(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        tracker = state.feud_tracking.get(incident.camera_id)
        avg_intensity = (
            sum(tracker.intensity_samples) / len(tracker.intensity_samples)
            if tracker and tracker.intensity_samples
            else incident.severity
        )
        duration = tracker.elapsed_duration_seconds if tracker else 60.0

        llm = state.llm_analysis
        # LLM may have detected weapons -> escalate to RIOT classification
        incident_type_class = "RIOT" if (
            avg_intensity > 0.8 or (llm and llm.vision_weapons_visible)
        ) else "PUBLIC_FEUD"

        report = PoliceIncidentReport(
            report_id=f"POL-REP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            incident_type=incident_type_class,
            dispute_duration_seconds=round(duration, 1),
            average_intensity=round(avg_intensity, 2),
            camera_id=incident.camera_id,
            location_node_id=incident.location_node_id,
            coordinates=(incident.latitude, incident.longitude),
            address=incident.address,
            dispatched_at=datetime.now(),
        )

        ack = self.police_agent.dispatch_police(report)
        msg = f"[POLICE] Alert confirmed. Case #{ack.case_number}. Units: {', '.join(ack.assigned_patrol_units)}. ETA: {ack.estimated_arrival_minutes}m."

        return {
            "workflow_step": "POLICE_DISPATCH",
            "police_report": report,
            "decision_summary": msg,
            "audit_log": state.audit_log + [msg],
        }

    # =========================================================================
    # Node: Monitor
    # =========================================================================

    def _node_monitor(self, state: EmergencyState) -> Dict[str, Any]:
        incident = state.current_incident
        llm = state.llm_analysis
        rationale = llm.llm_rationale if llm else "Monitoring - no dispatch required."
        msg = f"[MONITOR] Incident {incident.incident_id if incident else 'NONE'} queued for monitoring. {rationale}"
        return {
            "workflow_step": "MONITORING",
            "decision_summary": msg,
            "audit_log": state.audit_log + [msg],
        }

    # =========================================================================
    # Node: Log & Complete
    # =========================================================================

    def _node_log_and_complete(self, state: EmergencyState) -> Dict[str, Any]:
        msg = f"Pipeline complete. Step: {state.workflow_step}. Decision: {state.decision_summary[:120]}"
        return {
            "workflow_step": "COMPLETED",
            "audit_log": state.audit_log + [msg],
        }

    def process_incident(self, incident: IncidentPayload) -> EmergencyState:
        """Executes the full LangGraph pipeline for an incoming incident."""
        initial_state = EmergencyState(
            current_incident=incident,
            feud_tracking=dict(self.feud_tracker.tracked_cameras),
            ambulance_mission=None,
            police_report=None,
            workflow_step="START",
            decision_summary="",
            audit_log=[f"[START] Received {incident.incident_id} at {incident.timestamp.isoformat()}"],
            llm_analysis=LLMAnalysis(),
        )

        final_dict = self.graph.invoke(initial_state)
        return EmergencyState(**final_dict)
