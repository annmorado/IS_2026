"""RF-009: notas de voz asociadas a usuario y tenant.
Revision ID: voice_0008
Revises: orders_0007
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "voice_0008"
down_revision: Union[str, None] = "orders_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("sha256_hex", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"], name="fk_voice_notes_author_tenant", ondelete="CASCADE"),
        sa.CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_voice_notes_size"),
        sa.CheckConstraint("duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 3600000)",
                           name="ck_voice_notes_duration"),
        sa.CheckConstraint("length(sha256_hex) = 64", name="ck_voice_notes_sha256_length"),
    )
    op.create_index("ix_voice_notes_organization_id", "voice_notes", ["organization_id"])
    op.create_index("ix_voice_notes_created_by_user_id", "voice_notes", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_notes_created_by_user_id", table_name="voice_notes")
    op.drop_index("ix_voice_notes_organization_id", table_name="voice_notes")
    op.drop_table("voice_notes")
