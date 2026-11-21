"""RF-006: materiales, existencias y receta por producto.

Revision ID: materials_0005
Revises: products_0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "materials_0005"
down_revision: Union[str, None] = "products_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La unicidad compuesta garantiza FKs que incluyen organization_id.
    op.create_unique_constraint("uq_products_id_org", "products", ["id", "organization_id"])
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("quantity_available", sa.Numeric(15, 3), nullable=False, server_default=sa.text("0.000")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "sku", name="uq_materials_org_sku"),
        sa.UniqueConstraint("id", "organization_id", name="uq_materials_id_org"),
        sa.CheckConstraint("length(trim(sku)) > 0", name="ck_materials_sku_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_materials_name_nonempty"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_materials_unit_nonempty"),
        sa.CheckConstraint("quantity_available >= 0", name="ck_materials_stock_nonnegative"),
    )
    op.create_index("ix_materials_organization_id", "materials", ["organization_id"])
    op.create_table(
        "product_materials",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity_per_unit", sa.Numeric(15, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id", "organization_id"],
                                ["products.id", "products.organization_id"],
                                name="fk_recipe_product_tenant", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id", "organization_id"],
                                ["materials.id", "materials.organization_id"],
                                name="fk_recipe_material_tenant", ondelete="CASCADE"),
        sa.UniqueConstraint("product_id", "material_id", name="uq_product_materials_recipe"),
        sa.CheckConstraint("quantity_per_unit > 0", name="ck_recipe_positive_quantity"),
    )
    op.create_index("ix_product_materials_organization_id", "product_materials", ["organization_id"])
    op.create_index("ix_product_materials_product_id", "product_materials", ["product_id"])
    op.create_index("ix_product_materials_material_id", "product_materials", ["material_id"])


def downgrade() -> None:
    op.drop_index("ix_product_materials_material_id", table_name="product_materials")
    op.drop_index("ix_product_materials_product_id", table_name="product_materials")
    op.drop_index("ix_product_materials_organization_id", table_name="product_materials")
    op.drop_table("product_materials")
    op.drop_index("ix_materials_organization_id", table_name="materials")
    op.drop_table("materials")
    op.drop_constraint("uq_products_id_org", "products", type_="unique")
