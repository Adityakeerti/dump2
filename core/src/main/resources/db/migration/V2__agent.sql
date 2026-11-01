-- =====================================================================
-- CitySense V2: Multilingual Agent & Knowledge Schema (Member B)
-- =====================================================================

CREATE TABLE knowledge_docs (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(255) NOT NULL,
    category     VARCHAR(64)  NOT NULL DEFAULT 'CIVIC',
    department   VARCHAR(64)  NOT NULL DEFAULT 'MUNICIPAL',
    source_url   VARCHAR(512),
    is_verified  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai.knowledge_chunks (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id      UUID         NOT NULL REFERENCES knowledge_docs(id) ON DELETE CASCADE,
    chunk_index INT          NOT NULL,
    content     TEXT         NOT NULL,
    metadata    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_knowledge_chunks_doc_id ON ai.knowledge_chunks (doc_id);

CREATE TABLE chat_sessions (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NULL REFERENCES users(id) ON DELETE SET NULL,
    persona     VARCHAR(32)  NOT NULL DEFAULT 'CIVIC_ASSISTANT',
    language    VARCHAR(8)   NOT NULL DEFAULT 'en',
    messages    JSONB        NOT NULL DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions (user_id);
