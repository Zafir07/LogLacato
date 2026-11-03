"""Serviço "notifier" — o papel do Amazon SNS na arquitetura do relatório.

Assina smartmilk/events/alerta.aberto e envia um e-mail de não conformidade por SMTP.
Em desenvolvimento o SMTP é o Mailpit (caixa de entrada de teste em
http://localhost:8025); em produção, qualquer servidor SMTP (ex.: o da universidade
ou do provedor de e-mail).

Regras:
- alerta de dado SIMULADO não gera e-mail;
- só notifica a partir da severidade NOTIFY_MIN_SEVERITY (padrão: atencao);
- o mesmo alert_id não gera dois e-mails (o QoS 1 pode reentregar);
- falha de SMTP: 3 tentativas com espera crescente; depois, registra no log.

Executar:  python -m app.workers.notifier
"""
import json
import logging
import smtplib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from email.message import EmailMessage

from pydantic import ValidationError

from app.core.config import Settings
from app.mqtt import topics
from app.schemas.events import SEVERITY_ORDER, AlertOpenedEvent
from app.workers.base import Worker

log = logging.getLogger(__name__)

SEVERITY_LABEL = {"info": "INFORMATIVO", "atencao": "ATENÇÃO", "critico": "CRÍTICO"}
RETRY_DELAYS_S = (1, 2, 4)
DEDUP_SIZE = 1000

Sender = Callable[[EmailMessage], None]


def build_email(event: AlertOpenedEvent, settings: Settings) -> EmailMessage:
    label = SEVERITY_LABEL[event.severity]
    trip = f" — {event.trip_code}" if event.trip_code else ""
    msg = EmailMessage()
    msg["Subject"] = f"[LogLacto] {label}: {event.title}{trip}"
    msg["From"] = settings.alert_email_from
    msg["To"] = ", ".join(settings.alert_recipients)
    lines = [
        f"Severidade: {label}",
        f"Alerta:     {event.title}",
        f"Quando:     {event.at.isoformat()}",
        f"Viagem:     {event.trip_code or '—'}",
        f"Dispositivo:{' ' + event.device_id if event.device_id else ' —'}",
        "",
        event.description or "",
        "",
        f"Identificador do alerta: {event.alert_id}",
        "Mensagem automática do LogLacto. Reconheça o alerta no painel.",
    ]
    msg.set_content("\n".join(lines))
    return msg


def smtp_sender(settings: Settings) -> Sender:
    def send(msg: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)

    return send


class NotifierWorker(Worker):
    default_name = "svc-notifier"

    def __init__(self, settings: Settings | None = None, sender: Sender | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._lock = threading.Lock()
        self._seen: OrderedDict[str, None] = OrderedDict()
        self.counters = {
            "sent": 0, "failed": 0, "invalid": 0, "duplicate": 0,
            "skipped_simulated": 0, "skipped_severity": 0, "no_recipients": 0,
        }
        super().__init__(settings)
        self._send = sender or smtp_sender(self.settings)
        self._sleep = sleep

    def subscriptions(self) -> list[tuple[str, int]]:
        return [(topics.shared("notifier", topics.EVENT_ALERT_OPENED), 1)]

    def _count(self, key: str) -> None:
        with self._lock:
            self.counters[key] += 1

    def handle(self, topic: str, payload: bytes) -> None:
        try:
            event = AlertOpenedEvent.model_validate(json.loads(payload))
        except (ValueError, UnicodeDecodeError, ValidationError) as exc:
            self._count("invalid")
            log.warning("notifier: evento inválido em %s: %s", topic, str(exc).splitlines()[0])
            return

        with self._lock:
            if event.alert_id in self._seen:
                self.counters["duplicate"] += 1
                return
            self._seen[event.alert_id] = None
            if len(self._seen) > DEDUP_SIZE:
                self._seen.popitem(last=False)

        if event.is_simulated:
            self._count("skipped_simulated")
            return
        if SEVERITY_ORDER[event.severity] < SEVERITY_ORDER.get(self.settings.notify_min_severity, 1):
            self._count("skipped_severity")
            return
        if not self.settings.alert_recipients:
            self._count("no_recipients")
            log.warning("notifier: ALERT_EMAIL_TO vazio; alerta %s não enviado", event.alert_id)
            return

        msg = build_email(event, self.settings)
        for attempt, delay in enumerate((0, *RETRY_DELAYS_S), start=1):
            if delay:
                self._sleep(delay)
            try:
                self._send(msg)
            except (OSError, smtplib.SMTPException) as exc:
                log.warning("notifier: tentativa %d falhou para o alerta %s: %s", attempt, event.alert_id, exc)
                continue
            self._count("sent")
            log.info("notifier: e-mail do alerta %s enviado para %s", event.alert_id, msg["To"])
            return
        self._count("failed")
        # Libera o id para que uma reentrega futura tente de novo.
        with self._lock:
            self._seen.pop(event.alert_id, None)
        log.error("notifier: alerta %s não enviado após %d tentativas", event.alert_id, len(RETRY_DELAYS_S) + 1)

    def stats(self) -> dict:
        with self._lock:
            return dict(self.counters)


if __name__ == "__main__":
    NotifierWorker().run()
