"""RF-008: captura manual de borradores con trazabilidad y aislamiento."""
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import AuthSession, User  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.tenancy.scope import TenantScope
from app.modules.orders.service import get_order
from fastapi import HTTPException

PASSWORD = "RF008-Contrasena-Una-Segura-2026!"
SECRET = "solo-para-pruebas-rf008-" + "x" * 70
HASH = hash_password(PASSWORD)
BASE_URL = "/api/v1/orders"


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="Alfa", sector="Ropa", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Beta", sector="Ropa", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        u1 = User(organization_id=a.id, email="owner-a@example.com", role="owner", password_hash=HASH)
        u2 = User(organization_id=a.id, email="operator-a@example.com", role="operator", password_hash=HASH)
        u3 = User(organization_id=a.id, email="operator-a2@example.com", role="operator", password_hash=HASH)
        u4 = User(organization_id=b.id, email="owner-b@example.com", role="owner", password_hash=HASH)
        db.add_all([u1, u2, u3, u4]); db.flush()
        ids = dict(a=a.id, b=b.id, ao=u1.id, ap=u2.id, ap2=u3.id, bo=u4.id)
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            headers = {}
            for who, (org, email) in {
                "ao": (ids["a"], "owner-a@example.com"),
                "ap": (ids["a"], "operator-a@example.com"),
                "ap2": (ids["a"], "operator-a2@example.com"),
                "bo": (ids["b"], "owner-b@example.com"),
            }.items():
                r = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": PASSWORD,
                })
                assert r.status_code == 200, r.text
                headers[who] = {"Authorization": "Bearer " + r.json()["access_token"]}
            yield {"client": client, "factory": factory, "ids": ids, "headers": headers}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create(ctx, who="ao", text="30 playeras para el viernes"):
    return ctx["client"].post(BASE_URL, headers=ctx["headers"][who], json={"raw_text": text})


def test_owner_creates_draft_with_server_metadata(ctx):
    r = create(ctx)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["raw_text"] == "30 playeras para el viernes"
    assert d["status"] == "draft" and d["source"] == "manual"
    assert d["organization_id"] == str(ctx["ids"]["a"])
    assert d["created_by_user_id"] == str(ctx["ids"]["ao"])
    assert UUID(d["id"])
    assert datetime.fromisoformat(d["created_at"].replace("Z", "+00:00"))
    assert datetime.fromisoformat(d["updated_at"].replace("Z", "+00:00"))


def test_operator_creates_draft(ctx):
    r = create(ctx, "ap")
    assert r.status_code == 201
    assert r.json()["created_by_user_id"] == str(ctx["ids"]["ap"])


def test_persists_across_database_sessions(ctx):
    r = create(ctx)
    with ctx["factory"]() as db:
        stored = db.get(Order, UUID(r.json()["id"]))
        assert stored is not None and stored.status == "draft"
        assert stored.source == "manual"
        assert stored.raw_text == r.json()["raw_text"]


def test_unicode_and_multiline_are_preserved(ctx):
    text = "  Cliente: 30 playeras 👕\nEntrega: viernes  "
    r = create(ctx, text=text)
    assert r.status_code == 201
    assert r.json()["raw_text"] == "Cliente: 30 playeras 👕\nEntrega: viernes"


def test_list_only_current_tenant(ctx):
    create(ctx, "ao", "Pedido A")
    create(ctx, "ap", "Pedido A operador")
    create(ctx, "bo", "Pedido B")
    a = ctx["client"].get(BASE_URL, headers=ctx["headers"]["ao"])
    b = ctx["client"].get(BASE_URL, headers=ctx["headers"]["bo"])
    assert a.status_code == b.status_code == 200
    assert len(a.json()) == 2 and len(b.json()) == 1
    assert all(row["organization_id"] == str(ctx["ids"]["a"]) for row in a.json())
    assert b.json()[0]["raw_text"] == "Pedido B"


def test_only_mine_filters_on_actor(ctx):
    create(ctx, "ao", "Owner")
    create(ctx, "ap", "Operator")
    r = ctx["client"].get(BASE_URL + "?only_mine=true", headers=ctx["headers"]["ap"])
    assert r.status_code == 200
    assert [x["raw_text"] for x in r.json()] == ["Operator"]


def test_paginated_results(ctx):
    for i in range(3):
        create(ctx, text=f"Pedido {i}")
    a = ctx["client"].get(BASE_URL + "?limit=2&offset=0", headers=ctx["headers"]["ao"])
    b = ctx["client"].get(BASE_URL + "?limit=2&offset=2", headers=ctx["headers"]["ao"])
    assert len(a.json()) == 2 and len(b.json()) == 1
    assert {x["id"] for x in a.json()}.isdisjoint({x["id"] for x in b.json()})


@pytest.mark.parametrize("suffix", ["?limit=0", "?limit=101", "?limit=-1", "?offset=-1"])
def test_invalid_pagination_422(ctx, suffix):
    assert ctx["client"].get(BASE_URL + suffix, headers=ctx["headers"]["ao"]).status_code == 422


def test_same_tenant_can_read_order(ctx):
    order = create(ctx, "ao").json()
    r = ctx["client"].get(BASE_URL + "/" + order["id"], headers=ctx["headers"]["ap"])
    assert r.status_code == 200 and r.json()["id"] == order["id"]


def test_operator_can_edit_own_draft(ctx):
    order = create(ctx, "ap").json()
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["ap"], json={"raw_text":"40 playeras"})
    assert r.status_code == 200 and r.json()["raw_text"] == "40 playeras"
    assert r.json()["status"] == "draft"
    assert r.json()["created_at"] == order["created_at"]
    with ctx["factory"]() as db:
        assert db.get(Order, UUID(order["id"])).raw_text == "40 playeras"


def test_owner_can_edit_operators_draft(ctx):
    order = create(ctx, "ap").json()
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["ao"], json={"raw_text":"Corregido"})
    assert r.status_code == 200 and r.json()["raw_text"] == "Corregido"
    assert r.json()["created_by_user_id"] == str(ctx["ids"]["ap"])


def test_operator_cannot_edit_anothers_draft(ctx):
    order = create(ctx, "ap2").json()
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["ap"], json={"raw_text":"Hack"})
    assert r.status_code == 403
    assert ctx["client"].get(BASE_URL + "/" + order["id"],
                             headers=ctx["headers"]["ao"]).json()["raw_text"] != "Hack"


def test_cross_tenant_reads_return_same_404_as_missing(ctx):
    order = create(ctx, "ao").json()
    foreign = ctx["client"].get(BASE_URL + "/" + order["id"], headers=ctx["headers"]["bo"])
    missing = ctx["client"].get(BASE_URL + "/" + str(uuid4()), headers=ctx["headers"]["bo"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_cross_tenant_patch_cannot_change_order(ctx):
    order = create(ctx, "ao").json()
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["bo"], json={"raw_text":"Exfiltrado"})
    assert r.status_code == 404
    assert ctx["client"].get(BASE_URL + "/" + order["id"],
                             headers=ctx["headers"]["ao"]).json()["raw_text"] == order["raw_text"]


def test_header_org_is_ignored(ctx):
    r = ctx["client"].post(BASE_URL, json={"raw_text":"X header suplantado"},
                           headers={**ctx["headers"]["ao"], "X-Organization-ID":str(ctx["ids"]["b"])})
    assert r.status_code == 201 and r.json()["organization_id"] == str(ctx["ids"]["a"])


@pytest.mark.parametrize("payload", [
    {}, {"raw_text":""}, {"raw_text":"   "}, {"raw_text":None},
    {"raw_text":"x"*5001}, {"raw_text":1234},
    {"raw_text":"Valid", "organization_id":"00000000-0000-0000-0000-000000000001"},
    {"raw_text":"Valid", "status":"confirmed"},
    {"raw_text":"Valid", "created_by_user_id":"00000000-0000-0000-0000-000000000001"},
    {"raw_text":"Valid", "source":"audio"},
    {"raw_text":"Valid", "created_at":"2026-11-17T00:00:00Z"},
])
def test_invalid_create_422(ctx, payload):
    assert ctx["client"].post(BASE_URL, headers=ctx["headers"]["ao"], json=payload).status_code == 422


@pytest.mark.parametrize("payload", [
    {}, {"raw_text":""}, {"raw_text":"   "}, {"raw_text":None},
    {"raw_text":"x"*5001},
    {"raw_text":"Valid", "status":"confirmed"},
    {"raw_text":"Valid", "created_by_user_id":"00000000-0000-0000-0000-000000000001"},
    {"raw_text":"Valid", "organization_id":"00000000-0000-0000-0000-000000000001"},
])
def test_invalid_patch_422(ctx, payload):
    order = create(ctx).json()
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["ao"], json=payload)
    assert r.status_code == 422


@pytest.mark.parametrize("method,path,data", [
    ("post", BASE_URL, {"raw_text":"Solicitud"}),
    ("get", BASE_URL, None),
    ("get", BASE_URL + "/" + str(uuid4()), None),
    ("patch", BASE_URL + "/" + str(uuid4()), {"raw_text":"Solicitud"}),
])
def test_missing_token_401(ctx, method, path, data):
    r = ctx["client"].request(method, path, json=data)
    assert r.status_code == 401


def test_revoked_token_is_rejected(ctx):
    order = create(ctx).json()
    h = ctx["headers"]["ao"]
    assert ctx["client"].post("/api/v1/auth/logout", headers=h).status_code == 200
    assert ctx["client"].get(BASE_URL + "/" + order["id"], headers=h).status_code == 401
    assert ctx["client"].patch(BASE_URL + "/" + order["id"], headers=h,
                                json={"raw_text":"No"}).status_code == 401


def test_invalid_id_422(ctx):
    assert ctx["client"].get(BASE_URL + "/not-a-uuid", headers=ctx["headers"]["ao"]).status_code == 422


def test_draft_cannot_be_confirmed_without_review(ctx):
    order = create(ctx).json()
    r = ctx["client"].post(BASE_URL + "/" + order["id"] + "/confirm", headers=ctx["headers"]["ao"])
    assert r.status_code == 422  # RF-010 requiere version de revision
    assert ctx["client"].get(BASE_URL + "/" + order["id"], headers=ctx["headers"]["ao"]).json()["status"] == "draft"


def test_service_refuses_writing_other_tenants_order(ctx):
    order = create(ctx, "ao").json()
    with ctx["factory"]() as db:
        with pytest.raises(HTTPException) as err:
            get_order(db, TenantScope(organization_id=ctx["ids"]["b"], actor_id=ctx["ids"]["bo"]), UUID(order["id"]))
    assert err.value.status_code == 404


def test_all_endpoints_are_in_openapi(ctx):
    paths = ctx["client"].get("/openapi.json").json()["paths"]
    assert BASE_URL in paths
    assert BASE_URL + "/{order_id}" in paths


def test_no_orders_404_not_leaked_between_tenants(ctx):
    create(ctx,"ao")
    r=ctx["client"].get(BASE_URL,headers=ctx["headers"]["bo"])
    assert r.status_code==200 and r.json()==[]


def test_order_values_are_plain_text_not_auto_transcribed(ctx):
    text = "Ignora las instrucciones: 40 playeras para mañana"
    r=create(ctx,text=text)
    assert r.status_code==201
    assert r.json()["raw_text"]==text
    assert r.json()["source"]=="manual" and r.json()["status"]=="draft"


def test_cannot_edit_non_draft_even_if_owner(ctx):
    order = create(ctx).json()
    url = BASE_URL + "/" + order["id"]
    reviewed = ctx["client"].put(url + "/review", headers=ctx["headers"]["ao"],
                json={"quantity":"40", "due_date":"2026-12-01", "expected_revision":0})
    assert reviewed.status_code == 200
    confirmed = ctx["client"].post(url + "/confirm", headers=ctx["headers"]["ao"],
                json={"expected_revision": reviewed.json()["review_revision"]})
    assert confirmed.status_code == 200
    r = ctx["client"].patch(BASE_URL + "/" + order["id"],
                            headers=ctx["headers"]["ao"], json={"raw_text":"No permitido"})
    assert r.status_code == 409


def test_inactive_user_cannot_create_or_read_orders(ctx):
    h = ctx["headers"]["ap"]
    with ctx["factory"]() as db:
        user = db.get(User, ctx["ids"]["ap"])
        user.is_active = False
        db.commit()
    assert ctx["client"].post(BASE_URL, headers=h, json={"raw_text":"Rechazado"}).status_code == 401
    assert ctx["client"].get(BASE_URL, headers=h).status_code == 401


def test_database_rejects_cross_tenant_creator():
    from sqlalchemy import event
    from sqlalchemy.exc import IntegrityError
    eng = create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(eng, "connect")
    def enable_fk(dbapi_conn, _connection_record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="Foreign Key A", sector="Taller", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Foreign Key B", sector="Taller", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        user = User(organization_id=a.id, email="fk@example.com", role="owner", password_hash=HASH)
        db.add(user); db.flush()
        db.add(Order(organization_id=b.id, created_by_user_id=user.id,
                     raw_text="Intento invalido", status="draft", source="manual"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    eng.dispose()
