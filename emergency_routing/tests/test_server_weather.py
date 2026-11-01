"""Tests for Weather and Routing endpoints on FastAPI server."""

import pytest
from fastapi.testclient import TestClient
from server import app, graph


@pytest.fixture
def client():
    return TestClient(app)


def test_get_current_weather(client):
    response = client.get("/api/weather/current?city=Dehradun")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Dehradun"
    assert "temperature_c" in data
    assert "risk_level" in data
    assert "water_depth_cm_estimate" in data


def test_apply_weather_condition(client):
    # Find any edge in graph
    first_edge_id = list(graph.edges_by_id.keys())[0]

    payload = {
        "segment_id": first_edge_id,
        "rainfall_mm": 35.0,
        "flood_depth_cm": 28.0,
        "is_blocked": True,
        "block_reason": "High Water Alert",
    }
    response = client.post("/api/weather/apply-conditions", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "UPDATED"
    assert res_data["is_blocked"] is True

    # Reset
    graph.clear_weather_conditions()


def test_network_graph_endpoint(client):
    response = client.get("/api/network/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0
