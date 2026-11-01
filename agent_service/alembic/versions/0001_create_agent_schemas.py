"""create agent and knowledge schemas

Revision ID: 0001_create_agent_schemas
"""

from alembic import op

revision = "0001_create_agent_schemas"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")
    op.execute("CREATE SCHEMA IF NOT EXISTS agent")
    op.execute("""
        CREATE TABLE ai.knowledge_document (
            doc_id uuid PRIMARY KEY,
            tenant_id varchar(100) NOT NULL,
            title varchar(500) NOT NULL,
            publisher varchar(300) NOT NULL,
            source_url varchar(2000), jurisdiction varchar(100) NOT NULL,
            language varchar(20) NOT NULL,
            verification_status varchar(20) NOT NULL CHECK (verification_status IN ('unverified','verified','rejected')),
            content_hash varchar(64) NOT NULL,
            published_at timestamptz, fetched_at timestamptz NOT NULL,
            expires_at timestamptz, ingestion_status varchar(20) NOT NULL,
            ingestion_error text
        )
    """)
    op.execute("""
        CREATE TABLE ai.knowledge_chunk (
            chunk_id uuid PRIMARY KEY, doc_id uuid NOT NULL REFERENCES ai.knowledge_document(doc_id) ON DELETE CASCADE,
            tenant_id varchar(100) NOT NULL, chunk_index integer NOT NULL CHECK (chunk_index >= 0),
            section varchar(500), lang varchar(20) NOT NULL, text text NOT NULL,
            embedding vector(384) NOT NULL, embed_model varchar(200) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
            UNIQUE (doc_id, chunk_index)
        )
    """)
    op.execute(
        "CREATE TABLE agent.agent_config (agent_id varchar(100) PRIMARY KEY, tier varchar(20) NOT NULL, display_name varchar(200) NOT NULL, system_prompt text NOT NULL, tenants text[] NOT NULL, tools text[] NOT NULL, min_similarity double precision NOT NULL CHECK (min_similarity BETWEEN -1 AND 1), active boolean NOT NULL DEFAULT true)"
    )
    op.execute(
        "CREATE TABLE agent.chat_session (session_id uuid PRIMARY KEY, user_id varchar(200) NOT NULL, agent_id varchar(100) NOT NULL REFERENCES agent.agent_config(agent_id), language varchar(20), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)"
    )
    op.execute(
        "CREATE TABLE agent.chat_message (message_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES agent.chat_session(session_id) ON DELETE CASCADE, role varchar(20) NOT NULL, content text NOT NULL, status varchar(40) NOT NULL, request_id uuid NOT NULL UNIQUE, meta jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL)"
    )
    op.execute(
        "CREATE TABLE agent.message_source (message_id uuid NOT NULL REFERENCES agent.chat_message(message_id) ON DELETE CASCADE, chunk_id uuid NOT NULL REFERENCES ai.knowledge_chunk(chunk_id), rank integer NOT NULL, relevance_score double precision NOT NULL, excerpt text NOT NULL, PRIMARY KEY (message_id, chunk_id))"
    )
    op.execute(
        "CREATE TABLE agent.pending_action (token varchar(200) PRIMARY KEY, session_id uuid NOT NULL REFERENCES agent.chat_session(session_id), user_id varchar(200) NOT NULL, agent_id varchar(100) NOT NULL, tool varchar(100) NOT NULL, args jsonb NOT NULL, args_hash varchar(64) NOT NULL, summary text NOT NULL, expires_at timestamptz NOT NULL, status varchar(20) NOT NULL, result_ref text)"
    )
    op.execute(
        "CREATE TABLE agent.audit_log (audit_id uuid PRIMARY KEY, at timestamptz NOT NULL, actor varchar(200) NOT NULL, agent_id varchar(100), event varchar(100) NOT NULL, detail jsonb NOT NULL DEFAULT '{}'::jsonb)"
    )
    op.execute(
        "CREATE TABLE agent.answer_cache (cache_id uuid PRIMARY KEY, agent_id varchar(100) NOT NULL, q_embedding vector(384) NOT NULL, answer jsonb NOT NULL, created_at timestamptz NOT NULL)"
    )
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON ai.knowledge_chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunk_tsv ON ai.knowledge_chunk USING gin (tsv)")
    op.execute(
        "CREATE INDEX ix_doc_tenant_status_expiry ON ai.knowledge_document (tenant_id, verification_status, expires_at)"
    )
    op.execute("CREATE INDEX ix_chunk_tenant ON ai.knowledge_chunk (tenant_id)")
    op.execute("CREATE INDEX ix_session_user ON agent.chat_session (user_id)")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS agent CASCADE")
    op.execute("DROP SCHEMA IF EXISTS ai CASCADE")
