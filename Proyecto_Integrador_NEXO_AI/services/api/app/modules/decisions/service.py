"""RF-018, 021, 022: propuesta reproducible, confirmación expresa y claves idempotentes.

Una propuesta persiste únicamente su entrada/resultado, no altera pedidos. Aplicar
exige propietario, acto afirmativo, versión vigente y revalidar restricciones.
"""
import hashlib
import json
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.security import utc_now
from app.modules.decisions.audit import audit, canonical
from app.modules.decisions.keys import check_key
from app.modules.decisions.model import DecisionRecommendation
from app.modules.decisions.schemas import RecommendationRead, RecommendationCreate, RecommendationConfirm
from app.modules.orders.model import Order
from app.modules.order_status.service import write_status_event
from app.modules.scenarios.schemas import ScenarioInput, ScenarioResult
from app.modules.scenarios.service import evaluate
from app.modules.tenancy.scope import TenantScope

VERSION = 'rf017-v1'
def sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def render(obj: DecisionRecommendation) -> RecommendationRead:
    applied = json.loads(obj.applied_json) if obj.applied_json else None
    return RecommendationRead(
        id=obj.id, organization_id=obj.organization_id, order_id=obj.order_id,
        created_at=obj.created_at, created_by_user_id=obj.created_by_user_id,
        status=obj.status, engine_version=obj.engine_version,
        expected_review_revision=obj.expected_review_revision,
        expected_order_status=obj.expected_order_status,
        scenario=ScenarioInput.model_validate(json.loads(obj.input_json)),
        result=ScenarioResult.model_validate(json.loads(obj.result_json)),
        confirmed_at=obj.confirmed_at, confirmed_by_user_id=obj.confirmed_by_user_id,
        exception_reason=obj.exception_reason,
        applied_order_status=applied.get('status') if applied else None,
    )


def get_rec(db: Session, scope: TenantScope, recommendation_id: UUID, *, lock=False):
    q = select(DecisionRecommendation).where(
        DecisionRecommendation.id == recommendation_id,
        DecisionRecommendation.organization_id == scope.organization_id,
    )
    obj = db.scalar(q.with_for_update() if lock else q)
    if obj is None:
        raise HTTPException(status_code=404, detail='Recomendacion no encontrada')
    return obj


def list_recs(db: Session, scope: TenantScope, order_id: UUID):
    # No revelar a organizaciones ajenas si se conoce un UUID.
    order = db.scalar(select(Order).where(Order.id == order_id,
                    Order.organization_id == scope.organization_id))
    if order is None:
        raise HTTPException(status_code=404, detail='Pedido no encontrado')
    items = db.scalars(select(DecisionRecommendation).where(
        DecisionRecommendation.organization_id == scope.organization_id,
        DecisionRecommendation.order_id == order_id,
    ).order_by(DecisionRecommendation.created_at.desc(), DecisionRecommendation.id.desc()).limit(100)).all()
    return [render(x) for x in items]


def create_rec(db: Session, scope: TenantScope, payload: RecommendationCreate, key: str):
    key = check_key(key)
    snapshot = canonical(payload.scenario.model_dump(mode='json'))
    fingerprint = sha(snapshot)
    # Serializar por organización para evitar dos operaciones con la misma clave.
    from app.modules.organizations.model import Organization
    org = db.scalar(select(Organization).where(Organization.id == scope.organization_id).with_for_update())
    if org is None: raise HTTPException(status_code=404, detail='Organizacion no encontrada')
    prev = db.scalar(select(DecisionRecommendation).where(
        DecisionRecommendation.organization_id == scope.organization_id,
        DecisionRecommendation.created_by_user_id == scope.actor_id,
        DecisionRecommendation.create_key == key))
    if prev:
        if prev.create_hash != fingerprint:
            raise HTTPException(status_code=409, detail='Clave de idempotencia reutilizada con datos diferentes')
        return render(prev)
    order = db.scalar(select(Order).where(Order.id == payload.scenario.order_id,
         Order.organization_id == scope.organization_id))
    if order is None:
        raise HTTPException(status_code=404, detail='Pedido no encontrado')
    result = evaluate(db, scope, payload.scenario)
    result_data = canonical(result.model_dump(mode='json'))
    obj = DecisionRecommendation(
        organization_id=scope.organization_id, order_id=order.id,
        created_by_user_id=scope.actor_id, create_key=key, create_hash=fingerprint,
        input_json=snapshot, result_json=result_data, result_hash=sha(result_data),
        engine_version=VERSION, expected_review_revision=order.review_revision,
        expected_order_status=order.status,
    )
    db.add(obj)
    db.flush()
    audit(db, scope, entity_type='recommendation', entity_id=obj.id, action='recommendation.created',
          after={'status':'proposed','order_id':str(order.id),'engine_version':VERSION,
                 'result_hash':obj.result_hash})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflicto concurrente de idempotencia') from exc
    db.refresh(obj)
    return render(obj)


def confirm_rec(db: Session, scope: TenantScope, recommendation_id: UUID,
                payload: RecommendationConfirm, key: str):
    key = check_key(key)
    # Bloqueo por organización para serializar el uso de claves en toda la empresa.
    from app.modules.organizations.model import Organization
    org = db.scalar(select(Organization).where(Organization.id == scope.organization_id).with_for_update())
    if org is None: raise HTTPException(status_code=404, detail='Organizacion no encontrada')
    obj = get_rec(db, scope, recommendation_id, lock=True)
    fingerprint = sha(canonical(payload.model_dump(mode='json')))
    if obj.status == 'applied':
        if obj.confirmation_key == key and obj.confirmation_hash == fingerprint:
            return render(obj)
        raise HTTPException(status_code=409, detail='Recomendacion aplicada; no se repite la confirmacion')
    if obj.status != 'proposed':
        raise HTTPException(status_code=409, detail='Recomendacion no confirmable')
    used = db.scalar(select(DecisionRecommendation).where(
        DecisionRecommendation.organization_id == scope.organization_id,
        DecisionRecommendation.confirmation_key == key))
    if used:
        raise HTTPException(status_code=409, detail='Clave de idempotencia usada en otra confirmacion')
    order = db.scalar(select(Order).where(Order.id == obj.order_id,
                 Order.organization_id == scope.organization_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail='Pedido no encontrado')
    if order.status not in ('draft','pending') or order.status != obj.expected_order_status:
        raise HTTPException(status_code=409, detail='Estado de pedido cambiado; crea una nueva recomendacion')
    if (order.review_revision != obj.expected_review_revision or
            order.review_revision != payload.expected_review_revision):
        raise HTTPException(status_code=409, detail='Revision cambiada; crea una nueva recomendacion')
    scenario = ScenarioInput.model_validate(json.loads(obj.input_json))
    if scenario.unit_price_mxn is not None or scenario.resource_daily_capacity is not None:
        raise HTTPException(status_code=409, detail='Precio o capacidad hipotetica no se puede aplicar: crea una propuesta sin esos cambios')
    current_result = evaluate(db, scope, scenario)
    current_json = canonical(current_result.model_dump(mode='json'))
    if sha(current_json) != obj.result_hash:
        raise HTTPException(status_code=409, detail='Los datos de la simulacion cambiaron; recalcula la recomendacion')
    result = ScenarioResult.model_validate(json.loads(obj.result_json))
    if result.explanation.status != 'feasible_with_assumptions':
        reason = (payload.exception_reason or '').strip()
        if len(reason) < 15:
            raise HTTPException(status_code=409, detail='La restriccion o datos faltantes requieren una justificacion excepcional de al menos 15 caracteres')
    else:
        reason = (payload.exception_reason or '').strip() or None
    now = utc_now()
    from_status = order.status
    before = {'status':from_status,'review_revision':order.review_revision,
              'reviewed_quantity':str(order.reviewed_quantity) if order.reviewed_quantity else None,
              'reviewed_due_date':str(order.reviewed_due_date) if order.reviewed_due_date else None}
    order.reviewed_quantity = result.simulated.quantity
    order.reviewed_due_date = result.delivery_date
    order.reviewed_by_user_id = scope.actor_id
    order.reviewed_at = now
    order.review_revision += 1
    order.status = 'confirmed'
    order.confirmed_by_user_id = scope.actor_id
    order.confirmed_at = now
    write_status_event(db, scope, order, previous=from_status, new='confirmed',
                       note='Confirmacion humana RF-018, recomendacion '+str(obj.id))
    obj.status = 'applied'
    obj.confirmed_by_user_id = scope.actor_id
    obj.confirmed_at = now
    obj.confirmation_key = key
    obj.confirmation_hash = fingerprint
    obj.exception_reason = reason
    obj.applied_json = canonical({'status':'confirmed','review_revision':order.review_revision,
                                  'quantity':str(order.reviewed_quantity),'due_date':str(order.reviewed_due_date)})
    audit(db, scope, entity_type='order', entity_id=order.id, action='order.confirmed_from_recommendation',
          before=before,after={'status':'confirmed','review_revision':order.review_revision,
                 'quantity':str(order.reviewed_quantity),'due_date':str(order.reviewed_due_date),
                 'recommendation_id':str(obj.id),'exception_reason':reason})
    audit(db, scope, entity_type='recommendation', entity_id=obj.id, action='recommendation.applied',
          before={'status':'proposed'},after={'status':'applied','exception_reason':reason,
                  'result_hash':obj.result_hash})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='Conflicto concurrente de confirmacion') from exc
    db.refresh(obj)
    return render(obj)
