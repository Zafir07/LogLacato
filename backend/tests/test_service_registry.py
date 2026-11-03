"""O /health só diz que um serviço está online se ele se apresentou e continua batendo."""
import json
from datetime import UTC, datetime, timedelta

from app.services.service_registry import STALE_AFTER, ServiceRegistry


def _status(state: str, **extra) -> bytes:
    return json.dumps({"v": 1, "service": "x", "state": state, **extra}).encode()


def test_servico_obrigatorio_que_nunca_apareceu_e_falha():
    reg = ServiceRegistry(["svc-quality"])
    r = reg.check()
    assert not r.ok
    assert "nunca se apresentou" in r.error
    assert r.details["svc-quality"]["state"] == "desconhecido"


def test_servico_online_fica_ok_e_mostra_contadores():
    reg = ServiceRegistry(["svc-quality"])
    reg.handle("smartmilk/services/svc-quality/status", _status("online", received=12))
    r = reg.check()
    assert r.ok
    assert r.details["svc-quality"]["state"] == "online"
    assert r.details["svc-quality"]["received"] == 12


def test_last_will_offline_derruba_o_health():
    reg = ServiceRegistry(["svc-notifier"])
    reg.handle("smartmilk/services/svc-notifier/status", _status("online"))
    reg.handle("smartmilk/services/svc-notifier/status", _status("offline", reason="lwt"))
    r = reg.check()
    assert not r.ok
    assert r.details["svc-notifier"]["state"] == "offline"


def test_sem_batida_ha_muito_tempo_e_considerado_parado():
    reg = ServiceRegistry(["svc-quality"])
    reg.handle("smartmilk/services/svc-quality/status", _status("online"))
    depois = datetime.now(UTC) + STALE_AFTER + timedelta(seconds=5)
    r = reg.check(now=depois)
    assert not r.ok
    assert r.details["svc-quality"]["state"] == "sem batida"


def test_servico_opcional_offline_nao_derruba():
    reg = ServiceRegistry(["svc-quality"])
    reg.handle("smartmilk/services/svc-quality/status", _status("online"))
    reg.handle("smartmilk/services/svc-extra/status", _status("offline"))
    assert reg.check().ok


def test_mensagens_estranhas_sao_ignoradas():
    reg = ServiceRegistry([])
    reg.handle("smartmilk/services/svc-quality/status", b"nao e json")
    reg.handle("smartmilk/services/svc-quality/status", b"[1, 2]")
    reg.handle("outro/topico", _status("online"))
    assert reg.check().details == {}
