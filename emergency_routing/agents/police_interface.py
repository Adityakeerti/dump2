"""Police Agent Contract and Mock Adapter for Teammate Integration."""

from typing import Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel
from agents.state import PoliceIncidentReport


class PoliceAcknowledgment(BaseModel):
    case_number: str
    status: str
    assigned_patrol_units: List[str]
    estimated_arrival_minutes: float
    message: str
    timestamp: datetime


class PoliceAgentInterface:
    """Interface contract between Emergency Agent and teammate's Police Agent."""

    def dispatch_police(self, report: PoliceIncidentReport) -> PoliceAcknowledgment:
        raise NotImplementedError("Teammate's Police Agent will implement this method.")


class MockPoliceAgent(PoliceAgentInterface):
    """Reference implementation / mock for testing while teammate builds the Police Agent."""

    def __init__(self):
        self.dispatched_cases: Dict[str, PoliceIncidentReport] = {}
        self._case_counter = 5001

    def dispatch_police(self, report: PoliceIncidentReport) -> PoliceAcknowledgment:
        case_id = f"PCR-2026-{self._case_counter}"
        self._case_counter += 1
        self.dispatched_cases[case_id] = report

        units = ["PCR-ALPHA-4", "PCR-DELTA-9"]
        ack = PoliceAcknowledgment(
            case_number=case_id,
            status="UNITS_EN_ROUTE",
            assigned_patrol_units=units,
            estimated_arrival_minutes=4.5,
            message=(
                f"Police dispatch confirmed for {report.incident_type} at {report.address}. "
                f"Sustained altercation detected for {report.dispute_duration_seconds:.1f}s. "
                f"Units {', '.join(units)} en route with Code 3 lights/sirens."
            ),
            timestamp=datetime.now(),
        )
        return ack
