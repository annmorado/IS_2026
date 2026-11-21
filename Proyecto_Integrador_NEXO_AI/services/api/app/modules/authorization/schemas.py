"""Esquemas estrictos de politicas; importes decimales sin float."""
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requires_manual_approval: bool
    max_discount_percent: Decimal


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_manual_approval: bool | None = None
    max_discount_percent: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("100"), max_digits=5, decimal_places=2
    )

    @model_validator(mode="after")
    def validate_patch(self) -> "PolicyUpdate":
        changed = self.model_fields_set
        if not changed:
            raise ValueError("Debes indicar al menos una politica")
        if any(getattr(self, field) is None for field in changed):
            raise ValueError("Las politicas no pueden ser nulas")
        return self
