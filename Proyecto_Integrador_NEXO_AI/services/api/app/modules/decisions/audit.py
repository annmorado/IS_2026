"""Emite eventos de auditoría en la transacción del cambio productivo."""
import json
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.modules.decisions.model import AuditEvent
from app.modules.decisions.schemas import AuditRead, AuditPage
from app.modules.tenancy.scope import TenantScope


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def audit(db: Session, scope: TenantScope, *, entity_type: str, entity_id: UUID,
          action: str, before: dict | None = None, after: dict | None = None):
    obj = AuditEvent(organization_id=scope.organization_id, actor_user_id=scope.actor_id,
                     entity_type=entity_type, entity_id=entity_id, action=action,
                     before_json=canonical(before) if before is not None else None,
                     after_json=canonical(after) if after is not None else None)
    db.add(obj)
    return obj


def list_audit(db: Session, scope: TenantScope, *, limit: int, offset: int,
               entity_type: str | None = None, entity_id: UUID | None = None) -> AuditPage:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == scope.organization_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    events = db.scalars(stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                        .limit(limit).offset(offset)).all()
    return AuditPage(items=[AuditRead(
        id=e.id, entity_type=e.entity_type, entity_id=e.entity_id, action=e.action,
        actor_user_id=e.actor_user_id, organization_id=e.organization_id,
        before=json.loads(e.before_json) if e.before_json else None,
        after=json.loads(e.after_json) if e.after_json else None,
        occurred_at=e.occurred_at,
    ) for e in events], total=total, limit=limit, offset=offset)
