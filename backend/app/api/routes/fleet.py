"""Veículos, motoristas e dispositivos."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import audit, get_db, paginate, require
from app.models import Device, Driver, Trip, User, Vehicle
from app.schemas.api import (
    DeviceIn,
    DeviceOut,
    DeviceUpdate,
    DriverIn,
    DriverOut,
    DriverUpdate,
    Page,
    TripOut,
    VehicleIn,
    VehicleOut,
    VehicleUpdate,
)
from app.services.serializers import trip_out

router = APIRouter(prefix="/api/v1", tags=["Frota"])


def vehicle_out(v: Vehicle) -> VehicleOut:
    out = VehicleOut.model_validate(v)
    out.device_id = v.device.id if v.device else None
    return out


def device_out(d: Device) -> DeviceOut:
    out = DeviceOut.model_validate(d)
    out.vehicle_plate = d.vehicle.plate if d.vehicle else None
    return out


# ------------------------------------------------------------------ veículos
@router.get("/vehicles", response_model=Page[VehicleOut], summary="Listar veículos")
def list_vehicles(page: int = 1, page_size: int = 50, q: str | None = Query(None, max_length=80),
                  status: str | None = None, include_simulated: bool = True,
                  db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    stmt = select(Vehicle)
    if q:
        stmt = stmt.where(or_(Vehicle.plate.ilike(f"%{q}%"), Vehicle.model.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Vehicle.status == status)
    if not include_simulated:
        stmt = stmt.where(Vehicle.is_simulated.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    items = db.scalars(stmt.order_by(Vehicle.plate).offset(off).limit(size)).all()
    return Page(items=[vehicle_out(v) for v in items], total=total, page=page, page_size=size)


@router.post("/vehicles", response_model=VehicleOut, status_code=201, summary="Cadastrar veículo")
def create_vehicle(body: VehicleIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("gestor"))):
    if db.scalar(select(Vehicle).where(Vehicle.plate == body.plate)):
        raise HTTPException(409, "já existe um veículo com essa placa")
    v = Vehicle(**body.model_dump())
    db.add(v)
    db.flush()
    audit(db, request, user, "criar", "vehicle", v.id, body.model_dump())
    db.commit()
    return vehicle_out(v)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut, summary="Detalhar veículo")
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "veículo não encontrado")
    return vehicle_out(v)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut, summary="Alterar veículo")
def update_vehicle(vehicle_id: int, body: VehicleUpdate, request: Request,
                   db: Session = Depends(get_db), user: User = Depends(require("gestor"))):
    v = db.get(Vehicle, vehicle_id)
    if not v:
        raise HTTPException(404, "veículo não encontrado")
    changes = body.model_dump(exclude_none=True)
    for k, val in changes.items():
        setattr(v, k, val)
    audit(db, request, user, "alterar", "vehicle", v.id, changes)
    db.commit()
    return vehicle_out(v)


@router.get("/vehicles/{vehicle_id}/trips", response_model=list[TripOut], summary="Viagens do veículo")
def vehicle_trips(vehicle_id: int, limit: int = Query(20, le=200), db: Session = Depends(get_db),
                  _: User = Depends(require("leitura"))):
    trips = db.scalars(select(Trip).where(Trip.vehicle_id == vehicle_id)
                       .order_by(Trip.departure_at.desc().nulls_first(), Trip.id.desc()).limit(limit)).all()
    return [trip_out(db, t) for t in trips]


# ------------------------------------------------------------------ motoristas
@router.get("/drivers", response_model=Page[DriverOut], summary="Listar motoristas")
def list_drivers(page: int = 1, page_size: int = 50, q: str | None = Query(None, max_length=80),
                 status: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(require("leitura"))):
    stmt = select(Driver)
    if q:
        stmt = stmt.where(or_(Driver.name.ilike(f"%{q}%"), Driver.document.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Driver.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    off, size = paginate(page, page_size)
    items = db.scalars(stmt.order_by(Driver.name).offset(off).limit(size)).all()
    return Page(items=items, total=total, page=page, page_size=size)


@router.post("/drivers", response_model=DriverOut, status_code=201, summary="Cadastrar motorista")
def create_driver(body: DriverIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("gestor"))):
    if db.scalar(select(Driver).where(Driver.document == body.document)):
        raise HTTPException(409, "já existe um motorista com esse documento")
    d = Driver(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, request, user, "criar", "driver", d.id, {"name": d.name})
    db.commit()
    return d


@router.patch("/drivers/{driver_id}", response_model=DriverOut, summary="Alterar motorista")
def update_driver(driver_id: int, body: DriverUpdate, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(require("gestor"))):
    d = db.get(Driver, driver_id)
    if not d:
        raise HTTPException(404, "motorista não encontrado")
    changes = body.model_dump(exclude_none=True)
    for k, val in changes.items():
        setattr(d, k, val)
    audit(db, request, user, "alterar", "driver", d.id, changes)
    db.commit()
    return d


# ------------------------------------------------------------------ dispositivos
@router.get("/devices", response_model=list[DeviceOut], summary="Listar dispositivos e estado da conexão")
def list_devices(db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    return [device_out(d) for d in db.scalars(select(Device).order_by(Device.id)).all()]


@router.get("/devices/{device_id}", response_model=DeviceOut, summary="Detalhar dispositivo")
def get_device(device_id: str, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "dispositivo não encontrado")
    return device_out(d)


@router.post("/devices", response_model=DeviceOut, status_code=201, summary="Cadastrar dispositivo")
def create_device(body: DeviceIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require("admin"))):
    if db.get(Device, body.id):
        raise HTTPException(409, "já existe um dispositivo com esse id")
    if body.vehicle_id is not None:
        if not db.get(Vehicle, body.vehicle_id):
            raise HTTPException(404, "veículo não encontrado")
        if db.scalar(select(Device).where(Device.vehicle_id == body.vehicle_id)):
            raise HTTPException(409, "esse veículo já tem um dispositivo")
    d = Device(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, request, user, "criar", "device", d.id, body.model_dump())
    db.commit()
    db.refresh(d)
    return device_out(d)


@router.patch("/devices/{device_id}", response_model=DeviceOut, summary="Alterar ou associar dispositivo")
def update_device(device_id: str, body: DeviceUpdate, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(require("admin"))):
    d = db.get(Device, device_id)
    if not d:
        raise HTTPException(404, "dispositivo não encontrado")
    if body.serial_number is not None:
        d.serial_number = body.serial_number
    if body.unassign:
        d.vehicle_id = None
    elif body.vehicle_id is not None:
        if not db.get(Vehicle, body.vehicle_id):
            raise HTTPException(404, "veículo não encontrado")
        d.vehicle_id = body.vehicle_id
    try:
        audit(db, request, user, "alterar", "device", d.id, body.model_dump(exclude_none=True))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "esse veículo já tem um dispositivo") from None
    db.refresh(d)
    return device_out(d)
