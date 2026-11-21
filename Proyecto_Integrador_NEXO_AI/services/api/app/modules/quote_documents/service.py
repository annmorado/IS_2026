"""RF-014: emision de PDF con snapshot, folio exclusivo y control de tenant."""
from datetime import date, timedelta, datetime, timezone
from hashlib import sha256
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.organizations.model import Organization
from app.modules.quotes.model import Quote, QuoteLine
from app.modules.quotes.service import get_quote
from app.modules.quote_documents.model import QuoteDocument
from app.modules.quote_documents.pdf import render_quote_pdf
from app.modules.quote_documents.schemas import DocumentRead
from app.modules.decisions.audit import audit
from app.modules.tenancy.scope import TenantScope


def _read(db: Session, scope: TenantScope, quote_id: UUID):
    quote = get_quote(db, scope, quote_id)
    doc = db.scalar(select(QuoteDocument).where(
        QuoteDocument.organization_id == scope.organization_id,
        QuoteDocument.quote_id == quote_id))
    return quote, doc


def _metadata(quote: Quote, doc: QuoteDocument) -> DocumentRead:
    return DocumentRead(id=doc.id,quote_id=doc.quote_id,order_id=quote.order_id,
        organization_id=doc.organization_id,quote_version=quote.version,
        folio=doc.folio,valid_until=doc.valid_until,generated_at=doc.generated_at,
        generated_by_user_id=doc.generated_by_user_id,sha256=doc.sha256,
        size_bytes=doc.size_bytes,download_path=f'/quotes/{quote.id}/pdf')


def read_document(db: Session, scope: TenantScope, quote_id: UUID) -> DocumentRead:
    quote, doc = _read(db, scope, quote_id)
    if doc is None:
        raise HTTPException(status_code=404,detail='PDF de cotizacion no generado')
    return _metadata(quote, doc)


def read_pdf(db: Session, scope: TenantScope, quote_id: UUID) -> tuple[str,bytes]:
    _, doc = _read(db, scope, quote_id)
    if doc is None:
        raise HTTPException(status_code=404,detail='PDF de cotizacion no generado')
    return doc.folio, bytes(doc.pdf_bytes)


def create_document(db: Session, scope: TenantScope, quote_id: UUID, valid_until: date) -> DocumentRead:
    # SERIALIZA emisiones por organizacion para impedir folios repetidos bajo concurrencia.
    org = db.scalar(select(Organization).where(Organization.id == scope.organization_id).with_for_update())
    if org is None:
        raise HTTPException(status_code=404,detail='Organizacion no encontrada')
    quote = get_quote(db, scope, quote_id, lock=True)
    if quote.status != 'approved' or quote.approved_at is None:
        raise HTTPException(status_code=409,detail='Solo se emite PDF de cotizaciones aprobadas')
    previous = db.scalar(select(QuoteDocument).where(
        QuoteDocument.organization_id == scope.organization_id,
        QuoteDocument.quote_id == quote.id))
    if previous is not None:
        if previous.valid_until != valid_until:
            raise HTTPException(status_code=409,detail='El PDF ya fue emitido con otra vigencia; no se sobrescribe')
        return _metadata(quote,previous)

    try:
        today = datetime.now(ZoneInfo(org.timezone)).date()
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422,detail='Zona horaria de organizacion no reconocida') from exc
    if not today <= valid_until <= today + timedelta(days=365):
        raise HTTPException(status_code=422,detail='Vigencia entre hoy y 365 dias en zona horaria de la empresa')

    next_number = (db.scalar(select(func.max(QuoteDocument.sequence_number)).where(
        QuoteDocument.organization_id == scope.organization_id)) or 0) + 1
    issued = datetime.now(timezone.utc)
    folio = f'NEXO-{org.id.hex[:8].upper()}-{next_number:06d}'
    lines = list(db.scalars(select(QuoteLine).where(
        QuoteLine.organization_id == scope.organization_id, QuoteLine.quote_id == quote.id,
    ).order_by(QuoteLine.product_sku, QuoteLine.id)).all())
    pdf = render_quote_pdf(organization_name=org.name,quote=quote,lines=lines,
        folio=folio,valid_until=valid_until,generated_at=issued)
    if not pdf.startswith(b'%PDF-'):
        raise RuntimeError('Generador PDF devolvio bytes invalidos')
    obj = QuoteDocument(organization_id=scope.organization_id,quote_id=quote.id,
        sequence_number=next_number,folio=folio,valid_until=valid_until,
        generated_by_user_id=scope.actor_id,generated_at=issued,
        sha256=sha256(pdf).hexdigest(),size_bytes=len(pdf),pdf_bytes=pdf)
    db.add(obj)
    db.flush()
    audit(db, scope, entity_type='quote_document', entity_id=obj.id,
          action='quote_document.issued',after={'quote_id':str(quote.id),
          'folio':folio,'sha256':obj.sha256,'valid_until':str(valid_until)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409,detail='Conflicto concurrente al emitir folio') from exc
    db.refresh(obj)
    return _metadata(quote,obj)
