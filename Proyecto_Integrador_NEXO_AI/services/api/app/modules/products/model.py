"""Producto con identidad global, SKU unico por empresa y dinero decimal en MXN."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint,
    Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_products_org_sku"),
        UniqueConstraint("id", "organization_id", name="uq_products_id_org"),
        CheckConstraint("length(trim(sku)) > 0", name="ck_products_sku_not_empty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_products_name_not_empty"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_products_unit_not_empty"),
        CheckConstraint("cost_mxn >= 0", name="ck_products_nonnegative_cost"),
        CheckConstraint("price_mxn >= 0", name="ck_products_nonnegative_price"),
        CheckConstraint("base_production_minutes > 0", name="ck_products_positive_minutes"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    cost_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_mxn: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_production_minutes: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
