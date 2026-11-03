"""Acompanha o estado dos serviços internos (workers) pelo MQTT.

Cada worker publica, retido, em smartmilk/services/<nome>/status:
  - "online" ao conectar e a cada batida (heartbeat);
  - "offline" ao desligar, ou o broker publica por ele (Last Will) se ele cair.

A API assina esses tópicos e mostra o resultado no /health — é o papel que o
CloudWatch tinha na arquitetura em nuvem do relatório.
"""
import json
import threading
from datetime import UTC, datetime, timedelta

from app.core.health import CheckResult

# Sem batida por este tempo, o serviço é considerado parado mesmo que o último
# estado diga "online" (ex.: processo travado sem cair a conexão).
STALE_AFTER = timedelta(seconds=90)


class ServiceRegistry:
    def __init__(self, required: list[str]) -> None:
        self.required = required
        self._lock = threading.Lock()
        self._status: dict[str, dict] = {}

    def handle(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        if len(parts) != 4 or parts[0] != "smartmilk" or parts[1] != "services":
            return
        try:
            body = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(body, dict):
            return
        body["_received_at"] = datetime.now(UTC)
        with self._lock:
            self._status[parts[2]] = body

    def check(self, now: datetime | None = None) -> CheckResult:
        now = now or datetime.now(UTC)
        details: dict[str, dict] = {}
        problems: list[str] = []
        with self._lock:
            names = sorted(set(self.required) | set(self._status))
            for name in names:
                st = self._status.get(name)
                if st is None:
                    details[name] = {"state": "desconhecido"}
                    if name in self.required:
                        problems.append(f"{name}: nunca se apresentou")
                    continue
                age = now - st["_received_at"]
                state = st.get("state", "desconhecido")
                if state == "online" and age > STALE_AFTER:
                    state = "sem batida"
                details[name] = {
                    "state": state,
                    "last_seen_s": round(age.total_seconds()),
                    **{k: v for k, v in st.items() if k not in ("_received_at", "state", "v", "service")},
                }
                if name in self.required and state != "online":
                    problems.append(f"{name}: {state}")
        return CheckResult(ok=not problems, error="; ".join(problems) or None, details=details)
