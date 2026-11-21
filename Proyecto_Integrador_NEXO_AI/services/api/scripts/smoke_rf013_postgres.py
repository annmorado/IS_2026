"""RF-013: smoke real en Neon, sin imprimir secretos ni tocar registros existentes."""
from decimal import Decimal
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
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

BASE='/api/v1/quotes'


def main() -> None:
    org_ids: list[UUID]=[]
    password=token_urlsafe(25)
    try:
        with get_session_factory()() as db:
            org_a=Organization(name='RF013 A '+uuid4().hex[:8],sector='Pruebas',
                timezone='America/Mexico_City',currency='MXN', max_discount_percent=Decimal('10.00'))
            org_b=Organization(name='RF013 B '+uuid4().hex[:8],sector='Pruebas',
                timezone='America/Mexico_City',currency='MXN')
            db.add_all([org_a,org_b]);db.flush()
            org_ids=[org_a.id,org_b.id]
            create_first_owner(db,organization_id=org_a.id,email='rf013-owner-a@example.com',password=password)
            create_first_owner(db,organization_id=org_b.id,email='rf013-owner-b@example.com',password=password)
            db.add(User(organization_id=org_a.id,email='rf013-operator-a@example.com',
                        password_hash=hash_password(password),role='operator',is_active=True))
            db.commit()

        with TestClient(app) as c:
            def login(org,email):
                r=c.post('/api/v1/auth/login',json={'organization_id':str(org),'email':email,'password':password})
                assert r.status_code==200,f'Login HTTP {r.status_code}'
                return {'Authorization':'Bearer '+r.json()['access_token']}
            owner=login(org_ids[0],'rf013-owner-a@example.com')
            operator=login(org_ids[0],'rf013-operator-a@example.com')
            foreign=login(org_ids[1],'rf013-owner-b@example.com')
            order_resp=c.post('/api/v1/orders',headers=operator,json={'raw_text':'3 piezas cotizacion RF013'})
            assert order_resp.status_code==201,order_resp.text[:300]
            order=order_resp.json()
            p=c.post('/api/v1/products',headers=owner,json={
                'sku':'RF013-'+uuid4().hex[:8],'name':'Articulo RF013','unit':'pieza',
                'cost_mxn':'9.25','price_mxn':'25.50','base_production_minutes':'1.00'})
            assert p.status_code==201,p.text[:300]
            product=p.json()
            payload={'order_id':order['id'],'discount_percent':'10.00',
                     'items':[{'product_id':product['id'],'quantity':'3.000'}]}
            assert c.post(BASE,headers=owner,json=payload).status_code==409
            assert c.put(BASE+'/tax-config',headers=operator,json={'tax_percent':'16.00'}).status_code==403
            conf=c.put(BASE+'/tax-config',headers=owner,json={'tax_percent':'16.00'})
            assert conf.status_code==200,conf.text[:200]
            previous=c.post(BASE+'/preview',headers=operator,json=payload)
            assert previous.status_code==200,previous.text[:300]
            assert previous.json()['total']=='79.87'
            initial=c.post(BASE,headers=operator,json=payload)
            assert initial.status_code==201,initial.text[:300]
            first=initial.json()
            assert first['version']==1 and first['status']=='draft'
            assert first['subtotal']=='76.50' and first['tax_amount']=='11.02'
            assert first['direct_cost']=='27.75'
            assert c.get(BASE+'/'+first['id'],headers=foreign).status_code==404
            assert c.get(BASE,headers=foreign,params={'order_id':order['id']}).status_code==404
            assert c.post(BASE+'/'+first['id']+'/approve',headers=operator).status_code==403
            assert c.post(BASE,headers=owner,json={**payload,'discount_percent':'15.00'}).status_code==403
            change=c.patch('/api/v1/products/'+product['id'],headers=owner,json={'price_mxn':'30.00'})
            assert change.status_code==200,change.text[:300]
            other=c.post(BASE,headers=owner,json=payload)
            assert other.status_code==201,other.text[:300]
            second=other.json()
            assert second['version']==2 and second['subtotal']=='90.00'
            assert c.get(BASE+'/'+first['id'],headers=owner).json()['subtotal']=='76.50'
            assert c.post(BASE+'/'+first['id']+'/approve',headers=owner).status_code==409
            approved=c.post(BASE+'/'+second['id']+'/approve',headers=owner)
            assert approved.status_code==200,approved.text[:300]
            assert approved.json()['status']=='approved' and approved.json()['approved_by_user_id']
            quotes=c.get(BASE,headers=operator,params={'order_id':order['id']})
            assert quotes.status_code==200 and [q['version'] for q in quotes.json()]==[2,1]
            assert c.get('/api/v1/orders/'+order['id'],headers=owner).json()['status']=='draft'
            assert c.get(BASE+'/tax-config').status_code==401
            assert c.post('/api/v1/auth/logout',headers=operator).status_code==200
            assert c.get(BASE,headers=operator,params={'order_id':order['id']}).status_code==401
            with get_session_factory()() as db:
                persisted=list(db.scalars(select(Quote).where(
                    Quote.organization_id==org_ids[0],Quote.order_id==UUID(order['id']))).all())
                assert len(persisted)==2
                assert any(q.status=='approved' for q in persisted)
    finally:
        if org_ids:
            # Orden explicito: primero partidas y cotizaciones, luego usuarios/organizaciones.
            # El filtrado por UUID evita eliminar pedidos o empresas reales.
            with get_session_factory()() as db:
                try:
                    db.execute(delete(QuoteLine).where(QuoteLine.organization_id.in_(org_ids)))
                    db.execute(delete(Quote).where(Quote.organization_id.in_(org_ids)))
                    db.execute(delete(QuoteTaxConfig).where(QuoteTaxConfig.organization_id.in_(org_ids)))
                    db.execute(delete(OrderStatusEvent).where(OrderStatusEvent.organization_id.in_(org_ids)))
                    db.execute(delete(Order).where(Order.organization_id.in_(org_ids)))
                    db.execute(delete(Product).where(Product.organization_id.in_(org_ids)))
                    db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
    print('RF-013 PostgreSQL OK: subtotal 76.50, descuento 7.65, impuesto 11.02, '
          'total 79.87, precios aprobados, versiones, 401/403/404, tenants y limpieza verificados.')

if __name__=='__main__':main()
