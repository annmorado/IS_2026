"""RF-004: consultas scoped; 404 uniforme para recursos ajenos/inexistentes."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.auth.model import AuthSession, User
from app.modules.auth.security import utc_now
from app.modules.tenancy.scope import TenantScope


def get_scoped_member(
    db: Session, *, scope: TenantScope, user_id: UUID, for_update: bool = False
) -> User:
    # Filtro de tenant en SQL, ANTES de recuperar una fila.
    query = select(User).where(
        User.id == user_id,
        User.organization_id == scope.organization_id,
    )
    if for_update:
        query = query.with_for_update()
    result = db.scalar(query)
    if result is None:
        # Misma respuesta si el UUID existe en otra organizacion o no existe.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado")
    return result


def list_scoped_members(db: Session, *, scope: TenantScope, limit: int, offset: int) -> list[User]:
    return list(db.scalars(
        select(User)
        .where(User.organization_id == scope.organization_id)
        .order_by(User.created_at, User.id)
        .limit(limit)
        .offset(offset)
    ).all())


def revoke_member_sessions(db: Session, *, member_id: UUID) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == member_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    return result.rowcount or 0


def update_member_status(db: Session, *, scope: TenantScope, user_id: UUID, is_active: bool) -> User:
    # Scoped SELECT FOR UPDATE avoids cross-tenant writes, including forged UUID.
    member = get_scoped_member(db, scope=scope, user_id=user_id, for_update=True)
    if member.role != "operator":
        # Un propietario no se puede desactivar por esta API.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo se puede cambiar el estado de operadores")
    member.is_active = is_active
    if not is_active:
        # Un token anterior nunca revive al reactivar al operador.
        revoke_member_sessions(db, member_id=member.id)
    db.commit()
    db.refresh(member)
    return member


def revoke_scoped_sessions(db: Session, *, scope: TenantScope, user_id: UUID) -> int:
    member = get_scoped_member(db, scope=scope, user_id=user_id, for_update=True)
    count = revoke_member_sessions(db, member_id=member.id)
    db.commit()
    return count
