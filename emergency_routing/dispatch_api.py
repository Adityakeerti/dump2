"""Agent-facing dispatch API (consumed by agent_service's EmergencySpecialist).

Endpoints
---------
POST /api/dispatch                 Dispatch nearest ambulance / police squad and plan a green-wave route.
GET  /api/missions                 List missions (newest first).
GET  /api/missions/{mission_id}    Track one mission.
POST /api/missions/{mission_id}/complete   Release the unit back to AVAILABLE.
POST /api/corridor                 Plan a green-wave corridor without dispatching a unit.
POST /api/signals/override         Pre-empt signals along a corridor (simulated controller).
GET  /api/hospitals/nearest        Nearest hospital with ER capacity.
GET  /api/incidents                Recent CCTV / vision-detected incidents.
POST /api/incidents                Record a detected incident (used by the vision pipeline / tests).

The road network and hospital registry are the module's synthetic demo network, so every
response carries ``"network": "demo-synthetic"``. Nothing here talks to a real 108 / SCATS system.
"""

from __future__ import annotations

import math
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from routing.graph import RoadGraph
from routing.predictive_router import PredictiveRouter
from services.hospital_service import HospitalService

NETWORK_LABEL = "demo-synthetic"
MAX_INCIDENTS = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class DispatchRequest(BaseModel):
    incident_type: Literal["medical", "accident", "fire", "police", "feud", "other"] = "accident"
    severity: Literal["P0", "P1", "P2"] = "P0"
    location_label: str = Field(default="", max_length=300)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    description: str = Field(default="", max_length=2000)
    reported_by: str = Field(default="citizen", max_length=100)


class CorridorRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    vehicle_type: str = Field(default="ambulance", max_length=50)


class SignalOverrideRequest(BaseModel):
    corridor_id: Optional[str] = Field(default=None, max_length=100)
    signals: list[str] = Field(default_factory=list, max_length=50)
    duration_seconds: int = Field(default=180, ge=30, le=1800)


class IncidentRecord(BaseModel):
    camera_id: str = Field(default="CAM-UNKNOWN", max_length=100)
    incident_type: str = Field(default="accident", max_length=50)
    confidence: float = Field(default=0.0, ge=0, le=1)
    location_label: str = Field(default="", max_length=300)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    summary: str = Field(default="", max_length=2000)


def build_dispatch_router(
    hospital_service: HospitalService, router: PredictiveRouter, graph: RoadGraph
) -> APIRouter:
    api = APIRouter(tags=["dispatch"])
    lock = threading.Lock()
    missions: dict[str, dict[str, Any]] = {}
    incidents: list[dict[str, Any]] = []

    def resolve_node(label: str, lat: Optional[float], lon: Optional[float]) -> str:
        """Map a free-text label or coordinates onto a node of the demo network."""
        label_l = (label or "").strip().lower()
        if label_l:
            for node in graph.nodes.values():
                if label_l == node.id.lower() or label_l in node.name.lower() or node.name.lower() in label_l:
                    return node.id
        if lat is not None and lon is not None:
            return min(
                graph.nodes.values(), key=lambda n: _haversine_km(lat, lon, n.latitude, n.longitude)
            ).id
        # Unknown label and no coordinates: deterministic pick so the same text maps to the same node.
        candidates = sorted(n.id for n in graph.nodes.values() if not n.id.startswith("node_hospital"))
        return candidates[sum(map(ord, label_l)) % len(candidates)] if candidates else next(iter(graph.nodes))

    def plan(origin_node: str, dest_node: str) -> dict[str, Any]:
        decision = router.plan_emergency_route(origin_node, dest_node)
        if not decision:
            raise HTTPException(409, f"No route between {origin_node} and {dest_node}")
        path = decision.selected_path
        names = [graph.nodes[n].name if n in graph.nodes else n for n in path.nodes]
        eta = path.effective_time_minutes or path.nominal_time_minutes
        nominal = decision.nominal_fastest_path.nominal_time_minutes
        return {
            "route_nodes": path.nodes,
            "route_names": names,
            "route_edges": path.edges,
            "distance_km": round(path.total_distance_km, 2),
            "eta_minutes": round(eta, 1) if math.isfinite(eta) else None,
            "nominal_minutes": round(nominal, 1) if math.isfinite(nominal) else None,
            "rerouted": decision.rerouted,
            "weather_rerouted": decision.weather_rerouted,
            "reason": decision.reason,
            # Junctions between origin and destination get green-wave pre-emption.
            "signals_preempted": names[1:-1] or names,
        }

    @api.post("/api/dispatch")
    def dispatch(req: DispatchRequest) -> dict[str, Any]:
        mission_id = f"EMG-{uuid.uuid4().hex[:6].upper()}"
        scene_node = resolve_node(req.location_label, req.latitude, req.longitude)
        scene = graph.nodes[scene_node]
        unit_kind = "police_squad" if req.incident_type in {"police", "feud"} else (
            "fire_tender" if req.incident_type == "fire" else "ambulance"
        )
        with lock:
            hospital = hospital_service.find_nearest_hospital(scene.latitude, scene.longitude)
            unit = None
            if hospital and unit_kind == "ambulance":
                unit = hospital_service.dispatch_ambulance(hospital.id, mission_id)
            route = plan(hospital.road_node_id, scene_node) if hospital else None
            status = "DISPATCHED" if (unit or unit_kind != "ambulance") and hospital else "QUEUED"
            mission = {
                "mission_id": mission_id,
                "status": status,
                "severity": req.severity,
                "incident_type": req.incident_type,
                "unit_type": unit_kind,
                "unit_id": unit.id if unit else (f"{unit_kind.upper()}-{mission_id[-3:]}" if status == "DISPATCHED" else None),
                "scene": {"node": scene_node, "name": scene.name, "label": req.location_label,
                          "latitude": req.latitude, "longitude": req.longitude},
                "hospital": {
                    "id": hospital.id, "name": hospital.name, "trauma_level": hospital.trauma_level,
                    "er_beds_available": hospital.er_beds_available,
                } if hospital else None,
                "route": route,
                "green_wave_active": bool(route),
                "description": req.description,
                "reported_by": req.reported_by,
                "created_at": _now(),
                "network": NETWORK_LABEL,
            }
            missions[mission_id] = mission
        return mission

    @api.get("/api/missions")
    def list_missions() -> dict[str, Any]:
        with lock:
            items = sorted(missions.values(), key=lambda m: m["created_at"], reverse=True)
        return {"missions": items, "network": NETWORK_LABEL}

    @api.get("/api/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        mission = missions.get(mission_id)
        if not mission:
            raise HTTPException(404, "Mission not found")
        return mission

    @api.post("/api/missions/{mission_id}/complete")
    def complete_mission(mission_id: str) -> dict[str, Any]:
        with lock:
            mission = missions.get(mission_id)
            if not mission:
                raise HTTPException(404, "Mission not found")
            for hosp in hospital_service.hospitals.values():
                for amb in hosp.ambulances:
                    if amb.current_assigned_mission == mission_id:
                        amb.status = "AVAILABLE"
                        amb.current_assigned_mission = None
            mission["status"] = "COMPLETED"
            mission["completed_at"] = _now()
        return mission

    @api.post("/api/corridor")
    def corridor(req: CorridorRequest) -> dict[str, Any]:
        origin = resolve_node(req.origin, None, None)
        dest = resolve_node(req.destination, None, None)
        if origin == dest:
            dest = next((n for n in graph.nodes if n.startswith("node_hospital") and n != origin), dest)
        route = plan(origin, dest)
        return {
            "corridor_id": f"CORR-{uuid.uuid4().hex[:5].upper()}",
            "origin": req.origin,
            "destination": req.destination,
            "vehicle_type": req.vehicle_type,
            "status": "ACTIVE_CLEAR",
            "green_wave_active": True,
            "estimated_travel_time_minutes": route["eta_minutes"],
            "normal_travel_time_minutes": route["nominal_minutes"],
            "signals_cleared": route["signals_preempted"],
            "route": route,
            "network": NETWORK_LABEL,
        }

    @api.post("/api/signals/override")
    def override_signals(req: SignalOverrideRequest) -> dict[str, Any]:
        signals = req.signals
        if not signals and req.corridor_id:
            mission = next((m for m in missions.values() if m.get("route") and req.corridor_id in (m["mission_id"],)), None)
            signals = mission["route"]["signals_preempted"] if mission else []
        if not signals:
            raise HTTPException(422, "Provide signals or a known mission id as corridor_id")
        return {
            "override_id": f"SIG-{uuid.uuid4().hex[:6].upper()}",
            "status": "PREEMPTED",
            "signals": [{"junction": s, "phase": "GREEN", "hold_seconds": req.duration_seconds} for s in signals],
            "controller": "simulated",
            "issued_at": _now(),
            "network": NETWORK_LABEL,
        }

    @api.get("/api/hospitals/nearest")
    def nearest_hospital(lat: Optional[float] = None, lon: Optional[float] = None, location: str = "") -> dict[str, Any]:
        node = graph.nodes[resolve_node(location, lat, lon)]
        hospital = hospital_service.find_nearest_hospital(node.latitude, node.longitude)
        if not hospital:
            raise HTTPException(404, "No hospital with free ER capacity and an available ambulance")
        return {
            "hospital": {
                "id": hospital.id, "name": hospital.name, "trauma_level": hospital.trauma_level,
                "er_beds_available": hospital.er_beds_available,
                "available_ambulances": sum(a.status == "AVAILABLE" for a in hospital.ambulances),
                "distance_km": round(_haversine_km(node.latitude, node.longitude, hospital.latitude, hospital.longitude), 2),
            },
            "from_node": node.name,
            "network": NETWORK_LABEL,
        }

    @api.get("/api/incidents")
    def list_incidents(limit: int = 20) -> dict[str, Any]:
        with lock:
            items = list(reversed(incidents))[: max(1, min(limit, MAX_INCIDENTS))]
        return {"incidents": items, "count": len(items), "network": NETWORK_LABEL}

    @api.post("/api/incidents")
    def record_incident(rec: IncidentRecord) -> dict[str, Any]:
        item = {"incident_id": f"INC-{uuid.uuid4().hex[:6].upper()}", "detected_at": _now(), **rec.model_dump()}
        with lock:
            incidents.append(item)
            del incidents[:-MAX_INCIDENTS]
        return item

    api.record_incident = record_incident  # type: ignore[attr-defined]  # used by server.py's vision endpoints
    return api
