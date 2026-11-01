"""Unit tests for Weather and Flood-Aware Emergency Routing."""

import pytest
from routing.graph import RoadGraph
from routing.traffic_history import TrafficHistoryDB, SegmentHistoricalProfile
from routing.predictive_router import PredictiveRouter
from services.weather_service import WeatherService, WeatherCondition


@pytest.fixture
def weather_network():
    graph = RoadGraph()
    history = TrafficHistoryDB()

    # Network topology:
    # A -> B -> D (Primary shortest: 2.0 km + 2.0 km = 4.0 km @ 60 km/h = 4.0 mins)
    # A -> C -> D (Alternative longer bypass: 3.0 km + 3.0 km = 6.0 km @ 60 km/h = 6.0 mins)
    graph.add_node("A", "Clock Tower", 30.3255, 78.0436)
    graph.add_node("B", "Rajpur Road Underpass", 30.3300, 78.0480)
    graph.add_node("C", "EC Road Bypass", 30.3200, 78.0500)
    graph.add_node("D", "Doon Hospital", 30.3180, 78.0400)

    graph.add_edge("edge_AB", "A", "B", distance_km=2.0, speed_limit_kmh=60)
    graph.add_edge("edge_BD", "B", "D", distance_km=2.0, speed_limit_kmh=60)

    graph.add_edge("edge_AC", "A", "C", distance_km=3.0, speed_limit_kmh=60)
    graph.add_edge("edge_CD", "C", "D", distance_km=3.0, speed_limit_kmh=60)

    return graph, history


def test_flood_depth_impassable_triggers_reroute(weather_network):
    """When underpass flood depth >= 25cm, edge becomes impassable and router reroutes via EC Road."""
    graph, history = weather_network

    # Simulate cloudburst in Dehradun: Rajpur Road underpass submerged under 35cm water
    graph.set_weather_condition(
        "edge_BD",
        rainfall_mm=45.0,
        flood_depth_cm=35.0,
        is_blocked=False,
        block_reason="Underpass submerged",
    )

    router = PredictiveRouter(graph=graph, history_db=history)
    decision = router.plan_emergency_route("A", "D")

    assert decision is not None
    assert decision.weather_rerouted is True
    assert decision.rerouted is True
    assert decision.selected_path.nodes == ["A", "C", "D"]
    assert "edge_BD" not in decision.selected_path.edges
    assert any(w.segment_id == "edge_BD" and w.is_impassable for w in decision.weather_evaluations)
    assert "flood/blockage" in decision.reason.lower()


def test_moderate_flood_slowdown_reroutes_when_bypass_faster(weather_network):
    """Moderate flood (15cm) degrades speed by 60%, making 6.0-min bypass faster than 7.0-min waterlogged route."""
    graph, history = weather_network

    # 15cm flood on edge_BD (2km at 24 km/h = 5.0 mins). edge_AB = 2.0 mins -> Total = 7.0 mins.
    # Bypass via C = 3.0 + 3.0 = 6.0 mins.
    graph.set_weather_condition(
        "edge_BD",
        rainfall_mm=20.0,
        flood_depth_cm=15.0,
    )

    router = PredictiveRouter(graph=graph, history_db=history)
    decision = router.plan_emergency_route("A", "D")

    assert decision is not None
    # Router picks fastest effective path (A -> C -> D @ 6.0 min vs A -> B -> D @ 7.0 min)
    assert decision.selected_path.nodes == ["A", "C", "D"]
    assert decision.selected_path.effective_time_minutes <= 6.0


def test_dry_weather_preserves_fastest_path(weather_network):
    """Under normal dry weather, fastest path A -> B -> D is selected."""
    graph, history = weather_network

    router = PredictiveRouter(graph=graph, history_db=history)
    decision = router.plan_emergency_route("A", "D")

    assert decision is not None
    assert not decision.rerouted
    assert not decision.weather_rerouted
    assert decision.selected_path.nodes == ["A", "B", "D"]
    assert decision.selected_path.nominal_time_minutes == 4.0


def test_weather_service_dehradun():
    """Verify Open-Meteo weather service returns valid weather payload for Dehradun."""
    weather = WeatherService.get_weather_for_location(30.3165, 78.0322, "Dehradun")
    assert weather is not None
    assert weather.city == "Dehradun"
    assert weather.temperature_c is not None
    assert weather.condition_text is not None
    assert weather.water_depth_cm_estimate >= 0.0
