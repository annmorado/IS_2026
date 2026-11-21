"""Operaciones RF-007: sin confiar en IDs de tenant y sin simular compromisos inexistentes."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.decisions.audit import audit

from app.modules.capacity.model import ProductionResource, ResourceBlackout
from app.modules.capacity.schemas import CapacityEvaluation, ResourceCreate, ResourcePatch
from app.modules.tenancy.scope import TenantScope

MAX_PERIOD_DAYS = 366


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Recurso no encontrado")


def _duplicate() -> HTTPException:
    return HTTPException(status_code=409, detail="Codigo duplicado en esta organizacion")


def get_resource(db: Session, scope: TenantScope, resource_id: UUID, *, lock: bool = False) -> ProductionResource:
    query = select(ProductionResource).where(
        ProductionResource.id == resource_id,
        ProductionResource.organization_id == scope.organization_id,
    )
    if lock:
        query = query.with_for_update()
    resource = db.scalar(query)
    if resource is None:
        raise _not_found()
    return resource


def list_resources(db: Session, scope: TenantScope, *, include_inactive: bool, limit: int, offset: int) -> list[ProductionResource]:
    query = select(ProductionResource).where(ProductionResource.organization_id == scope.organization_id)
    if not include_inactive:
        query = query.where(ProductionResource.is_active.is_(True))
    return list(db.scalars(query.order_by(ProductionResource.code, ProductionResource.id)
                           .limit(limit).offset(offset)).all())


def create_resource(db: Session, scope: TenantScope, payload: ResourceCreate) -> ProductionResource:
    values = payload.model_dump(exclude={"workdays"})
    item = ProductionResource(
        organization_id=scope.organization_id,
        workdays_csv=",".join(map(str, payload.workdays)), **values,
    )
    db.add(item)
    try:
        db.flush()
        audit(db, scope, entity_type='resource', entity_id=item.id, action='resource.created',
              after={'name':item.name,'unit':item.unit,'daily_capacity':str(item.daily_capacity)})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    db.refresh(item)
    return item


def update_resource(db: Session, scope: TenantScope, resource_id: UUID, payload: ResourcePatch) -> ProductionResource:
    item = get_resource(db, scope, resource_id, lock=True)
    before={'daily_capacity':str(item.daily_capacity),'workdays':item.workdays}
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "workdays":
            item.workdays_csv = ",".join(map(str, value))
        else:
            setattr(item, key, value)
    audit(db, scope, entity_type='resource', entity_id=item.id, action='resource.updated',
          before=before,after={'daily_capacity':str(item.daily_capacity),'workdays':item.workdays})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    db.refresh(item)
    return item


def deactivate_resource(db: Session, scope: TenantScope, resource_id: UUID) -> ProductionResource:
    item = get_resource(db, scope, resource_id, lock=True)
    item.is_active = False
    audit(db, scope, entity_type='resource', entity_id=item.id, action='resource.deactivated',
          before={'is_active':True},after={'is_active':False})
    db.commit()
    db.refresh(item)
    return item


def list_blackouts(db: Session, scope: TenantScope, resource_id: UUID, *, limit: int, offset: int) -> list[ResourceBlackout]:
    get_resource(db, scope, resource_id)
    return list(db.scalars(select(ResourceBlackout).where(
        ResourceBlackout.organization_id == scope.organization_id,
        ResourceBlackout.resource_id == resource_id,
    ).order_by(ResourceBlackout.day).limit(limit).offset(offset)).all())


def set_blackout(db: Session, scope: TenantScope, resource_id: UUID, day: date) -> ResourceBlackout:
    # El recurso se bloquea para evitar carreras con actualizaciones administrativas.
    get_resource(db, scope, resource_id, lock=True)
    existing = db.scalar(select(ResourceBlackout).where(
        ResourceBlackout.resource_id == resource_id,
        ResourceBlackout.organization_id == scope.organization_id,
        ResourceBlackout.day == day,
    ))
    if existing is not None:
        return existing
    item = ResourceBlackout(resource_id=resource_id, organization_id=scope.organization_id, day=day)
    db.add(item)
    audit(db, scope, entity_type='resource', entity_id=resource_id, action='resource.blackout_added',
          after={'day':str(day)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto al registrar dia no disponible") from exc
    db.refresh(item)
    return item


def delete_blackout(db: Session, scope: TenantScope, resource_id: UUID, day: date) -> None:
    get_resource(db, scope, resource_id, lock=True)
    item = db.scalar(select(ResourceBlackout).where(
        ResourceBlackout.resource_id == resource_id,
        ResourceBlackout.organization_id == scope.organization_id,
        ResourceBlackout.day == day,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Dia no disponible no encontrado")
    audit(db, scope, entity_type='resource', entity_id=resource_id, action='resource.blackout_removed',
          before={'day':str(day)})
    db.delete(item)
    db.commit()


def evaluate_capacity(db: Session, scope: TenantScope, resource_id: UUID, *, start_date: date,
                      end_date: date, requested_units: Decimal) -> CapacityEvaluation:
    item = get_resource(db, scope, resource_id)
    if not item.is_active:
        raise HTTPException(status_code=409, detail="El recurso esta desactivado")
    total_days = (end_date - start_date).days + 1
    if total_days <= 0 or total_days > MAX_PERIOD_DAYS:
        raise HTTPException(status_code=422, detail="El periodo debe durar entre 1 y 366 dias")
    disabled = set(db.scalars(select(ResourceBlackout.day).where(
        ResourceBlackout.organization_id == scope.organization_id,
        ResourceBlackout.resource_id == resource_id,
        ResourceBlackout.day >= start_date,
        ResourceBlackout.day <= end_date,
    )).all())
    workdays = set(item.workdays)
    scheduled = 0
    blocked = 0
    for offset in range(total_days):
        day = start_date + timedelta(days=offset)
        if day.weekday() in workdays:
            scheduled += 1
            if day in disabled:
                blocked += 1
    available = scheduled - blocked
    gross = item.daily_capacity * Decimal(available)
    shortage = max(requested_units - gross, Decimal("0.000"))
    minimum = int((requested_units / item.daily_capacity).to_integral_value(rounding=ROUND_CEILING))
    return CapacityEvaluation(
        resource_id=item.id, unit=item.unit, start_date=start_date, end_date=end_date,
        requested_units=requested_units, daily_capacity=item.daily_capacity,
        calendar_days=total_days, scheduled_workdays=scheduled, blacked_out_workdays=blocked,
        available_workdays=available, gross_capacity=gross, shortage=shortage,
        feasible=shortage == 0, minimum_workdays=minimum,
        includes_existing_commitments=False,
    )
