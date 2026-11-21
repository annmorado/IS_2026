"""RF-005: catalogo de productos scoped por organizacion.

Revision ID: products_0004
Revises: rbac_0003
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "products_0004"
down_revision: Union[str, None] = "rbac_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("cost_mxn", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("price_mxn", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("base_production_minutes", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "sku", name="uq_products_org_sku"),
        sa.CheckConstraint("length(trim(sku)) > 0", name="ck_products_sku_not_empty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_products_name_not_empty"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_products_unit_not_empty"),
        sa.CheckConstraint("cost_mxn >= 0", name="ck_products_nonnegative_cost"),
        sa.CheckConstraint("price_mxn >= 0", name="ck_products_nonnegative_price"),
        sa.CheckConstraint("base_production_minutes > 0", name="ck_products_positive_minutes"),
    )
    op.create_index("ix_products_organization_id", "products", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_organization_id", table_name="products")
    op.drop_table("products")
