"""RF-008: prueba real con Neon; evita imprimir informacion sensible."""
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization

BASE = "/api/v1/orders"


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            a = Organization(name="RF008 Test A " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            b = Organization(name="RF008 Test B " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            db.add_all([a, b]); db.flush()
            org_ids = [a.id, b.id]
            create_first_owner(db, organization_id=a.id, email="rf008-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=b.id, email="rf008-owner-b@example.com", password=password)
            db.add(User(organization_id=a.id, email="rf008-operator-a@example.com",
                        role="operator", password_hash=hash_password(password), is_active=True))
            db.commit()

        with TestClient(app) as client:
            def auth(org: UUID, email: str):
                r = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": password,
                })
                assert r.status_code == 200, f"Login: HTTP {r.status_code}"
                return {"Authorization": "Bearer " + r.json()["access_token"]}

            owner_a = auth(org_ids[0], "rf008-owner-a@example.com")
            operator_a = auth(org_ids[0], "rf008-operator-a@example.com")
            owner_b = auth(org_ids[1], "rf008-owner-b@example.com")

            new = client.post(BASE, headers=operator_a,
                              json={"raw_text":"30 playeras estampadas para el viernes"})
            assert new.status_code == 201, f"Crear solicitud HTTP {new.status_code}"
            obj = new.json()
            assert obj["status"] == "draft" and obj["source"] == "manual"
            assert obj["organization_id"] == str(org_ids[0])
            assert obj["created_by_user_id"] and obj["created_at"]
            uri = BASE + "/" + obj["id"]

            with get_session_factory()() as db:
                stored = db.scalar(select(Order).where(
                    Order.id == UUID(obj["id"]), Order.organization_id == org_ids[0]
                ))
                assert stored is not None and stored.raw_text == obj["raw_text"], "No persistio el borrador"

            assert client.get(uri, headers=owner_a).status_code == 200
            assert len(client.get(BASE, headers=owner_a).json()) == 1
            assert len(client.get(BASE, headers=owner_b).json()) == 0
            assert len(client.get(BASE + "?only_mine=true", headers=owner_a).json()) == 0
            assert len(client.get(BASE + "?only_mine=true", headers=operator_a).json()) == 1
            edited = client.patch(uri, headers=operator_a, json={"raw_text":"40 playeras el viernes"})
            assert edited.status_code == 200 and edited.json()["raw_text"] == "40 playeras el viernes"
            assert edited.json()["created_at"] == obj["created_at"]
            assert client.get(uri, headers=owner_b).status_code == 404
            assert client.patch(uri, headers=owner_b, json={"raw_text":"hack"}).status_code == 404
            assert client.post(BASE, headers=operator_a, json={"raw_text":"x", "organization_id":str(org_ids[1])}).status_code == 422
            spoofed = client.post(BASE, headers={**operator_a, "X-Organization-ID":str(org_ids[1])},
                                  json={"raw_text":"Prueba de header"})
            assert spoofed.status_code == 201 and spoofed.json()["organization_id"] == str(org_ids[0])
            assert client.post(BASE, json={"raw_text":"Sin sesion"}).status_code == 401
            assert client.post("/api/v1/auth/logout", headers=operator_a).status_code == 200
            assert client.get(uri, headers=operator_a).status_code == 401
            assert client.get(uri, headers=owner_a).json()["raw_text"] == "40 playeras el viernes"

        print("RF-008 PostgreSQL OK: borrador manual persistido, usuario/tenant/fecha, "
              "edicion, 401/404/422, aislamiento y revocacion verificados.")
    finally:
        if org_ids:
            with get_session_factory()() as db:
                try:
                    for org_id in org_ids:
                        org = db.get(Organization, org_id)
                        if org is not None:
                            db.delete(org)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise


if __name__ == "__main__":
    main()
