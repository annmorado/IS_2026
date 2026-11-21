"""RF-004: pruebas de lectura, escritura, UUID ajenos y revocacion entre tenants."""
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import AuthSession, User
from app.modules.auth.security import JWT_AUDIENCE, JWT_ISSUER, hash_password
from app.modules.organizations.model import Organization

PASSWORD = "Contrasena-Fuerte-Tenant-2026!"
SECRET = "clave-rf004-exclusiva-pruebas-" + ("x" * 70)
# Precomputacion para no penalizar cada prueba con los mismos hashes Argon2.
PREHASH = hash_password(PASSWORD)
BASE = "/api/v1/tenants/me/members"


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="Tenant A", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Tenant B", sector="Imprenta", timezone="America/Mexico_City", currency="MXN")
        db.add_all((a, b)); db.flush()
        a_owner = User(organization_id=a.id, email="owner@a.example", role="owner", password_hash=PREHASH)
        a_op = User(organization_id=a.id, email="operator@a.example", role="operator", password_hash=PREHASH)
        b_owner = User(organization_id=b.id, email="owner@b.example", role="owner", password_hash=PREHASH)
        b_op = User(organization_id=b.id, email="operator@b.example", role="operator", password_hash=PREHASH)
        db.add_all((a_owner, a_op, b_owner, b_op)); db.flush()
        ids = {"a": a.id, "b": b.id, "ao": a_owner.id, "ap": a_op.id, "bo": b_owner.id, "bp": b_op.id}
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            cache = {}

            def token(who: str):
                if who not in cache:
                    info = {
                        "ao": (ids["a"], "owner@a.example"),
                        "ap": (ids["a"], "operator@a.example"),
                        "bo": (ids["b"], "owner@b.example"),
                        "bp": (ids["b"], "operator@b.example"),
                    }[who]
                    res = client.post("/api/v1/auth/login", json={"organization_id": str(info[0]), "email": info[1], "password": PASSWORD})
                    assert res.status_code == 200, res.text
                    cache[who] = res.json()["access_token"]
                return cache[who]

            def headers(who: str):
                return {"Authorization": "Bearer " + token(who)}

            yield {"client": client, "factory": factory, "ids": ids, "token": token, "headers": headers}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_list_only_own_members(ctx):
    r = ctx["client"].get(BASE, headers=ctx["headers"]("ao"))
    assert r.status_code == 200
    assert {x["id"] for x in r.json()} == {str(ctx["ids"]["ao"]), str(ctx["ids"]["ap"])}
    assert "owner@b.example" not in r.text
    assert "password_hash" not in r.text


def test_second_tenant_only_own_members(ctx):
    r = ctx["client"].get(BASE, headers=ctx["headers"]("bo"))
    assert r.status_code == 200
    assert {x["id"] for x in r.json()} == {str(ctx["ids"]["bo"]), str(ctx["ids"]["bp"])}
    assert "owner@a.example" not in r.text


def test_limit_offset_and_validation(ctx):
    h = ctx["headers"]("ao")
    assert len(ctx["client"].get(BASE + "?limit=1",headers=h).json()) == 1
    assert len(ctx["client"].get(BASE + "?limit=1&offset=1",headers=h).json()) == 1
    assert ctx["client"].get(BASE + "?limit=0",headers=h).status_code == 422
    assert ctx["client"].get(BASE + "?limit=101",headers=h).status_code == 422


def test_owner_gets_own_operator(ctx):
    r = ctx["client"].get(BASE + "/" + str(ctx["ids"]["ap"]), headers=ctx["headers"]("ao"))
    assert r.status_code == 200 and r.json()["email"] == "operator@a.example"


def test_cross_tenant_get_matches_missing_404(ctx):
    h = ctx["headers"]("ao")
    cross = ctx["client"].get(BASE + "/" + str(ctx["ids"]["bo"]), headers=h)
    missing = ctx["client"].get(BASE + "/" + str(uuid4()), headers=h)
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()


def test_cross_tenant_patch_is_404_and_no_effect(ctx):
    other = str(ctx["ids"]["bp"])
    r = ctx["client"].patch(BASE + "/" + other + "/status", headers=ctx["headers"]("ao"), json={"is_active": False})
    assert r.status_code == 404
    with ctx["factory"]() as db:
        assert db.get(User, ctx["ids"]["bp"]).is_active is True


def test_cross_tenant_revoke_is_404_and_victim_stays_logged_in(ctx):
    before = ctx["client"].get("/api/v1/auth/me", headers=ctx["headers"]("bp"))
    assert before.status_code == 200
    r = ctx["client"].post(BASE + "/" + str(ctx["ids"]["bp"]) + "/revoke-sessions",headers=ctx["headers"]("ao"))
    assert r.status_code == 404
    assert ctx["client"].get("/api/v1/auth/me", headers=ctx["headers"]("bp")).status_code == 200


def test_owner_status_update_deactivates_and_revokes(ctx):
    client = ctx["client"]
    op_headers = ctx["headers"]("ap")
    assert client.get("/api/v1/auth/me", headers=op_headers).status_code == 200
    r = client.patch(BASE + "/" + str(ctx["ids"]["ap"]) + "/status", headers=ctx["headers"]("ao"), json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=op_headers).status_code == 401
    with ctx["factory"]() as db:
        sessions = db.query(AuthSession).filter(AuthSession.user_id == ctx["ids"]["ap"]).all()
        assert sessions and all(s.revoked_at is not None for s in sessions)


def test_reactivation_does_not_resurrect_old_jwt(ctx):
    client = ctx["client"]
    old = ctx["headers"]("ap")
    p = BASE + "/" + str(ctx["ids"]["ap"]) + "/status"
    assert client.patch(p,headers=ctx["headers"]("ao"),json={"is_active":False}).status_code == 200
    assert client.patch(p,headers=ctx["headers"]("ao"),json={"is_active":True}).status_code == 200
    assert client.get("/api/v1/auth/me",headers=old).status_code == 401
    res = client.post("/api/v1/auth/login", json={"organization_id": str(ctx["ids"]["a"]), "email":"operator@a.example", "password": PASSWORD})
    assert res.status_code == 200
    assert client.get("/api/v1/auth/me",headers={"Authorization":"Bearer "+res.json()["access_token"]}).status_code == 200


def test_owner_can_revoke_operator_sessions(ctx):
    client = ctx["client"]
    active = ctx["headers"]("ap")
    url = BASE + "/" + str(ctx["ids"]["ap"]) + "/revoke-sessions"
    r = client.post(url, headers=ctx["headers"]("ao"))
    assert r.status_code == 200 and r.json()["revoked_count"] >= 1
    assert client.get("/api/v1/auth/me", headers=active).status_code == 401
    again = client.post(url, headers=ctx["headers"]("ao"))
    assert again.status_code == 200 and again.json()["revoked_count"] == 0


def test_owner_cannot_deactivate_owner(ctx):
    r = ctx["client"].patch(BASE + "/" + str(ctx["ids"]["ao"]) + "/status",headers=ctx["headers"]("ao"),json={"is_active":False})
    assert r.status_code == 403


@pytest.mark.parametrize("method,path,payload",[
    ("get","",None),
    ("get","/12345678-1234-1234-1234-123456789abc",None),
    ("patch","/12345678-1234-1234-1234-123456789abc/status",{"is_active":False}),
    ("post","/12345678-1234-1234-1234-123456789abc/revoke-sessions",None),
])
def test_operator_forbidden_for_admin_actions(ctx,method,path,payload):
    r = ctx["client"].request(method.upper(),BASE+path,headers=ctx["headers"]("ap"),json=payload)
    assert r.status_code == 403


@pytest.mark.parametrize("method,path,payload",[
    ("get","",None),
    ("get","/12345678-1234-1234-1234-123456789abc",None),
    ("patch","/12345678-1234-1234-1234-123456789abc/status",{"is_active":False}),
    ("post","/12345678-1234-1234-1234-123456789abc/revoke-sessions",None),
])
def test_missing_token_is_401(ctx,method,path,payload):
    r = ctx["client"].request(method.upper(),BASE+path,json=payload)
    assert r.status_code == 401


def test_reject_extra_fields(ctx):
    r = ctx["client"].patch(BASE+"/"+str(ctx["ids"]["ap"])+"/status",headers=ctx["headers"]("ao"),json={"is_active":False,"organization_id":str(ctx["ids"]["b"])})
    assert r.status_code == 422


def test_reject_missing_status(ctx):
    r = ctx["client"].patch(BASE+"/"+str(ctx["ids"]["ap"])+"/status",headers=ctx["headers"]("ao"),json={})
    assert r.status_code == 422


def test_reject_malformed_uuid(ctx):
    r = ctx["client"].get(BASE+"/no-es-uuid",headers=ctx["headers"]("ao"))
    assert r.status_code == 422


def test_malicious_organization_header_is_ignored(ctx):
    h = {**ctx["headers"]("ao"), "X-Organization-ID": str(ctx["ids"]["b"])}
    r = ctx["client"].get(BASE,headers=h)
    assert r.status_code == 200 and all(row["organization_id"] == str(ctx["ids"]["a"]) for row in r.json())


def test_signed_jwt_with_mismatched_org_is_rejected(ctx):
    token = ctx["token"]("ao")
    claims = jwt.decode(token, SECRET, algorithms=["HS256"],issuer=JWT_ISSUER,audience=JWT_AUDIENCE)
    claims["org"] = str(ctx["ids"]["b"])
    altered = jwt.encode(claims,SECRET,algorithm="HS256")
    h = {"Authorization": "Bearer " + altered}
    assert ctx["client"].get("/api/v1/auth/me",headers=h).status_code == 401
    assert ctx["client"].get(BASE,headers=h).status_code == 401


def test_existent_and_unknown_cross_tenant_get_same_detail(ctx):
    h = ctx["headers"]("bo")
    cross = ctx["client"].get(BASE+"/"+str(ctx["ids"]["ao"]), headers=h)
    unknown = ctx["client"].get(BASE+"/"+str(uuid4()), headers=h)
    assert cross.status_code == unknown.status_code == 404
    assert cross.json() == unknown.json()


def test_existing_organization_policy_remains_scoped(ctx):
    client = ctx["client"]
    h = {**ctx["headers"]("ao"), "X-Organization-ID": str(ctx["ids"]["b"])}
    r = client.patch("/api/v1/organizations/me/policies",headers=h,json={"max_discount_percent":"17.00"})
    assert r.status_code == 200
    assert client.get("/api/v1/organizations/me/policies",headers=ctx["headers"]("bo")).json()["max_discount_percent"] == "0.00"


def test_openapi_includes_scoped_endpoints(ctx):
    paths = ctx["client"].get("/openapi.json").json()["paths"]
    for suffix in ("", "/{user_id}", "/{user_id}/status", "/{user_id}/revoke-sessions"):
        assert BASE + suffix in paths
