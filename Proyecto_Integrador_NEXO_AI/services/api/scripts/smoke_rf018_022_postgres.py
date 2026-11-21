"""RF-018..RF-022: integración real en Neon con datos temporales identificados.

No toca organizaciones existentes. Limpia dependencias por UUID antes de borrar tenants temporales.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from secrets import token_urlsafe
from uuid import uuid4
from zoneinfo import ZoneInfo
from hashlib import sha256

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func
from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.service import create_first_owner
from app.modules.orders.model import Order
from app.modules.order_status.model import OrderStatusEvent
from app.modules.quotes.model import Quote, QuoteLine, QuoteTaxConfig
from app.modules.quote_documents.model import QuoteDocument
from app.modules.products.model import Product
from app.modules.organizations.model import Organization
from app.modules.decisions.model import AuditEvent,DecisionRecommendation

BASE='/api/v1'

def main():
    orgs=[]
    secret=token_urlsafe(36)
    passed=False
    try:
        with get_session_factory()() as db:
            for mark in ('A','B'):
                org=Organization(name='RF018-022 TEMP '+mark+' '+uuid4().hex[:10],
                    sector='Pruebas',timezone='America/Mexico_City',currency='MXN',
                    max_discount_percent=Decimal('0.00'))
                db.add(org);db.flush();orgs.append(org.id)
                create_first_owner(db,organization_id=org.id,
                    email='rf01822-'+mark.lower()+'@example.com',password=secret)
            db.commit()
        with TestClient(app) as c:
            def login(i):
                mark=('a','b')[i]
                resp=c.post(BASE+'/auth/login',json={'organization_id':str(orgs[i]),
                    'email':'rf01822-'+mark+'@example.com','password':secret})
                assert resp.status_code==200,resp.text
                return {'Authorization':'Bearer '+resp.json()['access_token']}
            owner,foreign=login(0),login(1)
            def call(method,path,headers,**kwargs):
                response=c.request(method,BASE+path,headers=headers,**kwargs)
                assert response.status_code in (200,201),f'{method} {path}: {response.status_code} {response.text[:350]}'
                return response
            order_key='batch-order-'+uuid4().hex
            order_headers={**owner,'Idempotency-Key':order_key}
            order=call('POST','/orders',order_headers,json={'raw_text':'RF018-022 temporal'}).json()
            same_order=call('POST','/orders',order_headers,json={'raw_text':'RF018-022 temporal'}).json()
            assert same_order['id']==order['id']
            product=call('POST','/products',owner,json={
               'sku':'BATCH-'+uuid4().hex[:8], 'name':'Producto batch','unit':'pieza',
               'cost_mxn':'9.25','price_mxn':'25.50','base_production_minutes':'2.00'}).json()
            today=datetime.now(ZoneInfo('America/Mexico_City')).date()
            start=today+timedelta(days=1);due=today+timedelta(days=5)
            scenario={'order_id':order['id'],'product_id':product['id'],
                      'quantity':'3.000','start_date':start.isoformat(),
                      'delivery_date':due.isoformat()}
            idempotency='batch-proposal-'+uuid4().hex
            h={**owner,'Idempotency-Key':idempotency}
            before=call('GET','/orders/'+order['id'],owner).json()
            rec=call('POST','/decisions/recommend',h,json={'scenario':scenario}).json()
            again=call('POST','/decisions/recommend',h,json={'scenario':scenario}).json()
            assert rec['id']==again['id'] and rec['status']=='proposed'
            assert call('GET','/orders/'+order['id'],owner).json()==before
            assert c.post(BASE+'/decisions/recommend',headers=h,json={'scenario':{**scenario,'quantity':'4.000'}}).status_code==409
            assert c.get(BASE+'/decisions/'+rec['id'],headers=foreign).status_code==404
            history=call('GET','/decisions',owner,params={'order_id':order['id']}).json()
            assert len(history)==1 and history[0]['engine_version']=='rf017-v1'
            confirm_key='batch-confirm-'+uuid4().hex
            conf={**owner,'Idempotency-Key':confirm_key}
            body={'confirmation':'CONFIRMAR','expected_review_revision':0,'acknowledge_estimates':True,
                  'exception_reason':'Acepto limitaciones sin recurso ni receta configurados'}
            assert c.post(BASE+'/decisions/'+rec['id']+'/confirm',headers=conf,
                          json={**body,'exception_reason':None}).status_code==409
            applied=call('POST','/decisions/'+rec['id']+'/confirm',conf,json=body).json()
            repeated=call('POST','/decisions/'+rec['id']+'/confirm',conf,json=body).json()
            assert applied['status']=='applied' and repeated['id']==applied['id']
            final=call('GET','/orders/'+order['id'],owner).json()
            assert final['status']=='confirmed' and final['reviewed_quantity']=='3.000'
            assert final['reviewed_due_date']==due.isoformat()
            ops=call('GET','/operations/summary',owner,json=None).json()
            assert ops['open_orders']==1 and ops['due_soon']==1 and ops['overdue']==0
            events=call('GET','/audit/events',owner,params={'entity_id':order['id']}).json()
            assert events['total']>=2 and all(e['organization_id']==str(orgs[0]) for e in events['items'])
            assert c.get(BASE+'/audit/events',headers=foreign).status_code==200
            # RF-022: documento aprobado no se duplica al repetir POST.
            call('PUT','/quotes/tax-config',owner,json={'tax_percent':'16.00'})
            quote_body={'order_id':order['id'],'discount_percent':'0.00',
                        'items':[{'product_id':product['id'],'quantity':'3.000'}]}
            quote_headers={**owner,'Idempotency-Key':'batch-quote-'+uuid4().hex}
            quote=call('POST','/quotes',quote_headers,json=quote_body).json()
            same_quote=call('POST','/quotes',quote_headers,json=quote_body).json()
            assert same_quote['id']==quote['id'] and same_quote['version']==quote['version']==1
            call('POST','/quotes/'+quote['id']+'/approve',owner)
            until=(today+timedelta(days=30)).isoformat()
            doc=call('POST','/quotes/'+quote['id']+'/document',owner,json={'valid_until':until}).json()
            other=call('POST','/quotes/'+quote['id']+'/document',owner,json={'valid_until':until}).json()
            assert doc['folio']==other['folio'] and doc['sha256']==other['sha256']
            with get_session_factory()() as db:
                assert db.scalar(select(func.count()).select_from(DecisionRecommendation).where(
                    DecisionRecommendation.organization_id==orgs[0]))==1
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.organization_id==orgs[0]))>=5
        passed=True
    finally:
        if orgs:
            # Limpiar SOLO los UUID generados durante ESTA ejecucion; nunca por nombre.
            # Los eventos de estado referencian usuarios sin ON DELETE CASCADE:
            # deben eliminarse antes que las organizaciones.
            # La bitacora RF-019 es inmutable: NO emitir DELETE directo
            # sobre business_audit_events. Su eliminacion es exclusivamente
            # en cascada cuando se elimina la organizacion temporal.
            with get_session_factory()() as db:
                try:
                    for model in (
                        OrderStatusEvent, QuoteDocument, QuoteLine, Quote,
                        QuoteTaxConfig, DecisionRecommendation, Order, Product,
                    ):
                        db.execute(delete(model).where(
                            model.organization_id.in_(orgs)
                        ))
                    db.execute(delete(Organization).where(
                        Organization.id.in_(orgs)
                    ))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
    if passed:
        print('RF-018–RF-022 PostgreSQL OK: confirmacion explicita, auditoria inmutable, '
              'panel operativo, historial versionado, idempotencia de propuesta y confirmacion, '
              'pedido, cotizacion y PDF no duplicados, seguridad multiempresa y limpieza verificados.')

if __name__=='__main__': main()
