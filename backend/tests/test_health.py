"""Testes de unidade do /health: não precisam de banco, broker nem workers."""
import pytest
from fastapi.testclient import TestClient

from app.api.routes.health import get_database_check, get_mqtt_check, get_services_check
from app.core.health import CheckResult
from app.main import create_app

OK = CheckResult(ok=True, latency_ms=1.0)
FORA = CheckResult(ok=False, error="ConnectionRefused")


def _client(db: CheckResult, mqtt: CheckResult, services: CheckResult = OK) -> TestClient:
    app = create_app(start_mqtt=False)
    app.dependency_overrides[get_database_check] = lambda: (lambda: db)
    app.dependency_overrides[get_mqtt_check] = lambda: (lambda: mqtt)
    app.dependency_overrides[get_services_check] = lambda: (lambda: services)
    return TestClient(app)


def test_live_sempre_responde():
    with TestClient(create_app(start_mqtt=False)) as client:
        r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ok_quando_tudo_responde():
    with _client(OK, OK, OK) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"database", "mqtt", "services"}


@pytest.mark.parametrize(
    ("db", "mqtt", "services", "fora"),
    [
        (FORA, OK, OK, "database"),
        (OK, FORA, OK, "mqtt"),
        (OK, OK, FORA, "services"),
        (FORA, FORA, OK, "database"),
    ],
)
def test_health_503_quando_algo_cai(db, mqtt, services, fora):
    with _client(db, mqtt, services) as client:
        r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"][fora]["ok"] is False
    assert body["checks"][fora]["error"]


def test_mqtt_desativado_aparece_como_falha():
    # Sem o cliente iniciado, a API não finge que está conectada.
    app = create_app(start_mqtt=False)
    app.dependency_overrides[get_database_check] = lambda: (lambda: OK)
    app.dependency_overrides[get_services_check] = lambda: (lambda: OK)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["checks"]["mqtt"]["error"] == "cliente MQTT desativado"


def test_resposta_traz_request_id():
    with _client(OK, OK) as client:
        r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
