"""Alertas, parâmetros de qualidade, telemetria recente, auditoria e WebSocket."""
import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, get_db, paginate, require, user_from_token
from app.api.events import Publisher, get_publisher
from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models import Alert, AuditLog, Device, QualityParameter, QualitySample, Telemetry, Trip, User
from app.mqtt import topics
from app.schemas.api import AlertAction, AlertOut, AuditOut, Page, ParameterIn, ParameterOut, TelemetryOut
from app.services.serializers import alert_out

router = APIRouter(prefix="/api/v1", tags=["Monitoramento"])


# ------------------------------------------------------------------ alertas
@router.get("/alerts", response_model=Page[AlertOut], summary="Central de alertas")
def list_alerts(page: int = 1, page_size: int = 25, status: str | None = None, severity: str | None = None,
                type: str | None = None, trip_id: int | None = None, active_only: bool = False,
                include_simulated: bool = False, db: Session = Depends(get_db),
                _: User = Depends(require("leitura"))):
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status == status)
    if active_only:
        stmt = stmt.where(Alert.status != "encerrado")
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if type:
        stmt = stmt.where(Alert.type == type)
    if trip_id:
        stmt = stmt.where(Alert.trip_id == trip_id)
    if not include_simulated:
        stmt = stmt.where(Alert.is_simulated.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    sev_order = func.array_position(["critico", "atencao", "info"], Alert.severity)
    rows = db.scalars(stmt.order_by((Alert.status == "encerrado"), sev_order, Alert.last_seen_at.desc())
                      .offset(off).limit(size)).all()
    return Page(items=[alert_out(db, a) for a in rows], total=total, page=page, page_size=size)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut, summary="Reconhecer alerta")
def acknowledge(alert_id: int, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("gestor"))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "alerta não encontrado")
    if a.status != "aberto":
        raise HTTPException(409, f"alerta já está {a.status}")
    a.status, a.acknowledged_at, a.acknowledged_by = "reconhecido", datetime.now(UTC), user.id
    audit(db, request, user, "reconhecer", "alert", a.id)
    db.commit()
    return alert_out(db, a)


@router.post("/alerts/{alert_id}/close", response_model=AlertOut, summary="Encerrar ocorrência")
def close(alert_id: int, body: AlertAction, request: Request, db: Session = Depends(get_db),
          user: User = Depends(require("gestor")), publish: Publisher = Depends(get_publisher)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "alerta não encontrado")
    if a.status == "encerrado":
        raise HTTPException(409, "alerta já está encerrado")
    a.status, a.closed_at, a.closed_by = "encerrado", datetime.now(UTC), user.id
    a.close_reason = body.reason or "encerrado manualmente"
    audit(db, request, user, "encerrar", "alert", a.id, {"motivo": a.close_reason})
    db.commit()
    publish(topics.EVENT_ALERT_CLOSED, {"v": 1, "type": "alerta.encerrado", "alert_id": str(a.id),
                                        "reason": a.close_reason, "is_simulated": a.is_simulated})
    return alert_out(db, a)


# ------------------------------------------------------------------ parâmetros
@router.get("/quality-parameters", response_model=list[ParameterOut], summary="Parâmetros de qualidade")
def list_parameters(include_history: bool = False, db: Session = Depends(get_db),
                    _: User = Depends(require("leitura"))):
    stmt = select(QualityParameter)
    if not include_history:
        stmt = stmt.where(QualityParameter.valid_to.is_(None))
    return db.scalars(stmt.order_by(QualityParameter.parameter, QualityParameter.context,
                                    QualityParameter.valid_from.desc())).all()


@router.post("/quality-parameters", response_model=ParameterOut, status_code=201,
             summary="Nova versão de um parâmetro (a anterior deixa de valer)")
def new_parameter(body: ParameterIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("admin"))):
    start = body.valid_from or datetime.now(UTC)
    current = db.scalar(select(QualityParameter).where(
        QualityParameter.parameter == body.parameter, QualityParameter.context == body.context,
        QualityParameter.valid_to.is_(None)))
    if current:
        if start <= current.valid_from:
            raise HTTPException(422, "a nova vigência precisa começar depois da atual")
        current.valid_to = start
        db.flush()
    p = QualityParameter(**body.model_dump(exclude={"valid_from"}), valid_from=start, updated_by=user.id)
    db.add(p)
    db.flush()
    audit(db, request, user, "nova_versao", "quality_parameter", p.id,
          {"parameter": p.parameter, "context": p.context, "min": str(p.minimum_value),
           "max": str(p.maximum_value), "anterior": current.id if current else None})
    db.commit()
    return p


# ------------------------------------------------------------------ telemetria
@router.get("/devices/{device_id}/readings", response_model=list[TelemetryOut], summary="Últimas leituras")
def device_readings(device_id: str, limit: int = Query(50, le=1000), db: Session = Depends(get_db),
                    _: User = Depends(require("leitura"))):
    if not db.get(Device, device_id):
        raise HTTPException(404, "dispositivo não encontrado")
    rows = db.scalars(select(Telemetry).where(Telemetry.device_id == device_id)
                      .order_by(Telemetry.received_at.desc(), Telemetry.id.desc()).limit(limit)).all()
    return rows


@router.get("/live", summary="Estado atual de cada dispositivo para a tela de tempo real")
def live(db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    settings = get_settings()
    now = datetime.now(UTC)
    out = []
    for d in db.scalars(select(Device).order_by(Device.is_simulated, Device.id)).all():
        last = db.scalar(select(Telemetry).where(
            Telemetry.device_id == d.id, Telemetry.validation_status.in_(("valid", "partial")))
            .order_by(Telemetry.measured_at.desc()).limit(1))
        trip = db.scalar(select(Trip).where(Trip.vehicle_id == d.vehicle_id, Trip.status == "em_andamento")) \
            if d.vehicle_id else None
        sample = db.scalar(select(QualitySample).where(QualitySample.trip_id == trip.id)
                           .order_by(QualitySample.collected_at.desc()).limit(1)) if trip else None
        age = (now - last.measured_at).total_seconds() if last and last.measured_at else None
        out.append({
            "device_id": d.id, "is_simulated": d.is_simulated, "connection_status": d.connection_status,
            "firmware_version": d.firmware_version, "last_status": d.last_status, "last_seen_at": d.last_seen_at,
            "vehicle_plate": d.vehicle.plate if d.vehicle else None,
            "trip": {"id": trip.id, "code": trip.code} if trip else None,
            "last_reading": TelemetryOut.model_validate(last).model_dump() if last else None,
            "reading_age_s": round(age) if age is not None else None,
            "is_live": age is not None and age <= settings.live_window_s and d.connection_status == "online",
            "last_sample": {"acidity_dornic": sample.acidity_dornic, "collected_at": sample.collected_at,
                            "producer": sample.producer} if sample else None,
        })
    return {"live_window_s": settings.live_window_s, "server_time": now, "devices": out}


# ------------------------------------------------------------------ auditoria
@router.get("/audit", response_model=Page[AuditOut], summary="Log de auditoria")
def list_audit(page: int = 1, page_size: int = 50, db: Session = Depends(get_db),
               _: User = Depends(require("admin"))):
    total = db.scalar(select(func.count()).select_from(AuditLog))
    off, size = paginate(page, page_size)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).offset(off).limit(size)).all()
    return Page(items=rows, total=total, page=page, page_size=size)


# ------------------------------------------------------------------ WebSocket
@router.websocket("/ws")
async def websocket(ws: WebSocket, token: str | None = None):
    """Tempo real: leituras, estado dos dispositivos e eventos. Autentica pelo token na URL."""
    try:
        with SessionLocal() as db:
            user_from_token(db, token)
    except HTTPException:
        await ws.close(code=4401)
        return
    await ws.accept()
    hub = ws.app.state.hub
    hub.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "server_time": datetime.now(UTC).isoformat()})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=60)
            except TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
