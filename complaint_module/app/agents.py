from typing import List, Dict, Any, Optional
from .models import Complaint, AuthorityModel
from .graph import civic_graph


class MunicipalIntakeAgent:
    """Agent that drives citizen intake using LangGraph StateGraph pipeline."""

    def __init__(self, name: str = "Municipal Intake Agent (LangGraph)"):
        self.name = name

    def process_and_assign(
        self, complaint: Complaint, available_workers: List[Dict[str, Any]]
    ) -> Complaint:
        initial_state = {
            "complaint": complaint,
            "action_type": "INTAKE",
            "workers": available_workers
        }
        result = civic_graph.invoke(initial_state)
        return result["complaint"]


class MunicipalCoordinatorAgent:
    """Agent that drives escalation, SLA warnings, and resolution using LangGraph StateGraph."""

    def __init__(self, name: str = "Municipal Coordinator Agent (LangGraph)"):
        self.name = name

    def tick_escalation(
        self, complaint: Complaint, authorities: List[AuthorityModel]
    ) -> Complaint:
        initial_state = {
            "complaint": complaint,
            "action_type": "ESCALATE_TICK",
            "authorities": authorities
        }
        result = civic_graph.invoke(initial_state)
        return result["complaint"]

    def resolve(
        self,
        complaint: Complaint,
        note: str,
        proof_photo_url: Optional[str] = None,
        resolved_by: str = "Worker",
    ) -> Complaint:
        initial_state = {
            "complaint": complaint,
            "action_type": "RESOLVE",
            "resolution_note": note,
            "proof_photo_url": proof_photo_url,
            "resolved_by": resolved_by
        }
        result = civic_graph.invoke(initial_state)
        return result["complaint"]


intake_agent = MunicipalIntakeAgent()
coordinator_agent = MunicipalCoordinatorAgent()
