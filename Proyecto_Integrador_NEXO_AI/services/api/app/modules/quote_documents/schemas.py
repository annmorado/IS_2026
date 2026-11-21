"""Contrato RF-014: vigencia explicita y metadatos sin el binario PDF."""
from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    valid_until: date

class DocumentRead(BaseModel):
    id: UUID
    quote_id: UUID
    order_id: UUID
    organization_id: UUID
    quote_version: int
    folio: str
    valid_until: date
    generated_at: datetime
    generated_by_user_id: UUID
    sha256: str
    size_bytes: int
    download_path: str
