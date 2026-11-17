#include "fila.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "logica.h"

static const char* CAMINHO_CURSOR = "/fcursor";
// O cursor vai para o flash a cada N entregas. Se a placa desligar no meio, no máximo
// N leituras são reenviadas, e o backend descarta as repetidas pelo msg_id.
static const uint8_t SALVAR_A_CADA = 10;

void Fila::configurar(Armazenamento* a, uint16_t linhasPorSegmento, uint16_t maxSegmentos, long minLivre) {
  arm_ = a;
  linhasSeg_ = linhasPorSegmento < 1 ? 1 : linhasPorSegmento;
  maxSeg_ = maxSegmentos < 2 ? 2 : maxSegmentos;
  minLivre_ = minLivre;
}

void Fila::caminho(uint32_t seg, char* out) const {
  snprintf(out, 20, "/f%08lu.jl", (unsigned long)seg);
}

void Fila::salvarCursor() {
  char txt[32];
  int n = snprintf(txt, sizeof(txt), "%lu %ld\n", (unsigned long)primeiro_, posicao_);
  arm_->gravar(CAMINHO_CURSOR, txt, (size_t)n);
  consumosSemSalvar_ = 0;
}

uint32_t Fila::contarLinhas(uint32_t seg, long desde) {
  // Bloco grande: cada leitura abre o arquivo no flash, então quanto menos leituras melhor
  // (com a fila cheia, a contagem no boot lê ~1 MB).
  static char buf[2048];
  char cam[20];
  caminho(seg, cam);
  uint32_t linhas = 0;
  long pos = desde;
  for (;;) {
    long n = arm_->ler(cam, pos, buf, sizeof(buf));
    if (n <= 0) break;
    for (long i = 0; i < n; i++) if (buf[i] == '\n') linhas++;
    pos += n;
  }
  return linhas;
}

bool Fila::iniciar() {
  if (!arm_) return false;
  primeiro_ = 1;
  posicao_ = 0;
  char txt[32];
  long n = arm_->existe(CAMINHO_CURSOR) ? arm_->ler(CAMINHO_CURSOR, 0, txt, sizeof(txt) - 1) : -1;
  if (n > 0) {
    txt[n] = 0;
    unsigned long p = 0;
    long pos = 0;
    if (sscanf(txt, "%lu %ld", &p, &pos) == 2 && p > 0 && pos >= 0) {
      primeiro_ = (uint32_t)p;
      posicao_ = pos;
    }
  }

  char cam[20];
  // Segmento já entregue que ficou para trás (desligou entre salvar o cursor e apagar)
  if (primeiro_ > 1) {
    caminho(primeiro_ - 1, cam);
    if (arm_->existe(cam)) arm_->apagar(cam);
  }

  caminho(primeiro_, cam);
  if (!arm_->existe(cam)) {   // fila vazia
    ultimo_ = primeiro_;
    linhasUltimo_ = 0;
    posicao_ = 0;
    pendentes_ = 0;
    return true;
  }

  ultimo_ = primeiro_;
  for (;;) {
    caminho(ultimo_ + 1, cam);
    if (!arm_->existe(cam)) break;
    ultimo_++;
  }

  // Última escrita cortada pela falta de energia: fecha a linha para a próxima não grudar nela.
  caminho(ultimo_, cam);
  long t = arm_->tamanho(cam);
  if (t > 0) {
    char c = 0;
    if (arm_->ler(cam, t - 1, &c, 1) == 1 && c != '\n') arm_->acrescentar(cam, "\n", 1);
  }

  caminho(primeiro_, cam);
  if (posicao_ > arm_->tamanho(cam)) posicao_ = 0;   // cursor estranho: reenvia (sem duplicar no banco)

  pendentes_ = contarLinhas(primeiro_, posicao_);
  for (uint32_t s = primeiro_ + 1; s <= ultimo_; s++) pendentes_ += contarLinhas(s, 0);
  linhasUltimo_ = contarLinhas(ultimo_, 0);
  return true;
}

void Fila::descartarMaisAntigo() {
  if (primeiro_ >= ultimo_) return;   // nunca descarta o segmento em que está gravando
  uint32_t perdidas = contarLinhas(primeiro_, posicao_);
  char cam[20];
  caminho(primeiro_, cam);
  primeiro_++;
  posicao_ = 0;
  salvarCursor();          // primeiro o cursor, depois apaga (iniciar() limpa sobras)
  arm_->apagar(cam);
  pendentes_ = pendentes_ >= perdidas ? pendentes_ - perdidas : 0;
  descartadas_ += perdidas;
  descartesNovos_ += perdidas;
}

bool Fila::empurrar(const char* linha) {
  if (!arm_ || !linha) return false;
  size_t n = strlen(linha);
  if (n == 0 || n >= MAX_LINHA || memchr(linha, '\n', n)) return false;

  if (linhasUltimo_ >= linhasSeg_) {
    ultimo_++;
    linhasUltimo_ = 0;
  }
  while ((ultimo_ - primeiro_ + 1) > maxSeg_) descartarMaisAntigo();
  for (int i = 0; i < (int)maxSeg_; i++) {
    long livre = arm_->livre();
    if (livre < 0 || livre >= minLivre_ || primeiro_ >= ultimo_) break;
    descartarMaisAntigo();
  }

  char buf[MAX_LINHA + 1];
  memcpy(buf, linha, n);
  buf[n] = '\n';
  char cam[20];
  caminho(ultimo_, cam);
  if (!arm_->acrescentar(cam, buf, n + 1)) return false;
  linhasUltimo_++;
  pendentes_++;
  return true;
}

void Fila::avancarSegmento() {
  char cam[20];
  caminho(primeiro_, cam);
  primeiro_++;
  posicao_ = 0;
  salvarCursor();
  arm_->apagar(cam);
}

void Fila::pularAteFimDeLinha(long tamanhoSeg) {
  char cam[20], buf[128];
  caminho(primeiro_, cam);
  while (posicao_ < tamanhoSeg) {
    long n = arm_->ler(cam, posicao_, buf, sizeof(buf));
    if (n <= 0) { posicao_ = tamanhoSeg; return; }
    const char* nl = (const char*)memchr(buf, '\n', (size_t)n);
    if (nl) { posicao_ += (nl - buf) + 1; return; }
    posicao_ += n;
  }
}

int Fila::espiar(char* buf, size_t cap) {
  if (!arm_ || cap < 4) return -1;
  char cam[20];
  for (;;) {
    caminho(primeiro_, cam);
    long t = arm_->tamanho(cam);
    if (t < 0 || posicao_ >= t) {
      if (primeiro_ < ultimo_) { avancarSegmento(); continue; }
      pendentes_ = 0;
      return 0;
    }
    long n = arm_->ler(cam, posicao_, buf, cap - 1);
    if (n <= 0) return -1;
    buf[n] = 0;
    char* nl = (char*)memchr(buf, '\n', (size_t)n);
    if (nl) {
      *nl = 0;
      consumoEspiado_ = (nl - buf) + 1;
      if (logica::linhaCompleta(buf)) return 1;
      // linha estragada (escrita cortada): pula e segue
      posicao_ += consumoEspiado_;
      consumoEspiado_ = 0;
      corrompidas_++;
      if (pendentes_) pendentes_--;
      continue;
    }
    // Sem fim de linha no pedaço lido: linha longa demais ou final sem \n. Pula.
    pularAteFimDeLinha(t);
    corrompidas_++;
    if (pendentes_) pendentes_--;
  }
}

void Fila::consumir() {
  if (consumoEspiado_ <= 0) return;
  posicao_ += consumoEspiado_;
  consumoEspiado_ = 0;
  if (pendentes_) pendentes_--;

  char cam[20];
  caminho(primeiro_, cam);
  long t = arm_->tamanho(cam);
  if (t >= 0 && posicao_ < t) {
    if (++consumosSemSalvar_ >= SALVAR_A_CADA) salvarCursor();
    return;
  }
  if (primeiro_ < ultimo_) {
    avancarSegmento();
    return;
  }
  // Entregou tudo: recomeça num segmento novo (os números só crescem)
  primeiro_ = ultimo_ = ultimo_ + 1;
  linhasUltimo_ = 0;
  posicao_ = 0;
  pendentes_ = 0;
  salvarCursor();
  arm_->apagar(cam);
}
