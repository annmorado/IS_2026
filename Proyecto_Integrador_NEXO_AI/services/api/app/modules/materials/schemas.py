"""Contratos estrictos para stock y recetas. Dinero y cantidades: Decimal."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STOCK = dict(ge=Decimal("0"), max_digits=15, decimal_places=3)
CONSUMPTION = dict(gt=Decimal("0"), max_digits=15, decimal_places=3)


class MaterialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=32)
    quantity_available: Decimal = Field(default=Decimal("0"), **STOCK)

    @field_validator("sku", "name", "unit")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value


class MaterialPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("sku", "name")
    @classmethod
    def strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @model_validator(mode="after")
    def verify(self) -> "MaterialPatch":
        if not self.model_fields_set or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError("Indica al menos un cambio no nulo")
        return self


class StockSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_available: Decimal = Field(**STOCK)


class RecipeItemSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity_per_unit: Decimal = Field(**CONSUMPTION)


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    sku: str
    name: str
    unit: str
    quantity_available: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RecipeItemRead(BaseModel):
    material_id: UUID
    sku: str
    name: str
    unit: str
    quantity_per_unit: Decimal
    quantity_available: Decimal
    is_active: bool


class RecipeRead(BaseModel):
    product_id: UUID
    items: list[RecipeItemRead]


class MaterialNeedRead(RecipeItemRead):
    required: Decimal
    shortage: Decimal
    sufficient: bool


class RequirementsRead(BaseModel):
    product_id: UUID
    quantity: Decimal
    recipe_configured: bool
    feasible: bool
    materials: list[MaterialNeedRead]
