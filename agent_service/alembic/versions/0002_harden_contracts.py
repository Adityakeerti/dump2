"""Harden states, tenant consistency, and retained citation history.

Revision ID: 0002_harden_contracts
Revises: 0001_create_agent_schemas
"""

from alembic import op

revision = "0002_harden_contracts"
down_revision = "0001_create_agent_schemas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai.knowledge_document ADD COLUMN file_path varchar(2000)")
    op.execute("ALTER TABLE agent.chat_message ALTER COLUMN request_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE ai.knowledge_document ADD CONSTRAINT uq_document_tenant UNIQUE (doc_id, tenant_id)"
    )
    op.execute(
        "ALTER TABLE ai.knowledge_chunk ADD CONSTRAINT fk_chunk_document_tenant FOREIGN KEY (doc_id, tenant_id) REFERENCES ai.knowledge_document(doc_id, tenant_id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE ai.knowledge_document ADD CONSTRAINT ck_ingestion_status CHECK (ingestion_status IN ('processing','ready','failed'))"
    )
    op.execute(
        "ALTER TABLE agent.agent_config ADD CONSTRAINT ck_agent_tier CHECK (tier IN ('general','professional'))"
    )
    op.execute(
        "ALTER TABLE agent.agent_config ADD CONSTRAINT ck_agent_tenants CHECK (cardinality(tenants) > 0)"
    )
    op.execute(
        "ALTER TABLE agent.pending_action ADD CONSTRAINT ck_pending_status CHECK (status IN ('pending','executing','executed','failed','expired','cancelled'))"
    )
    op.execute(
        "ALTER TABLE agent.chat_message ADD CONSTRAINT ck_message_role CHECK (role IN ('user','assistant','tool'))"
    )
    op.execute("CREATE INDEX ix_message_session_time ON agent.chat_message(session_id, created_at)")
    op.execute(
        "CREATE INDEX ix_pending_owner_status ON agent.pending_action(user_id, status, expires_at)"
    )
    op.execute("CREATE INDEX ix_cache_agent ON agent.answer_cache(agent_id, created_at)")
    op.execute("CREATE INDEX ix_audit_time ON agent.audit_log(at)")
    op.execute(
        "ALTER TABLE agent.pending_action ADD CONSTRAINT fk_action_persona FOREIGN KEY (agent_id) REFERENCES agent.agent_config(agent_id)"
    )
    op.execute(
        "ALTER TABLE agent.answer_cache ADD CONSTRAINT fk_cache_persona FOREIGN KEY (agent_id) REFERENCES agent.agent_config(agent_id)"
    )
    # Reindex replaces chunk rows. Retain the evidence snapshot in message meta/sources,
    # and remove only the obsolete relational link when its chunk is replaced.
    op.execute("ALTER TABLE agent.message_source DROP CONSTRAINT message_source_chunk_id_fkey")
    op.execute(
        "ALTER TABLE agent.message_source ADD CONSTRAINT message_source_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES ai.knowledge_chunk(chunk_id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE agent.chat_message SET request_id = gen_random_uuid() WHERE request_id IS NULL"
    )
    op.execute("ALTER TABLE agent.chat_message ALTER COLUMN request_id SET NOT NULL")
    op.execute("ALTER TABLE agent.message_source DROP CONSTRAINT message_source_chunk_id_fkey")
    op.execute(
        "ALTER TABLE agent.message_source ADD CONSTRAINT message_source_chunk_id_fkey FOREIGN KEY (chunk_id) REFERENCES ai.knowledge_chunk(chunk_id)"
    )
    op.execute("ALTER TABLE agent.pending_action DROP CONSTRAINT fk_action_persona")
    op.execute("ALTER TABLE agent.answer_cache DROP CONSTRAINT fk_cache_persona")
    for name, table in [
        ("ck_message_role", "agent.chat_message"),
        ("ck_pending_status", "agent.pending_action"),
        ("ck_agent_tenants", "agent.agent_config"),
        ("ck_agent_tier", "agent.agent_config"),
        ("ck_ingestion_status", "ai.knowledge_document"),
        ("fk_chunk_document_tenant", "ai.knowledge_chunk"),
        ("uq_document_tenant", "ai.knowledge_document"),
    ]:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    for index in (
        "agent.ix_message_session_time",
        "agent.ix_pending_owner_status",
        "agent.ix_cache_agent",
        "agent.ix_audit_time",
    ):
        op.execute(f"DROP INDEX {index}")
    op.execute("ALTER TABLE ai.knowledge_document DROP COLUMN file_path")
