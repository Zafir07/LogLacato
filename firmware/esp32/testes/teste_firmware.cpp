// Testes no PC da lógica do firmware (sem a placa):
//   - conversão tensão -> pH, faixas físicas e bits de sensor_flags
//   - msg_id e datas UTC
//   - fila offline: ordem, reinício da placa, linha cortada, fila cheia
//   - JSON de telemetria (gravado em telemetria_exemplo.json para o teste do backend)
//
// Rodar (Linux/macOS/WSL ou MinGW no Windows):  ./rodar_testes.sh
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include <string>
#include <vector>

#include "../loglacto_tbeam/fila.h"
#include "../loglacto_tbeam/logica.h"
#include "../loglacto_tbeam/payload.h"

static int falhas = 0, total = 0;
#define CONFERE(cond, msg)                                               \
  do {                                                                   \
    total++;                                                             \
    if (!(cond)) { falhas++; printf("  FALHOU: %s (linha %d)\n", msg, __LINE__); } \
  } while (0)
#define PERTO(a, b, tol) (fabs((double)(a) - (double)(b)) <= (tol))

// ---------------------------------------------------------------- armazenamento em disco
class ArmazenamentoDisco : public Armazenamento {
 public:
  explicit ArmazenamentoDisco(std::string dir) : dir_(dir) { mkdir(dir.c_str(), 0755); }
  std::string c(const char* p) { return dir_ + p; }
  bool existe(const char* p) override { struct stat st; return stat(c(p).c_str(), &st) == 0; }
  bool apagar(const char* p) override { return remove(c(p).c_str()) == 0; }
  long tamanho(const char* p) override { struct stat st; return stat(c(p).c_str(), &st) == 0 ? (long)st.st_size : -1; }
  long ler(const char* p, long pos, char* buf, size_t n) override {
    FILE* f = fopen(c(p).c_str(), "rb");
    if (!f) return -1;
    fseek(f, pos, SEEK_SET);
    long r = (long)fread(buf, 1, n, f);
    fclose(f);
    return r;
  }
  bool acrescentar(const char* p, const char* d, size_t n) override {
    FILE* f = fopen(c(p).c_str(), "ab");
    if (!f) return false;
    bool ok = fwrite(d, 1, n, f) == n;
    fclose(f);
    return ok;
  }
  bool gravar(const char* p, const char* d, size_t n) override {
    FILE* f = fopen(c(p).c_str(), "wb");
    if (!f) return false;
    bool ok = fwrite(d, 1, n, f) == n;
    fclose(f);
    return ok;
  }
  long livre() override { return livre_; }
  long livre_ = -1;

 private:
  std::string dir_;
};

static std::string linhaN(int i) {
  char b[64];
  snprintf(b, sizeof(b), "{\"n\":%d,\"buffered\":false}", i);
  return b;
}
static int numeroDe(const char* linha) { int n = -1; sscanf(linha, "{\"n\":%d", &n); return n; }

static std::string novaPasta(const char* nome) {
  std::string d = std::string("/tmp/loglacto_teste_") + nome;
  std::string cmd = "rm -rf " + d;
  int r = system(cmd.c_str());
  (void)r;
  return d;
}

// ---------------------------------------------------------------- testes
static void testePh() {
  printf("pH e faixas\n");
  CONFERE(PERTO(logica::phDeTensao(2.50f, 2.50f, 3.04f), 7.0, 1e-4), "Po = V7 -> pH 7");
  CONFERE(PERTO(logica::phDeTensao(3.04f, 2.50f, 3.04f), 4.0, 1e-4), "Po = V4 -> pH 4");
  CONFERE(PERTO(logica::phDeTensao(2.59f, 2.50f, 3.04f), 6.5, 1e-3), "exemplo do relatório: 2,59 V -> 6,5");
  CONFERE(PERTO(logica::phDeTensao(3.723f, 2.50f, 3.04f), 0.205, 1e-2), "caso do resistor solto (relatório 7.7)");
  CONFERE(isnan(logica::phDeTensao(2.5f, 2.5f, 2.5f)), "calibração inválida -> NaN");

  logica::Avaliacao a = logica::avaliar(2.563f, 6.65f, 21.4f, 65.2f, false, false, NAN);
  CONFERE(a.flags == 8, "protótipo sem DS18B20 -> sensor_flags = 8 (leitura-sensores.md)");
  CONFERE(PERTO(a.ph, 6.65, 1e-6) && PERTO(a.phVolts, 2.563, 1e-6), "pH e Po válidos");
  CONFERE(isnan(a.leiteTemp), "leite sem sensor -> null");

  a = logica::avaliar(0.012f, 20.9f, NAN, NAN, false, false, NAN);
  CONFERE(a.flags == (1 | 2 | 8), "sem sinal no Po + DHT22 sem resposta");
  CONFERE(isnan(a.ph) && PERTO(a.phVolts, 0.012, 1e-6), "sem sinal: pH null, tensão bruta vai");

  a = logica::avaliar(3.723f, 0.2f, 25, 50, true, true, 4.5f);
  CONFERE(a.flags == 0 && PERTO(a.ph, 0.2, 1e-6), "pH 0,2 ainda é físico (0–14)");
  a = logica::avaliar(4.5f, -2.0f, 25, 50, true, true, 4.5f);
  CONFERE(a.flags == 4 && isnan(a.ph), "pH -2 -> bit 2 e null");
  a = logica::avaliar(2.5f, 7.0f, 25, 150, true, true, -127.0f);
  CONFERE(a.flags == (1 | 16) && isnan(a.arUmid) && PERTO(a.arTemp, 25, 1e-6), "umidade 150% e DS -127");
  a = logica::avaliar(2.5f, 7.0f, 25, 50, true, true, 85.0f);
  CONFERE(a.flags == 16, "DS18B20 85 °C (valor de inicialização) -> bit 4");
  a = logica::avaliar(2.5f, 7.0f, 25, 50, true, false, NAN);
  CONFERE(a.flags == 8, "DS18B20 ligada mas não encontrada -> bit 3");
}

static void testeIdsEDatas() {
  printf("msg_id e datas\n");
  char id[48];
  logica::formatarMsgId(id, sizeof(id), "esp32-001", 17, 1234);
  CONFERE(strcmp(id, "esp32-001-00017-000001234") == 0, "formato do msg_id (protocolo-mqtt.md)");
  CONFERE(logica::epocaUtc(1970, 1, 1, 0, 0, 0) == 0, "época");
  CONFERE(logica::epocaUtc(2026, 11, 3, 18, 30, 5) == 1793730605LL, "2026-11-03T18:30:05Z");
  CONFERE(logica::epocaUtc(2024, 2, 29, 12, 0, 0) == 1709208000LL, "ano bissexto");
  char iso[24];
  logica::isoUtc((time_t)1793730605, iso, sizeof(iso));
  CONFERE(strcmp(iso, "2026-11-03T18:30:05Z") == 0, "ISO 8601 em UTC");
  CONFERE(!logica::relogioPlausivel(5) && logica::relogioPlausivel(1793730605), "relógio plausível");

  char l[64] = "{\"a\":1,\"buffered\":false,\"b\":2}";
  CONFERE(logica::marcarBuffered(l) && strcmp(l, "{\"a\":1,\"buffered\":true,\"b\":2}") == 0, "marca buffered");
  CONFERE(!logica::marcarBuffered(l), "não marca duas vezes");
  CONFERE(logica::linhaCompleta("{\"x\":1}") && !logica::linhaCompleta("{\"x\":1") && !logica::linhaCompleta(""),
          "detecta linha cortada");
}

static void testeFilaBasica() {
  printf("fila: ordem e reinício\n");
  ArmazenamentoDisco disco(novaPasta("basica"));
  Fila f;
  f.configurar(&disco, 100, 30, 0);
  CONFERE(f.iniciar() && f.pendentes() == 0, "começa vazia");
  char buf[Fila::MAX_LINHA];
  CONFERE(f.espiar(buf, sizeof(buf)) == 0, "espiar vazia = 0");
  for (int i = 1; i <= 250; i++) f.empurrar(linhaN(i).c_str());
  CONFERE(f.pendentes() == 250, "250 pendentes");
  CONFERE(disco.existe("/f00000003.jl") && !disco.existe("/f00000004.jl"), "3 segmentos de 100");

  for (int i = 1; i <= 123; i++) {
    CONFERE(f.espiar(buf, sizeof(buf)) == 1, "espiar ok");
    if (numeroDe(buf) != i) { CONFERE(false, "ordem FIFO"); break; }
    f.consumir();
  }
  CONFERE(f.pendentes() == 127, "127 depois de entregar 123");
  CONFERE(!disco.existe("/f00000001.jl"), "segmento entregue foi apagado");

  // "desliga a placa": nova fila no mesmo flash
  Fila g;
  g.configurar(&disco, 100, 30, 0);
  g.iniciar();
  CONFERE(g.pendentes() >= 127 && g.pendentes() <= 127 + 10, "depois de reiniciar: nada perdido (no máx. 10 repetidas)");
  CONFERE(g.espiar(buf, sizeof(buf)) == 1, "espiar depois de reiniciar");
  int primeiro = numeroDe(buf);
  CONFERE(primeiro >= 114 && primeiro <= 124, "recomeça perto de onde parou (cursor a cada 10)");
  int ultimo = 0, n = 0;
  while (g.espiar(buf, sizeof(buf)) == 1) { ultimo = numeroDe(buf); g.consumir(); n++; }
  CONFERE(ultimo == 250 && g.pendentes() == 0, "entrega até a última");
  CONFERE(!disco.existe("/f00000003.jl"), "tudo apagado depois de entregar");
  g.empurrar(linhaN(251).c_str());
  CONFERE(g.pendentes() == 1 && disco.existe("/f00000004.jl"), "segue gravando num segmento novo");
  Fila h;
  h.configurar(&disco, 100, 30, 0);
  h.iniciar();
  CONFERE(h.pendentes() == 1 && h.espiar(buf, sizeof(buf)) == 1 && numeroDe(buf) == 251, "reinício com 1 pendente");
}

static void testeFilaCortada() {
  printf("fila: energia cortada no meio da escrita\n");
  ArmazenamentoDisco disco(novaPasta("cortada"));
  Fila f;
  f.configurar(&disco, 100, 30, 0);
  f.iniciar();
  for (int i = 1; i <= 5; i++) f.empurrar(linhaN(i).c_str());
  disco.acrescentar("/f00000001.jl", "{\"n\":6,\"buf", 11);   // escrita interrompida
  Fila g;
  g.configurar(&disco, 100, 30, 0);
  g.iniciar();
  g.empurrar(linhaN(7).c_str());
  std::vector<int> vistos;
  char buf[Fila::MAX_LINHA];
  while (g.espiar(buf, sizeof(buf)) == 1) { vistos.push_back(numeroDe(buf)); g.consumir(); }
  CONFERE(vistos.size() == 6 && vistos[4] == 5 && vistos[5] == 7, "linha cortada é pulada, a próxima chega inteira");
  CONFERE(g.corrompidas() == 1, "conta 1 corrompida");
}

static void testeFilaCheia() {
  printf("fila: cheia descarta a mais antiga\n");
  ArmazenamentoDisco disco(novaPasta("cheia"));
  Fila f;
  f.configurar(&disco, 10, 3, 0);   // capacidade 30
  f.iniciar();
  for (int i = 1; i <= 45; i++) f.empurrar(linhaN(i).c_str());
  CONFERE(f.capacidade() == 30, "capacidade 30");
  CONFERE(f.pendentes() <= 30 && f.pendentes() >= 21, "nunca passa da capacidade");
  CONFERE(f.descartadas() == 45 - f.pendentes(), "descartadas + pendentes = gravadas");
  CONFERE(f.pegarDescartesNovos() == f.descartadas() && f.pegarDescartesNovos() == 0, "aviso de descarte sai uma vez");
  char buf[Fila::MAX_LINHA];
  f.espiar(buf, sizeof(buf));
  CONFERE(numeroDe(buf) == 45 - (int)f.pendentes() + 1, "a mais antiga que sobrou vem primeiro");

  printf("fila: flash quase cheio\n");
  ArmazenamentoDisco d2(novaPasta("flash"));
  Fila g;
  g.configurar(&d2, 10, 30, 1000);
  g.iniciar();
  for (int i = 1; i <= 35; i++) g.empurrar(linhaN(i).c_str());
  d2.livre_ = 500;   // abaixo do mínimo
  g.empurrar(linhaN(36).c_str());
  CONFERE(g.descartadas() > 0 && g.pendentes() == 36 - g.descartadas(), "libera espaço descartando a mais antiga");
}

static void testePayload() {
  printf("JSON de telemetria\n");
  Medicao m;
  m.deviceId = "esp32-001";
  logica::formatarMsgId(m.msgId, sizeof(m.msgId), "esp32-001", 17, 1234);
  m.fonteHora = "gps";
  m.hora = (time_t)1793730605;
  m.valores = logica::avaliar(2.5634f, 6.6512f, 21.43f, 65.21f, false, false, NAN);
  m.gpsFix = true;
  m.lat = -27.876104;
  m.lon = -54.459523;
  m.satelites = 8;
  char out[Fila::MAX_LINHA];
  size_t n = payload::telemetria(m, "0.2.0", out, sizeof(out));
  printf("  %s\n  (%zu bytes)\n", out, n);
  CONFERE(n > 0 && n < 450, "cabe com folga na linha da fila");
  CONFERE(strstr(out, "\"ph\":6.65") && strstr(out, "\"ph_voltage\":2.563") && strstr(out, "\"milk_temperature\":null"),
          "arredondamento e null");
  CONFERE(strstr(out, "\"measured_at\":\"2026-11-03T18:30:05Z\"") && strstr(out, "\"sensor_flags\":8"), "hora e flags");
  CONFERE(strstr(out, "\"buffered\":false") != nullptr, "sai com buffered false");
  FILE* f = fopen("telemetria_exemplo.json", "w");
  fputs(out, f);
  fputc('\n', f);
  logica::marcarBuffered(out);
  fputs(out, f);
  fputc('\n', f);

  m.fonteHora = "none";
  m.gpsFix = false;
  payload::telemetria(m, "0.2.0", out, sizeof(out));
  CONFERE(strstr(out, "\"measured_at\":null") && strstr(out, "\"gps\":null"), "sem hora e sem GPS -> null");
  fputs(out, f);
  fputc('\n', f);
  fclose(f);

  char al[400];
  payload::alerta("esp32-001", "SENSOR_FAULT", "warning", (time_t)1793730605, true,
                  "pH sem sinal há 3 leituras seguidas (Po < 0,1 V)", "ph", 2, al, sizeof(al));
  f = fopen("alerta_exemplo.json", "w");
  fputs(al, f);
  fputc('\n', f);
  fclose(f);
  CONFERE(strstr(al, "\"code\":\"SENSOR_FAULT\"") != nullptr, "alerta");
}

int main() {
  testePh();
  testeIdsEDatas();
  testeFilaBasica();
  testeFilaCortada();
  testeFilaCheia();
  testePayload();
  printf("\n%d de %d verificações passaram\n", total - falhas, total);
  return falhas ? 1 : 0;
}
