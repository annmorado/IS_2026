"""RF-024: suppliers and explicitly approved purchase requests; no stock receipt."""
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner,require_staff
from app.modules.decisions.audit import audit
from app.modules.materials.model import Material
from app.modules.purchasing.model import Supplier,PurchaseRequest
from app.modules.tenancy.scope import scope_from_context

router=APIRouter(prefix='/purchasing',tags=['RF-024 Proveedores y compras'])

class SupplierCreate(BaseModel):
    code:str=Field(min_length=1,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=160)
    contact_email:EmailStr|None=None
class PurchaseCreate(BaseModel):
    supplier_id:UUID
    material_id:UUID
    quantity:Decimal=Field(gt=0,max_digits=15,decimal_places=3)
    unit_cost_mxn:Decimal=Field(ge=0,max_digits=12,decimal_places=2)
    comment:str|None=Field(default=None,max_length=500)
class PurchaseDecision(BaseModel):
    decision:str=Field(pattern=r'^(approve|reject)$')
    note:str=Field(min_length=4,max_length=500)

def supplier_out(x):return {'id':str(x.id),'code':x.code,'name':x.name,'contact_email':x.contact_email,'active':x.active}
def purchase_out(x):return {'id':str(x.id),'supplier_id':str(x.supplier_id),'material_id':str(x.material_id),
 'quantity':str(x.quantity),'unit_cost_mxn':str(x.unit_cost_mxn),'total_mxn':str((x.quantity*x.unit_cost_mxn).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),
 'status':x.status,'comment':x.comment,'created_by_user_id':str(x.created_by_user_id),
 'decided_by_user_id':str(x.decided_by_user_id) if x.decided_by_user_id else None,
 'decision_note':x.decision_note,'created_at':x.created_at.isoformat() if x.created_at else None}

@router.get('/suppliers')
def suppliers(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return [supplier_out(x) for x in db.scalars(select(Supplier).where(Supplier.organization_id==context.user.organization_id).order_by(Supplier.name)).all()]

@router.post('/suppliers',status_code=201)
def create_supplier(data:SupplierCreate,context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(context);obj=Supplier(organization_id=scope.organization_id,code=data.code,name=data.name,contact_email=str(data.contact_email) if data.contact_email else None)
    db.add(obj)
    try:
        db.flush();audit(db,scope,entity_type='supplier',entity_id=obj.id,action='supplier.created',after={'code':obj.code,'name':obj.name});db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,detail='Código de proveedor duplicado') from exc
    return supplier_out(obj)

@router.get('/requests')
def requests(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return [purchase_out(x) for x in db.scalars(select(PurchaseRequest).where(PurchaseRequest.organization_id==context.user.organization_id).order_by(PurchaseRequest.created_at.desc())).all()]

@router.post('/requests',status_code=201)
def request_purchase(data:PurchaseCreate,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    supplier=db.scalar(select(Supplier).where(Supplier.id==data.supplier_id,Supplier.organization_id==scope.organization_id,Supplier.active.is_(True)))
    material=db.scalar(select(Material).where(Material.id==data.material_id,Material.organization_id==scope.organization_id,Material.is_active.is_(True)))
    if supplier is None or material is None:raise HTTPException(404,detail='Proveedor o material no encontrado en esta empresa')
    obj=PurchaseRequest(organization_id=scope.organization_id,supplier_id=supplier.id,material_id=material.id,
      quantity=data.quantity,unit_cost_mxn=data.unit_cost_mxn,comment=data.comment,created_by_user_id=scope.actor_id,status='pending')
    db.add(obj);db.flush()
    audit(db,scope,entity_type='purchase',entity_id=obj.id,action='purchase.requested',after={'supplier_id':str(obj.supplier_id),'material_id':str(obj.material_id),'quantity':str(obj.quantity),'unit_cost_mxn':str(obj.unit_cost_mxn)})
    db.commit();return purchase_out(obj)

@router.post('/requests/{purchase_id}/decision')
def decide(purchase_id:UUID,data:PurchaseDecision,context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    obj=db.scalar(select(PurchaseRequest).where(PurchaseRequest.id==purchase_id,PurchaseRequest.organization_id==scope.organization_id).with_for_update())
    if not obj:raise HTTPException(404,detail='Solicitud no encontrada')
    if obj.status!='pending':raise HTTPException(409,detail='La compra ya tiene una decisión')
    obj.status='approved' if data.decision=='approve' else 'rejected';obj.decided_by_user_id=scope.actor_id
    obj.decision_note=data.note;obj.decided_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='purchase',entity_id=obj.id,action='purchase.'+obj.status,after={'status':obj.status,'note':obj.decision_note})
    db.commit();return purchase_out(obj)
