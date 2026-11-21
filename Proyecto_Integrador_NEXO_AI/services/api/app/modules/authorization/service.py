"""Consultas exclusivamente por la organizacion del usuario validado."""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.authorization.schemas import PolicyUpdate
from app.modules.organizations.model import Organization


def get_own_organization(db: Session, *, organization_id: UUID) -> Organization:
    # No recibe un ID arbitrario de la peticion: viene de AuthContext (JWT + DB).
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizacion no encontrada")
    return organization


def update_own_policy(db: Session, *, organization_id: UUID, changes: PolicyUpdate) -> Organization:
    # SELECT FOR UPDATE serializa actualizaciones concurrentes en PostgreSQL.
    with db.begin_nested():
        organization = db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if organization is None:
            raise HTTPException(status_code=404, detail="Organizacion no encontrada")
        for key, value in changes.model_dump(exclude_unset=True).items():
            setattr(organization, key, value)
        db.flush()
    db.commit()
    db.refresh(organization)
    return organization
