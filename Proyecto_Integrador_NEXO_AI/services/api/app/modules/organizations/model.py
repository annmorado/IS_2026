from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("currency = 'MXN'", name="ck_organizations_currency_mxn"),
        CheckConstraint("length(trim(name)) > 0", name="ck_organizations_name_not_empty"),
        CheckConstraint("length(trim(sector)) > 0", name="ck_organizations_sector_not_empty"),
        CheckConstraint("max_discount_percent >= 0 AND max_discount_percent <= 100", name="ck_organizations_max_discount_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sector: Mapped[str] = mapped_column(String(80), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'MXN'"))
    requires_manual_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    max_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
