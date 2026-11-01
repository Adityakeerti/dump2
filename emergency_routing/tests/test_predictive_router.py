"""Unit tests for the Smart Predictive Routing Engine with Jam Clearance Prediction."""

import pytest
from routing.graph import RoadGraph
from routing.traffic_history import TrafficHistoryDB, SegmentHistoricalProfile
from routing.predictive_router import PredictiveRouter


@pytest.fixture
def network_setup():
    graph = RoadGraph()
    history = TrafficHistoryDB()

    # Create diamond network:
    # A -> B -> D (Primary shortest: total 4.0 km)
    # A -> C -> D (Alternative longer: total 6.0 km)
    graph.add_node("A", "Origin", 0.0, 0.0)
    graph.add_node("B", "Mid Primary", 0.0, 1.0)
    graph.add_node("C", "Mid Alternative", 1.0, 0.0)
    graph.add_node("D", "Destination", 1.0, 1.0)

    # Primary route edges (Speed limit: 60 km/h -> 1 min per km)
    graph.add_edge("edge_AB", "A", "B", distance_km=2.0, speed_limit_kmh=60)
    graph.add_edge("edge_BD", "B", "D", distance_km=2.0, speed_limit_kmh=60)

    # Alternative route edges
    graph.add_edge("edge_AC", "A", "C", distance_km=3.0, speed_limit_kmh=60)
    graph.add_edge("edge_CD", "C", "D", distance_km=3.0, speed_limit_kmh=60)

    # Custom historical profile for edge_BD
    history.register_profile(
        SegmentHistoricalProfile(
            segment_id="edge_BD",
            average_jam_duration_minutes=5.0,
            clearance_rate_factor=1.0,
        )
    )

    return graph, history


def test_clear_network_selects_fastest_path(network_setup):
    graph, history = network_setup
    router = PredictiveRouter(graph=graph, history_db=history)

    decision = router.plan_emergency_route("A", "D")
    assert decision is not None
    assert decision.selected_path.nodes == ["A", "B", "D"]
    assert not decision.rerouted
    assert decision.selected_path.nominal_time_minutes == 4.0


def test_jam_clears_before_arrival_preserves_path(network_setup):
    """Ambulance takes 2.0 mins to reach edge_BD.

    Jam started 4.5 mins ago and base duration is 5.0 mins -> Remaining clearance < 1.0 min.
    Since t_reach (2.0 mins) >= t_clear (0.5-1.0 mins), the ambulance SHOULD NOT REROUTE.
    """
    graph, history = network_setup
    # Inject jam on edge_BD that started 4.5 mins ago
    graph.set_jam("edge_BD", severity=0.2, delay_minutes=5.0, started_minutes_ago=4.5)

    router = PredictiveRouter(graph=graph, history_db=history)
    decision = router.plan_emergency_route("A", "D")

    assert decision is not None
    assert decision.selected_path.nodes == ["A", "B", "D"]
    assert not decision.rerouted
    assert "clear before ambulance arrives" in decision.reason.lower()


def test_persistent_jam_triggers_reroute(network_setup):
    """Ambulance takes 2.0 mins to reach edge_BD.

    Jam started 0.5 mins ago with severity 1.0 -> Remaining clearance > 8.0 mins.
    Primary route effective time = 4.0 + delay (~8 mins) = ~12 mins.
    Alternative route via C takes 6.0 mins.
    Therefore, the router MUST reroute via C!
    """
    graph, history = network_setup
    graph.set_jam("edge_BD", severity=1.0, delay_minutes=15.0, started_minutes_ago=0.5)

    router = PredictiveRouter(graph=graph, history_db=history)
    decision = router.plan_emergency_route("A", "D")

    assert decision is not None
    assert decision.rerouted
    assert decision.selected_path.nodes == ["A", "C", "D"]
    assert decision.selected_path.nominal_time_minutes == 6.0
    assert "Rerouting" in decision.reason
