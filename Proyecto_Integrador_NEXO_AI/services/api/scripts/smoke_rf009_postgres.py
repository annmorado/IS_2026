"""RF-009: verificaciones reales de Neon, sin publicar archivos ni tokens."""
import hashlib
import os
from secrets import token_urlsafe
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.voice_notes.model import VoiceNote
from app.modules.voice_notes.service import private_path

AUDIO = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A \x00\x00\x00\x08free"
BASE = "/api/v1/voice-notes"


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(24)
    original_storage = os.environ.get("NEXO_VOICE_STORAGE_DIR")
    with TemporaryDirectory(prefix="nexo-rf009-smoke-") as private_dir:
        os.environ["NEXO_VOICE_STORAGE_DIR"] = private_dir
        try:
            with get_session_factory()() as db:
                a = Organization(name="RF009 Test A " + uuid4().hex[:8], sector="Pruebas",
                                 timezone="America/Mexico_City", currency="MXN")
                b = Organization(name="RF009 Test B " + uuid4().hex[:8], sector="Pruebas",
                                 timezone="America/Mexico_City", currency="MXN")
                db.add_all((a,b)); db.flush()
                org_ids = [a.id,b.id]
                create_first_owner(db, organization_id=a.id, email="rf009-owner-a@example.com", password=password)
                create_first_owner(db, organization_id=b.id, email="rf009-owner-b@example.com", password=password)
                db.add(User(organization_id=a.id,email="rf009-operator-a@example.com",role="operator",
                            password_hash=hash_password(password),is_active=True))
                db.commit()

            with TestClient(app) as client:
                def auth(org: UUID, email: str):
                    r = client.post("/api/v1/auth/login",json={"organization_id":str(org),
                              "email":email,"password":password})
                    assert r.status_code == 200, f"Login HTTP {r.status_code}"
                    return {"Authorization":"Bearer "+r.json()["access_token"]}

                owner_a = auth(org_ids[0],"rf009-owner-a@example.com")
                operator_a = auth(org_ids[0],"rf009-operator-a@example.com")
                owner_b = auth(org_ids[1],"rf009-owner-b@example.com")
                r = client.post(BASE, headers=operator_a,
                         files={"file":("grabacion.m4a",AUDIO,"audio/mp4")},
                         data={"duration_ms":"1200"})
                assert r.status_code == 201, f"Carga HTTP {r.status_code}: {r.text[:200]}"
                item = r.json()
                assert item["organization_id"] == str(org_ids[0])
                assert item["byte_size"] == len(AUDIO) and item["duration_ms"] == 1200
                assert item["sha256_hex"] == hashlib.sha256(AUDIO).hexdigest()
                path = private_path(org_ids[0], UUID(item["id"]))
                assert path.is_file() and path.read_bytes() == AUDIO
                with get_session_factory()() as db:
                    stored = db.scalar(select(VoiceNote).where(VoiceNote.id == UUID(item["id"]),
                                                              VoiceNote.organization_id == org_ids[0]))
                    assert stored and stored.sha256_hex == item["sha256_hex"]
                url = BASE + "/" + item["id"]
                assert client.get(url,headers=owner_a).status_code == 200
                assert client.get(url+"/file",headers=owner_a).content == AUDIO
                assert len(client.get(BASE,headers=owner_a).json()) == 1
                assert len(client.get(BASE,headers=owner_b).json()) == 0
                assert client.get(url,headers=owner_b).status_code == 404
                assert client.get(url+"/file",headers=owner_b).status_code == 404
                assert client.get(url+"/file").status_code == 401
                assert client.post(BASE,headers=owner_a,
                           files={"file":("fake.m4a",b"fake","audio/mp4")}).status_code == 415
                assert client.post(BASE,headers=owner_a,
                           files={"file":("fake.mp3",b"fake","audio/mpeg")}).status_code == 415
                assert client.post("/api/v1/auth/logout",headers=operator_a).status_code == 200
                assert client.get(url,headers=operator_a).status_code == 401
                # La captura por texto sigue disponible para un microfono denegado.
                fallback = client.post("/api/v1/orders",headers=owner_a,
                                       json={"raw_text":"Solicitud por texto sin microfono"})
                assert fallback.status_code == 201 and fallback.json()["status"] == "draft"
            print("RF-009 PostgreSQL OK: carga M4A privada, metadatos, descarga, 401/404/415, "
                  "aislamiento, revocacion y alternativa por texto verificados.")
        finally:
            if org_ids:
                with get_session_factory()() as db:
                    try:
                        for org_id in org_ids:
                            org = db.get(Organization,org_id)
                            if org is not None:
                                db.delete(org)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
            if original_storage is None:
                os.environ.pop("NEXO_VOICE_STORAGE_DIR",None)
            else:
                os.environ["NEXO_VOICE_STORAGE_DIR"] = original_storage


if __name__ == "__main__":
    main()
