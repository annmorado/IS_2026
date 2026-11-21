"""RF-016: lectura aislada por tenant; calculos puros sin flush ni commit."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.capacity.model import ProductionResource, ResourceBlackout
from app.modules.materials.model import Material, ProductMaterial
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.products.model import Product
from app.modules.scenarios.schemas import (
    CapacitySimulation, MaterialSimulation, ScenarioInput, ScenarioResult, ScenarioTotals,
)
from app.modules.tenancy.scope import TenantScope
from app.modules.scenarios.explanations import explain_scenario

CENT = Decimal("0.01")
MILL = Decimal("0.001")
MAX_DAYS = 366


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _totals(quantity: Decimal, price: Decimal, cost: Decimal) -> ScenarioTotals:
    revenue = _money(quantity * price)
    direct_cost = _money(quantity * cost)
    return ScenarioTotals(
        quantity=quantity, unit_price_mxn=price, unit_cost_mxn=cost,
        revenue_mxn=revenue, direct_cost_mxn=direct_cost,
        estimated_gross_margin_mxn=revenue - direct_cost,
    )


def evaluate(db: Session, scope: TenantScope, payload: ScenarioInput) -> ScenarioResult:
    order = db.scalar(select(Order).where(
        Order.id == payload.order_id, Order.organization_id == scope.organization_id,
    ))
    product = db.scalar(select(Product).where(
        Product.id == payload.product_id, Product.organization_id == scope.organization_id,
    ))
    if order is None or product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Pedido o producto no encontrado en la organizacion")

    original_quantity = order.reviewed_quantity or order.suggested_quantity
    baseline_known = original_quantity is not None
    if original_quantity is None and payload.quantity is None:
        raise HTTPException(status_code=409, detail="Indica una cantidad hipotetica; el pedido aun no tiene cantidad revisada")
    if original_quantity is None:
        original_quantity = payload.quantity
    original_date = order.reviewed_due_date or order.suggested_due_date
    stored_date = original_date
    if original_date is None and payload.delivery_date is None:
        raise HTTPException(status_code=409, detail="Indica fecha de entrega hipotetica; el pedido aun no tiene fecha revisada")
    if original_date is None:
        original_date = payload.delivery_date
    qty = payload.quantity if payload.quantity is not None else original_quantity
    delivery = payload.delivery_date if payload.delivery_date is not None else original_date
    assert qty is not None and delivery is not None and original_quantity is not None

    org = db.scalar(select(Organization).where(Organization.id == scope.organization_id))
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacion no encontrada")
    try:
        tz = ZoneInfo(org.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Zona horaria de la organizacion invalida") from exc
    start = payload.start_date or datetime.now(timezone.utc).astimezone(tz).date()
    if delivery < start:
        raise HTTPException(status_code=422, detail="Fecha de entrega anterior a la fecha de inicio simulada")
    if (delivery - start).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail="La simulacion permite hasta 366 dias")

    capacity = None
    resource_workdays: set[int] = set()
    resource_blackouts: set[date] = set()
    resource_unit_compatible = True
    if payload.resource_id is not None:
        resource = db.scalar(select(ProductionResource).where(
            ProductionResource.id == payload.resource_id,
            ProductionResource.organization_id == scope.organization_id,
        ))
        if resource is None or not resource.is_active:
            raise HTTPException(status_code=404, detail="Recurso no encontrado o inactivo")
        blocked = set(db.scalars(select(ResourceBlackout.day).where(
            ResourceBlackout.organization_id == scope.organization_id,
            ResourceBlackout.resource_id == resource.id,
            ResourceBlackout.day >= start, ResourceBlackout.day <= delivery,
        )).all())
        workdays = set(resource.workdays)
        resource_workdays = workdays
        resource_unit_compatible = resource.unit.strip().casefold() == product.unit.strip().casefold()
        resource_blackouts = blocked
        available_days = 0
        blocked_days = 0
        for i in range((delivery - start).days + 1):
            day = start + timedelta(days=i)
            if day.weekday() in workdays:
                if day in blocked:
                    blocked_days += 1
                else:
                    available_days += 1
        daily = payload.resource_daily_capacity if payload.resource_daily_capacity is not None else resource.daily_capacity
        gross = (daily * available_days).quantize(MILL, rounding=ROUND_HALF_UP)
        shortage = max(Decimal("0"), qty - gross)
        capacity = CapacitySimulation(
            resource_id=resource.id, name=resource.name, unit=resource.unit,
            start_date=start, delivery_date=delivery,
            daily_capacity=daily, workable_days=available_days,
            blacked_out_days=blocked_days, available_capacity=gross,
            shortage=shortage, feasible_without_commitments=(shortage == 0),
        )

    recipe = db.execute(select(ProductMaterial, Material).join(
        Material, (Material.id == ProductMaterial.material_id) &
                  (Material.organization_id == ProductMaterial.organization_id),
    ).where(ProductMaterial.organization_id == scope.organization_id,
            ProductMaterial.product_id == product.id).order_by(Material.sku)).all()
    materials: list[MaterialSimulation] = []
    for ingredient, material in recipe:
        required = (qty * ingredient.quantity_per_unit).quantize(MILL, rounding=ROUND_HALF_UP)
        available = material.quantity_available if material.is_active else Decimal("0")
        materials.append(MaterialSimulation(
            material_id=material.id, name=material.name, unit=material.unit,
            quantity_per_unit=ingredient.quantity_per_unit,
            required=required, available=available,
            shortage=max(Decimal("0"), required - available),
        ))

    price = payload.unit_price_mxn if payload.unit_price_mxn is not None else product.price_mxn
    edits = [
        name for name, changed in [
            ("quantity", payload.quantity is not None),
            ("delivery_date", payload.delivery_date is not None),
            ("resource_id", payload.resource_id is not None),
            ("resource_daily_capacity", payload.resource_daily_capacity is not None),
            ("unit_price_mxn", payload.unit_price_mxn is not None),
        ] if changed
    ]
    notes = [
        "Evaluacion hipotetica: no se modifican pedidos, precios, materiales ni recursos.",
        "El margen es bruto estimado (ingreso menos costos directos), no utilidad neta.",
        "El inventario de materiales se compara con existencias registradas, sin descontar reservas de otros pedidos.",
    ]
    if not baseline_known:
        notes.append("Sin cantidad previamente registrada en el pedido: no hay linea base comparable.")
    if capacity:
        notes.append("Capacidad bruta: no se descuentan pedidos ya comprometidos. No garantiza fecha contractual.")
    else:
        notes.append("No se selecciono recurso: la capacidad operativa no fue evaluada.")
    if not materials:
        notes.append("El producto no tiene receta: no es posible verificar suficiencia de materiales.")
    explanation = explain_scenario(
        quantity=qty, delivery_date=delivery, capacity=capacity,
        materials=materials, recipe_configured=bool(materials),
        resource_workdays=resource_workdays, resource_blackouts=resource_blackouts,
        resource_unit_compatible=resource_unit_compatible,
    )
    return ScenarioResult(
        order_id=order.id, product_id=product.id, delivery_date=delivery,
        original=_totals(original_quantity, product.price_mxn, product.cost_mxn) if baseline_known else None,
        original_delivery_date=stored_date,
        simulated=_totals(qty, price, product.cost_mxn),
        capacity=capacity, materials=materials,
        recipe_configured=bool(materials),
        inventory_feasible_if_recipe_configured=all(m.shortage == 0 for m in materials) if materials else None,
        editable_fields=edits, notes=notes, explanation=explanation,
    )
