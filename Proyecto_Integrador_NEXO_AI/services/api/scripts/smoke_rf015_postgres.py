"""RF-015 en Neon: móvil escribe, web consulta; limpieza solo del tenant temporal."""
from datetime import datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.service import create_first_owner
from app.modules.order_status.model import OrderStatusEvent
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.products.model import Product
from app.modules.quotes.model import Quote,QuoteLine,QuoteTaxConfig
from app.modules.quote_documents.model import QuoteDocument

BASE='/api/v1'

def main():
    org_id=None
    password=token_urlsafe(32)
    try:
        with get_session_factory()() as db:
            org=Organization(name='RF015 Sincronizacion '+uuid4().hex[:9],sector='Pruebas',
                timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('10.00'))
            db.add(org);db.flush();org_id=org.id
            create_first_owner(db,organization_id=org.id,email='rf015-owner@example.com',password=password)
            db.commit()
        with TestClient(app) as c:
            def login():
                r=c.post(BASE+'/auth/login',json={'organization_id':str(org_id),'email':'rf015-owner@example.com','password':password})
                assert r.status_code==200,r.text[:400]
                return {'Authorization':'Bearer '+r.json()['access_token']}
            mobile=login();web=login()
            assert mobile!=web
            def call(method,path,headers,**kw):
                r=c.request(method,BASE+path,headers=headers,**kw)
                assert r.status_code in (200,201),f'{method} {path}: {r.status_code} {r.text[:300]}'
                return r
            order=call('POST','/orders',mobile,json={'raw_text':'RF015 sincronia pedido iPhone'}).json()
            assert call('GET','/orders/search',web,params={'q':'sincronia pedido iPhone'}).json()['items'][0]['id']==order['id']
            assert call('GET','/orders/'+order['id'],web).json()['raw_text']==order['raw_text']
            call('PATCH','/orders/'+order['id'],mobile,json={'raw_text':'RF015 actualizado desde móvil'})
            assert call('GET','/orders/'+order['id'],web).json()['raw_text']=='RF015 actualizado desde móvil'
            assert call('GET','/orders/search',web,params={'q':'actualizado desde'}).json()['total']==1
            prod=call('POST','/products',mobile,json={'sku':'RF015-'+uuid4().hex[:8],
                'name':'Articulo RF015','unit':'pieza','cost_mxn':'9.25','price_mxn':'25.50',
                'base_production_minutes':'1.00'}).json()
            call('PUT','/quotes/tax-config',mobile,json={'tax_percent':'16.00'})
            quote=call('POST','/quotes',mobile,json={'order_id':order['id'],'discount_percent':'0.00',
                'items':[{'product_id':prod['id'],'quantity':'3.000'}]}).json()
            assert quote['total']=='88.74'
            call('POST','/quotes/'+quote['id']+'/approve',mobile)
            until=(datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=20)).isoformat()
            doc=call('POST','/quotes/'+quote['id']+'/document',mobile,json={'valid_until':until}).json()
            qlist=call('GET','/quotes',web,params={'order_id':order['id']}).json()
            assert len(qlist)==1 and qlist[0]['id']==quote['id'] and qlist[0]['status']=='approved'
            assert call('GET','/quotes/'+quote['id']+'/document',web).json()['folio']==doc['folio']
            pdf=call('GET','/quotes/'+quote['id']+'/pdf',web)
            assert pdf.content.startswith(b'%PDF-') and sha256(pdf.content).hexdigest()==doc['sha256']
            assert c.get(BASE+'/orders/search').status_code==401
            assert call('POST','/auth/logout',web).status_code==200
            assert c.get(BASE+'/quotes/'+quote['id'],headers=web).status_code==401
            assert call('GET','/quotes/'+quote['id'],mobile).json()['id']==quote['id']
            with get_session_factory()() as db:
                assert db.scalar(select(func.count()).select_from(Order).where(Order.organization_id==org_id))==1
                assert db.scalar(select(func.count()).select_from(Quote).where(Quote.organization_id==org_id))==1
    finally:
        if org_id is not None:
            # Se elimina exclusivamente la organizacion creada por esta prueba.
            with get_session_factory()() as db:
                try:
                    db.execute(delete(QuoteDocument).where(QuoteDocument.organization_id==org_id))
                    db.execute(delete(QuoteLine).where(QuoteLine.organization_id==org_id))
                    db.execute(delete(Quote).where(Quote.organization_id==org_id))
                    db.execute(delete(QuoteTaxConfig).where(QuoteTaxConfig.organization_id==org_id))
                    db.execute(delete(OrderStatusEvent).where(OrderStatusEvent.organization_id==org_id))
                    db.execute(delete(Order).where(Order.organization_id==org_id))
                    db.execute(delete(Product).where(Product.organization_id==org_id))
                    db.execute(delete(Organization).where(Organization.id==org_id))
                    db.commit()
                except Exception:
                    db.rollback();raise
    print('RF-015 PostgreSQL OK: pedido movil visible web, edicion reflejada, '
          'cotizacion aprobada, version, PDF, sesiones independientes, '
          'revocacion, integridad, sin duplicacion y limpieza verificados.')

if __name__=='__main__':main()
