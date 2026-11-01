# Agentic Emergency Dispatch & Predictive Routing System: Implementation Plan

## Goal Description
The objective is to design and implement an end-to-end, multi-agent emergency response architecture powered by **LangGraph** and pretrained Computer Vision (CV) deep learning models. 

The system continuously processes CCTV/public video feeds to detect:
1. **Accidents (Vehicle collisions / crashes)**
2. **Public Feuds (Disputes, physical fights, and riots / danga)**

Once an incident is detected, the **Emergency Agent** (core orchestrator) manages routing and dispatches:
- **Accident detected**: Triggers the **Ambulance Agent**, which locates the nearest hospital with available emergency capacity, dispatches an ambulance, and computes a **Smart Predictive Route**. The routing algorithm evaluates active traffic jams against **historical clearance patterns**: if historical data indicates an upstream jam will dissipate before the ambulance arrives, the system maintains the primary fastest path instead of prematurely rerouting.
- **Feud detected**: Applies a **60-Second Persistence & Escalation Gate**. Trivial arguments or brief scuffles are filtered out; only feuds persisting $\ge 60$ seconds (or showing sustained escalation) trigger the **Police Agent Interface**.

> [!NOTE]
> Per the project specification, the Police Agent implementation is owned by a teammate. Our system provides a formal, typed integration contract (`PoliceDispatchContract`) and an automated mock service so the pipeline is fully testable end-to-end.

---

## System Architecture Diagram

```mermaid
flowchart TD
    subgraph Ingestion ["1. Video Ingestion & CV Layer"]
        CCTV["CCTV / Public Video Stream"] --> Preprocess["Frame Sampling & Video Buffer"]
        Preprocess --> AccModel["Accident Detection Model (YOLOv8-Accident)"]
        Preprocess --> FeudModel["Feud/Fight Detection Model (YOLOv8-Fight / 3D-CNN)"]
    end

    subgraph CoreAgent ["2. Emergency Core Agent (LangGraph StateGraph)"]
        AccModel -->|AccidentDetectedEvent| Supervisor["Emergency Agent Orchestrator"]
        FeudModel -->|FeudDetectedEvent| FeudTracker["60s Feud Temporal Filter\n& Intensity Gate"]
        
        FeudTracker -->|Duration < 60s| FeudLog["Log & Monitor (Suppressed)"]
        FeudTracker -->|Duration >= 60s| Supervisor
    end

    subgraph PoliceBoundary ["3. Police Integration Boundary (Teammate)"]
        Supervisor -->|Dispute Verified (>= 60s)| PoliceContract["Police Agent Interface (Schema / Contract)"]
        PoliceContract --> PoliceAgentMock["Teammate Police Agent / Mock Service"]
    end

    subgraph AmbulanceSubsystem ["4. Ambulance Agent Subsystem"]
        Supervisor -->|Accident Confirmed| AmbAgent["Ambulance Agent"]
        
        AmbAgent --> HospService["Hospital Discovery Service\n(Nearest ER & Bed Availability)"]
        HospService --> AmbDispatch["Ambulance Unit Allocated"]
        
        AmbDispatch --> RouteEngine["Smart Predictive Routing Engine"]
        
        subgraph RoutingDecision ["Predictive Jam Clearance Logic"]
            RouteEngine --> CandidatePaths["Calculate Candidate Paths (A* / Dijkstra)"]
            CandidatePaths --> JamCheck{"Traffic Jam on\nFastest Path?"}
            JamCheck -->|No Jam| KeepFastest["Keep Fastest Route"]
            JamCheck -->|Jam Detected| CalcETA["Calculate Ambulance ETA to Jam (t_reach)"]
            CalcETA --> QueryHist["Query Historical Clearance Data (t_clear)"]
            QueryHist --> ClearanceDecision{"t_reach >= t_clear ?\n(Will jam clear in time?)"}
            ClearanceDecision -->|Yes (Clears before arrival)| MaintainRoute["Maintain Fastest Path\n(Do NOT Reroute)"]
            ClearanceDecision -->|No (Jam will persist)| Reroute["Dynamic Reroute to\nOptimal Alternative"]
        end
    end
```

---

## User Review Required

> [!IMPORTANT]
> **Pre-trained Model Selection**:
> 1. **Accident Detection**: We propose using pretrained YOLOv8 weights specialized in road collisions (e.g. `keremberke/yolov8m-car-accident-detection` or Roboflow Universe `accident-detection-v8` weights) which output bounding boxes, vehicle classifications, and collision confidence scores in real time ($>30\text{ FPS}$).
> 2. **Feud Detection**: We propose using a dual-mode approach: `Musawer1214/Fight-Violence-detection-yolov8` for real-time bounding box fight localization, coupled with a temporal sliding window buffer to track fight duration over continuous frames.
> 
> *Fallback for offline testing*: A built-in mock stream simulator that generates realistic accident and dispute events with bounding boxes and timestamp sequences is included so you can develop and demonstrate the agents without requiring GPU video processing at every step.

> [!WARNING]
> **Python Environment Compatibility**:
> The active workspace is running Python `3.14.3`. PyTorch and some pre-compiled Computer Vision wheels (`ultralytics`, `torchvision`, `cv2`) often require Python `3.10`–`3.12` on Windows. We will configure the project using a virtual environment (`uv venv --python 3.11` or `3.12`) or gracefully fallback to mock vision providers when heavy C-extensions cannot compile on Python 3.14.

---

## Open Questions

> [!IMPORTANT]
> 1. **Hospital Selection Metric**: Should the nearest hospital be determined strictly by shortest driving distance, shortest nominal travel time, or should it also account for emergency room capacity / trauma center specialization? (We plan to default to *Effective Travel Time + Trauma Capability*).
> 2. **Police Agent Handoff Mechanism**: What protocol does your teammate plan to use to communicate with the Police Agent? (Options: Python module call, LangGraph sub-graph state handoff, FastAPI REST endpoint, or a shared JSON/Kafka queue. We provide both a Python typed protocol and a REST adapter).

---

## Proposed Changes: Module-by-Module Plan

We will organize the codebase cleanly into modular packages:

```
Emergency Agent/
├── config/
│   └── settings.py               # Config parameters, thresholds (60s feud window, weights, API keys)
├── models/
│   ├── accident_detector.py      # Pretrained YOLOv8 accident detector
│   ├── feud_detector.py          # Pretrained fight/feud detector & temporal window
│   └── vision_pipeline.py        # Stream ingestor combining video feed with both detectors
├── agents/
│   ├── state.py                  # LangGraph shared State definitions (TypedDict / Pydantic)
│   ├── emergency_agent.py        # LangGraph StateGraph Core Orchestrator
│   ├── feud_tracker.py           # 60-second dispute persistence & intensity evaluator
│   ├── ambulance_agent.py        # Ambulance Agent implementation
│   └── police_interface.py       # Contract & Mock for teammate's Police Agent
├── routing/
│   ├── graph.py                  # Road network graph (nodes, edges, lengths, capacities)
│   ├── traffic_history.py        # Historical traffic jam duration database & query engine
│   └── predictive_router.py      # Smart routing with Jam Clearance vs. Ambulance ETA algorithm
├── services/
│   └── hospital_service.py       # Hospital spatial registry & ambulance fleet allocator
├── simulation/
│   ├── synthetic_scenarios.py    # Pre-canned test video frames / simulated telemetry scenarios
│   └── runner.py                 # Interactive visual CLI & test bench
├── tests/
│   ├── test_feud_tracker.py      # Unit tests for 60-second gate
│   ├── test_predictive_router.py # Unit tests for jam clearance vs reroute decisions
│   └── test_ambulance_agent.py   # Unit tests for hospital matching & dispatch
└── pyproject.toml                # Project dependencies (langgraph, langchain-core, pydantic, etc.)
```

---

### Module 1: Computer Vision & Pre-trained Models

#### [NEW] `models/accident_detector.py`
Integrates pre-trained YOLO collision detection weights:
- Accepts raw frames or video streams.
- Runs bounding-box inference for vehicle collision signatures (e.g., overlapping vehicle bounding boxes with deformation/fire/smoke/speed vectors).
- Returns structured `AccidentDetection` payload:
  ```python
  class AccidentDetection(BaseModel):
      detected: bool
      confidence: float
      severity: Literal["low", "medium", "critical"]
      timestamp: datetime
      bounding_boxes: list[dict]
      location_id: str
  ```

#### [NEW] `models/feud_detector.py`
Integrates fight and public violence detection weights:
- Uses `Fight-Violence-detection-yolov8` or action-recognition video classifier.
- Returns frame-by-frame fight detection with intensity metrics:
  ```python
  class FeudFrameDetection(BaseModel):
      detected: bool
      confidence: float
      intensity_score: float # 0.0 to 1.0 (based on crowd density, motion entropy)
      timestamp: datetime
      camera_id: str
      location: tuple[float, float]
  ```

---

### Module 2: Core Orchestrator & State Management (LangGraph)

#### [NEW] `agents/state.py`
Defines the shared system state across the LangGraph execution lifecycle:
```python
from typing import Annotated, TypedDict, Literal, Optional
from datetime import datetime
from pydantic import BaseModel

class IncidentLocation(BaseModel):
    camera_id: str
    latitude: float
    longitude: float
    address: str

class FeudState(BaseModel):
    first_detected_at: Optional[datetime] = None
    last_detected_at: Optional[datetime] = None
    accumulated_duration_sec: float = 0.0
    intensity_history: list[float] = []
    is_police_notified: bool = False

class AmbulanceMission(BaseModel):
    mission_id: str
    ambulance_id: str
    hospital_name: str
    hospital_location: tuple[float, float]
    selected_route_nodes: list[str]
    nominal_eta_minutes: float
    rerouted: bool
    reroute_reason: Optional[str] = None

class EmergencyState(TypedDict):
    incident_type: Literal["ACCIDENT", "FEUD", "NONE"]
    location: IncidentLocation
    timestamp: datetime
    feud_state: FeudState
    ambulance_mission: Optional[AmbulanceMission]
    police_dispatch_id: Optional[str]
    status_log: list[str]
```

#### [NEW] `agents/emergency_agent.py`
Constructs the LangGraph `StateGraph`:
1. **Entry Node (`evaluate_incoming_event`)**: Inspects incoming CV detections.
2. **Conditional Branch**:
   - If `ACCIDENT` $\rightarrow$ Transition directly to `ambulance_agent_node`.
   - If `FEUD` $\rightarrow$ Transition to `feud_persistence_node`.
3. **Ambulance Agent Node**: Calls hospital finder, dispatches unit, computes predictive route.
4. **Feud Persistence Node**: Evaluates elapsed dispute duration.
   - If $< 60$ seconds: Loops to `monitor_feud_node` or terminates turn while preserving timestamp.
   - If $\ge 60$ seconds: Triggers `police_dispatch_node`.

---

### Module 3: 60-Second Feud Persistence Filter

#### [NEW] `agents/feud_tracker.py`
Implements the exact requirement: **police should not be disturbed regularly for trivial or instantaneous altercations.**
- Tracks dispute start timestamp $T_{start}$ and last confirmation $T_{last}$.
- Duration $\Delta t = T_{last} - T_{start}$.
- If an interruption in fighting exceeds a grace timeout (e.g. 15 seconds without violence), the dispute is classified as de-escalated and the timer is reset.
- If continuous or escalating conflict reaches $\ge 60.0$ seconds, it triggers the Police Agent.

Mathematical Decision:
$$\text{TriggerPolice} = \left(\Delta t \ge 60.0\text{s}\right) \land \left(\overline{\text{Intensity}} \ge \theta_{\text{intensity}}\right)$$

---

### Module 4: Ambulance Agent & Hospital Dispatcher

#### [NEW] `services/hospital_service.py`
Manages the regional hospital registry:
- Stores hospital coordinates, trauma capabilities, ICU availability, and current ambulance fleet status.
- Implements `find_nearest_hospital(incident_lat, incident_lon)` using Haversine & drive-time metrics.
- Allocates the closest available emergency ambulance.

#### [NEW] `agents/ambulance_agent.py`
Coordinates the ambulance workflow:
1. Receives accident coordinates.
2. Requests hospital allocation from `hospital_service`.
3. Invokes `PredictiveRouter` to determine the safest, fastest transit path.
4. Produces mission manifest and updates dispatch telemetry.

---

### Module 5: Smart Predictive Routing with Historical Jam Clearance

#### [NEW] `routing/traffic_history.py`
Maintains historical traffic jam clearance distributions:
- Jams are indexed by `(segment_id, time_of_day_bucket, day_of_week)`.
- Provides clearance prediction function:
  $$\hat{T}_{\text{clearance}}(\text{segment}, \text{jam\_severity}) \rightarrow \text{minutes until road clears}$$

#### [NEW] `routing/predictive_router.py`
Implements the smart routing algorithm specified in the prompt and `Flow.jpeg`:

```python
def evaluate_route_with_predictive_traffic(
    origin: str, 
    destination: str, 
    graph: RoadGraph, 
    history_db: TrafficHistoryDB
) -> RoutePlan:
    # 1. Compute fastest nominal path
    primary_path = graph.dijkstra_shortest_path(origin, destination)
    
    # 2. Check for traffic jams along the path
    jams = graph.get_active_jams_on_path(primary_path)
    if not jams:
        return RoutePlan(path=primary_path, rerouted=False, reason="Fastest path clear")

    # 3. For each jam, compare ambulance ETA vs predicted clearance
    for jam in jams:
        t_reach = graph.estimate_eta_to_node(origin, jam.node, speed_kmh=60.0)
        t_clear = history_db.predict_clearance_time(jam.segment_id, jam.current_duration)

        if t_reach >= t_clear:
            # Jam will dissipate BEFORE ambulance reaches this segment!
            # SPECIFICATION: Do NOT reroute!
            continue
        else:
            # Jam will still be active, imposing delay
            delay = t_clear - t_reach
            alternative_path = graph.dijkstra_shortest_path(
                origin, destination, avoid_segments=[jam.segment_id]
            )
            if alternative_path.total_time < (primary_path.total_time + delay):
                return RoutePlan(
                    path=alternative_path, 
                    rerouted=True, 
                    reason=f"Jam on {jam.segment_id} will persist (clears in {t_clear:.1f}m, reach in {t_reach:.1f}m)"
                )

    return RoutePlan(
        path=primary_path, 
        rerouted=False, 
        reason="Historical data predicts jam will clear before ambulance arrives"
    )
```

---

### Module 6: Police Agent Contract & Mock Service

#### [NEW] `agents/police_interface.py`
Defines the clean boundary for the teammate:
```python
class PoliceIncidentReport(BaseModel):
    report_id: str
    incident_type: Literal["PUBLIC_FEUD", "RIOT", "WEAPON_INVOLVED"]
    duration_seconds: float
    average_intensity: float
    location_coordinates: tuple[float, float]
    address: str
    estimated_crowd_size: int
    video_snapshot_url: Optional[str]
    dispatched_at: datetime

class PoliceAgentInterface:
    """Interface to be implemented by teammate or invoked via REST/IPC"""
    def dispatch_police(self, report: PoliceIncidentReport) -> dict:
        ...
```

---

### Module 7: Simulation & Interactive Test Bench

#### [NEW] `simulation/synthetic_scenarios.py` & `simulation/runner.py`
Provides 3 runnable simulation scenarios to demonstrate the agents in action:
1. **Scenario A (Accident with Clearing Jam)**: Accident occurs at intersection $X$. Fastest path has a jam $3\text{ km}$ ahead. Ambulance reaches in $4\text{ mins}$, historical clearance is $2.5\text{ mins}$. Verifies ambulance **maintains path without rerouting**.
2. **Scenario B (Accident with Persistent Jam)**: Jam $1\text{ km}$ ahead with clearance time $25\text{ mins}$. Verifies ambulance **dynamically reroutes** to alternate route.
3. **Scenario C (Minor Feud vs. Sustained Riot)**:
   - Scuffle lasts $35\text{ seconds}$ then stops $\rightarrow$ Emergency Agent logs but **does not alert police**.
   - Public dispute continues past $60\text{ seconds}$ $\rightarrow$ Emergency Agent triggers **Police Agent dispatch**.

---

## Verification Plan

### Automated Tests
We will execute pytest across all core modules:
```bash
pytest tests/ -v
```
Specific test suites:
- `tests/test_feud_tracker.py`:
  - Verify feud lasting $30\text{s}$ does NOT trigger police.
  - Verify feud lasting $65\text{s}$ triggers police dispatch exactly once.
  - Verify intermittent feud with long cooldown resets timer.
- `tests/test_predictive_router.py`:
  - Test case where $t_{reach} \ge t_{clear} \implies \text{No reroute}$.
  - Test case where $t_{reach} < t_{clear} \implies \text{Reroutes to fastest alternative}$.
- `tests/test_emergency_agent.py`:
  - Full LangGraph execution of Accident $\rightarrow$ Hospital $\rightarrow$ Ambulance flow.

### Manual Verification & Live Run
Run the interactive scenario runner:
```bash
python -m simulation.runner --scenario all
```
Expected output:
- Step-by-step colored console log showing LangGraph state transitions.
- Routing decision matrix explaining why a jam was bypassed or retained based on historical prediction.
- Feud timer countdown showing suppression below 60s and alert generation at 60s.
