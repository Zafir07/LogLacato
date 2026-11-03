"""Saúde do serviço.

- GET /health/live  -> o processo está de pé (usado pelo Docker).
- GET /health       -> o backend consegue falar com o PostgreSQL e com o broker.
                       Responde 503 quando alguma dependência está fora.
"""
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import get_settings
from app.core.health import CheckResult
from app.database.session import check_database

router = APIRouter(tags=["Saúde"])

Check = Callable[[], CheckResult]


def get_database_check() -> Check:
    return check_database


def get_mqtt_check(request: Request) -> Check:
    return request.app.state.mqtt.check


@router.get("/health/live", summary="O processo está de pé")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health", summary="Estado do backend e das dependências")
def health(
    response: Response,
    db_check: Check = Depends(get_database_check),
    mqtt_check: Check = Depends(get_mqtt_check),
) -> dict:
    checks = {"database": db_check(), "mqtt": mqtt_check()}
    all_ok = all(c.ok for c in checks.values())
    response.status_code = 200 if all_ok else 503
    settings = get_settings()
    return {
        "status": "ok" if all_ok else "degraded",
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": {name: c.as_dict() for name, c in checks.items()},
    }
