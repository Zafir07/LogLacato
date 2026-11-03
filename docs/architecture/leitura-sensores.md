# Leitura dos sensores na T-Beam

Como o firmware da T-Beam lê, confere e empacota cada medição antes de publicar no MQTT.
Implementação e testes: **Etapa 5**. Ligações físicas: [docs/hardware](../hardware/README.md).

## 1. Sensores e pinos

| Sensor | Grandeza | Pino da T-Beam | Situação |
|--------|----------|----------------|----------|
| HW-828 + sonda | pH do leite | **VP / GPIO 36** (ADC1), Po dividido por 2 (R1 = R2 = 560 Ω) | ✅ montado no protótipo |
| DHT22 | temperatura e umidade do **ar** | dados **GPIO 13**, alimentação **GPIO 14** | ✅ montado no protótipo |
| DS18B20 | temperatura do **leite** | **GPIO 25** (OneWire), pull-up de ~4,7 kΩ ao 3,3 V | ⏳ a integrar |
| GPS da placa | hora UTC e posição | interno (Serial1) | ✅ vem na placa |

O GPIO 33 não pode ser usado: é ligado ao rádio LoRa (relatório, Seção 7.3).

## 2. Ciclo de leitura

A cada **5 s** (configurável; o DHT22 exige no mínimo 2 s):

1. **pH:** média de 32 leituras de `analogReadMilliVolts(36)`, × 2 (divisor) = tensão do Po.
   Conversão pela reta de dois pontos (tampões pH 4 e pH 7):
   `pH = 7 + (V_pH7 − V) / ((V_pH4 − V_pH7) / 3)`.
2. **Ar:** `dht.readTemperature()` e `dht.readHumidity()`.
3. **Leite:** `DallasTemperature.requestTemperatures()` + `getTempCByIndex(0)`.
4. Confere as faixas físicas e liga os bits de `sensor_flags` (tabela abaixo).
5. Carimba `measured_at` e `time_source` (ADR-05) e gera o `msg_id` (ADR-07).
6. Grava a leitura na fila em flash e publica (ver [protocolo-mqtt.md](protocolo-mqtt.md)).

A leitura não bloqueia o resto do programa: Wi-Fi, MQTT e GPS continuam sendo atendidos
entre um ciclo e outro.

## 3. Faixas físicas e valores nulos

Valor que não pôde ser medido vai como **`null`**, nunca como 0, −127 ou NaN.

| Campo | Faixa física aceita | Fora da faixa |
|-------|---------------------|---------------|
| `ph` | 0 a 14 | vai `null` e liga o bit 2; a tensão bruta continua em `ph_voltage` |
| `ph_voltage` | 0 a 5,5 V | abaixo de 0,1 V liga o bit 1 (sem sinal) |
| `air_temperature` | −40 a 80 °C | `null` + bit 0 |
| `air_humidity` | 0 a 100 % | `null` + bit 0 |
| `milk_temperature` | −55 a 125 °C | `null` + bit 4 |

O firmware só descarta o que é **fisicamente impossível**. Os limites de **qualidade**
(pH 6,6 a 6,8, leite ≤ 7 °C…) são decididos pelo backend, com os parâmetros vigentes (ADR-09).

## 4. Bits de `sensor_flags`

| Bit | Valor | Significado | Mensagem do protótipo atual |
|-----|-------|-------------|-----------------------------|
| 0 | 1 | DHT22 não respondeu ou checksum errado | "DHT22: ERRO de leitura" |
| 1 | 2 | pH sem sinal (Po < 0,1 V: fio solto, divisor, sonda) | "pH: sem sinal" |
| 2 | 4 | pH fora de 0–14 (calibração necessária) | "fora da faixa, calibre o modulo" |
| 3 | 8 | DS18B20 não encontrada no barramento | — |
| 4 | 16 | DS18B20 encontrada, mas leitura inválida (−127 °C ou 85 °C de inicialização) | — |

Os três primeiros são os mesmos diagnósticos que o código do relatório (Quadro 1) já imprime
no Monitor Serial. A diferença é que agora eles viajam junto com a leitura.

Exemplo: protótipo atual, sem a DS18B20 ligada → `sensor_flags = 8`.

## 5. Calibração

- As constantes `PH7_VOLTS` e `PH4_VOLTS` ficam num arquivo de configuração do firmware
  (Etapa 5), não espalhadas pelo código.
- A tensão bruta do Po (`ph_voltage`) é enviada em toda leitura. Se a calibração for
  refeita, dá para recalcular o pH das leituras antigas e conferir a diferença.
- Compensação de temperatura no pH (inclinação de Nernst, relatório Seção 3.4): prevista
  para quando a DS18B20 estiver medindo o leite.

## 6. Como será testado (Etapa 5)

- A conversão tensão → pH, as faixas e os bits ficam num módulo C++ que não depende
  das bibliotecas da placa, compilado e testado no PC.
- Na bancada: tampões pH 4 e 7; soltar o fio do Po, do DHT22 e da DS18B20 de propósito e
  conferir o bit correspondente chegando no backend.
