"""Prueba aislada en Neon: dos negocios, lectura/escritura cruzada, revocacion."""
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.organizations.model import Organization

BASE = "/api/v1/tenants/me/members"


def main() -> None:
    ids: list[UUID] = []
    password = token_urlsafe(25)
    with get_session_factory()() as db:
        try:
            org_a = Organization(name="RF004 Smoke A " + uuid4().hex[:8], sector="Pruebas", timezone="America/Mexico_City", currency="MXN")
            org_b = Organization(name="RF004 Smoke B " + uuid4().hex[:8], sector="Pruebas", timezone="America/Mexico_City", currency="MXN")
            db.add_all((org_a,org_b)); db.flush()
            ids = [org_a.id, org_b.id]
            pwd_hash = hash_password(password)
            users = [
                User(organization_id=org_a.id,email="rf004-ownera@example.com",password_hash=pwd_hash,role="owner"),
                User(organization_id=org_a.id,email="rf004-operatora@example.com",password_hash=pwd_hash,role="operator"),
                User(organization_id=org_b.id,email="rf004-ownerb@example.com",password_hash=pwd_hash,role="owner"),
            ]
            db.add_all(users); db.flush()
            owner_a, operator_a, owner_b = [u.id for u in users]
            db.commit()
        except Exception:
            db.rollback()
            raise

    try:
        with TestClient(app) as client:
            def login(email: str, org: UUID):
                res = client.post("/api/v1/auth/login",json={"organization_id":str(org),"email":email,"password":password})
                assert res.status_code == 200, f"Login HTTP {res.status_code}"
                return {"Authorization":"Bearer "+res.json()["access_token"]}

            ha=login("rf004-ownera@example.com",ids[0]); hb=login("rf004-ownerb@example.com",ids[1]); hop=login("rf004-operatora@example.com",ids[0])
            a_list=client.get(BASE,headers=ha)
            assert a_list.status_code == 200
            assert {row["id"] for row in a_list.json()} == {str(owner_a),str(operator_a)}
            assert client.get(BASE,headers=hop).status_code == 403
            assert client.get(BASE+"/"+str(owner_b),headers=ha).status_code == 404
            assert client.patch(BASE+"/"+str(owner_b)+"/status",headers=ha,json={"is_active":False}).status_code == 404
            assert client.post(BASE+"/"+str(owner_b)+"/revoke-sessions",headers=ha).status_code == 404
            assert client.get("/api/v1/auth/me",headers=hb).status_code == 200
            patch=client.patch(BASE+"/"+str(operator_a)+"/status",headers=ha,json={"is_active":False})
            assert patch.status_code == 200 and patch.json()["is_active"] is False
            assert client.get("/api/v1/auth/me",headers=hop).status_code == 401
            assert client.patch(BASE+"/"+str(operator_a)+"/status",headers=ha,json={"is_active":True}).status_code == 200
            assert client.get("/api/v1/auth/me",headers=hop).status_code == 401
            assert client.get(BASE,headers={**ha,"X-Organization-ID":str(ids[1])}).status_code == 200
            assert client.get("/api/v1/auth/me",headers=hb).status_code == 200
        print("RF-004 PostgreSQL OK: tenant A/B aislados, UUID ajenos 404, operador 403, revocacion 401, lectura/escritura verificadas.")
    finally:
        # Borrar SOLO las organizaciones temporales creadas por esta prueba.
        # Un fallo de red puede requerir volver a ejecutar la limpieza manualmente.
        with get_session_factory()() as db:
            for org_id in ids:
                obj=db.get(Organization,org_id)
                if obj is not None:
                    db.delete(obj)
            db.commit()


if __name__ == "__main__":
    main()
