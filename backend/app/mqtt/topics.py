"""Nomes dos tópicos MQTT, num lugar só (ver docs/architecture/protocolo-mqtt.md)."""

DEVICE_TELEMETRY = "smartmilk/device/+/telemetry"
DEVICE_STATUS = "smartmilk/device/+/status"
DEVICE_ALERTS = "smartmilk/device/+/alerts"

# Eventos de negócio entre serviços (papel do EventBridge no relatório)
EVENTS_ALL = "smartmilk/events/#"
EVENT_ALERT_OPENED = "smartmilk/events/alerta.aberto"
EVENT_COLLECTION_REJECTED = "smartmilk/events/coleta.recusada"
EVENT_LOT_RECEIVED = "smartmilk/events/lote.recebido"
EVENT_ALERT_CLOSED = "smartmilk/events/alerta.encerrado"
# A api grava a leitura e avisa o quality (só leituras novas, nunca duplicatas)
EVENT_READING_STORED = "smartmilk/events/leitura.gravada"

# Estado de cada serviço interno (retido, com Last Will)
SERVICES_STATUS = "smartmilk/services/+/status"


def service_status(name: str) -> str:
    return f"smartmilk/services/{name}/status"


def shared(group: str, topic: str) -> str:
    """Assinatura compartilhada: várias réplicas do mesmo worker dividem as mensagens."""
    return f"$share/{group}/{topic}"
