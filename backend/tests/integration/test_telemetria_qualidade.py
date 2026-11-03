"""Gravação da telemetria (api) e regras de qualidade (quality), contra o PostgreSQL."""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.database.session import SessionLocal
from app.models import Alert, Device, Driver, RejectedMessage, Telemetry, Trip, Vehicle
from app.services.ingest import Ingestor
from app.workers.quality import QualityWorker

pytestmark = pytest.mark.integration
T = "smartmilk/device/{}/telemetry"


@pytest.fixture
def setup(db):
    v = Vehicle(plate="ABC1D23", model="Tanque", capacity_liters=10000)
    vs = Vehicle(plate="SIM0A01", model="Teste", capacity_liters=10000, is_simulated=True)
    d = Driver(name="João", document="1")
    db.add_all([v, vs, d])
    db.flush()
    db.add_all([Device(id="esp32-001", vehicle_id=v.id), Device(id="sim-001", vehicle_id=vs.id, is_simulated=True)])
    now = datetime.now(UTC)
    old = Trip(code="VG-0001", vehicle_id=v.id, driver_id=d.id, origin="A", destination="B",
               departure_at=now - timedelta(days=1, hours=6), arrival_at=now - timedelta(days=1),
               status="finalizada")
    cur = Trip(code="VG-0002", vehicle_id=v.id, driver_id=d.id, origin="A", destination="B",
               departure_at=now - timedelta(hours=2), status="em_andamento")
    db.add_all([old, cur])
    db.commit()
    return {"old": old.id, "cur": cur.id, "now": now}


@pytest.fixture
def ing():
    published, broadcast = [], []
    i = Ingestor(SessionLocal, lambda t, p: published.append((t, p)), broadcast.append)
    i.published, i.broadcasted = published, broadcast
    return i


def msg(seq, at, device="esp32-001", **readings):
    r = {"ph": 6.7, "ph_voltage": 2.554, "milk_temperature": 4.1, "air_temperature": 21.0, "air_humidity": 60.0}
    r.update(readings)
    return json.dumps({"v": 1, "msg_id": f"{device}-00001-{seq:09d}", "device_id": device,
                       "measured_at": at.isoformat() if at else None, "time_source": "ntp" if at else "none",
                       "readings": r, "sensor_flags": 0, "gps": {"lat": -28.38, "lon": -53.91, "fix": True},
                       "buffered": False, "simulated": device.startswith("sim")}).encode()


def rows(db):
    db.expire_all()
    return db.scalars(select(Telemetry).order_by(Telemetry.id)).all()


# ---------------------------------------------------------------- gravação
def test_leitura_valida_gravada_associada_e_avisada(db, setup, ing):
    tid = ing.handle(T.format("esp32-001"), msg(1, setup["now"])) or rows(db)[0].id
    r = rows(db)[0]
    assert r.id == tid and r.trip_id == setup["cur"] and r.validation_status == "valid"
    assert r.ph == Decimal("6.7") and r.received_at is not None
    assert ing.published[0][1]["type"] == "leitura.gravada"
    assert ing.broadcasted[0]["type"] == "telemetry"


def test_retransmissao_nao_duplica(db, setup, ing):
    for _ in range(3):
        ing.handle(T.format("esp32-001"), msg(7, setup["now"]))
    assert len(rows(db)) == 1 and len(ing.published) == 1


def test_leitura_atrasada_cai_na_viagem_certa(db, setup, ing):
    ontem = setup["now"] - timedelta(days=1, hours=3)
    ing.handle(T.format("esp32-001"), msg(2, ontem))
    assert rows(db)[0].trip_id == setup["old"]


def test_campo_impossivel_vira_parcial(db, setup, ing):
    ing.handle(T.format("esp32-001"), msg(3, setup["now"], ph=15.2))
    r = rows(db)[0]
    assert r.validation_status == "partial" and r.ph is None and r.milk_temperature == Decimal("4.1")
    assert r.validation_errors[0]["field"] == "ph"


def test_sem_horario_nao_entra_em_graficos(db, setup, ing):
    ing.handle(T.format("esp32-001"), msg(4, None))
    r = rows(db)[0]
    assert r.validation_status == "time_unknown" and r.trip_id == setup["cur"]


@pytest.mark.parametrize(("topic_dev", "payload", "motivo"), [
    ("esp32-999", msg(1, datetime.now(UTC), device="esp32-999"), "não cadastrado"),
    ("esp32-001", msg(1, datetime.now(UTC), device="sim-001"), "diferente do tópico"),
    ("esp32-001", b"isto nao e json", "payload inválido"),
])
def test_mensagens_rejeitadas(db, setup, ing, topic_dev, payload, motivo):
    ing.handle(T.format(topic_dev), payload)
    assert rows(db) == []
    rej = db.scalars(select(RejectedMessage)).all()
    assert len(rej) == 1 and motivo in rej[0].reason


def test_simulado_precisa_bater_com_o_cadastro(db, setup, ing):
    body = json.loads(msg(1, datetime.now(UTC)))
    body["simulated"] = True  # dispositivo real dizendo que é simulado
    ing.handle(T.format("esp32-001"), json.dumps(body).encode())
    assert rows(db) == []


def test_telemetria_e_imutavel(db, setup, ing):
    ing.handle(T.format("esp32-001"), msg(1, setup["now"]))
    with pytest.raises(Exception, match="somente inserção"):
        db.execute(text("DELETE FROM telemetry"))
    db.rollback()


def test_estado_e_last_will(db, setup, ing):
    ing.handle("smartmilk/device/esp32-001/status", b'{"v":1,"device_id":"esp32-001","state":"online","fw":"0.2.0"}')
    ing.handle("smartmilk/device/esp32-001/status", b'{"v":1,"device_id":"esp32-001","state":"offline","reason":"lwt"}')
    db.expire_all()
    dev = db.get(Device, "esp32-001")
    assert dev.connection_status == "offline" and dev.firmware_version == "0.2.0"


# ---------------------------------------------------------------- regras de qualidade
class FakeMqtt:
    def __init__(self):
        self.sent = []
        self.connected = True

    def publish_json(self, topic, payload, **_):
        self.sent.append((topic, payload))


@pytest.fixture
def worker():
    w = QualityWorker(Settings(mqtt_service_password="x", quality_open_after=2, quality_close_after=3,
                               no_data_minutes=5, invalid_streak=3))
    w.mqtt = FakeMqtt()
    return w


def feed(db, ing, worker, start_seq, temps, start):
    for i, temp in enumerate(temps):
        ing.handle(T.format("esp32-001"), msg(start_seq + i, start + timedelta(seconds=5 * i), milk_temperature=temp))
        worker.evaluate(db, rows(db)[-1].id)


def test_um_pico_isolado_nao_abre_alerta(db, setup, ing, worker):
    feed(db, ing, worker, 1, [4.0, 7.4, 4.1, 4.0], setup["now"] - timedelta(minutes=10))
    assert db.scalars(select(Alert)).all() == []


def test_ruptura_do_frio_abre_um_alerta_e_encerra_com_histerese(db, setup, ing, worker):
    base = setup["now"] - timedelta(minutes=10)
    feed(db, ing, worker, 1, [7.3, 7.6, 7.8, 7.5], base)  # 4 fora: abre 1 alerta, conta 3 ocorrências
    db.expire_all()
    alerts = db.scalars(select(Alert)).all()
    assert len(alerts) == 1 and alerts[0].severity == "critico" and alerts[0].occurrences == 3
    assert [t for t, _ in worker.mqtt.sent] == ["smartmilk/events/alerta.aberto"]
    feed(db, ing, worker, 10, [6.9, 6.8, 6.8], base + timedelta(minutes=1))  # dentro, mas sem folga de 0,3
    db.expire_all()
    assert db.scalars(select(Alert)).one().status == "aberto"
    feed(db, ing, worker, 20, [5.0, 4.8, 4.6], base + timedelta(minutes=2))  # 3 de volta com folga: encerra
    db.expire_all()
    a = db.scalars(select(Alert)).one()
    assert a.status == "encerrado" and a.close_reason == "voltou à faixa de referência"
    assert worker.mqtt.sent[-1][1]["type"] == "alerta.encerrado"


def test_leituras_invalidas_seguidas(db, setup, ing, worker):
    for i in range(3):
        ing.handle(T.format("esp32-001"), msg(30 + i, setup["now"], ph=None, milk_temperature=None,
                                               air_temperature=None, air_humidity=None))
        worker.evaluate(db, rows(db)[-1].id)
    db.expire_all()
    assert db.scalars(select(Alert)).one().type == "dados_invalidos"


def test_viagem_sem_leitura_abre_alerta(db, setup, worker):
    worker.periodic(db, now=setup["now"])
    db.expire_all()
    a = db.scalars(select(Alert).where(Alert.type == "sem_leitura")).one()
    assert "não significa que o leite está normal" in a.description


def test_atraso_e_dispositivo_offline(db, setup, worker):
    t = db.get(Trip, setup["cur"])
    t.expected_arrival_at = setup["now"] - timedelta(minutes=30)
    db.get(Device, "esp32-001").connection_status = "offline"
    db.commit()
    worker.periodic(db, now=setup["now"])
    db.expire_all()
    tipos = {a.type for a in db.scalars(select(Alert)).all()}
    assert {"atraso", "dispositivo_offline", "sem_leitura"} <= tipos
    worker.periodic(db, now=setup["now"])  # rodar de novo não duplica
    db.expire_all()
    assert len(db.scalars(select(Alert)).all()) == len(tipos)
