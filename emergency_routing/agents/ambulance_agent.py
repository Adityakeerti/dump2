"""Ambulance Agent: Nearest Hospital Discovery, Dispatch, and Smart Predictive Routing."""

from datetime import datetime
from typing import Optional, Tuple
from agents.state import AmbulanceMission, IncidentPayload
from services.hospital_service import HospitalService, Hospital, AmbulanceUnit
from routing.predictive_router import PredictiveRouter, PredictiveRouteDecision


class AmbulanceAgent:
    """Agent responsible for hospital allocation, vehicle dispatch, and predictive routing."""

    def __init__(
        self,
        hospital_service: Optional[HospitalService] = None,
        predictive_router: Optional[PredictiveRouter] = None,
    ):
        self.hospital_service = hospital_service or HospitalService()
        self.predictive_router = predictive_router

    def handle_accident(
        self, incident: IncidentPayload
    ) -> Tuple[Optional[AmbulanceMission], str]:
        """Dispatches the nearest available ambulance and computes predictive routing."""
        # Step 1: Connect to nearest hospital with available ER & ambulance
        hospital = self.hospital_service.find_nearest_hospital(
            incident_lat=incident.latitude, incident_lon=incident.longitude
        )

        if not hospital:
            return (
                None,
                f"ALERT: No hospital with available ER beds and ambulances found near {incident.address}!",
            )

        # Step 2: Initiate ambulance unit
        mission_id = f"MIS-AMB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        ambulance = self.hospital_service.dispatch_ambulance(hospital.id, mission_id)
        if not ambulance:
            return (
                None,
                f"Hospital {hospital.name} reached, but all ambulances are currently in transit.",
            )

        # Step 3: Compute smart predictive route with historical jam clearance analysis
        rerouted = False
        reason = "Fastest nominal route selected."
        route_nodes = [hospital.road_node_id, incident.location_node_id]
        route_edges = []
        total_dist_km = 4.2
        nominal_eta_min = 5.0

        if self.predictive_router:
            decision: Optional[PredictiveRouteDecision] = (
                self.predictive_router.plan_emergency_route(
                    origin_node=hospital.road_node_id,
                    destination_node=incident.location_node_id,
                )
            )

            if decision:
                route_nodes = decision.selected_path.nodes
                route_edges = decision.selected_path.edges
                total_dist_km = decision.selected_path.total_distance_km
                nominal_eta_min = decision.selected_path.nominal_time_minutes
                rerouted = decision.rerouted
                reason = decision.reason

        mission = AmbulanceMission(
            mission_id=mission_id,
            ambulance_id=ambulance.id,
            hospital_id=hospital.id,
            hospital_name=hospital.name,
            hospital_node_id=hospital.road_node_id,
            target_node_id=incident.location_node_id,
            route_nodes=route_nodes,
            route_edges=route_edges,
            total_distance_km=total_dist_km,
            estimated_arrival_minutes=nominal_eta_min,
            rerouted=rerouted,
            routing_reason=reason,
            dispatched_at=datetime.now(),
        )

        dispatch_summary = (
            f"Ambulance {ambulance.id} dispatched from {hospital.name} to {incident.address}. "
            f"Estimated transit: {nominal_eta_min:.1f} mins ({total_dist_km:.1f} km). "
            f"Route: {' -> '.join(route_nodes)}. "
            f"Decision: {reason}"
        )
        return mission, dispatch_summary
