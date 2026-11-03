"""Indicadores do dashboard, sempre calculados sobre o que está gravado.

Regras: só leituras válidas (valid/partial) entram em médias; dados simulados ficam
fora, a não ser que o filtro peça; sem dado, o indicador vem nulo (nunca zero).
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require
from app.models import Alert, Device, QualitySample, Telemetry, Trip, User, Vehicle
from app.services import quality as q

router = APIRouter(prefix="/api/v1/analytics", tags=["Indicadores"])

VALID = ("valid", "partial")


@dataclass
class Filters:
    date_from: datetime
    date_to: datetime
    vehicle_id: int | None
    driver_id: int | None
    trip_id: int | None
    include_simulated: bool

    def trip_conds(self):
        conds = [func.coalesce(Trip.departure_at, Trip.created_at).between(self.date_from, self.date_to)]
        if self.vehicle_id:
            conds.append(Trip.vehicle_id == self.vehicle_id)
        if self.driver_id:
            conds.append(Trip.driver_id == self.driver_id)
        if self.trip_id:
            conds = [Trip.id == self.trip_id]
        if not self.include_simulated:
            conds.append(Trip.is_simulated.is_(False))
        return and_(*conds)

    def telemetry_conds(self):
        conds = [Telemetry.validation_status.in_(VALID),
                 Telemetry.measured_at.between(self.date_from, self.date_to)]
        if not self.include_simulated:
            conds.append(Telemetry.is_simulated.is_(False))
        if self.trip_id or self.vehicle_id or self.driver_id:
            conds.append(Telemetry.trip_id.in_(select(Trip.id).where(self.trip_conds())))
        return and_(*conds)


def filters(
    date_from: datetime | None = None, date_to: datetime | None = None, vehicle_id: int | None = None,
    driver_id: int | None = None, trip_id: int | None = None, include_simulated: bool = False,
) -> Filters:
    now = datetime.now(UTC)
    return Filters(date_from or now - timedelta(days=7), date_to or now, vehicle_id, driver_id,
                   trip_id, include_simulated)


def _f(v, nd=2):
    return round(float(v), nd) if v is not None else None


@router.get("/overview", summary="Cards do dashboard")
def overview(f: Filters = Depends(filters), db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    trips = db.execute(select(
        func.count(Trip.id),
        func.coalesce(func.sum(Trip.volume_liters).filter(Trip.status.in_(("finalizada", "em_andamento"))), 0),
        func.count(Trip.id).filter(Trip.status == "finalizada"),
    ).where(f.trip_conds())).one()
    by_status = dict(db.execute(select(Trip.status, func.count()).where(f.trip_conds()).group_by(Trip.status)).all())
    veh = select(func.count(func.distinct(Trip.vehicle_id))).where(Trip.status == "em_andamento")
    if not f.include_simulated:
        veh = veh.where(Trip.is_simulated.is_(False))
    tel = db.execute(select(func.avg(Telemetry.milk_temperature), func.avg(Telemetry.ph),
                            func.count(Telemetry.id), func.count(Telemetry.milk_temperature))
                     .where(f.telemetry_conds())).one()
    acid = db.execute(select(func.avg(QualitySample.acidity_dornic), func.count(QualitySample.acidity_dornic))
                      .join(Trip).where(f.trip_conds(), QualitySample.collected_at.between(f.date_from, f.date_to)))\
        .one()
    alert_q = select(Alert.severity, func.count()).where(Alert.status != "encerrado")
    if not f.include_simulated:
        alert_q = alert_q.where(Alert.is_simulated.is_(False))
    alerts = dict(db.execute(alert_q.group_by(Alert.severity)).all())
    dev_q = select(Device.connection_status, func.count()).group_by(Device.connection_status)
    if not f.include_simulated:
        dev_q = dev_q.where(Device.is_simulated.is_(False))
    devices = dict(db.execute(dev_q).all())
    sim_devices = db.scalar(select(func.count()).select_from(Device).where(Device.is_simulated.is_(True)))
    return {
        "period": {"from": f.date_from, "to": f.date_to},
        "volume_liters": int(trips[1]), "trips": trips[0], "trips_finished": trips[2],
        "trips_by_status": by_status,
        "vehicles_in_operation": db.scalar(veh),
        "vehicles_total": db.scalar(select(func.count()).select_from(Vehicle).where(
            Vehicle.status == "ativo", *( [] if f.include_simulated else [Vehicle.is_simulated.is_(False)]))),
        "milk_temp_avg": _f(tel[0]), "ph_avg": _f(tel[1]), "readings_valid": tel[2],
        "milk_temp_readings": tel[3],
        "acidity_avg": _f(acid[0], 1), "acidity_samples": acid[1],
        "alerts_active": sum(alerts.values()), "alerts_by_severity": alerts,
        "devices_online": devices.get("online", 0), "devices_total": sum(devices.values()),
        "simulated_devices": sim_devices,
    }


@router.get("/series", summary="Evolução de temperatura do leite ou pH")
def series(metric: str = Query("milk_temperature", pattern="^(milk_temperature|ph|air_temperature)$"),
           f: Filters = Depends(filters), db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    span = f.date_to - f.date_from
    bucket = "minute" if span <= timedelta(hours=3) else "hour" if span <= timedelta(days=3) else "day"
    col = getattr(Telemetry, metric)
    # Agrupa no fuso de Brasília (o servidor do banco roda em UTC).
    t = func.date_trunc(bucket, func.timezone("America/Sao_Paulo", Telemetry.measured_at)).label("t")
    rows = db.execute(select(t, func.avg(col), func.min(col), func.max(col), func.count(col))
                      .where(f.telemetry_conds(), col.is_not(None)).group_by(t).order_by(t)).all()
    param = q.active_parameter(db, metric, "transporte") if metric != "air_temperature" else None
    return {
        "metric": metric, "bucket": bucket,
        "limits": {"min": _f(param.minimum_value, 3), "max": _f(param.maximum_value, 3), "unit": param.unit,
                   "source": param.source_reference} if param else None,
        "points": [{"t": r[0], "avg": _f(r[1]), "min": _f(r[2]), "max": _f(r[3]), "n": r[4]} for r in rows],
    }


@router.get("/acidity", summary="Acidez titulável por coleta")
def acidity(limit: int = Query(20, le=200), f: Filters = Depends(filters), db: Session = Depends(get_db),
            _: User = Depends(require("leitura"))):
    rows = db.execute(select(QualitySample, Trip.code).join(Trip)
                      .where(f.trip_conds(), QualitySample.acidity_dornic.is_not(None),
                             QualitySample.collected_at.between(f.date_from, f.date_to))
                      .order_by(QualitySample.collected_at.desc()).limit(limit)).all()
    param = q.active_parameter(db, "acidity_dornic", "coleta")
    return {
        "limits": {"min": _f(param.minimum_value, 1), "max": _f(param.maximum_value, 1)} if param else None,
        "samples": [{"id": s.id, "trip_code": code, "producer": s.producer, "collected_at": s.collected_at,
                     "acidity_dornic": _f(s.acidity_dornic, 1), "decision": s.decision}
                    for s, code in reversed(rows)],
    }


@router.get("/volume-by-day", summary="Volume transportado por dia")
def volume_by_day(f: Filters = Depends(filters), db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    day = func.date_trunc("day", func.timezone("America/Sao_Paulo", Trip.departure_at)).label("d")
    rows = db.execute(select(day, func.sum(Trip.volume_liters), func.count(Trip.id))
                      .where(f.trip_conds(), Trip.status.in_(("finalizada", "em_andamento")),
                             Trip.departure_at.is_not(None))
                      .group_by(day).order_by(day)).all()
    return [{"day": r[0].date().isoformat(), "volume_liters": int(r[1] or 0), "trips": r[2]} for r in rows]


@router.get("/trip-comparison", summary="Comparativo de qualidade entre viagens")
def trip_comparison(limit: int = Query(10, le=50), f: Filters = Depends(filters), db: Session = Depends(get_db),
                    _: User = Depends(require("leitura"))):
    trips = db.scalars(select(Trip).where(f.trip_conds())
                       .order_by(func.coalesce(Trip.departure_at, Trip.created_at).desc()).limit(limit)).all()
    out = []
    for t in trips:
        tel = db.execute(select(func.avg(Telemetry.ph), func.max(Telemetry.milk_temperature),
                                func.count(Telemetry.id))
                         .where(Telemetry.trip_id == t.id, Telemetry.validation_status.in_(VALID))).one()
        acid = db.scalar(select(func.avg(QualitySample.acidity_dornic)).where(QualitySample.trip_id == t.id))
        rejected = db.scalar(select(func.count()).select_from(QualitySample).where(
            QualitySample.trip_id == t.id, QualitySample.decision == "recusado"))
        alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.trip_id == t.id))
        gps = db.execute(select(Telemetry.lat, Telemetry.lon).where(
            Telemetry.trip_id == t.id, Telemetry.lat.is_not(None)).order_by(Telemetry.measured_at.desc())
            .limit(1)).first()
        out.append({
            "id": t.id, "code": t.code, "status": t.status, "is_simulated": t.is_simulated,
            "vehicle_plate": t.vehicle.plate, "driver_name": t.driver.name,
            "departure_at": t.departure_at, "volume_liters": t.volume_liters,
            "ph_avg": _f(tel[0]), "milk_temp_max": _f(tel[1]), "readings": tel[2],
            "acidity_avg": _f(acid, 1), "samples_rejected": rejected, "alerts": alerts,
            "last_gps": {"lat": float(gps[0]), "lon": float(gps[1])} if gps else None,
        })
    return out


@router.get("/positions", summary="Última posição GPS de cada veículo em viagem")
def positions(include_simulated: bool = False, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    stmt = select(Trip).where(Trip.status == "em_andamento")
    if not include_simulated:
        stmt = stmt.where(Trip.is_simulated.is_(False))
    out = []
    for t in db.scalars(stmt).all():
        row = db.execute(select(Telemetry.lat, Telemetry.lon, Telemetry.measured_at, Telemetry.device_id)
                         .where(Telemetry.trip_id == t.id, Telemetry.lat.is_not(None))
                         .order_by(Telemetry.measured_at.desc()).limit(1)).first()
        if row:
            out.append({"trip_id": t.id, "trip_code": t.code, "vehicle_plate": t.vehicle.plate,
                        "lat": float(row[0]), "lon": float(row[1]), "at": row[2], "device_id": row[3],
                        "is_simulated": t.is_simulated})
    return out

