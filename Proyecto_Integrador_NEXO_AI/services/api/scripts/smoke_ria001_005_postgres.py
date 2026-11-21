"""Neon smoke using two TEMP organizations with automatic cleanup.

Requires NEXO_ALLOW_AI_SMOKE=1. Transcription engine is MOCKED in this test;
real local Whisper is tested separately against a user-selected M4A file.
"""
import os
import tempfile
from secrets import token_urlsafe
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select, delete, func
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_session_factory
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.ai.model import TranscriptionJob,StructuredExtraction,FulfillmentEstimate
from app.modules.orders.model import Order

BASE='/api/v1'


def main():
    if os.environ.get('NEXO_ALLOW_AI_SMOKE')!='1':
        raise SystemExit('Activa NEXO_ALLOW_AI_SMOKE=1 tras respaldar Neon: crea 2 empresas temporales y las elimina.')
    ids=[];password=token_urlsafe(30)
    try:
        with get_session_factory()() as db:
            for label in ('a','b'):
                obj=Organization(name='RIA-001-005 TEMP '+uuid4().hex,sector='Smoke',
                     timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('0.00'))
                db.add(obj);db.flush();ids.append(obj.id)
                create_first_owner(db,organization_id=obj.id,email='ria-smoke-'+label+'@example.com',password=password)
            db.commit()
        with tempfile.TemporaryDirectory(prefix='nexo-ria-voice-') as audio_dir:
            with patch.dict(os.environ,{'NEXO_VOICE_STORAGE_DIR':audio_dir}):
                with TestClient(app) as client:
                    def req(method,path,auth=None,expected=(200,201),**kw):
                        r=client.request(method,BASE+path,headers=auth,**kw)
                        assert r.status_code in expected,(method,path,r.status_code,r.text[:350])
                        return r
                    def login(n):
                        label='a' if n==0 else 'b'
                        r=req('POST','/auth/login',json={'organization_id':str(ids[n]),
                            'email':'ria-smoke-'+label+'@example.com','password':password})
                        return {'Authorization':'Bearer '+r.json()['access_token']}
                    a,b=login(0),login(1)
                    pr=req('POST','/products',a,json={'sku':'RIA-TEST','name':'Taza RIA','unit':'pieza',
                        'price_mxn':'30.00','cost_mxn':'8.00','base_production_minutes':'2.00'}).json()
                    assert req('GET','/ai/extractions',b).json()==[]
                    raw='Necesito 2 piezas de Taza RIA precio unitario $30 para 2026-12-23; nota: azul'
                    x=req('POST','/ai/extractions',a,json={'raw_text':raw}).json()
                    assert x['result']['fields']['product']['value']['id']==pr['id']
                    assert x['result']['fields']['quantity']['value']=='2'
                    assert x['result']['fields']['requested_date']['origin']=='indicated'
                    assert req('GET','/ai/extractions',b).json()==[]
                    corrected={'product_id':pr['id'],'quantity':'2.000','unit_price_mxn':'30.00',
                       'requested_date':'2026-12-23','notes':'azul'}
                    assert req('POST','/ai/validate',a,json=corrected).json()['valid']
                    assert req('POST','/ai/validate',a,json={**corrected,'quantity':'-1'}).json()['valid'] is False
                    reviewed=req('POST','/ai/extractions/'+x['id']+'/review',a,
                                 json={**corrected,'confirm':True}).json()
                    assert reviewed['reviewed']['origin']=='human_confirmed'
                    req('GET','/ai/extractions/'+x['id'],b,expected=(404,))
                    estimate=req('POST','/ai/estimates',a,json={
                        'product_id':pr['id'],'quantity':'2.000','requested_date':'2026-12-23'}).json()
                    assert estimate['result']['engine_version']=='baseline_rules_1.0'
                    assert estimate['result']['quality_status']=='insufficient_operational_data'
                    assert req('GET','/ai/estimates',b).json()==[]
                    # M4A test fixture: signature accepted by RF009; transcription
                    # output is stubbed, not a claim that real audio was decoded.
                    fake=b'\x00\x00\x00\x14ftypM4A '+b'\x00'*16
                    v=req('POST','/voice-notes',a,files={'file':('ria.m4a',fake,'audio/mp4')},
                          data={'duration_ms':'1200'}).json()
                    with patch('app.modules.ai.speech.transcribe_m4a',return_value=(
                        'Necesito dos tazas',1200,'mock-test-only')):
                        job=req('POST','/ai/transcriptions',a,expected=(202,),json={
                            'voice_note_id':v['id']}).json()
                    state=req('GET','/ai/transcriptions/'+job['id'],a).json()
                    assert state['status']=='completed' and state['transcript']=='Necesito dos tazas'
                    req('GET','/ai/transcriptions/'+job['id'],b,expected=(404,))
                    with get_session_factory()() as db:
                        assert db.scalar(select(func.count()).select_from(StructuredExtraction).where(StructuredExtraction.organization_id==ids[0]))==1
                        assert db.scalar(select(func.count()).select_from(FulfillmentEstimate).where(FulfillmentEstimate.organization_id==ids[0]))==1
                        assert db.scalar(select(func.count()).select_from(TranscriptionJob).where(TranscriptionJob.organization_id==ids[0]))==1
                        assert db.scalar(select(func.count()).select_from(Order).where(Order.organization_id==ids[0]))==0
    finally:
        if ids:
            with get_session_factory()() as db:
                try:
                    for i in ids:db.execute(delete(Organization).where(Organization.id==i))
                    db.commit()
                except Exception:
                    db.rollback();raise
    print('RIA-001-RIA-005 PostgreSQL OK: 2 empresas temporales, trazabilidad, revisión humana, validación, baseline sin capacitación, STT simulado, aislamiento y limpieza. Modelo Whisper real se prueba aparte.')

if __name__=='__main__':main()
