"""Conexão com o PostgreSQL.

Na Etapa 2 este módulo ganha os modelos e as migrations (Alembic).
"""
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.health import CheckResult

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    connect_args={"connect_timeout": 3},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def check_database() -> CheckResult:
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
    except Exception as exc:  # noqa: BLE001 - a verificação relata qualquer falha
        return CheckResult(ok=False, error=type(exc).__name__ + ": " + str(exc).splitlines()[0])
    latency = round((time.perf_counter() - start) * 1000, 1)
    return CheckResult(ok=True, latency_ms=latency, details={"server_version": version})
