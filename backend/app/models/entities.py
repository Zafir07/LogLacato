"""Tabelas do LogLacto (Etapa 2). Ver docs/architecture/modelo-dados.md.

Regras que o banco garante:
- telemetria e coletas só recebem INSERT (gatilho na migration impede UPDATE/DELETE);
- uma leitura por (device_id, msg_id): retransmissões não duplicam;
- um veículo só tem uma viagem em andamento por vez;
- um alerta aberto por ocorrência (fingerprint), o resto vira contagem;
- faixas físicas (pH 0–14, umidade 0–100…) como CHECK. As faixas de QUALIDADE ficam
  em quality_parameters, nunca no esquema.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, in_check, utcnow

ROLES = ("admin", "gestor", "coletor", "leitura")
VEHICLE_STATUS = ("ativo", "manutencao", "inativo")
DRIVER_STATUS = ("ativo", "inativo")
TRIP_STATUS = ("planejada", "em_andamento", "finalizada", "cancelada")
SAMPLE_DECISION = ("aceito", "recusado", "reclassificado")
TIME_SOURCES = ("ntp", "gps", "estimated", "none")
VALIDATION = ("valid", "partial", "invalid", "time_unknown")
PARAMETERS = ("ph", "milk_temperature", "acidity_dornic", "density")
CONTEXTS = ("coleta", "transporte", "recepcao")
SEVERITY = ("info", "atencao", "critico")
ALERT_STATUS = ("aberto", "reconhecido", "encerrado")
ALERT_TYPES = ("qualidade", "sem_leitura", "dispositivo_offline", "dados_invalidos", "atraso", "sensor")


def ts(**kw) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(in_check("role", ROLES), name="role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(in_check("status", VEHICLE_STATUS), name="status"),
        CheckConstraint("capacity_liters > 0", name="capacity_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate: Mapped[str] = mapped_column(String(10), unique=True)
    model: Mapped[str] = mapped_column(String(120))
    capacity_liters: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))

    device: Mapped["Device | None"] = relationship(back_populates="vehicle", uselist=False)


class Driver(Base):
    __tablename__ = "drivers"
    __table_args__ = (CheckConstraint(in_check("status", DRIVER_STATUS), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    document: Mapped[str] = mapped_column(String(30), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))


class Device(Base):
    """Dispositivo no caminhão. O id é o usuário MQTT (ex.: esp32-001)."""

    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(in_check("connection_status", ("online", "offline", "desconhecido")), name="conn"),
        CheckConstraint("id ~ '^[a-z0-9][a-z0-9-]{1,39}$' AND id NOT LIKE 'svc-%'", name="id_format"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    serial_number: Mapped[str | None] = mapped_column(String(60))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id", ondelete="SET NULL"), unique=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    connection_status: Mapped[str] = mapped_column(String(20), default="desconhecido", server_default="desconhecido")
    last_seen_at: Mapped[datetime | None] = ts()
    firmware_version: Mapped[str | None] = mapped_column(String(40))
    last_status: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))

    vehicle: Mapped[Vehicle | None] = relationship(back_populates="device")


class Trip(Base):
    """Viagem. Não há roteirização: a rota real é o rastro do GPS da telemetria."""

    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint(in_check("status", TRIP_STATUS), name="status"),
        CheckConstraint("volume_liters IS NULL OR volume_liters >= 0", name="volume"),
        CheckConstraint("arrival_at IS NULL OR departure_at IS NULL OR arrival_at >= departure_at", name="dates"),
        Index(
            "uq_trips_vehicle_em_andamento", "vehicle_id", unique=True,
            postgresql_where=text("status = 'em_andamento'"),
        ),
        Index("ix_trips_departure", "departure_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    origin: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(160))
    volume_liters: Mapped[int | None] = mapped_column(Integer)
    departure_at: Mapped[datetime | None] = ts()
    expected_arrival_at: Mapped[datetime | None] = ts()
    arrival_at: Mapped[datetime | None] = ts()
    status: Mapped[str] = mapped_column(String(20), default="planejada", server_default="planejada")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))

    vehicle: Mapped[Vehicle] = relationship()
    driver: Mapped[Driver] = relationship()


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint("device_id", "msg_id", name="uq_telemetry_device_msg"),
        CheckConstraint(in_check("time_source", TIME_SOURCES), name="time_source"),
        CheckConstraint(in_check("validation_status", VALIDATION), name="validation"),
        CheckConstraint("ph IS NULL OR ph BETWEEN 0 AND 14", name="ph_range"),
        CheckConstraint("air_humidity IS NULL OR air_humidity BETWEEN 0 AND 100", name="hum_range"),
        CheckConstraint("milk_temperature IS NULL OR milk_temperature BETWEEN -55 AND 125", name="milk_range"),
        CheckConstraint("air_temperature IS NULL OR air_temperature BETWEEN -40 AND 80", name="air_range"),
        Index("ix_telemetry_trip_time", "trip_id", "measured_at"),
        Index("ix_telemetry_device_time", "device_id", text("measured_at DESC")),
        Index("ix_telemetry_received", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id"))
    msg_id: Mapped[str] = mapped_column(String(80))
    measured_at: Mapped[datetime | None] = ts()
    received_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    time_source: Mapped[str] = mapped_column(String(10))
    ph: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    ph_voltage: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    milk_temperature: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    air_temperature: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    air_humidity: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    sensor_flags: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    buffered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    validation_status: Mapped[str] = mapped_column(String(15))
    validation_errors: Mapped[list | None] = mapped_column(JSONB)
    raw_payload: Mapped[dict] = mapped_column(JSONB)


class QualitySample(Base):
    """Coleta registrada pelo coletor: acidez Dornic, densidade, litragem, decisão."""

    __tablename__ = "quality_samples"
    __table_args__ = (
        CheckConstraint(in_check("decision", SAMPLE_DECISION), name="decision"),
        CheckConstraint("acidity_dornic IS NULL OR acidity_dornic BETWEEN 0 AND 60", name="acidity_range"),
        CheckConstraint("density IS NULL OR density BETWEEN 0.9 AND 1.2", name="density_range"),
        CheckConstraint("ph_manual IS NULL OR ph_manual BETWEEN 0 AND 14", name="ph_range"),
        CheckConstraint("volume_liters IS NULL OR volume_liters >= 0", name="volume"),
        Index("ix_samples_trip", "trip_id", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"))
    collected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    collected_at: Mapped[datetime] = ts()
    producer: Mapped[str] = mapped_column(String(160))
    acidity_dornic: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    density: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    volume_liters: Mapped[int | None] = mapped_column(Integer)
    milk_temperature: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    ph_manual: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    seal_code: Mapped[str | None] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    corrects_id: Mapped[int | None] = mapped_column(ForeignKey("quality_samples.id"))
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))


class QualityParameter(Base):
    """Faixa de referência versionada. Mudar um limite = nova linha; a anterior ganha valid_to."""

    __tablename__ = "quality_parameters"
    __table_args__ = (
        CheckConstraint(in_check("parameter", PARAMETERS), name="parameter"),
        CheckConstraint(in_check("context", CONTEXTS), name="context"),
        CheckConstraint(
            "minimum_value IS NOT NULL OR maximum_value IS NOT NULL", name="has_limit"
        ),
        CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL OR minimum_value <= maximum_value", name="order"
        ),
        Index(
            "uq_qparam_vigente", "parameter", "context", unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parameter: Mapped[str] = mapped_column(String(30))
    context: Mapped[str] = mapped_column(String(20))
    minimum_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    maximum_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    unit: Mapped[str] = mapped_column(String(20))
    source_reference: Mapped[str] = mapped_column(String(300))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    valid_from: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    valid_to: Mapped[datetime | None] = ts()
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(in_check("severity", SEVERITY), name="severity"),
        CheckConstraint(in_check("status", ALERT_STATUS), name="status"),
        CheckConstraint(in_check("type", ALERT_TYPES), name="type"),
        Index(
            "uq_alerts_fingerprint_ativo", "fingerprint", unique=True,
            postgresql_where=text("status <> 'encerrado'"),
        ),
        Index("ix_alerts_status_sev", "status", "severity"),
        Index("ix_alerts_trip", "trip_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    parameter: Mapped[str | None] = mapped_column(String(30))
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"))
    quality_parameter_id: Mapped[int | None] = mapped_column(ForeignKey("quality_parameters.id"))
    measured_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    reference_min: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    reference_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(15), default="aberto", server_default="aberto")
    fingerprint: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    occurrences: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    first_seen_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    last_seen_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    created_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    acknowledged_at: Mapped[datetime | None] = ts()
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = ts()
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    close_reason: Mapped[str | None] = mapped_column(String(200))


class DeviceStatusEvent(Base):
    __tablename__ = "device_status_events"
    __table_args__ = (Index("ix_devstatus_device_at", "device_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    state: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict | None] = mapped_column(JSONB)


class RejectedMessage(Base):
    __tablename__ = "rejected_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    topic: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(300))
    payload: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_at", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = ts(default=utcnow, server_default=text("now()"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    details: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
