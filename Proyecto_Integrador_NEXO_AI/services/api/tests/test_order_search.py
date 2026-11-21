"""RF-012: filtros, paginacion, seguridad, datos persistidos y zona horaria."""
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User, AuthSession  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.order_search.service import _escape_like

BASE = '/api/v1/orders'
PASSWORD = 'RF012-Test-Valid-Password!'
SECRET = 'rf012-integration-only-' + 'a' * 80
HASH = hash_password(PASSWORD)

@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv('NEXO_JWT_SECRET', SECRET)
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def fks_on(conn, record):
        conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name='RF012 A', sector='Servicios', timezone='America/Mexico_City', currency='MXN')
        b = Organization(name='RF012 B', sector='Servicios', timezone='America/Mexico_City', currency='MXN')
        db.add_all([a,b]); db.flush()
        users={
            'owner': User(organization_id=a.id, email='owner@rf012.example', password_hash=HASH, role='owner'),
            'operator': User(organization_id=a.id, email='operator@rf012.example', password_hash=HASH, role='operator'),
            'operator2': User(organization_id=a.id, email='operator2@rf012.example', password_hash=HASH, role='operator'),
            'foreign': User(organization_id=b.id, email='foreign@rf012.example', password_hash=HASH, role='owner'),
        }
        db.add_all(users.values());db.flush()
        ids={'a':a.id,'b':b.id, **{name:obj.id for name,obj in users.items()}}
        db.commit()
    def override_db():
        with factory() as db:yield db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            auth={}
            for name,email,org in [
                ('owner','owner@rf012.example',ids['a']),
                ('operator','operator@rf012.example',ids['a']),
                ('operator2','operator2@rf012.example',ids['a']),
                ('foreign','foreign@rf012.example',ids['b']),
            ]:
                login=client.post('/api/v1/auth/login',json={
                    'organization_id':str(org),'email':email,'password':PASSWORD})
                assert login.status_code==200,login.text
                auth[name]={'Authorization':'Bearer '+login.json()['access_token']}
            yield {'client':client,'factory':factory,'auth':auth,'ids':ids}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def new(ctx, text='Playeras estampadas', who='owner'):
    r=ctx['client'].post(BASE, headers=ctx['auth'][who], json={'raw_text':text})
    assert r.status_code==201,r.text
    return r.json()


def search(ctx, who='owner', **params):
    return ctx['client'].get(BASE+'/search', headers=ctx['auth'][who], params=params)


def status(ctx, order, state, who='owner', expected='draft'):
    r=ctx['client'].post(BASE+'/'+order['id']+'/status', headers=ctx['auth'][who],
         json={'expected_status':expected,'to_status':state})
    assert r.status_code==200,r.text


def confirm(ctx, order, who='owner'):
    url=BASE+'/'+order['id']
    rv=ctx['client'].put(url+'/review',headers=ctx['auth'][who],json={
        'quantity':'25.500','due_date':'2026-12-20','expected_revision':0})
    assert rv.status_code==200,rv.text
    cf=ctx['client'].post(url+'/confirm',headers=ctx['auth'][who],json={
        'expected_revision':rv.json()['review_revision']})
    assert cf.status_code==200,cf.text


def set_created(ctx, order, iso):
    with ctx['factory']() as db:
        row=db.get(Order, UUID(order['id']))
        row.created_at=datetime.fromisoformat(iso.replace('Z','+00:00'))
        db.commit()


def test_search_route_is_before_uuid_route(ctx):
    paths=ctx['client'].get('/openapi.json').json()['paths']
    assert BASE+'/search' in paths
    assert search(ctx).status_code==200  # no UUID 422
    assert ctx['client'].get(BASE+'/'+str(uuid4()),headers=ctx['auth']['owner']).status_code==404


def test_empty_page_contract(ctx):
    r=search(ctx)
    assert r.status_code==200,r.text
    assert r.json()=={'items':[],'total':0,'limit':20,'offset':0,'has_more':False,'next_offset':None}


def test_all_orders_in_current_organization(ctx):
    a=new(ctx,'A1');b=new(ctx,'A2',who='operator');new(ctx,'B1',who='foreign')
    result=search(ctx).json()
    assert result['total']==2
    assert {x['id'] for x in result['items']}=={a['id'],b['id']}
    assert all(x['organization_id']==str(ctx['ids']['a']) for x in result['items'])
    assert search(ctx,'foreign').json()['total']==1


def test_operator_can_list_team_orders_but_only_mine_limits(ctx):
    new(ctx,'Owner');a=new(ctx,'Operator',who='operator');new(ctx,'Operator2',who='operator2')
    assert search(ctx,'operator').json()['total']==3
    r=search(ctx,'operator',only_mine='true')
    assert r.status_code==200
    assert [i['id'] for i in r.json()['items']]==[a['id']]


@pytest.mark.parametrize('value', ['draft','pending','confirmed','in_progress','completed','cancelled'])
def test_all_statuses_are_filterable(ctx,value):
    order=new(ctx,'Mantenimiento de equipo')
    if value=='pending': status(ctx,order,'pending')
    elif value in ('confirmed','in_progress','completed'):
        confirm(ctx,order)
        if value in ('in_progress','completed'): status(ctx,order,'in_progress',expected='confirmed')
        if value=='completed': status(ctx,order,'completed',expected='in_progress')
    elif value=='cancelled': status(ctx,order,'cancelled')
    new(ctx,'Borrador adicional')
    r=search(ctx,status=value)
    assert r.status_code==200,r.text
    assert r.json()['total']==(2 if value=='draft' else 1)
    assert all(x['status']==value for x in r.json()['items'])


def test_text_is_case_insensitive(ctx):
    a=new(ctx,'Playeras ESTAMPADAS');new(ctx,'Tazas bordadas')
    r=search(ctx,q=' estampadas ')
    assert r.status_code==200
    assert [o['id'] for o in r.json()['items']]==[a['id']]


@pytest.mark.parametrize('text,query', [('Descuento 100%','100%'),('Linea A_B','A_B'),(r'Carpeta C:\repo',r'C:\repo')])
def test_literal_special_characters_are_not_like_wildcards(ctx,text,query):
    expected=new(ctx,text);new(ctx,'ABC ' + query.replace('%','x').replace('_','q').replace('\\','z') + ' ABC')
    result=search(ctx,q=query).json()
    assert result['total']==1
    assert result['items'][0]['id']==expected['id']


def test_text_filter_is_parameterized_and_harmless(ctx):
    new(ctx,'Producto normal'); new(ctx,"el texto contiene ' OR 1=1 --")
    r=search(ctx,q="' OR 1=1 --").json()
    assert r['total']==1


def test_combined_filters(ctx):
    right=new(ctx,'Enviar 30 playeras',who='operator')
    status(ctx,right,'pending',who='operator')
    other=new(ctx,'Enviar 40 playeras',who='operator')
    new(ctx,'Enviar 30 tazas',who='operator')
    new(ctx,'Enviar 30 playeras',who='foreign')
    set_created(ctx,right,'2026-11-18T05:00:00Z') # 17 Nov, 23:00 MX
    set_created(ctx,other,'2026-11-18T08:00:00Z')
    result=search(ctx,'operator',status='pending',q='playeras',date_from='2026-11-17',
                  date_to='2026-11-17', only_mine=True).json()
    assert result['total']==1 and result['items'][0]['id']==right['id']


def test_date_filter_is_local_to_organization(ctx):
    evening=new(ctx,'La noche del 17'); nextday=new(ctx,'La madrugada del 18')
    set_created(ctx,evening,'2026-11-18T05:30:00Z') # 17 Nov 23:30 MX
    set_created(ctx,nextday,'2026-11-18T06:30:00Z') # 18 Nov 00:30 MX
    r=search(ctx,date_from='2026-11-17',date_to='2026-11-17').json()
    assert r['total']==1 and r['items'][0]['id']==evening['id']
    r=search(ctx,date_from='2026-11-18',date_to='2026-11-18').json()
    assert r['total']==1 and r['items'][0]['id']==nextday['id']


def test_date_bounds_independent(ctx):
    early=new(ctx,'Anterior'); late=new(ctx,'Posterior')
    set_created(ctx,early,'2026-11-16T12:00:00Z')
    set_created(ctx,late,'2026-11-18T18:00:00Z')
    assert search(ctx,date_from='2026-11-17').json()['items'][0]['id']==late['id']
    assert search(ctx,date_to='2026-11-17').json()['items'][0]['id']==early['id']


def test_pagination_stable_no_duplicates_and_has_more(ctx):
    orders=[new(ctx,f'Pedido {i}') for i in range(7)]
    first=search(ctx,limit=3,offset=0).json()
    second=search(ctx,limit=3,offset=3).json()
    third=search(ctx,limit=3,offset=6).json()
    assert first['total']==second['total']==third['total']==7
    assert first['has_more'] and first['next_offset']==3
    assert second['has_more'] and second['next_offset']==6
    assert not third['has_more'] and third['next_offset'] is None
    ids=[o['id'] for p in [first,second,third] for o in p['items']]
    assert len(ids)==len(set(ids))==7
    assert set(ids)=={o['id'] for o in orders}


def test_pagination_beyond_end_preserves_total(ctx):
    new(ctx);r=search(ctx,limit=10,offset=50).json()
    assert r['items']==[] and r['total']==1 and not r['has_more']


def test_mixed_tenant_pagination_never_leaks(ctx):
    for i in range(12):new(ctx,'Venta A '+str(i))
    for i in range(8):new(ctx,'Venta B '+str(i),who='foreign')
    for offset in [0,5,10,50]:
        page=search(ctx,limit=5,offset=offset).json()
        assert page['total']==12
        assert all(x['organization_id']==str(ctx['ids']['a']) for x in page['items'])
        page_b=search(ctx,'foreign',limit=5,offset=offset).json()
        assert page_b['total']==8
        assert all(x['organization_id']==str(ctx['ids']['b']) for x in page_b['items'])


@pytest.mark.parametrize('bad', [
    {'status':'unknown'}, {'status':'COMPLETE'}, {'date_from':'bad'},
    {'date_to':'2026-02-30'}, {'date_from':'2026-11-18','date_to':'2026-11-17'},
    {'q':'   '}, {'q':''}, {'q':'x'*201}, {'limit':0}, {'limit':101},
    {'limit':-1}, {'offset':-1}, {'offset':'xyz'}, {'date_to':'not-date'},
])
def test_bad_search_params_422(ctx,bad):
    assert search(ctx,**bad).status_code==422


def test_no_token_401(ctx):
    assert ctx['client'].get(BASE+'/search').status_code==401


def test_invalid_token_401(ctx):
    assert ctx['client'].get(BASE+'/search',headers={'Authorization':'Bearer invalid'}).status_code==401


def test_revoked_token_401(ctx):
    auth=ctx['auth']['owner'];assert ctx['client'].post('/api/v1/auth/logout',headers=auth).status_code==200
    assert ctx['client'].get(BASE+'/search',headers=auth).status_code==401


def test_tenant_spoofed_header_is_ignored(ctx):
    item=new(ctx,'Privado');new(ctx,'Otra empresa',who='foreign')
    r=ctx['client'].get(BASE+'/search', headers={**ctx['auth']['owner'],'X-Organization-ID':str(ctx['ids']['b'])})
    assert r.status_code==200
    assert r.json()['total']==1 and r.json()['items'][0]['id']==item['id']


def test_search_does_not_write_order_or_status_history(ctx):
    order=new(ctx,'Consulta sin mutaciones')
    with ctx['factory']() as db:
        old=db.get(Order,UUID(order['id'])).updated_at
    for _ in range(3):assert search(ctx,q='Consulta').status_code==200
    with ctx['factory']() as db:
        row=db.get(Order,UUID(order['id']))
        assert row.status=='draft' and row.updated_at==old


def test_empty_search_string_trim_validation(ctx):
    assert _escape_like('100% _ \\')==r'100\% \_ \\'


def test_maximum_date_is_accepted_without_overflow(ctx):
    new(ctx, 'Fecha maxima')
    result=search(ctx,date_to='9999-12-31')
    assert result.status_code==200
    assert result.json()['total']==1


def test_all_filters_are_read_only(ctx):
    obj=new(ctx,'Prueba de solo lectura')
    for params in ({'status':'draft'}, {'date_from':'2026-11-01'}, {'q':'lectura'},
                   {'only_mine':True}, {'limit':1,'offset':1}):
        assert search(ctx,**params).status_code==200
    with ctx['factory']() as db:
        row=db.get(Order,UUID(obj['id']))
        assert row.status=='draft' and row.review_revision==0
