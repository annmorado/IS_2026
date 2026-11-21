"""RF-008: captura manual de solicitudes; sin confirmar ni procesar pedidos."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.orders.schemas import OrderCreate, OrderPatch, OrderRead
from app.modules.orders.service import create_order, get_order, list_orders, patch_order
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/orders", tags=["RF-008 Solicitudes manuales"])


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create(payload: OrderCreate, context: AuthContext = Depends(require_staff),
           idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
           db: Session = Depends(get_db)):
    return create_order(db, scope_from_context(context), payload, idempotency_key=idempotency_key)


@router.get("", response_model=list[OrderRead])
def list_all(only_mine: bool = False, limit: int = Query(50, ge=1, le=100),
             offset: int = Query(0, ge=0), context: AuthContext = Depends(require_staff),
             db: Session = Depends(get_db)):
    return list_orders(db, scope_from_context(context), only_mine=only_mine, limit=limit, offset=offset)


@router.get("/{order_id}", response_model=OrderRead)
def read(order_id: UUID, context: AuthContext = Depends(require_staff),
         db: Session = Depends(get_db)):
    return get_order(db, scope_from_context(context), order_id)


@router.patch("/{order_id}", response_model=OrderRead)
def update(order_id: UUID, payload: OrderPatch,
           context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return patch_order(db, scope_from_context(context), order_id, payload, role=context.user.role)
