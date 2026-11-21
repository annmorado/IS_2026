"""RF-016: simulacion sin escrituras, proteccion por tenant y precision."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func

from test_quotes import ctx, order, product
from app.modules.orders.model import Order
from app.modules.products.model import Product
from app.modules.materials.model import Material, ProductMaterial
from app.modules.capacity.model import ProductionResource, ResourceBlackout

BASE = '/api/v1/simulations/evaluate'
TODAY = date.today()
START = TODAY + timedelta(days=7)
END = START + timedelta(days=6)


def post(ctx, o, p, *, who='owner', **updates):
    body = {'order_id':o['id'], 'product_id':p['id'], 'quantity':'3.000',
            'start_date':START.isoformat(), 'delivery_date':END.isoformat()}
    body.update(updates)
    return ctx['client'].post(BASE, headers=ctx['auth'][who], json=body)


def resource(ctx, daily='2.000'):
    result=ctx['client'].post('/api/v1/capacity/resources',headers=ctx['auth']['owner'],json={
        'code':'R-'+uuid4().hex[:8], 'name':'Taller 1','unit':'pieza',
        'daily_capacity':daily, 'workdays':[0,1,2,3,4,5,6]})
    assert result.status_code == 201, result.text
    return result.json()


def stock_recipe(ctx, p, available='5.000', units='2.000'):
    response=ctx['client'].post('/api/v1/materials',headers=ctx['auth']['owner'],json={
        'sku':'M-'+uuid4().hex[:8],'name':'Materia prima','unit':'kg'})
    assert response.status_code == 201,response.text
    m=response.json()
    r=ctx['client'].put('/api/v1/materials/'+m['id']+'/stock',headers=ctx['auth']['owner'],json={
        'quantity_available':available})
    assert r.status_code == 200,r.text
    r=ctx['client'].put('/api/v1/products/'+p['id']+'/recipe/'+m['id'],headers=ctx['auth']['owner'],json={
        'quantity_per_unit':units})
    assert r.status_code == 200,r.text
    return m


def test_hypothetical_changes_without_productive_writes(ctx):
    o,p=order(ctx),product(ctx)
    m=stock_recipe(ctx,p,available='12.000')
    r=resource(ctx)
    with ctx['factory']() as db:
        before={
            'order':(db.get(Order,UUID(o['id'])).status, db.get(Order,UUID(o['id'])).reviewed_quantity),
            'product':db.get(Product,UUID(p['id'])).price_mxn,
            'material':db.get(Material,UUID(m['id'])).quantity_available,
            'capacity':db.get(ProductionResource,UUID(r['id'])).daily_capacity,
            'orders':db.scalar(select(func.count()).select_from(Order)),
        }
    response=post(ctx,o,p,quantity='8.000',unit_price_mxn='40.00',resource_id=r['id'],resource_daily_capacity='1.000')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['hypothetical'] is True and data['persisted'] is False and data['changes_applied'] is False
    assert data['original'] is None and data['simulated']['quantity']=='8.000'
    assert data['simulated']['revenue_mxn']=='320.00'
    assert data['simulated']['direct_cost_mxn']=='74.00'
    assert data['simulated']['estimated_gross_margin_mxn']=='246.00'
    assert data['materials'][0]['required']=='16.000' and data['materials'][0]['shortage']=='4.000'
    assert data['capacity']['daily_capacity']=='1.000'
    with ctx['factory']() as db:
        after={
            'order':(db.get(Order,UUID(o['id'])).status, db.get(Order,UUID(o['id'])).reviewed_quantity),
            'product':db.get(Product,UUID(p['id'])).price_mxn,
            'material':db.get(Material,UUID(m['id'])).quantity_available,
            'capacity':db.get(ProductionResource,UUID(r['id'])).daily_capacity,
            'orders':db.scalar(select(func.count()).select_from(Order)),
        }
    assert before==after


def test_capacity_takes_blackouts_and_workdays(ctx):
    o,p=order(ctx),product(ctx)
    r=resource(ctx,daily='1.000')
    blocked=START+timedelta(days=2)
    response=ctx['client'].put('/api/v1/capacity/resources/'+r['id']+'/blackouts/'+blocked.isoformat(),headers=ctx['auth']['owner'])
    assert response.status_code==200,response.text
    result=post(ctx,o,p,resource_id=r['id'],quantity='7.000').json()
    assert result['capacity']['workable_days']==6
    assert result['capacity']['blacked_out_days']==1
    assert result['capacity']['available_capacity']=='6.000'
    assert result['capacity']['shortage']=='1.000'
    assert result['capacity']['feasible_without_commitments'] is False
    assert result['capacity']['includes_existing_commitments'] is False


def test_baseline_vs_simulated_difference(ctx):
    o,p=order(ctx),product(ctx)
    reviewed=ctx['client'].put('/api/v1/orders/'+o['id']+'/review',headers=ctx['auth']['owner'],json={
        'quantity':'3.000','due_date':END.isoformat(),'expected_revision':0})
    assert reviewed.status_code==200,reviewed.text
    result=post(ctx,o,p,quantity='4.000',unit_price_mxn='30.00').json()
    assert result['original_delivery_date']==END.isoformat()
    assert result['original']['quantity']=='3.000'
    assert result['original']['revenue_mxn']=='76.50'
    assert result['simulated']['quantity']=='4.000'
    assert result['simulated']['revenue_mxn']=='120.00'
    assert result['editable_fields']==['quantity','delivery_date','unit_price_mxn']


def test_no_recipe_not_mistaken_for_sufficient_inventory(ctx):
    o,p=order(ctx),product(ctx)
    result=post(ctx,o,p).json()
    assert result['recipe_configured'] is False
    assert result['inventory_feasible_if_recipe_configured'] is None
    assert result['materials']==[]


def test_recipe_sufficient(ctx):
    o,p=order(ctx),product(ctx)
    stock_recipe(ctx,p,'7.000','2.000')
    result=post(ctx,o,p).json()
    assert result['recipe_configured'] is True
    assert result['inventory_feasible_if_recipe_configured'] is True
    assert result['materials'][0]['required']=='6.000'


def test_operator_forbidden(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,who='operator').status_code==403


def test_auth_required(ctx):
    o,p=order(ctx),product(ctx)
    assert ctx['client'].post(BASE,json={'order_id':o['id'],'product_id':p['id']}).status_code==401


def test_foreign_order_is_invisible(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,who='foreign').status_code==404


def test_foreign_product_is_invisible(ctx):
    o,p=order(ctx),product(ctx)
    foreign_product=product(ctx,who='foreign')
    assert post(ctx,o,foreign_product).status_code==404


def test_foreign_resource_is_invisible(ctx):
    o,p=order(ctx),product(ctx)
    foreign_id=uuid4()
    with ctx['factory']() as db:
        db.add(ProductionResource(organization_id=ctx['ids']['b'],code='FOREIGN',name='Other',unit='pieza',
                                  daily_capacity=Decimal('20.000'),workdays_csv='0,1,2,3,4,5,6',id=foreign_id))
        db.commit()
    assert post(ctx,o,p,resource_id=str(foreign_id)).status_code==404


@pytest.mark.parametrize('field,value',[
    ('quantity','0'),('quantity','-1'),('quantity','NaN'),('quantity','1.0009'),
    ('resource_daily_capacity','0'),('unit_price_mxn','-0.01'),('unit_price_mxn','Infinity'),
    ('unit_price_mxn','1.001'),('bogus','yes')
])
def test_invalid_fields_422(ctx,field,value):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,**{field:value}).status_code==422


def test_capacity_override_requires_resource(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,resource_daily_capacity='5.000').status_code==422


def test_dates_rejected_reversed(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,start_date=END.isoformat(),delivery_date=START.isoformat()).status_code==422


def test_dates_rejected_range_over_year(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,delivery_date=(START+timedelta(days=366)).isoformat()).status_code==422


def test_quantity_missing_requires_explicit_override(ctx):
    o,p=order(ctx),product(ctx)
    response=ctx['client'].post(BASE,headers=ctx['auth']['owner'],json={
        'order_id':o['id'],'product_id':p['id'],'start_date':START.isoformat(),'delivery_date':END.isoformat()})
    assert response.status_code==409


def test_delivery_missing_requires_explicit_override(ctx):
    o,p=order(ctx),product(ctx)
    response=ctx['client'].post(BASE,headers=ctx['auth']['owner'],json={
        'order_id':o['id'],'product_id':p['id'],'start_date':START.isoformat(),'quantity':'3.000'})
    assert response.status_code==409


def test_missing_ids_return_404(ctx):
    o,p=order(ctx),product(ctx)
    assert post(ctx,o,p,order_id=str(uuid4())).status_code==404
    assert post(ctx,o,p,product_id=str(uuid4())).status_code==404


def test_repeat_does_not_accumulate_results(ctx):
    o,p=order(ctx),product(ctx)
    a=post(ctx,o,p).json()
    b=post(ctx,o,p).json()
    assert a==b
