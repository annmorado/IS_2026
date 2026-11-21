"""RF-028: cuota por empresa, activación trial una sola vez, sin auto-facturación."""
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.security import utc_now
from app.modules.authorization.dependencies import require_owner
from app.modules.extensions.entitlements import current,snapshot
from app.modules.decisions.audit import audit
from app.modules.tenancy.scope import scope_from_context
router=APIRouter(prefix='/subscriptions',tags=['RF-028 Planes y límites'])

@router.get('/me')
def read_plan(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    return snapshot(db,ctx.user.organization_id)

@router.post('/start-trial')
def start_trial(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    org=ctx.user.organization_id;sub=current(db,org,lock=True)
    if sub.trial_consumed or sub.plan_code!='starter' or sub.status!='active':
        raise HTTPException(status_code=409,detail='Prueba ya utilizada o plan no apto')
    sub.trial_consumed=True;sub.status='trial';sub.trial_ends_at=utc_now()+timedelta(days=7)
    audit(db,scope_from_context(ctx),entity_type='subscription',entity_id=org,action='subscription.trial_activated',after={'duration_days':7})
    db.commit();return snapshot(db,org)
