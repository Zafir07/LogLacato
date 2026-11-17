// Montagem dos JSON publicados no MQTT (docs/architecture/protocolo-mqtt.md, versão 1).
// Usa só ArduinoJson e tipos comuns: compila e é testado no PC contra o esquema do backend.
#pragma once
#include <ArduinoJson.h>
#include <math.h>

#include "logica.h"

struct Medicao {
  const char* deviceId;
  char msgId[48];
  time_t hora;              // UTC; vale se fonteHora != "none"
  const char* fonteHora;    // "ntp" | "gps" | "estimated" | "none"
  logica::Avaliacao valores;
  bool gpsFix;
  double lat, lon;
  int satelites;
};

namespace payload {

inline double arred(double v, int casas) {
  const double f = pow(10.0, casas);
  return round(v * f) / f;
}

// T&& e não T: o campo do ArduinoJson 7 não pode ser copiado (o compilador do ESP32 reclama)
template <typename T>
inline void numeroOuNulo(T&& campo, float v, int casas) {
  if (isnan(v)) campo.set(nullptr);
  else campo.set(arred(v, casas));
}

// "telemetry": uma leitura. buffered sai false; vira true no reenvio (logica::marcarBuffered).
inline size_t telemetria(const Medicao& m, const char* fw, char* out, size_t cap) {
  JsonDocument doc;
  doc["v"] = 1;
  doc["msg_id"] = m.msgId;
  doc["device_id"] = m.deviceId;
  const bool temHora = strcmp(m.fonteHora, "none") != 0;
  if (temHora) {
    char iso[24];
    logica::isoUtc(m.hora, iso, sizeof(iso));
    doc["measured_at"] = iso;
  } else {
    doc["measured_at"] = nullptr;
  }
  doc["time_source"] = m.fonteHora;
  JsonObject r = doc["readings"].to<JsonObject>();
  numeroOuNulo(r["ph"], m.valores.ph, 2);
  numeroOuNulo(r["ph_voltage"], m.valores.phVolts, 3);
  numeroOuNulo(r["milk_temperature"], m.valores.leiteTemp, 2);
  numeroOuNulo(r["air_temperature"], m.valores.arTemp, 1);
  numeroOuNulo(r["air_humidity"], m.valores.arUmid, 1);
  doc["sensor_flags"] = m.valores.flags;
  if (m.gpsFix) {
    JsonObject g = doc["gps"].to<JsonObject>();
    g["lat"] = arred(m.lat, 6);
    g["lon"] = arred(m.lon, 6);
    g["fix"] = true;
    g["sats"] = m.satelites;
  } else {
    doc["gps"] = nullptr;
  }
  doc["buffered"] = false;
  doc["simulated"] = false;
  doc["fw"] = fw;
  return serializeJson(doc, out, cap);
}

// "alerts": falha vista pelo próprio dispositivo (SENSOR_FAULT, QUEUE_HIGH, QUEUE_DROPPED, TIME_UNSYNCED)
inline size_t alerta(const char* deviceId, const char* codigo, const char* severidade, time_t hora,
                     bool temHora, const char* mensagem, const char* sensor, long numero,
                     char* out, size_t cap) {
  JsonDocument doc;
  doc["v"] = 1;
  doc["device_id"] = deviceId;
  doc["code"] = codigo;
  doc["severity"] = severidade;
  if (temHora) {
    char iso[24];
    logica::isoUtc(hora, iso, sizeof(iso));
    doc["at"] = iso;
  } else {
    doc["at"] = nullptr;
  }
  doc["message"] = mensagem;
  JsonObject d = doc["details"].to<JsonObject>();
  if (sensor) d["sensor"] = sensor;
  d["count"] = numero;
  return serializeJson(doc, out, cap);
}

}  // namespace payload
