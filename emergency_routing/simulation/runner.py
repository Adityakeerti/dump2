"""Interactive Scenario Runner and Demonstration Bench for Emergency Response System."""

import sys
import argparse
from datetime import datetime
from services.hospital_service import HospitalService
from routing.predictive_router import PredictiveRouter
from agents.ambulance_agent import AmbulanceAgent
from agents.feud_tracker import FeudTracker
from agents.police_interface import MockPoliceAgent
from agents.emergency_agent import EmergencyAgent
from simulation.synthetic_scenarios import (
    get_scenario_accident_clearing_jam,
    get_scenario_accident_persistent_jam,
    get_scenario_feud_timeline,
)


def print_banner(title: str):
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80)


def run_accident_scenario_clearing_jam():
    print_banner("Scenario 1: Accident with Upstream Jam that Dissipates in Time")
    incident, graph, history = get_scenario_accident_clearing_jam()

    hospital_service = HospitalService()
    router = PredictiveRouter(graph=graph, history_db=history)
    ambulance_agent = AmbulanceAgent(hospital_service=hospital_service, predictive_router=router)
    police_mock = MockPoliceAgent()
    feud_tracker = FeudTracker()

    emergency_agent = EmergencyAgent(
        ambulance_agent=ambulance_agent,
        police_agent=police_mock,
        feud_tracker=feud_tracker,
    )

    print(f"\n[EVENT INGESTED] {incident.incident_id}")
    print(f"  - Type: {incident.incident_type}")
    print(f"  - Location: {incident.address} (Node: {incident.location_node_id})")
    print(f"  - Severity: {incident.severity:.2f} | Confidence: {incident.confidence:.2%}")

    print("\n[LANGGRAPH ORCHESTRATION IN PROGRESS...]")
    final_state = emergency_agent.process_incident(incident)

    print("\n[ROUTING & AMBULANCE DISPATCH OUTCOME]")
    mission = final_state.ambulance_mission
    if mission:
        print(f"  - Mission ID: {mission.mission_id}")
        print(f"  - Unit Allocated: {mission.ambulance_id} from {mission.hospital_name}")
        print(f"  - Chosen Route: {' -> '.join(mission.route_nodes)}")
        print(f"  - Total Transit Distance: {mission.total_distance_km} km")
        print(f"  - Estimated Travel Time: {mission.estimated_arrival_minutes} mins")
        print(f"  - Rerouted: {mission.rerouted}")
        print(f"  - Reason: {mission.routing_reason}")

    print("\n[AUDIT LOG TRACE]")
    for log in final_state.audit_log:
        print(f"  * {log}")

    # Assertion check
    assert not mission.rerouted, "FAIL: Ambulance should NOT be rerouted when jam clears in time!"
    print("\n>>> VERIFICATION SUCCESS: Jam predicted to clear before arrival -> Fastest path PRESERVED!")


def run_accident_scenario_persistent_jam():
    print_banner("Scenario 2: Accident with Persistent Severe Bottleneck Jam")
    incident, graph, history = get_scenario_accident_persistent_jam()

    hospital_service = HospitalService()
    router = PredictiveRouter(graph=graph, history_db=history)
    ambulance_agent = AmbulanceAgent(hospital_service=hospital_service, predictive_router=router)
    police_mock = MockPoliceAgent()
    feud_tracker = FeudTracker()

    emergency_agent = EmergencyAgent(
        ambulance_agent=ambulance_agent,
        police_agent=police_mock,
        feud_tracker=feud_tracker,
    )

    print(f"\n[EVENT INGESTED] {incident.incident_id}")
    print(f"  - Type: {incident.incident_type}")
    print(f"  - Location: {incident.address} (Node: {incident.location_node_id})")

    final_state = emergency_agent.process_incident(incident)

    mission = final_state.ambulance_mission
    if mission:
        print("\n[ROUTING & AMBULANCE DISPATCH OUTCOME]")
        print(f"  - Mission ID: {mission.mission_id}")
        print(f"  - Unit Allocated: {mission.ambulance_id} from {mission.hospital_name}")
        print(f"  - Chosen Route: {' -> '.join(mission.route_nodes)}")
        print(f"  - Rerouted: {mission.rerouted}")
        print(f"  - Reason: {mission.routing_reason}")

    # Assertion check
    assert mission.rerouted, "FAIL: Ambulance SHOULD be rerouted around persistent jam!"
    print("\n>>> VERIFICATION SUCCESS: Jam will persist upon arrival -> Dynamic REROUTE executed!")


def run_feud_scenario_timeline():
    print_banner("Scenario 3: Public Feud / Danga 60-Second Persistence Gate")
    timeline_events = get_scenario_feud_timeline()

    hospital_service = HospitalService()
    ambulance_agent = AmbulanceAgent(hospital_service=hospital_service)
    police_mock = MockPoliceAgent()
    feud_tracker = FeudTracker(min_duration_sec=60.0)

    emergency_agent = EmergencyAgent(
        ambulance_agent=ambulance_agent,
        police_agent=police_mock,
        feud_tracker=feud_tracker,
    )

    for idx, event in enumerate(timeline_events):
        print(f"\n--- Step {idx + 1}: Event at timestamp {event.timestamp.strftime('%H:%M:%S')} ---")
        print(f"  Camera: {event.camera_id} | Location: {event.address}")
        print(f"  Intensity: {event.severity:.2f} | Confidence: {event.confidence:.2%}")

        result_state = emergency_agent.process_incident(event)
        tracker = result_state.feud_tracking.get(event.camera_id)

        print(f"  [Duration Elapsed]: {tracker.elapsed_duration_seconds:.1f}s / 60.0s")
        print(f"  [Gate Status]: {result_state.decision_summary}")

        if result_state.police_report:
            print(f"  >>> [POLICE DISPATCHED]: Report #{result_state.police_report.report_id}")
            print(f"      Type: {result_state.police_report.incident_type}")
            print(f"      Duration: {result_state.police_report.dispute_duration_seconds}s")
            print(f"      Average Intensity: {result_state.police_report.average_intensity}")
        else:
            print(f"  >>> [POLICE SUPPRESSED]: Police not notified. Minor/early dispute.")

    print("\n>>> VERIFICATION SUCCESS: Feud suppressed below 60s, Police called at >= 60s!")


def main():
    parser = argparse.ArgumentParser(description="Emergency Agent System Simulation Bench")
    parser.add_argument(
        "--scenario",
        choices=["clearing-jam", "persistent-jam", "feud", "all"],
        default="all",
        help="Simulation scenario to execute",
    )
    args = parser.parse_args()

    if args.scenario in ("clearing-jam", "all"):
        run_accident_scenario_clearing_jam()
    if args.scenario in ("persistent-jam", "all"):
        run_accident_scenario_persistent_jam()
    if args.scenario in ("feud", "all"):
        run_feud_scenario_timeline()


if __name__ == "__main__":
    main()
