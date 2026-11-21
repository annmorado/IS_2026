"""RF-005: integracion real PostgreSQL con limpieza de organizaciones de prueba."""
from secrets import token_urlsafe
from time import sleep
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization


ROOT = "/api/v1/products"


def _cleanup(organization_ids: list[UUID]) -> None:
    for oid in organization_ids:
        # Si Neon interrumpe una sesion, una transaccion nueva puede permitir limpiar.
        for attempt in range(3):
            try:
                with get_session_factory()() as db:
                    organization = db.get(Organization, oid)
                    if organization is not None:
                        db.delete(organization)
                        db.commit()
                break
            except SQLAlchemyError:
                if attempt == 2:
                    print(f"AVISO: revisar y eliminar organizacion temporal {oid} en Neon")
                    raise
                sleep(1)


def main() -> None:
    organization_ids: list[UUID] = []
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            try:
                a = Organization(
                    name="RF005 Catalog A " + uuid4().hex[:8],
                    sector="Pruebas", timezone="America/Mexico_City", currency="MXN",
                )
                b = Organization(
                    name="RF005 Catalog B " + uuid4().hex[:8],
                    sector="Pruebas", timezone="America/Mexico_City", currency="MXN",
                )
                db.add_all([a, b]); db.flush()
                organization_ids = [a.id, b.id]
                create_first_owner(db, organization_id=a.id, email="rf005-owner-a@example.com", password=password)
                create_first_owner(db, organization_id=b.id, email="rf005-owner-b@example.com", password=password)
                db.add(User(
                    organization_id=a.id, email="rf005-operator@example.com",
                    role="operator", is_active=True, password_hash=hash_password(password),
                ))
                db.commit()
            except Exception:
                db.rollback()
                raise

        with TestClient(app) as client:
            def auth(email: str, org: UUID) -> dict[str, str]:
                res = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": password,
                })
                assert res.status_code == 200, f"Login fallido: HTTP {res.status_code}"
                return {"Authorization": "Bearer " + res.json()["access_token"]}

            owner_a = auth("rf005-owner-a@example.com", organization_ids[0])
            owner_b = auth("rf005-owner-b@example.com", organization_ids[1])
            operator = auth("rf005-operator@example.com", organization_ids[0])
            data = {
                "sku": "SKU-RF005", "name": "Playera de prueba", "unit": "pieza",
                "description": "Impresion por pedido", "cost_mxn": "25.50",
                "price_mxn": "50.00", "base_production_minutes": "12.50",
            }
            created = client.post(ROOT, headers=owner_a, json=data)
            assert created.status_code == 201, f"Creacion fallida: HTTP {created.status_code}"
            pid = created.json()["id"]
            assert created.json()["cost_mxn"] == "25.50"
            assert created.json()["price_mxn"] == "50.00"
            assert created.json()["base_production_minutes"] == "12.50"
            assert client.get(ROOT + "/" + pid, headers=owner_a).status_code == 200
            assert client.patch(ROOT + "/" + pid,headers=owner_a,json={"price_mxn":"55.75"}).json()["price_mxn"] == "55.75"
            assert client.post(ROOT, headers=owner_a, json=data).status_code == 409
            other_create = client.post(ROOT, headers=owner_b, json=data)
            assert other_create.status_code == 201, f"SKU permitido en otro tenant: HTTP {other_create.status_code}"
            assert client.post(ROOT, headers=operator, json=data).status_code == 403
            assert client.patch(ROOT + "/" + pid,headers=operator,json={"name":"No"}).status_code == 403
            assert client.get(ROOT,headers=operator).status_code == 200
            assert client.get(ROOT + "/" + pid, headers=owner_b).status_code == 404
            assert client.patch(ROOT + "/" + pid,headers=owner_b,json={"name":"No"}).status_code == 404
            assert client.post(ROOT + "/" + pid + "/deactivate", headers=owner_b).status_code == 404
            assert all(p["organization_id"] == str(organization_ids[1]) for p in client.get(ROOT, headers=owner_b).json())
            forged_header = {**owner_a, "X-Organization-ID": str(organization_ids[1])}
            assert client.get(ROOT + "/" + other_create.json()["id"],headers=forged_header).status_code == 404
            assert any(p["id"] == pid for p in client.get(ROOT + "/quotable",headers=owner_a).json())
            inactive = client.post(ROOT + "/" + pid + "/deactivate",headers=owner_a)
            assert inactive.status_code == 200 and not inactive.json()["is_active"]
            assert all(p["id"] != pid for p in client.get(ROOT + "/quotable",headers=owner_a).json())
            assert any(p["id"] == pid for p in client.get(ROOT + "?include_inactive=true",headers=owner_a).json())
            assert client.post("/api/v1/auth/logout",headers=owner_a).status_code == 200
            assert client.get(ROOT,headers=owner_a).status_code == 401

        print("RF-005 PostgreSQL OK: CRUD, importes, tiempo base, SKU, 403, 404, 401, tenants y cotizables verificados.")
    finally:
        if organization_ids:
            _cleanup(organization_ids)


if __name__ == "__main__":
    main()
