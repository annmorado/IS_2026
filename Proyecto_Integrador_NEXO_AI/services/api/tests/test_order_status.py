"""RF-011: maquina de estados, historial, RBAC, tenant y persistencia."""
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User, AuthSession  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.order_status.model import OrderStatusEvent
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization

PASSWORD = "RF011-Prueba-Local-Muy-Segura!"
SECRET = "rf011-only-test-" + "a" * 80
HASH = hash_password(PASSWORD)
PREFIX = "/api/v1/orders"


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk_on(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="RF011 A", sector="Servicios", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="RF011 B", sector="Servicios", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        users = {
            "owner": User(organization_id=a.id, email="owner@rf011.example", password_hash=HASH, role="owner"),
            "operator": User(organization_id=a.id, email="op@rf011.example", password_hash=HASH, role="operator"),
            "operator2": User(organization_id=a.id, email="op2@rf011.example", password_hash=HASH, role="operator"),
            "other": User(organization_id=b.id, email="other@rf011.example", password_hash=HASH, role="owner"),
        }
        db.add_all(users.values()); db.flush()
        ids = {"a": a.id, "b": b.id, **{name: u.id for name, u in users.items()}}
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as c:
            auth = {}
            for name, email, org in [
                ("owner", "owner@rf011.example", ids["a"]),
                ("operator", "op@rf011.example", ids["a"]),
                ("operator2", "op2@rf011.example", ids["a"]),
                ("other", "other@rf011.example", ids["b"]),
            ]:
                r = c.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": PASSWORD,
                })
                assert r.status_code == 200, r.text
                auth[name] = {"Authorization": "Bearer " + r.json()["access_token"]}
            yield {"client": c, "factory": factory, "auth": auth, "ids": ids}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def new(ctx, who="operator"):
    r = ctx["client"].post(PREFIX, headers=ctx["auth"][who], json={"raw_text": "10 productos para el jueves"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def path(oid): return PREFIX + "/" + oid


def move(ctx, oid, previous, target, who="operator", **extra):
    return ctx["client"].post(path(oid) + "/status", headers=ctx["auth"][who],
                              json={"expected_status": previous, "to_status": target, **extra})


def review_confirm(ctx, oid, who="operator", expected_revision=0):
    reviewed = ctx["client"].put(path(oid) + "/review", headers=ctx["auth"][who], json={
        "quantity": "12.500", "due_date": "2026-12-10", "expected_revision": expected_revision,
    })
    assert reviewed.status_code == 200, reviewed.text
    r = ctx["client"].post(path(oid) + "/confirm", headers=ctx["auth"][who],
                           json={"expected_revision": reviewed.json()["review_revision"]})
    assert r.status_code == 200, r.text
    return r


def get_history(ctx, oid, who="operator", suffix=""):
    return ctx["client"].get(path(oid) + "/history" + suffix, headers=ctx["auth"][who])


def test_new_draft_has_no_events(ctx):
    oid = new(ctx)
    r = ctx["client"].get(path(oid) + "/status", headers=ctx["auth"]["operator"])
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    assert set(r.json()["allowed_next"]) == {"pending", "cancelled"}
    assert get_history(ctx, oid).json() == []


def test_full_lifecycle_records_all_5_events(ctx):
    oid = new(ctx)
    assert move(ctx, oid, "draft", "pending").status_code == 200
    assert move(ctx, oid, "pending", "draft").status_code == 200
    review_confirm(ctx, oid)
    assert move(ctx, oid, "confirmed", "in_progress").status_code == 200
    done = move(ctx, oid, "in_progress", "completed", note="Trabajo entregado")
    assert done.status_code == 200, done.text
    assert done.json()["order"]["status"] == "completed"
    assert done.json()["order"]["allowed_next"] == []
    events = get_history(ctx, oid).json()
    assert len(events) == 5
    assert {(x["from_status"], x["to_status"]) for x in events} == {
        ("draft", "pending"), ("pending", "draft"), ("draft", "confirmed"),
        ("confirmed", "in_progress"), ("in_progress", "completed"),
    }
    assert all(x["changed_by_user_id"] == str(ctx["ids"]["operator"]) for x in events)
    assert all(x["organization_id"] == str(ctx["ids"]["a"]) for x in events)
    assert all(datetime.fromisoformat(x["changed_at"].replace("Z", "+00:00")) for x in events)
    assert any(x["note"] == "Trabajo entregado" for x in events)


def test_pending_can_be_reviewed_and_confirmed(ctx):
    oid = new(ctx)
    assert move(ctx, oid, "draft", "pending").status_code == 200
    review_confirm(ctx, oid)
    events = get_history(ctx, oid).json()
    assert len(events) == 2
    assert {(e["from_status"], e["to_status"]) for e in events} == {
        ("draft", "pending"), ("pending", "confirmed")}


@pytest.mark.parametrize("origin", ["draft", "pending", "confirmed", "in_progress"])
def test_cancellation_from_open_states(ctx, origin):
    oid = new(ctx)
    if origin in {"pending"}:
        assert move(ctx, oid, "draft", "pending").status_code == 200
    if origin in {"confirmed", "in_progress"}:
        review_confirm(ctx, oid)
    if origin == "in_progress":
        assert move(ctx, oid, "confirmed", "in_progress").status_code == 200
    cancelled = move(ctx, oid, origin, "cancelled", note="Cliente cancela")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["event"]["from_status"] == origin
    assert cancelled.json()["event"]["to_status"] == "cancelled"
    assert move(ctx, oid, "cancelled", "completed").status_code == 409
    assert move(ctx, oid, "cancelled", "draft").status_code == 409


def test_completed_is_terminal(ctx):
    oid = new(ctx)
    review_confirm(ctx, oid)
    assert move(ctx, oid, "confirmed", "in_progress").status_code == 200
    assert move(ctx, oid, "in_progress", "completed").status_code == 200
    assert move(ctx, oid, "completed", "cancelled").status_code == 409
    assert move(ctx, oid, "completed", "in_progress").status_code == 409


@pytest.mark.parametrize("old,new", [
    ("draft", "completed"), ("draft", "in_progress"), ("draft", "confirmed"),
    ("pending", "completed"), ("pending", "in_progress"), ("pending", "confirmed"),
    ("draft", "draft"), ("draft", "completed"),
])
def test_illegal_state_changes_are_409(ctx, old, new):
    oid = globals()["new"](ctx)
    if old == "pending": assert move(ctx, oid, "draft", "pending").status_code == 200
    assert move(ctx, oid, old, new).status_code == 409
    assert len(get_history(ctx, oid).json()) == (0 if old == "draft" else 1)


def test_confirm_requires_rf010_review(ctx):
    oid = new(ctx)
    r = ctx["client"].post(path(oid) + "/confirm", headers=ctx["auth"]["operator"],
                           json={"expected_revision": 1})
    assert r.status_code == 409
    assert move(ctx, oid, "draft", "confirmed").status_code == 409
    assert get_history(ctx, oid).json() == []


def test_confirm_is_audited_even_when_called_via_rf010(ctx):
    oid = new(ctx)
    review_confirm(ctx, oid)
    events = get_history(ctx, oid).json()
    assert len(events) == 1
    assert events[0]["from_status"] == "draft" and events[0]["to_status"] == "confirmed"
    assert events[0]["note"] == "Confirmacion humana RF-010"


def test_stale_expected_status_rejected_without_event(ctx):
    oid = new(ctx)
    assert move(ctx, oid, "draft", "pending").status_code == 200
    assert move(ctx, oid, "draft", "cancelled").status_code == 409
    assert len(get_history(ctx, oid).json()) == 1


def test_owner_can_manage_another_operators_order(ctx):
    oid = new(ctx, who="operator2")
    assert move(ctx, oid, "draft", "pending", who="owner").status_code == 200


def test_operator_cannot_manage_other_operator_order(ctx):
    oid = new(ctx, who="operator2")
    assert move(ctx, oid, "draft", "pending", who="operator").status_code == 403
    assert get_history(ctx, oid).json() == []
    assert ctx["client"].get(path(oid) + "/status", headers=ctx["auth"]["operator"]).status_code == 200


def test_no_cross_tenant_access(ctx):
    oid = new(ctx)
    c = ctx["client"]
    h = ctx["auth"]["other"]
    assert c.get(path(oid) + "/status", headers=h).status_code == 404
    assert c.post(path(oid) + "/status", headers=h,
                  json={"expected_status": "draft", "to_status": "cancelled"}).status_code == 404
    assert get_history(ctx, oid, who="other").status_code == 404


def test_forged_organization_header_does_not_cross_tenants(ctx):
    oid = new(ctx)
    forged = {**ctx["auth"]["operator"], "X-Organization-ID": str(ctx["ids"]["b"])}
    r = ctx["client"].post(path(oid) + "/status", headers=forged,
                            json={"expected_status": "draft", "to_status": "pending"})
    assert r.status_code == 200
    assert r.json()["event"]["organization_id"] == str(ctx["ids"]["a"])


def test_unauthenticated_401(ctx):
    oid = new(ctx)
    c = ctx["client"]
    assert c.get(path(oid) + "/status").status_code == 401
    assert c.get(path(oid) + "/history").status_code == 401
    assert c.post(path(oid) + "/status", json={"expected_status": "draft", "to_status": "pending"}).status_code == 401


def test_revoked_session_401(ctx):
    oid = new(ctx)
    h = ctx["auth"]["operator"]
    assert ctx["client"].post("/api/v1/auth/logout", headers=h).status_code == 200
    assert ctx["client"].get(path(oid) + "/status", headers=h).status_code == 401
    assert move(ctx, oid, "draft", "pending").status_code == 401


def test_not_found_uuid_404(ctx):
    oid = str(uuid4())
    assert ctx["client"].get(path(oid) + "/status", headers=ctx["auth"]["owner"]).status_code == 404
    assert get_history(ctx, oid, who="owner").status_code == 404
    assert move(ctx, oid, "draft", "pending", who="owner").status_code == 404


@pytest.mark.parametrize("payload", [
    {}, {"expected_status": "draft"}, {"to_status": "pending"},
    {"expected_status": "draft", "to_status": "garbage"},
    {"expected_status": "garbage", "to_status": "pending"},
    {"expected_status": None, "to_status": "pending"},
    {"expected_status": "draft", "to_status": "pending", "note": "z" * 501},
    {"expected_status": "draft", "to_status": "pending", "organization_id": "fake"},
    {"expected_status": "draft", "to_status": "pending", "changed_by_user_id": "fake"},
])
def test_invalid_transition_payload_422(ctx, payload):
    oid = new(ctx)
    r = ctx["client"].post(path(oid) + "/status", headers=ctx["auth"]["owner"], json=payload)
    assert r.status_code == 422, r.text
    assert get_history(ctx, oid).json() == []


@pytest.mark.parametrize("suffix", ["?limit=0", "?limit=101", "?offset=-1", "?limit=-1"])
def test_invalid_history_pagination(ctx, suffix):
    oid = new(ctx)
    assert get_history(ctx, oid, suffix=suffix).status_code == 422


def test_history_pagination_and_dates(ctx):
    oid = new(ctx)
    assert move(ctx, oid, "draft", "pending").status_code == 200
    assert move(ctx, oid, "pending", "draft").status_code == 200
    assert move(ctx, oid, "draft", "pending").status_code == 200
    first = get_history(ctx, oid, suffix="?limit=2&offset=0").json()
    second = get_history(ctx, oid, suffix="?limit=2&offset=2").json()
    assert len(first) == 2 and len(second) == 1
    assert {x["id"] for x in first}.isdisjoint({x["id"] for x in second})


def test_database_rejects_cross_tenant_event(ctx):
    oid = new(ctx)
    with ctx["factory"]() as db:
        db.add(OrderStatusEvent(
            organization_id=ctx["ids"]["a"], order_id=UUID(oid),
            changed_by_user_id=ctx["ids"]["other"],
            from_status="draft", to_status="pending",
        ))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()


def test_database_rejects_invalid_transition_event(ctx):
    oid = new(ctx)
    with ctx["factory"]() as db:
        db.add(OrderStatusEvent(
            organization_id=ctx["ids"]["a"], order_id=UUID(oid),
            changed_by_user_id=ctx["ids"]["operator"],
            from_status="draft", to_status="draft",
        ))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()


def test_status_and_history_persist_in_database(ctx):
    oid = new(ctx)
    assert move(ctx, oid, "draft", "pending", note="  Esperando confirmacion  ").status_code == 200
    with ctx["factory"]() as db:
        saved = db.get(Order, UUID(oid))
        assert saved.status == "pending"
        events = db.scalars(select(OrderStatusEvent).where(OrderStatusEvent.order_id == UUID(oid))).all()
        assert len(events) == 1
        assert events[0].from_status == "draft" and events[0].to_status == "pending"
        assert events[0].note == "Esperando confirmacion"


def test_openapi_documents_status_and_history(ctx):
    data = ctx["client"].get("/openapi.json").json()["paths"]
    assert path("{order_id}") + "/status" in data
    assert path("{order_id}") + "/history" in data
