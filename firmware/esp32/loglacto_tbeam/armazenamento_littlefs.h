// A fila (fila.h) gravando no LittleFS da T-Beam.
#pragma once
#include <LittleFS.h>

#include "fila.h"

class ArmazenamentoLittleFS : public Armazenamento {
 public:
  bool existe(const char* c) override { return LittleFS.exists(c); }
  bool apagar(const char* c) override { return LittleFS.remove(c); }

  long tamanho(const char* c) override {
    if (!LittleFS.exists(c)) return -1;
    File f = LittleFS.open(c, "r");
    if (!f) return -1;
    long t = (long)f.size();
    f.close();
    return t;
  }

  // Sem exists() antes: a fila só lê arquivos que ela sabe que existem (uma abertura a menos).
  long ler(const char* c, long pos, char* buf, size_t n) override {
    File f = LittleFS.open(c, "r");
    if (!f) return -1;
    if (pos >= (long)f.size()) { f.close(); return 0; }
    if (!f.seek((uint32_t)pos)) { f.close(); return -1; }
    long lidos = (long)f.read((uint8_t*)buf, n);
    f.close();
    return lidos;
  }

  bool acrescentar(const char* c, const char* d, size_t n) override {
    File f = LittleFS.open(c, "a");
    if (!f) return false;
    size_t w = f.write((const uint8_t*)d, n);
    f.close();
    return w == n;
  }

  bool gravar(const char* c, const char* d, size_t n) override {
    File f = LittleFS.open(c, "w");
    if (!f) return false;
    size_t w = f.write((const uint8_t*)d, n);
    f.close();
    return w == n;
  }

  long livre() override { return (long)LittleFS.totalBytes() - (long)LittleFS.usedBytes(); }
};
