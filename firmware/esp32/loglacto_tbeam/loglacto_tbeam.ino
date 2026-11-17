// LogLacto — firmware da LilyGO T-Beam V1.2 (Etapa 5)
//
// A cada 5 s: lê pH (VP/GPIO 36), ar (DHT22) e, se ligada, a DS18B20; carimba a hora
// (NTP -> GPS -> estimada); grava a leitura na FILA EM FLASH; e envia ao painel pelo MQTT.
//
//   ONLINE  -> Wi-Fi + broker: publica com QoS 1 e só apaga da fila depois do PUBACK.
//   OFFLINE -> sem rede ou sem broker: continua medindo e guardando (~4 h). Quando a
//              conexão volta, reenvia tudo com "buffered": true e a hora original.
//              Sem rede nenhuma, dá para ver as leituras no Wi-Fi da própria placa
//              (LogLacto-<id>, http://192.168.4.1) e no display.
//
// Protocolo: docs/architecture/protocolo-mqtt.md · Sensores: docs/architecture/leitura-sensores.md
// Bibliotecas e passo a passo: firmware/esp32/README.md

#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <LittleFS.h>
#include <MQTT.h>
#include <Preferences.h>
#include <TinyGPSPlus.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <esp_sntp.h>
#include <sys/time.h>
#include <time.h>

#include "config.h"
#include "secrets.h"
#include "logica.h"
#include "fila.h"
#include "payload.h"
#include "armazenamento_littlefs.h"
#include "pagina.h"

#if USE_OLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#endif
#if USE_PMU
#include <XPowersLib.h>
#endif
#if USE_DS18B20
#include <DallasTemperature.h>
#include <OneWire.h>
#endif

static const int N_REDES = sizeof(REDES_WIFI) / sizeof(REDES_WIFI[0]);
static const int N_BROKERS = sizeof(BROKERS) / sizeof(BROKERS[0]);
static const int HIST_N = 60;   // 60 leituras x 5 s = 5 minutos na página da placa

// ---------------------------------------------------------------- objetos
DHT dht(PIN_DHT_DATA, DHT22);
TinyGPSPlus gps;
WebServer web(80);
WiFiClient redeSimples;
WiFiClientSecure redeTls;
MQTTClient mqtt(1024);
Preferences prefs;
ArmazenamentoLittleFS armazenamento;
Fila fila;
#if USE_OLED
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
bool oledOk = false;
#endif
#if USE_PMU
XPowersLibInterface* pmu = nullptr;
#endif
#if USE_DS18B20
OneWire umFio(PIN_DS18B20);
DallasTemperature ds(&umFio);
#endif

// ---------------------------------------------------------------- estado
uint32_t contagemBoot = 0, sequencia = 0, leiturasTotal = 0, enviadas = 0;
uint32_t ultimaLeituraMs = 0, ultimoStatusMs = 0, ultimoOledMs = 0, ultimaBateriaMs = 0;
Medicao ultima;
bool temUltima = false, leituraParaMostrar = false;
char msgIdRecente[48] = "";
uint32_t recenteMs = 0;
float historico[HIST_N];
int histPos = 0;
int bateriaPct = -1;
bool carregando = false;

// relógio (ADR-05)
volatile bool ntpChegou = false;
bool ntpOk = false, relogioAcertado = false;
uint32_t ultimoNtpMs = 0, ultimoAcertoGpsMs = 0;

// Wi-Fi
int redeAtual = -1, tentativasNaRodada = 0;
bool wifiTentando = false, wifiConectado = false, emPausaWifi = false;
uint32_t inicioTentativaMs = 0, inicioPausaMs = 0;

// MQTT
int brokerAtual = 0;
uint32_t proximaTentativaMqtt = 0, esperaMqtt = 1000;
const char* brokerConectado = nullptr;
char topTelemetria[64], topStatus[64], topAlertas[64], statusOffline[112];

// alertas do dispositivo (ficam na RAM até haver conexão)
static const int MAX_ALERTAS = 6, TAM_ALERTA = 400;
char alertasPendentes[MAX_ALERTAS][TAM_ALERTA];
int nAlertas = 0;
uint8_t sequenciaFalha[5] = {0, 0, 0, 0, 0};
bool filaAltaAvisada = false, horaAvisada = false;
time_t okPh = 0, okDht = 0, okDs = 0;

bool passou(uint32_t desde, uint32_t ms) { return (uint32_t)(millis() - desde) >= ms; }

// ================================================================ relógio
void aoSincronizarNtp(struct timeval* tv) { ntpChegou = true; }

void cuidarRelogio() {
  if (ntpChegou) {
    ntpChegou = false;
    if (!ntpOk) Serial.println("[hora] sincronizada pela internet (NTP)");
    ntpOk = true;
    relogioAcertado = true;
    ultimoNtpMs = millis();
  }
  const bool ntpRecente = ntpOk && !passou(ultimoNtpMs, 2 * 3600000UL);
  if (!ntpRecente && gps.date.isValid() && gps.time.isValid() && gps.time.age() < 1500 &&
      gps.date.year() >= 2025 && (!relogioAcertado || passou(ultimoAcertoGpsMs, 60000))) {
    int64_t t = logica::epocaUtc(gps.date.year(), gps.date.month(), gps.date.day(),
                                 gps.time.hour(), gps.time.minute(), gps.time.second());
    struct timeval tv = {(time_t)t, 0};
    settimeofday(&tv, nullptr);
    if (!relogioAcertado) Serial.println("[hora] acertada pelo GPS");
    relogioAcertado = true;
    ultimoAcertoGpsMs = millis();
  }
}

const char* fonteHora() {
  if (!relogioAcertado || !logica::relogioPlausivel(time(nullptr))) return "none";
  if (wifiConectado && ntpOk && !passou(ultimoNtpMs, 2 * 3600000UL)) return "ntp";
  if (gps.date.isValid() && gps.time.isValid() && gps.time.age() < 3000) return "gps";
  return "estimated";
}

// ================================================================ energia (AXP2101 / AXP192)
#if USE_PMU
void iniciarEnergia() {
  pmu = new XPowersAXP2101(Wire);
  if (!pmu->init()) {
    delete pmu;
    pmu = new XPowersAXP192(Wire);
    if (!pmu->init()) {
      delete pmu;
      pmu = nullptr;
      Serial.println("[energia] AXP não encontrado: GPS pode ficar desligado");
      return;
    }
  }
  if (pmu->getChipModel() == XPOWERS_AXP2101) {
    pmu->setPowerChannelVoltage(XPOWERS_ALDO2, 3300); pmu->enablePowerOutput(XPOWERS_ALDO2);  // LoRa
    pmu->setPowerChannelVoltage(XPOWERS_ALDO3, 3300); pmu->enablePowerOutput(XPOWERS_ALDO3);  // GPS
  } else {
    pmu->setPowerChannelVoltage(XPOWERS_LDO2, 3300);  pmu->enablePowerOutput(XPOWERS_LDO2);   // LoRa
    pmu->setPowerChannelVoltage(XPOWERS_LDO3, 3300);  pmu->enablePowerOutput(XPOWERS_LDO3);   // GPS
    pmu->setPowerChannelVoltage(XPOWERS_DCDC1, 3300); pmu->enablePowerOutput(XPOWERS_DCDC1);  // OLED
  }
  pmu->enableBattDetection();
  pmu->enableBattVoltageMeasure();
  Serial.println("[energia] AXP iniciado, GPS ligado");
}
#endif

void lerBateria() {
#if USE_PMU
  if (!pmu) return;
  if (pmu->isBatteryConnect()) {
    bateriaPct = pmu->getBatteryPercent();
    carregando = pmu->isCharging();
  } else {
    bateriaPct = -1;
    carregando = false;
  }
#endif
}

// ================================================================ sensores
float lerTensaoPo() {
  uint32_t somaMv = 0;
  for (int i = 0; i < AMOSTRAS_PH; i++) {
    somaMv += analogReadMilliVolts(PIN_PH);   // já corrigido pela calibração do ESP32
    delay(2);
  }
  return (somaMv / (float)AMOSTRAS_PH) / 1000.0f * FATOR_DIVISOR;
}

// ================================================================ alertas do dispositivo
void enfileirarAlerta(const char* codigo, const char* severidade, const char* mensagem,
                      const char* sensor, long numero) {
  if (nAlertas == MAX_ALERTAS) {   // sem conexão há muito tempo: fica com os mais novos
    memmove(alertasPendentes[0], alertasPendentes[1], (MAX_ALERTAS - 1) * TAM_ALERTA);
    nAlertas--;
  }
  payload::alerta(DEVICE_ID, codigo, severidade, time(nullptr), relogioAcertado, mensagem,
                  sensor, numero, alertasPendentes[nAlertas], TAM_ALERTA);
  nAlertas++;
  Serial.printf("[alerta] %s: %s\n", codigo, mensagem);
}

void verificarFalhas(uint8_t flags) {
  static const uint8_t bits[5] = {logica::BIT_DHT, logica::BIT_PH_SEM_SINAL, logica::BIT_PH_FAIXA,
                                  logica::BIT_DS_AUSENTE, logica::BIT_DS_INVALIDO};
  static const char* sensores[5] = {"dht22", "ph", "ph", "ds18b20", "ds18b20"};
  static const char* textos[5] = {
      "DHT22 sem resposta há 3 leituras seguidas",
      "pH sem sinal há 3 leituras seguidas (Po < 0,1 V)",
      "pH fora de 0–14 há 3 leituras seguidas (calibre o módulo)",
      "DS18B20 não encontrada há 3 leituras seguidas",
      "DS18B20 com leitura inválida há 3 leituras seguidas"};
  for (int i = 0; i < 5; i++) {
    if (i == 3 && !USE_DS18B20) continue;   // não ligada de propósito: não é falha
    if (flags & bits[i]) {
      if (sequenciaFalha[i] < 255) sequenciaFalha[i]++;
      if (sequenciaFalha[i] == 3) enfileirarAlerta("SENSOR_FAULT", "warning", textos[i], sensores[i], flags);
    } else {
      sequenciaFalha[i] = 0;
    }
  }
}

void verificarFila() {
  uint32_t descartes = fila.pegarDescartesNovos();
  if (descartes) enfileirarAlerta("QUEUE_DROPPED", "critical", "Fila cheia: leituras mais antigas descartadas",
                                  nullptr, (long)descartes);
  const uint32_t cap = fila.capacidade(), p = fila.pendentes();
  if (!filaAltaAvisada && p * 10 > cap * 8) {
    filaAltaAvisada = true;
    enfileirarAlerta("QUEUE_HIGH", "warning", "Fila offline acima de 80%", nullptr, (long)p);
  } else if (filaAltaAvisada && p * 10 < cap * 7) {
    filaAltaAvisada = false;
  }
}

// ================================================================ medição
void medir() {
  const float phV = lerTensaoPo();
  const float ph = logica::phDeTensao(phV, PH7_VOLTS, PH4_VOLTS);
  const float arT = dht.readTemperature();
  const float arU = dht.readHumidity();
  bool dsPresente = false;
  float leite = NAN;
#if USE_DS18B20
  if (ds.getDeviceCount() == 0) ds.begin();   // tenta achar de novo (fio recolocado)
  dsPresente = ds.getDeviceCount() > 0;
  if (dsPresente) {
    ds.requestTemperatures();
    leite = ds.getTempCByIndex(0);
  }
#endif

  Medicao m;
  m.deviceId = DEVICE_ID;
  m.valores = logica::avaliar(phV, ph, arT, arU, USE_DS18B20, dsPresente, leite);
  sequencia++;
  logica::formatarMsgId(m.msgId, sizeof(m.msgId), DEVICE_ID, contagemBoot, sequencia);
  m.fonteHora = fonteHora();
  m.hora = time(nullptr);
  m.gpsFix = gps.location.isValid() && gps.location.age() < 5000;
  m.lat = gps.location.lat();
  m.lon = gps.location.lng();
  m.satelites = gps.satellites.isValid() ? (int)gps.satellites.value() : 0;

  // 1) grava no flash ANTES de tentar enviar
  char linha[Fila::MAX_LINHA];
  size_t n = payload::telemetria(m, FW_VERSION, linha, sizeof(linha));
  if (n == 0 || n >= sizeof(linha) - 1) {
    Serial.println("[fila] ERRO: JSON maior que o espaço da linha");
  } else if (!fila.empurrar(linha)) {
    Serial.println("[fila] ERRO ao gravar no flash");
  } else {
    strncpy(msgIdRecente, m.msgId, sizeof(msgIdRecente) - 1);
    recenteMs = millis();
  }

  leiturasTotal++;
  ultima = m;
  temUltima = true;
  historico[histPos] = m.valores.ph;
  histPos = (histPos + 1) % HIST_N;

  const time_t agora = relogioAcertado ? time(nullptr) : 0;
  const uint8_t f = m.valores.flags;
  if (!(f & (logica::BIT_PH_SEM_SINAL | logica::BIT_PH_FAIXA))) okPh = agora;
  if (!(f & logica::BIT_DHT)) okDht = agora;
  if (!(f & (logica::BIT_DS_AUSENTE | logica::BIT_DS_INVALIDO))) okDs = agora;
  verificarFalhas(f);
  verificarFila();

  leituraParaMostrar = true;
}

// Linha no Monitor Serial (depois da tentativa de envio, para a fila mostrar o valor real)
void imprimirLeitura() {
  const Medicao& m = ultima;
  Serial.printf("[leitura %lu] pH %s (Po %.3f V) | ar %.1f C %.0f %% | flags %u | GPS %s %d sat | hora %s | fila %lu | %s\n",
                (unsigned long)sequencia, isnan(m.valores.ph) ? "--" : String(m.valores.ph, 2).c_str(),
                m.valores.phVolts, m.valores.arTemp, m.valores.arUmid, m.valores.flags, m.gpsFix ? "fix" : "sem fix",
                m.satelites, m.fonteHora, (unsigned long)fila.pendentes(),
                brokerConectado ? brokerConectado : "OFFLINE (guardando na placa)");
}

// ================================================================ Wi-Fi
void cuidarWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConectado) {
      wifiConectado = true;
      wifiTentando = false;
      tentativasNaRodada = 0;
      Serial.printf("[wifi] conectado em \"%s\" — página da placa: http://%s\n", WiFi.SSID().c_str(),
                    WiFi.localIP().toString().c_str());
      configTime(0, 0, NTP_SERVIDOR_1, NTP_SERVIDOR_2);
      brokerAtual = 0;
      esperaMqtt = 1000;
      proximaTentativaMqtt = millis();
    }
    return;
  }
  if (wifiConectado) {
    wifiConectado = false;
    wifiTentando = false;
    Serial.println("[wifi] caiu — as leituras continuam sendo guardadas na placa");
  }
  if (N_REDES == 0) return;
  if (wifiTentando && !passou(inicioTentativaMs, WIFI_TEMPO_TENTATIVA_MS)) return;
  if (wifiTentando) {
    wifiTentando = false;
    WiFi.disconnect();
    tentativasNaRodada++;
  }
  if (tentativasNaRodada >= N_REDES) {   // tentou todas: dá um tempo (o Wi-Fi da placa fica estável)
    if (!emPausaWifi) {
      emPausaWifi = true;
      inicioPausaMs = millis();
      Serial.printf("[wifi] nenhuma rede respondeu; tento de novo em %lu s\n",
                    (unsigned long)(WIFI_PAUSA_ENTRE_RODADAS / 1000));
    }
    if (!passou(inicioPausaMs, WIFI_PAUSA_ENTRE_RODADAS)) return;
    emPausaWifi = false;
    tentativasNaRodada = 0;
  }
  redeAtual = (redeAtual + 1) % N_REDES;
  Serial.printf("[wifi] tentando \"%s\"...\n", REDES_WIFI[redeAtual].ssid);
  WiFi.begin(REDES_WIFI[redeAtual].ssid, REDES_WIFI[redeAtual].senha);
  wifiTentando = true;
  inicioTentativaMs = millis();
}

// ================================================================ MQTT
void montarTopicos() {
  snprintf(topTelemetria, sizeof(topTelemetria), "smartmilk/device/%s/telemetry", DEVICE_ID);
  snprintf(topStatus, sizeof(topStatus), "smartmilk/device/%s/status", DEVICE_ID);
  snprintf(topAlertas, sizeof(topAlertas), "smartmilk/device/%s/alerts", DEVICE_ID);
  snprintf(statusOffline, sizeof(statusOffline),
           "{\"v\":1,\"device_id\":\"%s\",\"state\":\"offline\",\"reason\":\"lwt\"}", DEVICE_ID);
}

void fecharConexaoMqtt() {
  // Fecha o socket SEM mandar DISCONNECT: assim o broker publica o Last Will ("offline").
  redeSimples.stop();
  redeTls.stop();
  brokerConectado = nullptr;
}

void estadoSensor(JsonObject o, bool ausente, bool falha, time_t okEm) {
  o["state"] = ausente ? "absent" : (falha ? "fault" : "ok");
  if (okEm) {
    char iso[24];
    logica::isoUtc(okEm, iso, sizeof(iso));
    o["last_ok_at"] = iso;
  } else {
    o["last_ok_at"] = nullptr;
  }
}

void publicarStatus() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["state"] = "online";
  char iso[24];
  if (relogioAcertado) {
    logica::isoUtc(time(nullptr), iso, sizeof(iso));
    doc["at"] = iso;
  } else {
    doc["at"] = nullptr;
  }
  doc["fw"] = FW_VERSION;
  doc["uptime_s"] = millis() / 1000;
  doc["ip"] = WiFi.localIP().toString();
  doc["wifi_ssid"] = WiFi.SSID();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["broker"] = brokerConectado;
  doc["time_source"] = fonteHora();
  doc["gps_fix"] = gps.location.isValid() && gps.location.age() < 5000;
  JsonObject q = doc["queue"].to<JsonObject>();
  q["pending"] = fila.pendentes();
  q["capacity"] = fila.capacidade();
  q["dropped"] = fila.descartadas();
  const uint8_t f = temUltima ? ultima.valores.flags : 0;
  JsonObject s = doc["sensors"].to<JsonObject>();
  estadoSensor(s["ph"].to<JsonObject>(), false, f & (logica::BIT_PH_SEM_SINAL | logica::BIT_PH_FAIXA), okPh);
  estadoSensor(s["dht22"].to<JsonObject>(), false, f & logica::BIT_DHT, okDht);
  estadoSensor(s["ds18b20"].to<JsonObject>(), !USE_DS18B20 || (f & logica::BIT_DS_AUSENTE),
               f & logica::BIT_DS_INVALIDO, okDs);
  if (bateriaPct >= 0) {
    JsonObject b = doc["battery"].to<JsonObject>();
    b["percent"] = bateriaPct;
    b["charging"] = carregando;
  }
  doc["readings_total"] = leiturasTotal;
  char buf[900];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(topStatus, buf, (int)n, true, 1);
  ultimoStatusMs = millis();
}

void cuidarMqtt() {
  if (!wifiConectado || N_BROKERS == 0) {
    if (brokerConectado) fecharConexaoMqtt();
    return;
  }
  if (mqtt.connected()) {
    mqtt.loop();
    return;
  }
  if (brokerConectado) {
    Serial.printf("[mqtt] perdeu a conexão com %s — guardando na placa\n", brokerConectado);
    fecharConexaoMqtt();
    proximaTentativaMqtt = millis();
  }
  if ((int32_t)(millis() - proximaTentativaMqtt) < 0) return;

  const BrokerMqtt& b = BROKERS[brokerAtual];
  Serial.printf("[mqtt] conectando em %s (%s:%u%s)...\n", b.nome, b.host, b.porta, b.tls ? ", TLS" : "");
  if (b.tls) mqtt.begin(b.host, b.porta, redeTls);
  else mqtt.begin(b.host, b.porta, redeSimples);
  mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
  mqtt.setCleanSession(true);   // quem guarda as pendentes é a fila em flash
  mqtt.setTimeout(MQTT_TIMEOUT_MS);
  mqtt.setWill(topStatus, statusOffline, true, 1);
  const char* usuario = b.usuario ? b.usuario : DEVICE_ID;
  const char* senha = b.senha ? b.senha : MQTT_SENHA;

  if (mqtt.connect(DEVICE_ID, usuario, senha)) {
    brokerConectado = b.nome;
    esperaMqtt = 1000;
    Serial.printf("[mqtt] conectado em %s — %lu leitura(s) na fila para enviar\n", b.nome,
                  (unsigned long)fila.pendentes());
    publicarStatus();
    return;
  }

  const int rc = (int)mqtt.returnCode();
  Serial.printf("[mqtt] falhou em %s (erro %d, retorno %d)%s\n", b.nome, (int)mqtt.lastError(), rc,
                rc == 4 || rc == 5 ? " — usuário/senha recusados: confira MQTT_SENHA e o .env" : "");
  fecharConexaoMqtt();
  brokerAtual = (brokerAtual + 1) % N_BROKERS;
  if (brokerAtual == 0) esperaMqtt = esperaMqtt * 2 > MQTT_ESPERA_MAX_MS ? MQTT_ESPERA_MAX_MS : esperaMqtt * 2;
  proximaTentativaMqtt = millis() + (brokerAtual == 0 ? esperaMqtt : 200);
}

void enviarFila() {
  if (!brokerConectado || !mqtt.connected()) return;
  static char linha[Fila::MAX_LINHA];
  for (int i = 0; i < ENVIOS_POR_VOLTA; i++) {
    const int r = fila.espiar(linha, sizeof(linha));
    if (r == 0) return;
    if (r < 0) {
      Serial.println("[fila] erro de leitura no flash");
      return;
    }
    const bool recente = msgIdRecente[0] && strstr(linha, msgIdRecente) && !passou(recenteMs, 2 * INTERVALO_MS);
    if (!recente) logica::marcarBuffered(linha);   // ficou guardada antes de sair
    if (!mqtt.publish(topTelemetria, linha, (int)strlen(linha), false, 1)) {
      // Sem PUBACK em MQTT_TIMEOUT_MS: a conexão está ruim. A leitura fica na fila e reconecta.
      Serial.printf("[mqtt] envio sem confirmação (erro %d) — a leitura continua na fila\n", (int)mqtt.lastError());
      fecharConexaoMqtt();
      proximaTentativaMqtt = millis() + 1000;
      return;
    }
    fila.consumir();
    enviadas++;
    if (!recente && (fila.pendentes() % 50 == 0))
      Serial.printf("[fila] reenviando o que ficou guardado... faltam %lu\n", (unsigned long)fila.pendentes());
  }
}

void enviarAlertas() {
  while (nAlertas > 0 && brokerConectado && mqtt.connected()) {
    if (!mqtt.publish(topAlertas, alertasPendentes[0], (int)strlen(alertasPendentes[0]), false, 1)) {
      fecharConexaoMqtt();
      proximaTentativaMqtt = millis() + 1000;
      return;
    }
    memmove(alertasPendentes[0], alertasPendentes[1], (MAX_ALERTAS - 1) * TAM_ALERTA);
    nAlertas--;
  }
}

// ================================================================ página da placa
void paginaInicial() { web.send_P(200, "text/html; charset=utf-8", PAGINA_HTML); }

void apiAgora() {
  JsonDocument d;
  d["id"] = DEVICE_ID;
  d["fw"] = FW_VERSION;
  if (temUltima) {
    payload::numeroOuNulo(d["ph"], ultima.valores.ph, 2);
    payload::numeroOuNulo(d["ph_v"], ultima.valores.phVolts, 3);
    payload::numeroOuNulo(d["ar"], ultima.valores.arTemp, 1);
    payload::numeroOuNulo(d["umid"], ultima.valores.arUmid, 1);
    payload::numeroOuNulo(d["leite"], ultima.valores.leiteTemp, 2);
    d["flags"] = ultima.valores.flags;
  } else {
    d["ph"] = nullptr; d["ph_v"] = nullptr; d["ar"] = nullptr; d["umid"] = nullptr; d["leite"] = nullptr;
    d["flags"] = 0;
  }
  char iso[24];
  if (relogioAcertado) {
    logica::isoUtc(time(nullptr), iso, sizeof(iso));
    d["hora"] = iso;
  } else {
    d["hora"] = nullptr;
  }
  d["fonte"] = fonteHora();
  JsonObject g = d["gps"].to<JsonObject>();
  g["fix"] = gps.location.isValid() && gps.location.age() < 5000;
  g["sats"] = gps.satellites.isValid() ? (int)gps.satellites.value() : 0;
  g["lat"] = gps.location.lat();
  g["lon"] = gps.location.lng();
  if (bateriaPct >= 0) {
    d["bat"]["pct"] = bateriaPct;
    d["bat"]["carregando"] = carregando;
  } else {
    d["bat"] = nullptr;
  }
  JsonObject w = d["wifi"].to<JsonObject>();
  w["ok"] = wifiConectado;
  w["rede"] = wifiConectado ? WiFi.SSID() : String("");
  w["ip"] = wifiConectado ? WiFi.localIP().toString() : String("");
  w["rssi"] = wifiConectado ? WiFi.RSSI() : 0;
  JsonObject mq = d["mqtt"].to<JsonObject>();
  mq["ok"] = brokerConectado != nullptr;
  mq["broker"] = brokerConectado ? brokerConectado : "";
  JsonObject fl = d["fila"].to<JsonObject>();
  fl["pendentes"] = fila.pendentes();
  fl["capacidade"] = fila.capacidade();
  fl["descartadas"] = fila.descartadas();
  JsonArray h = d["hist"].to<JsonArray>();
  for (int i = 0; i < HIST_N; i++) {
    const float v = historico[(histPos + i) % HIST_N];
    if (isnan(v)) h.add(nullptr);
    else h.add(payload::arred(v, 2));
  }
  String out;
  serializeJson(d, out);
  web.send(200, "application/json", out);
}

// ================================================================ display
#if USE_OLED
void desenharOled() {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(2);
  oled.setCursor(0, 0);
  if (temUltima && !isnan(ultima.valores.ph)) oled.printf("pH %.2f", ultima.valores.ph);
  else oled.print("pH --");
  oled.setTextSize(1);
  oled.setCursor(0, 20);
  if (temUltima) {
    oled.printf("Po %.3fV ", ultima.valores.phVolts);
    if (!isnan(ultima.valores.arTemp)) oled.printf("%.1fC %.0f%%", ultima.valores.arTemp, ultima.valores.arUmid);
  }
  oled.setCursor(0, 31);
  oled.printf("GPS %s %d sat", gps.location.isValid() ? "ok" : "--",
              gps.satellites.isValid() ? (int)gps.satellites.value() : 0);
  oled.setCursor(0, 42);
  if (wifiConectado) oled.printf("%s", WiFi.localIP().toString().c_str());
  else oled.print("WiFi: --  (192.168.4.1)");
  oled.setCursor(0, 53);
  if (brokerConectado) oled.printf("Painel OK  fila %lu", (unsigned long)fila.pendentes());
  else oled.printf("OFFLINE  fila %lu", (unsigned long)fila.pendentes());
  oled.display();
}
#endif

// ================================================================ setup / loop
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== LogLacto · T-Beam · firmware " FW_VERSION " ===");

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
#if USE_PMU
  iniciarEnergia();
#endif
#if USE_OLED
  oledOk = oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (oledOk) {
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    oled.setTextSize(2);
    oled.setCursor(0, 0);
    oled.print("LogLacto");
    oled.setTextSize(1);
    oled.setCursor(0, 24);
    oled.print("iniciando...");
    oled.display();
  }
#endif

  analogSetPinAttenuation(PIN_PH, ADC_11db);
  pinMode(PIN_DHT_POWER, OUTPUT);
  digitalWrite(PIN_DHT_POWER, HIGH);   // o DHT22 precisa de 2 s antes da 1ª leitura
  Serial1.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
#if USE_DS18B20
  ds.begin();
  ds.setResolution(10);   // ~190 ms por leitura (0,25 °C)
#endif
  for (int i = 0; i < HIST_N; i++) historico[i] = NAN;

  // Contador de inicializações (parte do msg_id; nunca se repete)
  prefs.begin("loglacto", false);
  contagemBoot = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", contagemBoot);
  prefs.end();
  Serial.printf("[placa] %s, inicialização nº %lu\n", DEVICE_ID, (unsigned long)contagemBoot);

  // Fila em flash
  if (!LittleFS.begin(true)) Serial.println("[fila] ERRO: não foi possível montar o LittleFS");
  fila.configurar(&armazenamento, FILA_LINHAS_SEGMENTO, FILA_SEGMENTOS, FILA_MIN_LIVRE);
  fila.iniciar();
  Serial.printf("[fila] %lu leitura(s) guardada(s) de antes; capacidade %lu\n",
                (unsigned long)fila.pendentes(), (unsigned long)fila.capacidade());

  montarTopicos();
  redeTls.setCACert(CA_CERT);
  sntp_set_time_sync_notification_cb(aoSincronizarNtp);

  WiFi.persistent(false);
  WiFi.setAutoReconnect(false);   // quem decide a rede é cuidarWifi()
#if USE_AP
  WiFi.mode(WIFI_AP_STA);
  char nomeAp[40];
  snprintf(nomeAp, sizeof(nomeAp), "LogLacto-%s", DEVICE_ID);
  if (WiFi.softAP(nomeAp, AP_SENHA))
    Serial.printf("[wifi] rede da placa \"%s\" — abra http://%s\n", nomeAp, WiFi.softAPIP().toString().c_str());
  else
    Serial.println("[wifi] ERRO ao criar a rede da placa (AP_SENHA precisa de 8+ caracteres)");
#else
  WiFi.mode(WIFI_STA);
#endif

  web.on("/", paginaInicial);
  web.on("/api/agora", apiAgora);
  web.begin();

  dht.begin();
  ultimaLeituraMs = millis();   // 1ª leitura em 5 s (tempo do DHT22 estabilizar)
}

void loop() {
  while (Serial1.available()) gps.encode(Serial1.read());
  cuidarRelogio();
  cuidarWifi();
  cuidarMqtt();
  web.handleClient();

  if (passou(ultimaLeituraMs, INTERVALO_MS)) {
    ultimaLeituraMs = millis();
    medir();
  }
  enviarFila();
  enviarAlertas();
  if (leituraParaMostrar) {
    leituraParaMostrar = false;
    imprimirLeitura();
  }

  if (brokerConectado && passou(ultimoStatusMs, STATUS_INTERVALO_MS)) publicarStatus();
  if (passou(ultimaBateriaMs, 10000)) {
    ultimaBateriaMs = millis();
    lerBateria();
  }
#if USE_OLED
  if (oledOk && passou(ultimoOledMs, 1000)) {
    ultimoOledMs = millis();
    desenharOled();
  }
#endif
  if (!horaAvisada && !relogioAcertado && millis() > 600000UL) {
    horaAvisada = true;
    enfileirarAlerta("TIME_UNSYNCED", "warning", "10 min ligada sem NTP e sem GPS", nullptr, 0);
  }
  delay(2);
}
