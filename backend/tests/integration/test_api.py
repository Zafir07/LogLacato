"""API de ponta a ponta contra o PostgreSQL (banco de teste separado)."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.events import get_publisher
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def events():
    return []


@pytest.fixture
def client(db, events):
    app = create_app(start_mqtt=False)
    app.dependency_overrides[get_publisher] = lambda: (lambda topic, payload: events.append((topic, payload)))
    with TestClient(app) as c:
        yield c


def login(client, email="admin@teste.local", password="senha-admin-123") -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client)


def make_user(client, admin, role: str) -> dict:
    email = f"{role}@teste.local"
    r = client.post("/api/v1/users", headers=admin,
                    json={"name": role.title(), "email": email, "password": "senha-forte-123", "role": role})
    assert r.status_code == 201, r.text
    return login(client, email, "senha-forte-123")


@pytest.fixture
def fleet(client, admin):
    v = client.post("/api/v1/vehicles", headers=admin,
                    json={"plate": "abc-1d23", "model": "Tanque 10 mil", "capacity_liters": 10000}).json()
    d = client.post("/api/v1/drivers", headers=admin, json={"name": "João", "document": "123.456.789-00"}).json()
    dev = client.post("/api/v1/devices", headers=admin, json={"id": "esp32-001", "vehicle_id": v["id"]}).json()
    return v, d, dev


# ---------------------------------------------------------------- autenticação
def test_login_errado_e_sem_token(client):
    assert client.post("/api/v1/auth/login", json={"email": "admin@teste.local", "password": "x"}).status_code == 401
    assert client.get("/api/v1/trips").status_code == 401
    assert client.get("/api/v1/trips", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_login_bloqueia_depois_de_5_erros(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "alguem@teste.local", "password": "errada"})
    r = client.post("/api/v1/auth/login", json={"email": "alguem@teste.local", "password": "errada"})
    assert r.status_code == 429


def test_perfis(client, admin):
    leitura = make_user(client, admin, "leitura")
    coletor = make_user(client, admin, "coletor")
    body = {"plate": "XYZ9A99", "model": "Tanque", "capacity_liters": 5000}
    assert client.post("/api/v1/vehicles", headers=leitura, json=body).status_code == 403
    assert client.post("/api/v1/vehicles", headers=coletor, json=body).status_code == 403
    assert client.get("/api/v1/vehicles", headers=leitura).status_code == 200
    assert client.get("/api/v1/users", headers=leitura).status_code == 403
    assert client.get("/api/v1/auth/me", headers=coletor).json()["role"] == "coletor"


def test_admin_nao_se_desativa(client, admin):
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert client.patch(f"/api/v1/users/{me['id']}", headers=admin, json={"active": False}).status_code == 400


# ---------------------------------------------------------------- cadastros
def test_validacoes_de_cadastro(client, admin, fleet):
    v, _, _ = fleet
    assert v["plate"] == "ABC1D23"
    assert client.post("/api/v1/vehicles", headers=admin,
                       json={"plate": "12345", "model": "X", "capacity_liters": 1}).status_code == 422
    assert client.post("/api/v1/vehicles", headers=admin,
                       json={"plate": "ABC1D23", "model": "Outro", "capacity_liters": 1000}).status_code == 409
    assert client.post("/api/v1/devices", headers=admin, json={"id": "svc-quality"}).status_code == 422
    assert client.post("/api/v1/devices", headers=admin,
                       json={"id": "esp32-002", "vehicle_id": v["id"]}).status_code == 409


def test_auditoria_registra_acoes(client, admin, fleet):
    rows = client.get("/api/v1/audit", headers=admin).json()["items"]
    acoes = {(r["action"], r["entity"]) for r in rows}
    assert ("criar", "vehicle") in acoes and ("criar", "device") in acoes and ("login", "user") in acoes


# ---------------------------------------------------------------- viagens
def trip_body(v, d, **kw):
    return {"vehicle_id": v["id"], "driver_id": d["id"], "origin": "Fazenda A", "destination": "Laticínio",
            "volume_liters": 8000, **kw}


def test_ciclo_da_viagem(client, admin, fleet, events):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    assert t["code"] == "VG-0001" and t["status"] == "planejada" and t["device_id"] == "esp32-001"
    assert client.post(f"/api/v1/trips/{t['id']}/start", headers=admin).json()["status"] == "em_andamento"
    # o mesmo veículo não pode ter duas viagens em andamento
    t2 = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    assert client.post(f"/api/v1/trips/{t2['id']}/start", headers=admin).status_code == 409
    fin = client.post(f"/api/v1/trips/{t['id']}/finish", headers=admin, json={"volume_liters": 7900}).json()
    assert fin["status"] == "finalizada" and fin["volume_liters"] == 7900
    assert ("smartmilk/events/lote.recebido", ) == (events[-1][0],)
    assert client.patch(f"/api/v1/trips/{t['id']}", headers=admin, json={"origin": "Outra origem"}).status_code == 409


def test_volume_acima_da_capacidade(client, admin, fleet):
    v, d, _ = fleet
    r = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d, volume_liters=12000))
    assert r.status_code == 422


def test_filtros_e_busca_de_viagens(client, admin, fleet):
    v, d, _ = fleet
    for _ in range(3):
        client.post("/api/v1/trips", headers=admin, json=trip_body(v, d))
    page = client.get("/api/v1/trips?page_size=2", headers=admin).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert client.get("/api/v1/trips?q=ABC1D23", headers=admin).json()["total"] == 3
    assert client.get("/api/v1/trips?q=naoexiste", headers=admin).json()["total"] == 0
    assert client.get("/api/v1/trips?status=finalizada", headers=admin).json()["total"] == 0


# ---------------------------------------------------------------- coletas
def test_coleta_fora_da_faixa_abre_alerta_e_publica_eventos(client, admin, fleet, events):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    coletor = make_user(client, admin, "coletor")
    r = client.post(f"/api/v1/trips/{t['id']}/samples", headers=coletor, json={
        "collected_at": datetime.now(UTC).isoformat(), "producer": "Sítio Boa Vista", "acidity_dornic": 19.2,
        "density": 1.031, "volume_liters": 2000, "decision": "recusado"})
    assert r.status_code == 201, r.text
    assert r.json()["out_of_range"] == ["acidity_dornic"]
    alerts = client.get(f"/api/v1/trips/{t['id']}/alerts", headers=admin).json()
    assert len(alerts) == 1 and alerts[0]["severity"] == "critico" and alerts[0]["parameter"] == "acidity_dornic"
    tipos = [e[1]["type"] for e in events]
    assert tipos == ["alerta.aberto", "coleta.recusada"]


def test_coleta_dentro_da_faixa_sem_alerta(client, admin, fleet, events):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    r = client.post(f"/api/v1/trips/{t['id']}/samples", headers=admin, json={
        "collected_at": datetime.now(UTC).isoformat(), "producer": "Sítio", "acidity_dornic": 16,
        "decision": "aceito"})
    assert r.json()["out_of_range"] == [] and events == []


def test_coleta_e_imutavel_no_banco(client, admin, fleet, db):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    client.post(f"/api/v1/trips/{t['id']}/samples", headers=admin, json={
        "collected_at": datetime.now(UTC).isoformat(), "producer": "Sítio", "decision": "aceito"})
    with pytest.raises(Exception, match="somente inserção"):
        db.execute(text("UPDATE quality_samples SET producer = 'adulterado'"))
    db.rollback()


# ---------------------------------------------------------------- alertas e parâmetros
def test_reconhecer_e_encerrar_alerta(client, admin, fleet, events):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    client.post(f"/api/v1/trips/{t['id']}/samples", headers=admin, json={
        "collected_at": datetime.now(UTC).isoformat(), "producer": "Sítio Sul", "density": 1.020, "decision": "recusado"})
    a = client.get("/api/v1/alerts?active_only=true", headers=admin).json()["items"][0]
    leitura = make_user(client, admin, "leitura")
    assert client.post(f"/api/v1/alerts/{a['id']}/acknowledge", headers=leitura).status_code == 403
    assert client.post(f"/api/v1/alerts/{a['id']}/acknowledge", headers=admin).json()["status"] == "reconhecido"
    closed = client.post(f"/api/v1/alerts/{a['id']}/close", headers=admin, json={"reason": "lote descartado"}).json()
    assert closed["status"] == "encerrado" and closed["close_reason"] == "lote descartado"
    assert events[-1][1]["type"] == "alerta.encerrado"


def test_parametro_versionado(client, admin):
    atual = [p for p in client.get("/api/v1/quality-parameters", headers=admin).json()
             if p["parameter"] == "milk_temperature" and p["context"] == "transporte"][0]
    novo = client.post("/api/v1/quality-parameters", headers=admin, json={
        "parameter": "milk_temperature", "context": "transporte", "maximum_value": 6.5, "unit": "°C",
        "source_reference": "Decisão do laticínio parceiro, ata de 03/11/2026"}).json()
    hist = client.get("/api/v1/quality-parameters?include_history=true", headers=admin).json()
    antigo = [p for p in hist if p["id"] == atual["id"]][0]
    assert antigo["valid_to"] is not None and novo["valid_to"] is None and novo["needs_review"] is False
    assert client.post("/api/v1/quality-parameters", headers=admin, json={
        "parameter": "ph", "context": "coleta", "minimum_value": 7, "maximum_value": 6, "unit": "pH",
        "source_reference": "teste invertido"}).status_code == 422


# ---------------------------------------------------------------- indicadores e relatórios
def test_indicadores_separam_simulados(client, admin, fleet):
    v, d, _ = fleet
    sim = client.post("/api/v1/vehicles", headers=admin,
                      json={"plate": "SIM0A01", "model": "Teste", "capacity_liters": 9000, "is_simulated": True}).json()
    now = datetime.now(UTC)
    for vid, vol in ((v["id"], 5000), (sim["id"], 7000)):
        client.post("/api/v1/trips", headers=admin, json={
            "vehicle_id": vid, "driver_id": d["id"], "origin": "Origem A", "destination": "Destino B", "volume_liters": vol,
            "departure_at": (now - timedelta(hours=6)).isoformat(), "arrival_at": (now - timedelta(hours=1)).isoformat(),
            "status": "finalizada"})
    real = client.get("/api/v1/analytics/overview", headers=admin).json()
    tudo = client.get("/api/v1/analytics/overview?include_simulated=true", headers=admin).json()
    assert real["volume_liters"] == 5000 and real["trips"] == 1
    assert tudo["volume_liters"] == 12000 and tudo["trips"] == 2
    assert real["milk_temp_avg"] is None  # sem leitura, sem número (nunca zero)


def test_relatorios_baixam(client, admin, fleet):
    v, d, _ = fleet
    t = client.post("/api/v1/trips", headers=admin, json=trip_body(v, d)).json()
    pdf = client.get(f"/api/v1/reports/trips/{t['id']}.pdf", headers=admin)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    for url in ("/api/v1/reports/trips.xlsx", "/api/v1/reports/alerts.xlsx",
                f"/api/v1/reports/telemetry.xlsx?trip_id={t['id']}"):
        r = client.get(url, headers=admin)
        assert r.status_code == 200 and r.content[:2] == b"PK", url
