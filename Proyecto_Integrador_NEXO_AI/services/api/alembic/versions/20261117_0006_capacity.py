"""RF-007: capacidad diaria por recurso y dias fuera de servicio.

Revision ID: capacity_0006
Revises: materials_0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "capacity_0006"
down_revision: Union[str, None] = "materials_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_resources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("daily_capacity", sa.Numeric(12, 3), nullable=False),
        sa.Column("workdays_csv", sa.String(length=13), nullable=False, server_default=sa.text("'0,1,2,3,4'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "code", name="uq_resources_org_code"),
        sa.UniqueConstraint("id", "organization_id", name="uq_resources_id_org"),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_resources_code_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_resources_name_nonempty"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_resources_unit_nonempty"),
        sa.CheckConstraint("daily_capacity > 0", name="ck_resources_daily_capacity_positive"),
        sa.CheckConstraint("length(trim(workdays_csv)) > 0", name="ck_resources_workdays_nonempty"),
    )
    op.create_index("ix_production_resources_organization_id", "production_resources", ["organization_id"])
    op.create_table(
        "resource_blackouts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id", "organization_id"],
            ["production_resources.id", "production_resources.organization_id"],
            name="fk_blackouts_resource_tenant", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("resource_id", "day", name="uq_resource_blackouts_resource_day"),
    )
    op.create_index("ix_resource_blackouts_organization_id", "resource_blackouts", ["organization_id"])
    op.create_index("ix_resource_blackouts_resource_id", "resource_blackouts", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_blackouts_resource_id", table_name="resource_blackouts")
    op.drop_index("ix_resource_blackouts_organization_id", table_name="resource_blackouts")
    op.drop_table("resource_blackouts")
    op.drop_index("ix_production_resources_organization_id", table_name="production_resources")
    op.drop_table("production_resources")
