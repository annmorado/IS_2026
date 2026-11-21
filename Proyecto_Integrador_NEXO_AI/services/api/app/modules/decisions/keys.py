"""RF-022: validación pura y compartida de claves idempotentes."""
import re
from fastapi import HTTPException
KEY_PATTERN = re.compile(r'^[A-Za-z0-9._:\-]{8,128}$')

def check_key(key: str | None) -> str:
    if not key or not KEY_PATTERN.fullmatch(key):
        raise HTTPException(status_code=422, detail='Idempotency-Key obligatorio, 8-128 caracteres seguros')
    return key
