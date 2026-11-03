# Banco de dados

O PostgreSQL 16 roda no serviço `postgres` do `docker-compose.yml`, com os dados no
volume `pgdata` (sobrevive a `docker compose down`, é apagado por `docker compose down -v`).

- **Migrations:** Alembic, dentro de `backend/` (Etapa 2). O esquema nunca é alterado
  à mão em produção.
- **Seeds de demonstração:** Etapa 2, marcados como demonstração.

## Backup automático

O serviço `backup` do `docker-compose.yml` (papel dos backups do RDS) grava um dump a
cada `BACKUP_INTERVAL_HOURS` (24 h) na pasta `backups/` do projeto e apaga os com mais
de `BACKUP_KEEP_DAYS` (14). **Copie essa pasta para fora do computador**: backup no
mesmo disco não protege contra a perda do disco.

Restaurar um dump da pasta `backups/` (apaga o conteúdo atual):

```powershell
docker compose cp .\backups\loglacto-20261103T200951Z.dump postgres:/tmp/r.dump
docker compose exec postgres pg_restore -U loglacto -d loglacto --clean --if-exists /tmp/r.dump
```

## Backup manual

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
