"""Confere que o JSON que o firmware monta passa no esquema e nas faixas do backend.

Usa as mesmas classes do serviço de ingestão (backend/app/services/ingest.py).
"""
import json
import sys

from app.services.ingest import DeviceAlertPayload, TelemetryPayload, validate_readings

ok = True
with open("telemetria_exemplo.json", encoding="utf-8") as f:
    for i, linha in enumerate(f, 1):
        p = TelemetryPayload.model_validate(json.loads(linha))
        values, errors, status = validate_readings(p)
        print(f"telemetria {i}: buffered={p.buffered} time_source={p.time_source} -> {status} {errors or ''}")
        esperado = "time_unknown" if p.time_source == "none" else "valid"
        if status != esperado:
            ok = False
            print(f"  ESPERADO {esperado}")

with open("alerta_exemplo.json", encoding="utf-8") as f:
    a = DeviceAlertPayload.model_validate(json.loads(f.read()))
    print(f"alerta: {a.code} {a.severity} -> aceito")

print("JSON do firmware aceito pelo backend" if ok else "FALHOU")
sys.exit(0 if ok else 1)
