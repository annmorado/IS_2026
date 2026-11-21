"""RF-013: cotizaciones con precios del catalogo, impuestos explicitos y versiones inmutables."""
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from app.modules.decisions.audit import canonical
from app.modules.decisions.keys import check_key
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.security import utc_now
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.products.model import Product
from app.modules.quotes.model import Quote, QuoteLine, QuoteTaxConfig
from app.modules.decisions.audit import audit
from app.modules.quotes.schemas import QuoteCreate, QuoteLineRead, QuoteRead, QuoteTaxRead, QuoteTotals
from app.modules.tenancy.scope import TenantScope

CENT = Decimal('0.01')
HUNDRED = Decimal('100')
MAX_MONEY = Decimal('99999999999999.99')


def money(amount: Decimal) -> Decimal:
    if not amount.is_finite():
        raise HTTPException(status_code=422, detail='Monto no finito')
    result = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(result) > MAX_MONEY:
        raise HTTPException(status_code=422, detail='Monto excede el limite monetario')
    return result


def read_tax_config(db: Session, scope: TenantScope) -> QuoteTaxRead:
    obj = db.get(QuoteTaxConfig, scope.organization_id)
    return QuoteTaxRead(configured=obj is not None, tax_percent=obj.tax_percent if obj else None)


def save_tax_config(db: Session, scope: TenantScope, tax_percent: Decimal) -> QuoteTaxRead:
    # El limite y el rol de propietario son comprobados en la API; nunca hay tasa implicita.
    obj = db.get(QuoteTaxConfig, scope.organization_id)
    previous_tax=str(obj.tax_percent) if obj is not None else None
    if obj is None:
        obj = QuoteTaxConfig(organization_id=scope.organization_id,
                             tax_percent=tax_percent, updated_by_user_id=scope.actor_id)
        db.add(obj)
    else:
        obj.tax_percent = tax_percent
        obj.updated_by_user_id = scope.actor_id
    audit(db, scope, entity_type='organization', entity_id=scope.organization_id,
          action='organization.tax_configured',
          before={'tax_percent':previous_tax},after={'tax_percent':str(tax_percent)})
    db.commit()
    return QuoteTaxRead(configured=True, tax_percent=tax_percent)


def get_scoped_order(db: Session, scope: TenantScope, order_id: UUID, lock: bool = False) -> Order:
    stmt = select(Order).where(Order.id == order_id, Order.organization_id == scope.organization_id)
    if lock:
        stmt = stmt.with_for_update()
    order = db.scalar(stmt)
    if order is None:
        raise HTTPException(status_code=404, detail='Pedido no encontrado')
    return order


def quote_totals(db: Session, scope: TenantScope, payload: QuoteCreate) -> QuoteTotals:
    config = db.get(QuoteTaxConfig, scope.organization_id)
    if config is None:
        raise HTTPException(status_code=409, detail='Configura explicitamente el impuesto antes de cotizar')
    org = db.get(Organization, scope.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail='Organizacion no encontrada')
    if payload.discount_percent > org.max_discount_percent:
        raise HTTPException(status_code=403, detail='Descuento supera el maximo autorizado por la organizacion')

    ids = [item.product_id for item in payload.items]
    product_rows = list(db.scalars(select(Product).where(
        Product.organization_id == scope.organization_id,
        Product.id.in_(ids), Product.is_active.is_(True),
    )).all())
    products = {item.id: item for item in product_rows}
    if len(products) != len(ids):
        raise HTTPException(status_code=404, detail='Producto inactivo, inexistente o de otra empresa')

    line_items = []
    for item in payload.items:
        product = products[item.product_id]
        qty = item.quantity
        unit_price = Decimal(product.price_mxn)
        unit_cost = Decimal(product.cost_mxn)
        line_items.append(QuoteLineRead(
            product_id=product.id, product_sku=product.sku, product_name=product.name,
            unit=product.unit, quantity=qty, unit_price=unit_price, unit_cost=unit_cost,
            line_subtotal=money(qty * unit_price), line_direct_cost=money(qty * unit_cost),
        ))
    subtotal = money(sum((line.line_subtotal for line in line_items), Decimal('0')))
    discount_amount = money(subtotal * payload.discount_percent / HUNDRED)
    taxable_base = money(subtotal - discount_amount)
    tax_amount = money(taxable_base * config.tax_percent / HUNDRED)
    total = money(taxable_base + tax_amount)
    direct_cost = money(sum((line.line_direct_cost for line in line_items), Decimal('0')))
    return QuoteTotals(currency='MXN', discount_percent=payload.discount_percent,
        tax_percent=config.tax_percent, subtotal=subtotal,
        discount_amount=discount_amount, taxable_base=taxable_base,
        tax_amount=tax_amount, total=total, direct_cost=direct_cost,
        estimated_gross_margin=money(taxable_base - direct_cost), items=line_items)


def preview_quote(db: Session, scope: TenantScope, payload: QuoteCreate) -> QuoteTotals:
    order = get_scoped_order(db, scope, payload.order_id)
    if order.status in {'cancelled', 'completed'}:
        raise HTTPException(status_code=409, detail='El estado del pedido no admite nuevas cotizaciones')
    return quote_totals(db, scope, payload)


def _render_quote(db: Session, quote: Quote) -> QuoteRead:
    lines = list(db.scalars(select(QuoteLine).where(
        QuoteLine.organization_id == quote.organization_id,
        QuoteLine.quote_id == quote.id,
    ).order_by(QuoteLine.product_sku, QuoteLine.id)).all())
    return QuoteRead(id=quote.id, organization_id=quote.organization_id,
        order_id=quote.order_id, version=quote.version, status=quote.status,
        created_by_user_id=quote.created_by_user_id,
        approved_by_user_id=quote.approved_by_user_id, created_at=quote.created_at,
        approved_at=quote.approved_at, currency='MXN', discount_percent=quote.discount_percent,
        tax_percent=quote.tax_percent, subtotal=quote.subtotal,
        discount_amount=quote.discount_amount, taxable_base=quote.taxable_base,
        tax_amount=quote.tax_amount, total=quote.total,
        direct_cost=quote.direct_cost, estimated_gross_margin=quote.estimated_gross_margin,
        items=[QuoteLineRead.model_validate({
            field: getattr(line, field) for field in QuoteLineRead.model_fields
        }) for line in lines])


def create_quote(db: Session, scope: TenantScope, payload: QuoteCreate,
                 idempotency_key: str | None = None) -> QuoteRead:
    fingerprint=None
    if idempotency_key is not None:
        check_key(idempotency_key)
        db.scalar(select(Organization).where(Organization.id==scope.organization_id).with_for_update())
        fingerprint=sha256(canonical(payload.model_dump(mode='json')).encode()).hexdigest()
        prev=db.scalar(select(Quote).where(Quote.organization_id==scope.organization_id,
            Quote.created_by_user_id==scope.actor_id,Quote.idempotency_key==idempotency_key))
        if prev is not None:
            if prev.idempotency_hash != fingerprint:
                raise HTTPException(409,detail='Idempotency-Key reutilizada con otra cotizacion')
            return _render_quote(db,prev)
    order = get_scoped_order(db, scope, payload.order_id, lock=True)
    if order.status in {'cancelled', 'completed'}:
        raise HTTPException(status_code=409, detail='Pedido terminado o cancelado')
    calculated = quote_totals(db, scope, payload)
    version = (db.scalar(select(func.max(Quote.version)).where(
        Quote.organization_id == scope.organization_id, Quote.order_id == order.id)) or 0) + 1
    quote = Quote(organization_id=scope.organization_id, order_id=order.id,
                  version=version, status='draft', created_by_user_id=scope.actor_id,
                  idempotency_key=idempotency_key,idempotency_hash=fingerprint,
                  discount_percent=calculated.discount_percent, tax_percent=calculated.tax_percent,
                  subtotal=calculated.subtotal, discount_amount=calculated.discount_amount,
                  taxable_base=calculated.taxable_base, tax_amount=calculated.tax_amount,
                  total=calculated.total, direct_cost=calculated.direct_cost,
                  estimated_gross_margin=calculated.estimated_gross_margin)
    db.add(quote)
    db.flush()
    for line in calculated.items:
        db.add(QuoteLine(quote_id=quote.id, organization_id=scope.organization_id,
                         **line.model_dump()))
    audit(db, scope, entity_type='quote', entity_id=quote.id, action='quote.created',
          after={'order_id':str(order.id),'status':'draft','version':version,
                 'total':str(calculated.total)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflicto al crear version de cotizacion') from exc
    db.refresh(quote)
    return _render_quote(db, quote)


def get_quote(db: Session, scope: TenantScope, quote_id: UUID, lock: bool = False) -> Quote:
    stmt = select(Quote).where(Quote.organization_id == scope.organization_id, Quote.id == quote_id)
    if lock:
        stmt = stmt.with_for_update()
    obj = db.scalar(stmt)
    if obj is None:
        raise HTTPException(status_code=404, detail='Cotizacion no encontrada')
    return obj


def read_quote(db: Session, scope: TenantScope, quote_id: UUID) -> QuoteRead:
    return _render_quote(db, get_quote(db, scope, quote_id))


def list_quotes(db: Session, scope: TenantScope, order_id: UUID) -> list[QuoteRead]:
    get_scoped_order(db, scope, order_id)
    quotes = db.scalars(select(Quote).where(
        Quote.organization_id == scope.organization_id, Quote.order_id == order_id,
    ).order_by(Quote.version.desc())).all()
    return [_render_quote(db, quote) for quote in quotes]


def approve_quote(db: Session, scope: TenantScope, quote_id: UUID) -> QuoteRead:
    obj = get_quote(db, scope, quote_id, lock=True)
    order = get_scoped_order(db, scope, obj.order_id, lock=True)
    if order.status in {'cancelled', 'completed'}:
        raise HTTPException(status_code=409, detail='El pedido ya no admite aprobar cotizaciones')
    if obj.status != 'draft':
        raise HTTPException(status_code=409, detail='Cotizacion ya aprobada')
    newest = db.scalar(select(func.max(Quote.version)).where(
        Quote.organization_id == scope.organization_id, Quote.order_id == obj.order_id))
    if obj.version != newest:
        raise HTTPException(status_code=409, detail='Solo se puede aprobar la version mas reciente')
    obj.status = 'approved'
    obj.approved_by_user_id = scope.actor_id
    obj.approved_at = utc_now()
    audit(db, scope, entity_type='quote', entity_id=obj.id, action='quote.approved',
          before={'status':'draft'}, after={'status':'approved','version':obj.version,
                                          'total':str(obj.total)})
    db.commit()
    db.refresh(obj)
    return _render_quote(db, obj)
