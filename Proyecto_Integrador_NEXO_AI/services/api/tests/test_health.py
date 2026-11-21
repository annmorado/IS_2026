
"""
NEXO AI - Pruebas del endpoint Health.

Verifica la disponibilidad y el contrato
basico de la API.
"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_status_code():
    """El endpoint debe responder HTTP 200."""

    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_response():
    """El endpoint debe devolver el JSON esperado."""

    response = client.get("/api/v1/health")

    expected = {
        "status": "ok",
        "service": "nexo-ai-api",
        "version": "0.1.0",
    }

    assert response.json() == expected


def test_health_openapi():
    """El endpoint debe estar documentado en OpenAPI."""

    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "/api/v1/health" in paths
    assert "get" in paths["/api/v1/health"]


def test_health_rejects_post():
    """Health no debe aceptar solicitudes POST."""

    response = client.post("/api/v1/health")

    assert response.status_code == 405
