# Banco de dados

O PostgreSQL 16 roda no serviço `postgres` do `docker-compose.yml`, com os dados no
volume `pgdata` (sobrevive a `docker compose down`, é apagado por `docker compose down -v`).

- **Migrations:** Alembic, dentro de `backend/` (Etapa 2). O esquema nunca é alterado
  à mão em produção.
- **Seeds de demonstração:** Etapa 2, marcados como demonstração.

## Backup e restauração

```powershell
# backup
docker compose exec postgres pg_dump -U loglacto -d loglacto -Fc -f /tmp/loglacto.dump
docker compose cp postgres:/tmp/loglacto.dump .\loglacto.dump

# restauração (apaga o conteúdo atual)
docker compose cp .\loglacto.dump postgres:/tmp/loglacto.dump
docker compose exec postgres pg_restore -U loglacto -d loglacto --clean --if-exists /tmp/loglacto.dump
```

## Acessar com um cliente gráfico

pgAdmin ou DBeaver: host `localhost`, porta `POSTGRES_HOST_PORT` do `.env` (5432),
banco, usuário e senha do `.env`.
