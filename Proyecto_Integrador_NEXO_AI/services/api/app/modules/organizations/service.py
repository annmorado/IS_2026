from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.organizations.model import Organization
from app.modules.organizations.schemas import OrganizationCreate


def create_organization(db: Session, payload: OrganizationCreate) -> Organization:
    organization = Organization(**payload.model_dump())
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def get_organization(db: Session, organization_id: UUID) -> Organization | None:
    return db.get(Organization, organization_id)
