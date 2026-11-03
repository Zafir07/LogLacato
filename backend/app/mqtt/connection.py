"""Conexão MQTT persistente usada pela API e pelos workers.

- Reconecta sozinha (espera de 1 a 30 s) e refaz as assinaturas a cada reconexão.
- Sessão persistente (clean_session=False) por padrão: se o serviço cair, o broker
  guarda as mensagens QoS 1 destinadas a ele.
- Opcionalmente publica o próprio estado (retido) e registra um Last Will, para que
  os outros serviços saibam quando ele some.
"""
import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from app.core.health import CheckResult

log = logging.getLogger(__name__)

MessageHandler = Callable[[str, bytes], None]


class MqttConnection:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        client_id: str,
        keepalive: int = 30,
        clean_session: bool = False,
        subscriptions: list[tuple[str, int]] | None = None,
        on_message: MessageHandler | None = None,
        status_topic: str | None = None,
    ) -> None:
        self.host, self.port, self.client_id = host, port, client_id
        self._keepalive = keepalive
        self._subscriptions = subscriptions or []
        self._handler = on_message
        self._status_topic = status_topic
        self._lock = threading.Lock()
        self._connected = False
        self._last_error: str | None = "ainda não conectou"
        self._since: datetime | None = None
        self._started = False
        self._stopping = False

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            clean_session=clean_session,
        )
        self.client.username_pw_set(user, password)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        if status_topic:
            self.client.will_set(status_topic, self._status_payload("offline", "lwt"), qos=1, retain=True)

    def _status_payload(self, state: str, reason: str | None = None, **extra) -> str:
        body = {"v": 1, "service": self.client_id, "state": state, "at": datetime.now(UTC).isoformat()}
        if reason:
            body["reason"] = reason
        body.update(extra)
        return json.dumps(body)

    # -- callbacks do paho (rodam na thread de rede) -------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            with self._lock:
                self._connected = False
                self._last_error = f"broker recusou a conexão: {reason_code}"
            log.error("MQTT[%s]: %s", self.client_id, self._last_error)
            return
        with self._lock:
            self._connected = True
            self._last_error = None
            self._since = datetime.now(UTC)
        for topic, qos in self._subscriptions:
            client.subscribe(topic, qos=qos)
        if self._status_topic:
            client.publish(self._status_topic, self._status_payload("online"), qos=1, retain=True)
        log.info("MQTT[%s]: conectado a %s:%s", self.client_id, self.host, self.port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        with self._lock:
            was_connected = self._connected
            self._connected = False
            self._since = datetime.now(UTC)
            if reason_code.is_failure or was_connected:
                self._last_error = f"desconectado: {reason_code}"
        if self._stopping:
            log.info("MQTT[%s]: desconectado (encerramento)", self.client_id)
        elif was_connected:
            log.warning("MQTT[%s]: conexão perdida (%s); reconectando", self.client_id, reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        if not self._handler:
            return
        try:
            self._handler(msg.topic, msg.payload)
        except Exception:  # noqa: BLE001 - uma mensagem ruim não derruba o serviço
            log.exception("MQTT[%s]: erro ao processar mensagem de %s", self.client_id, msg.topic)

    # -- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        # connect_async não bloqueia nem falha se o broker estiver fora.
        self.client.connect_async(self.host, self.port, self._keepalive)
        self.client.loop_start()

    def stop(self) -> None:
        if not self._started:
            return
        self._stopping = True
        if self._status_topic and self.connected:
            self.client.publish(
                self._status_topic, self._status_payload("offline", "shutdown"), qos=1, retain=True
            ).wait_for_publish(2)
        self.client.disconnect()
        self.client.loop_stop()
        self._started = False
        self._stopping = False

    def publish_json(self, topic: str, payload: dict, qos: int = 1, retain: bool = False):
        return self.client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)

    def publish_status(self, **extra) -> None:
        if self._status_topic and self.connected:
            self.client.publish(self._status_topic, self._status_payload("online", **extra), qos=1, retain=True)

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def check(self) -> CheckResult:
        with self._lock:
            details = {
                "broker": f"{self.host}:{self.port}",
                "client_id": self.client_id,
                "since": self._since.isoformat() if self._since else None,
            }
            if not self._started:
                return CheckResult(ok=False, error="cliente MQTT desativado", details=details)
            return CheckResult(ok=self._connected, error=self._last_error, details=details)
