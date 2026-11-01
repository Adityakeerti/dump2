# City Sense Agent Service: Architecture

Scope: the conversational agent and RAG backend only. One FastAPI service, one PostgreSQL (pgvector), outbound calls to LLM/STT providers and tenant action adapters. Target: Android client (Expo), hackathon scale, zero paid dependencies.

Status: design. Items marked **(verify)** are assumptions about third-party behaviour that must be checked on day 1.

---

## 1. Governing rules

1. **Code decides, the model phrases.** Abstention, tenant scope, tool permissions, citations and action confirmation are enforced in code. The LLM never owns business logic.
2. **Abstain before generate.** If retrieval cannot support an answer, the LLM is not called.
3. **The agent proposes, the user disposes.** Side-effect tools never execute inside the agent loop. They create a pending action that the user confirms explicitly.
4. **Sources are evidence, not prose.** `sources[]` is built from retrieved chunks, never parsed from model output.
5. **Honest labelling.** Every answer carries a status. Stale, cached or fallback content is labelled as such.
6. **Every external dependency has a fallback**, and `DEMO_MODE=1` runs the full demo offline.

## 2. Decision log

| # | Decision | Reason | Revisit if |
|---|---|---|---|
| D1 | FastAPI is the only backend for this component | Team decision for this module | Team mandates a Spring gateway (see section 15) |
| D2 | Single process, no Redis, no queue | Load is under 20 concurrent users; fewer containers to fail | Sustained load or multi-worker need |
| D3 | PostgreSQL holds everything, including cache and audit | One store, one backup, one failure domain | Cache hit latency becomes a problem |
| D4 | SSE for streaming (not WebSocket) | Request-scoped, no connection state | Server-initiated push is required |
| D5 | One orchestrator, many `agent_config` rows | New business/government agent is data, not a deploy | Agents need genuinely different runtimes |
| D6 | LLM-driven handoff tool, no separate intent classifier | One fewer model call and failure point | Handoff accuracy is poor in evaluation |
| D7 | Hosted free-tier LLMs primary, local `llama.cpp` model last-resort fallback | Quality and Hindi support vs. offline resilience | Hosted quotas prove adequate |
| D8 | STT is a separate transcribe-only endpoint | Voice and text share one chat path | Streaming STT is needed |
| D9 | Hybrid retrieval (vector + full-text, rank-fused) | Scheme names and acronyms defeat pure vectors | Evaluation shows no gain |

## 3. Topology

```
Android (Expo, Ask tab)
      |  HTTPS (LAN or tunnel)
      v
+--------------------------------------------------------+
| FastAPI (uvicorn, 1 process)                           |
| middleware: request-id | JWT | per-user rate limit     |
|                                                        |
|  /api/agent/*   /api/knowledge/*   /health             |
|        |                                               |
|  Orchestrator --> Retrieval --> Evidence validator     |
|        |             (embedder in thread pool)         |
|        +--> LLM chain: Gemini -> Groq -> local llama.cpp|
|        +--> Tool registry --> Action adapters          |
|                                                        |
|  Background tasks: ingestion, source refresh           |
+---------+------------------------------+---------------+
          v                              v
   PostgreSQL + pgvector        Groq Whisper (STT)
   (single store)               Mock municipal portal
                                llama.cpp server (local)
```

## 4. Components

| Component | Responsibility | Notes |
|---|---|---|
| API layer | Auth, validation, SSE, error mapping | Pydantic models are the contract |
| Orchestrator | One turn: cache, retrieve, validate, generate, tools, persist | Parameterised by `AgentConfig` |
| Retrieval | Embed query, hybrid search, fuse, return scored hits | Tenant scope injected by server only |
| Evidence validator | Decide if hits are usable (section 8) | Pure function, unit-tested |
| LLM client | Provider chain, rate limits, failover | OpenAI-compatible endpoints **(verify)** |
| STT client | Audio to text with language hint | Groq Whisper free tier **(verify)** |
| Tool registry | Schemas, handlers, allowlists, side-effect flag | Allowlist enforced here, not only in prompts |
| Action adapters | Per-tenant execution of confirmed actions | Mock municipal portal first |
| Ingestion | Parse, chunk, embed, upsert | Background task, idempotent |
| Source refresher | Re-fetch whitelisted official URLs on schedule | Whitelist only (SSRF control) |

## 5. Data model

All tables live in one database. RAG tables in schema `ai`, conversation and operational tables in schema `agent`. Migrations via Alembic; no ORM auto-generation against shared environments.

**ai.knowledge_document**
`doc_id`, `tenant_id`, `title`, `publisher`, `source_url`, `jurisdiction`, `language`, `verification_status` (`unverified | verified | rejected`), `content_hash`, `published_at`, `fetched_at`, `expires_at`, `ingestion_status` (`processing | ready | failed`), `ingestion_error`

**ai.knowledge_chunk**
`chunk_id`, `doc_id` (FK, cascade), `tenant_id`, `chunk_index`, `section`, `lang`, `text`, `embedding vector(384)`, `embed_model`, `tsv` (generated full-text column)

**agent.agent_config**
`agent_id`, `tier` (`general | professional`), `display_name`, `system_prompt`, `tenants[]`, `tools[]`, `min_similarity`, `active`

**agent.chat_session**
`session_id`, `user_id`, `agent_id`, `language`, `created_at`, `updated_at`

**agent.chat_message**
`message_id`, `session_id` (FK), `role`, `content`, `status`, `request_id` (unique per user turn), `meta jsonb` (trace: scores, verdict, provider, stage timings), `created_at`

**agent.message_source**
`message_id` (FK), `chunk_id` (FK), `rank`, `relevance_score`, `excerpt`

**agent.pending_action**
`token`, `session_id`, `user_id`, `agent_id`, `tool`, `args jsonb`, `args_hash`, `summary`, `expires_at`, `status` (`pending | executed | failed | expired | cancelled`), `result_ref`

**agent.audit_log** (append-only; no update/delete paths in code)
`audit_id`, `at`, `actor`, `agent_id`, `event`, `detail jsonb`

**agent.answer_cache**
`cache_id`, `agent_id`, `q_embedding vector(384)`, `answer jsonb`, `created_at`

Constraints and indexes:
- HNSW (cosine) index on `knowledge_chunk.embedding`; GIN on `tsv`; btree on `tenant_id`, `verification_status`, `expires_at`.
- Session ownership: every history query filters by `user_id` from the JWT.
- `message_source.chunk_id` must reference a chunk actually retrieved for that turn.
- `chat_message.request_id` unique, so a client retry does not create a duplicate turn.
- Chat messages are conversation records; pending actions are operational records. A retried model call must never repeat an action.
- `embed_model` stored per chunk so an embedding change is a detectable reindex, not silent corruption.

## 6. API contract

Paths match the team-wide public contract (`/api/agent/*`, `/api/knowledge/*`). The user identity always comes from the validated JWT, never from the request body.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agent/chat` | One turn. SSE if `Accept: text/event-stream`, otherwise a single JSON response |
| POST | `/api/agent/voice` | Audio upload, returns transcript only |
| POST | `/api/agent/actions/{token}/confirm` | Execute a pending action |
| POST | `/api/agent/actions/{token}/cancel` | Cancel a pending action |
| GET | `/api/agent/personas` | Active agents (id, name, tier) |
| POST / GET | `/api/agent/sessions` | Create / list own sessions |
| GET | `/api/agent/sessions/{id}/messages` | History (ownership checked) |
| POST / GET | `/api/knowledge/docs` | Upload / list documents (admin) |
| POST | `/api/knowledge/docs/{id}/verify` | Mark verified or rejected (admin) |
| POST | `/api/knowledge/docs/{id}/reindex` | Reprocess (admin) |
| GET | `/api/admin/stats` | Operational metrics (admin) |
| GET | `/health`, `/ready` | Liveness, readiness (embedder warmed, DB reachable) |

**Chat request**
```json
{ "sessionId": "uuid|null", "requestId": "uuid", "agentId": "general|null",
  "message": "string", "language": "hi|en|null", "context": { "cityId": "dehradun" } }
```

**Chat response (final frame / JSON body)**
```json
{ "sessionId": "uuid", "messageId": "uuid",
  "status": "ANSWERED | CLARIFICATION_REQUIRED | ABSTAINED | HANDOFF_REQUIRED | ACTION_PENDING | UNAVAILABLE",
  "answer": "string", "agent": { "id": "string", "name": "string" },
  "sources": [ { "docId": "string", "title": "string", "url": "string|null",
                 "excerpt": "string", "fetchedAt": "date", "stale": false } ],
  "cta": null,
  "handoff": null,
  "pendingAction": null,
  "served": "live | cache | fallback" }
```

Rules:
- `sources` is `[]` when there are none. A citation is never fabricated to fill the field.
- `ABSTAINED` carries `cta: "file_complaint"`.
- `ACTION_PENDING` carries `pendingAction: { token, summary, expiresAt }`. A sentence like "I have filed your complaint" is never evidence of execution; only `/confirm` returning success is.
- `served` makes cache and fallback answers visibly distinct from live output (UI badge).

**SSE frames:** `{"t":"token","v":"..."}` repeated, then one `{"t":"final", ...response}`. Errors arrive as `{"t":"error","code":"..."}`.

## 7. Request flows

### 7.1 Chat turn
1. Middleware: request id, JWT verification, per-user rate limit (10 turns/min).
2. Idempotency: if `requestId` already exists for the user, return the stored result.
3. Load session (ownership check) and last 6 messages, capped at about 1500 tokens.
4. Semantic cache lookup, agent-scoped, similarity at least 0.95. Hit: stream cached answer with `served: cache`.
5. Embed `"query: " + text`. Hybrid search scoped to `agent.tenants`.
6. Evidence validator (section 8). If unusable: `ABSTAINED`, zero LLM calls.
7. LLM loop, at most 3 steps. Read-only tools run inline. A side-effect tool creates a pending action and ends the loop with `ACTION_PENDING`.
8. Stream tokens, then the final frame. Sources built from the validated hits.
9. Persist message, sources, trace. Write audit rows for tool use.

### 7.2 Voice
`/api/agent/voice` takes an audio file and a language hint, returns `{text, lang}`. The app then calls `/api/agent/chat` with the text. STT failure is isolated from agent logic. TTS is on-device.

### 7.3 Action confirmation
```
pending --confirm(user, token)--> executed | failed
   |--TTL 5 min--> expired
   |--cancel-----> cancelled
```
Confirm is one atomic statement conditioned on token, user, `status='pending'` and unexpired, returning the row. Zero rows means reject. Double-taps and replays are harmless without locks. Before executing, re-hash the stored args and compare to `args_hash`. Adapter is called with `Idempotency-Key = token`. On failure the status is `failed` and the failure is reported honestly; the user must start a new pending action. No silent retry.

### 7.4 Knowledge ingest
Upload saves the file and creates the document as `processing`. A background task parses (PyMuPDF for PDF, direct read for markdown/text), chunks, embeds, upserts, and sets `ready` or `failed` with the error. `verification_status` is a separate admin action; unverified documents are never retrievable. Re-ingest deletes the document's chunks first (idempotent).

### 7.5 Source refresh
Scheduled job over a whitelist of official domains. Fetch, hash content, re-ingest only on change, update `fetched_at`. URLs outside the whitelist are rejected.

## 8. Retrieval and evidence validation

**Embedding:** `intfloat/multilingual-e5-small`, 384 dims, in process on CPU **(verify)**. `"query: "` and `"passage: "` prefixes are mandatory.

**Chunking:** split on headings, pack to about 400 tokens with 50 overlap. Never split inside a table row or numbered list.

**Search:** two legs, vector cosine (top 20) and full-text (top 20), merged by reciprocal rank fusion (k=60), top 6 returned. Tenant filter and `verification_status='verified'` are in the SQL.

**Evidence validator** (pure function, unit-tested). Input: scored hits, agent config, request context. Rules, all required:
1. Chunk's document is `verified`.
2. Document is not past `expires_at`. Expired documents are excluded.
3. Jurisdiction matches the request's city, or is national.
4. Best **vector-leg cosine** at or above `agent.min_similarity`. Fused (RRF) scores are not comparable to a threshold and are never used for this.
5. At least one chunk survives.

Output: `usable hits (max 4)`, `abstain bool`, `flags` (e.g. `stale` when past the document's freshness window but not expired; shown as a STALE badge on the source).

**Threshold calibration:** e5 cosine scores sit in a narrow high band, so the cutoff is chosen from the evaluation sweep (answerable vs deliberately unanswerable questions), not by intuition.

## 9. Agents, tenancy and handoff

- Agents are rows in `agent_config`, cached in memory with a 60 s TTL so admin edits propagate without a deploy.
- Tenant scope comes only from config. The retrieval function takes `tenants` as a parameter that no model output can reach.
- `general` reads the `public` tenant, has read-only tools plus `handoff`, and sees a directory of active agents.
- `professional` agents (e.g. `municipal`) read `public` plus their own tenant and may hold side-effect tools.
- Handoff validates the target against active rows, then re-runs the turn with a fresh retrieval under the target's tenants. Prior retrieved context is never forwarded. The response carries `handoff: {agentId, name}`.
- Tool allowlist is enforced in the registry. A hallucinated tool name returns an error result.
- Required test: the general agent can never retrieve a chunk that exists only in a professional tenant.

## 10. Tools and actions

| Tool | Type | Notes |
|---|---|---|
| `get_events` | read | City events, filterable |
| `get_active_alerts` | read | Current alerts |
| `search_schemes` | read | Retrieval with a scheme filter |
| `get_complaint_status` | read | By tracking ID |
| `create_complaint` | **side effect** | Two-phase confirm; slot-filled category, location, description |
| `handoff` | control | Targets validated against active agents |

Adapter interface per tenant: `execute(action, args) -> result`. The mock municipal portal ships inside the service with a tracking-ID generator. Integration with the team's real complaint API is an adapter swap, not a redesign.

## 11. LLM and STT layer

**Provider chain (text):** Gemini free tier, then Groq free tier, then local `llama.cpp` server **(verify endpoints, tool-calling support, quotas)**. All behind one OpenAI-compatible client. Model names come from environment variables.

**Local model role:** last-resort fallback and `DEMO_MODE`. A 2B-class model is weak at Hindi and unreliable at tool calling, so in local mode: tools and handoff are disabled, the prompt is retrieval-extractive ("answer using only these passages"), and responses are labelled `served: fallback`.

**Resilience:**
- Global concurrency semaphore (4) around LLM calls.
- Per-provider token bucket sized to the provider's RPM. Empty bucket: wait up to 2 s, then fail over.
- 429: immediate failover. 5xx/timeout: one retry, then failover. A provider that fails 3 times is skipped for 60 s.
- All providers down: semantic cache, else a static unavailable frame (`UNAVAILABLE`).

**STT chain:** Groq Whisper free tier, then local `faster-whisper` (small/base, CPU) as offline fallback, then keyboard dictation on the device. A text-only Gemma 2B model cannot transcribe audio; Gemma 3n-class models accept audio but runtime support must be verified before relying on it.

**TTS:** on-device `expo-speech` (Google TTS engine on Android). Hindi voice pack must be installed on the demo phone. Speech is optional and off by default.

## 12. Security

| Threat | Control |
|---|---|
| Prompt injection via KB or user text | Retrieved text delimited and labelled as data; every side effect needs explicit confirmation |
| Cross-tenant leak | Tenant filter in SQL, server-side only, plus isolation test |
| Forged or modified confirmation | Token bound to user and `args_hash`; atomic state transition; TTL |
| Replay / double submit | Idempotency key per request and per action |
| Malicious upload | PDF/MD/TXT only, 10 MB cap, parse with timeout, admin role required |
| Citation spoofing | `sources[]` built from hits in code |
| SSRF via refresh job | Domain whitelist |
| Secret leakage | `.env` only; redact `Authorization` and keys in logs |
| PII sent to hosted LLMs | Free tiers may retain prompts; mask phone/email in complaint text before model calls where feasible; state in README |
| Quota abuse | Per-user rate limit, global semaphore |

## 13. Failure matrix

| Failure | Behaviour |
|---|---|
| Primary LLM 429/5xx | Fail over; 60 s cool-down for the failed provider |
| All hosted LLMs down | Local fallback, then cache, then `UNAVAILABLE`. Abstain paths unaffected |
| STT down | `/voice` returns a coded 503; app prompts for keyboard dictation |
| PostgreSQL down | `/health` fails; chat returns 503. Single point of failure; compose healthcheck restarts it |
| Adapter timeout on confirm | 10 s timeout, status `failed`, audited, user told |
| Embedder cold start | Warm in lifespan; `/ready` only after a dummy embed |
| Client disconnects mid-stream | Cancel generator, persist partial turn with `meta.interrupted` |
| Invalid model output | Validate against response schema; one repair attempt, then `UNAVAILABLE` |
| Stale source | Excluded if expired; flagged STALE if within grace |

## 14. Observability and deployment

**Observability:** JSON logs with `request_id`, `session_id`, `agent_id`. The per-turn trace in `chat_message.meta` feeds the admin activity panel directly. `/api/admin/stats` exposes turns, abstain rate, cache hit rate, provider share, and p50/p95 latency per stage. Abstain rate and provider share are the two numbers that predict trouble on demo day.

**Deployment:** Docker Compose with `db` (pgvector image, volume, healthcheck) and `api` (waits for healthy db, runs migrations, starts uvicorn). Optional `llm` service for the local `llama.cpp` server. Demo host is the team laptop; phone on the same Wi-Fi, with a tunnel as backup. Free hosting tiers sleep and cap RAM below what the embedder needs.

**`DEMO_MODE=1`:** LLM chain replaced by cache plus local model, STT replaced by prerecorded transcripts or keyboard, adapter is the mock portal. Rehearse with the network actually disabled.

**Seed command:** loads the corpus, agent configs and demo cache in one invocation.

## 15. Integration boundary with the wider team

This service is built to run standalone. Open items to settle with the other modules:

| Item | Current assumption | Decision needed from |
|---|---|---|
| JWT issuer | Platform module issues HS256 JWTs with a shared secret; this service verifies. A `/dev/token` stub exists only under `DEMO_MODE` | Platform owner |
| Real complaint API | Reached through the tenant adapter over REST; this service never writes to their tables | Civic owner |
| Events / alerts data | Read through their REST endpoints via read-only tool handlers | Civic / Platform owners |
| Spring gateway | None. If the team later mandates one, it proxies `/api/agent/*` unchanged; DTOs are already compatible | Team |

## 16. Assumptions to verify on day 1

- Gemini and Groq free tiers: OpenAI-compatible endpoints, tool-calling support, current rate limits, data-retention terms.
- Groq Whisper free tier: Hindi support, upload size limit, m4a acceptance.
- `llama-server` OpenAI-compatible endpoint and the chosen local model's context size.
- `expo/fetch` streaming support in the project's Expo SDK version.
- Hindi TTS voice available on the Android demo device.
- Demo laptop RAM: Postgres + embedder + optional local model needs roughly 3 GB free, more with a local LLM.
