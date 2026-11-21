"""RF-006: prueba real de PostgreSQL y aislamiento. Usa datos temporales.

NO imprimir URL, passwords ni JWT. Limpia organizaciones generadas si es posible.
"""
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            org_a = Organization(name="RF006 Test A " + uuid4().hex[:10], sector="Pruebas",
                                 timezone="America/Mexico_City", currency="MXN")
            org_b = Organization(name="RF006 Test B " + uuid4().hex[:10], sector="Pruebas",
                                 timezone="America/Mexico_City", currency="MXN")
            db.add_all((org_a, org_b))
            db.flush()
            org_ids = [org_a.id, org_b.id]
            create_first_owner(db, organization_id=org_a.id, email="rf006-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=org_b.id, email="rf006-owner-b@example.com", password=password)
            db.add(User(organization_id=org_a.id, email="rf006-operator-a@example.com",
                        password_hash=hash_password(password), role="operator", is_active=True))
            db.commit()

        with TestClient(app) as client:
            def auth(org_id: UUID, email: str) -> dict[str, str]:
                r = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org_id), "email": email, "password": password,
                })
                assert r.status_code == 200, "No fue posible iniciar sesion"
                return {"Authorization": "Bearer " + r.json()["access_token"]}

            owner_a = auth(org_ids[0], "rf006-owner-a@example.com")
            owner_b = auth(org_ids[1], "rf006-owner-b@example.com")
            operator_a = auth(org_ids[0], "rf006-operator-a@example.com")

            p = client.post("/api/v1/products", headers=owner_a, json={
                "sku": "RF006-CAM", "name": "Playera test", "unit": "pieza",
                "cost_mxn": "50.00", "price_mxn": "100.00", "base_production_minutes": "25.00",
            })
            assert p.status_code == 201, f"Crear producto: HTTP {p.status_code}"
            product_id = p.json()["id"]

            m = client.post("/api/v1/materials", headers=owner_a, json={
                "sku": "RF006-TELA", "name": "Tela de prueba", "unit": "metro",
                "quantity_available": "10.000",
            })
            assert m.status_code == 201, f"Crear material: HTTP {m.status_code}"
            material_id = m.json()["id"]

            recipe_url = f"/api/v1/products/{product_id}/recipe/{material_id}"
            rec = client.put(recipe_url, headers=owner_a, json={"quantity_per_unit": "0.500"})
            assert rec.status_code == 200, f"Crear receta: HTTP {rec.status_code}"

            requirements_url = f"/api/v1/products/{product_id}/material-requirements?quantity=30"
            insufficient = client.get(requirements_url, headers=operator_a)
            assert insufficient.status_code == 200
            assert insufficient.json()["feasible"] is False
            assert insufficient.json()["materials"][0]["required"] == "15.000"
            assert insufficient.json()["materials"][0]["shortage"] == "5.000"

            stock = client.put(f"/api/v1/materials/{material_id}/stock", headers=owner_a,
                               json={"quantity_available": "20.000"})
            assert stock.status_code == 200
            updated = client.get(requirements_url, headers=operator_a)
            assert updated.status_code == 200 and updated.json()["feasible"] is True
            assert updated.json()["materials"][0]["shortage"] == "0.000"

            assert client.get(f"/api/v1/materials/{material_id}", headers=owner_b).status_code == 404
            assert client.get(f"/api/v1/products/{product_id}/recipe", headers=owner_b).status_code == 404
            assert client.put(f"/api/v1/materials/{material_id}/stock", headers=owner_b,
                              json={"quantity_available": "999.000"}).status_code == 404
            assert client.put(recipe_url, headers=operator_a,
                              json={"quantity_per_unit":"1.000"}).status_code == 403
            assert client.get(requirements_url).status_code == 401
            assert client.get(f"/api/v1/materials/{material_id}", headers=owner_a).json()["quantity_available"] == "20.000"
            assert client.post(f"/api/v1/materials/{material_id}/deactivate", headers=owner_a).status_code == 200
            inactive = client.get(requirements_url, headers=owner_a)
            assert inactive.status_code == 200 and inactive.json()["feasible"] is False

            print("RF-006 PostgreSQL OK: materiales, receta, 30 x 0.500 = 15.000, "
                  "faltante, recálculo de stock, inactivo, 401/403/404 y tenants verificados.")
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
