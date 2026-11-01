from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Computed, DateTime, Index, LargeBinary, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeDocument(SQLModel, table=True):
    __tablename__ = "knowledge_document"
    __table_args__ = {"schema": "ai"}
    doc_id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: str = Field(index=True, max_length=100)
    title: str = Field(max_length=500)
    publisher: str = Field(max_length=300)
    source_url: str | None = Field(default=None, max_length=2000)
    jurisdiction: str = Field(max_length=100)
    language: str = Field(max_length=20)
    verification_status: str = Field(default="unverified", max_length=20, index=True)
    content_hash: str = Field(max_length=64, index=True)
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    fetched_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), index=True)
    )
    file_path: str | None = Field(default=None, max_length=2000)
    ingestion_status: str = Field(default="processing", max_length=20)
    ingestion_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class KnowledgeChunk(SQLModel, table=True):
    __tablename__ = "knowledge_chunk"
    __table_args__ = (
        Index("ix_knowledge_chunk_tenant", "tenant_id"),
        {"schema": "ai"},
    )
    chunk_id: UUID = Field(default_factory=uuid4, primary_key=True)
    doc_id: UUID = Field(foreign_key="ai.knowledge_document.doc_id", index=True)
    tenant_id: str = Field(max_length=100)
    chunk_index: int = Field(ge=0)
    section: str | None = Field(default=None, max_length=500)
    lang: str = Field(max_length=20)
    text: str = Field(sa_column=Column(Text, nullable=False))
    embedding: list[float] = Field(sa_column=Column(Vector(384), nullable=False))
    embed_model: str = Field(max_length=200)
    tsv: str | None = Field(
        default=None,
        sa_column=Column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True)),
    )


class AgentConfig(SQLModel, table=True):
    __tablename__ = "agent_config"
    __table_args__ = {"schema": "agent"}
    agent_id: str = Field(primary_key=True, max_length=100)
    tier: str = Field(max_length=20)
    display_name: str = Field(max_length=200)
    system_prompt: str = Field(sa_column=Column(Text, nullable=False))
    tenants: list[str] = Field(sa_column=Column(ARRAY(Text), nullable=False))
    tools: list[str] = Field(sa_column=Column(ARRAY(Text), nullable=False))
    min_similarity: float = Field(ge=-1, le=1)
    active: bool = True


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"
    __table_args__ = {"schema": "agent"}
    session_id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: str = Field(max_length=200, index=True)
    agent_id: str = Field(foreign_key="agent.agent_config.agent_id", max_length=100)
    language: str | None = Field(default=None, max_length=20)
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"
    __table_args__ = {"schema": "agent"}
    message_id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(foreign_key="agent.chat_session.session_id", index=True)
    role: str = Field(max_length=20)
    content: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(max_length=40)
    request_id: UUID | None = Field(default=None, index=True, unique=True)
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MessageSource(SQLModel, table=True):
    __tablename__ = "message_source"
    __table_args__ = {"schema": "agent"}
    message_id: UUID = Field(foreign_key="agent.chat_message.message_id", primary_key=True)
    chunk_id: UUID = Field(foreign_key="ai.knowledge_chunk.chunk_id", primary_key=True)
    rank: int = Field(ge=1)
    relevance_score: float
    excerpt: str = Field(sa_column=Column(Text, nullable=False))


class PendingAction(SQLModel, table=True):
    __tablename__ = "pending_action"
    __table_args__ = {"schema": "agent"}
    token: str = Field(primary_key=True, max_length=200)
    session_id: UUID = Field(foreign_key="agent.chat_session.session_id")
    user_id: str = Field(max_length=200, index=True)
    agent_id: str = Field(max_length=100, foreign_key="agent.agent_config.agent_id")
    tool: str = Field(max_length=100)
    args: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    args_hash: str = Field(max_length=64)
    summary: str = Field(sa_column=Column(Text, nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    status: str = Field(default="pending", max_length=20, index=True)
    result_ref: str | None = Field(default=None, max_length=500)


class Media(SQLModel, table=True):
    """A citizen photo (complaint evidence), stored in the database (alembic 0003_media)."""

    __tablename__ = "media"
    __table_args__ = {"schema": "agent"}
    media_id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: str = Field(max_length=200, index=True)
    action_token: str | None = Field(default=None, max_length=200, index=True)
    content_type: str = Field(max_length=100)
    filename: str = Field(max_length=200)
    size_bytes: int
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False))


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "agent"}
    audit_id: UUID = Field(default_factory=uuid4, primary_key=True)
    at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    actor: str = Field(max_length=200)
    agent_id: str | None = Field(default=None, max_length=100)
    event: str = Field(max_length=100)
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))


class AnswerCache(SQLModel, table=True):
    __tablename__ = "answer_cache"
    __table_args__ = {"schema": "agent"}
    cache_id: UUID = Field(default_factory=uuid4, primary_key=True)
    agent_id: str = Field(max_length=100, index=True, foreign_key="agent.agent_config.agent_id")
    q_embedding: list[float] = Field(sa_column=Column(Vector(384), nullable=False))
    answer: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
