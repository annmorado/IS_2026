"""RF-001: pruebas locales, rapidas y reproducibles (SQLite en memoria)."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import require_local_bootstrap
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.organizations import model  # noqa: F401 registra la tabla


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_local_bootstrap] = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_crear_y_recuperar_organizacion(client: TestClient):
    payload = {"name": "  Taller NEXO  ", "sector": "Imprenta", "timezone": "America/Mexico_City", "currency": "MXN"}
    response = client.post("/api/v1/organizations", json=payload)
    assert response.status_code == 201
    org = response.json()
    assert org["name"] == "Taller NEXO"
    assert org["currency"] == "MXN"
    assert org["id"]
    assert org["created_at"]
    fetched = client.get(f"/api/v1/organizations/{org['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == org


def test_identificadores_unicos_y_respuesta_sin_otros_registros(client: TestClient):
    a = client.post("/api/v1/organizations", json={"name": "Organizacion A", "sector": "Taller"}).json()
    b = client.post("/api/v1/organizations", json={"name": "Organizacion B", "sector": "Imprenta"}).json()
    assert a["id"] != b["id"]
    response = client.get(f"/api/v1/organizations/{a['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == a["id"]
    assert b["id"] not in response.text
    assert b["name"] not in response.text


def test_moneda_invalida(client: TestClient):
    response = client.post("/api/v1/organizations", json={"name": "Empresa", "sector": "Taller", "currency": "USD"})
    assert response.status_code == 422


def test_zona_horaria_invalida(client: TestClient):
    response = client.post("/api/v1/organizations", json={"name": "Empresa", "sector": "Taller", "timezone": "Marte/Olimpo"})
    assert response.status_code == 422


def test_nombre_vacio(client: TestClient):
    response = client.post("/api/v1/organizations", json={"name": "   ", "sector": "Taller"})
    assert response.status_code == 422


def test_organizacion_inexistente(client: TestClient):
    response = client.get(f"/api/v1/organizations/{uuid4()}")
    assert response.status_code == 404


def test_bootstrap_bloqueado_desde_cliente_no_local():
    # TestClient usa la direccion "testclient", no loopback real.
    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/organizations", json={"name": "No", "sector": "Taller"})
    assert response.status_code == 403
