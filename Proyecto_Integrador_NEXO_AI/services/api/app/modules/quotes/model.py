"""RF-013: impuestos configurados, cotizaciones versionadas y partidas inmutables."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer,
    Numeric, String, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class QuoteTaxConfig(Base):
    __tablename__ = "quote_tax_configs"
    __table_args__ = (
        CheckConstraint("tax_percent >= 0 AND tax_percent <= 100", name="ck_quote_tax_range"),
        ForeignKeyConstraint(["updated_by_user_id", "organization_id"],
                             ["users.id", "users.organization_id"], name="fk_quote_tax_editor_tenant"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now(), onupdate=func.now())


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_quotes_id_org"),
        UniqueConstraint('organization_id','created_by_user_id','idempotency_key',name='uq_quote_org_actor_idempotency'),
        UniqueConstraint("organization_id", "order_id", "version", name="uq_quotes_org_order_version"),
        ForeignKeyConstraint(["order_id", "organization_id"], ["orders.id", "orders.organization_id"],
                             name="fk_quotes_order_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["created_by_user_id", "organization_id"],
                             ["users.id", "users.organization_id"], name="fk_quotes_creator_tenant"),
        ForeignKeyConstraint(["approved_by_user_id", "organization_id"],
                             ["users.id", "users.organization_id"], name="fk_quotes_approver_tenant"),
        CheckConstraint("version >= 1", name="ck_quotes_positive_version"),
        CheckConstraint("status IN ('draft', 'approved')", name="ck_quotes_status"),
        CheckConstraint("discount_percent >= 0 AND discount_percent <= 100", name="ck_quotes_discount_range"),
        CheckConstraint("tax_percent >= 0 AND tax_percent <= 100", name="ck_quotes_tax_range"),
        CheckConstraint("subtotal >= 0 AND discount_amount >= 0 AND taxable_base >= 0 AND tax_amount >= 0 AND total >= 0", name="ck_quotes_nonnegative_money"),
        CheckConstraint("direct_cost >= 0", name="ck_quotes_nonnegative_cost"),
        CheckConstraint("(status = 'draft' AND approved_by_user_id IS NULL AND approved_at IS NULL) OR (status = 'approved' AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)", name="ck_quotes_approval_consistent"),
        Index("ix_quotes_org_order_version", "organization_id", "order_id", "version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'MXN'"))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    taxable_base: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    direct_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    estimated_gross_margin: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QuoteLine(Base):
    __tablename__ = "quote_lines"
    __table_args__ = (
        ForeignKeyConstraint(["quote_id", "organization_id"], ["quotes.id", "quotes.organization_id"],
                             name="fk_quote_lines_quote_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["product_id", "organization_id"], ["products.id", "products.organization_id"],
                             name="fk_quote_lines_product_tenant"),
        UniqueConstraint("quote_id", "product_id", name="uq_quote_lines_product"),
        CheckConstraint("quantity > 0", name="ck_quote_lines_positive_quantity"),
        CheckConstraint("unit_price >= 0 AND unit_cost >= 0 AND line_subtotal >= 0 AND line_direct_cost >= 0", name="ck_quote_lines_nonnegative_money"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    line_direct_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
