"""Metadatos de notas de voz: archivo fuera de la BD y propiedad comprobada en BD."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VoiceNote(Base):
    __tablename__ = "voice_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["created_by_user_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name="fk_voice_notes_author_tenant", ondelete="CASCADE",
        ),
        CheckConstraint("byte_size > 0 AND byte_size <= 10485760", name="ck_voice_notes_size"),
        CheckConstraint("duration_ms IS NULL OR (duration_ms >= 0 AND duration_ms <= 3600000)",
                        name="ck_voice_notes_duration"),
        CheckConstraint("length(sha256_hex) = 64", name="ck_voice_notes_sha256_length"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
