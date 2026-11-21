"""RF-003: pruebas RBAC de propietario y operador con dos organizaciones."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import AuthSession, User  # noqa: F401 register tables
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.authorization.dependencies import require_roles
from app.modules.organizations.model import Organization

PASSWORD = "Contrasena-RBAC-2026!"
JWT_SECRET = "solo-para-pruebas-rbac-nexo-" + ("z" * 60)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", JWT_SECRET)
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as db:
        a = Organization(name="Empresa Alfa", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Empresa Beta", sector="Reposteria", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        create_first_owner(db, organization_id=a.id, email="dueno@alfa.example", password=PASSWORD)
        create_first_owner(db, organization_id=b.id, email="dueno@beta.example", password=PASSWORD)
        db.add(User(
            organization_id=a.id, email="operador@alfa.example", role="operator",
            password_hash=hash_password(PASSWORD), is_active=True,
        ))
        aid, bid = a.id, b.id
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def token(email, organization):
                result = client.post("/api/v1/auth/login", json={
                    "email": email, "organization_id": str(organization), "password": PASSWORD,
                })
                assert result.status_code == 200, result.text
                return result.json()["access_token"]
            yield {
                "client": client, "factory": factory, "org_a": aid, "org_b": bid,
                "owner_a": token("dueno@alfa.example", aid),
                "operator_a": token("operador@alfa.example", aid),
                "owner_b": token("dueno@beta.example", bid),
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def endpoint(suffix=""):
    return "/api/v1/organizations/me" + suffix


def test_owner_can_read_own_organization(env):
    res = env["client"].get(endpoint(), headers=auth(env["owner_a"]))
    assert res.status_code == 200
    assert res.json()["id"] == str(env["org_a"])
    assert res.json()["name"] == "Empresa Alfa"


def test_operator_can_read_own_organization(env):
    res = env["client"].get(endpoint(), headers=auth(env["operator_a"]))
    assert res.status_code == 200
    assert res.json()["id"] == str(env["org_a"])


def test_owner_of_another_business_sees_only_own(env):
    response = env["client"].get(endpoint(), headers=auth(env["owner_b"]))
    assert response.status_code == 200
    assert response.json()["id"] == str(env["org_b"])
    assert str(env["org_a"]) not in response.text


def test_unauthed_profile_returns_401(env):
    assert env["client"].get(endpoint()).status_code == 401


def test_unauthed_policies_returns_401(env):
    assert env["client"].get(endpoint("/policies")).status_code == 401


def test_owner_reads_default_policies(env):
    res = env["client"].get(endpoint("/policies"), headers=auth(env["owner_a"]))
    assert res.status_code == 200
    assert res.json() == {"requires_manual_approval": True, "max_discount_percent": "0.00"}


def test_operator_reads_policies(env):
    res = env["client"].get(endpoint("/policies"), headers=auth(env["operator_a"]))
    assert res.status_code == 200


def test_owner_changes_policy(env):
    res = env["client"].patch(
        endpoint("/policies"), headers=auth(env["owner_a"]),
        json={"requires_manual_approval": False, "max_discount_percent": "12.50"},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"requires_manual_approval": False, "max_discount_percent": "12.50"}


def test_operator_cannot_change_policy_403(env):
    res = env["client"].patch(endpoint("/policies"), headers=auth(env["operator_a"]), json={"max_discount_percent": "15"})
    assert res.status_code == 403
    res2 = env["client"].get(endpoint("/policies"), headers=auth(env["owner_a"]))
    assert res2.json()["max_discount_percent"] == "0.00"


def test_policy_change_visible_to_operator_same_business(env):
    client=env["client"]
    assert client.patch(endpoint("/policies"), headers=auth(env["owner_a"]), json={"max_discount_percent": "5.25"}).status_code == 200
    read=client.get(endpoint("/policies"), headers=auth(env["operator_a"]))
    assert read.json()["max_discount_percent"] == "5.25"


def test_policy_isolation_across_businesses(env):
    client=env["client"]
    assert client.patch(endpoint("/policies"), headers=auth(env["owner_a"]), json={"max_discount_percent": "19.75"}).status_code == 200
    own_b=client.get(endpoint("/policies"),headers=auth(env["owner_b"]))
    assert own_b.status_code == 200
    assert own_b.json()["max_discount_percent"] == "0.00"


@pytest.mark.parametrize("value", ["-1", "100.01", "101", "1.999", "invalid"])
def test_invalid_discount_returns_422(env, value):
    res=env["client"].patch(endpoint("/policies"),headers=auth(env["owner_a"]),json={"max_discount_percent":value})
    assert res.status_code == 422


def test_unknown_field_rejected(env):
    response=env["client"].patch(endpoint("/policies"),headers=auth(env["owner_a"]),json={"role":"owner"})
    assert response.status_code == 422


def test_empty_patch_rejected(env):
    response=env["client"].patch(endpoint("/policies"),headers=auth(env["owner_a"]),json={})
    assert response.status_code == 422


def test_null_policy_rejected(env):
    response=env["client"].patch(endpoint("/policies"),headers=auth(env["owner_a"]),json={"requires_manual_approval":None})
    assert response.status_code == 422


def test_revoked_owner_token_cannot_change_policy(env):
    client=env["client"]
    headers=auth(env["owner_a"])
    assert client.post("/api/v1/auth/logout",headers=headers).status_code == 200
    assert client.patch(endpoint("/policies"),headers=headers,json={"max_discount_percent":"5"}).status_code == 401


def test_unknown_role_configuration_fails_closed():
    with pytest.raises(ValueError):
        require_roles("admin")
    with pytest.raises(ValueError):
        require_roles()


def test_policy_persists_across_db_sessions(env):
    client=env["client"]
    assert client.patch(endpoint("/policies"),headers=auth(env["owner_a"]),json={"max_discount_percent":"9.00"}).status_code == 200
    with env["factory"]() as db:
        org=db.get(Organization,env["org_a"])
        assert org.max_discount_percent == Decimal("9.00")


def test_duplicate_header_org_cannot_override_context(env):
    response=env["client"].get(endpoint(),headers={**auth(env["owner_a"]), "X-Organization-ID":str(env["org_b"])})
    assert response.status_code == 200
    assert response.json()["id"] == str(env["org_a"])
