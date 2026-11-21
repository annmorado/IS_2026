"""RF-008: borrador de pedido vinculado de manera fuerte a usuario y tenant."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric,
    String, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_orders_id_org"),
        UniqueConstraint('organization_id','created_by_user_id','idempotency_key',name='uq_order_org_actor_idempotency'),
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_orders_creator_tenant", ondelete="CASCADE",
        ),
        CheckConstraint("length(trim(raw_text)) > 0", name="ck_orders_raw_text_not_empty"),
        CheckConstraint("length(raw_text) <= 5000", name="ck_orders_raw_text_max_length"),
        CheckConstraint("status IN ('draft', 'pending', 'confirmed', 'in_progress', 'completed', 'cancelled')",
                        name="ck_orders_valid_status"),
        CheckConstraint("source IN ('manual', 'audio')", name="ck_orders_valid_source"),
        CheckConstraint("review_revision >= 0", name="ck_orders_review_revision_nonnegative"),
        CheckConstraint("reviewed_quantity IS NULL OR reviewed_quantity > 0", name="ck_orders_review_quantity_positive"),
        CheckConstraint("suggested_quantity IS NULL OR suggested_quantity > 0", name="ck_orders_suggested_quantity_positive"),
        CheckConstraint("status NOT IN ('confirmed', 'in_progress', 'completed') OR (reviewed_quantity IS NOT NULL AND reviewed_due_date IS NOT NULL AND reviewed_at IS NOT NULL AND reviewed_by_user_id IS NOT NULL AND confirmed_at IS NOT NULL AND confirmed_by_user_id IS NOT NULL)", name="ck_orders_confirmed_has_review"),
        ForeignKeyConstraint(["reviewed_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"], name="fk_orders_reviewer_tenant"),
        ForeignKeyConstraint(["confirmed_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"], name="fk_orders_confirmer_tenant"),
        Index("ix_orders_org_created", "organization_id", "created_at"),
        Index("ix_orders_org_status_created_id", "organization_id", "status", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    raw_text: Mapped[str] = mapped_column(String(5000), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'manual'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # RF-010: propuesta extraida (futura IA), separada de los valores humanos.
    suggested_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    suggested_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    reviewed_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
