"""RF-032: agentes de reglas deterministas. SOLO planean herramientas de lectura.
No ejecutan compras, cotizaciones, mensajes ni confirmaciones bajo ningún permiso.
"""
import json
from uuid import UUID
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner
from app.modules.decisions.audit import audit
from app.modules.extensions.entitlements import consume
from app.modules.extensions.model import AgentWorkflow
from app.modules.orders.model import Order
from app.modules.materials.model import Material
from app.modules.tenancy.scope import scope_from_context
router=APIRouter(prefix='/agents',tags=['RF-032 Flujos multiagente supervisados'])
SAFE_TOOLS={'orders.read','materials.read','calendar.read'}
AGENTS={'capacity_planner':('orders.read','calendar.read'),
        'material_advisor':('materials.read','orders.read'),
        'followup_drafter':('orders.read',)}
class PlanInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    agent_kind:str=Field(max_length=32)
    order_id:UUID|None=None
    objective:str=Field(min_length=10,max_length=300)
class ApproveInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm:bool

def present(w):
    return {'id':str(w.id),'agent_kind':w.agent_kind,'status':w.status,'engine_version':w.engine_version,
            'input':json.loads(w.input_json),'result':json.loads(w.result_json),'created_at':w.created_at,
            'authorized_at':w.authorized_at,'side_effects_executed':False}

@router.post('/prepare',status_code=201)
def prepare(body:PlanInput,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if body.agent_kind not in AGENTS:
        raise HTTPException(status_code=422,detail='Agente no autorizado')
    scope=scope_from_context(ctx)
    if body.order_id is not None:
        order=db.scalar(select(Order).where(Order.id==body.order_id,Order.organization_id==scope.organization_id))
        if not order:raise HTTPException(status_code=404,detail='Pedido no encontrado')
    else:order=None
    steps=[{'agent':body.agent_kind,'tool':x,'mode':'read_only','requires_approval':True} for x in AGENTS[body.agent_kind]]
    if any(x['tool'] not in SAFE_TOOLS for x in steps):
        raise HTTPException(status_code=500,detail='Herramienta fuera de lista segura')
    observations=[]
    if body.agent_kind=='material_advisor':
        qty=db.scalar(select(func.count()).select_from(Material).where(Material.organization_id==scope.organization_id,Material.quantity_available<=0)) or 0
        observations.append(f'Materiales registrados sin existencias: {qty}. Evaluación orientativa; no reserva ni compra.')
    elif body.agent_kind=='capacity_planner':
        observations.append('Consulta la carga del calendario y los compromisos antes de asignar recursos; no se reserva capacidad.')
    else:
        observations.append('Preparar borrador de seguimiento para revisión humana. No se envía por ningún canal.')
    if order:observations.append('Pedido de referencia: '+str(order.id))
    result={'steps':steps,'observations':observations,'requires_owner_authorization':True,
            'blocked_tools':['purchases.write','messaging.send','orders.confirm','quotes.approve'],
            'automated_external_actions':False,'model_type':'deterministic_rules','not_an_llm':True}
    consume(db,scope.organization_id,'agents')
    w=AgentWorkflow(organization_id=scope.organization_id,actor_id=scope.actor_id,
        agent_kind=body.agent_kind,input_json=body.model_dump_json(),result_json=json.dumps(result,ensure_ascii=False))
    db.add(w);db.flush()
    audit(db,scope,entity_type='agent_workflow',entity_id=w.id,action='agent.prepared',after={'agent_kind':body.agent_kind,'read_only':True})
    db.commit();return present(w)

@router.get('/workflows')
def workflows(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    return [present(x) for x in db.scalars(select(AgentWorkflow).where(AgentWorkflow.organization_id==ctx.user.organization_id)
         .order_by(AgentWorkflow.created_at.desc()).limit(40)).all()]

@router.post('/workflows/{workflow_id}/authorize')
def authorize(workflow_id:UUID,body:ApproveInput,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(status_code=422,detail='Confirmación explícita obligatoria')
    scope=scope_from_context(ctx)
    w=db.scalar(select(AgentWorkflow).where(AgentWorkflow.id==workflow_id,AgentWorkflow.organization_id==scope.organization_id).with_for_update())
    if not w:raise HTTPException(status_code=404,detail='Flujo no encontrado')
    if w.status!='prepared':raise HTTPException(status_code=409,detail='Flujo ya autorizado o finalizado')
    payload=json.loads(w.result_json)
    if any(step['tool'] not in SAFE_TOOLS or step['mode']!='read_only' for step in payload['steps']):
        raise HTTPException(status_code=403,detail='Herramienta no permitida')
    w.status='authorized';w.authorized_by=scope.actor_id;w.authorized_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='agent_workflow',entity_id=w.id,action='agent.readonly_plan_authorized',after={'only_readonly':True})
    db.commit();return present(w)
