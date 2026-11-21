"""RIA-001..005. All reads and writes are organization-scoped and role-guarded.
No endpoint confirms an order; no content is sent to third-party LLM services.
"""
import json
import logging
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.tenancy.scope import scope_from_context
from app.modules.voice_notes.service import get_voice_note, resolve_voice_note_file, list_voice_notes
from app.modules.products.model import Product
from app.modules.ai.model import TranscriptionJob, StructuredExtraction, FulfillmentEstimate
from app.modules.ai.extract import extract_fields
from app.modules.ai.validate import validate_input
from app.modules.ai.forecast import estimate, ENGINE_VERSION, FEATURE_VERSION
from app.modules.ai import speech
from app.modules.decisions.audit import audit

logger=logging.getLogger(__name__)
router=APIRouter(prefix="/ai",tags=["RIA-001..005 IA asistida"])

class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")

class CreateTranscript(Strict):
    voice_note_id: UUID

class EditTranscript(Strict):
    text: str = Field(min_length=1,max_length=5000)
    confirm: bool

class ExtractInput(Strict):
    raw_text: str = Field(min_length=1,max_length=5000)

class ValidateInput(Strict):
    product_id: str | None = None
    quantity: str | None = None
    unit_price_mxn: str | None = None
    requested_date: str | None = None
    notes: str | None = None

class ReviewExtraction(ValidateInput):
    confirm: bool

class EstimateInput(Strict):
    product_id: UUID
    quantity: Decimal = Field(gt=0,le=100000,max_digits=12,decimal_places=3)
    requested_date: date | None = None
    resource_id: UUID | None = None


def _job_out(x):
    return {"id":str(x.id),"voice_note_id":str(x.voice_note_id),"status":x.status,
            "engine":x.engine,"language":x.language,"duration_ms":x.duration_ms,"attempt_count":x.attempt_count,
            "transcript":x.transcript,"reviewed_text":x.reviewed_text,"error_code":x.error_code,
            "created_at":x.created_at.isoformat() if x.created_at else None,
            "completed_at":x.completed_at.isoformat() if x.completed_at else None,
            "review_required":True}


def _ex_out(x):
    return {"id":str(x.id),"raw_text":x.source_text,"result":json.loads(x.fields_json),
            "reviewed":json.loads(x.reviewed_json) if x.reviewed_json else None,
            "reviewed_at":x.reviewed_at.isoformat() if x.reviewed_at else None,
            "created_at":x.created_at.isoformat() if x.created_at else None}


def _prediction_out(x):
    return {"id":str(x.id),"product_id":str(x.product_id),
            "input":json.loads(x.input_json),"result":json.loads(x.result_json),
            "created_at":x.created_at.isoformat() if x.created_at else None}


def _read_job(db,scope,job_id):
    x=db.scalar(select(TranscriptionJob).where(TranscriptionJob.id==job_id,
                                               TranscriptionJob.organization_id==scope.organization_id))
    if x is None:raise HTTPException(404,"Transcripción no encontrada")
    return x


def process_transcription(bind, job_id):
    """Run after HTTP response. A separate durable task queue is required for prod scale."""
    factory=sessionmaker(bind=bind,expire_on_commit=False)
    with factory() as db:
        x=db.get(TranscriptionJob,job_id)
        if x is None or x.status!='queued':return
        x.status='processing';db.commit()
        org=x.organization_id;note=x.voice_note_id
    try:
        from app.modules.voice_notes.model import VoiceNote
        with factory() as db:
            voice=db.scalar(select(VoiceNote).where(VoiceNote.id==note,
                            VoiceNote.organization_id==org))
            if voice is None:raise ValueError("Archivo de audio no disponible")
            path=resolve_voice_note_file(voice)
        text,duration,engine=speech.transcribe_m4a(path)
        error_code=None
    except speech.SpeechUnavailable:
        text=None;duration=None;engine=None;error_code='engine_unavailable'
    except ValueError:
        text=None;duration=None;engine=None;error_code='invalid_or_long_audio'
    except Exception:
        logger.exception("Error de procesamiento RIA-001, sin transcripción inventada")
        text=None;duration=None;engine=None;error_code='processing_error'
    with factory() as db:
        x=db.get(TranscriptionJob,job_id)
        if x is None or x.status=='cancelled':return
        x.completed_at=datetime.now(timezone.utc)
        if error_code:
            x.error_code=error_code;x.status='failed'
        else:
            x.transcript=text;x.duration_ms=duration;x.engine=engine;x.status='completed'
        db.commit()


@router.get('/voice-note-options')
def voice_notes_for_ai(context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    rows=list_voice_notes(db,scope,only_mine=False,limit=50,offset=0)
    return [{'id':str(n.id),'duration_ms':n.duration_ms,'created_at':n.created_at.isoformat()} for n in rows]


@router.post('/transcriptions',status_code=202)
def transcribe_note(payload:CreateTranscript,background:BackgroundTasks,
                    context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    note=get_voice_note(db,scope,payload.voice_note_id)
    if note.duration_ms is not None and note.duration_ms>60000:
        raise HTTPException(422,"Solo notas de voz de hasta 60 segundos")
    prev=db.scalar(select(TranscriptionJob).where(
        TranscriptionJob.organization_id==scope.organization_id,
        TranscriptionJob.voice_note_id==note.id))
    if prev is not None:return _job_out(prev)
    x=TranscriptionJob(id=uuid4(),organization_id=scope.organization_id,
        actor_id=scope.actor_id,voice_note_id=note.id,duration_ms=note.duration_ms)
    db.add(x)
    audit(db,scope,entity_type='ai_transcription',entity_id=x.id,
          action='ai.transcription_queued',after={'voice_note_id':str(note.id)})
    db.commit();db.refresh(x)
    background.add_task(process_transcription,db.get_bind(),x.id)
    return _job_out(x)


@router.get('/transcriptions')
def list_transcriptions(limit:int=Query(20,ge=1,le=50),
   context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    return [_job_out(x) for x in db.scalars(select(TranscriptionJob).where(
        TranscriptionJob.organization_id==scope.organization_id).order_by(
        TranscriptionJob.created_at.desc(),TranscriptionJob.id.desc()).limit(limit)).all()]


@router.get('/transcriptions/{job_id}')
def get_transcription(job_id:UUID,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return _job_out(_read_job(db,scope_from_context(context),job_id))


@router.post('/transcriptions/{job_id}/retry',status_code=202)
def retry_transcription(job_id:UUID,background:BackgroundTasks,
  context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    x=_read_job(db,scope,job_id)
    if x.status!='failed' or x.attempt_count>=3:
        raise HTTPException(409,"Solo es posible reintentar un trabajo fallido hasta tres veces")
    x.attempt_count+=1;x.status='queued';x.error_code=None;x.completed_at=None
    audit(db,scope,entity_type='ai_transcription',entity_id=x.id,
          action='ai.transcription_retried',after={'attempt':x.attempt_count})
    db.commit();db.refresh(x)
    background.add_task(process_transcription,db.get_bind(),x.id)
    return _job_out(x)


@router.post('/transcriptions/{job_id}/cancel')
def cancel_transcription(job_id:UUID,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context);x=_read_job(db,scope,job_id)
    if x.status not in ('queued','processing'):raise HTTPException(409,"Trabajo no cancelable")
    x.status='cancelled';x.completed_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='ai_transcription',entity_id=x.id,
          action='ai.transcription_cancelled',after={'status':'cancelled'})
    db.commit();db.refresh(x);return _job_out(x)


@router.patch('/transcriptions/{job_id}/text')
def edit_transcription(job_id:UUID,payload:EditTranscript,
  context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context);x=_read_job(db,scope,job_id)
    if not payload.confirm:raise HTTPException(422,"Revisión humana explícita requerida")
    if x.status not in ('completed','reviewed'):raise HTTPException(409,"Trabajo sin texto transcrito")
    x.reviewed_text=payload.text.strip();x.status='reviewed'
    audit(db,scope,entity_type='ai_transcription',entity_id=x.id,action='ai.transcription_reviewed',
          after={'human_reviewed':True})
    db.commit();db.refresh(x);return _job_out(x)


@router.post('/extractions',status_code=201)
def create_extraction(payload:ExtractInput,
    context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    text=payload.raw_text.strip()
    if not text:raise HTTPException(422,"Texto vacío")
    catalog=[{'id':str(p.id),'name':p.name,'sku':p.sku} for p in db.scalars(
        select(Product).where(Product.organization_id==scope.organization_id,
            Product.is_active.is_(True)).order_by(Product.name).limit(500)).all()]
    result=extract_fields(text,catalog)
    x=StructuredExtraction(id=uuid4(),organization_id=scope.organization_id,
        actor_id=scope.actor_id,source_text=text,
        extractor_version=result['engine_version'],fields_json=json.dumps(result,ensure_ascii=False))
    db.add(x)
    audit(db,scope,entity_type='ai_extraction',entity_id=x.id,
          action='ai.extraction_proposed',after={'pending_fields':result['pending_fields'],
            'engine_version':result['engine_version']})
    db.commit();db.refresh(x);return _ex_out(x)


@router.get('/extractions')
def list_extractions(limit:int=Query(20,ge=1,le=50),
  context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    return [_ex_out(x) for x in db.scalars(select(StructuredExtraction).where(
        StructuredExtraction.organization_id==scope.organization_id).order_by(
        StructuredExtraction.created_at.desc(),StructuredExtraction.id.desc()).limit(limit)).all()]


@router.get('/extractions/{extraction_id}')
def get_extraction(extraction_id:UUID,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    x=db.scalar(select(StructuredExtraction).where(StructuredExtraction.id==extraction_id,
                StructuredExtraction.organization_id==scope.organization_id))
    if x is None:raise HTTPException(404,"Extracción no encontrada")
    return _ex_out(x)


@router.post('/extractions/{extraction_id}/review')
def review_extraction(extraction_id:UUID,payload:ReviewExtraction,
  context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    x=db.scalar(select(StructuredExtraction).where(StructuredExtraction.id==extraction_id,
                StructuredExtraction.organization_id==scope.organization_id).with_for_update())
    if x is None:raise HTTPException(404,"Extracción no encontrada")
    if x.reviewed_json is not None:raise HTTPException(409,"Esta revisión ya fue guardada")
    if not payload.confirm:raise HTTPException(422,"Aprobación humana explícita requerida")
    corrected=payload.model_dump(exclude={'confirm'})
    verdict=validate_input(db,scope,corrected)
    if not verdict['valid']:raise HTTPException(422,detail=verdict['issues'])
    # Original suggested values and their verbatim provenance are immutable.
    reviewed={'fields':corrected,'origin':'human_confirmed',
              'order_confirmed':False,'changes_applied':False}
    x.reviewed_json=json.dumps(reviewed,ensure_ascii=False)
    x.reviewed_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='ai_extraction',entity_id=x.id,
          action='ai.extraction_human_reviewed',after={'confirmed_by_human':True,'order_confirmed':False})
    db.commit();db.refresh(x)
    return _ex_out(x)


@router.post('/validate')
def validate_fields(payload:ValidateInput,context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return validate_input(db,scope_from_context(context),payload.model_dump())


@router.post('/estimates',status_code=201)
def create_estimate(payload:EstimateInput,
    context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    result=estimate(db,scope,product_id=payload.product_id,quantity=payload.quantity,
                    due_date=payload.requested_date,resource_id=payload.resource_id)
    inp={k:str(v) if v is not None else None for k,v in payload.model_dump().items()}
    x=FulfillmentEstimate(id=uuid4(),organization_id=scope.organization_id,
        actor_id=scope.actor_id,product_id=payload.product_id,
        engine_version=ENGINE_VERSION,feature_version=FEATURE_VERSION,
        input_json=json.dumps(inp),result_json=json.dumps(result,ensure_ascii=False))
    db.add(x)
    audit(db,scope,entity_type='ai_estimate',entity_id=x.id,action='ai.baseline_estimate_created',
          after={'engine_version':ENGINE_VERSION,'quality_status':result['quality_status']})
    db.commit();db.refresh(x);return _prediction_out(x)


@router.get('/estimates')
def list_estimates(limit:int=Query(20,ge=1,le=50),
  context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    scope=scope_from_context(context)
    return [_prediction_out(x) for x in db.scalars(select(FulfillmentEstimate).where(
        FulfillmentEstimate.organization_id==scope.organization_id).order_by(
        FulfillmentEstimate.created_at.desc(),FulfillmentEstimate.id.desc()).limit(limit)).all()]
