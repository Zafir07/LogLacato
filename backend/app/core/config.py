"""Configuração dos serviços do LogLacto, lida de variáveis de ambiente (ou do .env).

O mesmo código roda como três serviços (api, quality, notifier); cada container
recebe só as variáveis de que precisa. Nenhuma senha tem valor padrão utilizável.
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
    mqtt_keepalive_s: int = 30

    # Usuário MQTT da API
    mqtt_backend_user: str = "backend"
    mqtt_backend_password: str = ""
    mqtt_client_id: str = "loglacto-api"

    # Usuário MQTT dos workers (cada container de worker recebe o seu)
    mqtt_service_user: str = ""
    mqtt_service_password: str = ""

    # Serviços que a API espera ver online no /health
    required_services: str = "svc-quality,svc-notifier"

    # Notificador (equivalente ao SNS): e-mail por SMTP
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    alert_email_from: str = "LogLacto <alertas@loglacto.local>"
    alert_email_to: str = ""
    notify_min_severity: str = "atencao"

    # Origens do frontend autorizadas, separadas por vírgula
    cors_origins: str = "http://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def required_service_list(self) -> list[str]:
        return [s.strip() for s in self.required_services.split(",") if s.strip()]

    @property
    def alert_recipients(self) -> list[str]:
        return [s.strip() for s in self.alert_email_to.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
