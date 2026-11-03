"""Testes de integração da infraestrutura (Etapa 1).

Conferem, contra o PostgreSQL, o Mosquitto e os workers de verdade, que:
- a API conecta no banco e no broker, e vê os serviços internos online;
- o broker recusa conexões anônimas e senhas erradas;
- cada dispositivo só publica nos próprios tópicos (ACL);
- cada serviço interno só faz o que lhe cabe (ACL por serviço);
- um evento de alerta vira e-mail (com o Mailpit do docker-compose).

Rodar com os serviços no ar:
    RUN_INTEGRATION=1 pytest -m integration          (Linux/macOS)
    $env:RUN_INTEGRATION=1; pytest -m integration    (PowerShell)
"""
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.session import check_database
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="defina RUN_INTEGRATION=1"),
]

settings = get_settings()


def _device_credentials() -> dict[str, str]:
    raw = os.getenv("MQTT_DEVICE_CREDENTIALS", "")
    pairs = [p.split(":", 1) for p in raw.split(",") if ":" in p]
    creds = {u.strip(): pw for u, pw in pairs}
    if len(creds) < 2:
        pytest.skip("MQTT_DEVICE_CREDENTIALS precisa de pelo menos dois dispositivos")
    return creds


class _Cliente:
    """Cliente MQTT de teste que espera o resultado da conexão."""

    def __init__(self, user: str | None, password: str | None) -> None:
        self.conectou = threading.Event()
        self.respondeu = threading.Event()
        self.reason = None
        self.recebidas: list[tuple[str, bytes]] = []
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"teste-{uuid.uuid4().hex[:8]}")
        if user is not None:
            self.c.username_pw_set(user, password)
        self.c.on_connect = self._on_connect
        self.c.on_message = lambda c, u, m: self.recebidas.append((m.topic, m.payload))

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.reason = reason_code
        if not reason_code.is_failure:
            self.conectou.set()
        self.respondeu.set()

    def __enter__(self):
        self.c.connect(settings.mqtt_host, settings.mqtt_port, 10)
        self.c.loop_start()
        self.respondeu.wait(5)
        return self

    def __exit__(self, *exc):
        self.c.disconnect()
        self.c.loop_stop()


def _espera(cond, timeout: float = 3.0) -> bool:
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def test_banco_responde():
    r = check_database()
    assert r.ok, r.error
    assert r.details["server_version"]


def test_health_ok_com_servicos_reais():
    with TestClient(create_app(start_mqtt=True)) as client:
        assert _espera(lambda: client.get("/health").status_code == 200, timeout=8)
        body = client.get("/health").json()
    assert body["status"] == "ok"


def test_conexao_anonima_recusada():
    with _Cliente(None, None) as cli:
        assert not cli.conectou.is_set()
        assert cli.reason is not None and cli.reason.is_failure


def test_senha_errada_recusada():
    with _Cliente(settings.mqtt_backend_user, "senha-errada") as cli:
        assert not cli.conectou.is_set()


def test_dispositivo_publica_no_proprio_topico_e_backend_recebe():
    dev, senha = next(iter(_device_credentials().items()))
    marca = uuid.uuid4().hex.encode()
    with _Cliente(settings.mqtt_backend_user, settings.mqtt_backend_password) as backend:
        assert backend.conectou.is_set()
        backend.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        time.sleep(0.3)
        with _Cliente(dev, senha) as d:
            assert d.conectou.is_set()
            d.c.publish(f"smartmilk/device/{dev}/telemetry", marca, qos=1).wait_for_publish(3)
        assert _espera(lambda: (f"smartmilk/device/{dev}/telemetry", marca) in backend.recebidas)


def test_dispositivo_nao_publica_no_topico_de_outro():
    creds = _device_credentials()
    (dev_a, senha_a), (dev_b, _) = list(creds.items())[:2]
    marca = uuid.uuid4().hex.encode()
    with _Cliente(settings.mqtt_backend_user, settings.mqtt_backend_password) as backend:
        backend.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        time.sleep(0.3)
        with _Cliente(dev_a, senha_a) as d:
            # dev_a tenta se passar por dev_b
            d.c.publish(f"smartmilk/device/{dev_b}/telemetry", marca, qos=1)
            time.sleep(1.5)
        assert all(payload != marca for _, payload in backend.recebidas)


def test_dispositivo_nao_le_telemetria_de_outros():
    creds = _device_credentials()
    (dev_a, senha_a), (dev_b, senha_b) = list(creds.items())[:2]
    marca = uuid.uuid4().hex.encode()
    with _Cliente(dev_a, senha_a) as espiao:
        espiao.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        time.sleep(0.3)
        with _Cliente(dev_b, senha_b) as d:
            d.c.publish(f"smartmilk/device/{dev_b}/telemetry", marca, qos=1).wait_for_publish(3)
        time.sleep(1.0)
        assert all(payload != marca for _, payload in espiao.recebidas)


# ---------------------------------------------------------------- serviços internos

def _service(name: str) -> tuple[str, str]:
    env = {"svc-quality": "MQTT_QUALITY_PASSWORD", "svc-notifier": "MQTT_NOTIFIER_PASSWORD"}[name]
    pw = os.getenv(env)
    if not pw:
        pytest.skip(f"defina {env}")
    return name, pw


def test_servicos_internos_aparecem_online_no_health():
    with TestClient(create_app(start_mqtt=True)) as client:
        assert _espera(lambda: client.get("/health").json()["checks"]["services"]["ok"], timeout=8)
        services = client.get("/health").json()["checks"]["services"]["details"]
    assert services["svc-quality"]["state"] == "online"
    assert services["svc-notifier"]["state"] == "online"


def test_quality_recebe_leituras_gravadas_e_nao_a_telemetria_crua():
    dev, senha = next(iter(_device_credentials().items()))
    marca_crua, marca_evento = uuid.uuid4().hex.encode(), uuid.uuid4().hex.encode()
    with _Cliente(*_service("svc-quality")) as q:
        assert q.conectou.is_set()
        q.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        q.c.subscribe("smartmilk/events/leitura.gravada", qos=1)
        time.sleep(0.3)
        with _Cliente(dev, senha) as d:
            d.c.publish(f"smartmilk/device/{dev}/telemetry", marca_crua, qos=1).wait_for_publish(3)
        with _Cliente(settings.mqtt_backend_user, settings.mqtt_backend_password) as api:
            api.c.publish("smartmilk/events/leitura.gravada", marca_evento, qos=1).wait_for_publish(3)
        assert _espera(lambda: any(p == marca_evento for _, p in q.recebidas))
        assert all(p != marca_crua for _, p in q.recebidas)


def test_quality_nao_se_passa_por_dispositivo():
    dev, _ = next(iter(_device_credentials().items()))
    marca = uuid.uuid4().hex.encode()
    with _Cliente(settings.mqtt_backend_user, settings.mqtt_backend_password) as api:
        api.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        time.sleep(0.3)
        with _Cliente(*_service("svc-quality")) as q:
            q.c.publish(f"smartmilk/device/{dev}/telemetry", marca, qos=1)
            time.sleep(1.0)
        assert all(p != marca for _, p in api.recebidas)


def test_notifier_nao_le_telemetria():
    dev, senha = next(iter(_device_credentials().items()))
    marca = uuid.uuid4().hex.encode()
    with _Cliente(*_service("svc-notifier")) as n:
        n.c.subscribe("smartmilk/device/+/telemetry", qos=1)
        time.sleep(0.3)
        with _Cliente(dev, senha) as d:
            d.c.publish(f"smartmilk/device/{dev}/telemetry", marca, qos=1).wait_for_publish(3)
        time.sleep(1.0)
        assert all(p != marca for _, p in n.recebidas)


def test_dispositivo_nao_publica_eventos_de_alerta():
    dev, senha = next(iter(_device_credentials().items()))
    marca = uuid.uuid4().hex.encode()
    with _Cliente(*_service("svc-notifier")) as n:
        n.c.subscribe("smartmilk/events/alerta.aberto", qos=1)
        time.sleep(0.3)
        with _Cliente(dev, senha) as d:
            # um dispositivo comprometido tentando disparar e-mails falsos
            d.c.publish("smartmilk/events/alerta.aberto", marca, qos=1)
            time.sleep(1.0)
        assert all(p != marca for _, p in n.recebidas)


def test_evento_de_alerta_vira_email():
    mailpit = os.getenv("MAILPIT_URL")
    if not mailpit:
        pytest.skip("defina MAILPIT_URL (o docker-compose já define)")
    import json as _json
    import urllib.request

    alert_id = f"teste-{uuid.uuid4().hex[:10]}"
    evento = {
        "v": 1, "type": "alerta.aberto", "alert_id": alert_id, "at": "2026-11-03T12:00:00Z",
        "severity": "critico", "title": "Teste de integração do notificador",
        "description": "Pode ignorar.", "trip_code": "VG-TESTE", "is_simulated": False,
    }
    with _Cliente(settings.mqtt_backend_user, settings.mqtt_backend_password) as api:
        api.c.publish("smartmilk/events/alerta.aberto", _json.dumps(evento), qos=1).wait_for_publish(3)

    def chegou() -> bool:
        with urllib.request.urlopen(f"{mailpit}/api/v1/search?query={alert_id}", timeout=3) as r:
            return len(_json.load(r).get("messages") or []) > 0

    assert _espera(chegou, timeout=15), "o e-mail não chegou ao Mailpit (ALERT_EMAIL_TO definido?)"
