"""Pre-configured Scenarios for Demonstrating and Verifying the Emergency Agent System."""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from agents.state import IncidentPayload
from routing.graph import RoadGraph
from routing.traffic_history import TrafficHistoryDB


def build_demo_city_network() -> Tuple[RoadGraph, TrafficHistoryDB]:
    """Builds a realistic test city network representing intersections and arterial corridors."""
    graph = RoadGraph()
    history = TrafficHistoryDB()

    # Add Nodes
    graph.add_node("node_hospital_north", "City General Hospital", 28.6139, 77.2090)
    graph.add_node("node_hospital_east", "Apex Metro Hospital", 28.6300, 77.2800)
    graph.add_node("node_hospital_south", "St. Jude Hospital", 28.5800, 77.2300)

    graph.add_node("node_central_junction", "Central Square Junction", 28.6100, 77.2200)
    graph.add_node("node_accident_blvd", "Grand Boulevard Intersection", 28.6050, 77.2250)
    graph.add_node("node_west_bypass", "West Outer Junction", 28.6200, 77.1950)
    graph.add_node("node_industrial_cross", "Industrial Sector Crossing", 28.6400, 77.2950)
    graph.add_node("node_market_square", "Old Market Plaza", 28.6150, 77.2400)

    # Add Edges (Roads)
    # Hospital North Connections
    graph.add_edge("seg_north_to_central", "node_hospital_north", "node_central_junction", distance_km=2.5, speed_limit_kmh=60)
    graph.add_edge("seg_main_blvd", "node_central_junction", "node_accident_blvd", distance_km=1.8, speed_limit_kmh=50)

    # Alternative Route around Central Junction (West Bypass)
    graph.add_edge("seg_north_to_bypass", "node_hospital_north", "node_west_bypass", distance_km=3.0, speed_limit_kmh=65)
    graph.add_edge("seg_bypass_to_blvd", "node_west_bypass", "node_accident_blvd", distance_km=4.2, speed_limit_kmh=70)

    # East Hospital Network (Expressway Bridge vs Ring Road Bypass)
    graph.add_edge("seg_expressway_bridge", "node_hospital_east", "node_industrial_cross", distance_km=3.0, speed_limit_kmh=70)
    graph.add_edge("seg_east_to_ring", "node_hospital_east", "node_central_junction", distance_km=4.0, speed_limit_kmh=60)
    graph.add_edge("seg_ring_road", "node_central_junction", "node_industrial_cross", distance_km=4.8, speed_limit_kmh=65)

    return graph, history


def get_scenario_accident_clearing_jam() -> Tuple[IncidentPayload, RoadGraph, TrafficHistoryDB]:
    """Scenario 1: Accident with a Jam that is predicted to clear BEFORE ambulance arrives.

    Expected Result: Ambulance PRESERVES fastest path (DO NOT REROUTE).
    """
    graph, history = build_demo_city_network()
    # Inject a moderate jam on seg_main_blvd that started 5.5 mins ago and clears in 1.5 mins
    # Ambulance takes 2.5 mins to reach this segment (t_reach = 2.5m >= t_clear = 1.5m)
    graph.set_jam(
        edge_id="seg_main_blvd",
        severity=0.5,
        delay_minutes=6.0,
        started_minutes_ago=5.5,
    )

    incident = IncidentPayload(
        incident_id="INC-ACC-DEMO-01",
        incident_type="ACCIDENT",
        camera_id="CAM-TRAFFIC-BLVD",
        location_node_id="node_accident_blvd",
        latitude=28.6050,
        longitude=77.2250,
        address="Grand Boulevard & 4th Avenue",
        confidence=0.92,
        severity=0.85,
        timestamp=datetime.now(),
    )
    return incident, graph, history


def get_scenario_accident_persistent_jam() -> Tuple[IncidentPayload, RoadGraph, TrafficHistoryDB]:
    """Scenario 2: Accident with a severe persistent Jam that will NOT clear in time.

    Expected Result: Ambulance Agent DYNAMICALLY REROUTES to avoid the bridge.
    """
    graph, history = build_demo_city_network()
    # Inject severe jam on the expressway bridge that takes 35 mins to clear
    graph.set_jam(
        edge_id="seg_expressway_bridge",
        severity=0.95,
        delay_minutes=25.0,
        started_minutes_ago=2.0,
    )

    incident = IncidentPayload(
        incident_id="INC-ACC-DEMO-02",
        incident_type="ACCIDENT",
        camera_id="CAM-EXPRESSWAY-09",
        location_node_id="node_industrial_cross",
        latitude=28.6400,
        longitude=77.2950,
        address="Industrial Sector Road Crossing",
        confidence=0.89,
        severity=0.90,
        timestamp=datetime.now(),
    )
    return incident, graph, history


def get_scenario_feud_timeline() -> List[IncidentPayload]:
    """Scenario 3: Feud progression over time:

    - T = 0s: Feud starts (Duration 0s < 60s) -> Police NOT alerted
    - T = 30s: Feud ongoing (Duration 30s < 60s) -> Police NOT alerted
    - T = 65s: Feud persistent (Duration 65s >= 60s) -> POLICE ALERTED!
    - T = 90s: Feud still going -> Duplicate alert suppressed.
    """
    base_time = datetime.now()
    frames = [
        IncidentPayload(
            incident_id="INC-FEUD-T0",
            incident_type="FEUD",
            camera_id="CAM-MARKET-PLAZA",
            location_node_id="node_market_square",
            latitude=28.6150,
            longitude=77.2400,
            address="Old Market Plaza",
            confidence=0.85,
            severity=0.70,
            timestamp=base_time,
        ),
        IncidentPayload(
            incident_id="INC-FEUD-T30",
            incident_type="FEUD",
            camera_id="CAM-MARKET-PLAZA",
            location_node_id="node_market_square",
            latitude=28.6150,
            longitude=77.2400,
            address="Old Market Plaza",
            confidence=0.88,
            severity=0.75,
            timestamp=base_time + timedelta(seconds=30),
        ),
        IncidentPayload(
            incident_id="INC-FEUD-T65",
            incident_type="FEUD",
            camera_id="CAM-MARKET-PLAZA",
            location_node_id="node_market_square",
            latitude=28.6150,
            longitude=77.2400,
            address="Old Market Plaza",
            confidence=0.93,
            severity=0.82,
            timestamp=base_time + timedelta(seconds=65),
        ),
        IncidentPayload(
            incident_id="INC-FEUD-T90",
            incident_type="FEUD",
            camera_id="CAM-MARKET-PLAZA",
            location_node_id="node_market_square",
            latitude=28.6150,
            longitude=77.2400,
            address="Old Market Plaza",
            confidence=0.90,
            severity=0.80,
            timestamp=base_time + timedelta(seconds=90),
        ),
    ]
    return frames
