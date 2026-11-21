"""RIA-018 reproducible Monte Carlo digital twin. Simulated uncertainty only.

The selected supplier must belong to the tenant; no purchasing is performed.
Observed probabilities are not inferred from customer data.
"""
from datetime import date,timedelta
from decimal import Decimal
from math import ceil
from random import Random
from statistics import mean
from uuid import UUID
from sqlalchemy import select
from fastapi import HTTPException
from app.modules.purchasing.model import Supplier
from app.modules.ai_ops.planning import product_resource,available_materials,simulate_schedule,capacity_snapshot


def percentile(sorted_values,q):
    idx=(len(sorted_values)-1)*q
    i=int(idx);f=idx-i
    return round(sorted_values[i]*(1-f)+sorted_values[min(i+1,len(sorted_values)-1)]*f,3)


def monte_carlo(db,org,*,product_id,resource_id,quantity,starting_date:date,
                shifts:int,interruption_probability:float,supplier_id:UUID|None,
                supplier_delay_days:int,seed:int,runs:int):
    p,r=product_resource(db,org,product_id,resource_id)
    if supplier_id:
        supplier=db.scalar(select(Supplier).where(Supplier.id==supplier_id,Supplier.organization_id==org))
        if not supplier:raise HTTPException(404,'Proveedor no encontrado')
    materials=available_materials(db,org,p,quantity)
    horizon=starting_date+timedelta(days=89)
    baseline=simulate_schedule(db,org,p,r,quantity,start=starting_date,deadline=horizon)
    rng=Random(seed);samples=[]
    blackout,committed=capacity_snapshot(db,org,r,starting_date,horizon)
    # Simple stochastic shift-capacity model (not a calibrated operational twin).
    # 1 run = one independent daily schedule with downtime Bernoulli and
    # +/-10% capacity perturbation; no stock replenishment is assumed.
    for _ in range(runs):
        remaining=float(quantity)
        lead=rng.randint(0,supplier_delay_days) if supplier_id else 0
        current=starting_date+timedelta(days=lead)
        working=0
        while (current-starting_date).days<90 and remaining>0:
            if current.weekday() not in r.workdays or current in blackout:
                current+=timedelta(days=1);continue
            if rng.random()<interruption_probability:
                current+=timedelta(days=1);continue
            max_units=min(float(r.daily_capacity)*shifts,480.0*shifts/float(p.base_production_minutes))
            max_units*=rng.uniform(.9,1.1)
            max_units=max(0,max_units-float(committed.get(current,0)))
            remaining-=max_units;current+=timedelta(days=1);working+=1
        samples.append(min(90,(current-starting_date).days) if remaining<=0 else 90)
    samples.sort();q10=percentile(samples,.1);q50=percentile(samples,.5);q90=percentile(samples,.9)
    return {'engine_kind':'seeded_monte_carlo_synthetic_assumptions_not_trained',
      'seed':seed,'runs':runs,'shift_count':shifts,'interruption_probability_assumed':interruption_probability,
      'supplier_id':str(supplier_id) if supplier_id else None,'supplier_delay_max_days_assumed':supplier_delay_days if supplier_id else 0,
      'start_date':starting_date.isoformat(),'baseline_capacity_feasible':baseline['feasible_capacity'],
      'inventory_status':materials['status'],'inventory_sufficient':materials['sufficient'],
      'completion_days':{'p10':q10,'p50':q50,'p90':q90,'mean':round(mean(samples),3)},
      'truncation_horizon_days':90,'simulated_only':True,'changes_applied':False,
      'warnings':['Los percentiles son resultado de supuestos configurados; no representan probabilidad estadística calibrada.',
                  'La simulación no reserva materiales, capacidad ni envía compras.',
                  'Los compromisos y bloqueos existentes se respetan en cada trayectoria; no se añaden compras futuras de materiales.']}
