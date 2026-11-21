"""RIA-005: reproducible operational rule baseline (NOT a trained model).

Uses current catalog base duration, daily resource capacity, allocated units,
calendar workdays and blackouts. Resource commitments reflect a DB snapshot,
not a reservation or a contractual promise.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING
from sqlalchemy import select, func
from fastapi import HTTPException
from app.modules.products.model import Product
from app.modules.capacity.model import ProductionResource, ResourceBlackout
from app.modules.scheduling.model import ResourceAllocation

ENGINE_VERSION="baseline_rules_1.0"
FEATURE_VERSION="capacity_quantity_product_1.0"


def estimate(db, scope, *, product_id, quantity:Decimal, due_date:date|None,
             resource_id=None, start_date:date|None=None) -> dict:
    product=db.scalar(select(Product).where(Product.id==product_id,
                       Product.organization_id==scope.organization_id, Product.is_active.is_(True)))
    if product is None:raise HTTPException(404,"Producto no encontrado")
    if quantity<=0 or not quantity.is_finite() or quantity>Decimal("100000"):
        raise HTTPException(422,"Cantidad fuera del dominio del modelo base")
    start=max(start_date or date.today(),date.today())
    if due_date and (due_date-start).days>365:
        raise HTTPException(422,"Horizonte máximo: 365 días")
    base=Decimal(product.base_production_minutes)*quantity
    minutes=int(base.to_integral_value(rounding=ROUND_CEILING))
    factors=[{"name":"base_production_minutes","value":str(product.base_production_minutes),"source":"catalog_product"},
             {"name":"quantity","value":str(quantity),"source":"user_input"}]
    warnings=["Baseline de reglas, no modelo entrenado ni predicción validada."]
    quality="insufficient_operational_data"
    confidence="unvalidated"
    finish=None;resource_name=None;remaining_today=None; days_needed=None
    if resource_id:
        resource=db.scalar(select(ProductionResource).where(
            ProductionResource.id==resource_id,ProductionResource.organization_id==scope.organization_id,
            ProductionResource.is_active.is_(True)))
        if resource is None:raise HTTPException(404,"Recurso no disponible en esta organización")
        resource_name=resource.name
        factors.append({"name":"resource_daily_capacity","value":str(resource.daily_capacity),"source":"resource_catalog"})
        if resource.unit.strip().casefold()!=product.unit.strip().casefold():
            warnings.append("Unidades incompatibles entre recurso y producto; no se estimó la fecha")
        else:
            workdays=set(resource.workdays)
            block=set(db.scalars(select(ResourceBlackout.day).where(
                ResourceBlackout.organization_id==scope.organization_id,
                ResourceBlackout.resource_id==resource.id,
                ResourceBlackout.day>=start,ResourceBlackout.day<=start+timedelta(days=365))).all())
            allocations=dict(db.execute(select(ResourceAllocation.day,func.sum(ResourceAllocation.quantity)).where(
                ResourceAllocation.organization_id==scope.organization_id,
                ResourceAllocation.resource_id==resource.id,
                ResourceAllocation.day>=start,
                ResourceAllocation.day<=start+timedelta(days=365)).group_by(ResourceAllocation.day)).all())
            left=quantity
            used=0
            for days in range(366):
                day=start+timedelta(days=days)
                if day.weekday() not in workdays or day in block:continue
                remain=max(Decimal("0"),Decimal(resource.daily_capacity)-Decimal(allocations.get(day,0)))
                if day==start:remaining_today=str(remain)
                if remain==0:continue
                left-=min(left,remain);used+=1
                if left<=0:
                    finish=day;days_needed=used;break
            factors.append({"name":"committed_resource_units_in_horizon",
                            "value":str(sum(allocations.values(),Decimal("0"))),"source":"resource_allocations_snapshot"})
            if finish is not None:
                quality="rules_sufficient_inputs_unvalidated"
            else:
                warnings.append("No hay capacidad suficiente en el horizonte evaluado")
    else:
        warnings.append("Sin recurso seleccionado no es posible evaluar capacidad ni compromisos")
    risk="unknown"
    if due_date and finish:
        risk="high" if finish>due_date else "low_under_current_snapshot"
    elif due_date and due_date<start:
        risk="high"
    elif due_date:
        warnings.append("No se puede determinar riesgo con calendario incompleto")
    return {"engine_version":ENGINE_VERSION,"feature_version":FEATURE_VERSION,
            "engine_kind":"deterministic_rule_baseline_not_trained",
            "quality_status":quality,"confidence_status":confidence,
            "estimated_minutes":minutes,"estimated_completion_date":finish.isoformat() if finish else None,
            "estimated_workdays":days_needed,"requested_date":due_date.isoformat() if due_date else None,
            "delay_risk":risk,"resource_name":resource_name,"remaining_capacity_today":remaining_today,
            "factors":factors,"warnings":warnings,
            "changes_applied":False,"contractually_guaranteed":False}
