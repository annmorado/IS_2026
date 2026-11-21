"""RF-007: contratos para recursos, calendario y evaluacion bruta de capacidad."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

CAPACITY = dict(gt=Decimal("0"), max_digits=12, decimal_places=3)
DEMAND = dict(ge=Decimal("0"), max_digits=12, decimal_places=3)


def normalize_workdays(value: list[int]) -> list[int]:
    if not value or len(value) > 7 or any(type(day) is not int or day < 0 or day > 6 for day in value):
        raise ValueError("workdays debe contener dias entre 0 (lunes) y 6 (domingo)")
    if len(set(value)) != len(value):
        raise ValueError("workdays no admite dias repetidos")
    return sorted(value)


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=32)
    daily_capacity: Decimal = Field(**CAPACITY)
    workdays: list[StrictInt] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)

    @field_validator("code", "name", "unit")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @field_validator("workdays")
    @classmethod
    def validate_workdays(cls, value: list[int]) -> list[int]:
        return normalize_workdays(value)


class ResourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    daily_capacity: Decimal | None = Field(default=None, **CAPACITY)
    workdays: list[StrictInt] | None = Field(default=None, min_length=1, max_length=7)

    @field_validator("code", "name", "unit")
    @classmethod
    def strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @field_validator("workdays")
    @classmethod
    def validate_workdays(cls, value: list[int] | None) -> list[int] | None:
        return normalize_workdays(value) if value is not None else value

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Se requiere un cambio no nulo")
        return self


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    code: str
    name: str
    unit: str
    daily_capacity: Decimal
    workdays: list[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BlackoutRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resource_id: UUID
    day: date
    created_at: datetime


class CapacityEvaluation(BaseModel):
    resource_id: UUID
    unit: str
    start_date: date
    end_date: date
    requested_units: Decimal
    daily_capacity: Decimal
    calendar_days: int
    scheduled_workdays: int
    blacked_out_workdays: int
    available_workdays: int
    gross_capacity: Decimal
    shortage: Decimal
    feasible: bool
    minimum_workdays: int
    includes_existing_commitments: bool = False
