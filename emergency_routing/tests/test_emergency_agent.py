"""End-to-End LangGraph Orchestrator Integration Tests."""

from datetime import datetime, timedelta
import pytest
from services.hospital_service import HospitalService
from routing.predictive_router import PredictiveRouter
from agents.ambulance_agent import AmbulanceAgent
from agents.feud_tracker import FeudTracker
from agents.police_interface import MockPoliceAgent
from agents.emergency_agent import EmergencyAgent
from simulation.synthetic_scenarios import (
    build_demo_city_network,
    get_scenario_accident_clearing_jam,
    get_scenario_accident_persistent_jam,
    get_scenario_feud_timeline,
)


@pytest.fixture
def agent_system():
    graph, history = build_demo_city_network()
    hospital_service = HospitalService()
    router = PredictiveRouter(graph=graph, history_db=history)
    ambulance_agent = AmbulanceAgent(hospital_service=hospital_service, predictive_router=router)
    police_mock = MockPoliceAgent()
    feud_tracker = FeudTracker(min_duration_sec=60.0)

    agent = EmergencyAgent(
        ambulance_agent=ambulance_agent,
        police_agent=police_mock,
        feud_tracker=feud_tracker,
    )
    return agent, police_mock, hospital_service


def test_accident_triggers_ambulance_mission(agent_system):
    agent, _, _ = agent_system
    incident, _, _ = get_scenario_accident_clearing_jam()

    state = agent.process_incident(incident)

    assert state.workflow_step == "COMPLETED"
    assert state.ambulance_mission is not None
    assert state.ambulance_mission.ambulance_id.startswith("AMB-")
    assert state.ambulance_mission.hospital_name == "City General Trauma Center"
    assert state.police_report is None  # Police NOT disturbed for accident


def test_feud_gate_timeline_execution(agent_system):
    agent, police_mock, _ = agent_system
    timeline = get_scenario_feud_timeline()

    # Step 1: T=0s
    s1 = agent.process_incident(timeline[0])
    assert s1.police_report is None
    assert len(police_mock.dispatched_cases) == 0

    # Step 2: T=30s
    s2 = agent.process_incident(timeline[1])
    assert s2.police_report is None
    assert len(police_mock.dispatched_cases) == 0

    # Step 3: T=65s (Exceeds 60-second rule)
    s3 = agent.process_incident(timeline[2])
    assert s3.police_report is not None
    assert s3.police_report.dispute_duration_seconds >= 60.0
    assert len(police_mock.dispatched_cases) == 1
    assert "PCR-2026-" in list(police_mock.dispatched_cases.keys())[0]

    # Step 4: T=90s (No duplicate dispatch)
    s4 = agent.process_incident(timeline[3])
    assert s4.police_report is None
    assert len(police_mock.dispatched_cases) == 1
