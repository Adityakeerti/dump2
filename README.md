# CitySense (CityOS)

> **One app for everything happening in the city, from fun to fixes.**  
> A coordinated smart-city operating system combining an Expo mobile app (citizens & emergency crews), a React + Vite operations dashboard, a robust Spring Boot 3 core backend, and a specialized Python AI/ML simulation engine.

Repository: [https://github.com/Adityakeerti/CitySense](https://github.com/Adityakeerti/CitySense)  
Complete Implementation Plan: [plan.md](plan.md)

---

## 🏛️ High-Level Architecture

```text
       Mobile (Expo Router)              Admin Dashboard (React + Vite)
             \                                      /
              \             REST + STOMP           /
               v                                  v
    +-------------------------------------------------------------+
    |            SPRING BOOT 3 CORE (Public Gateway)              |  Java 21, Maven
    |  • M1: Platform & Governance  • M2: Multilingual Agent     |  PostgreSQL 16 + PostGIS
    |  • M3: Civic & Escalation     • M4: Intelligent Mobility   |  Spring Security (JWT)
    +-------------------------------------------------------------+
               |  REST (Internal)       ^ POST /internal/observations
               v                        |
    +-------------------------------------------------------------+
    |             PYTHON AI SERVICE (Internal Engine)             |  FastAPI, Python 3.11+
    |  • M2: pgvector RAG + Sarvam STT/TTS + Abstain Policy       |  NetworkX, YOLOv8,
    |  • M4: YOLOv8 Lane Density, SUMO + DQN Reinforcement Learn  |  SUMO + TraCI, PyTorch
    +-------------------------------------------------------------+
```

---

## 👥 Team Breakdown — 4 Feature Modules

Each of the 4 team members has full-stack ownership of their designated domain: a **Spring Boot module**, a **frontend vertical (Mobile + Dashboard)**, and the corresponding **algorithmic/AI engine**.

```
+-------------------------------------------------------------------------------------------------------+
|                                    CITYSENSE FULL-STACK WORKSPACE                                     |
+------------------------------------+------------------------------------+-----------------------------+
| Feature Module                     | Spring Boot Core (`core/`)         | Clients & AI Services       |
+------------------------------------+------------------------------------+-----------------------------+
| M1: Platform & Governance Lead     | com.citysense.platform             | Vite Map, Scenario, Approvals|
| M2: Multilingual Agent & RAG Lead  | com.citysense.agent                | Mobile Ask Tab, Python RAG  |
| M3: Civic Services & Escalation    | com.citysense.civic                | Mobile Explore/Report/Track |
| M4: Mobility & Traffic AI Lead     | com.citysense.mobility             | Mobile Alerts, YOLOv8, SUMO |
+------------------------------------+------------------------------------+-----------------------------+
```

---

### 🛡️ Member A: Platform & Governance Lead
*Lead architect for core reliability, real-time event streaming, and human-in-the-loop governance.*

- **Spring Boot Core:** `core/src/main/java/com/citysense/platform/`
  - JWT Authentication & RBAC (`User`: Citizen, Admin, Emergency Crew).
  - Ingestion engine for universal `Observation` data model (`POST /api/events`, `POST /internal/observations`).
  - Correlation engine: clusters observations into `Incident` objects and ranks urgency.
  - Human oversight: `AgentAction` approval/rejection state machine (`/api/actions`).
  - Append-only `AuditLog` persistence (`/api/audit`).
  - Real-time WebSocket/STOMP infrastructure (`/ws`, `/topic/city-events`).
- **Dashboard UI:** `dashboard/src/features/platform/`
  - Operations live map & active incident drawer.
  - High-impact action **Approval Queue** & audit history inspector.
  - **Scenario Control Panel** (one-click demo injection: rain, flood, crash).
- **Mobile UI:** Global Expo navigation shell, WebSocket listener, global alert toast.
- **Resume Highlight:** *Spring Boot Core Platform + Distributed Event Correlation Engine + Human-in-the-Loop Governance + Real-time WebSocket STOMP.*

---

### 🎙️ Member B: Multilingual City Agent & RAG Lead
*Lead engineer for the citizen-facing hero feature: conversational AI with verified citations and speech.*

- **Spring Boot Core:** `core/src/main/java/com/citysense/agent/`
  - Agent gateway controller (`POST /api/agent/chat`, `POST /api/agent/voice`).
  - Chat session management & tool-execution bridge (executing read-only queries for complaints/events).
  - Knowledge docs CRUD (`POST /api/knowledge/docs`).
  - Circuit breakers & cached fallbacks via **Resilience4j**.
- **Python AI Service:** `ai-service/app/agent/`
  - RAG engine on PostgreSQL `pgvector` (`ai` schema).
  - Strict **Abstain Policy**: triggers clear fallback when similarity < threshold.
  - Multilingual voice pipeline: Sarvam AI STT, TTS, and translation (Hindi, English, etc.).
  - Specialist personas (Civic, Traffic, Emergency, Transit).
- **Mobile UI:** `mobile/app/(tabs)/ask.tsx`
  - **Ask Tab (Hero feature):** voice recording waveform, text chat, live streaming, source citation pills (`sources[]`), abstain CTA modal.
- **Dashboard UI:** `dashboard/src/features/agent/`
  - Knowledge Base Manager (upload documents, vector indexing, verification badges).
  - Agent live activity & confidence metrics panel.
- **Resume Highlight:** *Enterprise RAG Architecture (pgvector) + Strict Abstain Guardrails + Multilingual Voice Agent (Sarvam AI) + Spring Resilience4j Gateway.*

---

### 📋 Member C: Civic Services & Automated Escalation Lead
*Lead engineer for citizen issue resolution, spatial awareness, and automated departmental escalation.*

- **Spring Boot Core:** `core/src/main/java/com/citysense/civic/`
  - Complaints workflow (`POST /api/complaints`, `GET /api/complaints/{trackingId}`).
  - Image storage adapter & unique tracking ID generator.
  - Automated multi-tier **Escalation Scheduler** (Spring `@Scheduled` state machine with `ESCALATION_TICK_SECONDS` demo acceleration):
    `Filed -> Worker Assigned -> Warnings 1-5 -> Ward Officer -> Municipal Commissioner -> CM Portal`.
  - City Events CRUD (`/api/city-events`).
  - Geofence calculation service via PostGIS spatial distance queries (`ST_DWithin`).
- **Mobile UI:** `mobile/app/(tabs)/`
  - `index.tsx` (**Explore Tab**): live map and events feed, category filters, "Near Me" geofence cards.
  - `report.tsx` (**Report Tab**): complaint form with photo capture/upload, category selector, GPS picker.
  - `track.tsx` (**Track Tab**): interactive complaint escalation ladder visualizer with milestone markers.
- **Dashboard UI:** `dashboard/src/features/civic/`
  - Complaints Board (Kanban & tabular views, assignment, SLA countdowns, fast-forward demo trigger).
  - City Events CRUD publisher.
- **Resume Highlight:** *Automated State Machine & Escalation Scheduler (Spring Scheduler) + Spatial PostGIS Geofencing + Citizen Civic Workflow.*

---

### 🚦 Member D: Intelligent Mobility & Emergency Routing Lead
*Lead engineer for computer vision traffic telemetry, adaptive signal control, and emergency transit.*

- **Spring Boot Core:** `core/src/main/java/com/citysense/mobility/`
  - Emergency route API (`POST /api/emergency/routes`, `POST /api/emergency/reassess`).
  - Green corridor proposal generator (signal timing windows sent to approval queue).
  - Traffic telemetry & junction status API (`/api/traffic/junctions`, `/api/traffic/rl-report`).
- **Python AI Service:**
  - `ai-service/app/cv/`: YOLOv8 lane grid-occupancy density from video frames, pushing to Spring Boot `/internal/observations`.
  - `ai-service/app/routing/`: NetworkX time-dependent road graph (arrival-time estimation, committed route hysteresis, minimum dwell time to eliminate route flutter).
  - `ai-service/app/rl/`: SUMO traffic simulator with TraCI interface; DQN signal control policy training and replay vs. fixed-time baseline.
- **Mobile UI:** `mobile/app/(tabs)/alerts.tsx`
  - **Alerts / Crew Mode Tab**: emergency vehicle crew view (active route polyline, predicted segment ETAs, reroute rationale badges), citizen "Clear the Lane" green corridor alerts.
- **Dashboard UI:** `dashboard/src/features/mobility/`
  - Traffic & Mobility panel (YOLO camera feeds with density grid overlay, junction signal states, DQN vs. fixed-time delay charts).
- **Resume Highlight:** *Computer Vision Traffic Telemetry (YOLOv8) + Reinforcement Learning Traffic Optimization (SUMO + DQN) + Hysteresis-Stabilized Emergency Routing.*

---

## 📂 Repository Layout

```text
CitySense/
├── README.md                           # Team onboarding & project architecture
├── plan.md                             # 14-day master engineering plan
├── docker-compose.yml                  # Local development orchestration
├── .env.example                        # Required environment variables
│
├── contracts/                          # Contract-first OpenAPI specs & schemas
│   └── openapi-public.yaml             # Spring Boot public API spec
│
├── core/                               # [Member A] Spring Boot 3 Core Backend (Java 21)
│   ├── pom.xml                         # Maven dependencies & plugins
│   ├── src/main/java/com/citysense/
│   │   ├── platform/                   # Core platform, auth, coordinator, audit, WebSocket STOMP
│   │   └── common/                     # Security, exceptions, configuration
│   └── src/main/resources/
│       ├── application.yml
│       └── db/migration/               # Flyway SQL migrations (V1__platform.sql)
│
├── db/                                 # [Member A] PostGIS database Dockerfile & seed
│   ├── Dockerfile
│   └── seed/dev_seed.sql
│
├── agent_service/                      # [Member B] Multilingual AI Agent & RAG Service (Python 3.11)
│   ├── src/                            # FastAPI app, RAG pgvector pipeline, Sarvam STT/TTS
│   ├── scripts/                        # Seed, bootstrap & provider verification
│   └── eval/                           # RAG evaluation benchmark
│
├── complaint_module/                   # [Member C] Civic Services & Escalation Engine (Python 3.11)
│   ├── app/                            # FastAPI, LangGraph StateGraph, LLM router & coordinator
│   ├── data/                           # Authorities JSON, citizen profile, workers matrix
│   └── test_pipeline.py                # Automated verification suite
│
├── emergency_routing/                  # [Member D] Intelligent Mobility & Emergency Routing (Python 3.11)
│   ├── models/                         # YOLOv8 accident & feud CV detectors, vision pipeline
│   ├── routing/                        # NetworkX arrival-time graph & dwell-time hysteresis
│   └── agents/                         # LangGraph emergency & ambulance dispatch agents
│
├── dashboard/                          # React + Vite operations dashboard (live twin, RL Policy Lab, agents, services)
├── city_sim/                           # LangGraph people-cluster agents on local Gemma -> car clusters in the twin
├── residuals/                          # Retired single-file UI.html pages (reference only)
│
└── docs/                               # Architecture blueprints, member guides & slide decks
    ├── MEMBER_A_PLATFORM.md            # Member A verification and platform report
    └── MembersTask.md                  # Team role assignments and task breakdown

```

---

## 🖥️ Operations dashboard & digital twin

`dashboard/` (React + Vite, built from `docs/dashboard.jpeg`) shows everything happening in the simulated city:

* **Digital twin + RL:** the CTM corridor from the sibling repo `../CITY SENSE RL` runs live (`scripts/serve_twin.py`, port 8003). A Double DQN learns online and drives the signals, while fixed-time, longest-queue and max-pressure run in lockstep on identical demand. Every signal decision is logged with explore / exploit / shield mode, Q-values and feature attributions. See `CITY SENSE RL/docs/live_twin.md`.
* **Population agents:** `city_sim/` (port 8004) runs one LangGraph agent per people cluster on local Gemma-4-E2B (llama-server, port 8090). The agents choose categorical travel plans; code turns those plans into car clusters that drive through the twin and wait at the RL-controlled signals.
* **City services:** complaints (TownHall), emergency missions (Tickets) and voice-agent events (Messages).

```bash
./run_backends.sh start     # agent 8000, complaints 8001, emergency 8002, twin 8003, Gemma 8090, agents 8004, dashboard 5173
open http://localhost:5173
```

All twin numbers are simulated (CTM), not field data. The old per-service `UI.html` pages are in `residuals/`.

## 📱 Mobile app (`mobile/`)

React Native (Expo SDK 58, Expo Router, MapLibre) citizen app built from `UI.jpeg` and `assets/`: onboarding → sign up / login → email OTP → Explore map of city-service avatars (geofence, search, chat) plus Townhall (complaints), Saved, Updates (live STOMP) and Settings. It talks **only** to core; maps, geocoding and routing are proxied by core's `/api/geo/*`. Build an APK with `cd mobile && npm run build:apk` — see [mobile/README.md](mobile/README.md).

---

## ⚡ Ground Rules & Collaboration Protocol

1. **Contracts Before Code:** Spring Boot is the single public gateway. All frontend clients use types generated from `openapi-public.yaml`. Spring calls Python via types from `openapi-internal.yaml`.
2. **Flyway Migrations:** Member A owns `V1__platform.sql`. Each teammate adds their modular migration (`V2__agent.sql`, `V3__civic.sql`, `V4__mobility.sql`).
3. **Hard Gate (Day 4):** Member A delivers the Spring Boot spine with database, auth, and STOMP event bus. Teammates must connect their stubs and UI to this spine by Day 4.
4. **Resilience & Demo Mode:** Every external dependency (Sarvam, LLM, YOLO video, SUMO) must have a cached/fallback adapter. `DEMO_MODE=1` must execute the entire 5-minute demo cleanly without internet access.

---

## 🚀 Quick Start (Development)

### 1. Prerequisites
- **Java 21 (JDK)** & **Maven 3.9+**
- **Python 3.11+** & `pip`
- **Node.js 20+** & `npm` / `pnpm`
- **Docker & Docker Compose**

### 2. Environment Setup
```bash
cp .env.example .env
./scripts/gen-secrets.sh .env   # strong DB password + JWT secret
# Edit .env: SARVAM_API_KEY (speech), GROQ_API_KEY (LLM), optional SMTP
```

### 3. Launch Services with Docker Compose
```bash
docker compose up -d postgres-postgis   # database only (run core / Python services locally)
docker compose up -d --build            # full stack behind Caddy on :80 (see docs/DEPLOYMENT.md)
./run_backends.sh start                 # Python services (8000/8001/8002) from the local .venv
```

Production deployment, public routes, the end-to-end voice → plan → action flow and known limits:
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

For complete technical specifications, API contracts, entity schemas, and day-by-day schedules, refer to [plan.md](plan.md).
# dump2
