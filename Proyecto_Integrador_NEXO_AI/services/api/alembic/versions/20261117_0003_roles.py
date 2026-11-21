"""RF-003: politicas de organizacion y controles basados en roles.

Revision ID: rbac_0003
Revises: auth_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "rbac_0003"
down_revision: Union[str, None] = "auth_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("requires_manual_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "organizations",
        sa.Column("max_discount_percent", sa.Numeric(precision=5, scale=2), nullable=False, server_default=sa.text("0.00")),
    )
    op.create_check_constraint(
        "ck_organizations_max_discount_range", "organizations",
        "max_discount_percent >= 0 AND max_discount_percent <= 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_organizations_max_discount_range", "organizations", type_="check")
    op.drop_column("organizations", "max_discount_percent")
    op.drop_column("organizations", "requires_manual_approval")
