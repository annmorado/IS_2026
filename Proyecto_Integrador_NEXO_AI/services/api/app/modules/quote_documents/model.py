"""Documento PDF inmutable y folio unico por organizacion.

El PDF completo se guarda en PostgreSQL para preservar el documento aprobado.
"""
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
                        Integer, LargeBinary, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuoteDocument(Base):
    __tablename__ = 'quote_documents'
    __table_args__ = (
        UniqueConstraint('quote_id', 'organization_id', name='uq_quote_doc_quote_org'),
        UniqueConstraint('organization_id', 'sequence_number', name='uq_quote_doc_org_seq'),
        UniqueConstraint('folio', name='uq_quote_doc_folio'),
        ForeignKeyConstraint(['quote_id', 'organization_id'],
            ['quotes.id', 'quotes.organization_id'],
            name='fk_quote_doc_quote_tenant', ondelete='CASCADE'),
        ForeignKeyConstraint(['generated_by_user_id', 'organization_id'],
            ['users.id', 'users.organization_id'], name='fk_quote_doc_actor_tenant'),
        CheckConstraint('sequence_number > 0', name='ck_quote_doc_sequence_positive'),
        CheckConstraint('size_bytes > 100', name='ck_quote_doc_size_positive'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    quote_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    folio: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    generated_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
