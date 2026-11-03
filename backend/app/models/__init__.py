"""Modelos SQLAlchemy (tabelas)."""
from app.models.base import Base
from app.models.entities import (
    Alert,
    AuditLog,
    Device,
    DeviceStatusEvent,
    Driver,
    QualityParameter,
    QualitySample,
    RejectedMessage,
    Telemetry,
    Trip,
    User,
    Vehicle,
)

__all__ = [
    "Alert", "AuditLog", "Base", "Device", "DeviceStatusEvent", "Driver", "QualityParameter",
    "QualitySample", "RejectedMessage", "Telemetry", "Trip", "User", "Vehicle",
]
