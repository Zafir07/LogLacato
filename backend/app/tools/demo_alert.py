"""Publica um evento alerta.aberto de demonstração, para ver o e-mail chegar.

Uso (com os serviços no ar):
    docker compose exec api python -m app.tools.demo_alert
    docker compose exec api python -m app.tools.demo_alert --id demo-2 --severity atencao

Usa as credenciais MQTT da API (a única, junto com o quality, que pode publicar eventos).
"""
import argparse
import json
import sys
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from app.core.config import get_settings
from app.mqtt import topics


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--id", default="demo-1", help="alert_id (o mesmo id não gera e-mail duas vezes)")
    p.add_argument("--severity", default="critico", choices=["info", "atencao", "critico"])
    args = p.parse_args(argv)

    s = get_settings()
    event = {
        "v": 1,
        "type": "alerta.aberto",
        "alert_id": args.id,
        "at": datetime.now(UTC).isoformat(),
        "severity": args.severity,
        "title": "Temperatura do leite acima do limite",
        "description": "DEMONSTRAÇÃO: 7,6 °C por 20 min (limite 7,0 °C no transporte).",
        "trip_code": "VG-DEMO",
        "device_id": "sim-001",
        "is_simulated": False,
    }
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="loglacto-demo-alert")
    c.username_pw_set(s.mqtt_backend_user, s.mqtt_backend_password)
    try:
        c.connect(s.mqtt_host, s.mqtt_port, 10)
    except OSError as exc:
        print(f"Não conectou ao broker {s.mqtt_host}:{s.mqtt_port}: {exc}", file=sys.stderr)
        return 1
    c.loop_start()
    info = c.publish(topics.EVENT_ALERT_OPENED, json.dumps(event, ensure_ascii=False), qos=1)
    info.wait_for_publish(5)
    c.disconnect()
    c.loop_stop()
    if not info.is_published():
        print("O broker não confirmou a publicação (senha da API correta?)", file=sys.stderr)
        return 1
    print(f"Evento {args.id} ({args.severity}) publicado. Veja o e-mail em http://localhost:8025")
    return 0


if __name__ == "__main__":
    sys.exit(main())
