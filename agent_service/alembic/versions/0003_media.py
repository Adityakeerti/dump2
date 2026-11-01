"""Citizen photos (e.g. complaint evidence) stored in the database.

Revision ID: 0003_media
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_media"
down_revision = "0002_harden_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("media_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(200), nullable=False, index=True),
        # The pending action (e.g. a drafted complaint) this photo is attached to.
        sa.Column("action_token", sa.String(200), nullable=True, index=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_media_size"),
        schema="agent",
    )


def downgrade() -> None:
    op.drop_table("media", schema="agent")
