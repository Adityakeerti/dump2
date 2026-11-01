# CitySense database

One PostgreSQL 16 instance (`postgres-postgis` in docker compose, PostGIS + pgvector) holds every
service's data. Each service owns its own schema and is the only writer to it; services talk to
each other over HTTP, never through each other's tables.

| Schema | Owner | Migrations |
|---|---|---|
| `public` | core (Spring Boot) | Flyway, `core/src/main/resources/db/migration/V*.sql` (applied on core start) |
| `ai` | core creates `ai.knowledge_chunks`; agent_service owns `ai.knowledge_document` / `ai.knowledge_chunk` | Flyway V2 + Alembic |
| `agent` | agent_service (FastAPI) | Alembic, `agent_service/alembic/versions/000*.py` (`alembic upgrade head` on container start) |
| `civic_flow` | complaint_module | `CREATE ... IF NOT EXISTS` in `complaint_module/app/pg_store.py` on start |

The emergency routing service keeps its dispatch state in memory and has no schema.

## `public` (core)

| Table | Migration | What it holds |
|---|---|---|
| `users`, `audit_log` | V1 | Accounts (password hashes, role, language) and the security audit trail |
| `incidents`, `observations`, `agent_actions` | V1 | Fused incidents and the observations behind them; proposed agent actions |
| `knowledge_docs` (+ `ai.knowledge_chunks`), `chat_sessions` | V2 | Core-side knowledge documents with pgvector chunks; chat sessions |
| `complaints`, `complaint_escalations` | V3 | Core's own complaint model (the mobile app files to complaint_module instead) |
| `city_events` | V3, extended in V7 | City events; V7 adds `venue`, `organizer`, `source_url`, `seed_key` (unique) |
| `weather_observations`, `traffic_junctions`, `route_plans` | V4 | Mobility: weather, junctions, planned routes |
| `email_otps`, `avatars`, `avatar_likes`, `avatar_saves` | V5 | OTP codes; local agents on the map (seeded from `seed/avatars.json`), likes and saves per user |
| `mesh_peers`, `mesh_messages` | V6 | Offline mesh messaging |
| `businesses` | V7 | Popular local businesses for the Townhall feed and agent recommendations |

### V7 `businesses`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `seed_key` | varchar(80) unique | Stable key from `seed/businesses.json`; re-seeding updates in place |
| `name`, `category`, `locality`, `description` | text | `category` is one of restaurant, cafe, sweets, bakery, bookstore, shopping |
| `latitude`, `longitude` | double | |
| `geom` | geography(Point) generated | GIST index; used by `ST_Distance` ordering in `/api/businesses` |
| `coords_precision` | `exact` / `approximate` (CHECK) | `approximate` = locality or junction centre |
| `source_url` | text | Where the listing came from |
| `featured`, `active` | boolean | |
| `created_at`, `updated_at` | timestamptz | |

### Seed data (core, on start)

`CityDirectorySeeder` upserts by `seed_key` from two classpath files (disable with
`citysense.directory.seed-enabled=false`):

- `seed/businesses.json`: 10 businesses, 2 to 4 per locality (Clement Town, Paltan Bazaar / Clock
  Tower, Rajpur Road / Jakhan, ISBT / Majra). Researched 2026-11-01 from public guides; every row
  cites its source. Several sources are aggregators, so confirm a place is still open before relying on it.
- `seed/events.json`: 9 real events for Nov to Dec 2026 (Virasat, Diwali, Uttarakhand Foundation Day,
  Igas Bagwal, Guru Nanak Jayanti, Dehradun Literature Festival, Kavishala meetup, Mussoorie Ultra,
  Christmas), each with a source URL. Times are set to 10:00 to 20:00 IST because the sources give
  dates only. The Igas date varies between sources (19 or 20 Nov); its description says so.

## `agent` and `ai` (agent_service)

| Table | Migration | What it holds |
|---|---|---|
| `ai.knowledge_document`, `ai.knowledge_chunk` | 0001 | RAG corpus; chunks carry 384-d E5 embeddings (pgvector) |
| `agent.agent_config` | 0001, constraints in 0002 | Personas: tier, system prompt, tenants, tools |
| `agent.chat_session`, `agent.chat_message`, `agent.message_source` | 0001 | Conversations with the main and local agents, with cited sources |
| `agent.pending_action` | 0001, hardened in 0002 | Drafted actions (e.g. a complaint) awaiting the citizen's confirm; args are integrity-hashed |
| `agent.audit_log` | 0001 | Tool calls and decisions |
| `agent.answer_cache` | 0001, constraints in 0002 | Cached grounded answers |
| `agent.media` | 0003 | Photos attached to a pending action (bytea, at most 10 MB, JPEG/PNG/WebP/HEIC by magic bytes), linked by `action_token`, owned by `user_id` |

Photo flow from a chat: the agent drafts a complaint, `photoSuggested` is set for issues a crew
needs to see (sewage, garbage, potholes...), the app takes a camera photo and uploads it to
`POST /api/agent/actions/{token}/photo` (stored in `agent.media`). On confirm the photo travels with
the complaint to complaint_module, which stores it in `civic_flow.photos`.

## `civic_flow` (complaint_module)

Enabled when `COMPLAINT_DATABASE_URL` is set (docker compose sets it). Without it the module uses its
JSON files, as in local development and tests. On first start an empty table is filled from the
existing JSON files.

| Table | Columns | Notes |
|---|---|---|
| `complaints` | `tracking_id` PK, `status`, `created_at`, `updated_at`, `data` jsonb | Full complaint document in `data`; status and time promoted for queries |
| `notices` | `id` PK, `publish_date`, `expiry_date`, `pinned`, `data` jsonb | Government notices published from the portal |
| `photos` | `name` PK, `content_type`, `size_bytes` (1 B to 10 MB), `data` bytea, `created_at` | Complaint evidence, served at `GET /api/photos/{name}` (public path `/api/complaint-flow/api/photos/{name}`) |

Photos filed from the manual "Report an issue" form go straight to `civic_flow.photos`.

## Backups

```bash
docker compose exec postgres-postgis pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > citysense-$(date +%F).dump
docker compose exec -T postgres-postgis pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean < citysense-YYYY-MM-DD.dump
```

Photos are stored in the database, so a dump includes them.
