"""Prueba end-to-end RF-002 sobre PostgreSQL real, sin revelar secretos."""
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization


def main() -> None:
    org_id: UUID | None = None
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            org = Organization(
                name="RF002 Smoke " + uuid4().hex[:8],
                sector="Pruebas", timezone="America/Mexico_City", currency="MXN",
            )
            db.add(org)
            db.flush()
            org_id = org.id
            create_first_owner(db, organization_id=org_id, email="rf002-test@example.com", password=password)
            db.commit()

        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json={
                "organization_id": str(org_id),
                "email": "rf002-test@example.com",
                "password": password,
            })
            assert response.status_code == 200, "Login no devolvio HTTP 200"
            token = response.json()["access_token"]
            headers = {"Authorization": "Bearer " + token}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        print("RF-002 PostgreSQL OK: inicio, consulta, revocacion y rechazo del JWT verificados.")
    finally:
        if org_id is not None:
            with get_session_factory()() as db:
                org = db.get(Organization, org_id)
                if org:
                    db.delete(org)
                    db.commit()


if __name__ == "__main__":
    main()
