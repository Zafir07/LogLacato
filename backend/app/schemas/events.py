"""Eventos de negócio trocados entre serviços pelo broker (smartmilk/events/...)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "atencao", "critico"]
SEVERITY_ORDER: dict[str, int] = {"info": 0, "atencao": 1, "critico": 2}


class AlertOpenedEvent(BaseModel):
    """Publicado em smartmilk/events/alerta.aberto quando um alerta novo é aberto."""

    v: Literal[1] = 1
    type: Literal["alerta.aberto"] = "alerta.aberto"
    alert_id: str = Field(min_length=1, max_length=64)
    at: datetime
    severity: Severity
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    trip_code: str | None = None
    device_id: str | None = None
    is_simulated: bool = False
