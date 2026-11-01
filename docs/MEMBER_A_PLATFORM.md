# Member A — Platform & Governance: Implementation Report

**Module:** M1 Platform & Governance (Spring Boot `com.citysense.platform` + PostgreSQL baseline)
**Status:** Backend spine complete and verified end-to-end. It meets the plan's "Day 4 hard gate" (database, auth, STOMP event bus).
**Date:** 2026-10-30

---

## 1. Summary

The table below lists the README's Member A backend items and their status.

| Requirement (README / plan.md) | Status | Where |
|---|---|---|
| JWT authentication & RBAC (Citizen, Admin, Crew) | Done | `platform/auth/` |
| Observation ingestion: `POST /api/events`, `POST /internal/observations` | Done | `platform/observation/` |
| Correlation engine: cluster observations into incidents, rank urgency | Done | `platform/incident/CorrelationEngine.java` |
| Coordinator rules → `AgentAction` proposals | Done | `platform/incident/CoordinatorRules.java` |
| Human-in-the-loop approval state machine (`/api/actions`) | Done | `platform/action/` |
| Append-only `AuditLog` (`/api/audit`) | Done (enforced in app **and** DB) | `platform/audit/`, `V1__platform.sql` |
| Real-time WebSocket/STOMP (`/ws`, `/topic/city-events`) | Done | `platform/realtime/` |
| Scenario injection backend (rain, flood, crash, congestion) | Done | `platform/scenario/` |
| Live map data (`GET /api/map/features`) | Done | `platform/map/` |
| Flyway baseline `V1__platform.sql` (PostgreSQL + PostGIS + pgvector) | Done | `core/src/main/resources/db/migration/` |
| Docker Compose, `.env.example` | Done | repo root |
| Public OpenAPI contract baseline | Done (exported from running app) | `contracts/openapi-public.yaml` |

Out of scope for this pass: Member A's **frontend** work (dashboard map, approval queue UI, mobile shell). This report covers only the backend and the database.

---

## 2. Architecture

```text
 Mobile / Dashboard ──REST (JWT)──┐          ┌── STOMP /ws  →  /topic/city-events
                                  ▼          │
 ai-service ──REST (X-Internal-Key)──►  Spring Boot core (platform module)
                                          │
   ObservationService.ingest()            │
     1. save Observation                  │
     2. CorrelationEngine.correlate()  ── PostGIS ST_DWithin (radius + time window)
          ├─ create or merge Incident, recompute severity / urgency
          └─ CoordinatorRules.evaluate() → AgentActionService.proposeOnce()
                 LOW risk  → AUTO_EXECUTED
                 MED/HIGH  → PENDING (admin approve / reject)
     3. AuditService.record()   (same transaction)
     4. publish CityEventMessage → broadcast AFTER COMMIT
                                          │
                                PostgreSQL 16 + PostGIS 3.4 + pgvector
```

### Package layout

```text
core/src/main/java/com/citysense/
├── CitySenseApplication.java
├── common/
│   ├── config/   CitySenseProperties (typed config), OpenApiConfig
│   └── error/    ApiException, GlobalExceptionHandler (RFC 7807 problem responses)
└── platform/
    ├── auth/         User, Role, JwtService, JwtAuthFilter, InternalApiKeyFilter,
    │                 SecurityConfig, AuthService/Controller, DevUserSeeder
    ├── observation/  Observation, ObservationType/Status, service, public + internal controllers
    ├── incident/     Incident, CorrelationEngine, CoordinatorRules, service, controller
    ├── action/       AgentAction, ActionType, RiskLevel, ApprovalStatus, service, controllers
    ├── audit/        AuditLog, AuditService, AuditController
    ├── realtime/     WebSocketConfig, CityEventMessage, CityEventBroadcaster
    ├── scenario/     Scenario (demo definitions), ScenarioController
    └── map/          MapController (GeoJSON)
```

### Tech stack

Java 21, Spring Boot 3.3.5, Spring Security, Spring Data JPA (Hibernate 6), Spring WebSocket (STOMP), Flyway, jjwt 0.12.6, springdoc-openapi 2.6.0, PostgreSQL 16 + PostGIS 3.4 + pgvector 0.8.

---

## 3. Database (PostgreSQL)

**Migration:** `core/src/main/resources/db/migration/V1__platform.sql`. Flyway owns the schema, and Hibernate runs with `ddl-auto: validate`: it only checks that the entities match the schema and never changes it.

**Extensions and schemas:** `postgis`, `vector` (for Member B), `pgcrypto` (`gen_random_uuid()`), and schema `ai` (reserved for the RAG tables).

| Table | Purpose | Notable columns / constraints |
|---|---|---|
| `users` | Accounts | `email` UNIQUE, `password_hash` (BCrypt), `role` CHECK IN (CITIZEN, ADMIN, CREW), `language` |
| `observations` | The single event model | `type` CHECK (cv_density, complaint, flood, crash, event, agent_finding, rain, congestion), `latitude`/`longitude`, **generated** `geom geography(Point,4326)`, `confidence` 0–1, `status` (UNVERIFIED, VERIFIED, SIMULATED, PREDICTED, STALE), `payload JSONB`, `incident_id` FK |
| `incidents` | Correlated clusters | `severity` 1–5, `urgency_score`, generated `geom`, `status` (OPEN, ACKNOWLEDGED, RESOLVED), `observation_count` |
| `agent_actions` | Approval queue | `action_type`, `risk_level` (LOW/MEDIUM/HIGH), `approval_status` (PENDING/APPROVED/REJECTED/AUTO_EXECUTED), `decided_by` FK users, `decision_reason`, `version` (optimistic lock) |
| `audit_log` | Governance trail | `actor`, `action`, `entity_type`/`entity_id`, `outcome`, `evidence JSONB` |

**Indexes:** GIST on both `geom` columns (spatial search); B-tree on `(status, updated_at)`, `observed_at`, `incident_id`, `type`, `(approval_status, created_at)` and `(entity_type, entity_id)`.

**Key design choices**
- **Generated `geom` column.** The app writes plain `latitude`/`longitude`, and PostgreSQL computes the PostGIS point. This avoids Hibernate Spatial and JTS mapping in Java while keeping spatial indexes and `ST_DWithin` queries. The point can't drift out of sync with the coordinates.
- **Append-only audit enforced in the database.** A trigger (`audit_log_no_update_delete`, plus `audit_log_no_truncate`) raises `audit_log is append-only`. This holds even if someone bypasses the app with `psql`. In Java the entity is also `@Immutable`, and its repository exposes no delete or update methods.
- **CHECK constraints** on all enum-like columns, so bad data is rejected even when it doesn't come through the API.

**Image:** `db/Dockerfile` extends `postgis/postgis:16-3.4` and installs `postgresql-16-pgvector`. Debian bullseye's PGDG repo has moved to `apt-archive.postgresql.org`, so the Dockerfile repoints it first. **Seed data:** `db/seed/dev_seed.sql` holds 5 observations around Dehradun Clock Tower for manual testing. It is not a migration.

---

## 4. API reference

All responses are JSON. Errors use RFC 7807 `ProblemDetail` (`{status, title, detail}`; validation errors add `fields`).
Live docs: `http://localhost:8080/swagger-ui.html` · Contract: `contracts/openapi-public.yaml`.

### 4.1 Auth

| Method & path | Access | Notes |
|---|---|---|
| `POST /api/auth/register` | Public | `{email, password(8–72), fullName, language?}` → 201 + token. Always creates a **CITIZEN**. |
| `POST /api/auth/login` | Public | `{email, password}` → `{accessToken, tokenType, expiresIn, user}` |
| `GET /api/auth/me` | Any logged-in user | Current user profile |

```bash
curl -s -XPOST localhost:8080/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@citysense.dev","password":"citysense123"}'
```

### 4.2 Observations (ingestion)

| Method & path | Access | Notes |
|---|---|---|
| `POST /api/events` | ADMIN, CREW | Inject an observation |
| `GET /api/events?type=&limit=` | Any logged-in user | Most recent observations |
| `POST /internal/observations` | ai-service (`X-Internal-Key` header) | Same body. Used by Python (e.g. YOLO `cv_density`) |

Request body (only `type`, `latitude`, `longitude` are required):

```json
{
  "type": "flood",
  "latitude": 30.3255, "longitude": 78.0430,
  "observedAt": "2026-10-30T10:00:00Z",
  "source": "crew-app", "confidence": 0.85, "status": "UNVERIFIED",
  "payload": { "locationName": "Clock Tower underpass", "water_depth_cm": 45 }
}
```

Response: `{ observation: {...}, incidentId: "uuid|null", newIncident: true|false }`.

### 4.3 Incidents

| Method & path | Access | Notes |
|---|---|---|
| `GET /api/incidents?status=` | Any logged-in user | Defaults to OPEN + ACKNOWLEDGED, **sorted by urgency** |
| `GET /api/incidents/{id}` | Any logged-in user | Incident drawer: incident + linked observations + actions |
| `PATCH /api/incidents/{id}/status` | ADMIN | `{status}`. Forward only: OPEN → ACKNOWLEDGED → RESOLVED. Going backwards → 409 |

### 4.4 Approvals (human-in-the-loop)

| Method & path | Access | Notes |
|---|---|---|
| `GET /api/actions?status=PENDING` | ADMIN | Approval queue |
| `POST /api/actions` | ADMIN | Propose an action manually |
| `POST /api/actions/{id}/approve` | ADMIN | Optional `{reason}` |
| `POST /api/actions/{id}/reject` | ADMIN | `{reason}` **required** |
| `POST /internal/actions` | ai-service | ai-service proposals enter the same queue |

### 4.5 Audit, scenarios, map

| Method & path | Access | Notes |
|---|---|---|
| `GET /api/audit?entityType=&entityId=&page=&size=` | ADMIN | Paged, newest first (max size 200) |
| `GET /api/scenarios` | ADMIN | `["rain","flood","crash","congestion"]` |
| `POST /api/scenarios/{name}` | ADMIN | Injects observations labelled **SIMULATED** |
| `GET /api/map/features` | Any logged-in user | GeoJSON `FeatureCollection` of active incidents and recent observations |

### 4.6 Real-time (STOMP)

- Endpoint: `ws://localhost:8080/ws` (plain WebSocket, for React Native and `@stomp/stompjs`). SockJS fallback: `/ws-sockjs`.
- Subscribe to `/topic/city-events`. Message envelope:

```json
{ "type": "INCIDENT_CREATED", "entityId": "uuid", "data": { ... }, "timestamp": "..." }
```

Event types: `OBSERVATION_CREATED`, `INCIDENT_CREATED`, `INCIDENT_UPDATED`, `ACTION_PENDING`, `ACTION_AUTO_EXECUTED`, `ACTION_APPROVED`, `ACTION_REJECTED`.

### 4.7 Access summary

| Role | Can do |
|---|---|
| Unauthenticated | login, register, Swagger docs, health, WebSocket connect |
| CITIZEN | read incidents, observations, map; own profile |
| CREW | the above + inject observations |
| ADMIN | everything: approvals, audit, scenarios, incident status |
| INTERNAL (ai-service key) | `/internal/**` only |

---

## 5. Core logic

### 5.1 Correlation engine (`CorrelationEngine`)

1. **Gate.** `event` observations (fun city events) and `cv_density` readings below **0.7** are stored but never create incidents. This keeps periodic camera telemetry from flooding the incident list.
2. **Find candidates.** Unresolved incidents within `CORRELATION_RADIUS_METERS` (default 500 m, using PostGIS `ST_DWithin` on geography, so distances are true meters) and updated within `CORRELATION_WINDOW_MINUTES` (default 30) of the observation. Nearest first.
3. **Merge or create.** The observation joins the nearest candidate, or a new incident is created.
4. **Score** (pure function, unit-tested):
   - **Severity (1–5)** = highest base severity among members (flood/crash 4; rain/congestion/complaint/agent_finding 2; cv_density 1, or 3 if density ≥ 0.9), **+1** if ≥ 3 observations corroborate, **+1** if ≥ 3 distinct types co-occur, capped at 5.
   - **Urgency (0–100)** = `severity×15 + maxConfidence×10 + min(count−1,5)×3 + min(distinctTypes−1,3)×5`, capped at 100.
   - The type and title come from the most severe member (e.g. "Flooding near Clock Tower").

The rules are deterministic on purpose (plan.md §8.6: *"Rules decide; the LLM only summarises"*). Every merge can be explained, reproduced and tested.

### 5.2 Coordinator rules (`CoordinatorRules`)

| Condition | Proposed action | Risk |
|---|---|---|
| Incident contains a flood | `ROAD_CLOSURE` | HIGH → queue |
| Incident contains a crash | `DISPATCH` | HIGH → queue |
| Flood and severity 5 | `EVACUATION` | HIGH → queue |
| Severity ≥ 3 | `NOTIFY_CITIZENS` | LOW → auto-executed |

The rules re-run on every new observation, but `proposeOnce` never duplicates an action type for the same incident.

### 5.3 Approval state machine (`AgentAction`)

```text
             risk LOW ─────────► AUTO_EXECUTED   (terminal)
 propose ──┤
             risk MED/HIGH ────► PENDING ──approve──► APPROVED  (terminal)
                                         └─reject───► REJECTED  (terminal, reason required)
```

- **Risk floor.** Each `ActionType` has a minimum risk. A proposer may raise it but never lower it, so an agent cannot get a green corridor or road closure auto-executed by labelling it LOW.
- **Terminal states.** Deciding an already-decided action → **409 Conflict**.
- **Concurrency.** A `@Version` optimistic lock means that if two admins click at once, one wins and the other gets 409 instead of silently overwriting.
- Every proposal and decision is written to the audit log with the decider and reason.

### 5.4 Audit & broadcast consistency

- `AuditService.record` requires an active transaction (`Propagation.MANDATORY`). The audit row commits or rolls back with the change it describes, so the log never records an action that didn't happen, or misses one that did.
- Broadcasts use `@TransactionalEventListener(AFTER_COMMIT)`, so clients never receive data that was later rolled back. Broadcasting is best-effort: if it fails, clients can still re-fetch over REST.

### 5.5 Security details

- Stateless JWT (HS256). The secret must be at least 32 bytes, otherwise startup fails. Requests are authorised from the token claims without a DB lookup.
- Login gives the same error for an unknown email and a wrong password, which prevents account enumeration.
- The internal API key is compared in constant time (`MessageDigest.isEqual`).
- Passwords are hashed with BCrypt.

---

## 6. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SPRING_DATASOURCE_URL` / `_USERNAME` / `_PASSWORD` | `jdbc:postgresql://localhost:5432/citysense`, `citysense`, `citysense` | DB connection |
| `JWT_SECRET` | dev placeholder | **Must be changed** outside local dev; ≥ 32 bytes |
| `JWT_EXPIRATION_MINUTES` | 720 | Token lifetime |
| `INTERNAL_API_KEY` | `dev-internal-key` | Shared secret for ai-service |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated origin patterns |
| `SEED_USERS` / `SEED_PASSWORD` | `true` / `citysense123` | Dev account seeding |
| `CORRELATION_RADIUS_METERS` | 500 | Spatial merge radius |
| `CORRELATION_WINDOW_MINUTES` | 30 | Temporal merge window |
| `DEMO_MODE` | 1 | Demo flag (for team-wide use) |

---

## 7. How to run

```bash
cp .env.example .env                              # optional; defaults work for local dev
docker compose up -d postgres-postgis             # database only
docker compose --profile app up -d --build        # database + core on :8080
```

No local JDK or Maven is required; the core image builds with Maven and Temurin 21.

**Seeded accounts** (password `citysense123`): `admin@citysense.dev`, `crew@citysense.dev`, `citizen@citysense.dev`.

**Run the unit tests:**

```bash
docker run --rm -v "$PWD/core":/app -v citysense-m2:/root/.m2 -w /app \
  maven:3.9-eclipse-temurin-21 mvn -B test
```

**Try the demo flow:**

```bash
TOKEN=$(curl -s -XPOST localhost:8080/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@citysense.dev","password":"citysense123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["accessToken"])')
curl -s -XPOST localhost:8080/api/scenarios/flood -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8080/api/actions?status=PENDING" -H "Authorization: Bearer $TOKEN"
```

---

## 8. Verification performed

### 8.1 Unit tests: 14 / 14 passing

| Test class | Tests | Covers |
|---|---|---|
| `CorrelationEngineTest` | 5 | Incident gating, severity escalation, urgency cap, density thresholds |
| `CoordinatorRulesTest` | 3 | Flood → closure + warning; severe flood → evacuation; low rain → nothing |
| `AgentActionTest` | 4 | Initial states, risk floor, decider recorded, terminal states |
| `JwtServiceTest` | 2 | Token round trip; forged/garbage tokens rejected |

### 8.2 Database checks (real PostGIS + pgvector container)

- The migration applies cleanly. Extensions present: postgis 3.4.3, vector 0.8.6, pgcrypto.
- `geom` fills in automatically, and writing to it directly is rejected.
- A 500 m `ST_DWithin` query around Clock Tower returned exactly the 3 expected seed rows (0 m, 221 m, 225 m).
- UPDATE, DELETE and TRUNCATE on `audit_log` all fail with `audit_log is append-only`.
- A CHECK constraint rejects `severity = 9`.

### 8.3 End-to-end against the running stack

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Incidents without a token | 401 | 401 |
| 2 | Wrong password | 401 | 401 |
| 3 | Citizen injects an observation | 403 | 403 |
| 4 | Citizen opens the approval queue | 403 | 403 |
| 5 | Internal endpoint without the key | 401 | 401 |
| 6 | Latitude 300 | 400 | 400 |
| 7 | Register a new citizen | 201 | 201 |
| 8 | Low `cv_density` (0.3) | No incident | `incidentId = null` |
| 9 | Flood scenario (rain + flood + congestion) | One merged incident | 3 observations → same incident |
| 10 | Incident score | Severity 5 | "Flooding near Clock Tower", severity 5, urgency 100 |
| 11 | Coordinator output | HIGH pending, LOW auto | EVACUATION + ROAD_CLOSURE pending; NOTIFY_CITIZENS auto-executed |
| 12–13 | Approve, then approve again | 200, then 409 | 200, 409 |
| 14–15 | Reject without a reason, then with one | 400, then 200 | 400, 200 |
| 16 | Audit trail | All steps logged with actor | Proposals, ingestion, correlation, approve and reject all present |
| 17 | Citizen reads the audit log | 403 | 403 (after fix, see §9) |
| 18 | Incident detail | 3 observations + 3 actions | Matches |
| 19 | Resolve, then reopen | 200, then 409 | 200, 409 |
| 20 | Map features | GeoJSON | `FeatureCollection` returned |
| 21 | STOMP subscriber during a crash injection | Events within 2 s (plan §13) | 4 events received in **~0.15 s** |

---

## 9. Issues found and fixed during testing

1. **403 responses showed up as 401.** A URL-level denial forwards to `/error`, and the JWT filter (a `OncePerRequestFilter`) doesn't run on error dispatches, so `/error` itself was rejected as unauthenticated. **Fix:** permit `/error` in `SecurityConfig`.
2. **Compose passed an empty JWT secret.** `${JWT_SECRET:-}` gives Spring an empty string when there is no `.env`, which overrides the YAML default and crashes startup. **Fix:** give a dev default in `docker-compose.yml`.
3. **The OpenAPI YAML export was blocked.** `/v3/api-docs.yaml` falls outside the `/v3/api-docs/**` permit. **Fix:** permit it explicitly.
4. **pgvector install failed (DB image).** The bullseye PGDG repo had moved. **Fix:** repoint it to `apt-archive.postgresql.org` in `db/Dockerfile`.

---

## 10. Integration guide for teammates

- **Migrations.** Add `V2__agent.sql` (B), `V3__civic.sql` (C) or `V4__mobility.sql` (D). **Never edit V1.** The `ai` schema and `vector` extension already exist.
- **Proposing high-impact actions** (e.g. D's green corridor). Inject `AgentActionService` and call `propose(new Proposal(...))`, or have Python call `POST /internal/actions`. Don't build a separate approval flow.
- **Auditing.** Call `AuditService.record(...)` from inside a `@Transactional` method.
- **Broadcasting.** `applicationEventPublisher.publishEvent(CityEventMessage.of("YOUR_TYPE", id, data))`. It goes out after commit.
- **Feeding the correlation engine** (e.g. C's complaints). Call `ObservationService.ingest(...)` with type `complaint`.
- **Current user** in a controller: `@AuthenticationPrincipal AuthUser user`.
- **Contract changes.** Submit a PR touching `contracts/openapi-public.yaml` (plan.md ground rule 1).

---

## 11. Known limitations & next steps

| Limitation | Impact | Suggested next step |
|---|---|---|
| The STOMP handshake is unauthenticated | Anyone can subscribe to the public topic | Add a JWT `ChannelInterceptor` on CONNECT |
| No Testcontainers integration tests yet (plan §13 asks for them) | E2E behaviour was verified manually only | Add integration tests with the `citysense-db` image for correlation and approvals |
| Incident location is fixed at the first observation | The centroid doesn't move as more reports arrive | Recompute the centroid on merge if needed |
| Approved actions are only recorded and broadcast | No simulated execution yet (signals, alerts) | Member D / mobile consume `ACTION_APPROVED` events |
| Correlation radius and weights are hand-tuned | They may over- or under-merge in other areas | Tune on scenario data; log merge decisions for review |
| The PostGIS base image is amd64-only | Runs emulated on Apple Silicon (slower) | Acceptable for the hackathon; consider a multi-arch base later |
| The urgency formula is a heuristic | Not validated against real outcomes | Present it as rule-based ranking, not a prediction |
| Scenario coordinates are approximate | Demo-only | Replace with surveyed points if accuracy matters |

---

## 12. Files added

```text
.env.example
docker-compose.yml
db/Dockerfile
db/seed/dev_seed.sql
contracts/openapi-public.yaml
docs/MEMBER_A_PLATFORM.md            (this file)
core/pom.xml
core/Dockerfile
core/README.md
core/src/main/resources/application.yml
core/src/main/resources/db/migration/V1__platform.sql
core/src/main/java/com/citysense/CitySenseApplication.java
core/src/main/java/com/citysense/common/{config,error}/        4 files
core/src/main/java/com/citysense/platform/auth/               12 files
core/src/main/java/com/citysense/platform/observation/         8 files
core/src/main/java/com/citysense/platform/incident/            8 files
core/src/main/java/com/citysense/platform/action/              9 files
core/src/main/java/com/citysense/platform/audit/               4 files
core/src/main/java/com/citysense/platform/realtime/            3 files
core/src/main/java/com/citysense/platform/scenario/            2 files
core/src/main/java/com/citysense/platform/map/                 1 file
core/src/test/java/com/citysense/platform/                     4 test classes
```
