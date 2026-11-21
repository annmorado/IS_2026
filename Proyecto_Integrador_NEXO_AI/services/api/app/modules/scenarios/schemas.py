"""Entradas y salidas explicitas de la simulacion editable."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: UUID
    product_id: UUID
    # Los cambios son exclusivamente temporales. No se guardan en la BD.
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    delivery_date: date | None = None
    start_date: date | None = None
    resource_id: UUID | None = None
    resource_daily_capacity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit_price_mxn: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def check_dependencies(self):
        if self.resource_daily_capacity is not None and self.resource_id is None:
            raise ValueError("Para modificar capacidad debe seleccionar un recurso")
        if self.start_date is not None and self.delivery_date is not None and self.start_date > self.delivery_date:
            raise ValueError("La fecha inicial no puede ser posterior a la entrega")
        return self


class MaterialSimulation(BaseModel):
    material_id: UUID
    name: str
    unit: str
    quantity_per_unit: Decimal
    required: Decimal
    available: Decimal
    shortage: Decimal


class CapacitySimulation(BaseModel):
    resource_id: UUID
    name: str
    unit: str
    start_date: date
    delivery_date: date
    daily_capacity: Decimal
    workable_days: int
    blacked_out_days: int
    available_capacity: Decimal
    shortage: Decimal
    feasible_without_commitments: bool
    includes_existing_commitments: bool = False


class ScenarioTotals(BaseModel):
    quantity: Decimal
    unit_price_mxn: Decimal
    unit_cost_mxn: Decimal
    revenue_mxn: Decimal
    direct_cost_mxn: Decimal
    estimated_gross_margin_mxn: Decimal


class ConstraintExplanation(BaseModel):
    code: str
    kind: str
    severity: str  # blocking | unknown
    title: str
    explanation: str
    shortage: Decimal | None
    unit: str | None
    missing_product_units: Decimal | None
    material_id: UUID | None = None


class ScenarioAlternative(BaseModel):
    units_possible_by_known_limits: Decimal
    units_to_reschedule: Decimal
    requested_delivery_date: date
    extra_workable_days_for_capacity: int | None
    estimated_delivery_date_by_capacity: date | None
    description: str


class ScenarioExplanation(BaseModel):
    status: str  # blocked | not_evaluable | feasible_with_assumptions
    constraints: list[ConstraintExplanation]
    alternative: ScenarioAlternative | None
    caveat: str


class ScenarioResult(BaseModel):
    order_id: UUID
    product_id: UUID
    delivery_date: date
    original: ScenarioTotals | None
    original_delivery_date: date | None
    simulated: ScenarioTotals
    capacity: CapacitySimulation | None
    materials: list[MaterialSimulation]
    recipe_configured: bool
    inventory_feasible_if_recipe_configured: bool | None
    editable_fields: list[str]
    explanation: ScenarioExplanation
    hypothetical: bool = True
    persisted: bool = False
    changes_applied: bool = False
    currency: str = "MXN"
    notes: list[str]
