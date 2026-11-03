"""Parâmetros de qualidade vigentes e abertura/encerramento de alertas.

Usado pela api (coletas manuais, comunicação) e pelo worker quality (telemetria).
Um alerta é identificado pelo `fingerprint`: enquanto houver um aberto/reconhecido com
o mesmo fingerprint, novas ocorrências só atualizam contagem e horário (deduplicação).
"""
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Alert, QualityParameter

PARAM_LABEL = {
    "ph": "pH",
    "milk_temperature": "Temperatura do leite",
    "acidity_dornic": "Acidez titulável",
    "density": "Densidade",
}

# Publica um evento (tópico, payload). A api e o quality injetam o seu publicador MQTT.
EventPublisher = Callable[[str, dict], None]


def active_parameter(db: Session, parameter: str, context: str, at: datetime | None = None) -> QualityParameter | None:
    at = at or datetime.now(UTC)
    return db.scalar(
        select(QualityParameter)
        .where(QualityParameter.parameter == parameter, QualityParameter.context == context,
               QualityParameter.valid_from <= at,
               or_(QualityParameter.valid_to.is_(None), QualityParameter.valid_to > at))
        .order_by(QualityParameter.valid_from.desc())
        .limit(1)
    )


def out_of_range(param: QualityParameter, value: Decimal | float | None) -> bool:
    if value is None:
        return False
    v = Decimal(str(value))
    if param.minimum_value is not None and v < param.minimum_value:
        return True
    return param.maximum_value is not None and v > param.maximum_value


def inside_with_margin(param: QualityParameter, value: Decimal | float, margin: Decimal) -> bool:
    """Volta à faixa com folga (histerese): evita abrir e fechar a cada oscilação na borda."""
    v = Decimal(str(value))
    if param.minimum_value is not None and v < param.minimum_value + margin:
        return False
    return not (param.maximum_value is not None and v > param.maximum_value - margin)


def describe_range(param: QualityParameter) -> str:
    mn, mx = param.minimum_value, param.maximum_value
    if mn is not None and mx is not None:
        return f"{_fmt(mn)} a {_fmt(mx)} {param.unit}"
    if mx is not None:
        return f"≤ {_fmt(mx)} {param.unit}"
    return f"≥ {_fmt(mn)} {param.unit}"


def _fmt(v: Decimal) -> str:
    return f"{v.normalize():f}".replace(".", ",")


def open_or_update(
    db: Session, *, fingerprint: str, type: str, severity: str, title: str, description: str,
    trip_id: int | None = None, device_id: str | None = None, parameter: str | None = None,
    qparam: QualityParameter | None = None, value: Decimal | float | None = None,
    is_simulated: bool = False, at: datetime | None = None,
) -> tuple[Alert, bool]:
    """Abre um alerta ou, se já houver um ativo com o mesmo fingerprint, atualiza-o.

    Retorna (alerta, criado_agora). Quem chama faz o commit e publica o evento se criado.
    """
    at = at or datetime.now(UTC)
    existing = db.scalar(select(Alert).where(Alert.fingerprint == fingerprint, Alert.status != "encerrado"))
    if existing:
        existing.occurrences += 1
        existing.last_seen_at = at
        if value is not None:
            existing.measured_value = Decimal(str(value))
        if _rank(severity) > _rank(existing.severity):
            existing.severity = severity
        return existing, False
    alert = Alert(
        fingerprint=fingerprint, type=type, severity=severity, title=title, description=description,
        trip_id=trip_id, device_id=device_id, parameter=parameter,
        quality_parameter_id=qparam.id if qparam else None,
        reference_min=qparam.minimum_value if qparam else None,
        reference_max=qparam.maximum_value if qparam else None,
        measured_value=Decimal(str(value)) if value is not None else None,
        is_simulated=is_simulated, first_seen_at=at, last_seen_at=at,
    )
    db.add(alert)
    db.flush()
    return alert, True


def close_active(db: Session, fingerprint: str, reason: str, at: datetime | None = None) -> Alert | None:
    alert = db.scalar(select(Alert).where(Alert.fingerprint == fingerprint, Alert.status != "encerrado"))
    if alert:
        alert.status = "encerrado"
        alert.closed_at = at or datetime.now(UTC)
        alert.close_reason = reason
    return alert


def alert_event(alert: Alert, trip_code: str | None) -> dict:
    return {
        "v": 1, "type": "alerta.aberto", "alert_id": str(alert.id),
        "at": alert.first_seen_at.isoformat(), "severity": alert.severity, "title": alert.title,
        "description": alert.description, "trip_code": trip_code, "device_id": alert.device_id,
        "is_simulated": alert.is_simulated,
    }


def _rank(sev: str) -> int:
    return {"info": 0, "atencao": 1, "critico": 2}[sev]
