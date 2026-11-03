"""Testes de integração da infraestrutura (Etapa 1).

Conferem, contra o PostgreSQL e o Mosquitto de verdade, que:
- o backend conecta no banco e no broker;
- o broker recusa conexões anônimas e senhas erradas;
- cada dispositivo só publica nos próprios tópicos (ACL);
- o backend recebe a telemetria publicada por um dispositivo.

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
