"""RF-010: revision humana obligatoria, permisos, concurrencia y persistencia."""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User, AuthSession  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.review.service import stage_suggested_extraction
from app.modules.tenancy.scope import TenantScope

PASSWORD = "RF010-Contrasena-Muy-Segura!"
SECRET = "test-secret-rf010-" + "X" * 70
HASH = hash_password(PASSWORD)
BASE_URL = "/api/v1/orders"


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(dbapi, _):
        dbapi.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="RF010 Alfa", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="RF010 Beta", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        users = [
            User(organization_id=a.id, email="owner-a@rf010.example", role="owner", password_hash=HASH),
            User(organization_id=a.id, email="operator-a@rf010.example", role="operator", password_hash=HASH),
            User(organization_id=a.id, email="operator2-a@rf010.example", role="operator", password_hash=HASH),
            User(organization_id=b.id, email="owner-b@rf010.example", role="owner", password_hash=HASH),
        ]
        db.add_all(users); db.flush()
        ids = {"a":a.id, "b":b.id, "owner":users[0].id, "operator":users[1].id,
               "operator2":users[2].id, "other":users[3].id}
        db.commit()

    def override():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as c:
            headers = {}
            for who, email, org in [
                ("owner", "owner-a@rf010.example",ids["a"]),
                ("operator", "operator-a@rf010.example",ids["a"]),
                ("operator2", "operator2-a@rf010.example",ids["a"]),
                ("other", "owner-b@rf010.example",ids["b"]),
            ]:
                r = c.post("/api/v1/auth/login", json={
                    "organization_id":str(org),"email":email,"password":PASSWORD})
                assert r.status_code==200, r.text
                headers[who]={"Authorization":"Bearer "+r.json()["access_token"]}
            yield {"client":c,"factory":factory,"headers":headers,"ids":ids}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def new(ctx, who="operator", text="30 camisetas para el viernes"):
    r=ctx["client"].post(BASE_URL, headers=ctx["headers"][who], json={"raw_text":text})
    assert r.status_code==201, r.text
    return r.json()


def review_url(order): return BASE_URL+"/"+order["id"]+"/review"
def confirm_url(order): return BASE_URL+"/"+order["id"]+"/confirm"

def save(ctx, order, who="operator", quantity="35.000", due="2026-12-19", rev=0):
    return ctx["client"].put(review_url(order), headers=ctx["headers"][who],json={
        "quantity":quantity,"due_date":due,"expected_revision":rev})

def confirm(ctx,order,who="operator",rev=1):
    return ctx["client"].post(confirm_url(order),headers=ctx["headers"][who],json={"expected_revision":rev})


def test_review_preview_starts_empty(ctx):
    order=new(ctx)
    r=ctx["client"].get(review_url(order),headers=ctx["headers"]["owner"])
    assert r.status_code==200
    body=r.json()
    assert body["raw_text"]==order["raw_text"]
    assert body["status"]=="draft" and body["requires_manual_review"] is True
    assert body["reviewed_quantity"] is None and body["suggested_quantity"] is None
    assert body["review_revision"]==0


def test_complete_review_confirm_persists_only_corrected_values(ctx):
    order=new(ctx, text="El sistema calculo 30 unidades entrega 2026-12-01")
    with ctx["factory"]() as db:
        scope=TenantScope(organization_id=ctx["ids"]["a"], actor_id=ctx["ids"]["operator"])
        stage_suggested_extraction(db,scope,UUID(order["id"]),quantity=Decimal("30.000"),due_date=date(2026,12,1))
    preview=ctx["client"].get(review_url(order),headers=ctx["headers"]["operator"]).json()
    assert preview["suggested_quantity"]=="30.000"
    assert preview["suggested_due_date"]=="2026-12-01" and preview["review_revision"]==1
    assert preview["reviewed_quantity"] is None
    reviewed=save(ctx,order,quantity="40.500",due="2026-12-10",rev=1)
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()["reviewed_quantity"]=="40.500"
    assert reviewed.json()["suggested_quantity"]=="30.000"
    confirmed=confirm(ctx,order,rev=reviewed.json()["review_revision"])
    assert confirmed.status_code==200, confirmed.text
    data=confirmed.json()
    assert data["status"]=="confirmed" and data["requires_manual_review"] is False
    assert data["reviewed_quantity"]=="40.500" and data["reviewed_due_date"]=="2026-12-10"
    assert data["confirmed_by_user_id"]==str(ctx["ids"]["operator"])
    assert data["confirmed_at"] is not None and data["reviewed_at"] is not None
    with ctx["factory"]() as db:
        persisted=db.get(Order,UUID(order["id"]))
        assert persisted.raw_text.startswith("El sistema calculo 30")
        assert persisted.suggested_quantity==Decimal("30.000")
        assert persisted.reviewed_quantity==Decimal("40.500")
        assert persisted.reviewed_due_date==date(2026,12,10)
        assert persisted.status=="confirmed"


def test_cannot_confirm_without_saved_review(ctx):
    order=new(ctx)
    assert confirm(ctx,order,rev=1).status_code==409
    assert ctx["client"].get(BASE_URL+"/"+order["id"],headers=ctx["headers"]["operator"]).json()["status"]=="draft"


def test_cannot_confirm_immediately_in_create_payload(ctx):
    r=ctx["client"].post(BASE_URL, headers=ctx["headers"]["owner"],
                         json={"raw_text":"30", "status":"confirmed", "reviewed_quantity":"30"})
    assert r.status_code==422


def test_save_then_explicit_confirm_required(ctx):
    order=new(ctx)
    assert save(ctx,order).status_code==200
    assert ctx["client"].get(review_url(order),headers=ctx["headers"]["operator"]).json()["status"]=="draft"


def test_operator_can_review_own(ctx):
    order=new(ctx)
    assert save(ctx,order).status_code==200


def test_owner_can_review_other_operators(ctx):
    order=new(ctx)
    assert save(ctx,order,who="owner").status_code==200
    assert confirm(ctx,order,who="owner").status_code==200


def test_operator_cannot_review_other_operators(ctx):
    order=new(ctx,who="operator2")
    assert save(ctx,order,who="operator").status_code==403
    assert confirm(ctx,order,who="operator").status_code==403
    assert ctx["client"].get(review_url(order),headers=ctx["headers"]["operator"]).status_code==200


def test_other_org_cannot_read_or_review_or_confirm(ctx):
    order=new(ctx)
    assert ctx["client"].get(review_url(order),headers=ctx["headers"]["other"]).status_code==404
    assert save(ctx,order,who="other").status_code==404
    assert confirm(ctx,order,who="other").status_code==404


def test_nonexisting_order_is_404(ctx):
    order={"id":str(uuid4())}
    assert ctx["client"].get(review_url(order),headers=ctx["headers"]["owner"]).status_code==404
    assert save(ctx,order,who="owner").status_code==404
    assert confirm(ctx,order,who="owner").status_code==404


def test_revision_conflicts_on_save_and_confirm(ctx):
    order=new(ctx)
    assert save(ctx,order,rev=5).status_code==409
    assert save(ctx,order).status_code==200
    assert save(ctx,order,rev=0).status_code==409
    assert confirm(ctx,order,rev=2).status_code==409
    assert confirm(ctx,order,rev=1).status_code==200


def test_review_can_be_corrected_twice(ctx):
    order=new(ctx)
    assert save(ctx,order,quantity="2",rev=0).status_code==200
    assert save(ctx,order,quantity="9",rev=1).status_code==200
    assert confirm(ctx,order,rev=2).json()["reviewed_quantity"]=="9.000"


def test_edit_raw_text_invalidates_review(ctx):
    order=new(ctx)
    assert save(ctx,order).status_code==200
    r=ctx["client"].patch(BASE_URL+"/"+order["id"],headers=ctx["headers"]["operator"],
                         json={"raw_text":"Se corrigio el texto"})
    assert r.status_code==200 and r.json()["review_revision"]==2
    preview=ctx["client"].get(review_url(order),headers=ctx["headers"]["operator"]).json()
    assert preview["reviewed_quantity"] is None and preview["reviewed_due_date"] is None
    assert confirm(ctx,order,rev=2).status_code==409
    assert save(ctx,order,rev=2).status_code==200
    assert confirm(ctx,order,rev=3).status_code==200


def test_new_candidate_invalidates_previous_review(ctx):
    order=new(ctx)
    assert save(ctx,order).status_code==200
    with ctx["factory"]() as db:
        scope=TenantScope(organization_id=ctx["ids"]["a"],actor_id=ctx["ids"]["owner"])
        d=stage_suggested_extraction(db,scope,UUID(order["id"]),quantity=Decimal("10"),due_date=date(2026,12,1))
        assert d.review_revision==2 and d.reviewed_quantity is None
    assert confirm(ctx,order,rev=1).status_code==409


def test_confirmed_cannot_be_edited_or_reconfirmed(ctx):
    order=new(ctx)
    assert save(ctx,order).status_code==200
    assert confirm(ctx,order).status_code==200
    assert save(ctx,order,rev=1).status_code==409
    assert confirm(ctx,order,rev=1).status_code==409
    assert ctx["client"].patch(BASE_URL+"/"+order["id"], headers=ctx["headers"]["owner"],
                                json={"raw_text":"Hack"}).status_code==409


@pytest.mark.parametrize("invalid", [
    "0", "-1", "1234567890123", "1.0001", "NaN", "Infinity", "invalid", None,
])
def test_invalid_quantity_rejected(ctx,invalid):
    order=new(ctx)
    r=save(ctx,order,quantity=invalid)
    assert r.status_code==422, r.text


@pytest.mark.parametrize("invalid", [
    "", "2026-99-01", "tomorrow", "2026-02-30", "2026/12/05", "2026-12-01T08:00:00Z", None,
])
def test_invalid_due_date_rejected(ctx,invalid):
    order=new(ctx)
    assert save(ctx,order,due=invalid).status_code==422


@pytest.mark.parametrize("payload", [
    {}, {"quantity":"10","due_date":"2026-12-10"},
    {"quantity":"10","due_date":"2026-12-10","expected_revision":True},
    {"quantity":"10","due_date":"2026-12-10","expected_revision":-1},
    {"quantity":"10","due_date":"2026-12-10","expected_revision":0,"status":"confirmed"},
    {"quantity":"10","due_date":"2026-12-10","expected_revision":0,"organization_id":"x"},
    {"quantity":"10","due_date":"2026-12-10","expected_revision":0,"reviewed_by_user_id":"x"},
])
def test_bad_review_payload_rejected(ctx,payload):
    order=new(ctx)
    assert ctx["client"].put(review_url(order),headers=ctx["headers"]["operator"],json=payload).status_code==422


@pytest.mark.parametrize("payload", [
    {}, {"expected_revision":0}, {"expected_revision":True},
    {"expected_revision":-1}, {"expected_revision":1,"status":"confirmed"},
])
def test_bad_confirm_payload_rejected(ctx,payload):
    order=new(ctx)
    assert ctx["client"].post(confirm_url(order),headers=ctx["headers"]["operator"],json=payload).status_code==422


@pytest.mark.parametrize("method,route,data", [
    ("get","review",None),("put","review",{"quantity":"10","due_date":"2026-12-10","expected_revision":0}),
    ("post","confirm",{"expected_revision":1}),
])
def test_no_token_401(ctx,method,route,data):
    order=new(ctx)
    endpoint=(confirm_url(order) if route=="confirm" else review_url(order))
    assert ctx["client"].request(method,endpoint,json=data).status_code==401


def test_revoked_token_401(ctx):
    order=new(ctx)
    h=ctx["headers"]["operator"]
    assert ctx["client"].post('/api/v1/auth/logout',headers=h).status_code==200
    assert ctx["client"].get(review_url(order),headers=h).status_code==401
    assert save(ctx,order).status_code==401


def test_cannot_spoof_tenant_by_header(ctx):
    order=new(ctx)
    hdr={**ctx["headers"]["operator"],"X-Organization-ID":str(ctx["ids"]["b"])}
    r=ctx["client"].put(review_url(order),headers=hdr,json={"quantity":"21","due_date":"2026-12-11","expected_revision":0})
    assert r.status_code==200 and r.json()["organization_id"]==str(ctx["ids"]["a"])


def test_database_rejects_cross_tenant_reviewer(ctx):
    order=new(ctx)
    with ctx["factory"]() as db:
        entity=db.get(Order,UUID(order["id"]))
        entity.reviewed_quantity=Decimal("9")
        entity.reviewed_due_date=date(2026,12,9)
        entity.reviewed_by_user_id=ctx["ids"]["other"]
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()


def test_database_rejects_unreviewed_confirmed(ctx):
    order=new(ctx)
    with ctx["factory"]() as db:
        entity=db.get(Order,UUID(order["id"]))
        entity.status="confirmed"
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()


def test_internal_suggestion_never_confirms(ctx):
    order=new(ctx)
    with ctx["factory"]() as db:
        scope=TenantScope(organization_id=ctx["ids"]["a"],actor_id=ctx["ids"]["operator"])
        stage_suggested_extraction(db,scope,UUID(order["id"]),quantity=Decimal("40"),due_date=date(2026,12,3))
    assert confirm(ctx,order,rev=1).status_code==409


def test_service_rejects_invalid_suggestions(ctx):
    order=new(ctx)
    scope=TenantScope(organization_id=ctx["ids"]["a"],actor_id=ctx["ids"]["operator"])
    with ctx["factory"]() as db:
        with pytest.raises(ValueError):
            stage_suggested_extraction(db,scope,UUID(order["id"]),quantity=Decimal("0"),due_date=None)
        with pytest.raises(ValueError):
            stage_suggested_extraction(db,scope,UUID(order["id"]),quantity=Decimal("NaN"),due_date=None)


def test_openapi_includes_review_confirm_endpoints(ctx):
    paths=ctx["client"].get('/openapi.json').json()['paths']
    assert BASE_URL+'/{order_id}/review' in paths
    assert BASE_URL+'/{order_id}/confirm' in paths
