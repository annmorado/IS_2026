"""RF-005: CRUD restringido por rol y tenant para el catálogo."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner, require_staff
from app.modules.products.schemas import ProductCreate, ProductPatch, ProductRead
from app.modules.products.service import (
    create_scoped_product, deactivate_scoped_product, get_scoped_product,
    list_quotable_products, list_scoped_products, patch_scoped_product,
)
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/products", tags=["RF-005 Catálogo de productos"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    context: AuthContext = Depends(require_owner), db: Session = Depends(get_db),
):
    return create_scoped_product(db, scope=scope_from_context(context), payload=payload)


@router.get("", response_model=list[ProductRead])
def list_products(
    include_inactive: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db),
):
    return list_scoped_products(
        db, scope=scope_from_context(context), include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/quotable", response_model=list[ProductRead])
def list_products_eligible_for_quotes(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db),
):
    return list_quotable_products(db, scope=scope_from_context(context), limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductRead)
def read_product(
    product_id: UUID,
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db),
):
    return get_scoped_product(db, scope=scope_from_context(context), product_id=product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: UUID, changes: ProductPatch,
    context: AuthContext = Depends(require_owner), db: Session = Depends(get_db),
):
    return patch_scoped_product(
        db, scope=scope_from_context(context), product_id=product_id, changes=changes,
    )


@router.post("/{product_id}/deactivate", response_model=ProductRead)
def deactivate_product(
    product_id: UUID,
    context: AuthContext = Depends(require_owner), db: Session = Depends(get_db),
):
    return deactivate_scoped_product(db, scope=scope_from_context(context), product_id=product_id)
