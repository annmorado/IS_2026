"""RF-005: permisos, validaciones, operaciones y separacion por tenant."""
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User  # noqa: F401 registra metadata
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.products.model import Product  # noqa: F401 registra metadata
from app.modules.products.service import get_quotable_product
from app.modules.tenancy.scope import TenantScope

PASSWORD = "Nexo-RF005-Catalogo-2026!"
JWT = "rf005-solo-pruebas-" + "z" * 80
BASE = "/api/v1/products"


def example(**overrides):
    fields = {
        "sku": "CAMISETA-01",
        "name": "Camiseta estampada",
        "description": "Impresion serigrafica",
        "unit": "pieza",
        "cost_mxn": "45.50",
        "price_mxn": "85.00",
        "base_production_minutes": "25.50",
    }
    fields.update(overrides)
    return fields


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", JWT)
    # Reutilizar contexto en pruebas no significa omitir hash de contrasena.
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="Alfa", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Beta", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        create_first_owner(db, organization_id=a.id, email="alfa@example.com", password=PASSWORD)
        create_first_owner(db, organization_id=b.id, email="beta@example.com", password=PASSWORD)
        db.add(User(organization_id=a.id, email="operador@example.com", role="operator", is_active=True,
                    password_hash=hash_password(PASSWORD)))
        aid, bid = a.id, b.id
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def header(email, org):
                res = client.post("/api/v1/auth/login", json={
                    "email": email, "organization_id": str(org), "password": PASSWORD,
                })
                assert res.status_code == 200, res.text
                return {"Authorization": "Bearer " + res.json()["access_token"]}

            yield {
                "client": client, "factory": factory, "a": aid, "b": bid,
                "owner_a": header("alfa@example.com", aid),
                "owner_b": header("beta@example.com", bid),
                "operator_a": header("operador@example.com", aid),
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create(env, *, headers=None, **overrides):
    return env["client"].post(BASE, headers=headers or env["owner_a"], json=example(**overrides))


def test_create_and_read_persists(env):
    res = create(env)
    assert res.status_code == 201, res.text
    obj = res.json()
    assert obj["organization_id"] == str(env["a"])
    assert obj["is_active"] is True
    assert obj["name"] == "Camiseta estampada"
    assert obj["cost_mxn"] == "45.50"
    assert obj["price_mxn"] == "85.00"
    assert obj["base_production_minutes"] == "25.50"
    assert obj["created_at"] and obj["updated_at"]
    assert env["client"].get(BASE + "/" + obj["id"], headers=env["owner_a"]).status_code == 200
    with env["factory"]() as db:
        assert db.get(Product, UUID(obj["id"])).name == "Camiseta estampada"


def test_owner_can_update(env):
    pid = create(env).json()["id"]
    res = env["client"].patch(BASE + "/" + pid, headers=env["owner_a"],
        json={"name": "Nuevo nombre", "cost_mxn": "49.99", "base_production_minutes": "30.00"})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "Nuevo nombre"
    assert res.json()["cost_mxn"] == "49.99"
    assert res.json()["base_production_minutes"] == "30.00"
    with env["factory"]() as db:
        assert db.get(Product, UUID(pid)).cost_mxn == Decimal("49.99")


def test_description_can_be_cleared(env):
    pid = create(env).json()["id"]
    res = env["client"].patch(BASE + "/" + pid, headers=env["owner_a"], json={"description": None})
    assert res.status_code == 200
    assert res.json()["description"] is None


def test_deactivate_excludes_quotations(env):
    pid = create(env).json()["id"]
    assert any(p["id"] == pid for p in env["client"].get(BASE + "/quotable",headers=env["owner_a"]).json())
    res = env["client"].post(BASE + "/" + pid + "/deactivate", headers=env["owner_a"])
    assert res.status_code == 200, res.text
    assert res.json()["is_active"] is False
    assert not any(p["id"] == pid for p in env["client"].get(BASE + "/quotable",headers=env["owner_a"]).json())
    assert not any(p["id"] == pid for p in env["client"].get(BASE,headers=env["owner_a"]).json())
    assert any(p["id"] == pid for p in env["client"].get(BASE + "?include_inactive=true",headers=env["owner_a"]).json())
    assert env["client"].get(BASE + "/" + pid,headers=env["owner_a"]).status_code == 200
    with env["factory"]() as db:
        scope = TenantScope(organization_id=env["a"],actor_id=uuid4())
        with pytest.raises(HTTPException) as e:
            get_quotable_product(db,scope=scope,product_id=UUID(pid))
        assert e.value.status_code == 404


def test_deactivate_idempotent(env):
    pid=create(env).json()["id"]
    for _ in range(2):
        res=env["client"].post(BASE + "/" + pid + "/deactivate",headers=env["owner_a"])
        assert res.status_code == 200 and res.json()["is_active"] is False


def test_operator_can_read_catalog(env):
    pid=create(env).json()["id"]
    assert env["client"].get(BASE,headers=env["operator_a"]).status_code == 200
    assert env["client"].get(BASE + "/" + pid,headers=env["operator_a"]).status_code == 200
    assert env["client"].get(BASE + "/quotable",headers=env["operator_a"]).status_code == 200


def test_operator_cannot_modify(env):
    pid=create(env).json()["id"]
    cl=env["client"]
    assert create(env, headers=env["operator_a"], sku="OTHER").status_code == 403
    assert cl.patch(BASE + "/" + pid,headers=env["operator_a"],json={"name":"Dañado"}).status_code == 403
    assert cl.post(BASE + "/" + pid + "/deactivate",headers=env["operator_a"]).status_code == 403
    assert cl.get(BASE + "/" + pid,headers=env["owner_a"]).json()["name"] == "Camiseta estampada"


def test_no_token_is_401(env):
    cl=env["client"]
    assert cl.get(BASE).status_code == 401
    assert cl.post(BASE,json=example()).status_code == 401
    assert cl.get(BASE + "/quotable").status_code == 401


def test_tenants_isolated_all_operations(env):
    a = create(env).json()
    b = create(env, headers=env["owner_b"],sku="CAMISETA-01", name="Producto B").json()
    assert a["id"] != b["id"]
    cl=env["client"]
    assert [x["id"] for x in cl.get(BASE,headers=env["owner_b"]).json()] == [b["id"]]
    assert cl.get(BASE + "/" + a["id"],headers=env["owner_b"]).status_code == 404
    assert cl.patch(BASE + "/" + a["id"],headers=env["owner_b"],json={"name":"Evil"}).status_code == 404
    assert cl.post(BASE + "/" + a["id"] + "/deactivate",headers=env["owner_b"]).status_code == 404
    assert cl.get(BASE + "/" + b["id"],headers=env["owner_a"]).status_code == 404
    assert cl.get(BASE + "/" + a["id"],headers=env["owner_a"]).json()["name"] == a["name"]
    assert cl.get(BASE + "/" + b["id"],headers=env["owner_b"]).json()["is_active"] is True


def test_tenant_header_cannot_override_session(env):
    pid = create(env, headers=env["owner_b"]).json()["id"]
    headers = {**env["owner_a"], "X-Organization-ID": str(env["b"])}
    assert env["client"].get(BASE + "/" + pid,headers=headers).status_code == 404
    assert env["client"].get(BASE,headers=headers).json() == []


def test_unknown_id_returns_404(env):
    assert env["client"].get(BASE + "/" + str(uuid4()), headers=env["owner_a"]).status_code == 404
    assert env["client"].post(BASE + "/" + str(uuid4()) + "/deactivate",headers=env["owner_a"]).status_code == 404


def test_duplicate_sku_same_tenant_409(env):
    assert create(env).status_code == 201
    assert create(env).status_code == 409
    assert create(env,headers=env["owner_b"]).status_code == 201


def test_duplicate_sku_when_patching_409(env):
    create(env)
    second = create(env,sku="OTRO").json()
    assert env["client"].patch(BASE + "/" + second["id"],headers=env["owner_a"],json={"sku":"CAMISETA-01"}).status_code == 409
    assert env["client"].get(BASE + "/" + second["id"],headers=env["owner_a"]).json()["sku"] == "OTRO"


@pytest.mark.parametrize("field,value",[
    ("cost_mxn", "-0.01"),
    ("price_mxn", "-4"),
    ("base_production_minutes", "0"),
    ("base_production_minutes", "-1"),
    ("price_mxn", "1000000000000"),
    ("cost_mxn", "12.345"),
    ("base_production_minutes", "1.234"),
    ("sku", " "),
    ("name", " "),
    ("unit", " "),
])
def test_invalid_create_422(env, field, value):
    assert create(env,**{field:value}).status_code == 422


def test_unknown_field_create_422(env):
    assert create(env,organization_id=str(env["b"])).status_code == 422


def test_invalid_patch_422(env):
    pid=create(env).json()["id"]
    for body in ({}, {"name": None}, {"unit": "  "}, {"price_mxn": "-1"}, {"is_active": False}, {"organization_id": str(env["b"])}):
        assert env["client"].patch(BASE + "/" + pid,headers=env["owner_a"],json=body).status_code == 422


def test_sku_trimmed(env):
    obj=create(env,sku=" CAM-001 ",name=" Articulo ",unit=" unidad ").json()
    assert obj["sku"] == "CAM-001"
    assert obj["name"] == "Articulo"
    assert obj["unit"] == "unidad"


def test_pagination_and_limit(env):
    create(env,sku="A",name="A")
    create(env,sku="B",name="B")
    cl=env["client"]
    r=cl.get(BASE+"?limit=1&offset=1",headers=env["owner_a"])
    assert r.status_code == 200 and len(r.json()) == 1
    assert cl.get(BASE+"?limit=0",headers=env["owner_a"]).status_code == 422
    assert cl.get(BASE+"?limit=101",headers=env["owner_a"]).status_code == 422


def test_revoked_token_rejected(env):
    cl=env["client"]
    assert cl.post("/api/v1/auth/logout",headers=env["owner_a"]).status_code == 200
    assert cl.get(BASE,headers=env["owner_a"]).status_code == 401
    assert cl.post(BASE,json=example(),headers=env["owner_a"]).status_code == 401


def test_openapi_lists_product_paths(env):
    paths=env["client"].get("/openapi.json").json()["paths"]
    for path in [BASE, BASE+"/quotable", BASE+"/{product_id}", BASE+"/{product_id}/deactivate"]:
        assert path in paths
