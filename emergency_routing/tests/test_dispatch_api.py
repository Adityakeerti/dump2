"""Contract tests for the agent-facing dispatch API (dispatch_api.py)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dispatch_api import build_dispatch_router
from routing.predictive_router import PredictiveRouter
from services.hospital_service import HospitalService
from simulation.synthetic_scenarios import build_demo_city_network


def make_client() -> TestClient:
    graph, history = build_demo_city_network()
    app = FastAPI()
    app.include_router(
        build_dispatch_router(HospitalService(), PredictiveRouter(graph=graph, history_db=history), graph)
    )
    return TestClient(app)


def test_dispatch_assigns_ambulance_and_route():
    client = make_client()
    res = client.post("/api/dispatch", json={"incident_type": "accident", "location_label": "Grand Boulevard"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "DISPATCHED"
    assert body["unit_id"].startswith("AMB-")
    assert body["route"]["route_nodes"][-1] == "node_accident_blvd"
    assert body["green_wave_active"] is True
    assert body["network"] == "demo-synthetic"

    tracked = client.get(f"/api/missions/{body['mission_id']}").json()
    assert tracked["mission_id"] == body["mission_id"]


def test_fleet_exhaustion_queues_then_completion_releases():
    client = make_client()
    ids = [client.post("/api/dispatch", json={"latitude": 28.61, "longitude": 77.22}).json() for _ in range(6)]
    assert ids[-1]["status"] == "QUEUED"  # 5 ambulances in the demo fleet
    client.post(f"/api/missions/{ids[0]['mission_id']}/complete")
    assert client.post("/api/dispatch", json={"latitude": 28.61, "longitude": 77.22}).json()["status"] == "DISPATCHED"


def test_corridor_and_signal_override():
    client = make_client()
    corridor = client.post("/api/corridor", json={"origin": "Central Square", "destination": "City General Hospital"})
    assert corridor.status_code == 200
    signals = corridor.json()["signals_cleared"]
    assert signals
    override = client.post("/api/signals/override", json={"signals": signals})
    assert override.json()["status"] == "PREEMPTED"
    assert client.post("/api/signals/override", json={}).status_code == 422


def test_incident_feed_roundtrip_and_nearest_hospital():
    client = make_client()
    client.post("/api/incidents", json={"camera_id": "CAM-7", "incident_type": "feud", "confidence": 0.8})
    feed = client.get("/api/incidents").json()
    assert feed["count"] == 1 and feed["incidents"][0]["camera_id"] == "CAM-7"
    nearest = client.get("/api/hospitals/nearest", params={"lat": 28.58, "lon": 77.23}).json()
    assert nearest["hospital"]["id"] == "hosp_st_jude"
