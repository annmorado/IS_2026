"""Entitlements P2; no restringen productos/pedidos/cotizaciones existentes.

Planes comerciales aún sin pasarela de pago; 'trial' es sandbox y no otorga mensajería.
"""
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.extensions.model import Subscription,FeatureUsage

PLANS={'starter':{'ocr':3,'agents':2,'messaging':0},'trial':{'ocr':10,'agents':10,'messaging':0},
       'growth':{'ocr':100,'agents':100,'messaging':20}}

def current(db:Session,org_id,lock=False):
    stmt=select(Subscription).where(Subscription.organization_id==org_id)
    if lock:stmt=stmt.with_for_update()
    sub=db.scalar(stmt)
    if sub is None:
        sub=Subscription(organization_id=org_id,plan_code='starter',status='active')
        db.add(sub);db.flush()
    return sub

def effective_plan(sub):
    if sub.status=='trial':
        end=sub.trial_ends_at
        if end is None or (end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end)<=datetime.now(timezone.utc):
            return 'starter'
        return 'trial'
    return sub.plan_code if sub.status=='active' else 'disabled'

def usage(db,org_id,feature,period=None):
    period=period or datetime.now(timezone.utc).strftime('%Y-%m')
    return db.scalar(select(FeatureUsage).where(FeatureUsage.organization_id==org_id,FeatureUsage.feature==feature,FeatureUsage.period==period))

def snapshot(db,org_id):
    sub=current(db,org_id);plan=effective_plan(sub);limits=PLANS.get(plan,{'ocr':0,'agents':0,'messaging':0})
    return {'plan':plan,'stored_plan':sub.plan_code,'status':sub.status,'trial_ends_at':sub.trial_ends_at,
            'trial_available':not sub.trial_consumed,'limits':limits,
            'usage':{k:(usage(db,org_id,k).used if usage(db,org_id,k) else 0) for k in limits},
            'notice':'Planes demostrativos sin cobros ni pasarela. Pedidos y cotizaciones existentes nunca se bloquean.'}

def consume(db,org_id,feature):
    sub=current(db,org_id,lock=True)
    limit=PLANS.get(effective_plan(sub),{}).get(feature,0)
    row=usage(db,org_id,feature)
    consumed=row.used if row else 0
    if consumed>=limit:
        raise HTTPException(status_code=403,detail=f'Funcionalidad {feature} no incluida o límite mensual alcanzado ({consumed}/{limit})')
    if row is None:
        row=FeatureUsage(organization_id=org_id,feature=feature,period=datetime.now(timezone.utc).strftime('%Y-%m'),used=0)
        db.add(row);db.flush()
    row.used+=1
