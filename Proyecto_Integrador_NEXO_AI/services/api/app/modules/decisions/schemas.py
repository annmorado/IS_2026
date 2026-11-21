"""Entradas acotadas para decisiones y respuestas versionadas."""
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.modules.scenarios.schemas import ScenarioInput, ScenarioResult


class RecommendationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: ScenarioInput


class RecommendationConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation: Literal['CONFIRMAR']
    expected_review_revision: int = Field(ge=0)
    acknowledge_estimates: Literal[True]
    exception_reason: str | None = Field(default=None, max_length=500)


class RecommendationRead(BaseModel):
    id: UUID
    organization_id: UUID
    order_id: UUID
    status: str
    engine_version: str
    expected_review_revision: int
    expected_order_status: str
    created_at: datetime
    created_by_user_id: UUID
    scenario: ScenarioInput
    result: ScenarioResult
    confirmed_at: datetime | None
    confirmed_by_user_id: UUID | None
    exception_reason: str | None
    applied_order_status: str | None
    persisted: bool = True


class AuditRead(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_user_id: UUID
    organization_id: UUID
    before: dict | None
    after: dict | None
    occurred_at: datetime


class AuditPage(BaseModel):
    items: list[AuditRead]
    total: int
    limit: int
    offset: int
