// Configuração do firmware da T-Beam V1.2 (LogLacto).
// Pinos e calibração conforme docs/architecture/leitura-sensores.md.
// Senhas e redes NÃO ficam aqui: vão em secrets.h (copie de secrets.example.h).
#pragma once

#define FW_VERSION "0.2.0"

// ---------------------------------------------------------------- pinos
#define PIN_DHT_DATA   13   // dados do DHT22
#define PIN_DHT_POWER  14   // alimenta o DHT22 (3,3 V por software)
#define PIN_PH         36   // VP, ADC1, sinal do Po dividido por 2
#define PIN_DS18B20    25   // OneWire da DS18B20 (temperatura do leite)
#define PIN_I2C_SDA    21   // OLED + gerenciador de energia (AXP)
#define PIN_I2C_SCL    22
#define PIN_GPS_RX     34   // GPS da placa (Serial1)
#define PIN_GPS_TX     12
#define GPS_BAUD       9600

// ---------------------------------------------------------------- recursos opcionais
// 1 = a DS18B20 está ligada no GPIO 25 (precisa das bibliotecas OneWire e DallasTemperature)
// 0 = ainda não ligada: milk_temperature vai null e sensor_flags leva o bit 3 (valor 8)
#define USE_DS18B20    0
// 1 = liga o GPS e lê a bateria pelo AXP2101/AXP192 (biblioteca XPowersLib)
#define USE_PMU        1
// 1 = display OLED SSD1306 0,96" (endereço 0x3C)
#define USE_OLED       1
// 1 = a placa cria o próprio Wi-Fi "LogLacto-<id>" para ver as leituras sem rede nenhuma
#define USE_AP         1

// ---------------------------------------------------------------- leitura
#define INTERVALO_MS   5000   // tempo entre leituras (DHT22 exige no mínimo 2 s)
#define AMOSTRAS_PH    32     // leituras do ADC na média do pH
#define FATOR_DIVISOR  2.0f   // R1 = R2 = 560 Ω: o pino recebe Po / 2

// Calibração do pH: tensão do Po (V) com a sonda nos tampões pH 7 e pH 4.
// Os valores abaixo são os típicos de fábrica do relatório (Seção 7.5).
// Troque pelos que você mediu (o "Po" aparece no Monitor Serial e na página da placa).
#define PH7_VOLTS      2.50f
#define PH4_VOLTS      3.04f

// ---------------------------------------------------------------- fila offline (LittleFS)
// Cada leitura ocupa ~350 bytes. 30 segmentos x 100 leituras = 3000 leituras
// (~4 h guardando uma a cada 5 s) e cabe na partição padrão de 1,5 MB.
// Com o esquema "No OTA (2MB APP/2MB SPIFFS)" dá para subir FILA_SEGMENTOS para 50.
#define FILA_LINHAS_SEGMENTO  100
#define FILA_SEGMENTOS        30
#define FILA_MIN_LIVRE        (24 * 1024)   // descarta a mais antiga se o flash ficar sem espaço
#define ENVIOS_POR_VOLTA      20            // reenvios por volta do loop (não trava a página)

// ---------------------------------------------------------------- conexão
#define WIFI_TEMPO_TENTATIVA_MS   12000   // quanto tempo espera cada rede responder
#define WIFI_PAUSA_ENTRE_RODADAS  30000   // depois de tentar todas as redes, espera isso
#define MQTT_KEEPALIVE_S          30
#define MQTT_TIMEOUT_MS           4000    // espera do CONNACK/PUBACK
#define MQTT_ESPERA_MAX_MS        60000   // espera crescente 1, 2, 4… até 60 s
#define STATUS_INTERVALO_MS       60000   // status retido a cada 60 s
#define NTP_SERVIDOR_1            "a.st1.ntp.br"
#define NTP_SERVIDOR_2            "pool.ntp.org"
