"""RF-012: prueba con PostgreSQL Neon; elimina solo sus organizaciones temporales."""
from datetime import datetime
from secrets import token_urlsafe
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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

BASE='/api/v1/orders'


def main() -> None:
    org_ids: list[UUID] = []
    password=token_urlsafe(25)
    try:
        with get_session_factory()() as db:
            org_a=Organization(name='RF012 A '+uuid4().hex[:8],sector='Pruebas',
                               timezone='America/Mexico_City',currency='MXN')
            org_b=Organization(name='RF012 B '+uuid4().hex[:8],sector='Pruebas',
                               timezone='America/Mexico_City',currency='MXN')
            db.add_all([org_a,org_b]);db.flush()
            org_ids=[org_a.id,org_b.id]
            create_first_owner(db,organization_id=org_a.id,email='owner-a-rf012@example.com',password=password)
            create_first_owner(db,organization_id=org_b.id,email='owner-b-rf012@example.com',password=password)
            db.add(User(organization_id=org_a.id,email='operator-a-rf012@example.com',
                        role='operator',password_hash=hash_password(password),is_active=True))
            db.commit()

        with TestClient(app) as client:
            def auth(org,email):
                r=client.post('/api/v1/auth/login',json={
                    'organization_id':str(org),'email':email,'password':password})
                assert r.status_code==200, f'Login HTTP {r.status_code}'
                return {'Authorization':'Bearer '+r.json()['access_token']}
            owner=auth(org_ids[0],'owner-a-rf012@example.com')
            operator=auth(org_ids[0],'operator-a-rf012@example.com')
            foreign=auth(org_ids[1],'owner-b-rf012@example.com')

            def new(headers,txt):
                r=client.post(BASE,headers=headers,json={'raw_text':txt})
                assert r.status_code==201, f'Crear HTTP {r.status_code}'
                return r.json()

            a=new(operator,'50 playeras estampadas RF012')
            b=new(owner,'25 playeras bordadas RF012')
            c=new(owner,'70 tazas RF012')
            new(foreign,'50 playeras estampadas RF012')
            change=client.post(BASE+'/'+a['id']+'/status',headers=operator,
                               json={'expected_status':'draft','to_status':'pending'})
            assert change.status_code==200, f'Cambio estado HTTP {change.status_code}'
            today=datetime.now(ZoneInfo('America/Mexico_City')).date().isoformat()
            data=client.get(BASE+'/search',headers=owner,params={
                'status':'pending','q':'playeras','date_from':today,'date_to':today,
                'limit':5,'offset':0})
            assert data.status_code==200, f'Busqueda HTTP {data.status_code}: {data.text[:200]}'
            assert data.json()['total']==1 and data.json()['items'][0]['id']==a['id']
            data=client.get(BASE+'/search',headers=owner,params={'limit':2,'offset':0})
            assert data.status_code==200 and data.json()['total']==3
            assert len(data.json()['items'])==2 and data.json()['has_more']
            assert data.json()['next_offset']==2
            data2=client.get(BASE+'/search',headers=owner,params={'limit':2,'offset':2})
            assert data2.status_code==200 and len(data2.json()['items'])==1
            assert set(x['id'] for x in data.json()['items']).isdisjoint(
                x['id'] for x in data2.json()['items'])
            limited=client.get(BASE+'/search',headers=operator,params={'only_mine':True})
            assert limited.status_code==200 and limited.json()['total']==1
            foreign_view=client.get(BASE+'/search',headers=foreign)
            assert foreign_view.status_code==200 and foreign_view.json()['total']==1
            assert all(x['organization_id']==str(org_ids[1]) for x in foreign_view.json()['items'])
            assert client.get(BASE+'/search').status_code==401
            assert client.get(BASE+'/search',headers=owner,params={'date_from':'2026-11-18',
                                                                   'date_to':'2026-11-17'}).status_code==422
            assert client.get(BASE+'/search',headers=owner,params={'status':'hack'}).status_code==422
            assert client.get(BASE+'/search',headers=owner,params={'q':'%'}).json()['total']==0
            with get_session_factory()() as db:
                orders=list(db.scalars(select(Order).where(Order.organization_id==org_ids[0])).all())
                assert len(orders)==3
                assert sum(o.status=='pending' for o in orders)==1
            assert client.post('/api/v1/auth/logout',headers=operator).status_code==200
            assert client.get(BASE+'/search',headers=operator).status_code==401
    finally:
        if org_ids:
            with get_session_factory()() as db:
                try:
                    # Aislamiento: borrar exclusivamente UUID creados en esta ejecucion.
                    db.execute(delete(OrderStatusEvent).where(OrderStatusEvent.organization_id.in_(org_ids)))
                    db.execute(delete(Order).where(Order.organization_id.in_(org_ids)))
                    db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
    print('RF-012 PostgreSQL OK: filtros estado/fecha/texto, paginacion, total, '
          'solo mis pedidos, aislamiento, 401/422, revocacion y limpieza verificados.')

if __name__=='__main__': main()
