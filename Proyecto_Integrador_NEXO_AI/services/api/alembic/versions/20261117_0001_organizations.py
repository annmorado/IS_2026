"""RF-001: crear organizaciones.

Revision ID: orgs_0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "orgs_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sector", sa.String(length=80), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'MXN'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("currency = 'MXN'", name="ck_organizations_currency_mxn"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_organizations_name_not_empty"),
        sa.CheckConstraint("length(trim(sector)) > 0", name="ck_organizations_sector_not_empty"),
    )


def downgrade() -> None:
    op.drop_table("organizations")
