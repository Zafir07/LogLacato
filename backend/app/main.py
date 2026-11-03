"""Ponto de entrada da API LogLacto (FastAPI).

Executar localmente:  uvicorn app.main:app --reload
Documentação da API:  http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.middleware.request_log import RequestLogMiddleware
from app.mqtt.connection import MqttConnection

log = logging.getLogger(__name__)


def create_app(start_mqtt: bool | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    should_start_mqtt = settings.mqtt_enabled if start_mqtt is None else start_mqtt

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mqtt = MqttConnection(settings)
        if should_start_mqtt:
            app.state.mqtt.start()
        log.info("%s %s iniciada (%s)", settings.app_name, settings.version, settings.environment)
        yield
        app.state.mqtt.stop()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Monitoramento logístico e de qualidade do leite (Smart Milk Logistics).",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
