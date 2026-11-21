"""Modelos persistentes para decisiones explícitas y registro de auditoría."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer,
    String, Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DecisionRecommendation(Base):
    __tablename__ = "decision_recommendations"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_decision_id_org"),
        UniqueConstraint("organization_id", "created_by_user_id", "create_key", name="uq_decision_create_key"),
        UniqueConstraint("organization_id", "confirmation_key", name="uq_decision_confirmation_key"),
        ForeignKeyConstraint(["order_id", "organization_id"],
                             ["orders.id", "orders.organization_id"],
                             name="fk_decision_order_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["created_by_user_id", "organization_id"],
                             ["users.id", "users.organization_id"],
                             name="fk_decision_creator_tenant", ondelete="CASCADE"),
        ForeignKeyConstraint(["confirmed_by_user_id", "organization_id"],
                             ["users.id", "users.organization_id"],
                             name="fk_decision_confirmer_tenant", ondelete="CASCADE"),
        CheckConstraint("status IN ('proposed','applied','rejected')", name="ck_decision_status"),
        CheckConstraint("expected_review_revision >= 0", name="ck_decision_revision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
                       ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'rf017-v1'"))
    create_key: Mapped[str] = mapped_column(String(128), nullable=False)
    create_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_review_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_order_status: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'proposed'"))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_key: Mapped[str | None] = mapped_column(String(128))
    confirmation_hash: Mapped[str | None] = mapped_column(String(64))
    exception_reason: Mapped[str | None] = mapped_column(String(500))
    applied_json: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    """Registro append-only. La migración impide UPDATE/DELETE en PostgreSQL."""
    __tablename__ = "business_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["actor_user_id", "organization_id"],
                             ["users.id", "users.organization_id"],
                             name="fk_audit_actor_tenant", ondelete="CASCADE"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
                       ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
