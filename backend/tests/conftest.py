"""Configuração comum dos testes.

Com RUN_INTEGRATION=1 os testes de integração usam um banco SEPARADO
(<nome do banco>_test), criado e migrado aqui, para nunca tocar nos dados de verdade.
"""
import os

import pytest

if os.getenv("RUN_INTEGRATION") == "1":
    base = os.environ.get("DATABASE_URL", "postgresql+psycopg://loglacto:loglacto@localhost:5432/loglacto")
    if not base.rsplit("/", 1)[1].endswith("_test"):
        os.environ["DATABASE_URL"] = base + "_test"
    os.environ.setdefault("JWT_SECRET", "segredo-somente-para-os-testes-automatizados-0123")


def _prepare_test_db() -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config

    url = os.environ["DATABASE_URL"]
    dbname = url.rsplit("/", 1)[1]
    admin_url = url.rsplit("/", 1)[0].replace("postgresql+psycopg://", "postgresql://") + "/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            conn.execute(f'CREATE DATABASE "{dbname}"')
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def migrated_db():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("defina RUN_INTEGRATION=1")
    _prepare_test_db()
    yield


TABLES = ("audit_log", "alerts", "telemetry", "quality_samples", "device_status_events", "rejected_messages",
          "trips", "devices", "drivers", "vehicles", "quality_parameters", "users")


@pytest.fixture
def db(migrated_db):
    """Sessão num banco limpo, com parâmetros e um administrador."""
    from sqlalchemy import text

    from app.database.session import SessionLocal, engine

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE telemetry DISABLE TRIGGER telemetry_somente_insercao"))
        conn.execute(text("ALTER TABLE quality_samples DISABLE TRIGGER quality_samples_somente_insercao"))
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER TABLE telemetry ENABLE TRIGGER telemetry_somente_insercao"))
        conn.execute(text("ALTER TABLE quality_samples ENABLE TRIGGER quality_samples_somente_insercao"))
    from app.core.security import hash_password
    from app.database.seed import seed_parameters
    from app.models import User

    with SessionLocal() as s:
        seed_parameters(s)
        s.add(User(name="Admin", email="admin@teste.local", password_hash=hash_password("senha-admin-123"),
                   role="admin"))
        s.commit()
    with SessionLocal() as s:
        yield s
