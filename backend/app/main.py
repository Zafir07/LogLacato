"""Serviço "api" do LogLacto (FastAPI) — o papel do ECS na arquitetura do relatório.

Além das rotas HTTP, a api:
- grava a telemetria, o estado e os alertas dos dispositivos que chegam pelo MQTT;
- repassa leituras, estados e eventos ao painel pelo WebSocket;
- acompanha o estado dos serviços internos (/health).

Executar localmente:  uvicorn app.main:app --reload
Documentação da API:  http://localhost/docs (pelo proxy) ou http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, auth, fleet, health, monitoring, reports, trips
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import SessionLocal
from app.middleware.request_log import RequestLogMiddleware
from app.mqtt import topics
from app.mqtt.connection import MqttConnection
from app.services.ingest import Ingestor
from app.services.service_registry import ServiceRegistry
from app.websocket.hub import Hub

log = logging.getLogger(__name__)


def create_app(start_mqtt: bool | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    should_start_mqtt = settings.mqtt_enabled if start_mqtt is None else start_mqtt

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub = Hub()
        await hub.start()
        app.state.hub = hub
        registry = ServiceRegistry(settings.required_service_list)
        app.state.services = registry

        def publish(topic: str, payload: dict) -> None:
            if app.state.mqtt.connected:
                app.state.mqtt.publish_json(topic, payload)

        def broadcast(message: dict) -> None:
            hub.publish_threadsafe(message)

        ingestor = Ingestor(SessionLocal, publish, broadcast)

        def on_message(topic: str, payload: bytes) -> None:
            if topic.startswith("smartmilk/services/"):
                registry.handle(topic, payload)
                broadcast({"type": "service_status", "topic": topic})
            else:
                ingestor.handle(topic, payload)

        app.state.mqtt = MqttConnection(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            user=settings.mqtt_backend_user,
            password=settings.mqtt_backend_password,
            client_id=settings.mqtt_client_id,
            keepalive=settings.mqtt_keepalive_s,
            subscriptions=[
                (topics.SERVICES_STATUS, 1),
                # Assinatura compartilhada: com duas réplicas da api, cada leitura é gravada uma vez.
                (topics.shared("ingest", topics.DEVICE_TELEMETRY), 1),
                (topics.shared("ingest", topics.DEVICE_STATUS), 1),
                (topics.shared("ingest", topics.DEVICE_ALERTS), 1),
                # Todas as réplicas recebem os eventos para avisar os próprios painéis.
                (topics.EVENTS_ALL, 1),
            ],
            on_message=on_message,
        )
        if should_start_mqtt:
            app.state.mqtt.start()
        log.info("%s %s iniciada (%s)", settings.app_name, settings.version, settings.environment)
        yield
        app.state.mqtt.stop()
        await hub.stop()

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
    for r in (health, auth, fleet, trips, monitoring, analytics, reports):
        app.include_router(r.router)
    return app


app = create_app()
