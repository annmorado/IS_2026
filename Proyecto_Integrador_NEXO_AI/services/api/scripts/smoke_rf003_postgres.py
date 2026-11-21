"""Prueba RF-003 real en PostgreSQL: permisos 200/403, aislamiento y limpieza."""
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
    with get_session_factory()() as db:
        try:
            org_a=Organization(name="RF003 Test A " + uuid4().hex[:6],sector="Pruebas",timezone="America/Mexico_City",currency="MXN")
            org_b=Organization(name="RF003 Test B " + uuid4().hex[:6],sector="Pruebas",timezone="America/Mexico_City",currency="MXN")
            db.add_all([org_a, org_b]); db.flush()
            org_ids = [org_a.id, org_b.id]
            create_first_owner(db, organization_id=org_a.id, email="rf003-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=org_b.id, email="rf003-owner-b@example.com", password=password)
            db.add(User(organization_id=org_a.id,email="rf003-operator-a@example.com",password_hash=hash_password(password),role="operator",is_active=True))
            db.commit()
        except Exception:
            db.rollback()
            raise

    try:
        with TestClient(app) as client:
            def login(email:str,org:UUID)->dict[str,str]:
                res=client.post("/api/v1/auth/login",json={"organization_id":str(org),"email":email,"password":password})
                assert res.status_code == 200, f"Error login: HTTP {res.status_code}"
                return {"Authorization":"Bearer "+res.json()["access_token"]}
            owner_a=login("rf003-owner-a@example.com",org_ids[0])
            operator_a=login("rf003-operator-a@example.com",org_ids[0])
            owner_b=login("rf003-owner-b@example.com",org_ids[1])
            url="/api/v1/organizations/me/policies"
            before=client.get(url,headers=owner_a)
            assert before.status_code == 200 and before.json()["max_discount_percent"] == "0.00"
            denied=client.patch(url,headers=operator_a,json={"max_discount_percent":"10.00"})
            assert denied.status_code == 403, f"Operador no bloqueado: HTTP {denied.status_code}"
            updated=client.patch(url,headers=owner_a,json={"max_discount_percent":"12.00"})
            assert updated.status_code == 200, f"Propietario no pudo actualizar: {updated.status_code}"
            read_operator=client.get(url,headers=operator_a)
            assert read_operator.json()["max_discount_percent"] == "12.00"
            other=client.get(url,headers=owner_b)
            assert other.json()["max_discount_percent"] == "0.00"
            assert client.get("/api/v1/organizations/me",headers=owner_b).json()["id"] == str(org_ids[1])
            assert client.post("/api/v1/auth/logout",headers=owner_a).status_code == 200
            assert client.patch(url,headers=owner_a,json={"max_discount_percent":"50.00"}).status_code == 401
        print("RF-003 PostgreSQL OK: propietario, operador, HTTP 403, aislamiento y revocacion verificados.")
    finally:
        with get_session_factory()() as db:
            for oid in org_ids:
                org=db.get(Organization,oid)
                if org is not None:
                    db.delete(org)
            db.commit()


if __name__ == "__main__":
    main()
