"""Viagens, coletas (registro do coletor) e dados de cada viagem."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import audit, get_db, paginate, require
from app.api.events import Publisher, get_publisher
from app.models import Alert, Driver, QualitySample, Telemetry, Trip, User, Vehicle
from app.mqtt import topics
from app.schemas.api import (
    AlertOut,
    Page,
    SampleIn,
    SampleOut,
    TelemetryOut,
    TripFinish,
    TripIn,
    TripOut,
    TripUpdate,
)
from app.services import quality as q
from app.services.serializers import alert_out, sample_out, trip_out

router = APIRouter(prefix="/api/v1", tags=["Viagens e coletas"])

SAMPLE_CHECKS = [("acidity_dornic", "Acidez titulável"), ("density", "Densidade"),
                 ("milk_temperature", "Temperatura do leite"), ("ph_manual", "pH")]


def _trip(db: Session, trip_id: int) -> Trip:
    t = db.get(Trip, trip_id)
    if not t:
        raise HTTPException(404, "viagem não encontrada")
    return t


def _next_code(db: Session) -> str:
    n = (db.scalar(select(func.max(Trip.id))) or 0) + 1
    while True:
        code = f"VG-{n:04d}"
        if not db.scalar(select(Trip.id).where(Trip.code == code)):
            return code
        n += 1


@router.get("/trips", response_model=Page[TripOut], summary="Listar viagens (com filtros)")
def list_trips(
    page: int = 1, page_size: int = 25, q_: str | None = Query(None, alias="q", max_length=80),
    status: str | None = None, vehicle_id: int | None = None, driver_id: int | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
    include_simulated: bool = False, db: Session = Depends(get_db), _: User = Depends(require("leitura")),
):
    stmt = select(Trip).join(Vehicle).join(Driver)
    if q_:
        like = f"%{q_}%"
        stmt = stmt.where(or_(Trip.code.ilike(like), Vehicle.plate.ilike(like), Driver.name.ilike(like),
                              Trip.origin.ilike(like), Trip.destination.ilike(like)))
    if status:
        stmt = stmt.where(Trip.status == status)
    if vehicle_id:
        stmt = stmt.where(Trip.vehicle_id == vehicle_id)
    if driver_id:
        stmt = stmt.where(Trip.driver_id == driver_id)
    if date_from:
        stmt = stmt.where(func.coalesce(Trip.departure_at, Trip.created_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.coalesce(Trip.departure_at, Trip.created_at) <= date_to)
    if not include_simulated:
        stmt = stmt.where(Trip.is_simulated.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    items = db.scalars(stmt.order_by(func.coalesce(Trip.departure_at, Trip.created_at).desc(), Trip.id.desc())
                       .offset(off).limit(size)).all()
    return Page(items=[trip_out(db, t) for t in items], total=total, page=page, page_size=size)


@router.post("/trips", response_model=TripOut, status_code=201, summary="Cadastrar viagem")
def create_trip(body: TripIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("gestor"))):
    vehicle = db.get(Vehicle, body.vehicle_id)
    if not vehicle:
        raise HTTPException(404, "veículo não encontrado")
    if not db.get(Driver, body.driver_id):
        raise HTTPException(404, "motorista não encontrado")
    if body.volume_liters and body.volume_liters > vehicle.capacity_liters:
        raise HTTPException(422, f"volume acima da capacidade do veículo ({vehicle.capacity_liters} L)")
    data = body.model_dump()
    data["code"] = data["code"] or _next_code(db)
    t = Trip(**data, is_simulated=vehicle.is_simulated)
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "código já usado ou o veículo já tem uma viagem em andamento") from None
    audit(db, request, user, "criar", "trip", t.id, {"code": t.code, "status": t.status})
    db.commit()
    return trip_out(db, t)


@router.get("/trips/{trip_id}", response_model=TripOut, summary="Detalhar viagem")
def get_trip(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    return trip_out(db, _trip(db, trip_id))


@router.patch("/trips/{trip_id}", response_model=TripOut, summary="Editar viagem")
def update_trip(trip_id: int, body: TripUpdate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("gestor"))):
    t = _trip(db, trip_id)
    if t.status in ("finalizada", "cancelada"):
        raise HTTPException(409, "viagem encerrada não pode ser editada")
    changes = body.model_dump(exclude_none=True)
    if "driver_id" in changes and not db.get(Driver, changes["driver_id"]):
        raise HTTPException(404, "motorista não encontrado")
    for k, v in changes.items():
        setattr(t, k, v)
    audit(db, request, user, "alterar", "trip", t.id, {k: str(v) for k, v in changes.items()})
    db.commit()
    return trip_out(db, t)


@router.post("/trips/{trip_id}/start", response_model=TripOut, summary="Iniciar viagem")
def start_trip(trip_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require("gestor"))):
    t = _trip(db, trip_id)
    if t.status != "planejada":
        raise HTTPException(409, f"só viagem planejada pode ser iniciada (está {t.status})")
    t.status, t.departure_at = "em_andamento", t.departure_at or datetime.now(UTC)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "o veículo já tem outra viagem em andamento") from None
    audit(db, request, user, "iniciar", "trip", t.id)
    db.commit()
    return trip_out(db, t)


@router.post("/trips/{trip_id}/finish", response_model=TripOut, summary="Finalizar viagem")
def finish_trip(trip_id: int, body: TripFinish, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("gestor")), publish: Publisher = Depends(get_publisher)):
    t = _trip(db, trip_id)
    if t.status != "em_andamento":
        raise HTTPException(409, f"só viagem em andamento pode ser finalizada (está {t.status})")
    arrival = body.arrival_at or datetime.now(UTC)
    if t.departure_at and arrival < t.departure_at:
        raise HTTPException(422, "a chegada não pode ser antes da saída")
    t.status, t.arrival_at = "finalizada", arrival
    if body.volume_liters is not None:
        t.volume_liters = body.volume_liters
    # Alertas de atraso e de falta de leitura perdem o sentido com a viagem encerrada.
    for a in db.scalars(select(Alert).where(Alert.trip_id == t.id, Alert.status != "encerrado",
                                            Alert.type.in_(("atraso", "sem_leitura")))):
        a.status, a.closed_at, a.close_reason = "encerrado", arrival, "viagem finalizada"
    audit(db, request, user, "finalizar", "trip", t.id, {"volume_liters": t.volume_liters})
    db.commit()
    publish(topics.EVENT_LOT_RECEIVED, {"v": 1, "type": "lote.recebido", "trip_code": t.code,
                                        "at": arrival.isoformat(), "volume_liters": t.volume_liters,
                                        "is_simulated": t.is_simulated})
    return trip_out(db, t)


@router.post("/trips/{trip_id}/cancel", response_model=TripOut, summary="Cancelar viagem")
def cancel_trip(trip_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("gestor"))):
    t = _trip(db, trip_id)
    if t.status in ("finalizada", "cancelada"):
        raise HTTPException(409, f"viagem já está {t.status}")
    t.status = "cancelada"
    for a in db.scalars(select(Alert).where(Alert.trip_id == t.id, Alert.status != "encerrado")):
        a.status, a.closed_at, a.close_reason = "encerrado", datetime.now(UTC), "viagem cancelada"
    audit(db, request, user, "cancelar", "trip", t.id)
    db.commit()
    return trip_out(db, t)


@router.get("/trips/{trip_id}/telemetry", response_model=list[TelemetryOut], summary="Leituras da viagem")
def trip_telemetry(trip_id: int, only_valid: bool = False, limit: int = Query(2000, le=20000),
                   db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    _trip(db, trip_id)
    stmt = select(Telemetry).where(Telemetry.trip_id == trip_id)
    if only_valid:
        stmt = stmt.where(Telemetry.validation_status.in_(("valid", "partial")))
    rows = db.scalars(stmt.order_by(Telemetry.measured_at.desc().nulls_last()).limit(limit)).all()
    return list(reversed(rows))


@router.get("/trips/{trip_id}/alerts", response_model=list[AlertOut], summary="Alertas da viagem")
def trip_alerts(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    _trip(db, trip_id)
    rows = db.scalars(select(Alert).where(Alert.trip_id == trip_id).order_by(Alert.first_seen_at.desc())).all()
    return [alert_out(db, a) for a in rows]


@router.get("/trips/{trip_id}/summary", summary="Resumo da operação")
def trip_summary(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    t = _trip(db, trip_id)
    valid = (Telemetry.trip_id == t.id) & Telemetry.validation_status.in_(("valid", "partial"))
    agg = db.execute(select(
        func.count(Telemetry.id), func.min(Telemetry.measured_at), func.max(Telemetry.measured_at),
        func.avg(Telemetry.ph), func.min(Telemetry.ph), func.max(Telemetry.ph),
        func.avg(Telemetry.milk_temperature), func.max(Telemetry.milk_temperature),
        func.count(Telemetry.id).filter(Telemetry.buffered.is_(True)),
    ).where(valid)).one()
    invalid = db.scalar(select(func.count()).select_from(Telemetry).where(
        Telemetry.trip_id == t.id, Telemetry.validation_status.in_(("invalid", "time_unknown"))))
    samples = db.scalars(select(QualitySample).where(QualitySample.trip_id == t.id)).all()
    last_gps = db.execute(select(Telemetry.lat, Telemetry.lon, Telemetry.measured_at)
                          .where(Telemetry.trip_id == t.id, Telemetry.lat.is_not(None))
                          .order_by(Telemetry.measured_at.desc()).limit(1)).first()
    duration_min = None
    if t.departure_at:
        end = t.arrival_at or datetime.now(UTC)
        duration_min = round((end - t.departure_at).total_seconds() / 60)
    acid = [float(s.acidity_dornic) for s in samples if s.acidity_dornic is not None]
    f = lambda v: round(float(v), 2) if v is not None else None  # noqa: E731
    return {
        "trip_code": t.code, "status": t.status, "duration_min": duration_min,
        "readings_valid": agg[0], "readings_invalid": invalid, "readings_from_queue": agg[8],
        "first_reading_at": agg[1], "last_reading_at": agg[2],
        "ph_avg": f(agg[3]), "ph_min": f(agg[4]), "ph_max": f(agg[5]),
        "milk_temp_avg": f(agg[6]), "milk_temp_max": f(agg[7]),
        "samples": len(samples), "samples_rejected": sum(1 for s in samples if s.decision == "recusado"),
        "acidity_avg": round(sum(acid) / len(acid), 1) if acid else None,
        "volume_collected": sum(s.volume_liters or 0 for s in samples) or None,
        "alerts_total": db.scalar(select(func.count()).select_from(Alert).where(Alert.trip_id == t.id)),
        "last_gps": {"lat": float(last_gps[0]), "lon": float(last_gps[1]), "at": last_gps[2]} if last_gps else None,
    }


@router.get("/trips/{trip_id}/track", summary="Rastro do GPS da viagem")
def trip_track(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    _trip(db, trip_id)
    rows = db.execute(select(Telemetry.lat, Telemetry.lon, Telemetry.measured_at)
                      .where(Telemetry.trip_id == trip_id, Telemetry.lat.is_not(None),
                             Telemetry.validation_status != "time_unknown")
                      .order_by(Telemetry.measured_at)).all()
    step = max(1, len(rows) // 500)  # no máximo ~500 pontos no mapa
    return [{"lat": float(r[0]), "lon": float(r[1]), "at": r[2]} for r in rows[::step]]


# ------------------------------------------------------------------ coletas
@router.get("/trips/{trip_id}/samples", response_model=list[SampleOut], summary="Coletas da viagem")
def list_samples(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    _trip(db, trip_id)
    rows = db.scalars(select(QualitySample).where(QualitySample.trip_id == trip_id)
                      .order_by(QualitySample.collected_at)).all()
    return [sample_out(db, s, _sample_violations(db, s)) for s in rows]


@router.get("/samples", response_model=Page[SampleOut], summary="Todas as coletas")
def all_samples(page: int = 1, page_size: int = 25, include_simulated: bool = False,
                db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    stmt = select(QualitySample).join(Trip)
    if not include_simulated:
        stmt = stmt.where(Trip.is_simulated.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    rows = db.scalars(stmt.order_by(QualitySample.collected_at.desc()).offset(off).limit(size)).all()
    return Page(items=[sample_out(db, s, _sample_violations(db, s)) for s in rows],
                total=total, page=page, page_size=size)


def _sample_violations(db: Session, s: QualitySample) -> list[str]:
    out = []
    for field, _label in SAMPLE_CHECKS:
        param = q.active_parameter(db, "ph" if field == "ph_manual" else field, "coleta", s.collected_at)
        if param and q.out_of_range(param, getattr(s, field)):
            out.append(field)
    return out


@router.post("/trips/{trip_id}/samples", response_model=SampleOut, status_code=201,
             summary="Registrar coleta (acidez Dornic, densidade, litragem, decisão)")
def create_sample(trip_id: int, body: SampleIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("coletor")), publish: Publisher = Depends(get_publisher)):
    t = _trip(db, trip_id)
    if t.status == "cancelada":
        raise HTTPException(409, "viagem cancelada não recebe coletas")
    if body.corrects_id is not None:
        orig = db.get(QualitySample, body.corrects_id)
        if not orig or orig.trip_id != t.id:
            raise HTTPException(422, "a coleta corrigida precisa ser desta viagem")
    s = QualitySample(trip_id=t.id, collected_by=user.id, **body.model_dump())
    db.add(s)
    db.flush()
    violations = _sample_violations(db, s)
    new_alerts = []
    for field in violations:
        pname = "ph" if field == "ph_manual" else field
        param = q.active_parameter(db, pname, "coleta", s.collected_at)
        value = getattr(s, field)
        alert, created = q.open_or_update(
            db, fingerprint=f"coleta:{s.id}:{pname}", type="qualidade", parameter=pname,
            severity="critico" if pname in ("acidity_dornic", "milk_temperature") else "atencao",
            title=f"{q.PARAM_LABEL[pname]} fora da faixa na coleta",
            description=(f"{s.producer}: {str(value).replace('.', ',')} {param.unit} "
                         f"(referência {q.describe_range(param)}). Decisão: {s.decision}."),
            trip_id=t.id, qparam=param, value=value, is_simulated=t.is_simulated, at=s.collected_at,
        )
        if created:
            new_alerts.append(alert)
    audit(db, request, user, "registrar", "sample", s.id,
          {"trip": t.code, "decision": s.decision, "fora_da_faixa": violations})
    db.commit()
    for a in new_alerts:
        publish(topics.EVENT_ALERT_OPENED, q.alert_event(a, t.code))
    if s.decision == "recusado":
        publish(topics.EVENT_COLLECTION_REJECTED, {
            "v": 1, "type": "coleta.recusada", "sample_id": s.id, "trip_code": t.code,
            "producer": s.producer, "at": s.collected_at.isoformat(), "is_simulated": t.is_simulated})
    return sample_out(db, s, violations)
