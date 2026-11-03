# Decisões de arquitetura (ADRs)

Cada decisão registra **o contexto, o que foi decidido e o que muda por causa dela**.
Quando uma decisão for revista, ela não é apagada: ganha o status "substituída" e
aponta para a nova.

| ADR | Decisão | Status |
|-----|---------|--------|
| [01](#adr-01) | Só a T-Beam (ESP32): lê os sensores e publica no MQTT, sem Arduino | Aceita |
| [02](#adr-02) | Backend em FastAPI (Python), não Node.js/Express | Aceita |
| [03](#adr-03) | Acidez Dornic é registro manual do coletor, não telemetria | Aceita |
| [04](#adr-04) | Temperatura do leite e temperatura do ar são grandezas separadas | Aceita |
| [05](#adr-05) | A hora da medição é carimbada no ESP32 (NTP ou GPS) | Aceita |
| [06](#adr-06) | Wi-Fi direto até um Mosquitto próprio | Aceita |
| [07](#adr-07) | Entrega confiável: fila em flash + QoS 1 + id único | Aceita |
| [08](#adr-08) | Um usuário MQTT por dispositivo, com ACL por tópico | Aceita |
| [09](#adr-09) | Limites de qualidade são parâmetros configuráveis com fonte | Aceita |
| [10](#adr-10) | O simulador é um dispositivo cadastrado como simulado | Aceita |

---

<a id="adr-01"></a>
## ADR-01 — Só a T-Beam: lê os sensores e publica no MQTT

**Contexto.** O prompt original previa um Arduino lendo os sensores e um ESP32 só para o
Wi-Fi, ligados por UART. O protótipo do grupo (relatório, Seção 7.2) já usa uma
**LilyGO T-Beam V1.2**, que é um ESP32 com Wi-Fi, LoRa e GPS e já lê o pH no VP (GPIO 36)
e o DHT22 no GPIO 13. O grupo decidiu usar **apenas a T-Beam**.

**Decisão.**
- A T-Beam lê os sensores **e** publica no MQTT, numa placa só e com um firmware só.
- As ligações do protótipo são mantidas (relatório, Tabela 4): pH no VP pelo divisor ÷2,
  DHT22 com dados no GPIO 13 e alimentação no GPIO 14.
- A DS18B20 (temperatura do leite) entra num pino livre: **GPIO 25** (a confirmar na
  montagem).

**Alternativa descartada.** Arduino + ESP32 por UART. Exigiria comprar um Arduino, um
divisor de nível 5 V → 3,3 V, dois firmwares e um protocolo serial entre eles, e não
acrescentaria nenhuma medição que a T-Beam não faça.

**Consequências.**
- Não há camada UART: o protocolo serial do prompt (Camada 2) não se aplica.
- A calibração do pH feita no protótipo continua valendo (mesmo ADC, mesmo divisor).
- O ADC do ESP32 (12 bits, média de 32 amostras) dá resolução melhor que 0,01 pH.
- O campo "Identificação do Arduino" da tela de tempo real é substituído por
  **versão do firmware** e **estado dos sensores** do próprio dispositivo.
- O GPIO 33 continua proibido para sensores: é ligado ao rádio LoRa.

---

<a id="adr-02"></a>
## ADR-02 — Backend em FastAPI (Python)

**Contexto.** O prompt pede Node.js + TypeScript + Express. O relatório (Capítulo 8,
Tabela 5) descreve a API em **FastAPI**, e o sistema de inventário já feito pelo grupo
usa FastAPI.

**Decisão.** Backend em **Python 3.12 + FastAPI**, com SQLAlchemy 2 (ORM), Alembic
(migrations), Pydantic (validação), paho-mqtt (cliente MQTT) e WebSocket nativo do FastAPI.
O PostgreSQL do prompt é mantido.

**Consequências.**
- O código bate com o que o relatório apresenta à banca.
- A documentação da API sai pronta pelo OpenAPI do FastAPI em `/docs`.
- A estrutura de pastas do prompt (pensada para Express) foi adaptada:
  `controllers/` + `routes/` viram `api/routes/`, e entra `schemas/` para validação.
- O frontend continua em React + TypeScript, como no prompt.

---

<a id="adr-03"></a>
## ADR-03 — Acidez Dornic é registro manual, não telemetria

**Contexto.** O exemplo de mensagem do prompt traz `"acidity": 16.5` vindo do hardware.
No projeto, a acidez titulável é medida por **titulação com NaOH 1/9N e fenolftaleína**
(relatório, Tabela 1 e Seção 4.2). Não há sensor que faça isso. O próprio prompt diz que
pH e acidez são grandezas diferentes e que não se deve inventar sensores.

**Decisão.**
- A telemetria **não tem campo de acidez**.
- A acidez entra pelo **registro de coleta**, junto com densidade, litragem,
  amostra testemunha e decisão de aceite ou recusa (relatório, Seção 8.1, "App do coletor").
- O indicador "acidez média" do dashboard é calculado sobre esses registros.

**Consequências.**
- A tabela `Telemetry` do prompt perde a coluna `acidity`, e surge uma tabela de
  **coletas** (Etapa 2).
- A tela de tempo real mostra pH e temperatura ao vivo, e a acidez como **"último
  registro do coletor, há X horas"**, nunca como valor em tempo real.
- Se um dia houver um equipamento de acidez com saída digital, ele entra como novo
  campo da telemetria sem mudar o resto.

---

<a id="adr-04"></a>
## ADR-04 — Temperatura do leite ≠ temperatura do ar

**Contexto.** O limite da cadeia do frio (≤ 7 °C, relatório Tabela 1 e Seção 5.3) vale
para o **leite**. O DHT22 mede o **ar**. O relatório também mostra que a compensação do
pH depende da temperatura do líquido (Seção 3.4). A sonda DS18B20 existe, mas ainda não
foi integrada (Seção 7.7).

**Decisão.** Três campos separados: `milk_temperature` (DS18B20), `air_temperature` e
`air_humidity` (DHT22). Os alertas de cadeia do frio usam **apenas** `milk_temperature`.

**Consequências.**
- Enquanto a DS18B20 não estiver ligada, `milk_temperature` chega como `null` e o painel
  mostra **"sem sensor"**. A temperatura do ar nunca é usada no lugar.
- A compensação de temperatura do pH fica prevista para quando a DS18B20 estiver ligada.

---

<a id="adr-05"></a>
## ADR-05 — A hora da medição é carimbada no ESP32

**Contexto.** O ESP32 não tem relógio com bateria: ao ligar, ele não sabe a hora. A leitura precisa preservar a hora original mesmo quando fica horas na fila
offline, sem internet, portanto sem NTP.

**Decisão.** O ESP32 carimba `measured_at` em UTC no momento em que aceita o quadro,
usando a melhor fonte disponível, informada em `time_source`:

| Ordem | `time_source` | Quando |
|-------|---------------|--------|
| 1 | `ntp` | Wi-Fi conectado e relógio sincronizado |
| 2 | `gps` | Sem internet, mas com sinal de GPS (a T-Beam tem receptor) |
| 3 | `estimated` | Já sincronizou antes nesta mesma inicialização; hora = última sincronização + tempo decorrido |
| 4 | `none` | Ligou sem internet e sem GPS e ainda não sincronizou |

**Consequências.**
- Leituras `none` são gravadas, mas ficam fora de gráficos e indicadores (não dá para
  saber quando aconteceram). Se o relógio sincronizar na mesma inicialização, o ESP32
  corrige as pendentes antes de enviar.
- A hora nunca é calculada no servidor: `received_at` (servidor) e `measured_at`
  (dispositivo) são campos diferentes.

---

<a id="adr-06"></a>
## ADR-06 — Wi-Fi direto até um Mosquitto próprio

**Contexto.** O relatório propõe LoRa até um gateway e AWS IoT Core. O grupo escolheu
**Wi-Fi direto**, com uma placa só. Para a disciplina, o sistema precisa rodar em um
computador comum, sem custo de nuvem.

**Decisão.** A T-Beam conecta no Wi-Fi (roteador, ou hotspot do celular no caminhão)
e publica em um **Eclipse Mosquitto 2** que roda no Docker Compose, junto com o backend.

**Consequências.**
- Tudo roda localmente com `docker compose up`.
- Os tópicos e payloads são MQTT padrão: migrar para o AWS IoT Core depois exige trocar
  a autenticação (certificado por dispositivo) e o endereço, não o protocolo.
- Na estrada, sem Wi-Fi, quem segura os dados é a fila offline (ADR-07). O rádio LoRa da
  T-Beam fica livre para uma evolução futura.
- O computador que roda o broker precisa liberar a porta 1883 no firewall do Windows.

---

<a id="adr-07"></a>
## ADR-07 — Entrega confiável: fila em flash + QoS 1 + id único

**Contexto.** A conexão no transporte é instável. Nenhuma leitura pode se perder, e
nenhuma pode ser contada duas vezes.

**Decisão.**
1. O ESP32 grava cada leitura numa **fila em LittleFS** antes de enviar.
2. Publica com **QoS 1** e só remove da fila depois do **PUBACK** do broker.
3. Cada leitura tem um `msg_id` = `<device_id>-<boot>-<seq>`. O contador de
   inicializações (`boot`) fica salvo na memória NVS, então o id nunca se repete,
   nem depois de desligar a placa.
4. O backend usa **sessão persistente** (`clean_session=False`): se ele cair, o
   broker guarda as mensagens.
5. O banco tem restrição de unicidade em (`device_id`, `msg_id`). Uma retransmissão
   vira `ON CONFLICT DO NOTHING`.

**Consequências.**
- Garantia "pelo menos uma vez" ponta a ponta, transformada em "exatamente uma vez" no banco.
- A fila tem tamanho limitado pela flash (definido na Etapa 5). Quando enche, o ESP32
  avisa no tópico `alerts` e descarta **as mais antigas**, e o descarte fica registrado.
- O PUBACK confirma que o **broker** recebeu, não que o banco gravou. A sessão persistente
  do backend cobre esse intervalo. Uma confirmação de aplicação (backend → dispositivo)
  fica como evolução, se os testes mostrarem necessidade.

---

<a id="adr-08"></a>
## ADR-08 — Um usuário MQTT por dispositivo, com ACL

**Contexto.** O prompt exige autenticação MQTT e controle de acesso aos dispositivos.

**Decisão.**
- Broker **sem acesso anônimo**.
- O usuário MQTT de cada dispositivo **é o próprio `device_id`**. A ACL usa
  `pattern write smartmilk/device/%u/...`, então um dispositivo só publica nos próprios
  tópicos e não lê os dos outros.
- O backend tem usuário próprio, que lê todos os tópicos de dispositivo.
- O backend também confere se o `device_id` do payload é igual ao do tópico.
- Senhas e ACL são geradas na inicialização a partir do `.env` e nunca entram no Git.
- Porta 1883 sem TLS **só na rede local**. Para rede externa, ouvinte 8883 com TLS
  (configuração já preparada e comentada em `mosquitto.conf`).

**Consequências.**
- Testado na Etapa 1: anônimo recusado, senha errada recusada, dispositivo não consegue
  publicar como outro nem ler a telemetria alheia.
- Cadastrar um dispositivo novo = acrescentar `id:senha` em `MQTT_DEVICE_CREDENTIALS`
  e reiniciar o broker. Na Etapa 3, isso passa a ser feito pela tela de dispositivos.

---

<a id="adr-09"></a>
## ADR-09 — Limites de qualidade são parâmetros configuráveis

**Contexto.** O prompt proíbe valores arbitrários como limites oficiais.
O relatório traz faixas de referência na Tabela 1 (pH 6,6 a 6,8; acidez 14 a 18 °D;
temperatura ≤ 7 °C na coleta e ≤ 10 °C na recepção) e cita a IN MAPA 76/77.

**Decisão.**
- Os limites ficam na tabela `quality_parameters`, com unidade, faixa, **contexto**
  (coleta, transporte, recepção), **início e fim de vigência** e **fonte técnica**.
- A carga inicial usa os valores da Tabela 1, com a fonte "Relatório do grupo, Tabela 1"
  e a marcação **"a revisar pelo administrador"**, até alguém conferir na norma.
- Mudar um limite cria uma nova versão. As leituras antigas continuam avaliadas pelo
  limite que valia na data delas.

---

<a id="adr-10"></a>
## ADR-10 — O simulador é um dispositivo cadastrado como simulado

**Contexto.** O prompt pede um simulador de hardware cujas leituras não se misturem
com as reais.

**Decisão.** O simulador publica pelo mesmo caminho MQTT, com um usuário próprio
(`sim-001`). O cadastro do dispositivo tem `is_simulated = true`, e é **o cadastro**
que marca as leituras como simuladas. Se o payload disser o contrário do cadastro, a
leitura é rejeitada.

**Consequências.**
- O simulador testa o fluxo completo (broker, ACL, backend, banco, WebSocket).
- Indicadores e relatórios filtram `is_simulated = false` por padrão. O painel mostra
  uma faixa **SIMULADO** sempre que exibe esses dados.
