"""RF-002: pruebas negativas/positivas de sesiones revocables."""
from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.organizations.model import Organization
from app.modules.auth.model import User, AuthSession  # noqa: F401, metadata
from app.modules.auth.security import (
    JWT_AUDIENCE, JWT_ISSUER, hash_password, verify_password, utc_now,
)
from app.modules.auth.service import create_first_owner

SECRET = "rf002-solo-pruebas-no-se-usa-en-produccion-" + ("x" * 40)
PASS = "Contrasena-Fuerte-12345"


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with sessions() as db:
        org = Organization(name="Organizacion A", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        other = Organization(name="Organizacion B", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        db.add_all((org, other))
        db.flush()
        owner = create_first_owner(db, organization_id=org.id, email="OWNER@NEXO.COM", password=PASS)
        owner_id = owner.id
        org_id = org.id
        other_id = other.id
        db.commit()

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield {"client": client, "sessions": sessions, "org": org_id, "other": other_id, "user": owner_id}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def credentials(ctx, password=PASS, org=None, email="owner@nexo.com"):
    return {"organization_id": str(org or ctx["org"]), "email": email, "password": password}


def login(ctx):
    response = ctx["client"].post("/api/v1/auth/login", json=credentials(ctx))
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_contrasena_se_hashea_argon2id(context):
    with context["sessions"]() as db:
        user = db.get(User, context["user"])
        assert user.password_hash.startswith("$argon2id$")
        assert PASS not in user.password_hash
        assert verify_password(PASS, user.password_hash)
        assert not verify_password("mal", user.password_hash)


def test_login_retorna_jwt(context):
    response = context["client"].post("/api/v1/auth/login", json=credentials(context))
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 900
    decoded = jwt.decode(response.json()["access_token"], SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    assert decoded["org"] == str(context["org"])
    assert decoded["sub"] == str(context["user"])
    assert "jti" in decoded


def test_me_autenticado(context):
    response = context["client"].get("/api/v1/auth/me", headers=bearer(login(context)))
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@nexo.com"
    assert data["organization_id"] == str(context["org"])
    assert data["role"] == "owner"
    assert "password_hash" not in data


def test_logout_revoca_inmediatamente(context):
    token = login(context)
    response = context["client"].post("/api/v1/auth/logout", headers=bearer(token))
    assert response.status_code == 200
    assert response.json()["status"] == "session_revoked"
    assert context["client"].get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    assert context["client"].post("/api/v1/auth/logout", headers=bearer(token)).status_code == 401


def test_sin_token_es_401(context):
    assert context["client"].get("/api/v1/auth/me").status_code == 401
    assert context["client"].post("/api/v1/auth/logout").status_code == 401


def test_credenciales_incorrectas(context):
    response = context["client"].post("/api/v1/auth/login", json=credentials(context, password="otra-contrasena"))
    assert response.status_code == 401
    assert "token" not in response.text


def test_usuario_no_existente(context):
    response = context["client"].post("/api/v1/auth/login", json=credentials(context, email="desconocido@nexo.com"))
    assert response.status_code == 401


def test_organizacion_ajena_no_puede_iniciar_sesion(context):
    response = context["client"].post("/api/v1/auth/login", json=credentials(context, org=context["other"]))
    assert response.status_code == 401


def test_jwt_manipulado(context):
    token = login(context)
    damaged = token[:-5] + ("a" if token[-5] != "a" else "b") + token[-4:]
    assert context["client"].get("/api/v1/auth/me", headers=bearer(damaged)).status_code == 401


def test_jwt_expirado(context):
    token = login(context)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    claims["exp"] = utc_now() - timedelta(seconds=60)
    expired = jwt.encode(claims, SECRET, algorithm="HS256")
    assert context["client"].get("/api/v1/auth/me", headers=bearer(expired)).status_code == 401


def test_jwt_sin_sesion_registrada(context):
    token = login(context)
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], issuer=JWT_ISSUER, audience=JWT_AUDIENCE)
    claims["jti"] = str(uuid4())
    forged = jwt.encode(claims, SECRET, algorithm="HS256")
    assert context["client"].get("/api/v1/auth/me", headers=bearer(forged)).status_code == 401


def test_usuario_inactivo_no_accede(context):
    token = login(context)
    with context["sessions"]() as db:
        user = db.get(User, context["user"])
        user.is_active = False
        db.commit()
    assert context["client"].get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    assert context["client"].post("/api/v1/auth/login", json=credentials(context)).status_code == 401


def test_bloqueo_tras_cinco_intentos(context):
    client = context["client"]
    for _ in range(5):
        response = client.post("/api/v1/auth/login", json=credentials(context, password="incorrecta"))
        assert response.status_code == 401
    assert client.post("/api/v1/auth/login", json=credentials(context)).status_code == 401
    with context["sessions"]() as db:
        user = db.get(User, context["user"])
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None
        user.locked_until = utc_now() - timedelta(minutes=1)
        db.commit()
    assert client.post("/api/v1/auth/login", json=credentials(context)).status_code == 200


def test_no_permite_segundo_bootstrap(context):
    with context["sessions"]() as db:
        with pytest.raises(ValueError, match="ya tiene usuarios"):
            create_first_owner(db, organization_id=context["org"], email="otro@nexo.com", password=PASS)


def test_no_permite_bootstrap_en_org_inexistente(context):
    with context["sessions"]() as db:
        with pytest.raises(ValueError, match="inexistente"):
            create_first_owner(db, organization_id=uuid4(), email="otro@nexo.com", password=PASS)


def test_falta_clave_jwt_error_controlado(context, monkeypatch):
    monkeypatch.delenv("NEXO_JWT_SECRET")
    response = context["client"].post("/api/v1/auth/login", json=credentials(context))
    assert response.status_code == 503


def test_password_corta_rechazada(context):
    with pytest.raises(ValueError, match="12 y 128"):
        hash_password("123")


def test_openapi_incluye_auth(context):
    response = context["client"].get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths
