"""RF-020: métricas de operación obtenidas del backend, sin inventar ocupación."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.orders.model import Order
from app.modules.capacity.model import ProductionResource, ResourceBlackout
from app.modules.organizations.model import Organization
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix='/operations', tags=['RF-020 Panel operativo'])

@router.get('/summary')
def summary(days: int = Query(default=7, ge=1, le=30),
            context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    scope = scope_from_context(context)
    org = db.get(Organization, scope.organization_id)
    if not org: raise HTTPException(404, detail='Organizacion no encontrada')
    try: today = datetime.now(timezone.utc).astimezone(ZoneInfo(org.timezone)).date()
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(409, detail='Zona horaria no reconocida') from exc
    end = today + timedelta(days=days)
    all_counts = dict(db.execute(select(Order.status,func.count()).where(
        Order.organization_id==scope.organization_id).group_by(Order.status)).all())
    open_states = ('draft','pending','confirmed','in_progress')
    orders = list(db.scalars(select(Order).where(
        Order.organization_id==scope.organization_id,
        Order.status.in_(('confirmed','in_progress')))).all())
    due = [o for o in orders if o.reviewed_due_date is not None]
    overdue = [o for o in due if o.reviewed_due_date < today]
    upcoming = [o for o in due if today <= o.reviewed_due_date <= end]
    resources = list(db.scalars(select(ProductionResource).where(
        ProductionResource.organization_id==scope.organization_id,
        ProductionResource.is_active.is_(True)).order_by(ProductionResource.name)).all())
    blocked = set(db.execute(select(ResourceBlackout.resource_id).where(
        ResourceBlackout.organization_id==scope.organization_id,
        ResourceBlackout.day==today)).scalars().all())
    resource_rows = [{
       'id':str(r.id),'name':r.name,'unit':r.unit,
       'daily_capacity':str(r.daily_capacity),
       'working_today':today.weekday() in r.workdays and r.id not in blocked,
       'available_capacity_today':str(r.daily_capacity if today.weekday() in r.workdays and r.id not in blocked else 0),
       'includes_existing_commitments':False,
    } for r in resources]
    alerts = ([{'code':'overdue','severity':'warning','count':len(overdue),
                'message':f'{len(overdue)} pedido(s) comprometido(s) vencidos'}] if overdue else [])
    if not resources: alerts.append({'code':'no_resources','severity':'info','count':0,
                                    'message':'No hay recursos productivos activos configurados'})
    if any(o.reviewed_due_date is None for o in orders):
        alerts.append({'code':'missing_due_date','severity':'warning','count':len(orders)-len(due),
                       'message':'Hay pedidos confirmados sin fecha revisada'})
    return {
      'as_of':datetime.now(timezone.utc).isoformat(),'today':today.isoformat(),
      'window_end':end.isoformat(), 'counts_by_status':{k:int(all_counts.get(k,0)) for k in
                    ('draft','pending','confirmed','in_progress','completed','cancelled')},
      'open_orders':sum(int(all_counts.get(k,0)) for k in open_states),
      'committed_orders':len(orders), 'due_soon':len(upcoming),'overdue':len(overdue),
      'capacity_resources':resource_rows, 'alerts':alerts,
      'capacity_caveat':'Capacidad bruta por recurso y unidad, sin descontar otros pedidos ni reservas. No sumar unidades diferentes.',
    }
