"""RF-004: gestion de miembros restringida al propietario del mismo negocio."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.schemas import UserRead
from app.modules.authorization.dependencies import require_owner
from app.modules.tenancy.schemas import MemberStatusUpdate, SessionRevocationResult
from app.modules.tenancy.scope import scope_from_context
from app.modules.tenancy.service import (
    get_scoped_member, list_scoped_members, revoke_scoped_sessions, update_member_status,
)

router = APIRouter(prefix="/tenants/me/members", tags=["RF-004 Aislamiento multiempresa"])


@router.get("", response_model=list[UserRead])
def list_members(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return list_scoped_members(db, scope=scope_from_context(context), limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserRead)
def get_member(
    user_id: UUID,
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return get_scoped_member(db, scope=scope_from_context(context), user_id=user_id)


@router.patch("/{user_id}/status", response_model=UserRead)
def update_status(
    user_id: UUID,
    payload: MemberStatusUpdate,
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return update_member_status(
        db, scope=scope_from_context(context), user_id=user_id, is_active=payload.is_active,
    )


@router.post("/{user_id}/revoke-sessions", response_model=SessionRevocationResult)
def revoke_sessions(
    user_id: UUID,
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return SessionRevocationResult(
        revoked_count=revoke_scoped_sessions(db, scope=scope_from_context(context), user_id=user_id)
    )
