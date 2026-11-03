"""Serviço "quality" — o papel da Lambda de qualidade na arquitetura do relatório.

1. A cada leitura nova (evento `leitura.gravada`, publicado pela api depois de gravar):
   compara pH e temperatura do leite com o parâmetro vigente de TRANSPORTE.
   - abre alerta só depois de QUALITY_OPEN_AFTER leituras seguidas fora da faixa;
   - encerra só depois de QUALITY_CLOSE_AFTER leituras seguidas de volta, com folga
     (histerese), para não abrir e fechar a cada oscilação na borda do limite;
   - leituras inválidas seguidas viram alerta de dados inválidos.
2. A cada 30 s, para cada viagem em andamento:
   - sem leitura válida há NO_DATA_MINUTES → alerta "sem leitura" (ausência ≠ normal);
   - dispositivo offline (Last Will) → alerta de comunicação;
   - passou da chegada prevista → alerta de atraso.

Alerta novo → publica `smartmilk/events/alerta.aberto` (o notifier manda o e-mail).

Executar:  python -m app.workers.quality
"""
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models import Device, Telemetry, Trip
from app.mqtt import topics
from app.services import quality as q
from app.workers.base import Worker

log = logging.getLogger(__name__)

MONITORED = {"milk_temperature": Decimal("0.3"), "ph": Decimal("0.02")}
PERIODIC_S = 30


@dataclass
class Streak:
    out: int = 0
    back: int = 0


class QualityWorker(Worker):
    default_name = "svc-quality"

    def __init__(self, *args, session_factory=SessionLocal, **kwargs) -> None:
        self._lock = threading.Lock()
        self.session_factory = session_factory
        self.streaks: dict[tuple[int, str], Streak] = {}
        self.invalid: dict[str, int] = {}
        self.counters = {"received": 0, "evaluated": 0, "alerts_opened": 0, "alerts_closed": 0, "errors": 0}
        self.last_message_at: str | None = None
        self._last_periodic = 0.0
        super().__init__(*args, **kwargs)

    def subscriptions(self) -> list[tuple[str, int]]:
        return [(topics.shared("quality", topics.EVENT_READING_STORED), 1)]

    # ---------------------------------------------------------------- eventos
    def _publish_opened(self, alert, trip_code):
        self.counters["alerts_opened"] += 1
        self.mqtt.publish_json(topics.EVENT_ALERT_OPENED, q.alert_event(alert, trip_code))

    def _publish_closed(self, alert):
        self.counters["alerts_closed"] += 1
        self.mqtt.publish_json(topics.EVENT_ALERT_CLOSED, {
            "v": 1, "type": "alerta.encerrado", "alert_id": str(alert.id),
            "reason": alert.close_reason, "is_simulated": alert.is_simulated})

    # ---------------------------------------------------------------- leituras
    def handle(self, topic: str, payload: bytes) -> None:
        with self._lock:
            self.counters["received"] += 1
            self.last_message_at = datetime.now(UTC).isoformat()
        try:
            event = json.loads(payload)
            tid = int(event["telemetry_id"])
        except (ValueError, KeyError, TypeError):
            log.warning("quality: evento inválido em %s", topic)
            return
        try:
            with self.session_factory() as db:
                self.evaluate(db, tid)
        except Exception:  # noqa: BLE001
            self.counters["errors"] += 1
            log.exception("quality: erro ao avaliar a leitura %s", tid)

    def evaluate(self, db: Session, telemetry_id: int) -> None:
        row = db.get(Telemetry, telemetry_id)
        if not row:
            return
        self.counters["evaluated"] += 1
        trip = db.get(Trip, row.trip_id) if row.trip_id else None
        opened, closed = [], []

        # Dados inválidos seguidos (sensor solto, sonda fora, payload estranho)
        fp_invalid = f"device:{row.device_id}:dados_invalidos"
        if row.validation_status in ("invalid", "time_unknown"):
            n = self.invalid.get(row.device_id, 0) + 1
            self.invalid[row.device_id] = n
            if n >= self._s("invalid_streak"):
                alert, created = q.open_or_update(
                    db, fingerprint=fp_invalid, type="dados_invalidos", severity="atencao",
                    title="Leituras inválidas seguidas do dispositivo",
                    description=f"{n} leituras seguidas sem dado aproveitável ({row.validation_status}).",
                    trip_id=trip.id if trip else None, device_id=row.device_id, is_simulated=row.is_simulated)
                if created:
                    opened.append(alert)
            db.commit()
            for a in opened:
                self._publish_opened(a, trip.code if trip else None)
            return
        self.invalid[row.device_id] = 0
        a = q.close_active(db, fp_invalid, "leituras válidas voltaram")
        if a:
            closed.append(a)

        if trip and trip.status in ("em_andamento", "finalizada"):
            for param, margin in MONITORED.items():
                value = getattr(row, param)
                if value is None:
                    continue
                qp = q.active_parameter(db, param, "transporte", row.measured_at)
                if not qp:
                    continue
                st = self.streaks.setdefault((trip.id, param), Streak())
                fp = f"trip:{trip.id}:{param}"
                if q.out_of_range(qp, value):
                    st.out, st.back = st.out + 1, 0
                    if st.out >= self._s("quality_open_after"):
                        alert, created = q.open_or_update(
                            db, fingerprint=fp, type="qualidade", parameter=param,
                            severity=self._severity(param, qp, value),
                            title=f"{q.PARAM_LABEL[param]} fora da faixa no transporte",
                            description=(f"{q.PARAM_LABEL[param]} {str(value).replace('.', ',')} {qp.unit} "
                                         f"na viagem {trip.code} (referência {q.describe_range(qp)})."),
                            trip_id=trip.id, device_id=row.device_id, qparam=qp, value=value,
                            is_simulated=row.is_simulated, at=row.measured_at)
                        if created:
                            opened.append(alert)
                elif q.inside_with_margin(qp, value, margin):
                    st.out, st.back = 0, st.back + 1
                    if st.back >= self._s("quality_close_after"):
                        a = q.close_active(db, fp, "voltou à faixa de referência", row.measured_at)
                        if a:
                            closed.append(a)
                else:
                    st.out = 0  # dentro da faixa, mas sem folga: não abre nem encerra
        db.commit()
        for a in opened:
            self._publish_opened(a, trip.code if trip else None)
        for a in closed:
            self._publish_closed(a)

    @staticmethod
    def _severity(param: str, qp, value) -> str:
        if param == "milk_temperature":
            return "critico"  # ruptura da cadeia do frio
        v = Decimal(str(value))
        far = (qp.minimum_value is not None and v < qp.minimum_value - Decimal("0.1")) or \
              (qp.maximum_value is not None and v > qp.maximum_value + Decimal("0.1"))
        return "critico" if far else "atencao"

    def _s(self, name: str) -> int:
        return getattr(self.settings, name)

    # ---------------------------------------------------------------- verificações periódicas
    def periodic(self, db: Session, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        opened, closed = [], []
        no_data = timedelta(minutes=self._s("no_data_minutes"))
        trips = db.scalars(select(Trip).where(Trip.status == "em_andamento")).all()
        for t in trips:
            device = db.scalar(select(Device).where(Device.vehicle_id == t.vehicle_id))
            # sem leitura
            fp = f"trip:{t.id}:sem_leitura"
            last = db.scalar(select(func.max(Telemetry.measured_at)).where(
                Telemetry.trip_id == t.id, Telemetry.validation_status.in_(("valid", "partial"))))
            ref = last or t.departure_at
            if device and ref and now - ref > no_data:
                mins = int((now - ref).total_seconds() // 60)
                alert, created = q.open_or_update(
                    db, fingerprint=fp, type="sem_leitura", severity="atencao",
                    title="Viagem sem leituras do sensor",
                    description=(f"Nenhuma leitura válida há {mins} min na viagem {t.code}. "
                                 "A ausência de leitura não significa que o leite está normal."),
                    trip_id=t.id, device_id=device.id, is_simulated=t.is_simulated, at=now)
                if created:
                    opened.append((alert, t.code))
            else:
                a = q.close_active(db, fp, "leituras voltaram", now)
                if a:
                    closed.append(a)
            # dispositivo offline
            if device:
                fp = f"device:{device.id}:offline"
                if device.connection_status == "offline":
                    alert, created = q.open_or_update(
                        db, fingerprint=fp, type="dispositivo_offline", severity="atencao",
                        title="Dispositivo sem comunicação",
                        description=(f"{device.id} desconectou do servidor durante a viagem {t.code}. "
                                     "As leituras ficam na fila do dispositivo até a conexão voltar."),
                        trip_id=t.id, device_id=device.id, is_simulated=t.is_simulated, at=now)
                    if created:
                        opened.append((alert, t.code))
                else:
                    a = q.close_active(db, fp, "dispositivo voltou a se comunicar", now)
                    if a:
                        closed.append(a)
            # atraso
            if t.expected_arrival_at and now > t.expected_arrival_at:
                mins = int((now - t.expected_arrival_at).total_seconds() // 60)
                alert, created = q.open_or_update(
                    db, fingerprint=f"trip:{t.id}:atraso", type="atraso", severity="atencao",
                    title="Viagem com atraso",
                    description=f"A viagem {t.code} passou {mins} min da chegada prevista.",
                    trip_id=t.id, device_id=device.id if device else None, is_simulated=t.is_simulated, at=now)
                if created:
                    opened.append((alert, t.code))
        db.commit()
        for a, code in opened:
            self._publish_opened(a, code)
        for a in closed:
            self._publish_closed(a)

    def tick(self) -> None:
        if time.monotonic() - self._last_periodic < PERIODIC_S:
            return
        self._last_periodic = time.monotonic()
        try:
            with self.session_factory() as db:
                self.periodic(db)
        except Exception:  # noqa: BLE001
            self.counters["errors"] += 1
            log.exception("quality: erro nas verificações periódicas")

    def stats(self) -> dict:
        with self._lock:
            return {**self.counters, "last_message_at": self.last_message_at}


if __name__ == "__main__":
    QualityWorker().run()
