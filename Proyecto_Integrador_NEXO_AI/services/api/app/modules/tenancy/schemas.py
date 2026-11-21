"""Solo se aceptan campos administrativos explicitamente autorizados."""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MemberStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class SessionRevocationResult(BaseModel):
    status: Literal["sessions_revoked"] = "sessions_revoked"
    revoked_count: int
