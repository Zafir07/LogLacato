# Protocolo MQTT — dispositivo ↔ servidor

Versão dos payloads: **1**. Broker: Eclipse Mosquitto 2 (configuração em
`infrastructure/mqtt/`). Consumo no backend: Etapa 4. Firmware: Etapa 5.

## 1. Conexão

| Parâmetro | Dispositivo (ESP32 / simulador) | Backend |
|-----------|--------------------------------|---------|
| Usuário | o próprio `device_id` (ex.: `esp32-001`) | `MQTT_BACKEND_USER` |
| Client ID | o próprio `device_id` | `loglacto-backend` |
| Porta | 1883 na rede local; 8883 com TLS fora dela | idem |
| Keepalive | 30 s | 30 s |
| Clean session | `true` (quem guarda as pendentes é a fila em flash) | **`false`** (o broker guarda as mensagens se o backend cair) |
| Reconexão | espera crescente: 1, 2, 4… até 60 s | 1 a 30 s (paho) |
| Last Will | `status` → `{"v":1,"device_id":"…","state":"offline","reason":"lwt"}`, QoS 1, retido | — |

## 2. Tópicos

```
smartmilk/device/{device_id}/telemetry   dispositivo → servidor   QoS 1   não retido
smartmilk/device/{device_id}/status      dispositivo → servidor   QoS 1   RETIDO
smartmilk/device/{device_id}/alerts      dispositivo → servidor   QoS 1   não retido
smartmilk/device/{device_id}/cmd         servidor → dispositivo   QoS 1   reservado
```

A ACL do broker garante que cada dispositivo só escreve nos tópicos com o próprio id
(testado na Etapa 1). O backend também confere se o `device_id` do tópico é igual ao do
payload e rejeita a mensagem se não for.

## 3. `telemetry` — uma leitura

```json
{
  "v": 1,
  "msg_id": "esp32-001-00017-000001234",
  "device_id": "esp32-001",
  "measured_at": "2026-11-03T18:30:05Z",
  "time_source": "ntp",
  "readings": {
    "ph": 6.65,
    "ph_voltage": 2.563,
    "milk_temperature": null,
    "air_temperature": 21.4,
    "air_humidity": 65.2
  },
  "sensor_flags": 8,
  "gps": { "lat": -28.3880, "lon": -53.9150, "fix": true, "sats": 7 },
  "buffered": false,
  "simulated": false,
  "fw": "0.1.0"
}
```

| Campo | Regra |
|-------|-------|
| `msg_id` | `<device_id>-<boot 5 dígitos>-<seq 9 dígitos>`. Único para sempre: `boot` vem da NVS e cresce a cada inicialização |
| `measured_at` | UTC, ISO 8601. `null` só quando `time_source = "none"` |
| `time_source` | `ntp`, `gps`, `estimated` ou `none` (ADR-05) |
| `readings.*` | `null` quando o sensor não mediu. Nunca 0 no lugar de "não sei" |
| `sensor_flags` | bits de falha dos sensores ([leitura-sensores.md](leitura-sensores.md#4-bits-de-sensor_flags)) |
| `gps` | `null` sem fix |
| `buffered` | `true` quando a leitura ficou na fila offline antes de ser enviada |
| `simulated` | precisa bater com o cadastro do dispositivo (ADR-10) |

Não existe campo de acidez (ADR-03).

## 4. `status` — estado do dispositivo (retido)

Publicado ao conectar, a cada 60 s e quando algo muda.
Por ser retido, quem assina o tópico recebe na hora o último estado conhecido.

```json
{
  "v": 1,
  "device_id": "esp32-001",
  "state": "online",
  "at": "2026-11-03T18:30:00Z",
  "fw": "0.1.0",
  "uptime_s": 3600,
  "ip": "192.168.0.42",
  "wifi_rssi": -61,
  "time_source": "ntp",
  "gps_fix": true,
  "queue": { "pending": 0, "capacity": 20000, "dropped": 0 },
  "sensors": {
    "ph":     { "state": "ok",     "last_ok_at": "2026-11-03T18:29:58Z" },
    "dht22":  { "state": "ok",     "last_ok_at": "2026-11-03T18:29:58Z" },
    "ds18b20":{ "state": "absent", "last_ok_at": null }
  },
  "readings_total": 1520
}
```

Quando a conexão cai sem aviso, o broker publica o Last Will (`state: "offline"`).

## 5. `alerts` — falhas vistas pelo próprio dispositivo

```json
{
  "v": 1,
  "device_id": "esp32-001",
  "code": "SENSOR_FAULT",
  "severity": "warning",
  "at": "2026-11-03T18:31:00Z",
  "message": "pH sem sinal há 3 leituras seguidas (Po < 0,1 V)",
  "details": { "sensor": "ph", "sensor_flags": 2, "ph_voltage": 0.012 }
}
```

| `code` | Quando |
|--------|--------|
| `SENSOR_FAULT` | um bit de `sensor_flags` ficou ligado por 3 leituras seguidas |
| `QUEUE_HIGH` | fila acima de 80 % |
| `QUEUE_DROPPED` | fila cheia; leituras mais antigas descartadas (`details.count`) |
| `TIME_UNSYNCED` | 10 min ligado sem NTP e sem GPS |

Os alertas de **qualidade do leite** (pH, temperatura, acidez) **não** vêm do dispositivo:
quem decide é o backend, com os parâmetros vigentes (ADR-09).

## 6. O que o backend faz ao receber (Etapa 4)

1. Lê o `device_id` do tópico e procura o dispositivo. Desconhecido → descarta e registra auditoria.
2. Valida o JSON com o esquema da versão `v`. Inválido → guarda o bruto numa tabela de
   rejeitados, com o motivo.
3. Confere `device_id` do payload = do tópico, e `simulated` = cadastro.
4. Grava com `received_at = agora`. Duplicata (`device_id` + `msg_id`) é ignorada.
5. Classifica a leitura:

| `validation_status` | Significado | Entra nos indicadores? |
|---------------------|-------------|------------------------|
| `valid` | tudo dentro das faixas físicas | sim |
| `partial` | algum campo inválido (ex.: pH fora de 0–14); os outros valem | só os campos válidos |
| `invalid` | nenhum campo aproveitável | não |
| `time_unknown` | `time_source = none` | não |

6. Associa à viagem do veículo cujo intervalo contém `measured_at`.
7. Avalia as regras de alerta e avisa o painel pelo WebSocket.

## 7. Garantias de entrega

| Falha | Quem segura o dado |
|-------|--------------------|
| Sem Wi-Fi / sem broker | fila em flash no ESP32 |
| Broker recebeu, backend fora do ar | sessão persistente do backend no broker (persistência em disco) |
| Mensagem repetida na reconexão | unicidade de (`device_id`, `msg_id`) no banco |
| Sensor desligado ou fio solto | a leitura chega com o campo `null` e o bit de falha; o ESP32 avisa `SENSOR_FAULT` e o backend não conta o campo nos indicadores |
| Placa desligada | nada chega: o broker publica o Last Will (`offline`) e o backend abre alerta de ausência de leitura |
