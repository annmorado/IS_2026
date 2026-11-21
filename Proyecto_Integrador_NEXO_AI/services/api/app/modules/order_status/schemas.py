"""RF-011: contratos estrictos de transiciones y consulta de auditoria."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrderStatus = Literal["draft", "pending", "confirmed", "in_progress", "completed", "cancelled"]


class StatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status: OrderStatus
    to_status: OrderStatus
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class StatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_id: UUID
    organization_id: UUID
    changed_by_user_id: UUID
    from_status: OrderStatus
    to_status: OrderStatus
    changed_at: datetime
    note: str | None


class StatusRead(BaseModel):
    order_id: UUID
    status: OrderStatus
    allowed_next: list[OrderStatus]
    review_revision: int


class TransitionResult(BaseModel):
    order: StatusRead
    event: StatusEventRead
