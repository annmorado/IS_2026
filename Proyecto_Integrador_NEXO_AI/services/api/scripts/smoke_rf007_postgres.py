"""Prueba integrada RF-007 en Neon; no imprime URLs, JWT, contrasenas ni UUID."""
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.capacity.model import ProductionResource
from app.modules.organizations.model import Organization

BASE = "/api/v1/capacity/resources"
WINDOW = "start_date=2026-11-16&end_date=2026-11-20&requested_units=160"


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            a = Organization(name="RF007 Test A " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            b = Organization(name="RF007 Test B " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            db.add_all([a,b])
            db.flush()
            org_ids = [a.id,b.id]
            create_first_owner(db, organization_id=a.id, email="rf007-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=b.id, email="rf007-owner-b@example.com", password=password)
            db.add(User(organization_id=a.id, email="rf007-operator-a@example.com",
                        password_hash=hash_password(password), role="operator", is_active=True))
            db.commit()

        with TestClient(app) as client:
            def auth(org: UUID, email: str):
                response = client.post("/api/v1/auth/login", json={
                    "organization_id":str(org), "email":email, "password":password,
                })
                assert response.status_code == 200, f"Login: HTTP {response.status_code}"
                return {"Authorization": "Bearer " + response.json()["access_token"]}

            owner_a = auth(org_ids[0], "rf007-owner-a@example.com")
            owner_b = auth(org_ids[1], "rf007-owner-b@example.com")
            operator_a = auth(org_ids[0], "rf007-operator-a@example.com")
            created = client.post(BASE, headers=owner_a, json={
                "code":"RF007-LINEA", "name":"Linea de prueba", "unit":"pieza",
                "daily_capacity":"30.000", "workdays":[0,1,2,3,4],
            })
            assert created.status_code == 201, f"Crear recurso: HTTP {created.status_code}"
            rid = created.json()["id"]
            uri = BASE + "/" + rid
            eval_uri = uri + "/evaluate?" + WINDOW

            baseline = client.get(eval_uri,headers=operator_a)
            assert baseline.status_code == 200, f"Evaluacion: HTTP {baseline.status_code}"
            baseline_data = baseline.json()
            assert baseline_data["gross_capacity"] == "150.000"
            assert baseline_data["shortage"] == "10.000"
            assert baseline_data["minimum_workdays"] == 6
            assert baseline_data["feasible"] is False
            assert baseline_data["includes_existing_commitments"] is False

            with get_session_factory()() as db:
                saved = db.scalar(select(ProductionResource).where(
                    ProductionResource.id == UUID(rid), ProductionResource.organization_id == org_ids[0],
                ))
                assert saved is not None and saved.code == "RF007-LINEA", "Persistencia fallida"

            blackout = client.put(uri + "/blackouts/2026-11-17",headers=owner_a)
            assert blackout.status_code == 200
            reduced = client.get(eval_uri,headers=operator_a)
            assert reduced.status_code == 200 and reduced.json()["gross_capacity"] == "120.000"
            updated = client.patch(uri,headers=owner_a,json={"daily_capacity":"40.000"})
            assert updated.status_code == 200
            new_eval = client.get(eval_uri,headers=operator_a)
            assert new_eval.status_code == 200 and new_eval.json()["gross_capacity"] == "160.000"
            assert new_eval.json()["feasible"] is True

            assert client.get(uri,headers=owner_b).status_code == 404
            assert client.patch(uri,headers=owner_b,json={"daily_capacity":"999.000"}).status_code == 404
            assert client.get(eval_uri,headers=owner_b).status_code == 404
            assert client.patch(uri,headers=operator_a,json={"daily_capacity":"10.000"}).status_code == 403
            assert client.get(eval_uri).status_code == 401
            assert client.get(eval_uri,headers={**operator_a, "X-Organization-ID":str(org_ids[1])}).status_code == 200
            assert client.post("/api/v1/auth/logout", headers=operator_a).status_code == 200
            assert client.get(eval_uri,headers=operator_a).status_code == 401
            assert client.post(uri + "/deactivate", headers=owner_a).status_code == 200
            assert client.get(eval_uri,headers=owner_a).status_code == 409

        print("RF-007 PostgreSQL OK: 30 x 5 = 150, solicitud 160 (faltante 10, 6 dias), "
              "calendario, recálculo, permisos 401/403/404, revocacion y tenants verificados.")
    finally:
        if org_ids:
            with get_session_factory()() as db:
                try:
                    for oid in org_ids:
                        org = db.get(Organization, oid)
                        if org is not None:
                            db.delete(org)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise


if __name__ == "__main__":
    main()
