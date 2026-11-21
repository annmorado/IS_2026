"""RF-011: estados permitidos, registro atomico y lectura con aislamiento de tenant.

Confirmar es exclusivo del endpoint de RF-010: exige revision humana guardada.
Un operador puede cambiar solamente solicitudes propias; el propietario, todas las de su empresa.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.security import utc_now
from app.modules.orders.model import Order
from app.modules.orders.service import get_order
from app.modules.order_status.model import OrderStatusEvent
from app.modules.decisions.audit import audit
from app.modules.order_status.schemas import StatusRead, StatusTransitionRequest, TransitionResult
from app.modules.tenancy.scope import TenantScope

# No se permite reabrir pedidos completados o cancelados, ni pasar directamente a completado.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("pending", "cancelled"),
    "pending": ("draft", "cancelled"),
    "confirmed": ("in_progress", "cancelled"),
    "in_progress": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}


def status_view(order: Order) -> StatusRead:
    return StatusRead(
        order_id=order.id, status=order.status,
        allowed_next=list(TRANSITIONS[order.status]),
        review_revision=order.review_revision,
    )


def get_status(db: Session, scope: TenantScope, order_id: UUID) -> StatusRead:
    return status_view(get_order(db, scope, order_id))


def write_status_event(db: Session, scope: TenantScope, order: Order, *,
                       previous: str, new: str, note: str | None = None) -> OrderStatusEvent:
    """Anade historial a la misma transaccion; el invocador hace commit una sola vez."""
    if previous == new:
        raise ValueError("Debe cambiar el estado")
    event = OrderStatusEvent(
        organization_id=scope.organization_id,
        order_id=order.id,
        changed_by_user_id=scope.actor_id,
        from_status=previous,
        to_status=new,
        changed_at=utc_now(),
        note=note,
    )
    db.add(event)
    return event


def transition_order(db: Session, scope: TenantScope, order_id: UUID, *,
                     payload: StatusTransitionRequest, role: str) -> TransitionResult:
    order = get_order(db, scope, order_id, lock=True)
    if role != "owner" and order.created_by_user_id != scope.actor_id:
        raise HTTPException(status_code=403, detail="Solo puedes administrar tus propias solicitudes")
    if order.status != payload.expected_status:
        raise HTTPException(status_code=409, detail="El estado cambio. Recarga la solicitud")
    if payload.to_status == "confirmed":
        raise HTTPException(status_code=409, detail="Usa /orders/{id}/confirm tras guardar la revision humana")
    if payload.to_status not in TRANSITIONS[order.status]:
        raise HTTPException(status_code=409, detail="Transicion de estado no permitida")
    previous = order.status
    order.status = payload.to_status
    event = write_status_event(db, scope, order, previous=previous,
                               new=payload.to_status, note=payload.note)
    audit(db, scope, entity_type='order', entity_id=order.id,
          action='order.status_changed',before={'status':previous},
          after={'status':payload.to_status,'note':payload.note})
    db.commit()
    db.refresh(order)
    db.refresh(event)
    return TransitionResult(order=status_view(order), event=event)


def get_history(db: Session, scope: TenantScope, order_id: UUID, *,
                limit: int, offset: int) -> list[OrderStatusEvent]:
    # Primero comprobar el recurso tenant-scoped; nunca revelar historial cross-tenant.
    get_order(db, scope, order_id)
    stmt = select(OrderStatusEvent).where(
        OrderStatusEvent.organization_id == scope.organization_id,
        OrderStatusEvent.order_id == order_id,
    ).order_by(OrderStatusEvent.changed_at.desc(), OrderStatusEvent.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())
