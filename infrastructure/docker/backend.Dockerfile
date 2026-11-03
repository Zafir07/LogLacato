# Imagem do backend LogLacto (FastAPI).
# Contexto de build: ./backend (definido no docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
# As dependências de teste ficam na imagem de desenvolvimento para permitir
# "docker compose exec backend pytest". Em produção, instale só requirements.txt.
RUN pip install -r requirements-dev.txt

COPY . .

RUN useradd --create-home --uid 1000 app && mkdir -p /data/files && chown app /data/files
USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else 1)"

# Aplica as migrations e a carga inicial (idempotente) antes de subir a API.
CMD ["sh", "-c", "alembic upgrade head && python -m app.database.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
