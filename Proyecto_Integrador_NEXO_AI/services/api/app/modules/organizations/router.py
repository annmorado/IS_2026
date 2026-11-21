from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_local_bootstrap
from app.db.session import get_db
from app.modules.organizations.schemas import OrganizationCreate, OrganizationRead
from app.modules.organizations.service import create_organization, get_organization

router = APIRouter(
    prefix="/organizations",
    tags=["Organizaciones (bootstrap local)"],
    dependencies=[Depends(require_local_bootstrap)],
)


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create(payload: OrganizationCreate, db: Session = Depends(get_db)):
    return create_organization(db, payload)


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_one(organization_id: UUID, db: Session = Depends(get_db)):
    item = get_organization(db, organization_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizacion no encontrada")
    return item
