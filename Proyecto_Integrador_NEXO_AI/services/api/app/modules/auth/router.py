"""RF-002: inicio y cierre de sesion; bootstrap de propietarios solo por CLI."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext, get_auth_context
from app.modules.auth.schemas import LoginRequest, LogoutResponse, TokenResponse, UserRead
from app.modules.auth.security import utc_now
from app.modules.auth.service import login

router = APIRouter(prefix="/auth", tags=["Autenticacion"])


@router.post("/login", response_model=TokenResponse)
def login_route(payload: LoginRequest, db: Session = Depends(get_db)):
    return login(db, payload)


@router.get("/me", response_model=UserRead)
def who_am_i(context: AuthContext = Depends(get_auth_context)):
    return context.user


@router.post("/logout", response_model=LogoutResponse)
def logout(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    context.session.revoked_at = utc_now()
    db.commit()
    return LogoutResponse()
