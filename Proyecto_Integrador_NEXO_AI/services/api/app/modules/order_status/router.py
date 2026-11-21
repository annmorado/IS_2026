"""RF-011: lectura de estado, transiciones y auditoria por pedido."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.order_status.schemas import StatusEventRead, StatusRead, StatusTransitionRequest, TransitionResult
from app.modules.order_status.service import get_history, get_status, transition_order
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/orders", tags=["RF-011 Estados de pedido"])


@router.get("/{order_id}/status", response_model=StatusRead)
def read_status(order_id: UUID, context: AuthContext = Depends(require_staff),
                db: Session = Depends(get_db)):
    return get_status(db, scope_from_context(context), order_id)


@router.post("/{order_id}/status", response_model=TransitionResult)
def change_status(order_id: UUID, payload: StatusTransitionRequest,
                  context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return transition_order(db, scope_from_context(context), order_id,
                            payload=payload, role=context.user.role)


@router.get("/{order_id}/history", response_model=list[StatusEventRead])
def read_history(order_id: UUID, limit: int = Query(50, ge=1, le=100),
                 offset: int = Query(0, ge=0), context: AuthContext = Depends(require_staff),
                 db: Session = Depends(get_db)):
    return get_history(db, scope_from_context(context), order_id, limit=limit, offset=offset)
