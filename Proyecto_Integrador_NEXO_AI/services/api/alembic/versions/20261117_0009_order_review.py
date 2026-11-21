"""RF-010: propuestas y valores revisados, antes de la confirmacion.

Revision ID: review_0009
Revises: voice_0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "review_0009"
down_revision: Union[str, None] = "voice_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("suggested_quantity", sa.Numeric(12, 3), nullable=True))
    op.add_column("orders", sa.Column("suggested_due_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("reviewed_quantity", sa.Numeric(12, 3), nullable=True))
    op.add_column("orders", sa.Column("reviewed_due_date", sa.Date(), nullable=True))
    op.add_column("orders", sa.Column("reviewed_by_user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("orders", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("confirmed_by_user_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("orders", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("review_revision", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.create_check_constraint("ck_orders_review_revision_nonnegative", "orders", "review_revision >= 0")
    op.create_check_constraint("ck_orders_review_quantity_positive", "orders",
                               "reviewed_quantity IS NULL OR reviewed_quantity > 0")
    op.create_check_constraint("ck_orders_suggested_quantity_positive", "orders",
                               "suggested_quantity IS NULL OR suggested_quantity > 0")
    op.create_check_constraint("ck_orders_confirmed_has_review", "orders",
                               "status <> 'confirmed' OR (reviewed_quantity IS NOT NULL AND reviewed_due_date IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL AND confirmed_by_user_id IS NOT NULL)")
    op.create_foreign_key("fk_orders_reviewer_tenant", "orders", "users",
                          ["reviewed_by_user_id", "organization_id"], ["id", "organization_id"])
    op.create_foreign_key("fk_orders_confirmer_tenant", "orders", "users",
                          ["confirmed_by_user_id", "organization_id"], ["id", "organization_id"])


def downgrade() -> None:
    op.drop_constraint("fk_orders_confirmer_tenant", "orders", type_="foreignkey")
    op.drop_constraint("fk_orders_reviewer_tenant", "orders", type_="foreignkey")
    op.drop_constraint("ck_orders_confirmed_has_review", "orders", type_="check")
    op.drop_constraint("ck_orders_suggested_quantity_positive", "orders", type_="check")
    op.drop_constraint("ck_orders_review_quantity_positive", "orders", type_="check")
    op.drop_constraint("ck_orders_review_revision_nonnegative", "orders", type_="check")
    for col in ["review_revision", "confirmed_at", "confirmed_by_user_id", "reviewed_at",
                "reviewed_by_user_id", "reviewed_due_date", "reviewed_quantity",
                "suggested_due_date", "suggested_quantity"]:
        op.drop_column("orders", col)
