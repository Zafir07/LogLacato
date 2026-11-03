# Etapas de implementação

Cada etapa só começa depois que os critérios da anterior forem conferidos.

| Etapa | Entrega | Critério para avançar | Situação |
|-------|---------|-----------------------|----------|
| 1 | Arquitetura e estrutura do repositório | Documentos revisados pelo grupo; `docker compose up` sobe PostgreSQL, Mosquitto e backend; `/health` = 200; testes de unidade e integração passando | ✅ Entregue — aguardando validação |
| 2 | Banco de dados | Migrations Alembic sobem e descem limpas; restrições testadas (duplicata, faixas, viagem única por veículo); seeds carregam | ⏳ |
| 3 | Backend, APIs e autenticação | Login JWT; senhas com Argon2; perfis (admin, gestor, coletor, leitura); CRUD de veículos, motoristas, viagens, dispositivos, coletas e parâmetros; auditoria; OpenAPI em `/docs` | ⏳ |
| 4 | MQTT e processamento da telemetria | Backend consome os tópicos; valida, deduplica, associa à viagem, grava; alertas com histerese; WebSocket; **simulador** publicando dados SIMULADOS | ⏳ |
| 5 | Firmware da T-Beam | Conversão do pH e bits de falha testados no PC; DS18B20 integrada; fila offline sobrevive a desligar a placa; reenvio sem duplicar; teste de bancada com o hardware | ⏳ |
| 6 | Frontend | Dashboard, tempo real, viagens, veículos, alertas, relatórios, tela do coletor; modo claro/escuro; responsivo | ⏳ |
| 7 | Integração | Fluxo completo com simulador e com o hardware real | ⏳ |
| 8 | Testes, segurança e falhas | Testes de reconexão, retransmissão, perda de Wi-Fi, broker fora, backend fora; TLS no broker; revisão de segredos | ⏳ |
| 9 | Documentação e implantação | Manual de instalação, de operação e de montagem; atualização do relatório | ⏳ |
