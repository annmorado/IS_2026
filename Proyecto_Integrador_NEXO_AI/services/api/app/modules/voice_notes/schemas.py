"""No exponer rutas locales del servidor ni claves de almacenamiento al cliente."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VoiceNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    byte_size: int
    duration_ms: int | None
    sha256_hex: str
    created_at: datetime
