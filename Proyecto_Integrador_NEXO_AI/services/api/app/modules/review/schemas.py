"""Contratos RF-010: sugerencias no confiables y decisiones humanas separadas."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class ReviewSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=3)
    due_date: date
    expected_revision: StrictInt = Field(ge=0)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: StrictInt = Field(ge=1)


class ReviewRead(BaseModel):
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    status: str
    raw_text: str
    # Solo datos propuestos. La IA aun no se conecta a RF-010.
    suggested_quantity: Decimal | None
    suggested_due_date: date | None
    # Valores revisados por una persona que pasan al pedido confirmado.
    reviewed_quantity: Decimal | None
    reviewed_due_date: date | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    confirmed_by_user_id: UUID | None
    confirmed_at: datetime | None
    review_revision: int
    requires_manual_review: bool


class ConfirmRead(ReviewRead):
    pass
