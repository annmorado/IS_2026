"""RIA-008..011 feasible, read-only planning using live organization snapshot.

Units are checked, inventories are never reserved, and all quantities use Decimal.
One eight-hour shift is an *explicit simulation assumption*, not observed truth.
"""
from datetime import date,timedelta
from decimal import Decimal
from sqlalchemy import select,func
from fastapi import HTTPException
from app.modules.products.model import Product
from app.modules.materials.model import Material,ProductMaterial
from app.modules.capacity.model import ProductionResource,ResourceBlackout
from app.modules.scheduling.model import ResourceAllocation

D=Decimal

def product_resource(db,org,product_id,resource_id):
    p=db.scalar(select(Product).where(Product.id==product_id,Product.organization_id==org,Product.is_active.is_(True)))
    if p is None:raise HTTPException(404,'Producto no encontrado')
    r=db.scalar(select(ProductionResource).where(ProductionResource.id==resource_id,
       ProductionResource.organization_id==org,ProductionResource.is_active.is_(True)))
    if r is None:raise HTTPException(404,'Recurso no encontrado')
    if p.unit.strip().casefold()!=r.unit.strip().casefold():raise HTTPException(422,'Unidades de producto y recurso incompatibles')
    return p,r


def available_materials(db,org,p,quantity):
    pairs=db.execute(select(ProductMaterial,Material).join(Material,
        (Material.id==ProductMaterial.material_id)&(Material.organization_id==ProductMaterial.organization_id)).where(
        ProductMaterial.organization_id==org,ProductMaterial.product_id==p.id)).all()
    shortages=[];limits=[]
    for recipe,m in pairs:
        available=D(m.quantity_available);per=D(recipe.quantity_per_unit)
        if per<=0:raise HTTPException(500,'Receta inválida')
        permitted=available//per
        limits.append(permitted)
        missing=max(D(0),quantity*per-available)
        shortages.append({'material_id':str(m.id),'name':m.name,'required':str(quantity*per),
                          'available':str(available),'missing':str(missing)})
    # No recipe is an UNKNOWN inventory status, never interpret it as unlimited material.
    return {'status':'known' if pairs else 'unknown_no_recipe',
            'max_units':str(min(limits)) if limits else None,'items':shortages,
            'sufficient':bool(pairs) and all(D(x['missing'])==0 for x in shortages)}


def capacity_snapshot(db,org,r,start,end):
    block=set(db.scalars(select(ResourceBlackout.day).where(ResourceBlackout.organization_id==org,
       ResourceBlackout.resource_id==r.id,ResourceBlackout.day>=start,ResourceBlackout.day<=end)).all())
    allocations=dict(db.execute(select(ResourceAllocation.day,func.sum(ResourceAllocation.quantity)).where(
       ResourceAllocation.organization_id==org,ResourceAllocation.resource_id==r.id,
       ResourceAllocation.day>=start,ResourceAllocation.day<=end).group_by(ResourceAllocation.day)).all())
    return block,allocations


def simulate_schedule(db,org,product,resource,quantity,*,start,deadline,boost=D('1'),shift_minutes=480):
    if (deadline-start).days>90:raise HTTPException(422,'Horizonte máximo de simulación: 90 días')
    block,allocated=capacity_snapshot(db,org,resource,start,deadline)
    remaining=quantity;days=[];used=D(0);workdays=set(resource.workdays)
    # The resource capacity is in PRODUCT units; hours are an additional limit.
    unit_time=D(product.base_production_minutes)
    for offset in range((deadline-start).days+1):
        day=start+timedelta(days=offset)
        if day.weekday() not in workdays or day in block:continue
        daily=min(D(resource.daily_capacity)*boost,D(shift_minutes)/unit_time)
        reserved=D(allocated.get(day,0))
        free=max(D(0),daily-reserved)
        assigned=min(remaining,free)
        if assigned>0:
            remaining-=assigned;used+=assigned
            days.append({'date':day.isoformat(),'available_units':str(free),'planned_units':str(assigned),
                         'committed_units':str(reserved)})
        if remaining<=0:break
    return {'feasible_capacity':remaining<=0,'units_planned':str(used),'units_unserved':str(remaining),
            'days':days,'finish':days[-1]['date'] if remaining<=0 and days else None,
            'total_estimated_minutes':str(quantity*unit_time)}


def three_scenarios(db,org,*,product_id,resource_id,quantity,start,deadline,shift_minutes=480):
    if deadline<start:raise HTTPException(422,'Fecha de entrega anterior a la fecha de inicio')
    p,r=product_resource(db,org,product_id,resource_id)
    materials=available_materials(db,org,p,quantity)
    rows=[]
    for name,day,boost,cost_multiplier in (
      ('accept',deadline,D('1'),D('1')),
      ('move_date',deadline+timedelta(days=7),D('1'),D('1')),
      ('increase_capacity',deadline,D('1.25'),D('1.05'))):
        if (day-start).days>90:raise HTTPException(422,'Horizonte máximo de 90 días')
        # Only PLANNABLE units, capped by material availability, are submitted to
        # the resource scheduler. A non-existent recipe permits ZERO units.
        material_limit=D(materials['max_units']) if materials['max_units'] is not None else D(0)
        production_target=min(quantity,max(D(0),material_limit))
        schedule=simulate_schedule(db,org,p,r,production_target,start=start,deadline=day,boost=boost,shift_minutes=shift_minutes)
        schedule['requested_units']=str(quantity)
        schedule['units_unserved_total']=str(quantity-D(schedule['units_planned']))
        schedule['units_unserved_due_to_inventory']=str(quantity-production_target)
        # If only a part of the order is material-feasible, mark the scenario
        # infeasible even if that part fits the calendar.
        schedule['feasible_capacity']=schedule['feasible_capacity'] and production_target==quantity
        income=quantity*D(p.price_mxn);cost=quantity*D(p.cost_mxn)*cost_multiplier
        margin=(income-cost).quantize(D('.01'))
        reasons=[]
        if not materials['sufficient']:reasons.append('inventario insuficiente o receta ausente')
        if not schedule['feasible_capacity']:reasons.append('capacidad / duración / compromisos')
        rows.append({'alternative':name,'due_date':day.isoformat(),
           'feasible':materials['sufficient'] and schedule['feasible_capacity'],
           'restrictions':reasons,'estimated_gross_margin_mxn':str(margin),
           'margin_for_full_order_only':True,'estimated_gross_margin_if_feasible':str(margin) if materials['sufficient'] and schedule['feasible_capacity'] else None,
           'estimated_revenue_mxn':str(income.quantize(D('.01'))),
           'estimated_cost_mxn':str(cost.quantize(D('.01'))),
           'schedule':schedule,'capacity_multiplier':str(boost),
           'cost_multiplier':str(cost_multiplier),
           'factors':[
             {'name':'recipe_available_materials','value':materials['status'],'source':'inventory_live_snapshot'},
             {'name':'resource_calendar_and_commitments','value':str(D(r.daily_capacity)),'source':'resource_allocations_snapshot'},
             {'name':'unit_duration_minutes','value':str(p.base_production_minutes),'source':'product_catalog'},
             {'name':'price_and_cost_mxn','value':f'{p.price_mxn}/{p.cost_mxn}','source':'product_catalog'}],
           'assumptions':['turno simulado de '+str(shift_minutes)+' minutos',
             'capacidad aumentada 25% y costo +5% solo en alternativa increase_capacity',
             'sin reservas, sin compras, sin confirmación',
             'estimación basada en foto de inventario/capacidad, no efecto causal demostrado']})
    return {'engine_kind':'deterministic_constraint_search_not_trained',
      'material_feasibility':materials,'alternatives':rows,'constraints_applied':True,
      'changes_applied':False,'recommendation_is_binding':False,
      'warnings':['La ausencia de receta hace la factibilidad material desconocida e impide declarar aceptable una alternativa.'] if materials['status']=='unknown_no_recipe' else []}
