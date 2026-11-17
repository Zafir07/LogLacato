// Lógica pura do firmware: não usa nenhuma biblioteca da placa, então compila e é
// testada no PC (firmware/esp32/testes). Conversão do pH, faixas físicas, bits de
// sensor_flags, msg_id e datas UTC.
#pragma once
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

namespace logica {

// ---------------------------------------------------------------- bits de sensor_flags
enum : uint8_t {
  BIT_DHT          = 1,   // DHT22 não respondeu / checksum / fora da faixa física
  BIT_PH_SEM_SINAL = 2,   // Po < 0,1 V (fio solto, divisor, sonda)
  BIT_PH_FAIXA     = 4,   // pH calculado fora de 0–14 (calibração)
  BIT_DS_AUSENTE   = 8,   // DS18B20 não encontrada (ou não ligada)
  BIT_DS_INVALIDO  = 16,  // DS18B20 respondeu -127 °C / 85 °C / fora da faixa
};

// pH pela reta de dois pontos (tampões pH 7 e pH 4): pH = 7 + (V7 - V) / m
inline float phDeTensao(float volts, float v7, float v4) {
  const float m = (v4 - v7) / 3.0f;   // volts por unidade de pH
  if (isnan(volts) || fabsf(m) < 1e-6f) return NAN;
  return 7.0f + (v7 - volts) / m;
}

// Resultado de uma leitura já conferida: NAN = "não medi" (vira null no JSON).
struct Avaliacao {
  float ph, phVolts, arTemp, arUmid, leiteTemp;
  uint8_t flags;
};

// Confere as faixas físicas (leitura-sensores.md, Seções 3 e 4).
// Só descarta o fisicamente impossível; limites de qualidade são do backend.
inline Avaliacao avaliar(float phVolts, float ph, float arTemp, float arUmid,
                         bool dsUsada, bool dsPresente, float leiteTemp) {
  Avaliacao a = {NAN, NAN, NAN, NAN, NAN, 0};

  // pH: a tensão bruta vai sempre que for fisicamente possível (permite recalibrar depois)
  if (!isnan(phVolts) && phVolts >= 0.0f && phVolts <= 5.5f) a.phVolts = phVolts;
  if (isnan(phVolts) || phVolts < 0.1f) {
    a.flags |= BIT_PH_SEM_SINAL;
  } else if (isnan(ph) || ph < 0.0f || ph > 14.0f) {
    a.flags |= BIT_PH_FAIXA;
  } else {
    a.ph = ph;
  }

  // Ar (DHT22): NaN = sem resposta
  if (isnan(arTemp) || isnan(arUmid)) {
    a.flags |= BIT_DHT;
  } else {
    if (arTemp >= -40.0f && arTemp <= 80.0f) a.arTemp = arTemp; else a.flags |= BIT_DHT;
    if (arUmid >= 0.0f && arUmid <= 100.0f)  a.arUmid = arUmid; else a.flags |= BIT_DHT;
  }

  // Leite (DS18B20)
  if (!dsUsada || !dsPresente) {
    a.flags |= BIT_DS_AUSENTE;
  } else if (isnan(leiteTemp) || leiteTemp <= -127.0f || leiteTemp == 85.0f ||
             leiteTemp < -55.0f || leiteTemp > 125.0f) {
    a.flags |= BIT_DS_INVALIDO;
  } else {
    a.leiteTemp = leiteTemp;
  }
  return a;
}

// ---------------------------------------------------------------- msg_id (ADR-07)
// <device_id>-<boot 5 dígitos>-<seq 9 dígitos>: nunca se repete, nem depois de desligar.
inline void formatarMsgId(char* out, size_t n, const char* deviceId, uint32_t boot, uint32_t seq) {
  snprintf(out, n, "%s-%05lu-%09lu", deviceId, (unsigned long)(boot % 100000UL),
           (unsigned long)(seq % 1000000000UL));
}

// ---------------------------------------------------------------- datas em UTC
// Dias desde 1970-01-01 (algoritmo days_from_civil de H. Hinnant): não depende do fuso.
inline int64_t diasDesdeEpoca(int y, unsigned m, unsigned d) {
  y -= m <= 2;
  const int era = (y >= 0 ? y : y - 399) / 400;
  const unsigned yoe = (unsigned)(y - era * 400);
  const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

inline int64_t epocaUtc(int ano, int mes, int dia, int hora, int min, int seg) {
  return diasDesdeEpoca(ano, (unsigned)mes, (unsigned)dia) * 86400LL + hora * 3600LL + min * 60LL + seg;
}

// "2026-11-03T18:30:05Z"
inline void isoUtc(time_t t, char* out, size_t n) {
  struct tm tmv;
  gmtime_r(&t, &tmv);
  strftime(out, n, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

// Relógio plausível? (o ESP32 começa em 1970 até sincronizar)
inline bool relogioPlausivel(time_t t) { return t > 1735689600; }  // depois de 2025-01-01

// ---------------------------------------------------------------- fila
// Marca uma leitura guardada como "buffered": true na hora do reenvio.
// Troca no próprio texto, sem refazer o JSON. Devolve true se trocou.
inline bool marcarBuffered(char* linha) {
  static const char de[] = "\"buffered\":false";
  static const char para[] = "\"buffered\":true";
  char* p = strstr(linha, de);
  if (!p) return false;
  memcpy(p, para, sizeof(para) - 1);
  memmove(p + sizeof(para) - 1, p + sizeof(de) - 1, strlen(p + sizeof(de) - 1) + 1);
  return true;
}

// Linha da fila com cara de JSON completo? (uma escrita cortada por falta de energia não tem)
inline bool linhaCompleta(const char* linha) {
  size_t n = strlen(linha);
  return n >= 2 && linha[0] == '{' && linha[n - 1] == '}';
}

}  // namespace logica
