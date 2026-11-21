"""Integración RF-028..032 contra Neon real; crea solo organizaciones desechables.
No requiere credenciales de Meta ni OCR instalado: verifica contrato y persistencia.
El reconocimiento Tesseract real se verifica por separado con una fotografía de usuario.
"""
from secrets import token_urlsafe
from uuid import uuid4
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import select,delete,func
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_session_factory
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.extensions.model import (Subscription,OcrProposal,AppliedSectorTemplate,AgentWorkflow,MessagingEvent)
from app.modules.decisions.model import AuditEvent

BASE='/api/v1'

def cleanup(ids):
    # Las organizaciones de prueba se crean en este mismo proceso. Nunca borrar IDs previos.
    with get_session_factory()() as db:
        try:
            for org_id in ids:
                db.execute(delete(Organization).where(Organization.id==org_id))
            db.commit()
        except Exception:db.rollback();raise

def main():
    ids=[];password=token_urlsafe(36);complete=False
    try:
        with get_session_factory()() as db:
            for label in ('A','B'):
                obj=Organization(name='RF028-032 TEMP '+label+' '+uuid4().hex[:10],sector='Integración',
                       timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('0.00'))
                db.add(obj);db.flush();ids.append(obj.id)
                create_first_owner(db,organization_id=obj.id,email='rf02832-'+label.lower()+'@example.com',password=password)
            db.commit()
        with TestClient(app) as client:
            def check(method,path,auth=None,expected=(200,201),**kwargs):
                r=client.request(method,BASE+path,headers=auth,**kwargs)
                assert r.status_code in expected,(method,path,r.status_code,r.text[:400])
                return r
            def login(n):
                label='a' if n==0 else 'b'
                data=check('POST','/auth/login',json={'organization_id':str(ids[n]),'email':'rf02832-'+label+'@example.com','password':password}).json()
                return {'Authorization':'Bearer '+data['access_token']}
            a,b=login(0),login(1)
            # RF-028: trial is single-use and isolated; restricted features only.
            assert check('GET','/subscriptions/me',a).json()['plan']=='starter'
            assert check('POST','/subscriptions/start-trial',a,json={}).json()['plan']=='trial'
            check('POST','/subscriptions/start-trial',a,expected=(409,),json={})
            assert check('GET','/subscriptions/me',b).json()['plan']=='starter'
            # RF-029: simulate recognized image text to test the persistence path
            # without making Neon depend on a local Tesseract executable.
            recognized={'raw_text':'Nota de prueba TOTAL 120.50','confidence':0.8,
                        'suggested_fields':{'amount_mxn':'120.50','date':None,'reference':None,'vendor':None},
                        'engine':'tesseract-local','review_required':True}
            with patch('app.modules.extensions.ocr.recognize',return_value=recognized):
                p=check('POST','/documents/ocr/proposals?document_type=receipt',a,
                    files={'file':('nota.png',b'\x89PNG\r\n\x1a\nFAKE_FOR_MOCK','image/png')}).json()
            assert p['status']=='proposed' and p['reviewed'] is None
            assert check('GET','/documents/ocr/proposals',b).json()==[]
            q=check('POST','/documents/ocr/proposals/'+p['id']+'/review',a,json={'vendor':'Proveedor de prueba','amount_mxn':'120.50','confirm':True}).json()
            assert q['status']=='reviewed' and q['reviewed']['vendor']=='Proveedor de prueba'
            # RF-030: no official org-specific creds => absolutely no sends.
            check('PUT','/messaging/configuration',a,json={'phone_number_id':'12345678901','enabled':True})
            assert check('GET','/messaging/configuration',a).json()['credentials_present'] is False
            check('POST','/messaging/send-template',a,expected=(409,),json={
                'recipient_e164':'+5215512345678','template_name':'mensaje','consent_reference':'optin-test-2026','confirm':True})
            # RF-031: versioned templates, no changes to historical orders.
            first=check('POST','/sector-templates/apply',a,json={'code':'bakery','confirm':True}).json()
            second=check('POST','/sector-templates/apply',a,json={'code':'printing','confirm':True}).json()
            assert first['version']==1 and second['version']==2
            assert check('GET','/sector-templates/active',b).json()['code'] is None
            # RF-032: explicit authorization only for plan tools, with no external side effects.
            w=check('POST','/agents/prepare',a,json={'agent_kind':'material_advisor',
                'objective':'Revisar faltantes sin aprobar compras reales'}).json()
            assert w['status']=='prepared' and w['side_effects_executed'] is False
            check('POST','/agents/workflows/'+w['id']+'/authorize',a,expected=(422,),json={'confirm':False})
            approved=check('POST','/agents/workflows/'+w['id']+'/authorize',a,json={'confirm':True}).json()
            assert approved['status']=='authorized' and approved['side_effects_executed'] is False
            assert check('GET','/agents/workflows',b).json()==[]
            with get_session_factory()() as db:
                assert db.scalar(select(func.count()).select_from(OcrProposal).where(OcrProposal.organization_id==ids[0]))==1
                assert db.scalar(select(func.count()).select_from(AgentWorkflow).where(AgentWorkflow.organization_id==ids[0]))==1
                assert db.scalar(select(func.count()).select_from(MessagingEvent).where(MessagingEvent.organization_id==ids[0]))==0
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.organization_id==ids[0]))>=5
        complete=True
    finally:
        if ids:cleanup(ids)
    if complete:
        print('RF-028-RF-032 PostgreSQL OK: planes aislados, OCR propuesto y revisado, mensajería bloqueada sin credenciales, plantillas versionadas, agentes sin efectos, auditoría y limpieza verificados. OCR de imagen real requiere Tesseract y prueba adicional.')
if __name__=='__main__':main()
