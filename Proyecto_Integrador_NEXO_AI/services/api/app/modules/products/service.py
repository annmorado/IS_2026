"""Servicios con alcance de tenant en cada consulta y operacion de escritura."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.decisions.audit import audit

from app.modules.products.model import Product
from app.modules.products.schemas import ProductCreate, ProductPatch
from app.modules.tenancy.scope import TenantScope


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Producto no encontrado")


def _conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="SKU ya registrado en esta organizacion")


def get_scoped_product(db: Session, *, scope: TenantScope, product_id: UUID, lock: bool = False) -> Product:
    stmt = select(Product).where(
        Product.id == product_id,
        Product.organization_id == scope.organization_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    product = db.scalar(stmt)
    if product is None:
        raise _not_found()
    return product


def list_scoped_products(
    db: Session, *, scope: TenantScope, include_inactive: bool = False,
    limit: int = 50, offset: int = 0,
) -> list[Product]:
    stmt = select(Product).where(Product.organization_id == scope.organization_id)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    return list(db.scalars(
        stmt.order_by(Product.name, Product.id).limit(limit).offset(offset)
    ).all())


def list_quotable_products(
    db: Session, *, scope: TenantScope, limit: int = 50, offset: int = 0,
) -> list[Product]:
    """Punto de integracion futuro para cotizaciones: NO incluir inactivos."""
    return list_scoped_products(db, scope=scope, include_inactive=False, limit=limit, offset=offset)


def get_quotable_product(db: Session, *, scope: TenantScope, product_id: UUID) -> Product:
    product = get_scoped_product(db, scope=scope, product_id=product_id)
    if not product.is_active:
        raise _not_found()
    return product


def create_scoped_product(db: Session, *, scope: TenantScope, payload: ProductCreate) -> Product:
    product = Product(organization_id=scope.organization_id, **payload.model_dump())
    db.add(product)
    try:
        db.flush()
        audit(db, scope, entity_type='product', entity_id=product.id, action='product.created',
              after={'sku':product.sku,'name':product.name,'price_mxn':str(product.price_mxn),'cost_mxn':str(product.cost_mxn)})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict() from exc
    db.refresh(product)
    return product


def patch_scoped_product(
    db: Session, *, scope: TenantScope, product_id: UUID, changes: ProductPatch,
) -> Product:
    product = get_scoped_product(db, scope=scope, product_id=product_id, lock=True)
    fields=changes.model_dump(exclude_unset=True)
    before={k:str(getattr(product,k)) for k in fields}
    for key, value in fields.items():
        setattr(product, key, value)
    audit(db, scope, entity_type='product', entity_id=product.id, action='product.updated',
          before=before,after={k:str(getattr(product,k)) for k in fields})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _conflict() from exc
    db.refresh(product)
    return product


def deactivate_scoped_product(db: Session, *, scope: TenantScope, product_id: UUID) -> Product:
    product = get_scoped_product(db, scope=scope, product_id=product_id, lock=True)
    product.is_active = False
    audit(db, scope, entity_type='product', entity_id=product.id, action='product.deactivated',
          before={'is_active':True},after={'is_active':False})
    db.commit()
    db.refresh(product)
    return product
