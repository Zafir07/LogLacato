# Instalação e execução (Windows)

Passo a passo para subir os serviços do LogLacto no seu computador e conferir que
tudo funciona. Tempo estimado: 15 minutos (mais o download do Docker na primeira vez).

---

## Passo 1 — Instalar o Docker Desktop

1. Baixe em <https://www.docker.com/products/docker-desktop/> e instale.
2. Na instalação, deixe marcada a opção **"Use WSL 2"**.
3. Reinicie o computador se ele pedir.
4. Abra o Docker Desktop e espere a baleia no canto da tela ficar **verde** ("Engine running").

✅ **Confira:** abra o PowerShell e rode

```powershell
docker --version
docker compose version
```

---

## Passo 2 — Abrir o terminal na pasta do projeto

```powershell
cd $HOME\Documents\LogLacto
```

---

## Passo 3 — Criar o arquivo `.env` com as senhas

```powershell
Copy-Item .env.example .env
notepad .env
```

Troque **todas** as senhas que começam com `troque-`. Para gerar senhas fortes:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

⚠️ A senha do PostgreSQL aparece **duas vezes** (`POSTGRES_PASSWORD` e dentro de
`DATABASE_URL`). As duas precisam ser iguais.

⚠️ Senhas de dispositivo (`MQTT_DEVICE_CREDENTIALS`) não podem ter vírgula.

---

## Passo 4 — Subir os serviços

```powershell
docker compose up -d --build
```

✅ **Confira:**

```powershell
docker compose ps
```

Esperado — **8 serviços**, todos `Up`, e os que têm verificação `(healthy)`:

```
SERVICE     STATUS                  PAPEL (Cap. 8 do relatório)
proxy       Up                      API Gateway + CloudFront
api         Up (healthy)            ECS
quality     Up (healthy)            Lambda de qualidade
notifier    Up (healthy)            SNS
mosquitto   Up (healthy)            IoT Core + EventBridge
postgres    Up (healthy)            RDS
backup      Up                      backups do RDS
mailpit     Up                      caixa de e-mail de teste
```

---

## Passo 5 — Ver a saúde do sistema

Abra no navegador: <http://localhost/health>

Esperado: `"status": "ok"` e três verificações verdes:

```json
"checks": {
  "database": { "ok": true },
  "mqtt":     { "ok": true },
  "services": { "ok": true, "details": {
      "svc-quality":  { "state": "online" },
      "svc-notifier": { "state": "online" } } }
}
```

Outros endereços:

| Endereço | O que é |
|----------|---------|
| <http://localhost> | página provisória do painel (o painel é a Etapa 6) |
| <http://localhost/docs> | documentação interativa da API |
| <http://localhost:8025> | Mailpit: os e-mails de alerta chegam aqui em desenvolvimento |

---

## Passo 6 — Rodar os testes

**Testes de unidade** (sem banco, broker nem workers):

```powershell
docker compose exec api pytest
```

Esperado: `26 passed, 13 skipped`.

**Testes de integração** (com todos os serviços de verdade):

```powershell
docker compose exec -e RUN_INTEGRATION=1 api pytest -m integration -v
```

Esperado: `13 passed`. Eles conferem:

| Teste | O que prova |
|-------|-------------|
| `test_banco_responde` | a API conecta no PostgreSQL |
| `test_health_ok_com_servicos_reais` | `/health` fica verde com tudo no ar |
| `test_servicos_internos_aparecem_online_no_health` | quality e notifier se apresentam pelo broker |
| `test_conexao_anonima_recusada` / `test_senha_errada_recusada` | ninguém entra no broker sem credencial |
| `test_dispositivo_*` | um ESP32 não se passa por outro, não lê dados alheios e não dispara alertas |
| `test_quality_*` | o serviço de qualidade lê a telemetria, mas não se passa por dispositivo |
| `test_notifier_nao_le_telemetria` | o notificador só vê eventos de alerta |
| `test_evento_de_alerta_vira_email` | evento `alerta.aberto` → e-mail no Mailpit, de ponta a ponta |

---

## Passo 7 — Ver um alerta virar e-mail (opcional)

```powershell
docker compose exec api python -m app.tools.demo_alert
```

Saída esperada: `Evento demo-1 (critico) publicado.`

✅ Abra <http://localhost:8025>: o e-mail **"[LogLacto] CRÍTICO: Temperatura do leite
acima do limite — VG-DEMO"** está na caixa.

Rode o mesmo comando de novo: **não** chega um segundo e-mail (mesmo `alert_id`).
Com outro id, chega: `docker compose exec api python -m app.tools.demo_alert --id demo-2`.

---

## Passo 8 — Derrubar um serviço de propósito (opcional)

```powershell
docker compose stop notifier
```

Atualize <http://localhost/health>: `"status": "degraded"`, HTTP **503** e
`svc-notifier: offline`.

```powershell
docker compose start notifier
```

Em poucos segundos volta para `"ok"`. Faça o mesmo com `postgres` e `mosquitto`: a API
e os workers reconectam sozinhos.

---

## Passo 9 — Conferir o backup (opcional)

```powershell
docker compose logs backup
dir backups
```

Esperado: `backup: … gravado /backups/loglacto-<data>.dump` e o arquivo na pasta
`backups`. Copie essa pasta para fora do computador de tempos em tempos.

---

## Parar e limpar

```powershell
docker compose down        # para os serviços, mantém os dados
docker compose down -v     # para e APAGA o banco, a fila do broker e os certificados
```

---

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `error during connect` | Docker Desktop fechado | Abra o Docker Desktop e espere ficar verde |
| `port is already allocated` na 80 ou 443 | Outro programa usa a porta (IIS, Skype, outro servidor) | No `.env`: `PROXY_HTTP_PORT=8080` e abra <http://localhost:8080> |
| `port is already allocated` na 5432 | Já existe um PostgreSQL no Windows | No `.env`: `POSTGRES_HOST_PORT=5433` |
| `required variable … is missing a value` | Falta uma senha no `.env` | Compare com o `.env.example` (ele ganhou senhas novas) |
| Mosquitto reinicia sem parar, log com `set: Illegal option -` | `docker-entrypoint.sh` salvo com fim de linha do Windows (CRLF) | No VS Code, troque `CRLF` por `LF` no canto inferior direito e salve |
| `services.ok = false`, "nunca se apresentou" | Worker ainda subindo ou senha errada | `docker compose logs quality notifier` |
| `mqtt.ok = false`, "Not authorized" | Senha mudou no `.env` depois de subir | `docker compose up -d --force-recreate` |
| `database.ok = false`, "password authentication failed" | O banco foi criado com outra senha | `docker compose down -v` e suba de novo (apaga os dados) |
| Nenhum e-mail no Mailpit | `ALERT_EMAIL_TO` vazio ou severidade abaixo do mínimo | Confira o `.env` e `docker compose logs notifier` |

Logs de um serviço: `docker compose logs -f <serviço>`.

---

## Rodar o backend fora do Docker (opcional, para desenvolver)

Com os outros serviços no Docker:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
docker compose stop api
uvicorn app.main:app --reload
```

O backend lê o `.env` da raiz (`DATABASE_URL` e `MQTT_HOST` apontam para `localhost`).

---

## Produção com HTTPS

1. Um servidor Linux com Docker e um domínio apontando para ele (portas 80 e 443 abertas).
2. No `.env`: `SITE_ADDRESS=loglacto.seudominio.com.br` e `CORS_ORIGINS=https://loglacto.seudominio.com.br`.
3. `docker compose up -d`: o Caddy obtém e renova o certificado sozinho.
4. Para a T-Beam fora da rede local: ative o ouvinte TLS 8883 em
   `infrastructure/mqtt/mosquitto.conf` (Etapa 8).
5. Troque o Mailpit por um SMTP real (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
   `SMTP_PASSWORD`, `SMTP_STARTTLS=true`) e remova o serviço `mailpit`.
