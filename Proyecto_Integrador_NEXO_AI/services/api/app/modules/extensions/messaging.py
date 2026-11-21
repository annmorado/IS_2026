"""RF-030: WhatsApp Cloud API oficial. Sin credenciales/consentimiento no envía nada.
No se admiten webhooks ni automatizaciones entrantes en este entregable.
"""
import os,re,json
from datetime import datetime,timedelta,timezone
from uuid import UUID
import httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner
from app.modules.decisions.audit import audit
from app.modules.extensions.model import MessagingConfig,MessagingEvent,MessagingConsent
from app.modules.extensions.entitlements import consume,snapshot
from app.modules.tenancy.scope import scope_from_context
router=APIRouter(prefix='/messaging',tags=['RF-030 Integraciones oficiales'])

class Config(BaseModel):
    model_config=ConfigDict(extra='forbid')
    phone_number_id:str=Field(pattern=r'^\d{5,40}$')
    enabled:bool=False

class ConsentCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    recipient_e164:str=Field(pattern=r'^\+[1-9]\d{7,14}$')
    evidence_reference:str=Field(min_length=10,max_length=160)
    valid_days:int=Field(default=90,ge=1,le=180)
    confirm:bool

class ConsentRevoke(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm:bool

@router.post('/consents',status_code=201)
def record_consent(body:ConsentCreate,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(status_code=422,detail='Confirmación de consentimiento requerida')
    scope=scope_from_context(ctx)
    row=db.scalar(select(MessagingConsent).where(MessagingConsent.organization_id==scope.organization_id,
        MessagingConsent.recipient_e164==body.recipient_e164).with_for_update())
    if row is None:
        row=MessagingConsent(organization_id=scope.organization_id,actor_id=scope.actor_id,recipient_e164=body.recipient_e164,
            evidence_reference=body.evidence_reference,expires_at=datetime.now(timezone.utc)+timedelta(days=body.valid_days))
        db.add(row)
    else:
        if row.revoked_at is None and (row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at)>datetime.now(timezone.utc):
            raise HTTPException(status_code=409,detail='Ya existe consentimiento vigente; revócalo antes de registrar otro')
        row.evidence_reference=body.evidence_reference;row.expires_at=datetime.now(timezone.utc)+timedelta(days=body.valid_days)
        row.revoked_at=None;row.actor_id=scope.actor_id
    db.flush()
    audit(db,scope,entity_type='messaging_consent',entity_id=row.id,action='messaging.consent_recorded',after={'recipient_tail':body.recipient_e164[-4:],'valid_days':body.valid_days})
    db.commit();return {'id':str(row.id),'recipient_tail':row.recipient_e164[-4:],'expires_at':row.expires_at,'active':True}

@router.get('/consents')
def consents(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    now=datetime.now(timezone.utc)
    rows=db.scalars(select(MessagingConsent).where(MessagingConsent.organization_id==ctx.user.organization_id)
       .order_by(MessagingConsent.created_at.desc()).limit(40)).all()
    return [{'id':str(row.id),'recipient_tail':row.recipient_e164[-4:],'expires_at':row.expires_at,
             'active':row.revoked_at is None and (row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at)>now} for row in rows]

@router.post('/consents/{consent_id}/revoke')
def revoke_consent(consent_id:UUID,body:ConsentRevoke,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:raise HTTPException(status_code=422,detail='Confirmación requerida')
    scope=scope_from_context(ctx);row=db.scalar(select(MessagingConsent).where(MessagingConsent.id==consent_id,
        MessagingConsent.organization_id==scope.organization_id).with_for_update())
    if row is None:raise HTTPException(status_code=404,detail='Consentimiento no encontrado')
    if row.revoked_at is not None:raise HTTPException(status_code=409,detail='Consentimiento ya revocado')
    row.revoked_at=datetime.now(timezone.utc)
    audit(db,scope,entity_type='messaging_consent',entity_id=row.id,action='messaging.consent_revoked',after={'recipient_tail':row.recipient_e164[-4:]})
    db.commit();return {'id':str(row.id),'active':False}

class SendTemplate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    recipient_e164:str=Field(pattern=r'^\+[1-9]\d{7,14}$')
    template_name:str=Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')
    consent_reference:str=Field(min_length=10,max_length=160)
    confirm:bool

@router.get('/configuration')
def config(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    c=db.get(MessagingConfig,ctx.user.organization_id)
    return {'provider':'whatsapp_cloud','configured':bool(c),'enabled':c.enabled if c else False,
       'phone_number_id':c.phone_number_id if c else None,'credentials_present':credentials(ctx.user.organization_id,c) if c else False,
       'notice':'Requiere credenciales oficiales por organización, consentimiento y aprobación explícita; sin envíos automáticos.'}

def credentials(org_id,c):
    return bool(c and os.getenv('NEXO_WHATSAPP_TOKEN') and os.getenv('NEXO_WHATSAPP_ORG_ID')==str(org_id)
            and os.getenv('NEXO_WHATSAPP_PHONE_ID')==c.phone_number_id)

@router.put('/configuration')
def configure(body:Config,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(ctx);c=db.get(MessagingConfig,scope.organization_id)
    if c is None:
        c=MessagingConfig(organization_id=scope.organization_id,phone_number_id=body.phone_number_id,enabled=body.enabled);db.add(c)
    else:c.phone_number_id=body.phone_number_id;c.enabled=body.enabled
    audit(db,scope,entity_type='messaging_config',entity_id=scope.organization_id,action='messaging.configured',after={'enabled':body.enabled,'provider':'whatsapp_cloud'})
    db.commit();return config(ctx,db)

@router.post('/send-template')
def send_template(body:SendTemplate,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=422,detail='Confirmación afirmativa obligatoria')
    scope=scope_from_context(ctx);c=db.get(MessagingConfig,scope.organization_id)
    if not c or not c.enabled or not credentials(scope.organization_id,c):
        raise HTTPException(status_code=409,detail='Mensajería no configurada para esta organización o faltan credenciales oficiales')
    # Owner attestations must exist, still be current, not revoked and match evidence.
    consent=db.scalar(select(MessagingConsent).where(MessagingConsent.organization_id==scope.organization_id,
        MessagingConsent.recipient_e164==body.recipient_e164))
    if not consent or consent.revoked_at is not None or consent.evidence_reference!=body.consent_reference or \
       (consent.expires_at.replace(tzinfo=timezone.utc) if consent.expires_at.tzinfo is None else consent.expires_at)<=datetime.now(timezone.utc):
        raise HTTPException(status_code=403,detail='Destinatario sin consentimiento documentado y vigente')
    # Check limit before calling provider, consume only after accepted send.
    ent=snapshot(db,scope.organization_id)
    if ent['usage']['messaging']>=ent['limits']['messaging']:
        raise HTTPException(status_code=403,detail='Mensajería fuera del plan o límite de uso alcanzado')
    graph=os.getenv('NEXO_WHATSAPP_GRAPH_VERSION','v24.0')
    if not re.fullmatch(r'v\d{1,2}\.\d{1,2}',graph):
        raise HTTPException(status_code=500,detail='Versión Graph API no válida')
    url=f'https://graph.facebook.com/{graph}/{c.phone_number_id}/messages'
    payload={'messaging_product':'whatsapp','to':body.recipient_e164.lstrip('+'),
        'type':'template','template':{'name':body.template_name,'language':{'code':'es_MX'}}}
    try:
        r=httpx.post(url,json=payload,headers={'Authorization':'Bearer '+os.environ['NEXO_WHATSAPP_TOKEN']},timeout=10.0)
        if r.status_code not in (200,201):
            raise HTTPException(status_code=502,detail='Proveedor rechazó el mensaje; verifica plantilla y consentimiento')
        raw=r.json();provider_id=(raw.get('messages') or [{}])[0].get('id')
        if not isinstance(provider_id,str) or len(provider_id)>150 or not provider_id:
            raise HTTPException(status_code=502,detail='Proveedor no confirmó identificador de mensaje')
    except (httpx.TimeoutException,httpx.RequestError) as exc:
        raise HTTPException(status_code=503,detail='Proveedor no disponible; comprueba el estado antes de reintentar') from exc
    # Avoid leaking destination/full consent reference in logs and audit.
    event=MessagingEvent(organization_id=scope.organization_id,actor_id=scope.actor_id,
         recipient_tail=body.recipient_e164[-4:],consent_reference=body.consent_reference,
         template_name=body.template_name,provider_message_id=provider_id)
    db.add(event);db.flush();consume(db,scope.organization_id,'messaging')
    audit(db,scope,entity_type='message',entity_id=event.id,action='messaging.sent_with_consent',after={'template':body.template_name,'provider':'whatsapp_cloud'})
    db.commit();return {'id':str(event.id),'provider_message_id':provider_id,'status':'sent_to_provider',
        'notice':'Aceptado por el proveedor, no implica entrega al destinatario'}

@router.get('/events')
def events(ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    records=db.scalars(select(MessagingEvent).where(MessagingEvent.organization_id==ctx.user.organization_id)
         .order_by(MessagingEvent.created_at.desc()).limit(20)).all()
    return [{'id':str(e.id),'recipient_tail':e.recipient_tail,'template':e.template_name,
             'created_at':e.created_at,'provider_message_id':e.provider_message_id} for e in records]
