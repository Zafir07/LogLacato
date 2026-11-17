# Firmware da T-Beam V1.2 (Etapa 5)

Uma placa só faz tudo no caminhão. A cada 5 s ela:

1. **Lê os sensores:** pH (HW-828 no VP / GPIO 36), ar (DHT22 no GPIO 13, alimentado pelo
   GPIO 14) e leite (DS18B20 no GPIO 25, desligada até `USE_DS18B20 = 1`).
2. **Confere** as faixas físicas e marca falhas em `sensor_flags`.
3. **Carimba a hora** (NTP → GPS → estimada) e gera o `msg_id` único.
4. **Grava na fila** em LittleFS **antes** de enviar.
5. **Publica no MQTT** com QoS 1 e só apaga da fila depois do PUBACK do broker.
6. **Publica o estado** (retido, a cada 60 s) e usa Last Will para avisar quando cai.

Especificações: [leitura dos sensores](../../docs/architecture/leitura-sensores.md) e
[protocolo MQTT](../../docs/architecture/protocolo-mqtt.md).

## Online e offline

| Situação | O que acontece |
|----------|----------------|
| Wi-Fi + broker no ar | leitura vai para o painel em ~1 s (`buffered: false`) |
| Rede local **sem internet** (roteador da fazenda, celular sem dados) | funciona igual: o broker e o painel rodam no computador da mesma rede. A hora vem do GPS |
| **Sem rede nenhuma** (estrada) | continua medindo e guarda até **3000 leituras (~4 h)** no flash. Dá para ver tudo no Wi-Fi da própria placa (`LogLacto-esp32-001`, <http://192.168.4.1>) e no display |
| A rede volta | reenvia o que ficou guardado, na ordem, com a hora original e `buffered: true`. O backend descarta repetidas pelo `msg_id` |
| Broker ou servidor fora do ar | igual a "sem rede": guarda e reenvia depois |
| Placa desligada no meio | a fila sobrevive; ao religar, continua de onde parou |
| Fila cheia | descarta as **mais antigas** e avisa o painel (`QUEUE_DROPPED`) |
| Caminhão longe do servidor | a placa usa o Wi-Fi do celular (4G) e publica num broker na nuvem; o Mosquitto do servidor busca de lá ([ponte](#online-fora-da-rede-local)) |

## Arquivos

| Arquivo | Conteúdo |
|---------|----------|
| `loglacto_tbeam/loglacto_tbeam.ino` | programa principal: sensores, Wi-Fi, MQTT, página, display |
| `loglacto_tbeam/config.h` | pinos, calibração do pH (`PH7_VOLTS`, `PH4_VOLTS`), intervalos, tamanho da fila |
| `loglacto_tbeam/secrets.example.h` | modelo das redes Wi-Fi, brokers e senha. Copie para `secrets.h` (fica fora do Git) |
| `loglacto_tbeam/logica.h` | conversão do pH, faixas, bits, `msg_id`, datas UTC (sem dependência da placa) |
| `loglacto_tbeam/fila.h/.cpp` | fila offline em segmentos no LittleFS |
| `loglacto_tbeam/payload.h` | JSON de telemetria e alertas |
| `loglacto_tbeam/pagina.h` | página que a placa serve (modo offline) |
| `testes/` | testes no PC da lógica, da fila e do JSON (contra o esquema do backend) |

## Gravar na placa (Arduino IDE 2)

1. **Placa:** em *Preferências → URLs adicionais* coloque
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`, instale **esp32 by
   Espressif** (2.0.x ou 3.x) e escolha a placa **ESP32 Dev Module** (ou "T-Beam").
2. **Bibliotecas** (*Ferramentas → Gerenciar bibliotecas*):

   | Biblioteca | Autor |
   |------------|-------|
   | MQTT | Joel Gaehwiler (256dpi) |
   | ArduinoJson (7.x) | Benoit Blanchon |
   | TinyGPSPlus | Mikal Hart |
   | DHT sensor library (+ Adafruit Unified Sensor) | Adafruit |
   | XPowersLib | Lewis He |
   | Adafruit SSD1306 (+ Adafruit GFX) | Adafruit |
   | OneWire e DallasTemperature | só quando `USE_DS18B20 = 1` |

3. **Partição:** *Ferramentas → Partition Scheme →* "Default 4MB with spiffs" (fila de 3000
   leituras). Com "No OTA (2MB APP/2MB SPIFFS)" dá para subir `FILA_SEGMENTOS` para 50.
4. **Segredos:** copie `secrets.example.h` para `secrets.h` e preencha:
   - `MQTT_SENHA` = a senha do `esp32-001` em `MQTT_DEVICE_CREDENTIALS` no `.env` do servidor;
   - `REDES_WIFI` = a rede do computador servidor e o roteador do celular;
   - `BROKERS` = o IP do computador servidor (`ipconfig` no Windows, "Endereço IPv4").
5. Grave e abra o **Monitor Serial a 115200**. Esperado:

   ```
   [fila] 0 leitura(s) guardada(s) de antes; capacidade 3000
   [wifi] conectado em "MinhaRede" — página da placa: http://192.168.0.57
   [mqtt] conectado em local — 0 leitura(s) na fila para enviar
   [leitura 3] pH 6.65 (Po 2.563 V) | ar 27.9 C 61 % | flags 8 | GPS fix 8 sat | hora ntp | fila 0 | local
   ```

   `flags 8` é normal enquanto a DS18B20 não estiver ligada.

## No servidor

1. Use a versão do repositório com o painel (branch `main`) e suba: `docker compose up -d --build`.
2. No `.env`, `MQTT_DEVICE_CREDENTIALS` precisa ter `esp32-001:<a mesma senha do secrets.h>` e
   `SEED_DEMO=true` (cadastra o `esp32-001` no caminhão de demonstração).
3. Libere a porta **1883** no Firewall do Windows (PowerShell como administrador):

   ```powershell
   New-NetFirewallRule -DisplayName "LogLacto MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Private
   ```

4. Abra o painel em <http://localhost> → **Tempo real**: o `esp32-001` aparece online.

## Online fora da rede local

Quando o caminhão está longe do servidor, a placa usa o roteador do celular (4G). Como a
internet de casa quase nunca deixa entrar conexões de fora (CGNAT), o caminho mais simples é
uma **ponte**: a placa publica num broker MQTT na nuvem e o Mosquitto do servidor **busca** as
mensagens de lá (conexão de saída, sem abrir porta no roteador).

1. Crie um cluster grátis no [HiveMQ Cloud](https://www.hivemq.com/products/mqtt-cloud-broker/)
   (ou outro broker com TLS) e duas credenciais: uma para a placa (`esp32-001`) e uma para a
   ponte (`loglacto-ponte`).
2. No `.env` do servidor: `MQTT_BRIDGE_HOST=<endereço do cluster>`, `MQTT_BRIDGE_USER` e
   `MQTT_BRIDGE_PASSWORD` da ponte. Reinicie o broker: `docker compose up -d mosquitto`.
   O log mostra `ponte com ... ativada`.
3. No `secrets.h`, descomente a linha `nuvem` em `BROKERS` com o endereço e a credencial da
   placa. A placa tenta o broker local primeiro e, se não achar, vai para a nuvem.

A ponte só **traz** `telemetry`, `status` e `alerts`; nada do servidor sobe para a nuvem. O
backend continua conferindo o `device_id` de cada mensagem. Num servidor com IP público
(VPS), dá para dispensar a ponte: ative o ouvinte 8883 com TLS que já está comentado em
`infrastructure/mqtt/mosquitto.conf` e aponte a placa para o domínio do servidor.

## Testes no PC

```sh
cd firmware/esp32/testes
./rodar_testes.sh            # usa ~/Arduino/libraries/ArduinoJson/src
```

Conferem a conversão do pH, os bits de `sensor_flags`, o `msg_id`, a fila (ordem, reinício,
linha cortada por falta de energia, fila cheia) e se o JSON gerado passa no esquema do backend.

## Teste de bancada (Etapa 5)

1. Com tudo ligado, confira a leitura no painel em **Tempo real**.
2. Desligue o Wi-Fi do roteador (ou pare o broker: `docker compose stop mosquitto`). O display
   mostra `OFFLINE fila N` e o painel marca o dispositivo como offline (Last Will).
3. Espere alguns minutos e religue. O Monitor Serial mostra
   `[fila] reenviando o que ficou guardado...` e o painel recebe as leituras com a hora
   original, marcadas como guardadas (`buffered`).
4. Repita desligando a **placa** enquanto está offline: ao religar, ela reenvia o que guardou.
5. Solte o fio do Po: depois de 3 leituras chega o alerta `SENSOR_FAULT` (bit 2 = valor 2).
