from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, Device, QualitySample, Trip
from app.schemas.api import AlertOut, SampleOut, TripOut


def trip_out(db: Session, t: Trip) -> TripOut:
    out = TripOut.model_validate(t)
    out.vehicle_plate = t.vehicle.plate if t.vehicle else None
    out.driver_name = t.driver.name if t.driver else None
    dev = db.scalar(select(Device.id).where(Device.vehicle_id == t.vehicle_id))
    out.device_id = dev
    out.open_alerts = db.scalar(
        select(func.count()).select_from(Alert).where(Alert.trip_id == t.id, Alert.status != "encerrado")
    ) or 0
    return out


def alert_out(db: Session, a: Alert) -> AlertOut:
    out = AlertOut.model_validate(a)
    if a.trip_id:
        out.trip_code = db.scalar(select(Trip.code).where(Trip.id == a.trip_id))
    return out


def sample_out(db: Session, s: QualitySample, out_of_range: list[str] | None = None) -> SampleOut:
    out = SampleOut.model_validate(s)
    out.trip_code = db.scalar(select(Trip.code).where(Trip.id == s.trip_id))
    if out_of_range is not None:
        out.out_of_range = out_of_range
    return out
