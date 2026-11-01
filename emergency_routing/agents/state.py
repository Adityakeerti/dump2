"""State models and schemas for LangGraph Emergency Agent."""

from typing import Annotated, Dict, List, Literal, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel


class IncidentPayload(BaseModel):
    incident_id: str
    incident_type: Literal["ACCIDENT", "FEUD", "NONE"]
    camera_id: str
    location_node_id: str
    latitude: float
    longitude: float
    address: str
    confidence: float
    severity: float  # 0.0 to 1.0
    timestamp: datetime
    frame_image_ref: Optional[str] = None   # base64 or file path to captured frame


class AmbulanceMission(BaseModel):
    mission_id: str
    ambulance_id: str
    hospital_id: str
    hospital_name: str
    hospital_node_id: str
    target_node_id: str
    route_nodes: List[str]
    route_edges: List[str]
    total_distance_km: float
    estimated_arrival_minutes: float
    rerouted: bool
    routing_reason: str
    dispatched_at: datetime


class PoliceIncidentReport(BaseModel):
    report_id: str
    incident_type: Literal["PUBLIC_FEUD", "RIOT", "WEAPONS_VIOLENCE"]
    dispute_duration_seconds: float
    average_intensity: float
    camera_id: str
    location_node_id: str
    coordinates: Tuple[float, float]
    address: str
    dispatched_at: datetime
    status: str = "DISPATCHED"


class FeudTrackingState(BaseModel):
    camera_id: str
    first_detected_at: Optional[datetime] = None
    last_detected_at: Optional[datetime] = None
    elapsed_duration_seconds: float = 0.0
    intensity_samples: List[float] = []
    police_alerted: bool = False
    is_active: bool = False


class LLMAnalysis(BaseModel):
    """Stores both vision and classifier LLM outputs for full pipeline visibility."""
    # Vision analysis (if image was provided)
    vision_detected_type: Optional[str] = None
    vision_description: Optional[str] = None
    vision_confidence: Optional[float] = None
    vision_severity: Optional[float] = None
    vision_injuries_visible: Optional[bool] = None
    vision_weapons_visible: Optional[bool] = None
    vision_model: Optional[str] = None
    vision_provider: Optional[str] = None
    vision_method: Optional[str] = None
    # LLM Classifier decision
    llm_decision: Optional[str] = None         # DISPATCH_AMBULANCE | DISPATCH_POLICE | MONITOR | IGNORE
    llm_confidence: Optional[float] = None
    llm_rationale: Optional[str] = None
    llm_model: Optional[str] = None
    llm_severity_override: Optional[float] = None


class EmergencyState(BaseModel):
    """LangGraph shared workflow state."""
    current_incident: Optional[IncidentPayload] = None
    feud_tracking: Dict[str, FeudTrackingState] = {}
    ambulance_mission: Optional[AmbulanceMission] = None
    police_report: Optional[PoliceIncidentReport] = None
    pending_police_dispatch: bool = False
    workflow_step: str = "START"
    decision_summary: str = ""
    audit_log: List[str] = []
    # LLM Analysis data (new - fully visible in UI)
    llm_analysis: Optional[LLMAnalysis] = None
