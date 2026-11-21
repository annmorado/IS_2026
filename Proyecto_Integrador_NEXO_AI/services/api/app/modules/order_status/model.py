"""Historial inmutable de cada transicion, con referencias tenant-safe."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS_SQL = "'draft', 'pending', 'confirmed', 'in_progress', 'completed', 'cancelled'"


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "organization_id"], ["orders.id", "orders.organization_id"],
            name="fk_order_events_order_tenant", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["changed_by_user_id", "organization_id"], ["users.id", "users.organization_id"],
            name="fk_order_events_user_tenant",
        ),
        CheckConstraint(f"from_status IN ({STATUS_SQL})", name="ck_order_events_from_status"),
        CheckConstraint(f"to_status IN ({STATUS_SQL})", name="ck_order_events_to_status"),
        CheckConstraint("from_status <> to_status", name="ck_order_events_status_changed"),
        Index("ix_order_events_org_order_date", "organization_id", "order_id", "changed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
