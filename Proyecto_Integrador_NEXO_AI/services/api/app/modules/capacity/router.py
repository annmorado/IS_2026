"""RF-007: control de capacidad y calendario, limitado al usuario autenticado."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner, require_staff
from app.modules.capacity.schemas import (
    ResourceCreate, ResourcePatch, ResourceRead, BlackoutRead, CapacityEvaluation,
)
from app.modules.capacity.service import (
    create_resource, list_resources, get_resource, update_resource, deactivate_resource,
    list_blackouts, set_blackout, delete_blackout, evaluate_capacity,
)
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/capacity/resources", tags=["RF-007 Capacidad operativa"])


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create(payload: ResourceCreate, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return create_resource(db, scope_from_context(context), payload)


@router.get("", response_model=list[ResourceRead])
def list_all(include_inactive: bool = False, limit: int = Query(50, ge=1, le=100),
             offset: int = Query(0, ge=0), context: AuthContext = Depends(require_staff),
             db: Session = Depends(get_db)):
    return list_resources(db, scope_from_context(context), include_inactive=include_inactive, limit=limit, offset=offset)


@router.get("/{resource_id}", response_model=ResourceRead)
def get_one(resource_id: UUID, context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return get_resource(db, scope_from_context(context), resource_id)


@router.patch("/{resource_id}", response_model=ResourceRead)
def edit(resource_id: UUID, payload: ResourcePatch, context: AuthContext = Depends(require_owner),
         db: Session = Depends(get_db)):
    return update_resource(db, scope_from_context(context), resource_id, payload)


@router.post("/{resource_id}/deactivate", response_model=ResourceRead)
def deactivate(resource_id: UUID, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return deactivate_resource(db, scope_from_context(context), resource_id)


@router.get("/{resource_id}/blackouts", response_model=list[BlackoutRead])
def blackouts(resource_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return list_blackouts(db, scope_from_context(context), resource_id, limit=limit, offset=offset)


@router.put("/{resource_id}/blackouts/{day}", response_model=BlackoutRead)
def block_day(resource_id: UUID, day: date, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return set_blackout(db, scope_from_context(context), resource_id, day)


@router.delete("/{resource_id}/blackouts/{day}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_day(resource_id: UUID, day: date, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    delete_blackout(db, scope_from_context(context), resource_id, day)
    return Response(status_code=204)


@router.get("/{resource_id}/evaluate", response_model=CapacityEvaluation)
def evaluate(resource_id: UUID, start_date: date, end_date: date,
             requested_units: Decimal = Query(..., ge=Decimal("0"), max_digits=12, decimal_places=3),
             context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return evaluate_capacity(db, scope_from_context(context), resource_id,
                             start_date=start_date, end_date=end_date, requested_units=requested_units)
