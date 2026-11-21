"""RF-017: restricciones y alternativas matematicamente calculadas; sin mutaciones.

Los limites son aproximaciones: la capacidad bruta no descuenta otros pedidos y las
existencias registradas no descuentan reservas. No constituyen un compromiso.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN

from app.modules.scenarios.schemas import (
    CapacitySimulation, ConstraintExplanation, MaterialSimulation,
    ScenarioAlternative, ScenarioExplanation,
)

THOUSANDTH = Decimal('0.001')
ZERO = Decimal('0')


def _units(stock: Decimal, per_unit: Decimal, requested: Decimal) -> Decimal:
    """Cantidad producida, redondeada hacia abajo a 0.001 para no sobreprometer."""
    if per_unit <= 0 or stock <= 0:
        return ZERO
    return min(requested, (stock / per_unit).quantize(THOUSANDTH, rounding=ROUND_DOWN))


def _delivery_after_capacity(
    current: date, *, daily: Decimal, available_capacity: Decimal,
    demand: Decimal, workdays: set[int], blackout_days: set[date], max_extra_days: int = 366,
) -> date | None:
    """Primera fecha futura que cubre la demanda por capacidad BRUTA calendario."""
    if not workdays or daily <= 0:
        return None
    capacity = available_capacity
    for i in range(1, max_extra_days + 1):
        d = current + timedelta(days=i)
        if d.weekday() in workdays and d not in blackout_days:
            capacity += daily
            if capacity >= demand:
                return d
    return None


def explain_scenario(
    *, quantity: Decimal, delivery_date: date, capacity: CapacitySimulation | None,
    materials: list[MaterialSimulation], recipe_configured: bool,
    resource_workdays: set[int] | None = None,
    resource_blackouts: set[date] | None = None,
    resource_unit_compatible: bool = True,
) -> ScenarioExplanation:
    constraints: list[ConstraintExplanation] = []
    limiting_qty = quantity
    capacity_limited = False
    material_limited = False

    if capacity is None:
        constraints.append(ConstraintExplanation(
            code='capacity_not_evaluated', kind='capacity', severity='unknown',
            title='Capacidad sin evaluar',
            explanation='Selecciona un recurso productivo para calcular unidades disponibles y faltantes.',
            shortage= None, unit=None, missing_product_units=None,
        ))
    elif not resource_unit_compatible:
        constraints.append(ConstraintExplanation(
            code='capacity_unit_mismatch', kind='capacity', severity='unknown',
            title='Unidades de capacidad no comparables',
            explanation=(f'El recurso se mide en {capacity.unit}. Configura un recurso en la '
                         'misma unidad que el producto, o establece una conversion validada '
                         'antes de calcular unidades faltantes.'),
            shortage=None, unit=None, missing_product_units=None,
        ))
    elif capacity.shortage > ZERO:
        capacity_limited = True
        limiting_qty = min(limiting_qty, capacity.available_capacity)
        constraints.append(ConstraintExplanation(
            code='capacity_insufficient', kind='capacity', severity='blocking',
            title='Capacidad insuficiente',
            explanation=(
                f'La capacidad bruta del recurso {capacity.name} es '
                f'{capacity.available_capacity} {capacity.unit} para el periodo; '
                f'se solicitan {quantity} unidades de producto. '
                'La cifra no descuenta compromisos existentes.'
            ), shortage=capacity.shortage, unit=capacity.unit,
            missing_product_units=capacity.shortage,
        ))

    if not recipe_configured:
        constraints.append(ConstraintExplanation(
            code='recipe_not_configured', kind='materials', severity='unknown',
            title='Inventario sin evaluar',
            explanation='No existe receta para el producto. No se puede asegurar que los materiales alcancen.',
            shortage=None, unit=None, missing_product_units=None,
        ))
    else:
        for m in materials:
            if m.shortage > ZERO:
                material_limited = True
                possible = _units(m.available, m.quantity_per_unit, quantity)
                limiting_qty = min(limiting_qty, possible)
                constraints.append(ConstraintExplanation(
                    code='material_insufficient', kind='materials', severity='blocking',
                    title=f'Material insuficiente: {m.name}',
                    explanation=(
                        f'Se requieren {m.required} {m.unit} y hay {m.available} {m.unit} disponibles. '
                        f'Faltan {m.shortage} {m.unit} para la cantidad simulada.'
                    ), shortage=m.shortage, unit=m.unit,
                    missing_product_units=quantity - possible,
                    material_id=m.material_id,
                ))

    blocked = capacity_limited or material_limited
    if blocked:
        max_units = max(ZERO, limiting_qty.quantize(THOUSANDTH, rounding=ROUND_DOWN))
        missing = quantity - max_units
        extra_workdays = None
        suggested_date = None
        if capacity_limited and capacity is not None:
            extra_workdays = int((capacity.shortage / capacity.daily_capacity).to_integral_value(rounding=ROUND_CEILING))
            suggested_date = _delivery_after_capacity(
                delivery_date, daily=capacity.daily_capacity,
                available_capacity=capacity.available_capacity, demand=quantity,
                workdays=resource_workdays or set(), blackout_days=resource_blackouts or set(),
            )
        note = (
            f'Alternativa calculada: limitar a {max_units} unidades para {delivery_date.isoformat()} '
            f'y reprogramar {missing} unidades. '
        )
        if capacity_limited and suggested_date:
            note += f'Con la misma capacidad bruta, la primera fecha estimada para {quantity} unidades es {suggested_date.isoformat()}. '
        if material_limited:
            note += 'Se requiere reabastecer los materiales indicados; cambiar la fecha por si solo no repone existencias. '
        note += 'No descuenta compromisos o reservas existentes; requiere validacion humana.'
        alternative = ScenarioAlternative(
            units_possible_by_known_limits=max_units,
            units_to_reschedule=missing,
            requested_delivery_date=delivery_date,
            extra_workable_days_for_capacity=extra_workdays,
            estimated_delivery_date_by_capacity=suggested_date,
            description=note,
        )
        state = 'blocked'
    elif capacity is None or not recipe_configured or not resource_unit_compatible:
        state = 'not_evaluable'
        alternative = None
    else:
        state = 'feasible_with_assumptions'
        alternative = None

    return ScenarioExplanation(
        status=state,
        constraints=constraints,
        alternative=alternative,
        caveat=(
            'Las cifras usan capacidad bruta y existencias registradas; no descuentan '
            'otros pedidos comprometidos ni reservas. Ningun resultado autoriza una promesa '
            'de entrega o una modificacion productiva.'
        ),
    )
