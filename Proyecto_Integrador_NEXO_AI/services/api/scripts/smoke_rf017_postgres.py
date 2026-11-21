"""RF-017: explicacion de restricciones y alternativas en Neon, sin escrituras."""
from datetime import datetime, timedelta
from decimal import Decimal
from secrets import token_urlsafe
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.service import create_first_owner
from app.modules.orders.model import Order
from app.modules.products.model import Product
from app.modules.materials.model import Material, ProductMaterial
from app.modules.capacity.model import ProductionResource, ResourceBlackout
from app.modules.organizations.model import Organization

BASE='/api/v1'


def main():
    ids=[]
    password=token_urlsafe(36)
    success=False
    try:
        with get_session_factory()() as db:
            for marker in ('A','B'):
                org=Organization(name='RF017 EXPLICACIONES '+marker+' '+uuid4().hex[:10],sector='Pruebas',
                    timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('0.00'))
                db.add(org);db.flush();ids.append(org.id)
                create_first_owner(db,organization_id=org.id,email='rf017-'+marker.lower()+'@example.com',password=password)
            db.commit()
        start=datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=5)
        due=start+timedelta(days=6)
        with TestClient(app) as client:
            def login(org,mark):
                response=client.post(BASE+'/auth/login',json={
                    'organization_id':str(org),'email':'rf017-'+mark+'@example.com','password':password})
                assert response.status_code==200,response.text
                return {'Authorization':'Bearer '+response.json()['access_token']}
            owner=login(ids[0],'a');foreign=login(ids[1],'b')
            def request(method,path,headers,**kw):
                response=client.request(method,BASE+path,headers=headers,**kw)
                assert response.status_code in (200,201),f'{path}: {response.status_code} {response.text[:400]}'
                return response.json()
            order=request('POST','/orders',owner,json={'raw_text':'RF017 pedido temporal solo simulacion'})
            product=request('POST','/products',owner,json={'sku':'RF017-'+uuid4().hex[:8],
                'name':'Articulo hipotetico','unit':'pieza','price_mxn':'25.50','cost_mxn':'9.25',
                'base_production_minutes':'5.00'})
            material=request('POST','/materials',owner,json={'sku':'RF017-M-'+uuid4().hex[:7],
                'name':'Material temporal','unit':'kg'})
            request('PUT','/materials/'+material['id']+'/stock',owner,json={'quantity_available':'12.000'})
            request('PUT','/products/'+product['id']+'/recipe/'+material['id'],owner,
                    json={'quantity_per_unit':'2.000'})
            resource=request('POST','/capacity/resources',owner,json={
                'code':'RF017-R-'+uuid4().hex[:7], 'name':'Mesa temporal', 'unit':'pieza',
                'daily_capacity':'2.000', 'workdays':[0,1,2,3,4,5,6]})
            before=request('GET','/orders/'+order['id'],owner)
            body={'order_id':order['id'],'product_id':product['id'],
                'quantity':'8.000','start_date':start.isoformat(),'delivery_date':due.isoformat(),
                'unit_price_mxn':'40.00','resource_id':resource['id'],'resource_daily_capacity':'1.000'}
            scenario=request('POST','/simulations/evaluate',owner,json=body)
            assert scenario['simulated']['revenue_mxn']=='320.00'
            assert scenario['simulated']['direct_cost_mxn']=='74.00'
            assert scenario['simulated']['estimated_gross_margin_mxn']=='246.00'
            assert scenario['capacity']['available_capacity']=='7.000'
            assert scenario['capacity']['shortage']=='1.000'
            assert scenario['materials'][0]['required']=='16.000'
            assert scenario['materials'][0]['shortage']=='4.000'
            explanations=scenario['explanation']
            assert explanations['status']=='blocked'
            assert {x['code'] for x in explanations['constraints']}=={'capacity_insufficient','material_insufficient'}
            assert explanations['alternative']['units_possible_by_known_limits']=='6.000'
            assert explanations['alternative']['units_to_reschedule']=='2.000'
            assert explanations['alternative']['extra_workable_days_for_capacity']==1
            assert explanations['alternative']['estimated_delivery_date_by_capacity']==(due+timedelta(days=1)).isoformat()
            assert 'reabastecer' in explanations['alternative']['description'].lower()
            assert explanations['caveat']
            assert scenario['hypothetical'] and not scenario['persisted'] and not scenario['changes_applied']
            assert request('GET','/orders/'+order['id'],owner)==before
            assert request('GET','/products/'+product['id'],owner)['price_mxn']=='25.50'
            assert request('GET','/materials/'+material['id'],owner)['quantity_available']=='12.000'
            assert request('GET','/capacity/resources/'+resource['id'],owner)['daily_capacity']=='2.000'
            repeated=request('POST','/simulations/evaluate',owner,json=body)
            assert repeated==scenario
            # La alternativa es solo un calculo; sin recurso ni receta no debe prometer viabilidad.
            other_product=request('POST','/products',owner,json={'sku':'RF017-N-'+uuid4().hex[:8],
                'name':'Sin receta','unit':'pieza','price_mxn':'10.00','cost_mxn':'5.00',
                'base_production_minutes':'2.00'})
            unknown=request('POST','/simulations/evaluate',owner,json={
                'order_id':order['id'],'product_id':other_product['id'],'quantity':'10.000',
                'start_date':start.isoformat(),'delivery_date':due.isoformat()})
            assert unknown['explanation']['status']=='not_evaluable'
            assert unknown['explanation']['alternative'] is None
            assert client.post(BASE+'/simulations/evaluate',json=body).status_code==401
            assert client.post(BASE+'/simulations/evaluate',headers=foreign,json=body).status_code==404
            with get_session_factory()() as db:
                real_order=db.scalar(select(Order).where(Order.organization_id==ids[0]))
                assert real_order.status=='draft'
        success=True
    finally:
        # Nunca se utiliza una busqueda por nombre: solo IDs creados en esta ejecucion.
        for org_id in ids:
            with get_session_factory()() as db:
                try:
                    db.execute(delete(ResourceBlackout).where(ResourceBlackout.organization_id==org_id))
                    db.execute(delete(ProductMaterial).where(ProductMaterial.organization_id==org_id))
                    db.execute(delete(Order).where(Order.organization_id==org_id))
                    db.execute(delete(Material).where(Material.organization_id==org_id))
                    db.execute(delete(ProductionResource).where(ProductionResource.organization_id==org_id))
                    db.execute(delete(Product).where(Product.organization_id==org_id))
                    db.execute(delete(Organization).where(Organization.id==org_id))
                    db.commit()
                except Exception:
                    db.rollback();raise
    if success:
        print('RF-017 PostgreSQL OK: restricciones de capacidad y materiales, unidades faltantes, alternativa y fecha, '
              'sin escrituras productivas, tenants, 401/404 y limpieza verificados.')


if __name__=='__main__':
    main()
