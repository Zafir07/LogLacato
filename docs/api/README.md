# API

A documentação completa e interativa é gerada pelo FastAPI a partir do código:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Esquema OpenAPI (JSON): <http://localhost:8000/openapi.json>

## Endpoints disponíveis (Etapa 1)

| Método | Rota | Resposta |
|--------|------|----------|
| GET | `/health/live` | `200 {"status":"ok"}` enquanto o processo estiver de pé |
| GET | `/health` | `200` se banco **e** broker respondem; `503` se algum estiver fora. O corpo mostra cada verificação, a latência do banco e o erro |

Toda resposta traz o cabeçalho `X-Request-ID`, que aparece também no log do backend.

## Módulos previstos (Etapas 3 e 4)

Todas as rotas abaixo ficarão sob `/api/v1` e, exceto o login, exigirão token JWT.

| Módulo | Prefixo | Perfis |
|--------|---------|--------|
| Autenticação | `/auth` (login, renovação, usuário atual) | todos |
| Usuários | `/users` | admin |
| Veículos | `/vehicles` | admin, gestor |
| Motoristas | `/drivers` | admin, gestor |
| Viagens | `/trips` (+ `/trips/{id}/telemetry`, `/alerts`, `/summary`) | admin, gestor; leitura para todos |
| Dispositivos | `/devices` (+ estado de conexão) | admin |
| Coletas | `/trips/{id}/samples` (acidez Dornic, densidade, litragem, decisão) | coletor, gestor |
| Telemetria | `/telemetry` (consulta; a gravação vem só pelo MQTT) | leitura |
| Parâmetros de qualidade | `/quality-parameters` | admin |
| Alertas | `/alerts` (+ reconhecer, encerrar) | gestor |
| Indicadores | `/analytics` (cards e séries do dashboard) | leitura |
| Relatórios | `/reports` (PDF e Excel) | leitura |
| Tempo real | `WS /ws` (leituras, estados e alertas) | leitura |
