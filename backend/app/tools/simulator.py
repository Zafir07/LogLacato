"""Simulador de hardware: faz o papel da T-Beam para testar tudo antes da montagem física.

Publica pelo mesmo caminho do dispositivo real (MQTT, usuário sim-001), no mesmo
formato (docs/architecture/protocolo-mqtt.md). O dispositivo sim-001 está cadastrado
como SIMULADO, então o servidor marca cada leitura como simulada e a mantém fora dos
indicadores reais.

Modos:
  live      envia uma leitura a cada --interval s na viagem simulada em andamento
            (cenários: demo, normal, ruptura, ph, falha, offline)
  history   cria viagens simuladas finalizadas nos últimos --days dias, com leituras
            e coletas, para o dashboard ter histórico

Exemplos (dentro do container da api):
  python -m app.tools.simulator live
  python -m app.tools.simulator live --scenario ruptura --interval 2
  python -m app.tools.simulator history --days 7
"""
import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import paho.mqtt.client as mqtt

from app.core.config import get_settings

DEVICE = "sim-001"
# Percurso fictício perto de Ijuí (RS): fazenda → laticínio. Só para o mapa ter movimento.
WAYPOINTS = [(-28.3010, -53.9910), (-28.3270, -53.9650), (-28.3560, -53.9420),
             (-28.3790, -53.9230), (-28.3890, -53.9150)]
# Calibração típica do relatório (Seção 7.5): Po = 2,50 V em pH 7, inclinação 0,18 V/pH
PH7_V, SLOPE = 2.50, 0.18


def device_password(arg: str | None) -> str:
    if arg:
        return arg
    for pair in os.getenv("MQTT_DEVICE_CREDENTIALS", "").split(","):
        if ":" in pair and pair.split(":", 1)[0].strip() == DEVICE:
            return pair.split(":", 1)[1]
    sys.exit("Senha do sim-001 não encontrada: use --password ou MQTT_DEVICE_CREDENTIALS")


def position(frac: float) -> tuple[float, float]:
    frac = min(max(frac, 0.0), 1.0) * (len(WAYPOINTS) - 1)
    i = min(int(frac), len(WAYPOINTS) - 2)
    t = frac - i
    (a1, o1), (a2, o2) = WAYPOINTS[i], WAYPOINTS[i + 1]
    return round(a1 + (a2 - a1) * t, 6), round(o1 + (o2 - o1) * t, 6)


class Scenario:
    """Gera valores plausíveis. `k` é o número da leitura; `frac` o progresso da viagem."""

    def __init__(self, name: str) -> None:
        self.name = name

    def values(self, k: int, frac: float) -> tuple[float | None, float | None, float, float, int]:
        name = self.name
        if name == "demo":  # ciclo de ~6 min (a 5 s): normal → ruptura do frio → normal → pH caindo
            name = ["normal", "ruptura", "normal", "ph"][(k // 18) % 4]
        temp = 4.0 + 0.6 * math.sin(k / 9) + random.uniform(-0.1, 0.1)
        ph = 6.71 + random.uniform(-0.015, 0.015)
        flags = 0
        if name == "ruptura":
            temp = 7.2 + 0.8 * math.sin(k / 6) ** 2 + random.uniform(-0.1, 0.1)
        elif name == "ph":
            ph = 6.62 - 0.004 * (k % 18) + random.uniform(-0.01, 0.01)
        elif name == "falha":
            ph, flags = None, 2  # fio do Po solto
        air_t = 22.0 + 2 * math.sin(k / 40) + random.uniform(-0.2, 0.2)
        air_h = 62 + 5 * math.sin(k / 30) + random.uniform(-1, 1)
        return (round(ph, 2) if ph is not None else None, round(temp, 2), round(air_t, 1),
                round(air_h, 1), flags)


def reading(seq: int, boot: int, at: datetime, values, frac: float, buffered: bool) -> dict:
    ph, milk_t, air_t, air_h, flags = values
    lat, lon = position(frac)
    volts = round(PH7_V - (ph - 7) * SLOPE, 3) if ph is not None else 0.012
    return {
        "v": 1, "msg_id": f"{DEVICE}-{boot}-{seq:09d}", "device_id": DEVICE,
        "measured_at": at.isoformat().replace("+00:00", "Z"), "time_source": "ntp",
        "readings": {"ph": ph, "ph_voltage": volts, "milk_temperature": milk_t,
                     "air_temperature": air_t, "air_humidity": air_h},
        "sensor_flags": flags, "gps": {"lat": lat, "lon": lon, "fix": True, "sats": 8},
        "buffered": buffered, "simulated": True, "fw": "simulador-0.1",
    }


def connect(password: str) -> mqtt.Client:
    s = get_settings()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=DEVICE)
    c.username_pw_set(DEVICE, password)
    status_topic = f"smartmilk/device/{DEVICE}/status"
    c.will_set(status_topic, json.dumps({"v": 1, "device_id": DEVICE, "state": "offline", "reason": "lwt"}),
               qos=1, retain=True)
    c.connect(s.mqtt_host, s.mqtt_port, 30)
    c.loop_start()
    c.publish(status_topic, json.dumps({
        "v": 1, "device_id": DEVICE, "state": "online", "at": datetime.now(UTC).isoformat(),
        "fw": "simulador-0.1", "time_source": "ntp", "wifi_rssi": -58, "ip": "simulador",
        "queue": {"pending": 0, "capacity": 20000, "dropped": 0},
        "sensors": {"ph": {"state": "ok"}, "dht22": {"state": "ok"}, "ds18b20": {"state": "ok"}},
    }), qos=1, retain=True).wait_for_publish(5)
    return c


def publish(c: mqtt.Client, msg: dict) -> bool:
    info = c.publish(f"smartmilk/device/{DEVICE}/telemetry", json.dumps(msg), qos=1)
    info.wait_for_publish(10)
    return info.is_published()


# ---------------------------------------------------------------- modo live
def live(args) -> None:
    c = connect(device_password(args.password))
    boot, scen = int(time.time()), Scenario(args.scenario)
    queue: list[dict] = []
    print(f"Simulador ao vivo: cenário {args.scenario}, uma leitura a cada {args.interval} s. Ctrl+C para parar.")
    k = 0
    try:
        while args.count == 0 or k < args.count:
            frac = (k % 720) / 720
            msg = reading(k, boot, datetime.now(UTC), scen.values(k, frac), frac, buffered=False)
            offline = args.scenario == "offline" and (k // 12) % 2 == 1  # 1 min sem rede, 1 min com
            if offline:
                msg["buffered"] = True
                queue.append(msg)
                print(f"  [sem rede] leitura {k} guardada na fila ({len(queue)} pendentes)")
            else:
                for old in queue:  # reenvia a fila, da mais antiga para a mais nova
                    publish(c, old)
                if queue:
                    print(f"  conexão voltou: {len(queue)} leituras da fila enviadas com o horário original")
                    queue.clear()
                ok = publish(c, msg)
                r = msg["readings"]
                print(f"  {msg['measured_at'][11:19]}  pH {r['ph']}  leite {r['milk_temperature']} °C"
                      f"  {'ok' if ok else 'SEM CONFIRMAÇÃO'}")
            k += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    c.publish(f"smartmilk/device/{DEVICE}/status", json.dumps(
        {"v": 1, "device_id": DEVICE, "state": "offline", "reason": "shutdown"}), qos=1, retain=True).wait_for_publish(3)
    c.disconnect()
    c.loop_stop()


# ---------------------------------------------------------------- modo history
def api(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"API {method} {url} → {e.code}: {e.read().decode()[:300]}")


def history(args) -> None:
    s = get_settings()
    email, pw = args.email or s.admin_email, args.admin_password or s.admin_password
    if not email or not pw:
        sys.exit("Informe --email e --admin-password (ou ADMIN_EMAIL/ADMIN_PASSWORD)")
    base = args.api.rstrip("/") + "/api/v1"
    token = api("POST", f"{base}/auth/login", body={"email": email, "password": pw})["access_token"]
    vehicles = api("GET", f"{base}/vehicles?q=SIM0A01", token)["items"]
    drivers = api("GET", f"{base}/drivers?q=SIM-001", token)["items"]
    if not vehicles or not drivers:
        sys.exit("Veículo SIM0A01 ou motorista SIM-001 não encontrados (rode a carga inicial)")
    vid, did = vehicles[0]["id"], drivers[0]["id"]
    c = connect(device_password(args.password))
    boot = int(time.time())
    seq, rnd = 0, random.Random(42)
    today = datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)  # 05:00 em Brasília
    producers = ["Propriedade Linha Simulada 1", "Propriedade Linha Simulada 2", "Propriedade Linha Simulada 3",
                 "Propriedade Linha Simulada 4", "Propriedade Linha Simulada 5"]
    for d in range(args.days, 0, -1):
        for shift in (0, 7):  # duas viagens por dia (manhã e tarde)
            dep = today - timedelta(days=d) + timedelta(hours=shift)
            arr = dep + timedelta(hours=5, minutes=rnd.randint(0, 50))
            volume = rnd.randrange(6500, 9800, 50)
            trip = api("POST", f"{base}/trips", token, {
                "vehicle_id": vid, "driver_id": did, "origin": "Linha simulada (fazendas de teste)",
                "destination": "Laticínio de teste", "volume_liters": volume,
                "departure_at": dep.isoformat(), "expected_arrival_at": (dep + timedelta(hours=6)).isoformat(),
                "arrival_at": arr.isoformat(), "status": "finalizada",
                "notes": "Histórico gerado pelo simulador. Dados SIMULADOS."})
            scen = Scenario(rnd.choice(["normal", "normal", "normal", "ruptura", "ph"]))
            n = int((arr - dep).total_seconds() // 300)  # uma leitura a cada 5 min
            for k in range(n):
                at = dep + timedelta(minutes=5 * k)
                excursion = scen.name != "normal" and n // 2 <= k < n // 2 + 4
                vals = Scenario(scen.name if excursion else "normal").values(k, k / n)
                publish(c, reading(seq, boot, at, vals, k / n, buffered=True))
                seq += 1
            for i in range(rnd.randint(3, 5)):
                acid = round(rnd.uniform(14.4, 17.6), 1) if rnd.random() > 0.12 else round(rnd.uniform(18.2, 19.0), 1)
                api("POST", f"{base}/trips/{trip['id']}/samples", token, {
                    "collected_at": (dep + timedelta(minutes=10 + 35 * i)).isoformat(),
                    "producer": producers[i], "acidity_dornic": acid,
                    "density": round(rnd.uniform(1.029, 1.033), 4), "volume_liters": volume // 4,
                    "milk_temperature": round(rnd.uniform(3.6, 5.2), 1), "ph_manual": round(rnd.uniform(6.64, 6.76), 2),
                    "seal_code": f"AT-{trip['code']}-{i + 1}",
                    "decision": "recusado" if acid > 18 else "aceito"})
            print(f"  {trip['code']}  {dep:%d/%m %H:%M} UTC  {n} leituras  cenário {scen.name}")
    c.disconnect()
    c.loop_stop()
    print(f"Histórico simulado criado: {args.days * 2} viagens. Marque 'incluir simulados' no painel para ver.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Simulador de hardware do LogLacto (dados SIMULADOS)")
    p.add_argument("--password", help="senha MQTT do sim-001 (padrão: MQTT_DEVICE_CREDENTIALS)")
    sub = p.add_subparsers(dest="mode", required=True)
    pl = sub.add_parser("live", help="leituras ao vivo")
    pl.add_argument("--scenario", default="demo", choices=["demo", "normal", "ruptura", "ph", "falha", "offline"])
    pl.add_argument("--interval", type=float, default=5.0)
    pl.add_argument("--count", type=int, default=0, help="quantas leituras (0 = sem fim)")
    ph = sub.add_parser("history", help="viagens simuladas passadas")
    ph.add_argument("--days", type=int, default=7)
    ph.add_argument("--api", default="http://localhost:8000")
    ph.add_argument("--email")
    ph.add_argument("--admin-password")
    args = p.parse_args(argv)
    live(args) if args.mode == "live" else history(args)


if __name__ == "__main__":
    main()
