"""RF-012: indice para listado tenant-scoped filtrado por estado.

Revision ID: search_0011
Revises: status_0010
"""
from alembic import op

revision = "search_0011"
down_revision = "status_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_orders_org_status_created_id", "orders",
                    ["organization_id", "status", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_orders_org_status_created_id", table_name="orders")
