"""Testes de unidade do /health: não precisam de banco nem de broker."""
import pytest
from fastapi.testclient import TestClient

from app.api.routes.health import get_database_check, get_mqtt_check
from app.core.health import CheckResult
from app.main import create_app


def _client(db: CheckResult, mqtt: CheckResult) -> TestClient:
    app = create_app(start_mqtt=False)
    app.dependency_overrides[get_database_check] = lambda: (lambda: db)
    app.dependency_overrides[get_mqtt_check] = lambda: (lambda: mqtt)
    return TestClient(app)


OK = CheckResult(ok=True, latency_ms=1.0)
FORA = CheckResult(ok=False, error="ConnectionRefused")


def test_live_sempre_responde():
    with TestClient(create_app(start_mqtt=False)) as client:
        r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ok_quando_banco_e_broker_respondem():
    with _client(OK, OK) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["mqtt"]["ok"] is True


@pytest.mark.parametrize(
    ("db", "mqtt", "fora"),
    [(FORA, OK, "database"), (OK, FORA, "mqtt"), (FORA, FORA, "database")],
)
def test_health_503_quando_alguma_dependencia_cai(db, mqtt, fora):
    with _client(db, mqtt) as client:
        r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"][fora]["ok"] is False
    assert body["checks"][fora]["error"]


def test_mqtt_desativado_aparece_como_falha():
    # Sem o cliente iniciado, o backend não finge que está conectado.
    app = create_app(start_mqtt=False)
    app.dependency_overrides[get_database_check] = lambda: (lambda: OK)
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["checks"]["mqtt"]["error"] == "cliente MQTT desativado"


def test_resposta_traz_request_id():
    with _client(OK, OK) as client:
        r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
