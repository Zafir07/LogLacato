"""Publicação de eventos de negócio a partir das rotas da API."""
import logging
from collections.abc import Callable

from fastapi import Request

log = logging.getLogger(__name__)

Publisher = Callable[[str, dict], None]


def get_publisher(request: Request) -> Publisher:
    mqtt = getattr(request.app.state, "mqtt", None)

    def publish(topic: str, payload: dict) -> None:
        if mqtt is None or not mqtt.connected:
            log.warning("evento %s não publicado: broker indisponível", topic)
            return
        mqtt.publish_json(topic, payload)

    return publish
