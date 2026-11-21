"""RF-003: rutas seguras de lectura y configuracion de la propia organizacion."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner, require_staff
from app.modules.authorization.schemas import PolicyRead, PolicyUpdate
from app.modules.authorization.service import get_own_organization, update_own_policy
from app.modules.organizations.schemas import OrganizationRead

router = APIRouter(prefix="/organizations/me", tags=["Organizacion autenticada (RBAC)"])


@router.get("", response_model=OrganizationRead)
def get_my_organization(
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)
):
    return get_own_organization(db, organization_id=context.user.organization_id)


@router.get("/policies", response_model=PolicyRead)
def get_my_policies(
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)
):
    return get_own_organization(db, organization_id=context.user.organization_id)


@router.patch("/policies", response_model=PolicyRead)
def change_my_policies(
    payload: PolicyUpdate,
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return update_own_policy(
        db, organization_id=context.user.organization_id, changes=payload
    )
