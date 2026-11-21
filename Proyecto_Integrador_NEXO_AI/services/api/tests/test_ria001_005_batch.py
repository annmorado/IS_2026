"""RIA-001..005 automated acceptance: tenant, human review, real fields, audit and baseline."""
import os
from datetime import date,timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID
from sqlalchemy import select,func
from test_quotes import ctx,product,order
from app.modules.ai import speech
from app.modules.ai.model import TranscriptionJob,StructuredExtraction,FulfillmentEstimate
from app.modules.orders.model import Order
from app.modules.decisions.model import AuditEvent
from app.modules.ai.extract import extract_fields
from app.modules.ai.forecast import ENGINE_VERSION
from scripts.evaluate_ria002 import DATA,measure
import json

BASE='/api/v1'
def req(c,method,path,who='owner',body=None,**kw):
 return c['client'].request(method,BASE+'/ai'+path,headers=c['auth'][who],json=body,**kw)


def test_ria002_persistent_grounded_and_tenant(ctx):
 p=product(ctx,sku='TZA-001');text='Necesito 3 unidades de Articulo de prueba precio unitario $25.50 para 2026-12-24; nota: navideñas'
 x=req(ctx,'POST','/extractions',body={'raw_text':text});assert x.status_code==201,x.text
 r=x.json()['result'];assert r['engine_kind']=='deterministic_baseline_not_trained'
 f=r['fields'];assert f['product']['value']['id']==p['id']
 assert f['quantity']['value']=='3'
 assert f['unit_price_mxn']['value']=='25.50'
 assert f['requested_date']['value']=='2026-12-24'
 assert f['notes']['value']=='navideñas'
 for field in f.values():
  if field['origin']=='indicated':
   a,b=field['span'];assert text[a:b]==field['source_fragment']
 assert req(ctx,'GET','/extractions',who='foreign').json()==[]
 assert req(ctx,'GET','/extractions/'+x.json()['id'],who='foreign').status_code==404
 assert len(req(ctx,'GET','/extractions').json())==1


def test_ria002_unknowns_not_invented(ctx):
 x=req(ctx,'POST','/extractions',body={'raw_text':'Cotización especial sin cantidad ni precio'})
 assert x.status_code==201,x.text
 result=x.json()['result'];assert len(result['pending_fields'])==5
 assert all(v['origin']=='pending' and v['value'] is None for v in result['fields'].values())


def test_ria003_invalid_dates_negatives_and_foreign_catalog(ctx):
 p=product(ctx)
 foreign=product(ctx,'foreign')
 def check(**kw):return req(ctx,'POST','/validate',body={'product_id':p['id'],'quantity':'2','requested_date':'2026-12-10',**kw})
 assert check().json()['valid'] is True
 assert check(quantity='-4',requested_date='2026-02-30',unit_price_mxn='-1').json()['valid'] is False
 assert set(x['field'] for x in check(quantity='-4',requested_date='2026-02-30',unit_price_mxn='-1').json()['issues'])=={'quantity','unit_price_mxn','requested_date'}
 assert check(product_id=foreign['id']).json()['valid'] is False
 assert check(quantity='Infinity').json()['valid'] is False
 assert check(quantity='0.000').json()['valid'] is False
 assert check(unit_price_mxn='NaN').json()['valid'] is False
 with ctx['factory']() as db:
  assert db.scalar(select(func.count()).select_from(Order))==0


def test_ria005_resource_rule_and_no_order_side_effect(ctx):
 p=product(ctx);o=order(ctx)
 resource=ctx['client'].post(BASE+'/capacity/resources',headers=ctx['auth']['owner'],json={
  'code':'M-AI-1','name':'Mesa IA','unit':'pieza','daily_capacity':'5',
  'workdays':[0,1,2,3,4,5,6]})
 assert resource.status_code==201,resource.text
 r=resource.json();today=date.today();due=(today+timedelta(days=14)).isoformat()
 # Confirm the order through the existing human review workflow.
 reviewed=ctx['client'].put(BASE+'/orders/'+o['id']+'/review',headers=ctx['auth']['owner'],json={
  'quantity':'4.000','due_date':due,'expected_revision':0})
 assert reviewed.status_code==200,reviewed.text
 approved=ctx['client'].post(BASE+'/orders/'+o['id']+'/confirm',headers=ctx['auth']['owner'],json={'expected_revision':1})
 assert approved.status_code==200,approved.text
 # Allocate 4 units on target day: baseline uses remaining capacity.
 booking=ctx['client'].post(BASE+'/scheduling/allocations',headers=ctx['auth']['owner'],json={
  'resource_id':r['id'],'order_id':o['id'],'day':today.isoformat(),'quantity':'4.000'})
 assert booking.status_code in (200,201),booking.text
 resp=req(ctx,'POST','/estimates',body={'product_id':p['id'],'quantity':'8.000',
   'requested_date':due,'resource_id':r['id']})
 assert resp.status_code==201,resp.text
 x=resp.json()['result'];assert x['engine_version']==ENGINE_VERSION
 assert x['remaining_capacity_today']=='1.000'
 assert x['estimated_minutes']==8
 assert x['estimated_completion_date'] == (today+timedelta(days=2)).isoformat()
 assert x['quality_status']=='rules_sufficient_inputs_unvalidated'
 assert x['confidence_status']=='unvalidated' and x['contractually_guaranteed'] is False
 assert len(x['factors'])>=3
 assert req(ctx,'GET','/estimates',who='foreign').json()==[]
 assert req(ctx,'POST','/estimates',who='foreign',body={
   'product_id':p['id'],'quantity':'5.000','resource_id':r['id']}).status_code==404
 with ctx['factory']() as db:
  assert db.get(Order,UUID(o['id'])).status=='confirmed'
  assert db.scalar(select(func.count()).select_from(FulfillmentEstimate))==1


def test_ria005_missing_capacity_honest_baseline(ctx):
 p=product(ctx)
 x=req(ctx,'POST','/estimates',body={'product_id':p['id'],'quantity':'2.000'})
 assert x.status_code==201,x.text
 r=x.json()['result'];assert r['estimated_minutes']==2
 assert r['estimated_completion_date'] is None and r['delay_risk']=='unknown'
 assert r['quality_status']=='insufficient_operational_data'
 assert r['engine_kind']=='deterministic_rule_baseline_not_trained'


def test_ria001_transcription_success_review_and_isolation(ctx,monkeypatch,tmp_path):
 monkeypatch.setenv('NEXO_VOICE_STORAGE_DIR',str(tmp_path))
 fake=b'\x00\x00\x00\x14ftypM4A '+'x'.encode()*12
 uploaded=ctx['client'].post(BASE+'/voice-notes',headers=ctx['auth']['owner'],
  files={'file':('nota.m4a',fake,'audio/mp4')},data={'duration_ms':'1500'})
 assert uploaded.status_code==201,uploaded.text
 note=uploaded.json()
 monkeypatch.setattr(speech,'transcribe_m4a',lambda path:('Quiero dos tazas',1500,'faster-whisper:base'))
 resp=req(ctx,'POST','/transcriptions',body={'voice_note_id':note['id']})
 assert resp.status_code==202,resp.text
 job_id=resp.json()['id']
 x=req(ctx,'GET','/transcriptions/'+job_id).json()
 assert x['status']=='completed' and x['transcript']=='Quiero dos tazas'
 assert x['duration_ms']==1500
 assert x['reviewed_text'] is None
 assert req(ctx,'GET','/transcriptions',who='foreign').json()==[]
 assert req(ctx,'GET','/transcriptions/'+job_id,who='foreign').status_code==404
 assert req(ctx,'POST','/transcriptions',who='foreign',body={'voice_note_id':note['id']}).status_code==404
 assert req(ctx,'PATCH','/transcriptions/'+job_id+'/text',body={'text':'Quiero 2 tazas','confirm':False}).status_code==422
 edited=req(ctx,'PATCH','/transcriptions/'+job_id+'/text',body={'text':'Quiero 2 tazas','confirm':True})
 assert edited.status_code==200 and edited.json()['status']=='reviewed'
 assert edited.json()['transcript']=='Quiero dos tazas' and edited.json()['reviewed_text']=='Quiero 2 tazas'
 assert req(ctx,'POST','/transcriptions',body={'voice_note_id':note['id']}).json()['id']==job_id
 assert req(ctx,'POST','/transcriptions/'+job_id+'/cancel',body={}).status_code==409
 with ctx['factory']() as db:
  assert db.scalar(select(func.count()).select_from(TranscriptionJob))==1
  assert db.scalar(select(func.count()).select_from(Order))==0


def test_ria001_failed_engine_never_fabricates(ctx,monkeypatch,tmp_path):
 monkeypatch.setenv('NEXO_VOICE_STORAGE_DIR',str(tmp_path))
 fake=b'\x00\x00\x00\x14ftypM4A '+'x'.encode()*12
 uploaded=ctx['client'].post(BASE+'/voice-notes',headers=ctx['auth']['owner'],files={
  'file':('nota.m4a',fake,'audio/mp4')},data={'duration_ms':'1100'})
 assert uploaded.status_code==201,uploaded.text
 def fail(path):raise speech.SpeechUnavailable('no model')
 monkeypatch.setattr(speech,'transcribe_m4a',fail)
 x=req(ctx,'POST','/transcriptions',body={'voice_note_id':uploaded.json()['id']})
 assert x.status_code==202
 job=req(ctx,'GET','/transcriptions/'+x.json()['id']).json()
 assert job['status']=='failed' and job['error_code']=='engine_unavailable'
 assert job['transcript'] is None
 assert req(ctx,'PATCH','/transcriptions/'+job['id']+'/text',body={'text':'inventado','confirm':True}).status_code==409
 monkeypatch.setattr(speech,'transcribe_m4a',lambda path:('Texto después de instalar',1100,'faster-whisper:base'))
 retry=req(ctx,'POST','/transcriptions/'+job['id']+'/retry',body={})
 assert retry.status_code==202 and retry.json()['attempt_count']==2
 completed=req(ctx,'GET','/transcriptions/'+job['id']).json()
 assert completed['status']=='completed' and completed['transcript']=='Texto después de instalar'
 assert req(ctx,'POST','/transcriptions/'+job['id']+'/retry',body={}).status_code==409


def test_ria001_reject_long_audio(ctx,monkeypatch,tmp_path):
 monkeypatch.setenv('NEXO_VOICE_STORAGE_DIR',str(tmp_path))
 fake=b'\x00\x00\x00\x14ftypM4A '+'x'.encode()*12
 u=ctx['client'].post(BASE+'/voice-notes',headers=ctx['auth']['owner'],files={'file':('a.m4a',fake,'audio/mp4')},data={'duration_ms':'61000'})
 assert u.status_code==201
 assert req(ctx,'POST','/transcriptions',body={'voice_note_id':u.json()['id']}).status_code==422


def test_ria002_synthetic_labelled_50_dataset():
 rows=[json.loads(s) for s in DATA.read_text(encoding='utf8').splitlines() if s.strip()]
 assert len(rows)==50 and all('text' in x and 'labels' in x for x in rows)
 metrics=measure(rows)
 assert set(metrics)=={'product','quantity','unit_price_mxn','requested_date','notes'}
 for k,v in metrics.items():assert v['tp']+v['fn']>=10 and 0<=v['f1']<=1


def test_ria_audit_leaves_no_order(ctx):
 p=product(ctx)
 req(ctx,'POST','/extractions',body={'raw_text':'Pedido de 3 Tazas'})
 req(ctx,'POST','/estimates',body={'product_id':p['id'],'quantity':'1.000'})
 with ctx['factory']() as db:
  events=[x.action for x in db.scalars(select(AuditEvent).where(AuditEvent.organization_id==ctx['ids']['a'])).all()]
  assert 'ai.extraction_proposed' in events and 'ai.baseline_estimate_created' in events
  assert db.scalar(select(func.count()).select_from(Order))==0


def test_ria004_human_review_is_immutable_and_not_an_order(ctx):
 p=product(ctx)
 original='Necesito 2 unidades de Articulo de prueba para 2026-12-20'
 x=req(ctx,'POST','/extractions',body={'raw_text':original}).json()
 original_fragment=x['result']['fields']['quantity']['source_fragment']
 corrected={'product_id':p['id'],'quantity':'3','requested_date':'2026-12-23',
            'unit_price_mxn':'100.00','notes':'Corregido por la persona','confirm':True}
 assert req(ctx,'POST','/extractions/'+x['id']+'/review',body={**corrected,'confirm':False}).status_code==422
 invalid=req(ctx,'POST','/extractions/'+x['id']+'/review',body={**corrected,'requested_date':'2026-02-30'})
 assert invalid.status_code==422
 foreign=req(ctx,'POST','/extractions/'+x['id']+'/review',who='foreign',body=corrected)
 assert foreign.status_code==404
 reviewed=req(ctx,'POST','/extractions/'+x['id']+'/review',body=corrected)
 assert reviewed.status_code==200,reviewed.text
 x2=reviewed.json()
 assert x2['result']['fields']['quantity']['source_fragment']==original_fragment
 assert x2['reviewed']['origin']=='human_confirmed'
 assert x2['reviewed']['fields']['quantity']=='3'
 assert x2['reviewed']['order_confirmed'] is False
 assert req(ctx,'POST','/extractions/'+x['id']+'/review',body=corrected).status_code==409
 with ctx['factory']() as db:
  assert db.scalar(select(func.count()).select_from(Order))==0


def test_ria_permissions_for_restricted_operator(ctx):
 import json
 from app.modules.auth.model import User
 with ctx['factory']() as db:
  u=db.get(User,ctx['ids']['operator'])
  u.permissions_json=json.dumps(['orders.read'])
  db.commit()
 assert req(ctx,'GET','/extractions',who='operator').status_code==403
 assert req(ctx,'POST','/extractions',who='operator',body={'raw_text':'Necesito algo'}).status_code==403
 with ctx['factory']() as db:
  u=db.get(User,ctx['ids']['operator'])
  u.permissions_json=json.dumps(['ai.read','ai.write'])
  db.commit()
 assert req(ctx,'GET','/extractions',who='operator').status_code==200
 assert req(ctx,'POST','/extractions',who='operator',body={'raw_text':'Necesito algo'}).status_code==201


def test_ria_cancel_queued_prevents_future_transcript(ctx,tmp_path,monkeypatch):
 from uuid import uuid4
 from app.modules.ai.router import process_transcription
 from app.modules.ai.model import TranscriptionJob
 monkeypatch.setenv('NEXO_VOICE_STORAGE_DIR',str(tmp_path))
 fake=b'\x00\x00\x00\x14ftypM4A '+b'\x00'*20
 uploaded=ctx['client'].post(BASE+'/voice-notes',headers=ctx['auth']['owner'],files={
   'file':('cancel.m4a',fake,'audio/mp4')},data={'duration_ms':'1000'})
 assert uploaded.status_code==201,uploaded.text
 note=uploaded.json()
 jid=uuid4()
 with ctx['factory']() as db:
  db.add(TranscriptionJob(id=jid,organization_id=ctx['ids']['a'],actor_id=ctx['ids']['owner'],
                          voice_note_id=UUID(note['id']),status='queued'))
  db.commit()
 x=req(ctx,'POST','/transcriptions/'+str(jid)+'/cancel',body={})
 assert x.status_code==200 and x.json()['status']=='cancelled'
 with ctx['factory']() as db:
  process_transcription(db.get_bind(),jid)
 assert req(ctx,'GET','/transcriptions/'+str(jid)).json()['transcript'] is None
