"""RF-031: plantillas versionadas; solo parámetros FUTUROS, sin reescritura histórica."""
import json
from datetime import datetime,timezone
from pydantic import BaseModel,ConfigDict,Field
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner,require_staff
from app.modules.decisions.audit import audit
from app.modules.extensions.model import AppliedSectorTemplate,TemplateEvent
from app.modules.tenancy.scope import scope_from_context
router=APIRouter(prefix='/sector-templates',tags=['RF-031 Plantillas sectoriales'])

CATALOG={
 'textile':{'name':'Confección y textiles','fields':['talla','color','tipo_tela'],'reminders':['compra_material','entrega'],'default_unit':'pieza'},
 'bakery':{'name':'Panadería y repostería','fields':['sabor','porciones','alergenos'],'reminders':['produccion','entrega'],'default_unit':'pieza'},
 'printing':{'name':'Imprenta y diseño','fields':['formato','tiraje','acabado'],'reminders':['aprobacion_arte','entrega'],'default_unit':'pieza'},
 'furniture':{'name':'Carpintería y mobiliario','fields':['medidas','material','acabado'],'reminders':['corte','entrega'],'default_unit':'pieza'},
}

class ApplyTemplate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(max_length=32)
    confirm:bool

def detail(obj):
    return {'code':obj.template_code,'version':obj.version,'config':json.loads(obj.config_json),'applied_at':obj.applied_at}

@router.get('/catalog')
def catalog(ctx:AuthContext=Depends(require_staff)):
    return [{'code':k,'version':1,'config':v} for k,v in CATALOG.items()]

@router.get('/active')
def active(ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    value=db.get(AppliedSectorTemplate,ctx.user.organization_id)
    return detail(value) if value else {'code':None,'version':None,'config':None,'applied_at':None}

@router.get('/history')
def history(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    rows=db.scalars(select(TemplateEvent).where(TemplateEvent.organization_id==ctx.user.organization_id)
      .order_by(TemplateEvent.version.desc(),TemplateEvent.created_at.desc()).limit(30)).all()
    return [{'code':v.template_code,'version':v.version,'config':json.loads(v.snapshot_json),'created_at':v.created_at} for v in rows]

@router.post('/apply')
def apply(body:ApplyTemplate,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if body.code not in CATALOG:raise HTTPException(status_code=422,detail='Plantilla no permitida')
    if not body.confirm:raise HTTPException(status_code=422,detail='Confirma el cambio de plantilla')
    scope=scope_from_context(ctx);obj=db.get(AppliedSectorTemplate,scope.organization_id)
    if obj is None:
        obj=AppliedSectorTemplate(organization_id=scope.organization_id,template_code=body.code,version=1,
                                   config_json=json.dumps(CATALOG[body.code],ensure_ascii=False));db.add(obj)
    else:
        if obj.template_code==body.code:return detail(obj)
        obj.template_code=body.code;obj.version+=1;obj.config_json=json.dumps(CATALOG[body.code],ensure_ascii=False)
        obj.applied_at=datetime.now(timezone.utc)
    event=TemplateEvent(organization_id=scope.organization_id,actor_id=scope.actor_id,template_code=body.code,
                        version=obj.version,snapshot_json=obj.config_json)
    db.add(event);db.flush()
    audit(db,scope,entity_type='sector_template',entity_id=event.id,action='sector_template.applied',after={'code':body.code,'version':obj.version})
    db.commit();return detail(obj)
