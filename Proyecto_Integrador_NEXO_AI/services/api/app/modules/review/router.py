"""RF-010: formulario editable persistido y confirmacion en dos pasos."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.review.schemas import ConfirmRead, ConfirmRequest, ReviewRead, ReviewSave
from app.modules.review.service import confirm_review, get_review, save_review
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/orders", tags=["RF-010 Revision humana previa"])


@router.get("/{order_id}/review", response_model=ReviewRead)
def read_review(order_id: UUID, context: AuthContext = Depends(require_staff),
                db: Session = Depends(get_db)):
    return get_review(db, scope_from_context(context), order_id)


@router.put("/{order_id}/review", response_model=ReviewRead)
def write_review(order_id: UUID, payload: ReviewSave,
                 context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return save_review(db, scope_from_context(context), order_id, payload, role=context.user.role)


@router.post("/{order_id}/confirm", response_model=ConfirmRead)
def confirm(order_id: UUID, payload: ConfirmRequest,
            context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return confirm_review(db, scope_from_context(context), order_id,
                          expected_revision=payload.expected_revision, role=context.user.role)
