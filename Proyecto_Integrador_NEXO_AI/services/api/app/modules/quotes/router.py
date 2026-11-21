"""RF-013: cotizaciones y politica de impuesto, siempre bajo JWT y tenant."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner, require_staff
from app.modules.tenancy.scope import scope_from_context
from app.modules.quotes.schemas import QuoteCreate, QuoteRead, QuoteTaxRead, QuoteTaxUpdate, QuoteTotals
from app.modules.quotes.service import (
    approve_quote, create_quote, list_quotes, preview_quote, read_quote,
    read_tax_config, save_tax_config,
)

router = APIRouter(prefix='/quotes', tags=['RF-013 Costeo y cotizacion'])

@router.get('/tax-config', response_model=QuoteTaxRead)
def get_tax(context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return read_tax_config(db, scope_from_context(context))

@router.put('/tax-config', response_model=QuoteTaxRead)
def put_tax(payload: QuoteTaxUpdate, context: AuthContext = Depends(require_owner),
            db: Session = Depends(get_db)):
    return save_tax_config(db, scope_from_context(context), payload.tax_percent)

@router.post('/preview', response_model=QuoteTotals)
def preview(payload: QuoteCreate, context: AuthContext = Depends(require_staff),
            db: Session = Depends(get_db)):
    return preview_quote(db, scope_from_context(context), payload)

@router.post('', response_model=QuoteRead, status_code=status.HTTP_201_CREATED)
def create(payload: QuoteCreate, context: AuthContext = Depends(require_staff),
           idempotency_key: str | None = Header(default=None,alias='Idempotency-Key'),
           db: Session = Depends(get_db)):
    return create_quote(db, scope_from_context(context), payload, idempotency_key=idempotency_key)

@router.get('', response_model=list[QuoteRead])
def all_for_order(order_id: UUID, context: AuthContext = Depends(require_staff),
                  db: Session = Depends(get_db)):
    return list_quotes(db, scope_from_context(context), order_id)

@router.get('/{quote_id}', response_model=QuoteRead)
def get(quote_id: UUID, context: AuthContext = Depends(require_staff),
        db: Session = Depends(get_db)):
    return read_quote(db, scope_from_context(context), quote_id)

@router.post('/{quote_id}/approve', response_model=QuoteRead)
def approve(quote_id: UUID, context: AuthContext = Depends(require_owner),
            db: Session = Depends(get_db)):
    return approve_quote(db, scope_from_context(context), quote_id)
