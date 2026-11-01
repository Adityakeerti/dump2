# CitySense Civic Complaint & Automated Escalation Module (Member C)

**Lead Engineer:** Member C — Civic Services & Automated Departmental Escalation  
**Module Directory:** `complaint_module/`  
**Framework:** LangGraph (`langgraph.graph.StateGraph`) + FastAPI + Pydantic  
**Integration Status:** Standalone Python Prototype with Spring Boot Feed API Contract (`com.citysense.civic`)

---

## 1. LangGraph StateGraph Architecture

The entire grievance lifecycle is executed through a compiled **LangGraph `StateGraph`** ([`app/graph.py`](file:///home/aditya/Desktop/STUDY/SmartCity/complaint_module/app/graph.py)):

```
                     ┌───────────────────────┐
                     │         START         │
                     └───────────┬───────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │ (action: INTAKE)    │ (action: ESCALATE)  │ (action: RESOLVE)
           ▼                     │                     ▼
┌───────────────────────┐        │           ┌────────────────────────┐
│ node_intake_classifier│        │           │ node_resolution_handler│
│   (LLM Routing)       │        │           └───────────┬────────────┘
└──────────┬────────────┘        │                       ▼
           ▼                     │           ┌────────────────────────┐
┌───────────────────────┐        │           │  node_citizen_notifier │
│ node_worker_dispatcher│        │           │     (LLM Message)      │
└──────────┬────────────┘        │           └───────────┬────────────┘
           │                     │                       │
           │                     ▼                       │
           │          ┌──────────────────────┐           │
           │          │ [SLA Warning Phase?] │           │
           │          └──┬────────────────┬──┘           │
           │             │ (warnings 1-5) │ (breached)   │
           │             ▼                ▼              │
           │  ┌────────────────────┐ ┌───────────────────┐│
           │  │ node_sla_governor  │ │node_authority_    ││
           │  │                    │ │escalator (Memo)   ││
           │  └──────────┬─────────┘ └────────┬──────────┘│
           │             │                    │           │
           └─────────────┴──────────┬─────────┴───────────┘
                                    ▼
                                   END
```

### LangGraph Nodes
1. **`node_intake_classifier`:** Parses citizen natural language using LLM (Groq / Gemini) to auto-detect category, department, and priority.
2. **`node_worker_dispatcher`:** Assigns matching field crew from `data/workers.json` and updates status to `WORKER_ASSIGNED`.
3. **`node_sla_governor`:** Computes SLA consumption and issues sequential warnings 1 through 5.
4. **`node_authority_escalator`:** Auto-escalates unresolved tickets along the bureaucratic ladder (Ward Officer ➔ Municipal Commissioner ➔ CM Portal) with official LLM-drafted memos.
5. **`node_resolution_handler`:** Records on-site worker notes and transitions status to `RESOLVED`.
6. **`node_citizen_notifier`:** Uses LLM to draft an official citizen resolution dispatch to Aditya Sharma.

```
[ Citizen (Aditya Sharma) ]
         │
         │ 1. Uploads photo + Geo-tagged Civic Issue
         ▼
[ Municipal Intake Agent (AI) ]
         │
         │ 2. Analyzes severity, category & assigns Field Worker
         ▼
[ Worker Assigned ] ───────► (Worker can resolve on-site at any stage)
         │
         │ 3. Handoff to Municipal Coordinator Agent
         ▼
[ Municipal Coordinator Agent ]
         │
         ├──► SLA Check ──► Warning 1 (20% SLA)
         ├──► SLA Check ──► Warning 2 (40% SLA)
         ├──► SLA Check ──► Warning 3 (60% SLA)
         ├──► SLA Check ──► Warning 4 (80% SLA)
         └──► SLA Check ──► Warning 5 (100% SLA Breached!)
                                 │
                                 ▼
                     [ Level 1: Ward Officer ] (Er. Ramesh Verma)
                                 │ (Unresolved)
                                 ▼
                     [ Level 2: Municipal Commissioner ] (Shri Alok Negi, IAS)
                                 │ (Unresolved)
                                 ▼
                     [ Level 3: CM Portal (Apex) ] (Helpline 1905 / State Urban Directorate)
```

---

## 2. Key Components

### A. Municipal Intake Agent (`app/agents.py`)
- Receives uploaded photo evidence and issue report.
- Determines severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).
- Matches issue category to specialized municipal field crews:
  - `pothole` / `road` ➔ Roads Rapid Repair Unit #3 (`Rakesh Rawat`)
  - `garbage` / `waste` ➔ Ward 14 Solid Waste & Sanitation Squad (`Sunil Kumar`)
  - `streetlight` / `electric` ➔ Civic Streetlighting & Electrical Crew B (`Manoj Bhatt`)
  - `drainage` / `flood` ➔ Monsoon Drainage Taskforce (`Vipin Joshi`)
- Assigns worker, transitions state to `WORKER_ASSIGNED`, and registers the ticket with the Municipal Coordinator Agent.

### B. Municipal Coordinator Agent (`app/agents.py`)
- Continuously monitors active tickets against configured SLA timers (`ESCALATION_TICK_SECONDS`).
- Automated multi-tier escalation ladder:
  1. `WARNING_1` to `WARNING_5`: Progressive worker reminders and SLA countdown.
  2. `ESCALATED_WARD_OFFICER`: Escalates to Ward 14 Executive Officer.
  3. `ESCALATED_MUNICIPAL_COMMISSIONER`: Escalates to Municipal Commissioner.
  4. `ESCALATED_CM_PORTAL`: Escalates to the State Chief Minister Urban Grievance Redressal Cell.
- Automatically handles resolution verification when worker completes work.

### C. Simulated JSON Profiles (`data/`)
- **Higher Authorities (`data/authorities.json`):**
  - Level 1: `Er. Ramesh Verma` (Ward Executive Officer, Ward 14)
  - Level 2: `Shri Alok Negi, IAS` (Municipal Commissioner, DMC)
  - Level 3: `CM Grievance Redressal Cell` (State Public Grievances & Principal Secretary Urban Development)
- **Single Citizen Account (`data/users.json`):**
  - Name: `Aditya Sharma`
  - Citizen ID: `CIT-2026-8921`
  - Ward: `Ward 14 - Rajpur Road`

### D. Spring Boot Feed API (`GET /api/feed`)
Serves normalized JSON feed ready for future Spring Boot backend ingestion (`com.citysense.civic` module):
```json
{
  "service": "CitySense Civic Complaint Subsystem (Member C)",
  "feed_timestamp": "2026-10-30T...",
  "target_springboot_module": "com.citysense.civic",
  "spring_sync_ready": true,
  "summary": {
    "total_complaints": 1,
    "active_unresolved": 1,
    "resolved": 0
  },
  "complaints": [
    {
      "trackingId": "CMP-2026-F112F3",
      "title": "Severe road cavity on Rajpur Road",
      "category": "pothole",
      "status": "ESCALATED_WARD_OFFICER",
      "warningsCount": 5,
      "assignedWorker": { ... },
      "currentAuthority": { ... },
      "citizen": { ... },
      "timeline": [ ... ]
    }
  ]
}
```

### D2. Govt portal & mobile app integration (no database)
This module is the shared, JSON-backed hub between the citizen mobile app and the state govt portal (`govt_portal/`, static site):

| Endpoint | Used by | Purpose |
| :--- | :--- | :--- |
| `GET /api/complaints`, `GET /api/complaints/{id}` | mobile app, govt portal | Complaints filed from the app (form + voice agent) |
| `POST /api/complaints` (multipart) | mobile app, govt portal | File as the demo citizen; intake agent assigns dept + priority |
| `POST /api/complaints/{id}/escalate-tick`, `/resolve` | govt portal | Officer actions |
| `GET /api/meta` | mobile app, govt portal | Escalation ladder: `statuses[i]` is level `i` |
| `GET /api/notices?limit=&include_expired=` | mobile app feed, govt portal | Notices, newest first; expired ones hidden by default |
| `POST /api/notices`, `DELETE /api/notices/{id}` | govt portal | Publish / revoke a notice |

Notices are stored in `$COMPLAINT_STATE_DIR/notices.json` (default `data/`). Publishing has **no authentication yet** (demo only): anyone who can reach port 8001 can publish or revoke a notice. Add publisher auth before exposing this beyond a trusted network.

### E. Interactive Blue & White UI (retired: now `residuals/complaint_module.UI.html`; use the React dashboard's TownHall page)
- Simple, clean municipal blue (`#1d4ed8`) and white theme (not vibecoded).
- **Features:**
  - Photo upload with live preview and quick sample buttons.
  - Interactive Escalation Ladder with animated stepper and radar pulse on the active node.
  - Real-time SLA tick and speed adjuster (2s, 5s).
  - Higher Authorities Desks showing live escalated cases.
  - Spring Boot Feed API JSON viewer with auto-refresh.
  - One-click "Simulate Worker Resolution" modal.

---

## 3. How to Run

### Quick Start
```bash
cd complaint_module
./run.sh
```

### Manual Execution with venv
```bash
cd complaint_module
~/.local/bin/uv venv --python /home/aditya/.local/bin/python3.11 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **`http://localhost:8000`**

---

## 4. Running Verification Tests

```bash
cd complaint_module
.venv/bin/python test_pipeline.py
```
Outputs 7/7 passing unit and integration tests verifying all 6 stages of the contract.
