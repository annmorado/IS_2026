"""RF-018, RF-019, RF-021 y RF-022 — rutas autorizadas por tenant."""
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner
from app.modules.decisions.audit import list_audit
from app.modules.decisions.schemas import (
    RecommendationCreate, RecommendationConfirm, RecommendationRead, AuditPage,
)
from app.modules.decisions.service import create_rec, get_rec, render, list_recs, confirm_rec
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix='/decisions', tags=['RF-018-022 Decisiones auditadas'])
audit_router = APIRouter(prefix='/audit', tags=['RF-019 Auditoria'])

@router.post('/recommend', response_model=RecommendationRead, status_code=status.HTTP_201_CREATED)
def recommend(payload: RecommendationCreate,
              key: str | None = Header(default=None, alias='Idempotency-Key'),
              context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return create_rec(db, scope_from_context(context), payload, key)

@router.post('/{decision_id}/confirm', response_model=RecommendationRead)
def confirm(decision_id: UUID, payload: RecommendationConfirm,
            key: str | None = Header(default=None, alias='Idempotency-Key'),
            context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return confirm_rec(db, scope_from_context(context), decision_id, payload, key)

@router.get('', response_model=list[RecommendationRead])
def list_recommendations(order_id: UUID, context: AuthContext = Depends(require_owner),
                         db: Session = Depends(get_db)):
    return list_recs(db, scope_from_context(context), order_id)

@router.get('/{decision_id}', response_model=RecommendationRead)
def get_recommendation(decision_id: UUID, context: AuthContext = Depends(require_owner),
                       db: Session = Depends(get_db)):
    return render(get_rec(db, scope_from_context(context), decision_id))

@audit_router.get('/events', response_model=AuditPage)
def events(entity_type: str | None = Query(default=None, max_length=40),
           entity_id: UUID | None = None, limit: int = Query(default=30, ge=1, le=100),
           offset: int = Query(default=0, ge=0),
           context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return list_audit(db, scope_from_context(context),limit=limit,offset=offset,
                      entity_type=entity_type,entity_id=entity_id)
