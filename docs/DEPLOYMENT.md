# Deploying CitySense

One `docker compose` stack runs every backend behind a Caddy reverse proxy.

| Service | Port | Image source | Role |
|---|---|---|---|
| `postgres-postgis` | 5432 (loopback only) | `db/` | PostgreSQL 16 + PostGIS + pgvector |
| `core` | 8080 | `core/` | Spring Boot gateway: auth/JWT, geo, avatars, complaints, live events. Proxies avatar chat to the agent |
| `agent-service` | 8000 | `agent_service/` | Main voice agent: guardrails → planner → specialist sub-agents; Sarvam STT/TTS |
| `complaint-module` | 8001 | `complaint_module/` | LangGraph complaint lifecycle: worker assignment, SLA escalation ladder |
| `emergency-routing` | 8002 | `emergency_routing/` | LangGraph emergency dispatch, green-wave corridors, CCTV vision triage |
| `reverse-proxy` | 80 / 443 | `caddy:2.8-alpine` | Public entrypoint, automatic HTTPS |

## 1. First deploy (about 15 minutes on a 2 vCPU / 4 GB VM)

```bash
git clone https://github.com/Adityakeerti/CitySense.git && cd CitySense
git clone https://github.com/Adityakeerti/govt_website.git ../govt_portal   # citizen portal served at /
cp .env.example .env
./scripts/gen-secrets.sh .env           # strong POSTGRES_PASSWORD / JWT_SECRET / INTERNAL_API_KEY
$EDITOR .env                            # SARVAM_API_KEY, GROQ_API_KEY, SITE_ADDRESS, SMTP
docker compose up -d --build
docker compose ps                       # wait until agent-service is "healthy" (~2 min: embeds the corpus on first boot)
```

`SITE_ADDRESS=citysense.example.com` (with DNS pointing at the VM and ports 80 and 443 open) makes Caddy
fetch and renew the TLS certificate automatically. With `SITE_ADDRESS=:80` the stack serves plain HTTP.

## 2. Public routes

| Path | Goes to | Notes |
|---|---|---|
| `/api/agent/*` | agent-service | chat, `voice` (STT), `tts`, `tts/clips`, `actions/{token}/confirm`, `preferences/audio`, `tools` |
| `/agent/ui`, `/agent/health`, `/agent/ready` | agent-service | landing page and probes (prefix stripped) |
| `/api/complaint-flow/*` | complaint-module | `/api/complaint-flow/feed` → `/api/feed` |
| `/api/emergency/*` | emergency-routing | `/api/emergency/dispatch` → `/api/dispatch` |
| `/api/*`, `/ws`, `/avatars/*`, `/swagger-ui.html` | core | |
| `/` | static portal | `PORTAL_DIR` |

The mobile app needs only one URL: set `EXPO_PUBLIC_API_BASE_URL=https://citysense.example.com` and rebuild.
In local development it can point straight at core (`:8080`). Core forwards `/api/agent/voice`, `tts`,
`tts/clips`, `actions/*` and `preferences/audio` to the agent, so every feature works either way.

## 3. The intended flow end to end

1. The citizen taps the mic in an avatar chat. `POST /api/agent/voice` transcribes with Sarvam `saaras:v3`, falling back to Groq Whisper.
2. `POST /api/avatars/{id}/chat` reaches core. Core forwards to `agent-service /api/agent/chat` with the citizen's own JWT (shared `JWT_SECRET`), plus GPS when available.
3. The main voice agent runs the input guardrail and scope classifier. `VoiceAgentPlanner` then builds the plan, e.g. `[main: resolve location] → [emergency: dispatch + corridor + signal pre-emption] → [complaint: draft]`.
4. Each step runs under exactly one owner (`tool_registry.TOOL_OWNERS`; `call_tool` rejects any other caller):
   - Emergency specialist: `POST emergency-routing /api/dispatch`, `/api/corridor`, `/api/signals/override`.
   - Complaint specialist: drafts a complaint and returns a confirm token. On **Confirm**, `POST complaint-module /api/complaints` assigns a worker and starts the SLA ladder. Escalate and reassign use `/escalate-tick` and `/reassign`.
   - City Pulse: alerts, events (core `/api/city-events`), traffic, weather/inundation (emergency-routing → Open-Meteo), AQI (Open-Meteo).
5. The response carries `answer`, `plan[]`, `toolCalls[]`, `pendingAction` and `actionData`. The app plays the reply through `POST /api/agent/tts/clips` (Sarvam `bulbul:v3`) unless the speaker toggle is muted. The mute choice is stored on the device and in `PUT /api/agent/preferences/audio`.

## 4. Operations

```bash
docker compose logs -f agent-service core        # JSON logs with request ids
docker compose exec agent-service python -m scripts.seed   # re-ingest the verified corpus
docker compose up -d --build agent-service       # redeploy one service
docker compose exec postgres-postgis pg_dump -U citysense citysense > backup.sql
```

Health checks: core `GET /actuator/health`, agent `GET /ready` (database plus embedder), complaint-module
`GET /api/simulation/status`, emergency-routing `GET /api/health`.

## 5. Known limits (read before going live)

- **Simulated field systems.** Emergency dispatch, signal pre-emption and hospital capacity run on emergency_routing's synthetic demo network. Every response is labelled `"network": "demo-synthetic"`, and the citizen is told to also call 112. Connecting a real 108/112 CAD or SCATS controller is integration work that has not been done.
- **Complaint module persistence.** Complaints are stored in a JSON file on the `complaint-state` volume. That is fine for a single instance, but it is not a database. Core's PostGIS complaints are a separate system of record.
- **Process-local state.** TTS clips, audio preferences, officer handoffs and the agent's offline pending actions are kept in memory. Run one agent replica, or move them to Postgres/Redis before scaling out.
- **Dashboard tokens.** The React dashboard's Messages page gets its token from `/api/auth/dev-token`, which only exists when `AGENT_DEMO_MODE=1`. That endpoint mints arbitrary identities, so never enable it on a public host.
- **Database migrations.** Core (Flyway) owns schema `public`. The agent (Alembic) owns schemas `ai` and `agent`, with its version table in `agent` (`ALEMBIC_VERSION_SCHEMA`). Existing dev databases that already track Alembic in `public` should leave that variable unset.
