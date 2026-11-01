from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import datetime


class ComplaintStatus(str, Enum):
    FILED = "FILED"
    WORKER_ASSIGNED = "WORKER_ASSIGNED"
    WARNING_1 = "WARNING_1"
    WARNING_2 = "WARNING_2"
    WARNING_3 = "WARNING_3"
    WARNING_4 = "WARNING_4"
    WARNING_5 = "WARNING_5"
    ESCALATED_WARD_OFFICER = "ESCALATED_WARD_OFFICER"
    ESCALATED_MUNICIPAL_COMMISSIONER = "ESCALATED_MUNICIPAL_COMMISSIONER"
    ESCALATED_CM_PORTAL = "ESCALATED_CM_PORTAL"
    RESOLVED = "RESOLVED"


class ActorRole(str, Enum):
    CITIZEN = "CITIZEN"
    MUNICIPAL_AGENT = "MUNICIPAL_AGENT"
    MUNICIPAL_COORDINATOR_AGENT = "MUNICIPAL_COORDINATOR_AGENT"
    WORKER = "WORKER"
    WARD_OFFICER = "WARD_OFFICER"
    MUNICIPAL_COMMISSIONER = "MUNICIPAL_COMMISSIONER"
    CM_PORTAL = "CM_PORTAL"


class TimelineEvent(BaseModel):
    id: str
    timestamp: str
    actor: ActorRole
    actor_name: str
    action: str
    message: str
    badge_type: str = "info"  # info, warning, danger, success, escalation


class LocationModel(BaseModel):
    lat: float = 30.3165
    lng: float = 78.0322
    address: str = "Rajpur Road, Near Clock Tower, Dehradun"
    ward: str = "Ward 14"


class CitizenModel(BaseModel):
    user_id: str
    name: str
    email: str
    phone: str
    ward: str


class WorkerModel(BaseModel):
    id: str
    name: str
    team: str
    department: str
    phone: str
    rating: float = 4.8


class AuthorityModel(BaseModel):
    id: str
    name: str
    designation: str
    department: str
    level: int
    tier_name: str
    email: str
    phone: str
    jurisdiction: str
    escalation_trigger: str
    avatar: str


class CitizenNotification(BaseModel):
    recipient: str
    channel: str
    message: str
    sent_at: str
    llm_powered: bool = False


class ComplaintCreateRequest(BaseModel):
    title: str
    category: Optional[str] = "Auto-Detect"
    description: str
    address: Optional[str] = "Rajpur Road, Ward 14, Dehradun"
    lat: Optional[float] = 30.3165
    lng: Optional[float] = 78.0322
    photo_url: Optional[str] = None


class Complaint(BaseModel):
    tracking_id: str
    title: str
    category: str = "Auto-Detecting..."
    description: str
    photo_url: str
    location: LocationModel
    citizen: CitizenModel
    status: ComplaintStatus = ComplaintStatus.FILED
    priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    assigned_worker: Optional[WorkerModel] = None
    coordinator_agent: str = "Municipal Coordinator AI Agent"
    warnings_count: int = 0
    current_authority: Optional[AuthorityModel] = None
    sla_seconds: int = 30
    sla_remaining_seconds: int = 30
    timeline: List[TimelineEvent] = Field(default_factory=list)
    created_at: str
    updated_at: str
    resolution_note: Optional[str] = None
    resolution_time: Optional[str] = None
    resolved_at_stage: Optional[str] = None
    future_springboot_synced: bool = False
    llm_reasoning: Optional[str] = None
    citizen_notification: Optional[CitizenNotification] = None
    escalation_memo: Optional[str] = None


class ResolveRequest(BaseModel):
    resolution_note: str = "Repair completed and site inspected."
    proof_photo_url: Optional[str] = None
