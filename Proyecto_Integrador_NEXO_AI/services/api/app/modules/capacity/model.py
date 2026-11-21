"""RF-007: recursos productivos, dias habiles y excepciones por recurso y tenant."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
    Numeric, String, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductionResource(Base):
    __tablename__ = "production_resources"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_resources_org_code"),
        UniqueConstraint("id", "organization_id", name="uq_resources_id_org"),
        CheckConstraint("length(trim(code)) > 0", name="ck_resources_code_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_resources_name_nonempty"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_resources_unit_nonempty"),
        CheckConstraint("daily_capacity > 0", name="ck_resources_daily_capacity_positive"),
        CheckConstraint("length(trim(workdays_csv)) > 0", name="ck_resources_workdays_nonempty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    daily_capacity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    # 0=lunes ... 6=domingo. Lista ordenada/validada por esquemas Pydantic.
    workdays_csv: Mapped[str] = mapped_column(String(13), nullable=False, server_default=text("'0,1,2,3,4'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    @property
    def workdays(self) -> list[int]:
        return [int(part) for part in self.workdays_csv.split(",")]


class ResourceBlackout(Base):
    __tablename__ = "resource_blackouts"
    __table_args__ = (
        UniqueConstraint("resource_id", "day", name="uq_resource_blackouts_resource_day"),
        ForeignKeyConstraint(
            ["resource_id", "organization_id"],
            ["production_resources.id", "production_resources.organization_id"],
            name="fk_blackouts_resource_tenant", ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
