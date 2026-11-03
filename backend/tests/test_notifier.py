"""Regras do notificador (papel do SNS), sem broker e sem servidor de e-mail."""
import json
import smtplib

import pytest

from app.core.config import Settings
from app.workers.notifier import NotifierWorker, build_email
from app.schemas.events import AlertOpenedEvent

TOPIC = "smartmilk/events/alerta.aberto"


def _settings(**over) -> Settings:
    base = {"alert_email_to": "gestor@laticinio.test", "mqtt_service_password": "x", "notify_min_severity": "atencao"}
    base.update(over)
    return Settings(**base)


def _event(**over) -> bytes:
    body = {
        "v": 1, "type": "alerta.aberto", "alert_id": "a-1", "at": "2026-11-03T12:24:10Z",
        "severity": "critico", "title": "Temperatura do leite acima do limite",
        "description": "7,6 °C por 20 min (limite 7,0 °C).", "trip_code": "VG-0142",
        "device_id": "esp32-001", "is_simulated": False,
    }
    body.update(over)
    return json.dumps(body).encode()


class FakeSender:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls = 0
        self.sent = []

    def __call__(self, msg):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise smtplib.SMTPServerDisconnected("caiu")
        self.sent.append(msg)


@pytest.fixture
def make():
    def _make(sender=None, **settings):
        return NotifierWorker(_settings(**settings), sender=sender or FakeSender(), sleep=lambda s: None)
    return _make


def test_alerta_critico_vira_email(make):
    sender = FakeSender()
    w = make(sender)
    w.handle(TOPIC, _event())
    assert len(sender.sent) == 1
    msg = sender.sent[0]
    assert msg["Subject"] == "[LogLacto] CRÍTICO: Temperatura do leite acima do limite — VG-0142"
    assert msg["To"] == "gestor@laticinio.test"
    assert "7,6 °C por 20 min" in msg.get_content()
    assert w.stats()["sent"] == 1


def test_mesmo_alerta_reentregue_nao_gera_segundo_email(make):
    sender = FakeSender()
    w = make(sender)
    w.handle(TOPIC, _event())
    w.handle(TOPIC, _event())
    assert len(sender.sent) == 1
    assert w.stats()["duplicate"] == 1


def test_alerta_simulado_nao_gera_email(make):
    sender = FakeSender()
    w = make(sender)
    w.handle(TOPIC, _event(is_simulated=True))
    assert sender.sent == []
    assert w.stats()["skipped_simulated"] == 1


def test_severidade_abaixo_do_minimo_nao_gera_email(make):
    sender = FakeSender()
    w = make(sender, notify_min_severity="critico")
    w.handle(TOPIC, _event(severity="atencao"))
    assert sender.sent == []
    assert w.stats()["skipped_severity"] == 1


def test_sem_destinatario_configurado_avisa_e_nao_envia(make):
    sender = FakeSender()
    w = make(sender, alert_email_to="")
    w.handle(TOPIC, _event())
    assert sender.sent == []
    assert w.stats()["no_recipients"] == 1


@pytest.mark.parametrize("payload", [b"nao e json", b"{}", _event(severity="gravissimo"), _event(alert_id="")])
def test_evento_invalido_e_contado_e_ignorado(make, payload):
    sender = FakeSender()
    w = make(sender)
    w.handle(TOPIC, payload)
    assert sender.sent == []
    assert w.stats()["invalid"] == 1


def test_smtp_instavel_tenta_de_novo(make):
    sender = FakeSender(fail_times=2)
    w = make(sender)
    w.handle(TOPIC, _event())
    assert sender.calls == 3
    assert w.stats()["sent"] == 1


def test_smtp_fora_desiste_e_libera_para_nova_tentativa(make):
    sender = FakeSender(fail_times=99)
    w = make(sender)
    w.handle(TOPIC, _event())
    assert w.stats()["failed"] == 1
    assert sender.calls == 4  # 1 tentativa + 3 repetições
    # Se o broker reentregar depois, o notificador tenta de novo (não conta como duplicata).
    w.handle(TOPIC, _event())
    assert w.stats()["duplicate"] == 0


def test_email_sem_viagem_nao_quebra():
    ev = AlertOpenedEvent.model_validate(json.loads(_event(trip_code=None, device_id=None)))
    msg = build_email(ev, _settings())
    assert msg["Subject"].endswith("Temperatura do leite acima do limite")
    assert "Viagem:     —" in msg.get_content()
