"""Hash de contrasenas Argon2id y JWT firmados con clave de entorno."""
from datetime import datetime, timedelta, timezone
import os
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, status
import jwt

from app.core.config import API_ROOT  # noqa: F401 - carga .env en el arranque

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "nexo-ai-api"
JWT_AUDIENCE = "nexo-ai-clients"
ACCESS_TOKEN_MINUTES = 15

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
# Hash ficticio para que las cuentas inexistentes ejecuten una comparacion Argon2.
DUMMY_HASH = hasher.hash("Cuenta-desconocida-no-utilizable-2026")


def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("La contrasena debe tener entre 12 y 128 caracteres")
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def get_jwt_secret() -> str:
    secret = os.getenv("NEXO_JWT_SECRET", "")
    if len(secret) < 48:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticacion no configurada",
        )
    return secret


def create_access_token(*, user_id: UUID, organization_id: UUID, session_id: UUID, now: datetime) -> tuple[str, datetime]:
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "org": str(organization_id),
        "jti": str(session_id),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM), expires_at


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, get_jwt_secret(), algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
            options={"require": ["sub", "org", "jti", "iss", "aud", "iat", "nbf", "exp"]},
            leeway=0,
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion invalida o vencida",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite de pruebas no conserva tzinfo; PostgreSQL si.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
