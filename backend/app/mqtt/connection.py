"""Conexão persistente do backend com o broker MQTT.

Na Etapa 1 ela só conecta e informa o estado. Na Etapa 4 passa a assinar os
tópicos smartmilk/device/+/telemetry|status|alerts e a processar as mensagens.

A sessão é persistente (clean_session=False): se o backend cair, o broker guarda
as mensagens QoS 1 destinadas a ele e as entrega quando ele voltar.
"""
import logging
import threading
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from app.core.config import Settings
from app.core.health import CheckResult

log = logging.getLogger(__name__)


class MqttConnection:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._connected = False
        self._last_error: str | None = "ainda não conectou"
        self._since: datetime | None = None
        self._started = False

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        self.client.username_pw_set(settings.mqtt_backend_user, settings.mqtt_backend_password)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # -- callbacks do paho (rodam na thread de rede) -------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        with self._lock:
            if reason_code.is_failure:
                self._connected = False
                self._last_error = f"broker recusou a conexão: {reason_code}"
                log.error("MQTT: %s", self._last_error)
                return
            self._connected = True
            self._last_error = None
            self._since = datetime.now(UTC)
        log.info("MQTT: conectado a %s:%s", self._settings.mqtt_host, self._settings.mqtt_port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        with self._lock:
            was_connected = self._connected
            self._connected = False
            self._since = datetime.now(UTC)
            if reason_code.is_failure or was_connected:
                self._last_error = f"desconectado: {reason_code}"
        if was_connected:
            log.warning("MQTT: conexão perdida (%s); o paho tenta reconectar sozinho", reason_code)

    # -- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        # connect_async não bloqueia nem falha se o broker estiver fora;
        # o loop em segundo plano tenta de novo com espera crescente (1 a 30 s).
        self.client.connect_async(
            self._settings.mqtt_host, self._settings.mqtt_port, self._settings.mqtt_keepalive_s
        )
        self.client.loop_start()

    def stop(self) -> None:
        if not self._started:
            return
        self.client.disconnect()
        self.client.loop_stop()
        self._started = False

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def check(self) -> CheckResult:
        with self._lock:
            details = {
                "broker": f"{self._settings.mqtt_host}:{self._settings.mqtt_port}",
                "client_id": self._settings.mqtt_client_id,
                "since": self._since.isoformat() if self._since else None,
            }
            if not self._started:
                return CheckResult(ok=False, error="cliente MQTT desativado", details=details)
            return CheckResult(ok=self._connected, error=self._last_error, details=details)
