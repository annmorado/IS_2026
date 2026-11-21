"""RF-010: prueba de persistencia y seguridad en Neon (limpia sus datos)."""
from datetime import date
from decimal import Decimal
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
from app.modules.review.service import stage_suggested_extraction
from app.modules.tenancy.scope import TenantScope

BASE = "/api/v1/orders"


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(24)
    try:
        with get_session_factory()() as db:
            a = Organization(name="RF010 Test A " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            b = Organization(name="RF010 Test B " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            db.add_all([a, b]); db.flush()
            org_ids = [a.id, b.id]
            create_first_owner(db, organization_id=a.id,
                               email="rf010-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=b.id,
                               email="rf010-owner-b@example.com", password=password)
            op = User(organization_id=a.id, email="rf010-operator-a@example.com", role="operator",
                      password_hash=hash_password(password), is_active=True)
            db.add(op); db.flush()
            actor_id = op.id
            db.commit()

        with TestClient(app) as c:
            def auth(org: UUID, email: str):
                r = c.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email":email, "password":password,
                })
                assert r.status_code==200, f"Login HTTP {r.status_code}"
                return {"Authorization":"Bearer "+r.json()["access_token"]}

            owner_a = auth(org_ids[0], "rf010-owner-a@example.com")
            operator = auth(org_ids[0], "rf010-operator-a@example.com")
            owner_b = auth(org_ids[1], "rf010-owner-b@example.com")

            creation=c.post(BASE,headers=operator,json={
                "raw_text":"Extraccion propuesta: 30 unidades para el 1 de diciembre"})
            assert creation.status_code==201, f"Crear solicitud HTTP {creation.status_code}"
            order_id=UUID(creation.json()["id"])
            uri=BASE+"/"+str(order_id)
            with get_session_factory()() as db:
                stage_suggested_extraction(
                    db, TenantScope(organization_id=org_ids[0],actor_id=actor_id),
                    order_id,quantity=Decimal("30.000"),due_date=date(2026,12,1))

            candidate=c.get(uri+"/review",headers=operator)
            assert candidate.status_code==200
            assert candidate.json()["suggested_quantity"]=="30.000"
            assert candidate.json()["reviewed_quantity"] is None
            assert c.post(uri+"/confirm",headers=operator,json={"expected_revision":1}).status_code==409
            assert c.put(uri+"/review",headers=owner_b,json={"quantity":"1","due_date":"2026-12-01","expected_revision":1}).status_code==404
            assert c.get(uri+"/review",headers=owner_b).status_code==404
            assert c.put(uri+"/review",headers=operator,json={"quantity":"0","due_date":"2026-12-10","expected_revision":1}).status_code==422
            assert c.get(uri+"/review").status_code==401

            edited=c.put(uri+"/review",headers=operator,json={
                "quantity":"40.500", "due_date":"2026-12-10", "expected_revision":1})
            assert edited.status_code==200, f"Revision HTTP {edited.status_code}: {edited.text[:200]}"
            assert edited.json()["reviewed_quantity"]=="40.500" and edited.json()["review_revision"]==2
            assert c.post(uri+"/confirm",headers=operator,json={"expected_revision":1}).status_code==409

            done=c.post(uri+"/confirm",headers=operator,json={"expected_revision":2})
            assert done.status_code==200, f"Confirmar HTTP {done.status_code}: {done.text[:200]}"
            assert done.json()["status"]=="confirmed"
            assert done.json()["reviewed_quantity"]=="40.500"
            assert done.json()["reviewed_due_date"]=="2026-12-10"
            assert done.json()["suggested_quantity"]=="30.000"
            assert c.put(uri+"/review",headers=owner_a,json={
                "quantity":"90", "due_date":"2026-12-10", "expected_revision":2}).status_code==409

            with get_session_factory()() as db:
                saved = db.scalar(select(Order).where(Order.id==order_id,
                                                    Order.organization_id==org_ids[0]))
                assert saved is not None and saved.status=="confirmed"
                assert saved.suggested_quantity==Decimal("30.000")
                assert saved.reviewed_quantity==Decimal("40.500")
                assert saved.reviewed_due_date==date(2026,12,10)
                assert saved.confirmed_at is not None

            assert c.post("/api/v1/auth/logout", headers=operator).status_code==200
            assert c.get(uri+"/review",headers=operator).status_code==401

        print("RF-010 PostgreSQL OK: sugerencia 30, correccion 40.500 y fecha, "
              "confirmacion explicita, persistencia, versiones, 401/404/409/422 y tenants verificados.")
    finally:
        if org_ids:
            with get_session_factory()() as db:
                try:
                    for org_id in org_ids:
                        org=db.get(Organization,org_id)
                        if org is not None: db.delete(org)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise


if __name__ == "__main__":
    main()
