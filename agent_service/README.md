# City Sense AI service

Standalone Python **3.11.9**, FastAPI, SQLModel + async SQLAlchemy/asyncpg, PostgreSQL + pgvector. Public DTOs follow `architecture.md` section 6. This service owns only `ai` and `agent` schemas; it does not own platform users, traffic controls, or civic complaint tables.

## Start locally (PowerShell, from Avatar)

The `.venv` has already been created in this workspace. Always use its interpreter.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv\Scripts\python.exe -m scripts.bootstrap
docker compose up -d db
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.seed
.\.venv\Scripts\python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

`scripts.bootstrap` preserves an existing `.env` and generates a random JWT secret for a new one. `.env` is ignored by Git and Docker build context. Set `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL` for your inference server. Optional Groq/Sarvam keys enable their adapters; provider order is configurable. Sarvam's documented chat endpoint and model IDs changed from the original proposal; see `docs/verification.md`.

The first normal startup downloads `intfloat/multilingual-e5-small`. Warm/cache it before going offline. If loading fails, `/ready` stays 503; there is no silent change of embedding model. Reindex documents after deliberately switching embedding backends.

For a complete Docker deployment:

```powershell
docker compose up --build -d
docker compose exec api python -m scripts.seed
```

Inside Docker, point host inference URLs at `http://host.docker.internal:8080/v1`, not `localhost`. Compose overrides DATABASE_URL to reach `db`. Uploads and model cache use persistent volumes. One API process is intentional: in-memory request limits/provider circuits are process-local.

## Authentication

Every application route requires `Authorization: Bearer <JWT>` except `/health`, `/ready`, and the demo-token helper. Verify HS256 using `JWT_SECRET`; required claims are `sub`, `iat`, and `exp`. Optional `JWT_ISSUER`/`JWT_AUDIENCE` are enforced when configured. The main platform supplies tokens in normal mode. Admin routes require role `admin` or `service`.

With `DEMO_MODE=1`, `POST /api/auth/dev-token` accepts `{"user_id":"demo","role":"admin"}` and returns a token. This unauthenticated helper is for local demonstrations only; it returns 404 in normal mode. `GET /api/auth/me` shows the verified identity.

## API

Interactive schemas and multipart forms: `http://localhost:8000/docs`. OpenAPI: `/openapi.json`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agent/chat` | Text turn; JSON or SSE via Accept header |
| POST | `/api/agent/voice` | Multipart `file`, optional `language` (`en`/`hi`); transcript only |
| GET | `/api/agent/personas` | Active personas |
| POST / GET | `/api/agent/sessions` | Create/list own sessions |
| GET | `/api/agent/sessions/{session_id}/messages` | Own paginated history |
| POST | `/api/agent/actions/{token}/confirm` | Atomically claim and execute a proposed complaint |
| POST | `/api/agent/actions/{token}/cancel` | Cancel a pending complaint |
| GET | `/api/agent/actions/{token}` | Read own action receipt/state after a lost response |
| POST / GET | `/api/knowledge/docs` | Admin upload/list |
| GET | `/api/knowledge/docs/{doc_id}` | Admin document/indexing status |
| POST | `/api/knowledge/docs/{doc_id}/verify` | Admin verification/rejection |
| POST | `/api/knowledge/docs/{doc_id}/reindex` | Reprocess stored source |
| POST | `/api/admin/personas/{agent_id}` | Configure persona scopes, prompt, tools, threshold |
| GET | `/api/admin/stats` | Turn counts, status rates, provider share, sampled latency |

Chat request:

```json
{"sessionId":null,"requestId":"c0dca9b2-e13a-41b9-9148-2f25a7b5f956","agentId":"general","message":"Which documents do I need?","language":"en","context":{"cityId":"dehradun"}}
```

Reuse `requestId` **only for an identical retry**. Reusing it with another payload returns 409. Another user's request ID cannot disclose its stored response. Sessions are ownership-filtered. `user_id` and tenant scope are not accepted from clients. Chat messages are capped at 4000 characters. Unknown request fields are rejected.

Responses include `sessionId`, `messageId`, `status`, `answer`, `agent:{id,name}`, `sources:[]`, nullable `cta`, `handoff`, `pendingAction`, and `served`. Unsupported evidence returns `ABSTAINED` with `cta:"file_complaint"` and **zero model calls**. Sources and relational citation links are created exclusively from validated hits.

SSE emits `data: {"t":"token","v":"..."}` then `data: {"t":"final", ...response}`. The current transport buffers generation before emitting; it does not expose unvalidated partial provider tokens. Retrying after a transport disconnect returns the persisted turn.

## Knowledge setup

Upload a PDF/MD/TXT file (10 MB default) with a multipart `metadata` field containing JSON:

```json
{"tenant_id":"public","title":"Official scheme eligibility","publisher":"Responsible department","source_url":"https://example.gov.in/scheme.pdf","jurisdiction":"national","language":"en","expires_at":"2027-12-31T00:00:00Z"}
```

Use the actual official source URL and metadata. Uploads begin **unverified**. Poll the document until `ingestion_status=ready`, then POST `{"status":"verified"}` to its `/verify` route after human review. Verification is never inferred from a model or a domain name. Hindi documents need `language:"hi"`. Encrypted, malformed, oversized, empty/scanned-without-text PDFs fail indexing honestly. Dates require time zones. Paths are generated by the server and not accepted from upload metadata.

The seed CLI loads agents and files under `data/corpus/<tenant>/`. Existing source hashes are tenant-scoped. Seeded files remain unverified. For rich metadata, use the upload API. The initial 0.75 similarity threshold is **provisional**; calibrate it on the real corpus using the evaluation sweep and save it through the admin persona API.

Hybrid retrieval unions vector top 20 and lexical top 20, RRF k=60, and returns top 6. Tenant/verification/readiness/expiry/model filters are in SQL. The evidence validator checks jurisdiction and cosine per chunk and returns at most 4. Staleness derives from fetch age, not time until expiry.

## Tools and external platform adapters

Seeded personas: `general` (public), `municipal` (public+municipal). Additional personas are configuration rows. Authorized tools: events, alerts, complaint status, scheme search, handoff, complaint proposal, and a clarification control tool. Handoffs discard prior retrieval context and retrieve afresh under the target's server-side scope. A turn stops after 3 model steps. Local model tools are disabled by default; enable `LOCAL_TOOLS_ENABLED=1` only after its tool probe passes.

For civic integration configure **exact endpoint URLs**:

- `COMPLAINT_ADAPTER_URL`: POST accepts `{category,location,description}`, returns `{"trackingId":"..."}`. Receives `Idempotency-Key` and the JWT-derived `X-User-ID`.
- `COMPLAINT_STATUS_URL`: GET with `tracking_id` query parameter, or use a URL containing `{tracking_id}` for a path-based platform API.
- `EVENTS_URL` / `ALERTS_URL`: GET with `query` parameter.
- `ADAPTER_API_KEY`: optional bearer token for those service endpoints. The platform must authorize ownership using its service authentication and user context.

Without civic URLs the adapter returns explicitly simulated mock results, not live records. The complaint tracking ID is deterministic for its confirmation token. Confirmation uses atomic `UPDATE ... WHERE pending AND user_id AND unexpired RETURNING`, commits an `executing` claim before I/O, verifies argument hash and current allowlist, and never silently retries. Timeouts/failures are recorded as failed; abandoned executing claims expire to failed. Replays are rejected. See `docs/schemas.md` for the additive state/migration notes.

## Offline mode and voice

`DEMO_MODE=1` makes no hosted model/STT/adapter calls. It returns extractive evidence answers labelled fallback and uses keyboard dictation for voice. To exercise without a cached E5 model, explicitly set `USE_SENTENCE_TRANSFORMER=0` as well. That uses **demo hash vectors**, not multilingual semantic embeddings; reindex and never report its metrics as E5 quality. Offline model tool calls/handoff are disabled, per the architecture's local fallback restriction. TTS is on-device as specified; this backend's voice contract returns only `{text,lang}`.

Normal STT tries `STT_PROVIDER_ORDER`: local OpenAI-compatible `/audio/transcriptions`, Groq Whisper, then Sarvam. No provider available means coded 503 and keyboard dictation. Language detection is normalized to short language codes.

## Refresh, cache, and operations

Refresh is disabled until `REFRESH_ALLOWED_DOMAINS` contains exact hosts (JSON list). Only HTTPS public destinations are allowed, redirects are rejected, and downloads are capped. Changed sources are unverified again before reindex. Maintenance resumes interrupted ingestion and expires actions. It is an in-process task, consistent with the single-process/no-queue design.

Cache hits are revalidated against current evidence and keyed by persona/prompt/scopes/language/city/model/chunks **and user**, with 0.95 minimum query cosine and TTL. Tool-backed and contextual multi-turn answers are not cached. Verification/index changes invalidate cached answers. Logs avoid prompts, JWTs, provider keys, and Authorization headers.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src scripts tests eval alembic
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
.\.venv\Scripts\python.exe -m scripts.retrieval_cli "your question"
.\.venv\Scripts\python.exe -m eval.run_eval --thresholds 0.70 0.75 0.80 0.85 0.90
```

PostgreSQL integration tests require a **dedicated database ending in `_test`**:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://citysense:YOUR_ENV_PASSWORD@localhost:5432/citysense_test"
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

They apply Alembic migrations and truncate service tables in that test database. The regular suite explicitly skips them when no test DB is supplied. `eval/questions.jsonl` contains five schema examples; replace document labels and add the real evaluation set before claiming quality targets. Hosted providers may retain prompts; masking phone/email reduces exposure but is not complete anonymization. Free-tier quotas, recording quality, and hardware latency must be checked on your account/device using `docs/verification.md`.
