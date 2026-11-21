"""RF-008: captura estricta de texto libre y lectura de metadatos inmutables."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str = Field(min_length=1, max_length=5000)

    @field_validator("raw_text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El texto de la solicitud no puede estar vacio")
        return value


class OrderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str | None = Field(default=None, min_length=1, max_length=5000)

    @field_validator("raw_text")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("El texto de la solicitud no puede estar vacio")
        return value

    @model_validator(mode="after")
    def validate_patch(self):
        if self.model_fields_set != {"raw_text"} or self.raw_text is None:
            raise ValueError("Se requiere raw_text valido")
        return self


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    raw_text: str
    status: Literal["draft", "pending", "confirmed", "in_progress", "completed", "cancelled"]
    source: Literal["manual", "audio"]
    created_at: datetime
    updated_at: datetime
    reviewed_quantity: Decimal | None
    reviewed_due_date: date | None
    confirmed_at: datetime | None
    review_revision: int
