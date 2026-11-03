"""Healthcheck do Docker para os workers.

Uso:  python -m app.workers.healthcheck svc-quality
Sai com 0 se o worker gravou uma batida (conectado ao broker) nos últimos 45 s.
"""
import sys
import time

from app.workers.base import heartbeat_file

MAX_AGE_S = 45


def main(name: str) -> int:
    path = heartbeat_file(name)
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        print(f"{name}: sem batida (ainda não conectou ao broker)")
        return 1
    if age > MAX_AGE_S:
        print(f"{name}: última batida há {age:.0f} s")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "svc-worker"))
