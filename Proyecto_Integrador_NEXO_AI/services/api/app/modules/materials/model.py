"""RF-006: existencias y receta de consumo por una unidad de producto.

Los FKs compuestos impiden relacionar productos y materiales de diferentes tenants,
incluso ante un error en la capa de servicio.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Numeric, String, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_materials_org_sku"),
        UniqueConstraint("id", "organization_id", name="uq_materials_id_org"),
        CheckConstraint("length(trim(sku)) > 0", name="ck_materials_sku_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_materials_name_nonempty"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_materials_unit_nonempty"),
        CheckConstraint("quantity_available >= 0", name="ck_materials_stock_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_available: Mapped[Decimal] = mapped_column(
        Numeric(15, 3), nullable=False, server_default=text("0.000")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProductMaterial(Base):
    __tablename__ = "product_materials"
    __table_args__ = (
        UniqueConstraint("product_id", "material_id", name="uq_product_materials_recipe"),
        ForeignKeyConstraint(
            ["product_id", "organization_id"], ["products.id", "products.organization_id"],
            name="fk_recipe_product_tenant", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["material_id", "organization_id"], ["materials.id", "materials.organization_id"],
            name="fk_recipe_material_tenant", ondelete="CASCADE",
        ),
        CheckConstraint("quantity_per_unit > 0", name="ck_recipe_positive_quantity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    material_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    quantity_per_unit: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
