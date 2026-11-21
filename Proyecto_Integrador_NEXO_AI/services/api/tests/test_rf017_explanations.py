"""RF-017: faltantes, alternativas y ausencia de efectos productivos."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.modules.scenarios.explanations import explain_scenario
from app.modules.scenarios.schemas import CapacitySimulation, MaterialSimulation
from app.modules.orders.model import Order
from app.modules.products.model import Product
from app.modules.materials.model import Material
from app.modules.capacity.model import ProductionResource
from test_rf016_scenarios import ctx, post, order, product, stock_recipe, resource, START, END


def cap(qty='100.000', available='60.000', daily='10.000', delivery=date(2026, 12, 6)):
    return CapacitySimulation(
        resource_id=uuid4(),name='Linea 1',unit='pieza',start_date=date(2026,12,1),
        delivery_date=delivery,daily_capacity=Decimal(daily),workable_days=6,
        blacked_out_days=0,available_capacity=Decimal(available),
        shortage=max(Decimal('0'), Decimal(qty)-Decimal(available)),
        feasible_without_commitments=Decimal(qty)<=Decimal(available),
    )


def mat(required='20.000', available='5.000', per_unit='2.000', name='Acero'):
    return MaterialSimulation(
        material_id=uuid4(),name=name,unit='kg',
        quantity_per_unit=Decimal(per_unit),required=Decimal(required),
        available=Decimal(available),
        shortage=max(Decimal('0'),Decimal(required)-Decimal(available)),
    )


def run(qty='100.000', capacity=None, materials=(), recipe_configured=False, workdays=None, blackouts=(), date_=date(2026,12,6), compatible=True):
    return explain_scenario(quantity=Decimal(qty),delivery_date=date_,capacity=capacity,
        materials=list(materials),recipe_configured=recipe_configured,
        resource_workdays=set(range(7)) if workdays is None else set(workdays),
        resource_blackouts=set(blackouts),resource_unit_compatible=compatible)


def test_rf017_capacity_shortage_and_calculated_alternative():
    result=run(capacity=cap())
    assert result.status=='blocked'
    c=next(x for x in result.constraints if x.code=='capacity_insufficient')
    assert c.shortage==Decimal('40.000') and c.missing_product_units==Decimal('40.000')
    alt=result.alternative
    assert alt.units_possible_by_known_limits==Decimal('60.000')
    assert alt.units_to_reschedule==Decimal('40.000')
    assert alt.extra_workable_days_for_capacity==4
    assert alt.estimated_delivery_date_by_capacity==date(2026,12,10)
    assert 'no descuenta' in result.caveat.lower()


def test_capacity_date_skips_nonworkdays_and_blackouts():
    # Current is domingo. 1 available extra Monday, Tuesday blackout, next Wednesday.
    result=run(qty='8.000',capacity=cap(qty='8.000',available='6.000',daily='1.000'),
        workdays={0,1,2,3,4},blackouts={date(2026,12,8)})
    assert result.alternative.estimated_delivery_date_by_capacity==date(2026,12,9)
    assert result.alternative.extra_workable_days_for_capacity==2


def test_stock_shortage_and_product_units_without_resource():
    x=mat()
    result=run(qty='10.000',materials=[x],recipe_configured=True)
    assert result.status=='blocked'
    c=next(v for v in result.constraints if v.code=='material_insufficient')
    assert c.shortage==Decimal('15.000')
    assert c.missing_product_units==Decimal('7.500')
    assert result.alternative.units_possible_by_known_limits==Decimal('2.500')
    assert result.alternative.units_to_reschedule==Decimal('7.500')
    assert result.alternative.estimated_delivery_date_by_capacity is None
    assert 'reabastecer' in result.alternative.description.lower()


def test_capacity_and_materials_take_minimum_upper_bound():
    r=run(qty='10.000',capacity=cap(qty='10.000',available='7.000',daily='2.000'),
        materials=[mat(required='20.000',available='12.000')],recipe_configured=True)
    assert r.status=='blocked'
    assert len([c for c in r.constraints if c.severity=='blocking'])==2
    assert r.alternative.units_possible_by_known_limits==Decimal('6.000')
    assert r.alternative.units_to_reschedule==Decimal('4.000')
    assert r.alternative.extra_workable_days_for_capacity==2
    assert r.alternative.estimated_delivery_date_by_capacity==date(2026,12,8)


def test_no_capacity_or_recipe_must_not_claim_feasible():
    r=run(qty='3.000')
    assert r.status=='not_evaluable'
    assert r.alternative is None
    assert {c.code for c in r.constraints}=={'capacity_not_evaluated','recipe_not_configured'}


def test_materials_ok_and_capacity_unknown_is_not_evaluable():
    r=run(qty='3.000',materials=[mat(required='6.000',available='9.000')],recipe_configured=True)
    assert r.status=='not_evaluable'
    assert len(r.constraints)==1 and r.constraints[0].code=='capacity_not_evaluated'


def test_capacity_ok_and_recipe_unknown_is_not_evaluable():
    r=run(qty='3.000',capacity=cap(qty='3.000',available='6.000'))
    assert r.status=='not_evaluable'
    assert len(r.constraints)==1 and r.constraints[0].code=='recipe_not_configured'


def test_all_known_limits_sufficient():
    r=run(qty='3.000',capacity=cap(qty='3.000',available='6.000'),
        materials=[mat(required='6.000',available='12.000')],recipe_configured=True)
    assert r.status=='feasible_with_assumptions'
    assert r.constraints==[] and r.alternative is None
    assert 'promesa' in r.caveat


def test_zero_inventory_gives_zero_feasible_units():
    r=run(qty='3.000',materials=[mat(required='6.000',available='0.000')],recipe_configured=True)
    assert r.alternative.units_possible_by_known_limits==Decimal('0.000')
    assert r.alternative.units_to_reschedule==Decimal('3.000')


def test_floor_to_thousandth_prevents_overpromising():
    r=run(qty='3.000',materials=[mat(required='9.000',available='4.000',per_unit='3.000')],recipe_configured=True)
    assert r.alternative.units_possible_by_known_limits==Decimal('1.333')
    assert r.alternative.units_to_reschedule==Decimal('1.667')


def test_multiple_material_constraints_minimum():
    r=run(qty='10.000',materials=[mat(required='20.000',available='6.000'),
        mat(required='10.000',available='2.000',per_unit='1.000',name='Papel')],recipe_configured=True)
    assert r.alternative.units_possible_by_known_limits==Decimal('2.000')
    assert len([x for x in r.constraints if x.code=='material_insufficient'])==2


def test_no_possible_delivery_when_no_future_workdays():
    r=run(capacity=cap(),workdays=set())
    assert r.alternative.estimated_delivery_date_by_capacity is None
    assert r.alternative.extra_workable_days_for_capacity==4


def test_result_stable_for_same_inputs():
    kwargs={'qty':'100.000','capacity':cap(),'materials':[], 'recipe_configured':False}
    assert run(**kwargs)==run(**kwargs)


def test_rf017_api_exposes_explanations_and_keeps_data_unchanged(ctx):
    o,p=order(ctx),product(ctx)
    m=stock_recipe(ctx,p,available='12.000')
    r=resource(ctx,daily='1.000')
    with ctx['factory']() as db:
        before=(db.get(Order,__import__('uuid').UUID(o['id'])).status,
                db.get(Material,__import__('uuid').UUID(m['id'])).quantity_available,
                db.get(Product,__import__('uuid').UUID(p['id'])).price_mxn)
    response=post(ctx,o,p,quantity='8.000',resource_id=r['id'],resource_daily_capacity='1.000',unit_price_mxn='40.00')
    assert response.status_code==200,response.text
    body=response.json();expl=body['explanation']
    assert expl['status']=='blocked'
    assert {x['code'] for x in expl['constraints']}=={'capacity_insufficient','material_insufficient'}
    assert expl['alternative']['units_possible_by_known_limits']=='6.000'
    assert expl['alternative']['units_to_reschedule']=='2.000'
    assert expl['alternative']['extra_workable_days_for_capacity']==1
    assert expl['alternative']['estimated_delivery_date_by_capacity']==(END+timedelta(days=1)).isoformat()
    assert body['hypothetical'] and not body['persisted'] and not body['changes_applied']
    with ctx['factory']() as db:
        after=(db.get(Order,__import__('uuid').UUID(o['id'])).status,
               db.get(Material,__import__('uuid').UUID(m['id'])).quantity_available,
               db.get(Product,__import__('uuid').UUID(p['id'])).price_mxn)
    assert before==after
    assert post(ctx,o,p,who='operator').status_code==403
    assert post(ctx,o,p,who='foreign').status_code==404
    assert post(ctx,o,p).json()['explanation']['status']=='not_evaluable'


def test_mismatched_resource_units_are_not_converted_into_product_units():
    r=run(qty='10.000',capacity=cap(qty='10.000',available='6.000'),
        materials=[mat(required='20.000',available='25.000')],recipe_configured=True,
        compatible=False)
    assert r.status=='not_evaluable'
    assert r.alternative is None
    assert [v.code for v in r.constraints]==['capacity_unit_mismatch']
    assert r.constraints[0].missing_product_units is None
