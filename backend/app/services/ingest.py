"""Recebe o que os dispositivos publicam e grava no banco (papel do módulo de Telemetria).

- telemetry: valida, deduplica por (device_id, msg_id), associa à viagem pelo horário
  da medição, grava e publica `leitura.gravada` para o serviço de qualidade.
- status:    atualiza o estado de conexão do dispositivo (inclui o Last Will).
- alerts:    falhas vistas pelo próprio dispositivo viram alertas.

Nada que chega do dispositivo é confiado sem conferir: o device_id do tópico manda,
"simulated" precisa bater com o cadastro e valores fisicamente impossíveis não entram.
"""
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.models import Device, DeviceStatusEvent, RejectedMessage, Telemetry, Trip
from app.mqtt import topics
from app.services import quality as q

log = logging.getLogger(__name__)

RANGES = {
    "ph": (0, 14), "ph_voltage": (0, 5.5), "milk_temperature": (-55, 125),
    "air_temperature": (-40, 80), "air_humidity": (0, 100),
}
# Leitura com horário mais de 10 min no futuro: relógio do dispositivo errado.
MAX_CLOCK_AHEAD = timedelta(minutes=10)


class Readings(BaseModel):
    ph: float | None = None
    ph_voltage: float | None = None
    milk_temperature: float | None = None
    air_temperature: float | None = None
    air_humidity: float | None = None


class Gps(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    fix: bool = True
    sats: int | None = None


class TelemetryPayload(BaseModel):
    v: Literal[1]
    msg_id: str = Field(min_length=3, max_length=80)
    device_id: str
    measured_at: datetime | None
    time_source: Literal["ntp", "gps", "estimated", "none"]
    readings: Readings
    sensor_flags: int = Field(default=0, ge=0, le=255)
    gps: Gps | None = None
    buffered: bool = False
    simulated: bool = False
    fw: str | None = Field(default=None, max_length=40)


class DeviceAlertPayload(BaseModel):
    v: Literal[1]
    device_id: str
    code: Literal["SENSOR_FAULT", "QUEUE_HIGH", "QUEUE_DROPPED", "TIME_UNSYNCED"]
    severity: Literal["info", "warning", "critical"] = "warning"
    at: datetime | None = None
    message: str = Field(default="", max_length=300)
    details: dict | None = None


DEVICE_ALERT_TEXT = {
    "SENSOR_FAULT": "Falha de sensor no dispositivo",
    "QUEUE_HIGH": "Fila offline do dispositivo acima de 80%",
    "QUEUE_DROPPED": "Dispositivo descartou leituras (fila cheia)",
    "TIME_UNSYNCED": "Dispositivo sem horário sincronizado",
}
SEV_MAP = {"info": "info", "warning": "atencao", "critical": "critico"}

Publish = Callable[[str, dict], None]
Broadcast = Callable[[dict], None]


def validate_readings(p: TelemetryPayload) -> tuple[dict, list[dict], str]:
    """Separa valores aceitos dos impossíveis e classifica a leitura."""
    values, errors = {}, []
    for field, (lo, hi) in RANGES.items():
        val = getattr(p.readings, field)
        if val is None:
            values[field] = None
            continue
        if not (lo <= val <= hi):
            errors.append({"field": field, "value": val, "error": f"fora da faixa física {lo}–{hi}"})
            values[field] = None
        else:
            values[field] = Decimal(str(round(val, 3)))
    measured = [values[f] for f in ("ph", "milk_temperature", "air_temperature", "air_humidity")]
    if p.time_source == "none" or p.measured_at is None:
        status = "time_unknown"
    elif all(v is None for v in measured):
        status = "invalid"
    elif errors:
        status = "partial"
    else:
        status = "valid"
    return values, errors, status


class Ingestor:
    def __init__(self, session_factory: sessionmaker, publish: Publish, broadcast: Broadcast) -> None:
        self.session_factory = session_factory
        self.publish = publish
        self.broadcast = broadcast

    # ------------------------------------------------------------- roteamento
    def handle(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        if len(parts) == 4 and parts[0] == "smartmilk" and parts[1] == "device":
            kind = parts[3]
            if kind == "telemetry":
                self.telemetry(parts[2], topic, payload)
            elif kind == "status":
                self.status(parts[2], topic, payload)
            elif kind == "alerts":
                self.device_alert(parts[2], topic, payload)
        elif len(parts) == 3 and parts[1] == "events":
            try:
                body = json.loads(payload)
            except ValueError:
                return
            if isinstance(body, dict):
                self.broadcast({"type": "event", "event": parts[2], "data": body})

    def _reject(self, db: Session, topic: str, reason: str, payload: bytes) -> None:
        db.add(RejectedMessage(topic=topic[:200], reason=reason[:300],
                               payload=payload[:4000].decode("utf-8", "replace")))
        db.commit()
        log.warning("mensagem rejeitada em %s: %s", topic, reason)

    # ------------------------------------------------------------- telemetria
    def telemetry(self, device_id: str, topic: str, payload: bytes) -> int | None:
        with self.session_factory() as db:
            device = db.get(Device, device_id)
            if not device:
                self._reject(db, topic, "dispositivo não cadastrado", payload)
                return None
            try:
                raw = json.loads(payload)
                p = TelemetryPayload.model_validate(raw)
            except (ValueError, UnicodeDecodeError, ValidationError) as exc:
                self._reject(db, topic, f"payload inválido: {str(exc).splitlines()[0]}", payload)
                return None
            if p.device_id != device_id:
                self._reject(db, topic, f"device_id do payload ({p.device_id}) diferente do tópico", payload)
                return None
            if p.simulated != device.is_simulated:
                self._reject(db, topic, "campo 'simulated' não bate com o cadastro do dispositivo", payload)
                return None
            now = datetime.now(UTC)
            measured_at = p.measured_at
            values, errors, status = validate_readings(p)
            if measured_at and measured_at > now + MAX_CLOCK_AHEAD:
                errors.append({"field": "measured_at", "value": measured_at.isoformat(),
                               "error": "horário no futuro"})
                status = "time_unknown"
            trip_id = self._find_trip(db, device, measured_at if status != "time_unknown" else None)
            stmt = insert(Telemetry).values(
                device_id=device.id, trip_id=trip_id, msg_id=p.msg_id, measured_at=measured_at,
                received_at=now, time_source=p.time_source, sensor_flags=p.sensor_flags,
                lat=Decimal(str(p.gps.lat)) if p.gps and p.gps.fix else None,
                lon=Decimal(str(p.gps.lon)) if p.gps and p.gps.fix else None,
                buffered=p.buffered, is_simulated=device.is_simulated, validation_status=status,
                validation_errors=errors or None, raw_payload=raw, **values,
            ).on_conflict_do_nothing(constraint="uq_telemetry_device_msg").returning(Telemetry.id)
            new_id = db.scalar(stmt)
            if new_id is None:
                db.rollback()
                return None  # retransmissão de uma leitura já gravada
            if not device.last_seen_at or device.last_seen_at < now:
                device.last_seen_at = now
            if p.fw:
                device.firmware_version = p.fw
            if not p.buffered and device.connection_status != "online":
                device.connection_status = "online"
            db.commit()
        event = {
            "v": 1, "type": "leitura.gravada", "telemetry_id": new_id, "device_id": device_id,
            "trip_id": trip_id, "validation_status": status, "is_simulated": p.simulated,
        }
        self.publish(topics.EVENT_READING_STORED, event)
        self.broadcast({"type": "telemetry", "data": {
            "id": new_id, "device_id": device_id, "trip_id": trip_id, "msg_id": p.msg_id,
            "measured_at": measured_at, "received_at": now, "time_source": p.time_source,
            "buffered": p.buffered, "is_simulated": p.simulated, "validation_status": status,
            "validation_errors": errors or None, "sensor_flags": p.sensor_flags,
            "lat": p.gps.lat if p.gps and p.gps.fix else None,
            "lon": p.gps.lon if p.gps and p.gps.fix else None,
            **{k: (float(v) if v is not None else None) for k, v in values.items()},
        }})
        return new_id

    @staticmethod
    def _find_trip(db: Session, device: Device, at: datetime | None) -> int | None:
        """A viagem cujo intervalo contém o horário da medição (não 'a viagem atual')."""
        if not device.vehicle_id:
            return None
        base = select(Trip.id).where(Trip.vehicle_id == device.vehicle_id)
        if at is None:
            return db.scalar(base.where(Trip.status == "em_andamento"))
        return db.scalar(
            base.where(Trip.status.in_(("em_andamento", "finalizada")),
                       Trip.departure_at <= at,
                       at <= func.coalesce(Trip.arrival_at, at))
            .order_by(Trip.departure_at.desc()).limit(1)
        )

    # ------------------------------------------------------------- estado
    def status(self, device_id: str, topic: str, payload: bytes) -> None:
        with self.session_factory() as db:
            device = db.get(Device, device_id)
            if not device:
                self._reject(db, topic, "dispositivo não cadastrado", payload)
                return
            try:
                body = json.loads(payload)
                state = body.get("state")
                if state not in ("online", "offline") or body.get("device_id", device_id) != device_id:
                    raise ValueError("state deve ser online/offline")
            except (ValueError, AttributeError, UnicodeDecodeError) as exc:
                self._reject(db, topic, f"status inválido: {exc}", payload)
                return
            changed = device.connection_status != state
            device.connection_status = state
            device.last_status = body
            if body.get("fw"):
                device.firmware_version = str(body["fw"])[:40]
            if state == "online":
                device.last_seen_at = datetime.now(UTC)
            if changed:
                db.add(DeviceStatusEvent(device_id=device_id, state=state, details=body))
            db.commit()
        self.broadcast({"type": "device_status", "data": {"device_id": device_id, "state": state, "status": body}})

    # ------------------------------------------------------------- alertas do dispositivo
    def device_alert(self, device_id: str, topic: str, payload: bytes) -> None:
        with self.session_factory() as db:
            device = db.get(Device, device_id)
            if not device:
                self._reject(db, topic, "dispositivo não cadastrado", payload)
                return
            try:
                p = DeviceAlertPayload.model_validate(json.loads(payload))
                if p.device_id != device_id:
                    raise ValueError("device_id diferente do tópico")
            except (ValueError, ValidationError, UnicodeDecodeError) as exc:
                self._reject(db, topic, f"alerta inválido: {str(exc).splitlines()[0]}", payload)
                return
            trip_id = self._find_trip(db, device, None)
            alert, created = q.open_or_update(
                db, fingerprint=f"device:{device_id}:{p.code}", type="sensor",
                severity=SEV_MAP[p.severity], title=DEVICE_ALERT_TEXT[p.code],
                description=p.message or DEVICE_ALERT_TEXT[p.code], trip_id=trip_id,
                device_id=device_id, is_simulated=device.is_simulated, at=p.at,
            )
            db.commit()
            trip_code = db.scalar(select(Trip.code).where(Trip.id == trip_id)) if trip_id else None
            event = q.alert_event(alert, trip_code) if created else None
        if event:
            self.publish(topics.EVENT_ALERT_OPENED, event)
