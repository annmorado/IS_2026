"""Operaciones transaccionales de login, cierre y aprovisionamiento inicial."""
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.modules.auth.model import AuthSession, User
from app.modules.auth.schemas import LoginRequest, TokenResponse
from app.modules.auth.security import (
    DUMMY_HASH, ACCESS_TOKEN_MINUTES, as_utc, create_access_token,
    hash_password, utc_now, verify_password,
)
from app.modules.organizations.model import Organization

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_first_owner(db: Session, *, organization_id: UUID, email: str, password: str) -> User:
    # Operacion exclusiva de CLI local; nunca se expone como endpoint publico.
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ValueError("Organizacion inexistente")
    existing_count = db.scalar(select(func.count()).select_from(User).where(User.organization_id == organization_id))
    if existing_count:
        raise ValueError("Esta organizacion ya tiene usuarios; utiliza la administracion de usuarios (RF-003)")
    user = User(
        organization_id=organization_id, email=normalize_email(email),
        password_hash=hash_password(password), role="owner", is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def login(db: Session, payload: LoginRequest) -> TokenResponse:
    # Clave definida antes del acceso a credenciales, incluso si el usuario no existe.
    from app.modules.auth.security import get_jwt_secret
    get_jwt_secret()
    user = db.scalar(
        select(User).where(
            User.organization_id == payload.organization_id,
            User.email == normalize_email(str(payload.email)),
        )
    )
    now = utc_now()
    if user is None:
        verify_password(payload.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    if user.locked_until is not None and as_utc(user.locked_until) > now:
        verify_password(payload.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    if not user.is_active:
        verify_password(payload.password, DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        raise HTTPException(status_code=401, detail="Credenciales invalidas")

    user.failed_login_attempts = 0
    user.locked_until = None
    session_id = uuid4()
    token, expires_at = create_access_token(
        user_id=user.id, organization_id=user.organization_id,
        session_id=session_id, now=now,
    )
    db.add(AuthSession(id=session_id, user_id=user.id, expires_at=expires_at))
    db.commit()
    return TokenResponse(access_token=token, expires_in=ACCESS_TOKEN_MINUTES * 60)
