# Instalação e execução (Windows)

Passo a passo para subir a Etapa 1 no seu computador e conferir que tudo funciona.
Tempo estimado: 15 minutos (mais o download do Docker na primeira vez).

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

As duas linhas devem mostrar um número de versão.

---

## Passo 2 — Abrir o terminal na pasta do projeto

```powershell
cd $HOME\Documents\LogLacto
```

Ou: abra a pasta `Documentos\LogLacto` no Explorador, clique na barra de endereço,
digite `powershell` e aperte Enter.

---

## Passo 3 — Criar o arquivo `.env` com as senhas

```powershell
Copy-Item .env.example .env
notepad .env
```

No Bloco de Notas, troque **todas** as senhas que começam com `troque-`.
Para gerar senhas fortes:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

⚠️ A senha do PostgreSQL aparece **duas vezes** no `.env` (`POSTGRES_PASSWORD` e dentro
de `DATABASE_URL`). As duas precisam ser iguais.

⚠️ As senhas dos dispositivos (`MQTT_DEVICE_CREDENTIALS`) não podem ter vírgula.

---

## Passo 4 — Subir os serviços

```powershell
docker compose up -d --build
```

Na primeira vez ele baixa as imagens (PostgreSQL, Mosquitto, Python): alguns minutos.

✅ **Confira:**

```powershell
docker compose ps
```

Resultado esperado — três serviços **running**, e o postgres **(healthy)**:

```
NAME                   SERVICE     STATUS
loglacto-backend-1     backend     Up (healthy)
loglacto-mosquitto-1   mosquitto   Up (healthy)
loglacto-postgres-1    postgres    Up (healthy)
```

---

## Passo 5 — Ver a saúde do sistema

Abra no navegador: <http://localhost:8000/health>

Resultado esperado:

```json
{
  "status": "ok",
  "checks": {
    "database": { "ok": true, ... },
    "mqtt":     { "ok": true, ... }
  }
}
```

E a documentação interativa da API: <http://localhost:8000/docs>

---

## Passo 6 — Rodar os testes

**Testes de unidade** (não dependem de banco nem broker):

```powershell
docker compose exec backend pytest
```

Esperado: `7 passed, 7 skipped` (os 7 pulados são os de integração).

**Testes de integração** (usam o PostgreSQL e o Mosquitto de verdade):

```powershell
docker compose exec -e RUN_INTEGRATION=1 backend pytest -m integration -v
```

Esperado: `7 passed`. Eles conferem:

| Teste | O que prova |
|-------|-------------|
| `test_banco_responde` | o backend conecta no PostgreSQL |
| `test_health_ok_com_servicos_reais` | `/health` fica verde com tudo no ar |
| `test_conexao_anonima_recusada` | ninguém entra no broker sem usuário |
| `test_senha_errada_recusada` | senha errada é barrada |
| `test_dispositivo_publica_no_proprio_topico_e_backend_recebe` | o caminho dispositivo → broker → backend funciona |
| `test_dispositivo_nao_publica_no_topico_de_outro` | um ESP32 não consegue se passar por outro |
| `test_dispositivo_nao_le_telemetria_de_outros` | um ESP32 não lê os dados dos outros |

---

## Passo 7 — Testar o broker na mão (opcional)

Abra **dois** PowerShell na pasta do projeto.

**Janela 1** — o backend "escutando" (troque `SENHA_BACKEND` pela do `.env`):

```powershell
docker compose exec mosquitto mosquitto_sub -u backend -P SENHA_BACKEND -t "smartmilk/device/+/telemetry" -v
```

**Janela 2** — o simulador publicando (troque `SENHA_SIM`):

```powershell
docker compose exec mosquitto mosquitto_pub -u sim-001 -P SENHA_SIM -t "smartmilk/device/sim-001/telemetry" -m "teste" -q 1
```

✅ A janela 1 mostra `smartmilk/device/sim-001/telemetry teste`.

Agora tente publicar **no tópico de outro dispositivo**:

```powershell
docker compose exec mosquitto mosquitto_pub -u sim-001 -P SENHA_SIM -t "smartmilk/device/esp32-001/telemetry" -m "invasao" -q 1
```

✅ A janela 1 **não** mostra nada: a ACL bloqueou.

---

## Passo 8 — Simular uma queda (opcional)

```powershell
docker compose stop postgres
```

Atualize <http://localhost:8000/health>: `"status": "degraded"`, `database.ok = false`
e código HTTP **503**.

```powershell
docker compose start postgres
```

Em poucos segundos volta para `"ok"`. Faça o mesmo com `mosquitto`: o backend
reconecta sozinho.

---

## Parar e limpar

```powershell
docker compose down        # para os serviços, mantém os dados
docker compose down -v     # para e APAGA o banco e a fila do broker
```

---

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `error during connect` / `cannot find the file specified` | Docker Desktop fechado | Abra o Docker Desktop e espere ficar verde |
| `port is already allocated` na 5432 | Já existe um PostgreSQL instalado no Windows | No `.env`, mude `POSTGRES_HOST_PORT=5433` |
| `port is already allocated` na 1883 | Outro broker MQTT rodando | Feche o outro broker |
| Mosquitto reinicia sem parar, log com `set: Illegal option -` | O `docker-entrypoint.sh` foi salvo com fim de linha do Windows (CRLF) | No VS Code, abra o arquivo, clique em `CRLF` no canto inferior direito, troque para `LF` e salve |
| `/health` mostra `mqtt.ok = false` com "Not authorized" | Senha do backend no `.env` mudou depois de subir | `docker compose up -d --force-recreate` |
| `/health` mostra `database.ok = false` com "password authentication failed" | O banco foi criado com outra senha (o volume guarda a primeira) | `docker compose down -v` e suba de novo (apaga os dados) |

Para ver os logs de um serviço:

```powershell
docker compose logs -f backend
docker compose logs -f mosquitto
```

---

## Rodar o backend fora do Docker (opcional, para desenvolver)

Com o PostgreSQL e o Mosquitto rodando no Docker:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

O backend lê o `.env` da raiz (`DATABASE_URL` e `MQTT_HOST` apontam para `localhost`).

---

## TLS no broker (para rede externa)

Na rede local a porta 1883 funciona sem TLS. Para expor o broker fora dela:

1. Gere uma CA e o certificado do servidor (ex.: com `openssl`) e coloque em
   `infrastructure/mqtt/certs/` (a pasta está no `.gitignore`).
2. Descomente o bloco `listener 8883` em `infrastructure/mqtt/mosquitto.conf`.
3. Monte a pasta no `docker-compose.yml` e publique a porta 8883.
4. No ESP32 (Etapa 5), grave o certificado da CA e use a porta 8883.

O passo a passo completo entra na Etapa 8.
