"""RIA-006..018. Safe tenant-bound APIs; no mutation of orders, quotes, stock or prices.

Statistical quality is not implied by a successful HTTP response. All operational
recommendations are drafts and snapshots, never binding decisions.
"""
import hashlib
import json
from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff,require_owner
from app.modules.tenancy.scope import scope_from_context
from app.modules.ai_ops.model import AIModelVersion,AIEvidenceRun,AIQualityWindow
from app.modules.ai_ops.evaluation import evaluate_temporal,FEATURE_VERSION,ALLOWED
from app.modules.ai_ops.planning import three_scenarios,product_resource
from app.modules.ai_ops.twin import monte_carlo
from app.modules.ai.forecast import estimate as base_estimate
from app.modules.ai.model import StructuredExtraction
from app.modules.products.model import Product
from app.modules.decisions.audit import audit

router=APIRouter(prefix='/ai-ops',tags=['RIA-006..RIA-018 IA verificable'])
ENGINE='rules_baseline_2.0';MODEL_KEY='duration'

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Sample(Strict):
    created_on:date
    product_id:str=Field(min_length=1,max_length=80)
    quantity:Decimal=Field(gt=0,le=100000)
    base_minutes_per_unit:Decimal=Field(gt=0,le=100000)
    promised_minutes:Decimal=Field(gt=0,le=100000000)
    actual_minutes:Decimal=Field(gt=0,le=100000000)
    delayed:bool
class Train(Strict):
    observations:list[Sample]=Field(min_length=30,max_length=200)
    data_origin:str=Field(pattern='^(synthetic|real_reviewed)$')
    confirm:bool
class Approval(Strict):confirm:bool
class Forecast(Strict):
    product_id:UUID
    resource_id:UUID|None=None
    quantity:Decimal=Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    requested_date:date|None=None
class Optimize(Strict):
    product_id:UUID
    resource_id:UUID
    quantity:Decimal=Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    requested_date:date
    start_date:date|None=None
    shift_minutes:int=Field(default=480,ge=60,le=1440)
class Agent(Strict):
    kind:str=Field(pattern='^(quote_draft|task_draft)$')
    product_id:UUID
    quantity:Decimal=Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    customer_text:str=Field(default='',max_length=1000)
class Sensitive(Strict):
    action:str=Field(pattern='^(orders.confirm|messaging.send|purchases.write|prices.modify)$')
    confirm:bool=False
class Twin(Strict):
    product_id:UUID
    resource_id:UUID
    quantity:Decimal=Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    start_date:date|None=None
    shifts:int=Field(default=1,ge=1,le=3)
    interruption_probability:float=Field(default=.1,ge=0,le=.5)
    supplier_id:UUID|None=None
    supplier_delay_days:int=Field(default=4,ge=0,le=30)
    runs:int=Field(default=200,ge=100,le=500)
    seed:int=Field(default=42,ge=0,le=2147483647)


def dumps(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def hash_config(x):return hashlib.sha256(dumps(x).encode()).hexdigest()
def model_out(m):
    return {'id':str(m.id),'model_key':m.model_key,'version':m.version,'feature_version':m.feature_version,
      'engine_kind':m.engine_kind,'config_sha256':m.config_sha256,'metrics':json.loads(m.metrics_json),
      'status':m.status,'trained_at':m.trained_at.isoformat() if m.trained_at else None,
      'approved_at':m.approved_at.isoformat() if m.approved_at else None,
      'configuration':json.loads(m.config_json),'synthetic_not_real':json.loads(m.metrics_json).get('data_origin')=='synthetic'}
def run_out(r):
    return {'id':str(r.id),'kind':r.kind,'model_version':r.engine_version,'feature_version':r.feature_version,
      'model_id':str(r.model_id) if r.model_id else None,'configuration_sha256':r.config_sha256,
      'input':json.loads(r.input_json),'result':json.loads(r.result_json),
      'created_at':r.created_at.isoformat() if r.created_at else None}

def active_model(db,scope,create=False):
    m=db.scalar(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
      AIModelVersion.model_key==MODEL_KEY,AIModelVersion.status=='active').order_by(AIModelVersion.trained_at.desc()))
    if not m and create:
        config={'engine_kind':'deterministic_baseline_not_trained',
           'unit_minutes_source':'product_catalog','feature_version':FEATURE_VERSION}
        m=AIModelVersion(id=uuid4(),organization_id=scope.organization_id,actor_id=scope.actor_id,
           model_key=MODEL_KEY,version='rules-base-2.0',feature_version=FEATURE_VERSION,
           engine_kind='deterministic_baseline_not_trained',config_json=dumps(config),
           config_sha256=hash_config(config),metrics_json=dumps({'metrics_validated':False,'data_origin':'none'}),
           status='active',approved_at=datetime.now(timezone.utc))
        db.add(m);db.flush()
    return m

def save_run(db,scope,kind,inputs,results,model=None):
    config={'engine_kind':ENGINE,'feature_version':FEATURE_VERSION,'planning':True}
    # Non-forecast planners are ALWAYS deterministic; never mislabel their
    # output with an active learned-duration model version.
    if model is not None:
        m=model
    else:
        m=db.scalar(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
           AIModelVersion.model_key==MODEL_KEY,AIModelVersion.version=='rules-base-2.0'))
        if m is None:
            active_model(db,scope,create=True)
            m=db.scalar(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
               AIModelVersion.model_key==MODEL_KEY,AIModelVersion.version=='rules-base-2.0'))
    r=AIEvidenceRun(id=uuid4(),organization_id=scope.organization_id,actor_id=scope.actor_id,
       model_id=m.id if m else None,kind=kind,engine_version=m.version if m else ENGINE,
       feature_version=m.feature_version if m else FEATURE_VERSION,
       config_sha256=m.config_sha256 if m else hash_config(config),
       input_json=dumps(inputs),result_json=dumps(results))
    db.add(r);db.flush()
    audit(db,scope,entity_type='ai_run',entity_id=r.id,action='ai.'+kind+'.prepared',
      after={'model_version':r.engine_version,'side_effects':False})
    db.commit();db.refresh(r);return run_out(r)

@router.get('/models')
def list_models(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    return [model_out(x) for x in db.scalars(select(AIModelVersion).where(
      AIModelVersion.organization_id==scope.organization_id).order_by(AIModelVersion.trained_at.desc()).limit(50)).all()]

@router.post('/models/train',status_code=201)
def train_candidate(body:Train,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(422,'Entrenamiento requiere confirmación explícita')
    scope=scope_from_context(ctx)
    active_model(db,scope,create=True)  # Preserve a restorable baseline before candidate training.
    # Only known tenant products in this demonstration may be labelled.
    samples=[{k:(v.isoformat() if isinstance(v,date) else str(v) if isinstance(v,Decimal) else v)
              for k,v in s.model_dump().items()} for s in body.observations]
    product_ids={x['product_id'] for x in samples}
    available={str(x) for x in db.scalars(select(Product.id).where(Product.organization_id==scope.organization_id,
      Product.is_active.is_(True))).all()}
    if not product_ids.issubset(available):raise HTTPException(422,'Observaciones de productos fuera del catálogo de esta empresa')
    try:report,config=evaluate_temporal(samples)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    report['data_origin']=body.data_origin
    version='median-'+config['dataset_sha256'][:16]
    prev=db.scalar(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
     AIModelVersion.model_key==MODEL_KEY,AIModelVersion.version==version))
    if prev:return model_out(prev)
    x=AIModelVersion(id=uuid4(),organization_id=scope.organization_id,actor_id=scope.actor_id,
      model_key=MODEL_KEY,version=version,feature_version=FEATURE_VERSION,
      engine_kind='per_product_median_from_train_only',config_json=dumps(config),
      config_sha256=hash_config(config),metrics_json=dumps(report),status='candidate')
    db.add(x);db.flush()
    audit(db,scope,entity_type='ai_model',entity_id=x.id,action='ai.model_candidate_trained',
      after={'version':version,'data_origin':body.data_origin,'test_mae':report['test']['candidate']['MAE_minutes'],
             'train_count':report['split']['train_count']})
    db.commit();db.refresh(x);return model_out(x)


def get_model(db,scope,model_id,lock=False):
    stmt=select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,AIModelVersion.id==model_id)
    x=db.scalar(stmt.with_for_update() if lock else stmt)
    if not x:raise HTTPException(404,'Versión de modelo no encontrada')
    return x

@router.post('/models/{model_id}/promote')
def promote(model_id:UUID,body:Approval,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(422,'Aprobación de despliegue explícita requerida')
    scope=scope_from_context(ctx);m=get_model(db,scope,model_id,True)
    if m.status!='candidate':raise HTTPException(409,'Solo candidatos pueden desplegarse')
    stats=json.loads(m.metrics_json)
    if stats.get('data_origin')!='real_reviewed':raise HTTPException(409,'Un conjunto sintético no autoriza despliegue')
    if stats['split']['test_count']<5:raise HTTPException(409,'Conjunto de prueba insuficiente')
    if (stats['validation']['candidate']['MAE_minutes']>=stats['validation']['baseline']['MAE_minutes'] or
        stats['test']['candidate']['MAE_minutes']>=stats['test']['baseline']['MAE_minutes']):
        raise HTTPException(409,'Modelo inferior o igual al baseline; despliegue bloqueado')
    for x in db.scalars(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
      AIModelVersion.model_key==MODEL_KEY,AIModelVersion.status=='active').with_for_update()).all():x.status='archived'
    db.flush()  # Release partial unique active-index before promoting replacement.
    m.status='active';m.approved_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='ai_model',entity_id=m.id,action='ai.model_promoted',
      after={'version':m.version,'test_mae':stats['test']['candidate']['MAE_minutes']})
    db.commit();return model_out(m)

@router.post('/models/{model_id}/rollback')
def rollback(model_id:UUID,body:Approval,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(422,'Restauración explícita requerida')
    scope=scope_from_context(ctx);m=get_model(db,scope,model_id,True)
    if m.status!='archived':raise HTTPException(409,'Solo una versión anterior archivada es restaurable')
    # A rollback restores an ALREADY APPROVED version, never promotes an unevaluated candidate.
    if m.approved_at is None:raise HTTPException(409,'Versión histórica nunca aprobada')
    for x in db.scalars(select(AIModelVersion).where(AIModelVersion.organization_id==scope.organization_id,
      AIModelVersion.model_key==MODEL_KEY,AIModelVersion.status=='active').with_for_update()).all():x.status='archived'
    db.flush()  # Release partial unique active-index before promoting replacement.
    m.status='active'
    audit(db,scope,entity_type='ai_model',entity_id=m.id,action='ai.model_rollback',after={'restored':m.version})
    db.commit();return model_out(m)

@router.post('/forecast',status_code=201)
def forecast(body:Forecast,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    baseline=base_estimate(db,scope,product_id=body.product_id,quantity=body.quantity,
                          due_date=body.requested_date,resource_id=body.resource_id)
    m=active_model(db,scope,create=True)
    cfg=json.loads(m.config_json)
    counts=cfg.get('training_counts',{});factors=cfg.get('factors_minutes_per_unit',{})
    key=str(body.product_id);support=counts.get(key,0)
    historical=m.engine_kind=='per_product_median_from_train_only' and support>=8 and key in factors
    if historical:
        duration=round(float(body.quantity)*float(factors[key]),3)
        quality='historical_model_evaluated';uncertainty='sample_limited' if support<20 else 'medium'
    else:
        duration=baseline['estimated_minutes'];quality='insufficient_data_fallback';uncertainty='high'
    result={'model_id':str(m.id),'engine_version':m.version,'feature_version':m.feature_version,
      'configuration_sha256':m.config_sha256,'estimated_minutes':duration,'baseline_estimated_minutes':baseline['estimated_minutes'],
      'quality_status':quality,'uncertainty':uncertainty,'historical_samples_for_product':support,
      'baseline':baseline,'warnings':(["Datos escasos o fuera de dominio; se aplicaron reglas base."] if not historical else
      ['Estimación empírica: requiere validación continua y no garantiza la fecha.']),
      'prediction_validated_for_customer':False,'changes_applied':False}
    return save_run(db,scope,'forecast',body.model_dump(),result,m)

@router.post('/optimize',status_code=201)
def optimize(body:Optimize,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx);start=body.start_date or date.today()
    if start<date.today():raise HTTPException(422,'Fecha inicial anterior al día actual')
    result=three_scenarios(db,scope.organization_id,product_id=body.product_id,resource_id=body.resource_id,
      quantity=body.quantity,start=start,deadline=body.requested_date,shift_minutes=body.shift_minutes)
    return save_run(db,scope,'optimization',body.model_dump(),result)

SAFE_TOOLS={'catalog.read','inventory.read','calendar.read'}
@router.post('/agent/prepare',status_code=201)
def prepare_agent(body:Agent,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    product=db.scalar(select(Product).where(Product.id==body.product_id,Product.organization_id==scope.organization_id,
      Product.is_active.is_(True)))
    if product is None:raise HTTPException(404,'Producto no encontrado')
    # Raw customer input is UNTRUSTED evidence: it is never parsed into commands or tools.
    steps=[{'tool':'catalog.read','mode':'read_only'}]
    if body.kind=='task_draft':steps.append({'tool':'calendar.read','mode':'read_only'})
    assert all(s['tool'] in SAFE_TOOLS for s in steps)
    quote={'product_id':str(product.id),'product_name':product.name,'quantity':str(body.quantity),
           'suggested_unit_price_mxn':str(product.price_mxn),
           'suggested_total_mxn':str((body.quantity*product.price_mxn).quantize(Decimal('.01')))}
    result={'draft_kind':body.kind,'draft':quote,'planned_operations':steps,
      'origin':'trusted_product_catalog_and_explicit_user_fields',
      'customer_text_used_as_commands':False,'customer_text_is_untrusted_data':True,
      'requires_explicit_human_approval':True,'approved':False,
      'forbidden_tools':['orders.confirm','messaging.send','purchases.write','prices.modify'],
      'changes_applied':False,'engine_kind':'registered_read_only_tools_rules_not_llm'}
    # Retain only digest of client content, not potentially sensitive raw text.
    inp={'kind':body.kind,'product_id':str(body.product_id),'quantity':str(body.quantity),
         'customer_text_sha256':hashlib.sha256(body.customer_text.encode()).hexdigest()}
    return save_run(db,scope,'agent',inp,result)

@router.post('/agent/attempt-sensitive')
def denied_sensitive_action(body:Sensitive,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    entity=uuid4()
    audit(db,scope,entity_type='ai_safety_denial',entity_id=entity,action='ai.sensitive_tool_denied',
      after={'attempted_tool':body.action,'approval_flag_received':body.confirm,
             'reason':'no_executable_sensitive_tools_registered','side_effects':False})
    db.commit()
    raise HTTPException(403,'Operación sensible bloqueada y auditada: no existe herramienta ejecutable')

@router.get('/runs')
def runs(kind:str|None=Query(default=None,pattern='^(forecast|optimization|agent|digital_twin)$'),
             limit:int=Query(default=15,ge=1,le=50),ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    stmt=select(AIEvidenceRun).where(AIEvidenceRun.organization_id==scope.organization_id)
    if kind:stmt=stmt.where(AIEvidenceRun.kind==kind)
    return [run_out(x) for x in db.scalars(stmt.order_by(AIEvidenceRun.created_at.desc(),AIEvidenceRun.id.desc()).limit(limit)).all()]

@router.get('/runs/{run_id}')
def run_by_id(run_id:UUID,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    x=db.scalar(select(AIEvidenceRun).where(AIEvidenceRun.id==run_id,AIEvidenceRun.organization_id==scope.organization_id))
    if not x:raise HTTPException(404,'Evidencia no encontrada')
    return run_out(x)

@router.post('/quality/refresh',status_code=201)
def refresh_quality(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx);m=active_model(db,scope,create=True)
    extracts=db.scalars(select(StructuredExtraction).where(StructuredExtraction.organization_id==scope.organization_id).limit(2000)).all()
    reviews=errors=0
    for e in extracts:
        if not e.reviewed_json:continue
        reviews+=1
        original=json.loads(e.fields_json).get('fields',{})
        revised=json.loads(e.reviewed_json).get('fields',{})
        for k,f in original.items():
            expected=f.get('value');expected=expected.get('id') if isinstance(expected,dict) else expected
            if revised.get(k)!=expected:errors+=1
    total_runs=db.scalar(select(func.count()).select_from(AIEvidenceRun).where(
      AIEvidenceRun.organization_id==scope.organization_id,AIEvidenceRun.engine_version==m.version)) or 0
    # Coarse 4-bin quantity distribution without storing any per-client text.
    forecast_rows=db.scalars(select(AIEvidenceRun).where(AIEvidenceRun.organization_id==scope.organization_id,
      AIEvidenceRun.kind=='forecast',AIEvidenceRun.model_id==m.id).order_by(AIEvidenceRun.created_at.desc()).limit(300)).all()
    bins=[0,0,0,0]
    for entry in forecast_rows:
        try:
            value=Decimal(json.loads(entry.input_json)['quantity'])
            index=0 if value<=1 else 1 if value<=5 else 2 if value<=20 else 3
            bins[index]+=1
        except (KeyError,ValueError,TypeError):pass
    history=db.scalars(select(AIQualityWindow).where(AIQualityWindow.organization_id==scope.organization_id,
      AIQualityWindow.model_id==m.id).order_by(AIQualityWindow.created_at.desc()).limit(1)).all()
    prior=json.loads(history[0].metrics_json) if history else None
    previous=prior['reviewed_extractions'] if prior else 0
    previous_hist=prior.get('quantity_histogram',[0,0,0,0]) if prior else [0,0,0,0]
    current_n=sum(bins);previous_n=sum(previous_hist)
    total_variation=(round(.5*sum(abs(a/current_n-b/previous_n) for a,b in zip(bins,previous_hist)),4)
                     if current_n>=20 and previous_n>=20 else None)
    stats={'model_version':m.version,'reviewed_extractions':reviews,'corrected_fields_count':errors,
      'correction_rate_per_review':round(errors/(reviews*5),4) if reviews else None,
      'runs_for_version':total_runs,'review_count_change':reviews-previous,
      'quantity_histogram':bins,'quantity_bins':['<=1','1-5','5-20','>20'],
      'quantity_total_variation_vs_previous':total_variation,
      'distribution_shift_alert':total_variation>0.25 if total_variation is not None else None,
      'drift_metric_type':'total_variation_quantity_bins_descriptive_not_validated',
      'contains_private_text':False,'status':'monitoring_unvalidated'}
    row=AIQualityWindow(id=uuid4(),organization_id=scope.organization_id,actor_id=scope.actor_id,
      model_id=m.id,version=m.version,metrics_json=dumps(stats))
    db.add(row);db.flush()
    audit(db,scope,entity_type='ai_quality',entity_id=row.id,action='ai.quality_aggregated',
      after={'model_version':m.version,'contains_raw_text':False})
    db.commit();return {'id':str(row.id),'statistics':stats}

@router.get('/quality')
def quality(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx)
    return [{'id':str(x.id),'version':x.version,'statistics':json.loads(x.metrics_json),
         'created_at':x.created_at.isoformat() if x.created_at else None}
       for x in db.scalars(select(AIQualityWindow).where(AIQualityWindow.organization_id==scope.organization_id)
         .order_by(AIQualityWindow.created_at.desc()).limit(30)).all()]

@router.post('/twin',status_code=201)
def twin(body:Twin,ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx);start=body.start_date or date.today()
    if start<date.today():raise HTTPException(422,'Fecha inicial anterior al día actual')
    result=monte_carlo(db,scope.organization_id,product_id=body.product_id,resource_id=body.resource_id,
      quantity=body.quantity,starting_date=start,shifts=body.shifts,
      interruption_probability=body.interruption_probability,supplier_id=body.supplier_id,
      supplier_delay_days=body.supplier_delay_days,seed=body.seed,runs=body.runs)
    return save_run(db,scope,'digital_twin',body.model_dump(),result)
