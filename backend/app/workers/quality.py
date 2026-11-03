"""Serviço "quality" — o papel da Lambda de qualidade na arquitetura do relatório.

Recebe cada leitura publicada pelos dispositivos e, a partir da Etapa 4, compara com
os parâmetros de qualidade vigentes, abre/atualiza/encerra alertas e publica
smartmilk/events/alerta.aberto para o notificador.

Etapa 1 (este arquivo): conecta com o próprio usuário, assina a telemetria por
assinatura compartilhada (várias réplicas dividem as leituras) e conta o que
recebe. Ainda não avalia regras.

Executar:  python -m app.workers.quality
"""
import json
import logging
import threading
from datetime import UTC, datetime

from app.mqtt import topics
from app.workers.base import Worker

log = logging.getLogger(__name__)


class QualityWorker(Worker):
    default_name = "svc-quality"

    def __init__(self, *args, **kwargs) -> None:
        self._lock = threading.Lock()
        self.received = 0
        self.invalid_json = 0
        self.last_message_at: str | None = None
        super().__init__(*args, **kwargs)

    def subscriptions(self) -> list[tuple[str, int]]:
        return [(topics.shared("quality", topics.DEVICE_TELEMETRY), 1)]

    def handle(self, topic: str, payload: bytes) -> None:
        try:
            body = json.loads(payload)
            ok = isinstance(body, dict)
        except (ValueError, UnicodeDecodeError):
            ok = False
        with self._lock:
            self.received += 1
            self.last_message_at = datetime.now(UTC).isoformat()
            if not ok:
                self.invalid_json += 1
        if not ok:
            log.warning("quality: mensagem que não é JSON em %s", topic)
            return
        # Etapa 4: validar, avaliar os parâmetros de qualidade e gerar alertas.
        log.debug("quality: leitura recebida de %s", topic)

    def stats(self) -> dict:
        with self._lock:
            return {
                "received": self.received,
                "invalid_json": self.invalid_json,
                "last_message_at": self.last_message_at,
                "rules": "Etapa 4",
            }


if __name__ == "__main__":
    QualityWorker().run()
