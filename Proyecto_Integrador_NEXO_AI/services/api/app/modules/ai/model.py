"""Tenant-isolated evidence for supervised speech and intake recommendations."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Integer, String, Text, UniqueConstraint, Uuid, func, text)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class TranscriptionJob(Base):
    __tablename__ = "ai_transcription_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "voice_note_id", name="uq_ai_transcription_note_tenant"),
        ForeignKeyConstraint(["actor_id", "organization_id"], ["users.id", "users.organization_id"],
                             name="fk_ai_transcript_actor_tenant"),
        CheckConstraint("status IN ('queued','processing','completed','failed','cancelled','reviewed')",
                        name="ck_ai_transcription_status"),
        CheckConstraint("attempt_count >= 1 AND attempt_count <= 3", name="ck_ai_transcription_attempts"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    voice_note_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("voice_notes.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    engine: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'whisper-local'"))
    language: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'es'"))
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StructuredExtraction(Base):
    __tablename__ = "ai_structured_extractions"
    __table_args__ = (
        ForeignKeyConstraint(["actor_id", "organization_id"], ["users.id", "users.organization_id"],
                             name="fk_ai_extract_actor_tenant"),
        CheckConstraint("length(trim(source_text)) > 0 AND length(source_text) <= 5000",
                        name="ck_ai_source_length"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_text: Mapped[str] = mapped_column(String(5000), nullable=False)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FulfillmentEstimate(Base):
    __tablename__ = "ai_fulfillment_estimates"
    __table_args__ = (
        ForeignKeyConstraint(["actor_id", "organization_id"], ["users.id", "users.organization_id"],
                             name="fk_ai_estimate_actor_tenant"),
        ForeignKeyConstraint(["product_id", "organization_id"],
                             ["products.id", "products.organization_id"],name="fk_ai_estimate_product_tenant"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
