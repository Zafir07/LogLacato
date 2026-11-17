# Banco de dados

O PostgreSQL 16 roda no serviço `postgres` do `docker-compose.yml`, com os dados no
volume `pgdata` (sobrevive a `docker compose down`, é apagado por `docker compose down -v`).
Tudo o que a T-Beam envia e tudo o que o painel mostra fica aqui.

- **Esquema:** criado pela migration Alembic `backend/migrations/versions/0001_esquema_inicial.py`,
  aplicada sozinha quando o container `api` sobe (`alembic upgrade head`). Nunca altere o
  esquema à mão: crie uma migration nova.
- **Carga inicial:** `python -m app.database.seed` (também automático) cria o administrador do
  `.env`, os limites de qualidade e, com `SEED_DEMO=true`, o caminhão de demonstração com a
  placa `esp32-001` e o simulador `sim-001`.
- Modelo detalhado: [docs/architecture/modelo-dados.md](../../docs/architecture/modelo-dados.md).

## Onde fica cada dado

| Tabela | O que guarda | Quem escreve |
|--------|--------------|--------------|
| `telemetry` | cada leitura da placa: pH, tensão do Po, temperatura do leite e do ar, umidade, GPS, hora da medição e da chegada, se ficou guardada offline (`buffered`), bits de falha e o JSON original | api, ao receber o MQTT |
| `devices` | as placas cadastradas, estado online/offline, versão do firmware e o último status (fila, bateria, sensores) | seed / painel / api |
| `device_status_events` | histórico de quando cada placa ficou online e offline | api |
| `rejected_messages` | mensagens recusadas (dispositivo não cadastrado, JSON inválido) com o motivo | api |
| `vehicles`, `drivers`, `trips` | caminhões, motoristas e viagens; a leitura entra na viagem cujo horário contém `measured_at` | painel |
| `quality_samples` | coletas do coletor: acidez Dornic, densidade, litragem, aceite ou recusa | painel |
| `quality_parameters` | limites de qualidade vigentes (pH, temperatura…) | seed / painel |
| `alerts` | alertas abertos e encerrados (qualidade, falha de sensor, placa sem dados) | quality / api |
| `users`, `audit_log` | usuários do painel e quem fez o quê | painel |

Regras garantidas pelo próprio banco:

- `UNIQUE (device_id, msg_id)`: a mesma leitura reenviada depois de uma queda de rede não
  entra duas vezes.
- `CHECK` das faixas físicas (pH 0–14, umidade 0–100…).
- `telemetry` e `quality_samples` só aceitam INSERT: o histórico não pode ser alterado nem
  apagado (gatilho `*_somente_insercao`).

## Consultas úteis

Abra um terminal no banco:

```powershell
docker compose exec postgres psql -U loglacto -d loglacto
```

```sql
-- últimas leituras da placa
SELECT measured_at, ph, ph_voltage, air_temperature, air_humidity, buffered, sensor_flags
FROM telemetry WHERE device_id = 'esp32-001' ORDER BY measured_at DESC LIMIT 20;

-- quantas leituras chegaram ao vivo e quantas vieram da fila offline, por dia
SELECT date(measured_at) AS dia, count(*) AS total, sum(buffered::int) AS da_fila_offline
FROM telemetry WHERE device_id = 'esp32-001' GROUP BY 1 ORDER BY 1 DESC;

-- estado atual da placa (fila, bateria, sensores)
SELECT connection_status, last_seen_at, firmware_version, last_status
FROM devices WHERE id = 'esp32-001';

-- mensagens recusadas (senha certa, mas dispositivo não cadastrado, JSON errado…)
SELECT received_at, topic, reason FROM rejected_messages ORDER BY id DESC LIMIT 10;
```

## Acessar com um cliente gráfico

pgAdmin ou DBeaver: host `localhost`, porta `POSTGRES_HOST_PORT` do `.env` (5432),
banco, usuário e senha do `.env`. A porta só abre para o próprio computador, nunca na rede.

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
