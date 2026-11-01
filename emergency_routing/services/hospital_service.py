"""Hospital Registry and Ambulance Fleet Management Service."""

from typing import Dict, List, Optional, Tuple
import math
from pydantic import BaseModel


class AmbulanceUnit(BaseModel):
    id: str
    hospital_id: str
    status: str = "AVAILABLE"  # AVAILABLE, DISPATCHED, IN_TRANSIT
    current_assigned_mission: Optional[str] = None


class Hospital(BaseModel):
    id: str
    name: str
    road_node_id: str
    latitude: float
    longitude: float
    er_beds_available: int
    trauma_level: int  # 1 (Highest), 2, 3
    ambulances: List[AmbulanceUnit] = []


class HospitalService:
    """Registry of city emergency hospitals and ambulance dispatch."""

    def __init__(self):
        self.hospitals: Dict[str, Hospital] = {}
        self._seed_default_hospitals()

    def _seed_default_hospitals(self):
        # Seed realistic hospitals attached to road network nodes
        h1 = Hospital(
            id="hosp_city_general",
            name="City General Trauma Center",
            road_node_id="node_hospital_north",
            latitude=28.6139,
            longitude=77.2090,
            er_beds_available=14,
            trauma_level=1,
            ambulances=[
                AmbulanceUnit(id="AMB-101", hospital_id="hosp_city_general"),
                AmbulanceUnit(id="AMB-102", hospital_id="hosp_city_general"),
            ],
        )
        h2 = Hospital(
            id="hosp_st_jude",
            name="St. Jude Emergency Hospital",
            road_node_id="node_hospital_south",
            latitude=28.5800,
            longitude=77.2300,
            er_beds_available=6,
            trauma_level=2,
            ambulances=[
                AmbulanceUnit(id="AMB-201", hospital_id="hosp_st_jude"),
                AmbulanceUnit(id="AMB-202", hospital_id="hosp_st_jude"),
            ],
        )
        h3 = Hospital(
            id="hosp_apex_med",
            name="Apex Metro Emergency Center",
            road_node_id="node_hospital_east",
            latitude=28.6300,
            longitude=77.2800,
            er_beds_available=8,
            trauma_level=1,
            ambulances=[
                AmbulanceUnit(id="AMB-301", hospital_id="hosp_apex_med"),
            ],
        )
        self.hospitals[h1.id] = h1
        self.hospitals[h2.id] = h2
        self.hospitals[h3.id] = h3

    def find_nearest_hospital(
        self, incident_lat: float, incident_lon: float, require_er_bed: bool = True
    ) -> Optional[Hospital]:
        """Finds the geographically closest hospital with available capacity using Haversine distance."""
        best_hospital: Optional[Hospital] = None
        min_dist = float("inf")

        for hosp in self.hospitals.values():
            if require_er_bed and hosp.er_beds_available <= 0:
                continue

            # Check if has at least one available ambulance
            has_amb = any(amb.status == "AVAILABLE" for amb in hosp.ambulances)
            if not has_amb:
                continue

            # Haversine distance in km
            d_lat = math.radians(hosp.latitude - incident_lat)
            d_lon = math.radians(hosp.longitude - incident_lon)
            a = (
                math.sin(d_lat / 2) ** 2
                + math.cos(math.radians(incident_lat))
                * math.cos(math.radians(hosp.latitude))
                * math.sin(d_lon / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            dist_km = 6371.0 * c

            if dist_km < min_dist:
                min_dist = dist_km
                best_hospital = hosp

        return best_hospital

    def dispatch_ambulance(self, hospital_id: str, mission_id: str) -> Optional[AmbulanceUnit]:
        """Dispatches an available ambulance from the specified hospital."""
        hospital = self.hospitals.get(hospital_id)
        if not hospital:
            return None

        for amb in hospital.ambulances:
            if amb.status == "AVAILABLE":
                amb.status = "DISPATCHED"
                amb.current_assigned_mission = mission_id
                return amb
        return None
