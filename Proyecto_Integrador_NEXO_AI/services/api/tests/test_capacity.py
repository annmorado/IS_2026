"""RF-007: 30 x 5 = 150, calendario, roles, tenant y validacion de rangos."""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth import security as security_module
from app.modules.auth.model import User  # noqa: F401 registra metadata
from app.modules.auth.security import hash_password
from app.modules.capacity.model import ProductionResource, ResourceBlackout  # noqa: F401
from app.modules.organizations.model import Organization
from app.modules.products.model import Product  # noqa: F401
from app.modules.materials.model import Material, ProductMaterial  # noqa: F401

SECRET = "rf007-test-jwt-solamente-" + "x" * 75
PASSWORD = "RF007-Capacidad-Segura-2026"
BASE = "/api/v1/capacity/resources"
WINDOW = "start_date=2026-11-16&end_date=2026-11-20&requested_units=160"


def payload(**changes):
    result = {
        "code": "LINEA-A", "name": "Linea de playeras", "unit": "pieza",
        "daily_capacity": "30.000", "workdays": [0, 1, 2, 3, 4],
    }
    result.update(changes)
    return result


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    # Test-only Argon2 settings. No se modifican hash ni tiempos en produccion.
    monkeypatch.setattr(security_module, "hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1))
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_fk(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    encoded = hash_password(PASSWORD)
    with factory() as db:
        a = Organization(name="Capacidad Alfa", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Capacidad Beta", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        db.add_all((a, b))
        db.flush()
        db.add_all([
            User(organization_id=a.id, email="cap-owner-a@example.com", password_hash=encoded, role="owner"),
            User(organization_id=a.id, email="cap-operator-a@example.com", password_hash=encoded, role="operator"),
            User(organization_id=b.id, email="cap-owner-b@example.com", password_hash=encoded, role="owner"),
        ])
        aid, bid = a.id, b.id
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def auth(email: str, org: UUID) -> dict[str, str]:
                r = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": PASSWORD,
                })
                assert r.status_code == 200, r.text
                return {"Authorization": "Bearer " + r.json()["access_token"]}
            yield {
                "client": client, "factory": factory, "a": aid, "b": bid,
                "owner_a": auth("cap-owner-a@example.com", aid),
                "operator_a": auth("cap-operator-a@example.com", aid),
                "owner_b": auth("cap-owner-b@example.com", bid),
            }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def request(ctx, method, url, *, role="owner_a", body=None):
    return ctx["client"].request(method, url, headers=ctx[role], json=body)


def create(ctx, *, role="owner_a", **changes):
    return request(ctx, "POST", BASE, role=role, body=payload(**changes))


def evaluation(ctx, resource_id, *, role="owner_a", query=WINDOW):
    return request(ctx, "GET", f"{BASE}/{resource_id}/evaluate?{query}", role=role)


def test_create_read_persist(ctx):
    r = create(ctx)
    assert r.status_code == 201, r.text
    value = r.json()
    assert value["organization_id"] == str(ctx["a"])
    assert value["workdays"] == [0,1,2,3,4]
    assert value["daily_capacity"] == "30.000"
    assert value["is_active"] is True
    assert request(ctx, "GET", BASE + "/" + value["id"]).status_code == 200
    with ctx["factory"]() as db:
        assert db.get(ProductionResource, UUID(value["id"])).daily_capacity == Decimal("30.000")


def test_30_per_day_times_5_workdays_is_150(ctx):
    rid = create(ctx).json()["id"]
    r = evaluation(ctx, rid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["calendar_days"] == 5
    assert data["scheduled_workdays"] == 5
    assert data["available_workdays"] == 5
    assert data["gross_capacity"] == "150.000"
    assert data["requested_units"] == "160"
    assert data["shortage"] == "10.000"
    assert data["feasible"] is False
    assert data["minimum_workdays"] == 6
    assert data["includes_existing_commitments"] is False


def test_exact_capacity_feasible(ctx):
    rid = create(ctx).json()["id"]
    response = evaluation(ctx, rid, query=WINDOW.replace("160", "150"))
    assert response.status_code == 200
    assert response.json()["feasible"] is True
    assert response.json()["shortage"] == "0.000"


def test_zero_requested_units_allowed(ctx):
    rid = create(ctx).json()["id"]
    data = evaluation(ctx, rid, query=WINDOW.replace("160", "0")).json()
    assert data["minimum_workdays"] == 0 and data["feasible"] is True


def test_operator_reads_but_cannot_create(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx, "GET", BASE, role="operator_a").status_code == 200
    assert request(ctx, "GET", BASE + "/" + rid, role="operator_a").status_code == 200
    assert evaluation(ctx, rid, role="operator_a").status_code == 200
    assert create(ctx, role="operator_a").status_code == 403


def test_list_and_pagination(ctx):
    create(ctx)
    create(ctx, code="LINEA-B")
    assert len(request(ctx, "GET", BASE).json()) == 2
    assert len(request(ctx, "GET", BASE + "?limit=1").json()) == 1
    assert len(request(ctx, "GET", BASE + "?offset=1&limit=1").json()) == 1


def test_duplicate_code_409(ctx):
    assert create(ctx).status_code == 201
    assert create(ctx).status_code == 409


def test_other_tenant_same_code_allowed(ctx):
    assert create(ctx).status_code == 201
    assert create(ctx, role="owner_b").status_code == 201


def test_patch_capacity_and_workdays(ctx):
    rid = create(ctx).json()["id"]
    r = request(ctx, "PATCH", BASE + "/" + rid, body={"daily_capacity": "40.000", "workdays": [4,0,1,3,2,5]})
    assert r.status_code == 200, r.text
    assert r.json()["workdays"] == [0,1,2,3,4,5]
    assert r.json()["daily_capacity"] == "40.000"
    assert evaluation(ctx, rid).json()["gross_capacity"] == "200.000"


def test_patch_duplicate_code_409(ctx):
    create(ctx)
    rid = create(ctx, code="LINEA-B").json()["id"]
    assert request(ctx, "PATCH", BASE + "/" + rid, body={"code":"LINEA-A"}).status_code == 409


def test_patch_invalid_unknown_field(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx, "PATCH", BASE + "/" + rid, body={"organization_id":str(ctx["b"])}).status_code == 422


@pytest.mark.parametrize("change", [
    {"daily_capacity":"0"}, {"daily_capacity":"-5"}, {"daily_capacity":"abc"},
    {"daily_capacity":"0.0001"}, {"daily_capacity": "1234567890123.000"},
    {"workdays": []}, {"workdays": [7]}, {"workdays": [-1]},
    {"workdays": [0,0]}, {"workdays": [True,2]}, {"workdays": [0,1,2,3,4,5,6,7]},
    {"name":"   "}, {"unit":"   "},
])
def test_invalid_create_returns_422(ctx, change):
    assert create(ctx, **change).status_code == 422


def test_empty_patch_and_null_rejected(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx, "PATCH", BASE + "/" + rid, body={}).status_code == 422
    assert request(ctx, "PATCH", BASE + "/" + rid, body={"daily_capacity": None}).status_code == 422


def test_blackout_reduces_available_capacity(ctx):
    rid = create(ctx).json()["id"]
    url = f"{BASE}/{rid}/blackouts/2026-11-17"
    r = request(ctx, "PUT", url)
    assert r.status_code == 200, r.text
    data = evaluation(ctx, rid).json()
    assert data["scheduled_workdays"] == 5
    assert data["blacked_out_workdays"] == 1
    assert data["available_workdays"] == 4
    assert data["gross_capacity"] == "120.000"
    assert data["shortage"] == "40.000"


def test_blackout_idempotent(ctx):
    rid = create(ctx).json()["id"]
    url = f"{BASE}/{rid}/blackouts/2026-11-17"
    a = request(ctx, "PUT", url).json()["id"]
    b = request(ctx, "PUT", url).json()["id"]
    assert a == b
    with ctx["factory"]() as db:
        assert db.query(ResourceBlackout).count() == 1


def test_blackout_list_and_delete(ctx):
    rid = create(ctx).json()["id"]
    url = f"{BASE}/{rid}/blackouts/2026-11-17"
    request(ctx, "PUT", url)
    assert request(ctx,"GET",f"{BASE}/{rid}/blackouts",role="operator_a").json()[0]["day"] == "2026-11-17"
    assert request(ctx, "DELETE", url).status_code == 204
    assert request(ctx, "DELETE", url).status_code == 404
    assert evaluation(ctx, rid).json()["gross_capacity"] == "150.000"


def test_blackout_on_weekend_does_not_reduce_workdays(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx, "PUT", f"{BASE}/{rid}/blackouts/2026-11-21").status_code == 200
    q = "start_date=2026-11-16&end_date=2026-11-22&requested_units=150"
    data = evaluation(ctx, rid, query=q).json()
    assert data["calendar_days"] == 7
    assert data["available_workdays"] == 5
    assert data["blacked_out_workdays"] == 0


def test_weekend_only_resource(ctx):
    rid = create(ctx, workdays=[5,6]).json()["id"]
    q = "start_date=2026-11-16&end_date=2026-11-22&requested_units=60"
    data = evaluation(ctx, rid, query=q).json()
    assert data["available_workdays"] == 2
    assert data["gross_capacity"] == "60.000"
    assert data["feasible"] is True


def test_one_day_period(ctx):
    rid = create(ctx).json()["id"]
    data = evaluation(ctx, rid, query="start_date=2026-11-16&end_date=2026-11-16&requested_units=31").json()
    assert data["calendar_days"] == 1 and data["gross_capacity"] == "30.000"
    assert data["shortage"] == "1.000"


@pytest.mark.parametrize("query", [
    "start_date=2026-11-20&end_date=2026-11-16&requested_units=1",
    "start_date=2026-01-01&end_date=2027-12-31&requested_units=1",
    "start_date=invalid&end_date=2026-11-20&requested_units=1",
    "start_date=2026-11-16&end_date=2026-11-20&requested_units=-1",
    "start_date=2026-11-16&end_date=2026-11-20&requested_units=0.0001",
])
def test_invalid_eval_returns_422(ctx, query):
    rid = create(ctx).json()["id"]
    assert evaluation(ctx, rid, query=query).status_code == 422


def test_owner_can_deactivate_and_exclude_from_list(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx, "POST", BASE + "/" + rid + "/deactivate").status_code == 200
    assert request(ctx, "GET", BASE).json() == []
    assert len(request(ctx,"GET",BASE+"?include_inactive=true").json()) == 1
    assert evaluation(ctx, rid).status_code == 409


def test_owner_can_read_deactivated_resource(ctx):
    rid = create(ctx).json()["id"]
    request(ctx,"POST", BASE+"/"+rid+"/deactivate")
    assert request(ctx,"GET",BASE+"/"+rid).json()["is_active"] is False


def test_other_tenant_cannot_access_or_edit(ctx):
    rid = create(ctx).json()["id"]
    assert request(ctx,"GET", BASE + "/" + rid,role="owner_b").status_code == 404
    assert request(ctx,"PATCH", BASE + "/" + rid,role="owner_b",body={"daily_capacity":"900.000"}).status_code == 404
    assert evaluation(ctx,rid,role="owner_b").status_code == 404
    assert request(ctx,"PUT",f"{BASE}/{rid}/blackouts/2026-11-17",role="owner_b").status_code == 404
    assert request(ctx,"GET",f"{BASE}/{rid}/blackouts",role="owner_b").status_code == 404
    assert request(ctx,"POST",BASE+"/"+rid+"/deactivate",role="owner_b").status_code == 404
    assert evaluation(ctx,rid).json()["gross_capacity"] == "150.000"


def test_tenant_header_is_ignored(ctx):
    rid = create(ctx).json()["id"]
    h = {**ctx["owner_a"], "X-Organization-ID": str(ctx["b"])}
    r = ctx["client"].get(BASE + "/" + rid, headers=h)
    assert r.status_code == 200 and r.json()["organization_id"] == str(ctx["a"])


def test_missing_vs_other_tenant_same_404(ctx):
    rid = create(ctx).json()["id"]
    other = request(ctx,"GET",BASE+"/"+rid,role="owner_b")
    unknown = request(ctx,"GET",BASE+"/"+str(uuid4()),role="owner_b")
    assert other.status_code == unknown.status_code == 404
    assert other.json() == unknown.json()


def test_operator_cannot_write(ctx):
    rid = create(ctx).json()["id"]
    urls = [
        ("PATCH",BASE+"/"+rid,{"daily_capacity":"40.000"}),
        ("POST",BASE+"/"+rid+"/deactivate",None),
        ("PUT",f"{BASE}/{rid}/blackouts/2026-11-17",None),
        ("DELETE",f"{BASE}/{rid}/blackouts/2026-11-17",None),
    ]
    for method, url, body in urls:
        assert request(ctx,method,url,role="operator_a",body=body).status_code == 403


def test_missing_token_rejected(ctx):
    rid = create(ctx).json()["id"]
    for method, path in [("GET",BASE),("POST",BASE),("GET",BASE+"/"+rid),
                         ("GET",BASE+"/"+rid+"/evaluate?"+WINDOW)]:
        response = ctx["client"].request(method,path,json=payload() if method=="POST" else None)
        assert response.status_code == 401


def test_operator_logout_revokes_eval_access(ctx):
    rid = create(ctx).json()["id"]
    h = ctx["operator_a"]
    assert ctx["client"].post("/api/v1/auth/logout",headers=h).status_code == 200
    assert ctx["client"].get(BASE+"/"+rid+"/evaluate?"+WINDOW,headers=h).status_code == 401


def test_openapi_includes_resource_endpoints(ctx):
    paths = ctx["client"].get("/openapi.json").json()["paths"]
    assert BASE in paths
    assert BASE+"/{resource_id}" in paths
    assert BASE+"/{resource_id}/evaluate" in paths
    assert BASE+"/{resource_id}/blackouts/{day}" in paths


def test_cross_tenant_blackout_fk_enforced(ctx):
    left = create(ctx).json()["id"]
    # No se pueden insertar excepciones de tenant B ligadas a un recurso de A.
    with ctx["factory"]() as db:
        db.add(ResourceBlackout(resource_id=UUID(left), organization_id=ctx["b"], day=date(2026, 11, 17)))
        with pytest.raises(Exception):
            db.commit()
        db.rollback()
