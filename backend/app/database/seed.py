"""Carga inicial idempotente (pode rodar a cada inicialização).

- Usuário administrador a partir de ADMIN_EMAIL / ADMIN_PASSWORD (nunca no código).
- Parâmetros de qualidade da Tabela 1 do relatório, marcados "a revisar".
- Com SEED_DEMO=true: um caminhão real de demonstração (esp32-001) e um caminhão de
  teste SIMULADO (sim-001) com uma viagem simulada em andamento para o simulador.

Executar:  python -m app.database.seed
"""
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import Device, Driver, QualityParameter, Trip, User, Vehicle

log = logging.getLogger("seed")

FONTE = "Relatório do grupo, Tabela 1 (ref. IN MAPA nº 76 e 77/2018) — conferir na norma"
# Vigência desde a publicação das INs 76/77, para valer também para dados históricos.
VIGENCIA = datetime(2018, 11, 26, tzinfo=UTC)

PARAMETROS = [
    # parameter, context, min, max, unit
    ("ph", "coleta", "6.6", "6.8", "pH"),
    ("ph", "transporte", "6.6", "6.8", "pH"),
    ("acidity_dornic", "coleta", "14", "18", "°D"),
    ("density", "coleta", "1.028", "1.034", "g/mL"),
    ("milk_temperature", "coleta", None, "7", "°C"),
    ("milk_temperature", "transporte", None, "7", "°C"),
    ("milk_temperature", "recepcao", None, "10", "°C"),
]


def _dec(v: str | None) -> Decimal | None:
    return Decimal(v) if v is not None else None


def seed_admin(db: Session) -> None:
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        log.warning("ADMIN_EMAIL/ADMIN_PASSWORD não definidos: nenhum administrador criado")
        return
    if db.scalar(select(User).where(User.email == s.admin_email.lower())):
        return
    if len(s.admin_password) < 10:
        raise SystemExit("ADMIN_PASSWORD precisa ter pelo menos 10 caracteres")
    db.add(User(name=s.admin_name, email=s.admin_email.lower(),
                password_hash=hash_password(s.admin_password), role="admin"))
    log.info("administrador %s criado", s.admin_email)


def seed_parameters(db: Session) -> None:
    for param, ctx, mn, mx, unit in PARAMETROS:
        exists = db.scalar(select(QualityParameter).where(
            QualityParameter.parameter == param, QualityParameter.context == ctx,
            QualityParameter.valid_to.is_(None)))
        if exists:
            continue
        db.add(QualityParameter(parameter=param, context=ctx, minimum_value=_dec(mn),
                                maximum_value=_dec(mx), unit=unit, source_reference=FONTE,
                                needs_review=True, valid_from=VIGENCIA))
        log.info("parâmetro %s/%s criado", param, ctx)


def seed_demo(db: Session) -> None:
    def vehicle(plate, model, cap, simulated):
        v = db.scalar(select(Vehicle).where(Vehicle.plate == plate))
        if not v:
            v = Vehicle(plate=plate, model=model, capacity_liters=cap, is_simulated=simulated)
            db.add(v)
            db.flush()
        return v

    def driver(doc, name):
        d = db.scalar(select(Driver).where(Driver.document == doc))
        if not d:
            d = Driver(name=name, document=doc)
            db.add(d)
            db.flush()
        return d

    def device(dev_id, v, simulated):
        d = db.get(Device, dev_id)
        if not d:
            d = Device(id=dev_id, vehicle_id=v.id, is_simulated=simulated,
                       serial_number="T-Beam V1.2" if not simulated else "simulador")
            db.add(d)
            db.flush()
        return d

    real = vehicle("TBM1A01", "Caminhão-tanque de demonstração (T-Beam)", 12000, False)
    sim = vehicle("SIM0A01", "Caminhão de teste (SIMULADO)", 10000, True)
    driver("DEMO-001", "Motorista de demonstração")
    dsim = driver("SIM-001", "Motorista simulado")
    device("esp32-001", real, False)
    device("sim-001", sim, True)

    active = db.scalar(select(Trip).where(Trip.vehicle_id == sim.id, Trip.status == "em_andamento"))
    if not active and not db.scalar(select(Trip).where(Trip.code == "SIM-0001")):
        db.add(Trip(code="SIM-0001", vehicle_id=sim.id, driver_id=dsim.id,
                    origin="Propriedade de teste (simulada)", destination="Laticínio de teste",
                    volume_liters=8000, departure_at=datetime.now(UTC), status="em_andamento",
                    is_simulated=True, notes="Viagem do simulador de hardware. Dados SIMULADOS."))
        log.info("viagem simulada SIM-0001 criada")


def run() -> None:
    configure_logging(get_settings().log_level)
    with SessionLocal() as db, db.begin():
        seed_admin(db)
        seed_parameters(db)
        if get_settings().seed_demo:
            seed_demo(db)
    log.info("carga inicial concluída")


if __name__ == "__main__":
    run()
