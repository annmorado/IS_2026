"""RF-011: historial de estados y mayor consistencia de pedidos.

Revision ID: status_0010
Revises: review_0009
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "status_0010"
down_revision: Union[str, None] = "review_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUSES = "'draft', 'pending', 'confirmed', 'in_progress', 'completed', 'cancelled'"


def upgrade() -> None:
    op.create_unique_constraint("uq_orders_id_org", "orders", ["id", "organization_id"])
    op.drop_constraint("ck_orders_confirmed_has_review", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_confirmed_has_review", "orders",
        "status NOT IN ('confirmed', 'in_progress', 'completed') OR "
        "(reviewed_quantity IS NOT NULL AND reviewed_due_date IS NOT NULL "
        "AND reviewed_at IS NOT NULL AND reviewed_by_user_id IS NOT NULL "
        "AND confirmed_at IS NOT NULL AND confirmed_by_user_id IS NOT NULL)",
    )
    op.create_table(
        "order_status_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(
            ["order_id", "organization_id"], ["orders.id", "orders.organization_id"],
            name="fk_order_events_order_tenant", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id", "organization_id"], ["users.id", "users.organization_id"],
            name="fk_order_events_user_tenant",
        ),
        sa.CheckConstraint(f"from_status IN ({STATUSES})", name="ck_order_events_from_status"),
        sa.CheckConstraint(f"to_status IN ({STATUSES})", name="ck_order_events_to_status"),
        sa.CheckConstraint("from_status <> to_status", name="ck_order_events_status_changed"),
    )
    op.create_index("ix_order_events_org_order_date", "order_status_events",
                    ["organization_id", "order_id", "changed_at"])

    # RF-010 solo permite confirmar desde 'draft'. Backfill de confirmaciones
    # previas: sus actor y fecha originales ya estan en la tabla orders.
    if op.get_context().as_sql:
        return
    conn = op.get_bind()
    old_orders = sa.table(
        "orders",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("organization_id", sa.Uuid(as_uuid=True)),
        sa.column("confirmed_by_user_id", sa.Uuid(as_uuid=True)),
        sa.column("confirmed_at", sa.DateTime(timezone=True)),
        sa.column("status", sa.String(20)),
    )
    audit_table = sa.table(
        "order_status_events",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("organization_id", sa.Uuid(as_uuid=True)),
        sa.column("order_id", sa.Uuid(as_uuid=True)),
        sa.column("changed_by_user_id", sa.Uuid(as_uuid=True)),
        sa.column("from_status", sa.String(20)),
        sa.column("to_status", sa.String(20)),
        sa.column("changed_at", sa.DateTime(timezone=True)),
        sa.column("note", sa.String(500)),
    )
    existing = conn.execute(sa.select(
        old_orders.c.id, old_orders.c.organization_id,
        old_orders.c.confirmed_by_user_id, old_orders.c.confirmed_at,
    ).where(
        old_orders.c.status == "confirmed",
        old_orders.c.confirmed_by_user_id.is_not(None),
        old_orders.c.confirmed_at.is_not(None),
    )).all()
    if existing:
        conn.execute(sa.insert(audit_table), [
            {
                "id": uuid4(), "organization_id": org,
                "order_id": oid, "changed_by_user_id": actor,
                "from_status": "draft", "to_status": "confirmed",
                "changed_at": when,
                "note": "Confirmacion previa a RF-011; RF-010",
            }
            for oid, org, actor, when in existing
        ])



def downgrade() -> None:
    op.drop_index("ix_order_events_org_order_date", table_name="order_status_events")
    op.drop_table("order_status_events")
    op.drop_constraint("ck_orders_confirmed_has_review", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_confirmed_has_review", "orders",
        "status <> 'confirmed' OR (reviewed_quantity IS NOT NULL AND reviewed_due_date IS NOT NULL "
        "AND reviewed_at IS NOT NULL AND reviewed_by_user_id IS NOT NULL "
        "AND confirmed_at IS NOT NULL AND confirmed_by_user_id IS NOT NULL)",
    )
    op.drop_constraint("uq_orders_id_org", "orders", type_="unique")
