# Database and contract notes

All persistent entities have SQLModel mappings in `src/models.py`; `src/agent/models.py` and `src/knowledge/models.py` expose domain models. UUIDs are generated in Python, timestamps are UTC-aware PostgreSQL `timestamptz`, structured payloads are JSONB, and tenant/tool lists are PostgreSQL text arrays.

| Table | Key and important invariants |
|---|---|
| ai.knowledge_document | UUID doc_id; tenant, title, publisher, jurisdiction, language, SHA-256 content hash; verification and ingestion states independent; optional expiry/source URL and stored file path |
| ai.knowledge_chunk | UUID chunk_id; document+tenant composite FK prevents mismatched scopes; unique document+chunk_index; vector(384); actual embed_model name; generated simple-language tsvector |
| agent.agent_config | String agent_id; general/professional tier; server-owned nonempty tenant list; tool allowlist; cosine threshold [-1,1]; active flag |
| agent.chat_session | UUID session_id; JWT subject string user_id; persona FK; language; created/updated UTC |
| agent.chat_message | UUID message_id; session FK; role, content, status, JSONB metadata; nullable unique request_id for the assistant turn; user messages do not consume request IDs |
| agent.message_source | Composite message+chunk PK; snapshot excerpt, real vector score, rank; chunk FK corresponds to a retrieved hit |
| agent.pending_action | Unguessable token; owner/session/persona/tool; canonical argument SHA-256; immutable summary/arguments through public API; TTL and execution state |
| agent.audit_log | UUID; UTC time, actor, persona, event, JSONB detail; only append operations exposed |
| agent.answer_cache | UUID; persona, query vector, answer JSONB including evidence/model/user signature; TTL based on creation time |

Migration 0001 is preserved. Migration 0002 adds stored file paths, allows NULL request IDs for user messages, adds state checks and tenant consistency, and lets reindex delete obsolete citation links. Historical citation **snapshots remain in the assistant response metadata** even after source chunks are replaced. This avoids reindex failing on historical FK references.

Pending actions have an additive internal `executing` state: the atomic claim is committed before external I/O. This prevents a crashed process or lost HTTP response from replaying an external side effect. Public confirmation still reports executed/failed/rejected; cancellation reports cancelled. An interrupted executing claim is marked failed on expiry, never retried. Resolving uncertain outcomes at a real adapter requires its idempotency lookup; the service does not claim success without a successful adapter receipt.

Migrations are the only DDL path. `create_all` is never called. No foreign key to platform users is created because that service/database is outside this component. `sub` remains an opaque string, not an invented local user record.

## Input validation

- Chat: valid request UUID; optional session UUID; message stripped, 1–4000 characters; optional en/hi language; city identifier <=100 characters. No client tenant/user/tool permissions. Extra fields rejected.
- JWT: fixed HS256, signature verification, mandatory sub/iat/exp, optional issuer/audience. Missing/invalid bearer ->401; missing admin role ->403.
- Knowledge: multipart PDF/MD/TXT plus validated metadata JSON; type/signature/size checks; timezone-aware dates; unverified by default. Verify requires ready ingestion.
- Actions: only server-stored arguments; token owner, pending state, and expiry checked in one atomic SQL statement. Canonical hash and current tool allowlist rechecked before adapter use.
- Tools: Pydantic argument schemas forbid extra fields; unknown and unauthorized names rejected in code; list/location/description limits; model cannot choose tenant scope.
- Pagination: bounded limits on list/history endpoints.

## Output contract

Chat response fields are frozen as in architecture section 6. `agent` contains id/name; personas contain id/name/tier. `sources` is an array even when empty. Status is an enumerated string. Pending actions have token/summary/expiresAt, and handoff has agentId/name. `served` is live/cache/fallback. Voice returns text/lang only. Never infer complaint success from generated prose; use `/confirm` status/result.

## Explicit operational choices

- Readiness requires migrated PostgreSQL+vector and a warmed 384-dimensional embedder; liveness is process-only.
- Query hash embeddings are an explicit demo/testing backend, never a silent fallback for E5.
- Buffered SSE emits only a persisted, validated answer. It trades provider-token latency for safe final-contract delivery and retry consistency; it is not live provider streaming.
- Direct chat with an active professional persona is allowed, as in the original design. If professional corpora need role-based access beyond persona scopes, the platform must define that additional authorization policy.
- The original design abstains before any LLM/tool call. Consequently an unsupported general query cannot trigger an LLM-selected handoff; the client can select the municipal persona explicitly. This preserves the zero-call rule rather than inventing an intent classifier.
