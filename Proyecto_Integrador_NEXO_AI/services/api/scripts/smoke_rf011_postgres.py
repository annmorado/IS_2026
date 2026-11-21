"""RF-011: integracion real PostgreSQL y limpieza segura de datos de prueba.

No muestra credenciales; los dos negocios creados se eliminan en finally.
"""
from datetime import datetime
from secrets import token_urlsafe
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import get_session_factory
from app.main import app
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.auth.service import create_first_owner
from app.modules.order_status.model import OrderStatusEvent
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization

BASE = "/api/v1/orders"


def main() -> None:
    org_ids: list[UUID] = []
    password = token_urlsafe(25)
    try:
        with get_session_factory()() as db:
            a = Organization(name="RF011 A " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            b = Organization(name="RF011 B " + uuid4().hex[:8], sector="Pruebas",
                             timezone="America/Mexico_City", currency="MXN")
            db.add_all([a, b]); db.flush()
            org_ids = [a.id, b.id]
            create_first_owner(db, organization_id=a.id, email="rf011-owner-a@example.com", password=password)
            create_first_owner(db, organization_id=b.id, email="rf011-owner-b@example.com", password=password)
            operator = User(organization_id=a.id, email="rf011-operator-a@example.com", role="operator",
                            password_hash=hash_password(password), is_active=True)
            db.add(operator); db.flush()
            operator_id = operator.id
            db.commit()

        with TestClient(app) as client:
            def auth(org: UUID, email: str):
                response = client.post("/api/v1/auth/login", json={
                    "organization_id": str(org), "email": email, "password": password,
                })
                assert response.status_code == 200, f"Login HTTP {response.status_code}"
                return {"Authorization": "Bearer " + response.json()["access_token"]}

            owner_a = auth(org_ids[0], "rf011-owner-a@example.com")
            operator_a = auth(org_ids[0], "rf011-operator-a@example.com")
            owner_b = auth(org_ids[1], "rf011-owner-b@example.com")

            created = client.post(BASE, headers=operator_a, json={"raw_text": "12 productos para el viernes"})
            assert created.status_code == 201, f"Crear HTTP {created.status_code}"
            order_id = UUID(created.json()["id"])
            url = f"{BASE}/{order_id}"
            assert client.get(url + "/history", headers=owner_a).json() == []

            def change(previous: str, target: str, note: str = ""):
                return client.post(url + "/status", headers=operator_a, json={
                    "expected_status": previous, "to_status": target, "note": note,
                })

            assert change("draft", "pending").status_code == 200
            review = client.put(url + "/review", headers=operator_a,
                                json={"quantity": "40.500", "due_date": "2026-12-10", "expected_revision": 0})
            assert review.status_code == 200, f"Revisar HTTP {review.status_code}: {review.text[:200]}"
            assert client.post(url + "/confirm", headers=operator_a,
                               json={"expected_revision": review.json()["review_revision"]}).status_code == 200
            assert change("confirmed", "in_progress", "Produccion iniciada").status_code == 200
            completed = change("in_progress", "completed", "Pedido entregado")
            assert completed.status_code == 200, f"Completar HTTP {completed.status_code}: {completed.text[:200]}"
            assert completed.json()["order"]["status"] == "completed"
            assert change("completed", "cancelled").status_code == 409
            assert change("completed", "in_progress").status_code == 409
            assert client.get(url + "/status", headers=owner_b).status_code == 404
            assert client.get(url + "/history", headers=owner_b).status_code == 404
            assert client.post(url + "/status", headers=owner_b,
                               json={"expected_status": "completed", "to_status": "cancelled"}).status_code == 404
            assert client.get(url + "/status").status_code == 401
            assert client.post(url + "/status", headers=operator_a,
                               json={"expected_status": "completed", "to_status": "hack"}).status_code == 422

            events = client.get(url + "/history", headers=owner_a).json()
            assert len(events) == 4
            assert {(e["from_status"], e["to_status"]) for e in events} == {
                ("draft", "pending"), ("pending", "confirmed"),
                ("confirmed", "in_progress"), ("in_progress", "completed"),
            }
            assert all(e["changed_by_user_id"] == str(operator_id) for e in events)
            assert all(e["organization_id"] == str(org_ids[0]) for e in events)
            assert all(datetime.fromisoformat(e["changed_at"].replace("Z", "+00:00")) for e in events)
            assert client.get(url + "/history?limit=2&offset=0", headers=owner_a).status_code == 200

            cancelled_order = client.post(BASE, headers=operator_a,
                                          json={"raw_text": "Pedido a cancelar"}).json()
            cancel_uri = BASE + "/" + cancelled_order["id"]
            cancelled = client.post(cancel_uri + "/status", headers=operator_a,
                                    json={"expected_status": "draft", "to_status": "cancelled"})
            assert cancelled.status_code == 200 and cancelled.json()["order"]["status"] == "cancelled"
            assert client.post(cancel_uri + "/status", headers=operator_a,
                               json={"expected_status": "cancelled", "to_status": "completed"}).status_code == 409

            with get_session_factory()() as db:
                order = db.scalar(select(Order).where(Order.organization_id == org_ids[0], Order.id == order_id))
                assert order is not None and order.status == "completed"
                assert str(order.reviewed_quantity) == "40.500" and order.reviewed_due_date.isoformat() == "2026-12-10"
                audit = list(db.scalars(select(OrderStatusEvent).where(
                    OrderStatusEvent.organization_id == org_ids[0], OrderStatusEvent.order_id == order_id)).all())
                assert len(audit) == 4

            assert client.post("/api/v1/auth/logout", headers=operator_a).status_code == 200
            assert client.get(url + "/status", headers=operator_a).status_code == 401

    finally:
        if org_ids:
            with get_session_factory()() as db:
                try:
                    # La auditoria referencia al usuario actor mediante FK restrictiva.
                    # Limpiar los eventos primero; luego pedidos y organizaciones.
                    # Restringido EXCLUSIVAMENTE a los UUID temporales de esta ejecucion.
                    db.execute(delete(OrderStatusEvent).where(
                        OrderStatusEvent.organization_id.in_(org_ids)
                    ))
                    db.execute(delete(Order).where(Order.organization_id.in_(org_ids)))
                    db.execute(delete(Organization).where(Organization.id.in_(org_ids)))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

    # No informar OK antes de confirmar que la limpieza tambien termino.
    print("RF-011 PostgreSQL OK: draft, pending, confirmed, in_progress, completed, "
          "cancelled; historial fecha/actor/estado previo, revision humana, "
          "401/404/409/422, revocacion, tenants y limpieza verificados.")


if __name__ == "__main__":
    main()
