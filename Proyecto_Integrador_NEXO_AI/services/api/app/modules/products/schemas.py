"""Validaciones Pydantic para catálogo de productos RF-005."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    unit: str = Field(min_length=1, max_length=32)
    cost_mxn: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    price_mxn: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    base_production_minutes: Decimal = Field(gt=Decimal("0"), max_digits=10, decimal_places=2)

    @field_validator("sku", "name", "unit")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ProductCreate(ProductFields):
    pass


class ProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    cost_mxn: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=2)
    price_mxn: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=12, decimal_places=2)
    base_production_minutes: Decimal | None = Field(default=None, gt=Decimal("0"), max_digits=10, decimal_places=2)

    @field_validator("sku", "name", "unit")
    @classmethod
    def strip_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def ensure_real_change(self) -> "ProductPatch":
        if not self.model_fields_set:
            raise ValueError("Debes indicar al menos un campo")
        if any(
            field != "description" and getattr(self, field) is None
            for field in self.model_fields_set
        ):
            raise ValueError("Los campos obligatorios no pueden ser nulos")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    sku: str
    name: str
    description: str | None
    unit: str
    cost_mxn: Decimal
    price_mxn: Decimal
    base_production_minutes: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
