"""RF-025: explicit day/resource load with commitments and residual capacity."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner,require_staff
from app.modules.capacity.model import ProductionResource,ResourceBlackout
from app.modules.decisions.audit import audit
from app.modules.orders.model import Order
from app.modules.scheduling.model import ResourceAllocation
from app.modules.tenancy.scope import scope_from_context

router=APIRouter(prefix='/scheduling',tags=['RF-025 Calendario de carga'])

class AllocationCreate(BaseModel):
    resource_id:UUID
    order_id:UUID
    day:date
    quantity:Decimal=Field(gt=0,max_digits=12,decimal_places=3)

def row(a):
    return {'id':str(a.id),'resource_id':str(a.resource_id),'order_id':str(a.order_id),'day':a.day.isoformat(),'quantity':str(a.quantity)}

@router.get('/calendar')
def calendar(day:date=Query(...),context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context);resources=list(db.scalars(select(ProductionResource).where(
       ProductionResource.organization_id==scope.organization_id,ProductionResource.is_active.is_(True)).order_by(ProductionResource.name)).all())
    allocation=list(db.scalars(select(ResourceAllocation).where(ResourceAllocation.organization_id==scope.organization_id,ResourceAllocation.day==day)).all())
    blackouts=set(db.scalars(select(ResourceBlackout.resource_id).where(ResourceBlackout.organization_id==scope.organization_id,ResourceBlackout.day==day)).all())
    result=[]
    for r in resources:
        working=day.weekday() in r.workdays and r.id not in blackouts
        cap=r.daily_capacity if working else Decimal('0')
        entries=[a for a in allocation if a.resource_id==r.id]
        used=sum((a.quantity for a in entries),Decimal('0'))
        result.append({'resource_id':str(r.id),'resource_name':r.name,'unit':r.unit,'day':day.isoformat(),
           'working':working,'capacity':str(cap),'occupied':str(used),'remaining':str(max(Decimal('0'),cap-used)),
           'allocations':[row(a) for a in entries]})
    return {'day':day.isoformat(),'resources':result,
      'notice':'Solo compromisos asignados explícitamente; pedidos anteriores sin asignación no se contabilizan.'}

@router.post('/allocations',status_code=201)
def allocate(data:AllocationCreate,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    resource=db.scalar(select(ProductionResource).where(ProductionResource.id==data.resource_id,
       ProductionResource.organization_id==scope.organization_id).with_for_update())
    order=db.scalar(select(Order).where(Order.id==data.order_id,Order.organization_id==scope.organization_id))
    if resource is None or order is None:raise HTTPException(404,detail='Pedido o recurso no encontrado')
    if not resource.is_active or order.status not in ('confirmed','in_progress'):
        raise HTTPException(409,detail='Solo se asignan pedidos confirmados a recursos activos')
    if data.day.weekday() not in resource.workdays or db.scalar(select(ResourceBlackout).where(
       ResourceBlackout.organization_id==scope.organization_id,ResourceBlackout.resource_id==resource.id,ResourceBlackout.day==data.day)):
        raise HTTPException(409,detail='El recurso no trabaja ese día')
    used=db.scalar(select(func.coalesce(func.sum(ResourceAllocation.quantity),0)).where(
        ResourceAllocation.organization_id==scope.organization_id,ResourceAllocation.resource_id==resource.id,ResourceAllocation.day==data.day))
    if used+data.quantity>resource.daily_capacity:
        raise HTTPException(409,detail='Capacidad insuficiente: quedan '+str(max(Decimal('0'),resource.daily_capacity-used))+' '+resource.unit)
    if db.scalar(select(ResourceAllocation).where(ResourceAllocation.resource_id==resource.id,
       ResourceAllocation.order_id==order.id,ResourceAllocation.day==data.day)):
        raise HTTPException(409,detail='El pedido ya está asignado a este recurso ese día')
    obj=ResourceAllocation(organization_id=scope.organization_id,resource_id=resource.id,order_id=order.id,day=data.day,
      quantity=data.quantity,created_by_user_id=scope.actor_id)
    db.add(obj);db.flush()
    audit(db,scope,entity_type='allocation',entity_id=obj.id,action='capacity.allocated',after={'resource':str(resource.id),'order':str(order.id),'day':str(data.day),'quantity':str(data.quantity),'unit':resource.unit})
    db.commit();return row(obj)

@router.delete('/allocations/{allocation_id}')
def unassign(allocation_id:UUID,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    obj=db.scalar(select(ResourceAllocation).where(ResourceAllocation.id==allocation_id,ResourceAllocation.organization_id==scope.organization_id).with_for_update())
    if not obj:raise HTTPException(404,detail='Asignación no encontrada')
    audit(db,scope,entity_type='allocation',entity_id=obj.id,action='capacity.allocation_cancelled',before=row(obj))
    db.delete(obj);db.commit();return {'removed':True}
