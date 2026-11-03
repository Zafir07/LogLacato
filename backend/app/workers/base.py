"""Base dos workers (serviços que só conversam pelo broker, sem HTTP).

Cada worker:
- conecta no broker com o próprio usuário MQTT (ACL própria);
- assina os tópicos de que precisa;
- publica o próprio estado em smartmilk/services/<usuário>/status, retido, com
  Last Will — a API mostra isso no /health;
- grava uma "batida" num arquivo local, que o healthcheck do Docker confere.
"""
import logging
import signal
import threading
import time
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.mqtt import topics
from app.mqtt.connection import MqttConnection

log = logging.getLogger(__name__)

HEARTBEAT_S = 15


def heartbeat_file(name: str) -> Path:
    return Path("/tmp") / f"loglacto-{name}.alive"


class Worker:
    #: nome padrão do serviço = usuário MQTT dele (as regras da ACL dependem disso)
    default_name: str = "svc-worker"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.name = self.settings.mqtt_service_user or self.default_name
        self._stop = threading.Event()
        self.mqtt = MqttConnection(
            host=self.settings.mqtt_host,
            port=self.settings.mqtt_port,
            user=self.name,
            password=self.settings.mqtt_service_password,
            client_id=self.name,
            keepalive=self.settings.mqtt_keepalive_s,
            subscriptions=self.subscriptions(),
            on_message=self.handle,
            status_topic=topics.service_status(self.name),
        )

    # -- para as subclasses --------------------------------------------------
    def subscriptions(self) -> list[tuple[str, int]]:
        return []

    def handle(self, topic: str, payload: bytes) -> None:
        raise NotImplementedError

    def stats(self) -> dict:
        return {}

    # -- execução ------------------------------------------------------------
    def stop(self, *_args) -> None:
        self._stop.set()

    def run(self) -> None:
        configure_logging(self.settings.log_level)
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        log.info("%s: iniciando", self.name)
        self.mqtt.start()
        beat = heartbeat_file(self.name)
        while not self._stop.is_set():
            if self.mqtt.connected:
                self.mqtt.publish_status(**self.stats())
                beat.write_text(str(time.time()))
                self._stop.wait(HEARTBEAT_S)
            else:
                # Sem conexão: não grava batida (o healthcheck do Docker acusa) e
                # confere de novo em 1 s, para bater logo que o broker voltar.
                self._stop.wait(1)
        log.info("%s: encerrando", self.name)
        self.mqtt.stop()
        beat.unlink(missing_ok=True)
