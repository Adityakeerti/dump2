# CITYOS — Implementation Plan

## 1. Goal
Build a hackathon-ready prototype of a futuristic city operating system: a shared city map, cooperating AI agents, predictive emergency routing, and multilingual civic services. Present it as a citywide vision, but clearly label simulated features versus live integrations.

## 2. Stack
- **Frontend:** React + TypeScript + Vite; MapLibre GL for 2D; Three.js for a lightweight 3D city view.
- **Backend:** Python + FastAPI; REST for queries/actions; WebSockets for live map updates.
- **Data:** PostgreSQL + PostGIS for roads, zones, incidents, assets, and complaints. Use seeded JSON/CSV data for the demo.
- **Routing/simulation:** NetworkX for the initial road graph; SUMO only if traffic simulation time permits.
- **Perception:** Start with simulated camera/sensor events. Add OpenCV/YOLO only if a working video source is available.
- **Civic AI:** LLM with RAG over a small, verified local-government FAQ/document set; provide a deterministic fallback.
- **Deployment:** Docker Compose for frontend, API, and database.

## 3. Core Architecture
1. **City data layer:** road graph, intersections, signals, hospitals, public facilities, sensor readings, incidents, weather, complaints.
2. **Event ingestion:** normalize each observation into `{id, type, location, observed_at, source, confidence, status}`.
3. **Specialist agents:** Traffic, Emergency, Infrastructure/Disaster, Environment, Transit, Civic/Governance.
4. **Shared incident/context store:** agents read and publish events through one API and common schema.
5. **City coordinator:** correlates events, ranks urgency, detects cross-domain impact, and creates a proposed action plan.
6. **Action policy:** low-risk demo notifications may run automatically; high-impact actions (signal control, road closure, emergency dispatch, evacuation) require explicit operator approval.
7. **Interfaces:** 2D/3D map, agent activity panel, incident detail drawer, approval queue, civic avatar/complaint screen.

Do not build every futuristic feature as a separate AI model. Use deterministic rules and ordinary services where they are safer and more reliable; use LLMs for grounded civic conversation and summarization.

## 4. Repository Layout
```text
cityos/
  frontend/
    src/
      components/       # Map2D, City3D, AgentPanel, IncidentDrawer
      features/         # emergency, traffic, civic, infrastructure
      api/              # typed API client and WebSocket client
  backend/
    app/
      main.py
      api/              # routes for incidents, routes, agents, complaints
      models/           # Pydantic schemas and ORM models
      services/          # routing, forecasts, event bus, notifications
      agents/            # traffic, emergency, civic, infrastructure, coordinator
      policies/          # approvals, safety rules, audit logging
      seed/              # demo roads, hospitals, events, civic knowledge
    tests/
  docker-compose.yml
  README.md
  .env.example
```

## 5. Build Sequence

### Phase 1 — Demo foundation
- Create FastAPI app, React UI, PostGIS schema, Docker Compose, and seeded sample city.
- Render roads, intersections, hospitals, emergency vehicles, incidents, and city zones on the 2D map.
- Add a basic 3D view of the same locations; synchronize selected incidents between both views.
- Add a scenario-control panel to inject traffic, crash, rain/flood, and complaint events.

**Done when:** the map loads seeded data and injected events appear live without refreshing.

### Phase 2 — Shared event model and agents
- Define common event and agent-response schemas.
- Each agent consumes relevant events and emits a structured finding or proposed action.
- Coordinator groups related events into one incident, records evidence/confidence, and displays a unified timeline.
- Show agent status, latest observation, finding, and proposed action in the UI.

**Done when:** one injected flood event can trigger drainage risk, road-risk, traffic-impact, and citizen-warning proposals linked to the same incident.

### Phase 3 — Predictive, history-aware ambulance routing
- Represent the road network as a weighted graph; edges include length, baseline speed, current state, observed-at timestamp, confidence, and incident status.
- Estimate each edge's travel time at the ambulance's **predicted arrival time**, not just at route-planning time.
- Forecast future edge travel time from current observations, historical time-of-day patterns, signal cycles, roadworks, weather, and active incident evidence.
- Calculate end-to-end ETA for candidate routes. Include turn delays and expected signal delay where modeled.
- Maintain a **committed route**. Recalculate on new observations, but switch only when:
  1. the current route is blocked/unsafe or a critical new fact invalidates it; or
  2. an alternative is reliably expected to beat the current route by a configurable material margin for a sustained period.
- Use hysteresis/minimum dwell time to prevent route oscillation. Log the old route, new route, reason, predicted ETAs, confidence, and evidence for every change.
- Historical patterns are priors, not proof of current road conditions. Fresh verified closure or hazard information overrides historical expectations.
- Simulate ambulance movement along the route and display ETA, route commitment, confidence, and route-change rationale.
- Green-corridor proposals identify relevant intersections and signal timing windows. In the prototype they are simulated; real signal control requires authorized integration and operator approval.

**Done when:** a temporary congestion spike does not cause needless rerouting, while a verified blockage triggers a safe alternative.

### Phase 4 — Civic avatar and complaint workflow
- Build a chat interface for a city digital representative.
- Retrieve answers only from a small verified knowledge base; show the source used and say when information is unavailable.
- Support complaint creation with category, description, location, optional image, status, and tracking ID.
- Route complaints to a simulated responsible department and show status updates.
- Add language selection; enable speech/multilingual APIs only if keys and connectivity are available.

**Done when:** a citizen can ask a grounded question, submit a geo-tagged complaint, and track its simulated status.

### Phase 5 — Cross-domain scenario and demo polish
- Prepare one scripted scenario: heavy rain → underpass risk → traffic forecast → ambulance route check → transit impact → civic alert proposal.
- Add operator approval/rejection for high-impact actions and append every decision to an audit log.
- Add clear labels for simulated feeds, predicted values, stale observations, and uncertain reports.
- Add loading/error states, a reset-scenario button, and a demo mode that works without external API keys.

**Done when:** the complete scenario can be demonstrated reliably in under five minutes.

## 6. Minimum Data Model
- `RoadSegment(id, geometry, length_m, baseline_speed, status)`
- `Observation(id, type, location, observed_at, source, confidence, payload)`
- `Incident(id, type, severity, location, status, created_at, evidence_ids)`
- `RoutePlan(id, vehicle_id, edge_ids, predicted_eta, confidence, committed_at, status)`
- `RouteDecision(id, route_plan_id, reason, old_eta, new_eta, evidence_ids, created_at)`
- `AgentAction(id, incident_id, agent_type, action_type, payload, risk_level, approval_status)`
- `Complaint(id, category, description, location, status, department, created_at)`
- `AuditLog(id, actor, action, timestamp, evidence, outcome)`

## 7. Initial API Contract
- `GET /api/map/features` — roads, hospitals, intersections, active incidents.
- `GET /api/incidents` and `POST /api/events` — list incidents and inject a demo observation.
- `POST /api/emergency/routes` — calculate an ambulance route and predicted ETA.
- `POST /api/emergency/reassess` — evaluate whether evidence justifies a route change.
- `GET /api/agents/status` — agent health and latest findings.
- `POST /api/actions/{id}/approve` and `/reject` — operator decision.
- `POST /api/complaints` and `GET /api/complaints/{id}` — complaint workflow.
- `WS /ws/city-events` — push map updates, incident changes, agent findings, and route decisions.

## 8. Demo Acceptance Tests
- Map and agents work using seeded data with no external services.
- A route decision shows predicted ETA, confidence, and evidence.
- A minor temporary speed change does not flip the committed ambulance route repeatedly.
- A verified blockage can trigger route reassessment.
- High-impact actions remain pending until approved.
- A cross-domain incident is visible as one linked timeline.
- Civic answers cite the configured knowledge source or explicitly abstain.
- Every route change and approval/rejection is audit-logged.

## 9. Out of Scope for the Hackathon
Do not claim live access to city cameras, hospital capacity, traffic signals, government databases, emergency dispatch, or citizen identities unless an authorized integration exists. Treat citywide surveillance, automated enforcement, autonomous closures, and evacuation orders as future work requiring legal, privacy, security, and operational review.

## 10. Slide Details (8–9 Slides)

### Slide 1 — CITYOS
**Headline:** The Agentic AI Operating System for Smart Cities  
**Message:** One city. One intelligent map. Many cooperating agents. One coordinated response.  
**Visual:** 2D operations map beside a 3D digital twin, with emergency, mobility, infrastructure, and civic markers.

### Slide 2 — The Problem
**Cover:** Disconnected departments; reactive traffic management; unreliable incident context; fragmented citizen communication.  
**Visual:** Separate traffic, emergency, infrastructure, and civic systems producing isolated alerts.

### Slide 3 — The Unified Solution
**Cover:** Shared city context, specialist agents, cross-agent coordinator, human approval for high-impact actions, 2D and 3D interfaces.  
**Visual:** City map at the center with connected agents and a coordination layer.

### Slide 4 — Predictive Emergency Grid
**Cover:** Arrival-time-aware road forecasts, end-to-end ETA comparison, route commitment, hysteresis, evidence-driven switching, green-corridor proposals.  
**Key line:** “Do not chase the fastest road right now; choose the safest expected route when the ambulance reaches each segment.”  
**Visual:** Two route options with predicted ETAs and a committed route; show a minor congestion spike that does not trigger a switch.

### Slide 5 — Citywide Feature Set
**Cover:** Emergency/disaster response; traffic and mobility; public transport; infrastructure; environment; civic avatar; complaint tracking; governance updates and townhalls.  
**Visual:** Compact feature groups around one map. Label unbuilt items as planned capabilities.

### Slide 6 — Technical Architecture
**Cover:** Sensors/data → event ingestion → specialist agents → shared context → coordinator → approval/policy layer → map, alerts, work orders, civic interface.  
**Mention:** FastAPI, React, PostGIS, WebSockets, routing engine, RAG knowledge base, simulation.  
**Visual:** Layered architecture with feedback from outcomes to predictions.

### Slide 7 — One Incident, Coordinated Response
**Scenario:** Heavy rain raises underpass flood risk. Drainage, road, traffic, emergency, transit, and civic agents contribute to one incident record; the coordinator proposes actions for approval.  
**Visual:** Event timeline plus the same incident on 2D and 3D maps.

### Slide 8 — Working Prototype and Evaluation
**Show:** Interactive map, multiple agents, route prediction and commitment, civic avatar, complaint tracking, approval queue.  
**Measure:** ETA error, unnecessary route switches, incident-to-alert latency, complaint-routing accuracy, grounded-answer rate, coordination latency.  
**Visual:** Prototype screenshot/mock-up and metrics panel. Do not present unmeasured gains as results.

### Slide 9 — Impact and Roadmap
**Cover:** Simulation first; supervised pilot; approved live integrations; scale after safety/privacy/reliability testing.  
**Closing line:** “CITYOS turns a city map from a display into a coordinated intelligence layer.”  
**Visual:** From isolated alerts to a coordinated, resilient city.
