"""RF-026: user-triggered in-app alert scan; no emails or background delivery."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.decisions.audit import audit
from app.modules.notifications.model import NotificationPreference,BusinessNotification
from app.modules.organizations.model import Organization
from app.modules.orders.model import Order
from app.modules.quotes.model import Quote,QuoteLine
from app.modules.materials.model import Material,ProductMaterial
from app.modules.tenancy.scope import scope_from_context

router=APIRouter(prefix='/notifications',tags=['RF-026 Alertas configurables'])

class PreferenceUpdate(BaseModel):
    due_soon:bool
    risk:bool
    material_shortage:bool

def values(p):
    return {k:bool(getattr(p,k)) if p else False for k in ('due_soon','risk','material_shortage')}

def pget(db,context):
    return db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==context.user.id,
        NotificationPreference.organization_id==context.user.organization_id))

@router.get('/preferences')
def preferences(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return values(pget(db,context))

@router.put('/preferences')
def update_preferences(data:PreferenceUpdate,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context);obj=pget(db,context)
    if not obj:
        obj=NotificationPreference(user_id=scope.actor_id,organization_id=scope.organization_id,
               due_soon=False,risk=False,material_shortage=False);db.add(obj)
    before=values(obj)
    for k,v in data.model_dump().items():setattr(obj,k,v)
    audit(db,scope,entity_type='notification_pref',entity_id=scope.actor_id,action='notification.preferences_changed',before=before,after=values(obj))
    db.commit();return values(obj)

def out(x):return {'id':str(x.id),'kind':x.kind,'source_key':x.source_key,'message':x.message,
  'created_at':x.created_at.isoformat() if x.created_at else None,'read':bool(x.read_at)}

@router.get('/entries')
def entries(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return [out(x) for x in db.scalars(select(BusinessNotification).where(
        BusinessNotification.organization_id==context.user.organization_id,BusinessNotification.user_id==context.user.id)
        .order_by(BusinessNotification.created_at.desc()).limit(100)).all()]

@router.post('/scan')
def scan(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context);settings=values(pget(db,context))
    org=db.get(Organization,scope.organization_id)
    if org is None:raise HTTPException(404,detail='Organización no encontrada')
    try:today=datetime.now(timezone.utc).astimezone(ZoneInfo(org.timezone)).date()
    except Exception as exc:raise HTTPException(409,detail='Zona horaria inválida') from exc
    active=list(db.scalars(select(Order).where(Order.organization_id==scope.organization_id,
        Order.status.in_(('confirmed','in_progress')))).all())
    signals=[]
    for o in active:
        if o.reviewed_due_date is None:continue
        if settings['due_soon'] and today<=o.reviewed_due_date<=today+timedelta(days=7):
            signals.append(('due_soon','order:'+str(o.id)+':'+o.reviewed_due_date.isoformat(),
              'Entrega próxima '+o.reviewed_due_date.isoformat()+' del pedido '+str(o.id)[:8]))
        if settings['risk'] and o.reviewed_due_date<today:
            signals.append(('risk','order:'+str(o.id)+':'+o.reviewed_due_date.isoformat(),
              'Entrega vencida del pedido '+str(o.id)[:8]+' desde '+o.reviewed_due_date.isoformat()))
    if settings['material_shortage'] and active:
        # Cada orden tiene como máximo una cotización aprobada vigente (mayor versión).
        approved=list(db.scalars(select(Quote).where(Quote.organization_id==scope.organization_id,
            Quote.status=='approved',Quote.order_id.in_([o.id for o in active])).order_by(Quote.version.desc())).all())
        latest={}
        for q in approved:latest.setdefault(q.order_id,q)
        demand={}
        if latest:
            quote_ids=[q.id for q in latest.values()]
            lines=list(db.scalars(select(QuoteLine).where(QuoteLine.organization_id==scope.organization_id,
                QuoteLine.quote_id.in_(quote_ids))).all())
            recipe=list(db.scalars(select(ProductMaterial).where(ProductMaterial.organization_id==scope.organization_id)).all())
            by_product={}
            for part in recipe:by_product.setdefault(part.product_id,[]).append(part)
            for line in lines:
                for part in by_product.get(line.product_id,[]):
                    demand[part.material_id]=demand.get(part.material_id,Decimal('0'))+line.quantity*part.quantity_per_unit
        if demand:
            material=list(db.scalars(select(Material).where(Material.organization_id==scope.organization_id,
                Material.id.in_(list(demand)))).all())
            for m in material:
                if demand[m.id]>m.quantity_available:
                    signals.append(('material_shortage','material:'+str(m.id)+':'+today.isoformat(),
                       'Material insuficiente '+m.name+': faltan '+str((demand[m.id]-m.quantity_available).quantize(Decimal('0.001')))+' '+m.unit))
    existing=set(db.scalars(select(BusinessNotification.source_key).where(
        BusinessNotification.organization_id==scope.organization_id,BusinessNotification.user_id==scope.actor_id)).all())
    created=[]
    for kind,key,message in signals:
        if key in existing:continue
        note=BusinessNotification(organization_id=scope.organization_id,user_id=scope.actor_id,
            kind=kind,source_key=key,message=message)
        db.add(note);created.append(note);existing.add(key)
    db.commit()
    return {'created':len(created),'signals_evaluated':len(signals),'enabled':settings,
       'notice':'Escaneo manual de alertas internas. No se envían correos ni notificaciones push.'}
