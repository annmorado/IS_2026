"""RF-010: guardar correcciones explicitamente antes de confirmar.

RF-010 no interpreta audio ni texto con IA. El punto de integracion
`stage_suggested_extraction` recibe sugerencias futuras del pipeline IA,
pero no queda expuesto como endpoint publico que un cliente pueda falsificar.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.auth.security import utc_now
from app.modules.orders.model import Order
from app.modules.orders.service import get_order
from app.modules.order_status.service import write_status_event
from app.modules.decisions.audit import audit
from app.modules.review.schemas import ReviewRead, ReviewSave
from app.modules.tenancy.scope import TenantScope


def _can_edit(order: Order, scope: TenantScope, role: str) -> None:
    if role != "owner" and order.created_by_user_id != scope.actor_id:
        raise HTTPException(status_code=403, detail="Solo puedes revisar tus propias solicitudes")


def _reviewable(order: Order) -> None:
    if order.status not in {"draft", "pending"}:
        raise HTTPException(status_code=409, detail="El pedido ya no admite revision")


def review_view(order: Order) -> ReviewRead:
    return ReviewRead(
        id=order.id, organization_id=order.organization_id,
        created_by_user_id=order.created_by_user_id,
        raw_text=order.raw_text, status=order.status,
        suggested_quantity=order.suggested_quantity,
        suggested_due_date=order.suggested_due_date,
        reviewed_quantity=order.reviewed_quantity,
        reviewed_due_date=order.reviewed_due_date,
        reviewed_at=order.reviewed_at,
        reviewed_by_user_id=order.reviewed_by_user_id,
        confirmed_at=order.confirmed_at,
        confirmed_by_user_id=order.confirmed_by_user_id,
        review_revision=order.review_revision,
        requires_manual_review=(order.status in {"draft", "pending"}),
    )


def get_review(db: Session, scope: TenantScope, order_id: UUID) -> ReviewRead:
    return review_view(get_order(db, scope, order_id))


def save_review(db: Session, scope: TenantScope, order_id: UUID,
                payload: ReviewSave, *, role: str) -> ReviewRead:
    order = get_order(db, scope, order_id, lock=True)
    _can_edit(order, scope, role)
    _reviewable(order)
    if order.review_revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="La revision cambio. Vuelve a abrir el formulario")
    before={'reviewed_quantity':str(order.reviewed_quantity) if order.reviewed_quantity else None,
            'reviewed_due_date':str(order.reviewed_due_date) if order.reviewed_due_date else None,
            'review_revision':order.review_revision}
    order.reviewed_quantity = payload.quantity
    order.reviewed_due_date = payload.due_date
    order.reviewed_by_user_id = scope.actor_id
    order.reviewed_at = utc_now()
    order.review_revision += 1
    audit(db, scope, entity_type='order', entity_id=order.id, action='order.reviewed',
          before=before,after={'reviewed_quantity':str(payload.quantity),
             'reviewed_due_date':str(payload.due_date),'review_revision':order.review_revision})
    db.commit()
    db.refresh(order)
    return review_view(order)


def confirm_review(db: Session, scope: TenantScope, order_id: UUID, *,
                   expected_revision: int, role: str) -> ReviewRead:
    order = get_order(db, scope, order_id, lock=True)
    _can_edit(order, scope, role)
    _reviewable(order)
    if order.review_revision != expected_revision:
        raise HTTPException(status_code=409, detail="La revision cambio. Vuelve a abrir el formulario")
    if (order.reviewed_quantity is None or order.reviewed_due_date is None or
            order.reviewed_by_user_id is None or order.reviewed_at is None):
        raise HTTPException(status_code=409, detail="Debes guardar los datos revisados antes de confirmar")
    # La confirmacion toma SOLO los valores corregidos, no la propuesta IA.
    previous_status = order.status
    order.status = "confirmed"
    order.confirmed_by_user_id = scope.actor_id
    order.confirmed_at = utc_now()
    write_status_event(db, scope, order, previous=previous_status, new="confirmed",
                       note="Confirmacion humana RF-010")
    audit(db, scope, entity_type='order', entity_id=order.id, action='order.confirmed',
          before={'status':previous_status},after={'status':'confirmed',
               'review_revision':order.review_revision})
    db.commit()
    db.refresh(order)
    return review_view(order)


def stage_suggested_extraction(db: Session, scope: TenantScope, order_id: UUID, *,
                               quantity: Decimal | None, due_date: date | None) -> ReviewRead:
    """Punto interno para RF de interpretacion IA posteriores.

    Una sugerencia nueva invalida las revisiones antiguas. Nunca confirma un pedido.
    Debe invocarlo un proceso confiable con `TenantScope` validado.
    """
    if quantity is not None and (not quantity.is_finite() or quantity <= 0):
        raise ValueError("Cantidad sugerida invalida")
    if due_date is not None and not isinstance(due_date, date):
        raise ValueError("Fecha sugerida invalida")
    order = get_order(db, scope, order_id, lock=True)
    _reviewable(order)
    order.suggested_quantity = quantity
    order.suggested_due_date = due_date
    order.reviewed_quantity = None
    order.reviewed_due_date = None
    order.reviewed_by_user_id = None
    order.reviewed_at = None
    order.review_revision += 1
    db.commit()
    db.refresh(order)
    return review_view(order)
