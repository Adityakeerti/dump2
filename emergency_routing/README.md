# Agentic Emergency Dispatch & Predictive Routing System

An agentic emergency orchestration platform built using **Python 3.11** and **LangGraph**, integrating pre-trained Computer Vision models for real-time accident and feud detection with an automated ambulance dispatch system and predictive traffic routing.

---

## Key Features

1. **Computer Vision Inference Layer**:
   - **Accident Detection**: Pre-trained YOLOv8 weights detecting vehicle collisions and crashes.
   - **Feud & Riot Detection**: Pre-trained fight detection weights detecting physical fights, brawls, and mob altercations.

2. **Core Emergency Orchestrator (LangGraph `StateGraph`)**:
   - Coordinates incident intake, routing decisions, and dispatch lifecycles.
   - Preserves state across frames and time intervals.

3. **60-Second Feud Persistence & Escalation Gate**:
   - Trivial altercations and brief arguments are filtered out to prevent disturbing the police department unnecessarily.
   - Triggers the **Police Agent** only when an altercation persists continuously for **at least 60 seconds** (or exhibits escalating intensity).

4. **Ambulance Agent & Smart Predictive Routing**:
   - Queries regional hospital registry for nearest available emergency facility and assigns an ambulance.
   - Implements **Predictive Jam Clearance Logic**:
     - Calculates ambulance ETA to reach upstream congestion points ($t_{\text{reach}}$).
     - Queries historical traffic jam clearance distributions ($t_{\text{clear}}$).
     - **Core Rule**: If $t_{\text{reach}} \ge t_{\text{clear}}$, the jam is predicted to dissipate before the ambulance arrives, so the ambulance **maintains the fastest nominal path without rerouting**.
     - If the jam will persist ($t_{\text{reach}} < t_{\text{clear}}$), the agent dynamically evaluates and selects the optimal bypass route.

5. **Police Agent Integration Interface**:
   - Typed Pydantic data contract (`PoliceIncidentReport` & `PoliceAcknowledgment`) ready for seamless integration with your teammate's Police Agent.

---

## Directory Structure

```
Emergency Agent/
├── config/
│   ├── settings.py               # Global parameters, 60s feud thresholds, speeds
├── models/
│   ├── accident_detector.py      # Pretrained YOLOv8 accident detector
│   ├── feud_detector.py          # Fight/feud detection wrapper
│   └── vision_pipeline.py        # Stream ingestor bridging CV models to LangGraph
├── agents/
│   ├── state.py                  # LangGraph state schemas & Pydantic incident models
│   ├── feud_tracker.py           # 60s temporal persistence & cooldown tracker
│   ├── ambulance_agent.py        # Hospital matcher & ambulance dispatch agent
│   ├── police_interface.py       # Contract & mock for teammate's Police Agent
│   └── emergency_agent.py        # LangGraph StateGraph Core Orchestrator
├── routing/
│   ├── graph.py                  # Road network graph (nodes, edges, active jams)
│   ├── traffic_history.py        # Historical jam duration analytics
│   └── predictive_router.py      # Predictive routing algorithm (t_reach vs t_clear)
├── services/
│   └── hospital_service.py       # Hospital registry, ER capacity & ambulance fleet
├── simulation/
│   ├── synthetic_scenarios.py    # Pre-configured test scenarios (clearing jam, persistent jam, feud)
│   └── runner.py                 # Interactive demonstration runner
└── tests/
    ├── test_feud_tracker.py      # Unit tests for 60-second dispute gate
    ├── test_predictive_router.py # Unit tests for jam clearance vs reroute decisions
    └── test_emergency_agent.py   # Integration tests for LangGraph workflows
```

---

## Getting Started

### 1. Activate Python 3.11 Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Run All Automated Tests
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

### 3. Run the Demonstration Simulation
To run all scenarios:
```powershell
.\.venv\Scripts\python.exe -m simulation.runner --scenario all
```

Or individual scenarios:
```powershell
# Scenario 1: Accident with jam that clears before arrival (preserves path)
.\.venv\Scripts\python.exe -m simulation.runner --scenario clearing-jam

# Scenario 2: Accident with persistent severe bottleneck (dynamic reroute)
.\.venv\Scripts\python.exe -m simulation.runner --scenario persistent-jam

# Scenario 3: Public feud timeline (0s -> 30s suppressed, 65s alerts police)
.\.venv\Scripts\python.exe -m simulation.runner --scenario feud
```
