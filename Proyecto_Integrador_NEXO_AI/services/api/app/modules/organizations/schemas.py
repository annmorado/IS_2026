from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sector: str = Field(min_length=1, max_length=80)
    timezone: str = Field(default="America/Mexico_City", max_length=64)
    currency: Literal["MXN"] = "MXN"

    @field_validator("name", "sector")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacio")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Zona horaria IANA invalida") from None
        return value


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sector: str
    timezone: str
    currency: Literal["MXN"]
    created_at: datetime
