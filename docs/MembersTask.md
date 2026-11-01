Here is the topic and responsibility breakdown for each of the 4 team members, as defined in [plan.md](file:///home/aditya/Desktop/STUDY/SmartCity/Project/plan.md) and [README.md](file:///home/aditya/Desktop/STUDY/SmartCity/Project/README.md). You can copy and share this directly with your teammates:

---

### 🛡️ Member A: Platform Core & Governance Lead
**Focus:** System backbone, event streaming, incident correlation, and human-in-the-loop safety.

* **Spring Boot Core (`com.citysense.platform`):**
  * JWT Authentication & Role-Based Access Control (Citizen, Admin, Emergency Crew).
  * Universal `Observation` ingestion endpoint (`POST /api/events`, `POST /internal/observations`).
  * Spatial & temporal event correlation engine (clusters observations into an `Incident`).
  * Coordinator rule engine ranking incident urgency.
  * Human-in-the-loop **Approval Queue** state machine (`/api/actions`).
  * Append-only `AuditLog` persistence (`/api/audit`).
  * Real-time WebSocket/STOMP infrastructure (`/ws`, `/topic/city-events`).
  * Flyway baseline migration (`V1__platform.sql`).
* **Scripts & Tools:**
  * Scenario injection script (one-click demo injection of heavy rain, underpass flood, road blockage).
* **Frontend Modules:**
  * **Mobile:** Root Expo navigation shell, WebSocket client listener, global alert banner & toast notifications.
  * **Admin Dashboard:** Operations live map & incident drawer, Approval queue interface, Audit log inspector, Scenario control panel.
* **Entities Owned:** `Observation`, `Incident`, `AgentAction`, `AuditLog`, `User`.
* **Resume Headline:** *Spring Boot Core Platform + Distributed Event Correlation Engine + Human-in-the-Loop Governance + Real-time WebSocket STOMP.*

---

### 🎙️ Member B: Multilingual City Agent & Knowledge Engine Lead
**Focus:** Citizen-facing hero feature, grounded RAG, citation guardrails, and voice AI.

* **Spring Boot Core (`com.citysense.agent`):**
  * Agent gateway controller (`POST /api/agent/chat`, `POST /api/agent/voice`, `GET /api/agent/personas`).
  * Chat session management and tool-execution bridge (executing read-only queries for complaints/events).
  * Knowledge docs CRUD (`POST /api/knowledge/docs`).
  * Resilience4j circuit breakers & cached fallback answer adapter.
  * Flyway migration (`V2__agent.sql`).
* **Python AI Service (`ai-service/app/agent/`):**
  * RAG pipeline on PostgreSQL `pgvector` (`ai` schema).
  * Strict **Abstain Policy** (similarity thresholds; cites verified context or gracefully abstains).
  * Multilingual voice pipeline with Sarvam AI: Speech-to-Text (STT), Text-to-Speech (TTS), and translation (Hindi, English, etc.).
  * Specialist agent personas (Civic, Traffic, Emergency, Transit).
* **Frontend Modules:**
  * **Mobile (Hero Feature — Ask Tab):** Multilingual voice/text chat, audio waveform recorder, source citation badges (`sources[]`), abstain modal ("File a Complaint" CTA), language switcher.
  * **Admin Dashboard:** Knowledge Base Manager (upload documents, vector indexing, verification badges), Agent live activity & confidence metrics panel.
* **Entities Owned:** `KnowledgeDoc`, `KnowledgeChunk` (`ai` schema with `vector`), `ChatSession`.
* **Resume Headline:** *Enterprise RAG Architecture (pgvector) + Strict Abstain Guardrails + Multilingual Voice Agent (Sarvam AI) + Spring Resilience4j Gateway.*

---

### 📋 Member C: Civic Services & Automated Escalation Lead
**Focus:** Public feed, citizen issue reporting, and automated departmental escalation.

* **Spring Boot Core (`com.citysense.civic`):**
  * Citizen complaints workflow (`POST /api/complaints`, `GET /api/complaints/{trackingId}`).
  * Photo attachment storage adapter & unique tracking ID generator.
  * Automated multi-tier **Escalation Scheduler** (Spring `@Scheduled` state machine with `ESCALATION_TICK_SECONDS` demo acceleration):
    `Filed -> Worker Assigned -> Warnings 1-5 -> Ward Officer -> Municipal Commissioner -> CM Portal`.
  * City Events CRUD API (`GET/POST /api/city-events`).
  * PostGIS spatial radius calculation (`ST_DWithin`) for geofenced user proximity alerts.
  * Flyway migration (`V3__civic.sql`).
* **Scripts & Tools:**
  * Synthetic civic data generator & spatial test fixtures.
* **Frontend Modules:**
  * **Mobile (3 Tabs):**
    * **Explore Tab:** City events live feed, category filters, "Near Me" geofenced cards.
    * **Report Tab:** Issue submission form with photo upload, category dropdown, GPS location pin.
    * **Track Tab:** Interactive complaint timeline visualizer displaying the live escalation ladder.
  * **Admin Dashboard:** Complaints Board (Kanban/table view, department assignment, SLA timers, fast-forward demo trigger), City Events CRUD modal.
* **Entities Owned:** `Complaint`, `EscalationStep`, `CityEvent`.
* **Resume Headline:** *Automated State Machine & Escalation Scheduler (Spring Scheduler) + Spatial PostGIS Geofencing + Citizen Civic Workflow.*

---

### 🚦 Member D: Intelligent Mobility & Emergency Routing Lead
**Focus:** Computer vision traffic density, reinforcement learning signal control, and predictive emergency routing.

* **Spring Boot Core (`com.citysense.mobility`):**
  * Emergency route API (`POST /api/emergency/routes`, `POST /api/emergency/reassess`).
  * Green corridor proposal generator (signal timing windows sent to Member A's approval queue).
  * Traffic telemetry & junction status API (`GET /api/traffic/junctions`, `GET /api/traffic/rl-report`).
  * Flyway migration (`V4__mobility.sql`).
* **Python AI Service (`ai-service/app/`):**
  * **Computer Vision (`app/cv/`):** YOLOv8 per-lane grid occupancy density from video frames, streaming to Spring Boot `/internal/observations`.
  * **Emergency Routing (`app/routing/`):** NetworkX arrival-time road graph (OSM extract of Dehradun) with committed route hysteresis & minimum dwell time (prevents route flutter).
  * **Traffic Simulation & RL (`app/rl/`):** SUMO environment with TraCI; DQN adaptive signal policy training and replay vs. fixed-time baseline.
* **Frontend Modules:**
  * **Mobile (Alerts Tab / Crew Mode):** Emergency vehicle crew interface (active route polyline, predicted segment ETAs, reroute evidence badges), citizen "Clear the Lane" green corridor pop-up alert.
  * **Admin Dashboard:** Traffic & Mobility Panel (YOLO camera feeds with density grid overlay, junction signal controls, DQN vs. fixed-time delay comparison charts).
* **Entities Owned:** `RoutePlan`, `RouteDecision`, `RoadSegment`, `JunctionSignalTelemetry`.
* **Resume Headline:** *Computer Vision Traffic Telemetry (YOLOv8) + Reinforcement Learning Traffic Optimization (SUMO + DQN) + Hysteresis-Stabilized Emergency Routing.*