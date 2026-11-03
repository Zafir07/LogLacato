"""Esquemas de entrada e saída da API (validação com Pydantic)."""
import re
from datetime import datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL.match(v):
        raise ValueError("e-mail inválido")
    return v


# E-mail simples: aceita domínios internos (ex.: @loglacto.local), que o EmailStr recusa.
Email = Annotated[str, AfterValidator(_email)]

Role = Literal["admin", "gestor", "coletor", "leitura"]
VehicleStatus = Literal["ativo", "manutencao", "inativo"]
DriverStatus = Literal["ativo", "inativo"]
TripStatus = Literal["planejada", "em_andamento", "finalizada", "cancelada"]
Decision = Literal["aceito", "recusado", "reclassificado"]
Parameter = Literal["ph", "milk_temperature", "acidity_dornic", "density"]
Context = Literal["coleta", "transporte", "recepcao"]
Severity = Literal["info", "atencao", "critico"]
AlertStatus = Literal["aberto", "reconhecido", "encerrado"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# ------------------------------------------------------------------ auth / users
class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: int
    name: str
    email: str
    role: Role
    active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: Email
    password: str = Field(min_length=10, max_length=200)
    role: Role


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


# ------------------------------------------------------------------ frota
PLATE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")


class VehicleIn(BaseModel):
    plate: str
    model: str = Field(min_length=2, max_length=120)
    capacity_liters: int = Field(gt=0, le=60000)
    status: VehicleStatus = "ativo"
    is_simulated: bool = False

    @field_validator("plate")
    @classmethod
    def _plate(cls, v: str) -> str:
        v = v.upper().replace("-", "").replace(" ", "")
        if not PLATE.match(v):
            raise ValueError("placa inválida (formato ABC1D23 ou ABC1234)")
        return v


class VehicleUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=2, max_length=120)
    capacity_liters: int | None = Field(default=None, gt=0, le=60000)
    status: VehicleStatus | None = None


class VehicleOut(ORM):
    id: int
    plate: str
    model: str
    capacity_liters: int
    status: VehicleStatus
    is_simulated: bool
    device_id: str | None = None
    created_at: datetime


class DriverIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    document: str = Field(min_length=3, max_length=30)
    phone: str | None = Field(default=None, max_length=30)
    status: DriverStatus = "ativo"


class DriverUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)
    status: DriverStatus | None = None


class DriverOut(ORM):
    id: int
    name: str
    document: str
    phone: str | None
    status: DriverStatus
    created_at: datetime


class DeviceIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")
    serial_number: str | None = Field(default=None, max_length=60)
    vehicle_id: int | None = None
    is_simulated: bool = False

    @field_validator("id")
    @classmethod
    def _not_service(cls, v: str) -> str:
        if v.startswith("svc-") or v == "backend":
            raise ValueError("nome reservado para serviços internos")
        return v


class DeviceUpdate(BaseModel):
    serial_number: str | None = Field(default=None, max_length=60)
    vehicle_id: int | None = None
    unassign: bool = False


class DeviceOut(ORM):
    id: str
    serial_number: str | None
    vehicle_id: int | None
    vehicle_plate: str | None = None
    is_simulated: bool
    connection_status: str
    last_seen_at: datetime | None
    firmware_version: str | None
    last_status: dict | None


# ------------------------------------------------------------------ viagens
class TripIn(BaseModel):
    code: str | None = Field(default=None, pattern=r"^[A-Z0-9-]{3,20}$")
    vehicle_id: int
    driver_id: int
    origin: str = Field(min_length=2, max_length=160)
    destination: str = Field(min_length=2, max_length=160)
    volume_liters: int | None = Field(default=None, ge=0, le=60000)
    departure_at: datetime | None = None
    expected_arrival_at: datetime | None = None
    arrival_at: datetime | None = None
    status: TripStatus = "planejada"
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates(self):
        if self.arrival_at and self.departure_at and self.arrival_at < self.departure_at:
            raise ValueError("a chegada não pode ser antes da saída")
        if self.status == "em_andamento" and not self.departure_at:
            raise ValueError("viagem em andamento precisa do horário de saída")
        if self.status == "finalizada" and not (self.departure_at and self.arrival_at):
            raise ValueError("viagem finalizada precisa de saída e chegada")
        return self


class TripUpdate(BaseModel):
    driver_id: int | None = None
    origin: str | None = Field(default=None, min_length=2, max_length=160)
    destination: str | None = Field(default=None, min_length=2, max_length=160)
    volume_liters: int | None = Field(default=None, ge=0, le=60000)
    departure_at: datetime | None = None
    expected_arrival_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class TripFinish(BaseModel):
    arrival_at: datetime | None = None
    volume_liters: int | None = Field(default=None, ge=0, le=60000)


class TripOut(ORM):
    id: int
    code: str
    vehicle_id: int
    vehicle_plate: str | None = None
    driver_id: int
    driver_name: str | None = None
    device_id: str | None = None
    origin: str
    destination: str
    volume_liters: int | None
    departure_at: datetime | None
    expected_arrival_at: datetime | None
    arrival_at: datetime | None
    status: TripStatus
    is_simulated: bool
    notes: str | None
    created_at: datetime
    open_alerts: int = 0


# ------------------------------------------------------------------ coletas
class SampleIn(BaseModel):
    collected_at: datetime
    producer: str = Field(min_length=2, max_length=160)
    acidity_dornic: Decimal | None = Field(default=None, ge=0, le=60)
    density: Decimal | None = Field(default=None, ge=Decimal("0.9"), le=Decimal("1.2"))
    volume_liters: int | None = Field(default=None, ge=0, le=60000)
    milk_temperature: Decimal | None = Field(default=None, ge=-5, le=60)
    ph_manual: Decimal | None = Field(default=None, ge=0, le=14)
    seal_code: str | None = Field(default=None, max_length=40)
    decision: Decision
    notes: str | None = Field(default=None, max_length=2000)
    corrects_id: int | None = None


class SampleOut(ORM):
    id: int
    trip_id: int
    trip_code: str | None = None
    collected_by: int | None
    collected_at: datetime
    producer: str
    acidity_dornic: Decimal | None
    density: Decimal | None
    volume_liters: int | None
    milk_temperature: Decimal | None
    ph_manual: Decimal | None
    seal_code: str | None
    decision: Decision
    notes: str | None
    corrects_id: int | None
    created_at: datetime
    out_of_range: list[str] = []


# ------------------------------------------------------------------ parâmetros
class ParameterIn(BaseModel):
    parameter: Parameter
    context: Context
    minimum_value: Decimal | None = None
    maximum_value: Decimal | None = None
    unit: str = Field(min_length=1, max_length=20)
    source_reference: str = Field(min_length=5, max_length=300)
    needs_review: bool = False
    valid_from: datetime | None = None

    @model_validator(mode="after")
    def _limits(self):
        if self.minimum_value is None and self.maximum_value is None:
            raise ValueError("informe mínimo, máximo ou ambos")
        if (self.minimum_value is not None and self.maximum_value is not None
                and self.minimum_value > self.maximum_value):
            raise ValueError("o mínimo não pode ser maior que o máximo")
        return self


class ParameterOut(ORM):
    id: int
    parameter: Parameter
    context: Context
    minimum_value: Decimal | None
    maximum_value: Decimal | None
    unit: str
    source_reference: str
    needs_review: bool
    valid_from: datetime
    valid_to: datetime | None
    updated_by: int | None


# ------------------------------------------------------------------ alertas
class AlertOut(ORM):
    id: int
    type: str
    parameter: str | None
    trip_id: int | None
    trip_code: str | None = None
    device_id: str | None
    measured_value: Decimal | None
    reference_min: Decimal | None
    reference_max: Decimal | None
    severity: Severity
    status: AlertStatus
    title: str
    description: str
    is_simulated: bool
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None


class AlertAction(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


# ------------------------------------------------------------------ telemetria
class TelemetryOut(ORM):
    id: int
    device_id: str
    trip_id: int | None
    msg_id: str
    measured_at: datetime | None
    received_at: datetime
    time_source: str
    ph: Decimal | None
    ph_voltage: Decimal | None
    milk_temperature: Decimal | None
    air_temperature: Decimal | None
    air_humidity: Decimal | None
    lat: Decimal | None
    lon: Decimal | None
    sensor_flags: int
    buffered: bool
    is_simulated: bool
    validation_status: str
    validation_errors: list | None


class AuditOut(ORM):
    id: int
    at: datetime
    user_id: int | None
    action: str
    entity: str
    entity_id: str | None
    details: dict | None
    ip: str | None
