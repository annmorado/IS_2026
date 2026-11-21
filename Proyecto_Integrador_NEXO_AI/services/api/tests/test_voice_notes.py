"""RF-009: multipart M4A, permisos, tamano y segregacion de audio por tenant."""
import hashlib
from pathlib import Path
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
from app.modules.auth.model import AuthSession, User  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.organizations.model import Organization
from app.modules.voice_notes.model import VoiceNote
from app.modules.voice_notes.service import private_path, storage_root

PASSWORD = "RF009-Audio-SuperPassword-2026!"
SECRET = "clave-rf009-solo-pruebas-" + "s" * 80
HASH = hash_password(PASSWORD)
AUDIO = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A \x00\x00\x00\x08free"
BASE_URL = "/api/v1/voice-notes"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    monkeypatch.setenv("NEXO_VOICE_STORAGE_DIR", str(tmp_path / "private_audio"))
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        a = Organization(name="A RF009", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="B RF009", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        db.add_all([a, b]); db.flush()
        ao = User(organization_id=a.id, role="owner", email="ao@rf009.example", password_hash=HASH)
        ap = User(organization_id=a.id, role="operator", email="ap@rf009.example", password_hash=HASH)
        bo = User(organization_id=b.id, role="owner", email="bo@rf009.example", password_hash=HASH)
        db.add_all([ao, ap, bo]); db.flush()
        ids = {"a": a.id, "b": b.id, "ao": ao.id, "ap": ap.id, "bo": bo.id}
        db.commit()

    def override_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def login(who):
                oid = ids["b"] if who == "bo" else ids["a"]
                response = client.post("/api/v1/auth/login", json={
                    "email": who + "@rf009.example", "organization_id": str(oid), "password": PASSWORD,
                })
                assert response.status_code == 200, response.text
                return {"Authorization": "Bearer " + response.json()["access_token"]}
            yield {"client": client, "factory": factory, "ids": ids, "ao": login("ao"),
                   "ap": login("ap"), "bo": login("bo"), "storage": tmp_path / "private_audio"}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def upload(env, headers=None, *, audio=AUDIO, mime="audio/mp4", filename="recording.m4a", data=None):
    return env["client"].post(
        BASE_URL, headers=headers or env["ao"],
        files={"file": (filename, audio, mime)}, data={"duration_ms": "1337"} if data is None else data,
    )


def test_upload_owner_persists_and_returns_safe_metadata(env):
    response = upload(env)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization_id"] == str(env["ids"]["a"])
    assert body["created_by_user_id"] == str(env["ids"]["ao"])
    assert body["duration_ms"] == 1337
    assert body["byte_size"] == len(AUDIO)
    assert body["sha256_hex"] == hashlib.sha256(AUDIO).hexdigest()
    assert "created_at" in body
    assert "storage" not in response.text and "private_audio" not in response.text
    with env["factory"]() as db:
        assert db.get(VoiceNote, UUID(body["id"])) is not None
    assert private_path(env["ids"]["a"], UUID(body["id"])).read_bytes() == AUDIO


def test_operator_can_upload_and_owner_can_view(env):
    response = upload(env, env["ap"])
    assert response.status_code == 201
    assert response.json()["created_by_user_id"] == str(env["ids"]["ap"])
    note_id = response.json()["id"]
    assert env["client"].get(BASE_URL + "/" + note_id, headers=env["ao"]).status_code == 200


def test_download_authenticated_file_and_headers(env):
    note_id = upload(env).json()["id"]
    response = env["client"].get(BASE_URL + "/" + note_id + "/file", headers=env["ap"])
    assert response.status_code == 200, response.text
    assert response.content == AUDIO
    assert response.headers["content-type"].startswith("audio/mp4")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment")


def test_list_is_tenant_scoped(env):
    a = upload(env, env["ao"]).json()["id"]
    b = upload(env, env["bo"]).json()["id"]
    aa = env["client"].get(BASE_URL, headers=env["ap"])
    bb = env["client"].get(BASE_URL, headers=env["bo"])
    assert aa.status_code == bb.status_code == 200
    assert [x["id"] for x in aa.json()] == [a]
    assert [x["id"] for x in bb.json()] == [b]


def test_only_mine(env):
    a = upload(env, env["ao"]).json()["id"]
    b = upload(env, env["ap"]).json()["id"]
    mine = env["client"].get(BASE_URL + "?only_mine=true", headers=env["ap"])
    assert [item["id"] for item in mine.json()] == [b]
    assert a not in mine.text


def test_cross_tenant_metadata_404_matches_missing(env):
    note_id = upload(env, env["bo"]).json()["id"]
    other = env["client"].get(BASE_URL + "/" + note_id, headers=env["ao"])
    missing = env["client"].get(BASE_URL + "/" + str(uuid4()), headers=env["ao"])
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


def test_cross_tenant_file_404(env):
    note_id = upload(env, env["bo"]).json()["id"]
    assert env["client"].get(BASE_URL + "/" + note_id + "/file", headers=env["ao"]).status_code == 404


def test_unauthenticated_list_401(env):
    assert env["client"].get(BASE_URL).status_code == 401


def test_unauthenticated_create_401(env):
    r = env["client"].post(BASE_URL, files={"file": ("test.m4a", AUDIO, "audio/mp4")})
    assert r.status_code == 401
    assert not list(env["storage"].rglob("*.m4a"))


def test_unauthenticated_download_401(env):
    note_id = upload(env).json()["id"]
    assert env["client"].get(BASE_URL + "/" + note_id + "/file").status_code == 401


def test_logout_rejects_upload(env):
    headers = env["ap"]
    assert env["client"].post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert upload(env, headers).status_code == 401


def test_wrong_mime_415(env):
    response = upload(env, mime="audio/mpeg")
    assert response.status_code == 415
    assert not list(env["storage"].rglob("*.m4a"))


def test_invalid_binary_415(env):
    response = upload(env, audio=b"falso M4A")
    assert response.status_code == 415
    assert not list(env["storage"].rglob("*.m4a"))


def test_empty_422(env):
    assert upload(env, audio=b"").status_code == 422


def test_oversized_413_and_cleaned(env):
    oversized = AUDIO + b"0" * (10 * 1024 * 1024 + 1)
    response = upload(env, audio=oversized)
    assert response.status_code == 413
    assert not list(env["storage"].rglob("*.m4a"))
    assert not list(env["storage"].rglob("*.part"))


@pytest.mark.parametrize("duration", ["-1", "3600001", "abc", "1.1"])
def test_invalid_duration_422(env, duration):
    assert upload(env, data={"duration_ms": duration}).status_code == 422


def test_duration_optional(env):
    result = upload(env, data={})
    assert result.status_code == 201
    assert result.json()["duration_ms"] is None


def test_same_filename_does_not_overwrite(env):
    a = upload(env).json()["id"]
    b = upload(env).json()["id"]
    assert a != b
    assert private_path(env["ids"]["a"], UUID(a)).is_file()
    assert private_path(env["ids"]["a"], UUID(b)).is_file()


def test_filename_traversal_is_not_used(env):
    result = upload(env, filename="../../escape.m4a")
    assert result.status_code == 201
    assert private_path(env["ids"]["a"], UUID(result.json()["id"])).is_file()
    assert not (env["storage"].parent / "escape.m4a").exists()


def test_header_cannot_switch_tenant(env):
    note = upload(env, headers={**env["ap"], "X-Organization-ID": str(env["ids"]["b"])})
    assert note.status_code == 201
    assert note.json()["organization_id"] == str(env["ids"]["a"])


def test_list_pagination_validation(env):
    upload(env)
    assert len(env["client"].get(BASE_URL + "?limit=1", headers=env["ao"]).json()) == 1
    assert env["client"].get(BASE_URL + "?limit=0", headers=env["ao"]).status_code == 422
    assert env["client"].get(BASE_URL + "?offset=-1", headers=env["ao"]).status_code == 422


def test_cross_tenant_author_fk_rejects_db_insert(env):
    with env["factory"]() as db:
        note = VoiceNote(id=uuid4(), organization_id=env["ids"]["a"],
             created_by_user_id=env["ids"]["bo"], byte_size=20,
             sha256_hex="a" * 64)
        db.add(note)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_missing_file_gives_404(env):
    voice = upload(env).json()["id"]
    private_path(env["ids"]["a"], UUID(voice)).unlink()
    assert env["client"].get(BASE_URL + "/" + voice + "/file", headers=env["ao"]).status_code == 404


def test_openapi_contains_voice_routes(env):
    paths = env["client"].get("/openapi.json").json()["paths"]
    assert BASE_URL in paths
    assert BASE_URL + "/{note_id}" in paths
    assert BASE_URL + "/{note_id}/file" in paths
