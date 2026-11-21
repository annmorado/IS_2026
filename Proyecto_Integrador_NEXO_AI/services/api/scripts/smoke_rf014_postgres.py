"""RF-014 real Neon smoke: empresas UUID temporales y limpieza referencial segura."""
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from secrets import token_urlsafe
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import delete, select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.order_status.model import OrderStatusEvent
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.products.model import Product
from app.modules.quotes.model import Quote, QuoteLine, QuoteTaxConfig
from app.modules.quote_documents.model import QuoteDocument

BASE='/api/v1/quotes'


def main():
    org_ids: list[UUID]=[]
    password=token_urlsafe(28)
    try:
        with get_session_factory()() as db:
            a=Organization(name='RF014 Empresa A '+uuid4().hex[:8],sector='Pruebas',
                timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('10.00'))
            b=Organization(name='RF014 Empresa B '+uuid4().hex[:8],sector='Pruebas',
                timezone='America/Mexico_City',currency='MXN')
            db.add_all([a,b]); db.flush()
            org_ids=[a.id,b.id]
            create_first_owner(db,organization_id=a.id,email='rf014-owner-a@example.com',password=password)
            create_first_owner(db,organization_id=b.id,email='rf014-owner-b@example.com',password=password)
            db.add(User(organization_id=a.id,email='rf014-operator@example.com',
                password_hash=hash_password(password),role='operator',is_active=True))
            db.commit()

        with TestClient(app) as c:
            def login(org,email):
                r=c.post('/api/v1/auth/login',json={'organization_id':str(org),'email':email,'password':password})
                assert r.status_code==200,r.text[:300]
                return {'Authorization':'Bearer '+r.json()['access_token']}
            owner=login(org_ids[0],'rf014-owner-a@example.com')
            operator=login(org_ids[0],'rf014-operator@example.com')
            foreign=login(org_ids[1],'rf014-owner-b@example.com')
            order=c.post('/api/v1/orders',headers=operator,json={'raw_text':'3 piezas cotizacion PDF RF014'})
            assert order.status_code==201,order.text[:300]
            product=c.post('/api/v1/products',headers=owner,json={
                'sku':'RF014-'+uuid4().hex[:8], 'name':'Articulo prueba RF014',
                'unit':'pieza','cost_mxn':'9.25','price_mxn':'25.50',
                'base_production_minutes':'1.00'})
            assert product.status_code==201,product.text[:300]
            assert c.put(BASE+'/tax-config',headers=owner,json={'tax_percent':'16.00'}).status_code==200
            quote=c.post(BASE,headers=owner,json={'order_id':order.json()['id'],
                'discount_percent':'10.00', 'items':[{'product_id':product.json()['id'],'quantity':'3.000'}]})
            assert quote.status_code==201,quote.text[:300]
            qid=quote.json()['id']
            path=BASE+'/'+qid
            expiry=(datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=30)).isoformat()
            assert c.get(path+'/pdf',headers=operator).status_code==404
            assert c.post(path+'/document',headers=operator,json={'valid_until':expiry}).status_code==409
            assert c.post(path+'/approve',headers=operator).status_code==403
            approved=c.post(path+'/approve',headers=owner)
            assert approved.status_code==200,approved.text[:300]
            assert approved.json()['total']=='79.87'
            assert c.post(path+'/document',headers=foreign,json={'valid_until':expiry}).status_code==404
            assert c.get(path+'/pdf',headers=foreign).status_code==404
            emitted=c.post(path+'/document',headers=operator,json={'valid_until':expiry})
            assert emitted.status_code==201,emitted.text[:300]
            doc=emitted.json()
            assert doc['folio'] and doc['valid_until']==expiry
            assert c.post(path+'/document',headers=operator,
                json={'valid_until':expiry}).json()['id']==doc['id']
            assert c.post(path+'/document',headers=operator,
                json={'valid_until':(datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=31)).isoformat()}).status_code==409
            document=c.get(path+'/pdf',headers=operator)
            assert document.status_code==200 and document.content[:5]==b'%PDF-'
            assert sha256(document.content).hexdigest()==doc['sha256']
            assert len(document.content)==doc['size_bytes']
            reader=PdfReader(BytesIO(document.content))
            text=' '.join(page.extract_text() or '' for page in reader.pages)
            for expected in ['RF014 Empresa A',doc['folio'],'RF014','79.87','76.50','11.02',expiry,'CFDI']:
                assert expected in text,expected
            assert '9.25' not in text
            assert c.get(path+'/document',headers=owner).json()['folio']==doc['folio']
            assert c.get(path+'/pdf',headers=foreign).status_code==404
            assert c.get(path+'/pdf').status_code==401
            assert c.post('/api/v1/auth/logout',headers=operator).status_code==200
            assert c.get(path+'/pdf',headers=operator).status_code==401
            with get_session_factory()() as db:
                obj=db.scalar(select(QuoteDocument).where(QuoteDocument.id==UUID(doc['id']),
                    QuoteDocument.organization_id==org_ids[0]))
                assert obj and bytes(obj.pdf_bytes)==document.content
    finally:
        if org_ids:
            # Solo se eliminan las dos organizaciones creadas EN ESTA ejecucion.
            with get_session_factory()() as db:
                try:
                    db.execute(delete(QuoteDocument).where(QuoteDocument.organization_id.in_(org_ids)))
                    db.execute(delete(QuoteLine).where(QuoteLine.organization_id.in_(org_ids)))
                    db.execute(delete(Quote).where(Quote.organization_id.in_(org_ids)))
                    db.execute(delete(QuoteTaxConfig).where(QuoteTaxConfig.organization_id.in_(org_ids)))
                    db.execute(delete(OrderStatusEvent).where(OrderStatusEvent.organization_id.in_(org_ids)))
                    db.execute(delete(Order).where(Order.organization_id.in_(org_ids)))
                    db.execute(delete(Product).where(Product.organization_id.in_(org_ids)))
                    db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
                    db.commit()
                except Exception:
                    db.rollback();raise
    print('RF-014 PostgreSQL OK: PDF, folio, vigencia, partidas, totales, '\
          'version, 401/403/404/409, tenants, revocacion y limpieza verificados.')

if __name__=='__main__':main()
