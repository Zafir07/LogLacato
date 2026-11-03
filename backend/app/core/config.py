"""Configuração do backend, lida de variáveis de ambiente (ou do arquivo .env).

Nenhuma senha tem valor padrão utilizável: em produção tudo vem do ambiente.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Lê o .env da raiz do repositório (rodando de dentro de backend/) ou da pasta atual.
    # Variáveis de ambiente de verdade sempre têm prioridade sobre o arquivo.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "LogLacto API"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # PostgreSQL (formato SQLAlchemy + psycopg 3)
    database_url: str = "postgresql+psycopg://loglacto:loglacto@localhost:5432/loglacto"

    # Broker MQTT
    mqtt_enabled: bool = True
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_backend_user: str = "backend"
    mqtt_backend_password: str = ""
    mqtt_client_id: str = "loglacto-backend"
    mqtt_keepalive_s: int = 30

    # Origens do frontend autorizadas, separadas por vírgula
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
