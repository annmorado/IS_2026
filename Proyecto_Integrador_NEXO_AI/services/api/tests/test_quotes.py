"""RF-013: aprobacion, descuentos, impuestos, versionado y aislamiento."""
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.organizations.model import Organization
from app.modules.quotes.model import Quote, QuoteLine, QuoteTaxConfig

PASSWORD='RF013-Integra-Test-Valid-Pass!'
SECRET='RF013-integration-secret-'+'x'*78
HASH=hash_password(PASSWORD)
BASE='/api/v1/quotes'

@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv('NEXO_JWT_SECRET', SECRET)
    engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def foreign_keys(c,r):c.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as db:
        a=Organization(name='RF013 A',sector='Ventas',timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('10.00'))
        b=Organization(name='RF013 B',sector='Ventas',timezone='America/Mexico_City',currency='MXN',max_discount_percent=Decimal('20.00'))
        db.add_all([a,b]);db.flush()
        people={'owner':User(organization_id=a.id,email='owner@rf013.example',password_hash=HASH,role='owner'),
                'operator':User(organization_id=a.id,email='operator@rf013.example',password_hash=HASH,role='operator'),
                'foreign':User(organization_id=b.id,email='foreign@rf013.example',password_hash=HASH,role='owner')}
        db.add_all(people.values());db.flush()
        ids={'a':a.id,'b':b.id,**{k:v.id for k,v in people.items()}}
        db.commit()
    def override():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app) as c:
            auth={}
            for label,org in [('owner',ids['a']),('operator',ids['a']),('foreign',ids['b'])]:
                resp=c.post('/api/v1/auth/login',json={'organization_id':str(org),
                    'email':label+'@rf013.example','password':PASSWORD})
                assert resp.status_code==200,resp.text
                auth[label]={'Authorization':'Bearer '+resp.json()['access_token']}
            yield {'client':c,'auth':auth,'factory':factory,'ids':ids}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine);engine.dispose()


def request(ctx,path,who='owner',method='GET',json=None,params=None):
    return ctx['client'].request(method,BASE+path,headers=ctx['auth'][who],json=json,params=params)


def product(ctx,who='owner',price='25.50',cost='9.25',sku=None):
    resp=ctx['client'].post('/api/v1/products',headers=ctx['auth'][who],json={
        'sku':sku or uuid4().hex[:8], 'name':'Articulo de prueba',
        'unit':'pieza','price_mxn':price,'cost_mxn':cost,'base_production_minutes':'1.00'})
    assert resp.status_code==201,resp.text
    return resp.json()


def order(ctx,who='owner'):
    resp=ctx['client'].post('/api/v1/orders',headers=ctx['auth'][who],json={'raw_text':'Pedido RF-013'})
    assert resp.status_code==201,resp.text
    return resp.json()


def tax(ctx,rate='16.00',who='owner'):
    return request(ctx,'/tax-config',who,'PUT',{'tax_percent':rate})


def payload(o,p,q='3.000',discount='10.00'):
    return {'order_id':o['id'],'discount_percent':discount,'items':[{'product_id':p['id'],'quantity':q}]}


def create(ctx,payload,who='owner'):
    return request(ctx,'',who,'POST',payload)


def prepared(ctx,who='owner'):
    assert tax(ctx,who=who).status_code==200
    return order(ctx,who),product(ctx,who)


def test_tax_must_be_configured_explicitly(ctx):
    o,p=order(ctx),product(ctx)
    assert request(ctx,'/tax-config').json()=={'configured':False,'tax_percent':None}
    assert create(ctx,payload(o,p)).status_code==409
    assert request(ctx,'/preview',method='POST',json=payload(o,p)).status_code==409


def test_explicit_zero_tax_and_no_implicit_defaults(ctx):
    o,p=prepared(ctx)
    assert tax(ctx,'0.00').status_code==200
    r=create(ctx,payload(o,p,q='1.000',discount='0.00'))
    assert r.status_code==201,r.text
    assert r.json()['tax_percent']=='0.00'
    assert r.json()['total']=='25.50' and r.json()['tax_amount']=='0.00'


def test_decimal_calculation_subtotal_discount_tax_total_cost_margin(ctx):
    o,p=prepared(ctx)
    r=create(ctx,payload(o,p))
    assert r.status_code==201,r.text
    q=r.json()
    assert q['subtotal']=='76.50' and q['discount_amount']=='7.65'
    assert q['taxable_base']=='68.85' and q['tax_amount']=='11.02'
    assert q['total']=='79.87' and q['direct_cost']=='27.75'
    assert q['estimated_gross_margin']=='41.10'
    assert q['items'][0]['unit_price']=='25.50' and q['version']==1
    assert q['status']=='draft' and q['approved_by_user_id'] is None


def test_preview_is_read_only_and_matches_creation(ctx):
    o,p=prepared(ctx);body=payload(o,p)
    preview=request(ctx,'/preview',method='POST',json=body)
    assert preview.status_code==200,preview.text
    with ctx['factory']() as db: assert db.scalar(select(func.count()).select_from(Quote))==0
    created=create(ctx,body).json()
    assert created['total']==preview.json()['total']
    assert created['items']==preview.json()['items']


def test_multi_product_decimal_exact(ctx):
    o,p=prepared(ctx);other=product(ctx,price='0.10',cost='0.03')
    r=create(ctx,{'order_id':o['id'],'discount_percent':'0.00','items':[
        {'product_id':p['id'],'quantity':'1.000'}, {'product_id':other['id'],'quantity':'0.300'}]})
    assert r.status_code==201,r.text
    assert r.json()['subtotal']=='25.53' and r.json()['tax_amount']=='4.08'
    assert r.json()['total']=='29.61'


def test_half_up_money_rounding(ctx):
    o,p=prepared(ctx);tax(ctx,'0.00')
    p2=product(ctx,price='1.00',cost='0.50')
    r=create(ctx,payload(o,p2,q='0.005',discount='0.00'))
    assert r.status_code==201
    assert r.json()['subtotal']=='0.01'


def test_owner_can_set_tax_and_operator_cannot(ctx):
    assert request(ctx,'/tax-config',who='operator',method='PUT',json={'tax_percent':'16.00'}).status_code==403
    assert tax(ctx,'8.00').status_code==200
    assert request(ctx,'/tax-config',who='operator').json()['tax_percent']=='8.00'
    assert tax(ctx,'16.00').status_code==200
    assert request(ctx,'/tax-config').json()['tax_percent']=='16.00'


@pytest.mark.parametrize('rate',['-0.01','100.01','abc','NaN','Infinity','0.001',None])
def test_reject_invalid_tax_config(ctx,rate):
    assert tax(ctx,rate).status_code==422


@pytest.mark.parametrize('discount',['-1','10.01','101','0.001','abc','NaN'])
def test_invalid_or_excessive_discount(ctx,discount):
    o,p=prepared(ctx)
    expected=403 if discount=='10.01' else 422
    assert create(ctx,payload(o,p,discount=discount)).status_code==expected


def test_owner_policy_discount_controls_operators(ctx):
    o,p=prepared(ctx)
    assert create(ctx,payload(o,p,discount='10.00'),who='operator').status_code==201
    assert create(ctx,payload(o,p,discount='11.00'),who='operator').status_code==403


def test_price_override_and_tax_override_forbidden(ctx):
    o,p=prepared(ctx);b=payload(o,p)
    b['items'][0]['unit_price']='0.01'
    assert create(ctx,b).status_code==422
    b=payload(o,p);b['tax_percent']='0.00'
    assert create(ctx,b).status_code==422


def test_product_price_changes_create_new_version_not_rewrite_old(ctx):
    o,p=prepared(ctx)
    one=create(ctx,payload(o,p,discount='0.00')).json()
    assert ctx['client'].patch('/api/v1/products/'+p['id'],headers=ctx['auth']['owner'],json={
        'price_mxn':'30.00','cost_mxn':'10.00'}).status_code==200
    two=create(ctx,payload(o,p,discount='0.00')).json()
    assert one['version']==1 and two['version']==2 and one['id']!=two['id']
    assert one['subtotal']=='76.50' and two['subtotal']=='90.00'
    assert request(ctx,'/'+one['id']).json()['subtotal']=='76.50'
    assert [x['version'] for x in request(ctx,'',params={'order_id':o['id']}).json()]==[2,1]


def test_tax_changes_create_snapshots(ctx):
    o,p=prepared(ctx)
    before=create(ctx,payload(o,p)).json()
    assert tax(ctx,'0.00').status_code==200
    after=create(ctx,payload(o,p)).json()
    assert request(ctx,'/'+before['id']).json()['tax_percent']=='16.00'
    assert after['tax_percent']=='0.00' and after['version']==2


def test_approval_owner_only_and_latest_version(ctx):
    o,p=prepared(ctx)
    first=create(ctx,payload(o,p)).json()
    second=create(ctx,payload(o,p)).json()
    assert request(ctx,'/'+first['id']+'/approve',method='POST').status_code==409
    assert request(ctx,'/'+second['id']+'/approve',who='operator',method='POST').status_code==403
    approved=request(ctx,'/'+second['id']+'/approve',method='POST')
    assert approved.status_code==200,approved.text
    assert approved.json()['status']=='approved' and approved.json()['approved_at']
    assert request(ctx,'/'+second['id']+'/approve',method='POST').status_code==409
    assert request(ctx,'/'+first['id']).json()['status']=='draft'


def test_operator_can_create_draft_quotes(ctx):
    o,p=prepared(ctx)
    assert create(ctx,payload(o,p),who='operator').status_code==201


def test_quotes_do_not_change_order_status_or_inventory(ctx):
    o,p=prepared(ctx)
    quote=create(ctx,payload(o,p))
    assert quote.status_code==201
    assert request(ctx,'/'+quote.json()['id']+'/approve',method='POST').status_code==200
    still=ctx['client'].get('/api/v1/orders/'+o['id'],headers=ctx['auth']['owner']).json()
    assert still['status']=='draft' and still['review_revision']==0


def test_cross_tenant_visibility(ctx):
    o,p=prepared(ctx)
    foreign_order=order(ctx,'foreign'); foreign_prod=product(ctx,'foreign')
    assert tax(ctx,who='foreign').status_code==200
    quote=create(ctx,payload(o,p)).json()
    assert request(ctx,'/'+quote['id'],who='foreign').status_code==404
    assert request(ctx,'',who='foreign',params={'order_id':o['id']}).status_code==404
    assert create(ctx,payload(foreign_order,foreign_prod),who='owner').status_code==404
    assert create(ctx,payload(o,foreign_prod)).status_code==404
    assert request(ctx,'/'+quote['id']+'/approve',who='foreign',method='POST').status_code==404


def test_deactivated_product_not_quotable(ctx):
    o,p=prepared(ctx)
    assert ctx['client'].post('/api/v1/products/'+p['id']+'/deactivate',headers=ctx['auth']['owner']).status_code==200
    assert create(ctx,payload(o,p)).status_code==404


def test_duplicate_products_rejected(ctx):
    o,p=prepared(ctx);b=payload(o,p);b['items'].append(b['items'][0]);assert create(ctx,b).status_code==422


@pytest.mark.parametrize('qty',['0','-1','1.0001','NaN','Infinity','1234567890123','abc'])
def test_invalid_quantities(ctx,qty):
    o,p=prepared(ctx)
    assert create(ctx,payload(o,p,q=qty)).status_code==422


def test_missing_items_and_too_many(ctx):
    o,p=prepared(ctx)
    assert create(ctx,{'order_id':o['id'],'items':[]}).status_code==422
    ids=[product(ctx) for _ in range(31)]
    assert create(ctx,{'order_id':o['id'],'items':[
        {'product_id':prod['id'],'quantity':'1'} for prod in ids]}).status_code==422


def test_completed_and_cancelled_cannot_be_quoted(ctx):
    o,p=prepared(ctx)
    resp=ctx['client'].post('/api/v1/orders/'+o['id']+'/status',headers=ctx['auth']['owner'],json={
        'expected_status':'draft','to_status':'cancelled'})
    assert resp.status_code==200,resp.text
    assert create(ctx,payload(o,p)).status_code==409
    assert request(ctx,'/preview',method='POST',json=payload(o,p)).status_code==409


def test_missing_order_and_quote_return_404(ctx):
    o,p=prepared(ctx)
    assert create(ctx,{'order_id':str(uuid4()),'items':[{'product_id':p['id'],'quantity':'1'}]}).status_code==404
    assert request(ctx,'/'+str(uuid4())).status_code==404
    assert request(ctx,'/'+str(uuid4())+'/approve',method='POST').status_code==404


def test_unauthenticated_and_revoked(ctx):
    assert ctx['client'].get(BASE+'/tax-config').status_code==401
    assert ctx['client'].post(BASE,json={}).status_code==401
    auth=ctx['auth']['operator']
    assert ctx['client'].post('/api/v1/auth/logout',headers=auth).status_code==200
    assert request(ctx,'/tax-config',who='operator').status_code==401


def test_foreign_tax_config_not_exposed(ctx):
    assert tax(ctx,'16.00').status_code==200
    assert request(ctx,'/tax-config',who='foreign').json()['configured']==False


def test_invalid_order_status_not_modified_by_quote(ctx):
    o,p=prepared(ctx)
    assert create(ctx,payload(o,p)).status_code==201
    assert ctx['client'].get('/api/v1/orders/'+o['id'],headers=ctx['auth']['owner']).json()['status']=='draft'


def test_database_enforces_tenant_foreign_keys(ctx):
    o,p=prepared(ctx)
    q=create(ctx,payload(o,p)).json()
    with ctx['factory']() as db:
        line=db.scalar(select(QuoteLine).where(QuoteLine.quote_id==UUID(q['id'])))
        assert line is not None
        line.organization_id=ctx['ids']['b']
        with pytest.raises(Exception):db.commit()
        db.rollback()


def test_route_schema_includes_rf013(ctx):
    paths=ctx['client'].get('/openapi.json').json()['paths']
    assert '/api/v1/quotes' in paths
    assert '/api/v1/quotes/preview' in paths
    assert '/api/v1/quotes/tax-config' in paths
    assert '/api/v1/quotes/{quote_id}/approve' in paths


def test_quote_cannot_be_approved_after_order_cancelled(ctx):
    o,p=prepared(ctx)
    q=create(ctx,payload(o,p)).json()
    r=ctx['client'].post('/api/v1/orders/'+o['id']+'/status',headers=ctx['auth']['owner'],json={
        'expected_status':'draft','to_status':'cancelled'})
    assert r.status_code==200
    assert request(ctx,'/'+q['id']+'/approve',method='POST').status_code==409
