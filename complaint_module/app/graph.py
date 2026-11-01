from typing import TypedDict, Optional, List, Dict, Any
from langgraph.graph import StateGraph, START, END

from .models import (
    Complaint,
    ComplaintStatus,
    ActorRole,
    TimelineEvent,
    WorkerModel,
    AuthorityModel,
    CitizenNotification,
)
from .llm_service import llm
import uuid
import datetime


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CivicWorkflowState(TypedDict, total=False):
    complaint: Complaint
    action_type: str  # "INTAKE", "ESCALATE_TICK", "RESOLVE"
    workers: List[Dict[str, Any]]
    authorities: List[AuthorityModel]
    resolution_note: Optional[str]
    proof_photo_url: Optional[str]
    resolved_by: Optional[str]


# --- Graph Nodes ---

def node_intake_classifier(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Uses LLM/Vision/classifier to classify citizen problem, detect department,
    and determine priority without requiring citizens to manually choose municipal taxonomy."""
    complaint = state["complaint"]
    analysis = llm.classify_and_route(
        text=complaint.description,
        title=complaint.title,
        location=complaint.location.address
    )

    detected_cat = analysis.get("category")
    if detected_cat:
        complaint.category = detected_cat
    elif not complaint.category or "detect" in complaint.category.lower():
        complaint.category = "pothole"

    complaint.priority = analysis.get("priority", "MEDIUM")
    complaint.llm_reasoning = analysis.get("reasoning", "")
    clean_title = analysis.get("clean_title")
    if clean_title:
        complaint.title = clean_title

    state["_target_department"] = analysis.get("department", "")
    state["_llm_powered"] = analysis.get("llm_powered", False)
    return state


def node_worker_dispatcher(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Matches department & skills with available municipal crews

    and assigns the work order to the field worker."""
    complaint = state["complaint"]
    available_workers = state.get("workers", [])
    target_dept = state.get("_target_department", "")

    matched = None
    for w in available_workers:
        if target_dept and w.get("department") == target_dept:
            matched = w
            break

    if not matched:
        cat_lower = complaint.category.lower()
        for w in available_workers:
            if any(m in cat_lower for m in w.get("category_match", [])):
                matched = w
                break

    if not matched and available_workers:
        matched = available_workers[0]

    if matched:
        complaint.assigned_worker = WorkerModel(
            id=matched["id"],
            name=matched["name"],
            team=matched["team"],
            department=matched["department"],
            phone=matched["phone"],
            rating=matched.get("rating", 4.8),
        )

    complaint.status = ComplaintStatus.WORKER_ASSIGNED
    complaint.updated_at = _iso_now()

    powered_tag = " (LangGraph + LLM)" if state.get("_llm_powered") else " (LangGraph Engine)"
    complaint.timeline.append(
        TimelineEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            timestamp=_iso_now(),
            actor=ActorRole.MUNICIPAL_AGENT,
            actor_name="Municipal Intake Agent (LangGraph)",
            action="WORKER_ASSIGNED",
            message=(
                f"LangGraph Ingestion Node processed report{powered_tag}. "
                f"Auto-routed to {complaint.assigned_worker.department if complaint.assigned_worker else 'Civil Dept'} "
                f"[Priority: {complaint.priority}]. Assigned worker: "
                f"{complaint.assigned_worker.name if complaint.assigned_worker else 'Field Crew'} "
                f"({complaint.assigned_worker.team if complaint.assigned_worker else 'General'}). "
                f"Diagnosis: {complaint.llm_reasoning}"
            ),
            badge_type="info"
        )
    )
    return state


def node_sla_governor(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Evaluates SLA time consumption and issues progressive warnings 1 to 5."""
    complaint = state["complaint"]
    now_str = _iso_now()
    complaint.updated_at = now_str

    if complaint.status == ComplaintStatus.WORKER_ASSIGNED:
        complaint.status = ComplaintStatus.WARNING_1
        complaint.warnings_count = 1
        complaint.sla_remaining_seconds = max(0, complaint.sla_seconds - 6)
        msg = f"Warning 1/5 dispatched to worker {complaint.assigned_worker.name if complaint.assigned_worker else 'crew'}. SLA countdown active (20% elapsed)."
        badge = "warning"

    elif complaint.status == ComplaintStatus.WARNING_1:
        complaint.status = ComplaintStatus.WARNING_2
        complaint.warnings_count = 2
        complaint.sla_remaining_seconds = max(0, complaint.sla_seconds - 12)
        msg = "Warning 2/5 issued. Task status pending on-site progress. 40% SLA elapsed."
        badge = "warning"

    elif complaint.status == ComplaintStatus.WARNING_2:
        complaint.status = ComplaintStatus.WARNING_3
        complaint.warnings_count = 3
        complaint.sla_remaining_seconds = max(0, complaint.sla_seconds - 18)
        msg = "Warning 3/5 issued. 60% SLA elapsed. Department supervisor notified of crew inaction."
        badge = "warning"

    elif complaint.status == ComplaintStatus.WARNING_3:
        complaint.status = ComplaintStatus.WARNING_4
        complaint.warnings_count = 4
        complaint.sla_remaining_seconds = max(0, complaint.sla_seconds - 24)
        msg = "Warning 4/5 issued. Urgent pre-breach alert. 80% SLA elapsed. Field crew penalty warning active."
        badge = "danger"

    elif complaint.status == ComplaintStatus.WARNING_4:
        complaint.status = ComplaintStatus.WARNING_5
        complaint.warnings_count = 5
        complaint.sla_remaining_seconds = 0
        msg = "CRITICAL Warning 5/5: Worker SLA fully breached! Assigned crew failed to resolve ticket in time. Initiating bureaucratic escalation ladder."
        badge = "danger"

    else:
        return state

    complaint.timeline.append(
        TimelineEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            timestamp=now_str,
            actor=ActorRole.MUNICIPAL_COORDINATOR_AGENT,
            actor_name="Municipal Coordinator Agent (LangGraph)",
            action=complaint.status.value,
            message=msg,
            badge_type=badge
        )
    )
    return state


def node_authority_escalator(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Escalates breached tickets along the bureaucratic ladder:

    Ward Officer -> Municipal Commissioner -> CM Grievance Redressal Portal."""
    complaint = state["complaint"]
    authorities = state.get("authorities", [])
    auth_map = {a.level: a for a in authorities}
    now_str = _iso_now()
    complaint.updated_at = now_str

    if complaint.status == ComplaintStatus.WARNING_5:
        ward_officer = auth_map.get(1)
        complaint.status = ComplaintStatus.ESCALATED_WARD_OFFICER
        complaint.current_authority = ward_officer

        memo = llm.generate_escalation_memo(
            tracking_id=complaint.tracking_id,
            title=complaint.title,
            address=complaint.location.address,
            authority_tier="Ward Officer",
            authority_name=ward_officer.name if ward_officer else "Ward Officer",
            warnings_count=5
        )
        complaint.escalation_memo = memo
        complaint.timeline.append(
            TimelineEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                timestamp=now_str,
                actor=ActorRole.MUNICIPAL_COORDINATOR_AGENT,
                actor_name="Municipal Coordinator Agent (LangGraph)",
                action="ESCALATE_WARD_OFFICER",
                message=f"Escalation Level 1: Transferred complaint to Ward Officer ({ward_officer.name if ward_officer else 'Ward Officer'}). Memo: {memo}",
                badge_type="escalation"
            )
        )

    elif complaint.status == ComplaintStatus.ESCALATED_WARD_OFFICER:
        commissioner = auth_map.get(2)
        complaint.status = ComplaintStatus.ESCALATED_MUNICIPAL_COMMISSIONER
        complaint.current_authority = commissioner

        memo = llm.generate_escalation_memo(
            tracking_id=complaint.tracking_id,
            title=complaint.title,
            address=complaint.location.address,
            authority_tier="Municipal Commissioner",
            authority_name=commissioner.name if commissioner else "Commissioner",
            warnings_count=5
        )
        complaint.escalation_memo = memo
        complaint.timeline.append(
            TimelineEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                timestamp=now_str,
                actor=ActorRole.MUNICIPAL_COORDINATOR_AGENT,
                actor_name="Municipal Coordinator Agent (LangGraph)",
                action="ESCALATE_MUNICIPAL_COMMISSIONER",
                message=f"Escalation Level 2: Ward Officer SLA overdue! Escalated to Municipal Commissioner ({commissioner.name if commissioner else 'Commissioner'}). Memo: {memo}",
                badge_type="escalation"
            )
        )

    elif complaint.status == ComplaintStatus.ESCALATED_MUNICIPAL_COMMISSIONER:
        cm_portal = auth_map.get(3)
        complaint.status = ComplaintStatus.ESCALATED_CM_PORTAL
        complaint.current_authority = cm_portal

        memo = llm.generate_escalation_memo(
            tracking_id=complaint.tracking_id,
            title=complaint.title,
            address=complaint.location.address,
            authority_tier="CM Grievance Redressal Cell",
            authority_name=cm_portal.name if cm_portal else "CM Portal",
            warnings_count=5
        )
        complaint.escalation_memo = memo
        complaint.timeline.append(
            TimelineEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                timestamp=now_str,
                actor=ActorRole.MUNICIPAL_COORDINATOR_AGENT,
                actor_name="Municipal Coordinator Agent (LangGraph)",
                action="ESCALATE_CM_PORTAL",
                message=f"Escalation Level 3 (Apex): Municipal Commissioner SLA breached! Transmitted to State CM Portal (Helpline 1905). Apex Summons: {memo}",
                badge_type="escalation"
            )
        )

    elif complaint.status == ComplaintStatus.ESCALATED_CM_PORTAL:
        cm_portal = auth_map.get(3)
        complaint.timeline.append(
            TimelineEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                timestamp=now_str,
                actor=ActorRole.CM_PORTAL,
                actor_name=cm_portal.name if cm_portal else "CM Portal",
                action="APEX_AUDIT_PING",
                message="Apex Governance Monitor: Active departmental compliance summons pending response.",
                badge_type="danger"
            )
        )

    return state


def node_resolution_handler(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Marks ticket resolved, records field notes, halts escalation,
    and records the exact stage where the issue was resolved."""
    complaint = state["complaint"]
    now_str = _iso_now()
    note = state.get("resolution_note") or "Work order completed and site verified."
    resolved_by = state.get("resolved_by") or (complaint.assigned_worker.name if complaint.assigned_worker else "Municipal Worker")

    complaint.resolved_at_stage = complaint.status.value
    complaint.status = ComplaintStatus.RESOLVED
    complaint.resolution_note = note
    complaint.resolution_time = now_str
    complaint.updated_at = now_str
    return state


def node_citizen_notifier(state: CivicWorkflowState) -> CivicWorkflowState:
    """LangGraph Node: Uses LLM to draft and dispatch an official notification to citizen Aditya Sharma."""
    complaint = state["complaint"]
    now_str = _iso_now()
    resolved_by = state.get("resolved_by") or (complaint.assigned_worker.name if complaint.assigned_worker else "Municipal Worker")
    note = complaint.resolution_note or "Issue repaired on-site."

    notif_data = llm.generate_citizen_notification(
        citizen_name=complaint.citizen.name,
        tracking_id=complaint.tracking_id,
        title=complaint.title,
        address=complaint.location.address,
        resolution_note=note,
        worker_name=resolved_by
    )

    complaint.citizen_notification = CitizenNotification(
        recipient=notif_data["recipient"],
        channel=notif_data["channel"],
        message=notif_data["message"],
        sent_at=now_str,
        llm_powered=notif_data.get("llm_powered", False)
    )

    complaint.timeline.append(
        TimelineEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            timestamp=now_str,
            actor=ActorRole.WORKER,
            actor_name=resolved_by,
            action="RESOLVED",
            message=(
                f"Complaint resolved at stage '{complaint.resolved_at_stage or 'WORKER_ASSIGNED'}' by {resolved_by}. "
                f"Resolution note: '{note}'. LangGraph Coordinator halted escalation ladder. Citizen notified: \"{notif_data['message']}\""
            ),
            badge_type="success"
        )
    )
    return state


# --- LangGraph Conditional Router ---

def route_civic_action(state: CivicWorkflowState) -> str:
    action = state.get("action_type")
    if action == "INTAKE":
        return "node_intake_classifier"
    elif action == "RESOLVE":
        return "node_resolution_handler"
    elif action == "ESCALATE_TICK":
        c = state["complaint"]
        if c.status == ComplaintStatus.RESOLVED:
            return END
        # If in worker warning phase (WORKER_ASSIGNED through WARNING_4)
        if c.status in [
            ComplaintStatus.WORKER_ASSIGNED,
            ComplaintStatus.WARNING_1,
            ComplaintStatus.WARNING_2,
            ComplaintStatus.WARNING_3,
            ComplaintStatus.WARNING_4,
        ]:
            return "node_sla_governor"
        else:
            return "node_authority_escalator"
    return END


# --- Compile the LangGraph ---

builder = StateGraph(CivicWorkflowState)

builder.add_node("node_intake_classifier", node_intake_classifier)
builder.add_node("node_worker_dispatcher", node_worker_dispatcher)
builder.add_node("node_sla_governor", node_sla_governor)
builder.add_node("node_authority_escalator", node_authority_escalator)
builder.add_node("node_resolution_handler", node_resolution_handler)
builder.add_node("node_citizen_notifier", node_citizen_notifier)

builder.add_conditional_edges(
    START,
    route_civic_action,
    {
        "node_intake_classifier": "node_intake_classifier",
        "node_sla_governor": "node_sla_governor",
        "node_authority_escalator": "node_authority_escalator",
        "node_resolution_handler": "node_resolution_handler",
        END: END
    }
)

builder.add_edge("node_intake_classifier", "node_worker_dispatcher")
builder.add_edge("node_worker_dispatcher", END)

builder.add_edge("node_sla_governor", END)
builder.add_edge("node_authority_escalator", END)

builder.add_edge("node_resolution_handler", "node_citizen_notifier")
builder.add_edge("node_citizen_notifier", END)

civic_graph = builder.compile()
