"""Integration test of RF-023..027 with real Neon; UUID-scoped temporary data only.

Never deletes a preexisting organization; cleanup order respects restrictive user FKs.
"""
from datetime import datetime,timedelta
from decimal import Decimal
from secrets import token_urlsafe
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from sqlalchemy import delete,select,func
from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.order_status.model import OrderStatusEvent
from app.modules.scheduling.model import ResourceAllocation
from app.modules.purchasing.model import PurchaseRequest
from app.modules.quotes.model import Quote,QuoteLine,QuoteTaxConfig
from app.modules.quote_documents.model import QuoteDocument
from app.modules.decisions.model import DecisionRecommendation,AuditEvent
from app.modules.orders.model import Order
from app.modules.products.model import Product

ROOT='/api/v1'

def cleanup(organizations):
    with get_session_factory()() as db:
        try:
            for table in (ResourceAllocation,PurchaseRequest,OrderStatusEvent,
                          QuoteDocument,QuoteLine,Quote,QuoteTaxConfig,
                          DecisionRecommendation,Order,Product):
                db.execute(delete(table).where(table.organization_id.in_(organizations)))
            db.execute(delete(Organization).where(Organization.id.in_(organizations)))
            db.commit()
        except Exception:
            db.rollback();raise

def main():
    organizations=[]; password=token_urlsafe(36);passed=False
    try:
        with get_session_factory()() as db:
            for label in ('A','B'):
                org=Organization(name='RF023-027 TEMP '+label+' '+uuid4().hex[:10],sector='Integración',
                    timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('0.00'))
                db.add(org);db.flush();organizations.append(org.id)
                create_first_owner(db,organization_id=org.id,email='rf02327'+label.lower()+'@example.com',password=password)
            db.commit()
        with TestClient(app) as client:
            def must(method,path,h=None,expected=(200,201),**kwargs):
                r=client.request(method,ROOT+path,headers=h,**kwargs)
                assert r.status_code in expected,f'{method} {path} => {r.status_code} {r.text[:300]}'
                return r
            def login(index):
                name='a' if index==0 else 'b'
                return {'Authorization':'Bearer '+must('POST','/auth/login',json={
                   'organization_id':str(organizations[index]),'email':'rf02327'+name+'@example.com','password':password}).json()['access_token']}
            a=login(0);b=login(1)
            # RF-023: invitation valid once; restricted privileges; suspension revokes active JWT.
            invitation=must('POST','/collaborators/invitations',a,json={
                'email':'collaborator'+uuid4().hex[:8]+'@example.com','permissions':['orders.read','notifications.read']}).json()
            member=must('POST','/collaborators/invitations/accept',json={
                'token':invitation['token'],'password':password}).json()
            assert must('POST','/collaborators/invitations/accept',expected=(410,),json={
                'token':invitation['token'],'password':password}).status_code==410
            member_auth={'Authorization':'Bearer '+must('POST','/auth/login',json={
                'organization_id':str(organizations[0]),'email':member['email'],'password':password}).json()['access_token']}
            must('GET','/orders/search',member_auth)
            must('POST','/orders',member_auth,expected=(403,),json={'raw_text':'Sin permiso'})
            must('PATCH','/collaborators/users/'+member['id']+'/suspension',a,json={'is_active':False})
            must('GET','/orders/search',member_auth,expected=(401,))
            # RF-024: request approval cannot receive or modify stock.
            material=must('POST','/materials',a,json={'sku':'MAT'+uuid4().hex[:7],'name':'Material','unit':'kg'}).json()
            supplier=must('POST','/purchasing/suppliers',a,json={'code':'SUP'+uuid4().hex[:7],'name':'Proveedor prueba'}).json()
            purchase=must('POST','/purchasing/requests',a,json={'supplier_id':supplier['id'],'material_id':material['id'],
                'quantity':'5.000','unit_cost_mxn':'10.00'}).json()
            assert purchase['status']=='pending'
            approved=must('POST','/purchasing/requests/'+purchase['id']+'/decision',a,
                          json={'decision':'approve','note':'Aprobación temporal explícita'}).json()
            assert approved['status']=='approved'
            assert must('GET','/materials/'+material['id'],a).json()['quantity_available']=='0.000'
            must('GET','/purchasing/requests',b)
            must('POST','/purchasing/requests',b,expected=(404,),json={
                'supplier_id':supplier['id'],'material_id':material['id'],'quantity':'1','unit_cost_mxn':'1'})
            # RF-025: allocate to a confirmed order, reject overflow, check remaining.
            today=datetime.now(ZoneInfo('America/Mexico_City')).date()
            day=today+timedelta(days=3)
            order=must('POST','/orders',a,json={'raw_text':'RF023027 pedido de prueba'}).json()
            must('PUT','/orders/'+order['id']+'/review',a,json={'quantity':'4.000',
                 'due_date':day.isoformat(),'expected_revision':0})
            must('POST','/orders/'+order['id']+'/confirm',a,json={'expected_revision':1})
            res=must('POST','/capacity/resources',a,json={'code':'RES'+uuid4().hex[:7],
                'name':'Recurso prueba','unit':'pieza','daily_capacity':'5.000','workdays':[0,1,2,3,4,5,6]}).json()
            allocation=must('POST','/scheduling/allocations',a,json={
                'resource_id':res['id'],'order_id':order['id'],'day':day.isoformat(),'quantity':'3.000'}).json()
            calendar=must('GET','/scheduling/calendar?day='+day.isoformat(),a).json()
            assert calendar['resources'][0]['occupied']=='3.000' and calendar['resources'][0]['remaining']=='2.000'
            must('POST','/scheduling/allocations',a,expected=(409,),json={
               'resource_id':res['id'],'order_id':order['id'],'day':day.isoformat(),'quantity':'3.000'})
            assert must('GET','/scheduling/calendar?day='+day.isoformat(),b).json()['resources']==[]
            # RF-026: disabled by default, only configured alert is delivered on scan.
            assert must('POST','/notifications/scan',a).json()['created']==0
            must('PUT','/notifications/preferences',a,json={'due_soon':True,'risk':False,'material_shortage':False})
            assert must('POST','/notifications/scan',a).json()['created']==1
            assert must('POST','/notifications/scan',a).json()['created']==0
            assert [x['kind'] for x in must('GET','/notifications/entries',a).json()]==['due_soon']
            assert must('GET','/notifications/entries',b).json()==[]
            # RF-027: approved quote appears once, CSV + PDF and filters coincide.
            product=must('POST','/products',a,json={'sku':'PR'+uuid4().hex[:7],'name':'Articulo',
                'unit':'pieza','price_mxn':'25.50','cost_mxn':'9.00','base_production_minutes':'1.00'}).json()
            must('PUT','/quotes/tax-config',a,json={'tax_percent':'0.00'})
            quote=must('POST','/quotes',a,json={'order_id':order['id'],'discount_percent':'0.00',
                'items':[{'product_id':product['id'],'quantity':'2.000'}]}).json()
            must('POST','/quotes/'+quote['id']+'/approve',a)
            summary=must('GET','/reports/summary',a).json()
            assert summary['totals']['orders']==1 and summary['totals']['revenue_mxn']=='51.00'
            csv=must('GET','/reports/export?format=csv',a); pdf=must('GET','/reports/export?format=pdf',a)
            assert csv.content.startswith(b'\xef\xbb\xbf') and b'51.00' in csv.content
            assert pdf.content.startswith(b'%PDF-')
            assert must('GET','/reports/summary?status=cancelled',a).json()['totals']['orders']==0
            assert must('GET','/reports/summary',b).json()['totals']['orders']==0
            with get_session_factory()() as db:
                assert db.scalar(select(func.count()).select_from(ResourceAllocation).where(ResourceAllocation.organization_id==organizations[0]))==1
                assert db.scalar(select(func.count()).select_from(PurchaseRequest).where(PurchaseRequest.organization_id==organizations[0]))==1
                assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.organization_id==organizations[0]))>=7
        passed=True
    finally:
        if organizations:
            cleanup(organizations)
    if passed:
        print('RF-023–RF-027 PostgreSQL OK: invitaciones, suspensión, permisos, compras aprobadas, calendario ocupado/restante, alertas configurables, CSV/PDF filtrados, aislamiento multiempresa y limpieza verificados.')

if __name__=='__main__':main()
