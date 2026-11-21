"""RF-028–032 acceptance: per tenant quotas, human review, explicit consent,
immutable order history and read-only, owner-authorized agent workflows.
"""
import io,os
from datetime import datetime,timedelta,timezone
from uuid import UUID
import pytest
from unittest.mock import patch
from PIL import Image,ImageDraw
from sqlalchemy import select,func
from test_quotes import ctx,order
from app.modules.extensions import ocr
from app.modules.extensions.model import (Subscription,FeatureUsage,OcrProposal,MessagingEvent,
    AppliedSectorTemplate,TemplateEvent,AgentWorkflow)
from app.modules.orders.model import Order
from app.modules.decisions.model import AuditEvent
ROOT='/api/v1'
def request(c,route,method='GET',body=None,who='owner',files=None):
    return c['client'].request(method,ROOT+route,headers=c['auth'][who],json=body if files is None else None,files=files)

def photo():
    i=Image.new('RGB',(600,150),'white');ImageDraw.Draw(i).text((20,35),'FACTURA TOTAL $ 120.50 2026-11-20',fill='black')
    b=io.BytesIO();i.save(b,'PNG');return b.getvalue()

def fake_ocr(payload):
    return {'raw_text':'FACTURA TOTAL $120.50 2026-11-20','confidence':0.75,
            'suggested_fields':{'amount_mxn':'120.50','date':'2026-11-20','reference':None,'vendor':None},
            'engine':'tesseract-local','review_required':True}

def test_subscription_state_and_trial(ctx):
    a=request(ctx,'/subscriptions/me').json();b=request(ctx,'/subscriptions/me',who='foreign').json()
    assert a['plan']=='starter' and a['limits']['messaging']==0 and b['plan']=='starter'
    assert request(ctx,'/subscriptions/start-trial','POST',who='operator').status_code==403
    trial=request(ctx,'/subscriptions/start-trial','POST');assert trial.status_code==200,trial.text
    assert trial.json()['plan']=='trial' and trial.json()['limits']['ocr']==10
    assert request(ctx,'/subscriptions/start-trial','POST').status_code==409
    assert request(ctx,'/subscriptions/me',who='foreign').json()['plan']=='starter'
    o=order(ctx);assert o['status']=='draft'  # existing RF-008 stays available
    with ctx['factory']() as db:
        s=db.get(Subscription,ctx['ids']['a']);s.trial_ends_at=datetime.now(timezone.utc)-timedelta(days=1);db.commit()
    assert request(ctx,'/subscriptions/me').json()['plan']=='starter'

def test_ocr_review_no_order_or_invoice_created(ctx,monkeypatch):
    monkeypatch.setattr(ocr,'recognize',fake_ocr)
    with ctx['factory']() as db:
        before=db.scalar(select(func.count()).select_from(Order))
    sent=ctx['client'].post(ROOT+'/documents/ocr/proposals',headers=ctx['auth']['owner'],
        files={'file':('factura.png',photo(),'image/png')})
    assert sent.status_code==201,sent.text
    data=sent.json();assert data['status']=='proposed' and data['extracted']['confidence']==0.75
    assert data['reviewed'] is None
    assert request(ctx,'/documents/ocr/proposals',who='foreign').json()==[]
    assert request(ctx,'/documents/ocr/proposals/'+data['id']+'/review','POST',{'vendor':'Proveedor X','amount_mxn':'120.50','concept':'Compra','confirm':True},who='operator').status_code==403
    assert request(ctx,'/documents/ocr/proposals/'+data['id']+'/review','POST',{'confirm':False}).status_code==422
    reviewed=request(ctx,'/documents/ocr/proposals/'+data['id']+'/review','POST',{'vendor':'Proveedor X','amount_mxn':'120.50','concept':'Compra','confirm':True})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['reviewed']['vendor']=='Proveedor X'
    assert request(ctx,'/documents/ocr/proposals/'+data['id']+'/review','POST',{'vendor':'Again','confirm':True}).status_code==409
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(Order))==before
        assert db.scalar(select(func.count()).select_from(OcrProposal))==1

def test_ocr_invalid_image_and_quota(ctx,monkeypatch):
    monkeypatch.setattr(ocr,'recognize',fake_ocr)
    assert ctx['client'].post(ROOT+'/documents/ocr/proposals',headers=ctx['auth']['owner'],files={
        'file':('x.txt',b'a','text/plain')}).status_code==415
    for j in range(3):
        r=ctx['client'].post(ROOT+'/documents/ocr/proposals',headers=ctx['auth']['owner'],files={'file':(f'{j}.png',photo(),'image/png')})
        assert r.status_code==201,r.text
    r=ctx['client'].post(ROOT+'/documents/ocr/proposals',headers=ctx['auth']['owner'],files={'file':('4.png',photo(),'image/png')})
    assert r.status_code==403
    assert request(ctx,'/subscriptions/me').json()['usage']['ocr']==3

def test_messaging_missing_credentials_and_consent_no_network(ctx,monkeypatch):
    monkeypatch.delenv('NEXO_WHATSAPP_TOKEN',raising=False)
    cfg=request(ctx,'/messaging/configuration','PUT',{'phone_number_id':'123456789012','enabled':True})
    assert cfg.status_code==200 and cfg.json()['credentials_present'] is False
    send={'recipient_e164':'+5215512345678','template_name':'seguimiento','consent_reference':'optin-2026-approved','confirm':False}
    assert request(ctx,'/messaging/send-template','POST',send).status_code==422
    send['confirm']=True
    assert request(ctx,'/messaging/send-template','POST',send).status_code==409
    assert request(ctx,'/messaging/configuration',who='foreign').json()['configured'] is False
    assert request(ctx,'/messaging/configuration',who='operator').status_code==403
    with ctx['factory']() as db:assert db.scalar(select(func.count()).select_from(MessagingEvent))==0

def test_templates_versions_and_order_not_modified(ctx):
    o=order(ctx)
    first=request(ctx,'/sector-templates/apply','POST',{'code':'textile','confirm':False});assert first.status_code==422
    first=request(ctx,'/sector-templates/apply','POST',{'code':'textile','confirm':True});assert first.status_code==200
    assert first.json()['version']==1
    again=request(ctx,'/sector-templates/apply','POST',{'code':'textile','confirm':True});assert again.json()['version']==1
    second=request(ctx,'/sector-templates/apply','POST',{'code':'printing','confirm':True});assert second.json()['version']==2
    assert request(ctx,'/sector-templates/history').json()[0]['code']=='printing'
    assert request(ctx,'/sector-templates/history').json()[1]['config']['name']=='Confección y textiles'
    assert request(ctx,'/sector-templates/active',who='foreign').json()['code'] is None
    assert request(ctx,'/sector-templates/apply','POST',{'code':'printing','confirm':True},who='operator').status_code==403
    with ctx['factory']() as db:
        row=db.get(Order,UUID(o['id']));assert row.raw_text=='Pedido RF-013' and row.review_revision==0

def test_agent_plan_approval_no_side_effects(ctx):
    o=order(ctx)
    body={'agent_kind':'capacity_planner','objective':'Evaluar la carga sin modificar operaciones','order_id':o['id']}
    assert request(ctx,'/agents/prepare','POST',body,who='operator').status_code==403
    p=request(ctx,'/agents/prepare','POST',body);assert p.status_code==201,p.text
    obj=p.json();assert obj['status']=='prepared' and obj['side_effects_executed'] is False
    assert all(step['mode']=='read_only' for step in obj['result']['steps'])
    assert request(ctx,'/agents/workflows',who='foreign').json()==[]
    assert request(ctx,'/agents/workflows/'+obj['id']+'/authorize','POST',{'confirm':False}).status_code==422
    approved=request(ctx,'/agents/workflows/'+obj['id']+'/authorize','POST',{'confirm':True})
    assert approved.status_code==200 and approved.json()['status']=='authorized'
    assert approved.json()['side_effects_executed'] is False
    assert request(ctx,'/agents/workflows/'+obj['id']+'/authorize','POST',{'confirm':True}).status_code==409
    assert request(ctx,'/agents/workflows/'+obj['id']+'/authorize','POST',{'confirm':True},who='foreign').status_code==404
    with ctx['factory']() as db:
        row=db.get(Order,UUID(o['id']));assert row.status=='draft' and row.reviewed_quantity is None

def test_agent_quota_and_tool_restrictions(ctx):
    x={'agent_kind':'material_advisor','objective':'Revisar materias primas sin hacer compras'}
    assert request(ctx,'/agents/prepare','POST',{'agent_kind':'auto_purchase','objective':'Ejecutar compras automáticas'}).status_code==422
    assert request(ctx,'/agents/prepare','POST',x).status_code==201
    assert request(ctx,'/agents/prepare','POST',x).status_code==201
    assert request(ctx,'/agents/prepare','POST',x).status_code==403
    assert request(ctx,'/subscriptions/me').json()['usage']['agents']==2

def test_audit_records_p2_operations(ctx):
    request(ctx,'/subscriptions/start-trial','POST')
    request(ctx,'/sector-templates/apply','POST',{'code':'bakery','confirm':True})
    with ctx['factory']() as db:
        actions=[e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.organization_id==ctx['ids']['a'])).all()]
        assert 'subscription.trial_activated' in actions
        assert 'sector_template.applied' in actions

def test_suspended_subscription_blocks_only_new_features(ctx,monkeypatch):
    request(ctx,'/subscriptions/start-trial','POST')
    with ctx['factory']() as db:
        s=db.get(Subscription,ctx['ids']['a']);s.status='suspended';db.commit()
    s=request(ctx,'/subscriptions/me').json()
    assert s['plan']=='disabled' and s['limits']['ocr']==0
    x={'agent_kind':'capacity_planner','objective':'Solo revisar las lecturas disponibles'}
    assert request(ctx,'/agents/prepare','POST',x).status_code==403
    assert order(ctx)['status']=='draft'
    assert request(ctx,'/subscriptions/me',who='foreign').json()['plan']=='starter'

def test_invalid_image_and_ocr_engine_fail_without_persist(ctx):
    # El motor falla antes de que la cuota se contabilice o la propuesta se guarde.
    r=ctx['client'].post(ROOT+'/documents/ocr/proposals',headers=ctx['auth']['owner'],
                         files={'file':('corrupto.png',b'INVALID-IMAGE-BYTES','image/png')})
    assert r.status_code==422
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(OcrProposal))==0
    assert request(ctx,'/subscriptions/me').json()['usage']['ocr']==0

def test_messaging_blocked_for_wrong_org_even_when_server_has_credentials(ctx,monkeypatch):
    monkeypatch.setenv('NEXO_WHATSAPP_TOKEN','token-de-prueba-no-real')
    monkeypatch.setenv('NEXO_WHATSAPP_ORG_ID',str(ctx['ids']['b']))
    monkeypatch.setenv('NEXO_WHATSAPP_PHONE_ID','123456789012')
    request(ctx,'/messaging/configuration','PUT',{'phone_number_id':'123456789012','enabled':True})
    with patch('app.modules.extensions.messaging.httpx.post',side_effect=RuntimeError('NUNCA DEBE HACER RED')):
        send={'recipient_e164':'+5215512345678','template_name':'seguimiento','consent_reference':'optin-2026-approved','confirm':True}
        assert request(ctx,'/messaging/send-template','POST',send).status_code==409
        monkeypatch.setenv('NEXO_WHATSAPP_ORG_ID',str(ctx['ids']['a']))
        # Además de credenciales, el plan debe permitir envíos.
        assert request(ctx,'/messaging/send-template','POST',send).status_code==403

def test_messaging_registered_consent_revocation_and_tenant(ctx,monkeypatch):
    body={'recipient_e164':'+5215512345678','evidence_reference':'optin-authorized-2026','valid_days':45,'confirm':False}
    assert request(ctx,'/messaging/consents','POST',body).status_code==422
    body['confirm']=True
    r=request(ctx,'/messaging/consents','POST',body)
    assert r.status_code==201,r.text
    assert r.json()['recipient_tail']=='5678' and r.json()['active'] is True
    assert request(ctx,'/messaging/consents',who='foreign').json()==[]
    assert request(ctx,'/messaging/consents','POST',body).status_code==409
    assert request(ctx,'/messaging/consents/'+r.json()['id']+'/revoke','POST',{'confirm':False}).status_code==422
    rev=request(ctx,'/messaging/consents/'+r.json()['id']+'/revoke','POST',{'confirm':True})
    assert rev.status_code==200 and rev.json()['active'] is False
    assert request(ctx,'/messaging/consents/'+r.json()['id']+'/revoke','POST',{'confirm':True}).status_code==409
    assert request(ctx,'/messaging/consents/'+r.json()['id']+'/revoke','POST',{'confirm':True},who='foreign').status_code==404
