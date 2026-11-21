"""RF-008: solicitudes manuales en borrador trazables por tenant y usuario.

Revision ID: orders_0007
Revises: capacity_0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "orders_0007"
down_revision: Union[str, None] = "capacity_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_users_id_org", "users", ["id", "organization_id"])
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.String(length=5000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("source", sa.String(length=20), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"], name="fk_orders_creator_tenant", ondelete="CASCADE"),
        sa.CheckConstraint("length(trim(raw_text)) > 0", name="ck_orders_raw_text_not_empty"),
        sa.CheckConstraint("length(raw_text) <= 5000", name="ck_orders_raw_text_max_length"),
        sa.CheckConstraint("status IN ('draft', 'pending', 'confirmed', 'in_progress', 'completed', 'cancelled')", name="ck_orders_valid_status"),
        sa.CheckConstraint("source IN ('manual', 'audio')", name="ck_orders_valid_source"),
    )
    op.create_index("ix_orders_org_created", "orders", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_org_created", table_name="orders")
    op.drop_table("orders")
    op.drop_constraint("uq_users_id_org", "users", type_="unique")
