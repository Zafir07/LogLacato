// Fila offline em flash (ADR-07): cada leitura é gravada ANTES de ser enviada e só sai
// da fila depois do PUBACK do broker. Sobrevive a desligar a placa.
//
// Formato: arquivos-segmento com uma leitura (JSON) por linha, /f00000001.jl, /f00000002.jl…
// e um arquivo /fcursor com "<primeiro segmento> <posição já enviada>".
// Quando a fila enche, o segmento mais antigo é descartado (e contado em "descartadas").
//
// Não depende da placa: o acesso ao flash passa pela interface Armazenamento
// (LittleFS na T-Beam, arquivos comuns nos testes do PC).
#pragma once
#include <stddef.h>
#include <stdint.h>

class Armazenamento {
 public:
  virtual ~Armazenamento() {}
  virtual bool existe(const char* caminho) = 0;
  virtual bool apagar(const char* caminho) = 0;
  virtual long tamanho(const char* caminho) = 0;                               // -1 = não existe
  virtual long ler(const char* caminho, long pos, char* buf, size_t n) = 0;     // bytes lidos, -1 = erro
  virtual bool acrescentar(const char* caminho, const char* dados, size_t n) = 0;
  virtual bool gravar(const char* caminho, const char* dados, size_t n) = 0;    // sobrescreve
  virtual long livre() = 0;                                                     // bytes livres, -1 = não sabe
};

class Fila {
 public:
  static const size_t MAX_LINHA = 768;

  void configurar(Armazenamento* a, uint16_t linhasPorSegmento, uint16_t maxSegmentos, long minLivre);
  bool iniciar();                              // recupera a fila depois de reiniciar
  bool empurrar(const char* linha);            // grava no fim
  int espiar(char* buf, size_t cap);           // 1 = próxima linha em buf, 0 = vazia, -1 = erro
  void consumir();                             // a linha espiada foi entregue
  void salvarCursor();

  uint32_t pendentes() const { return pendentes_; }
  uint32_t capacidade() const { return (uint32_t)linhasSeg_ * maxSeg_; }
  uint32_t descartadas() const { return descartadas_; }
  uint32_t corrompidas() const { return corrompidas_; }
  uint32_t pegarDescartesNovos() { uint32_t n = descartesNovos_; descartesNovos_ = 0; return n; }

 private:
  void caminho(uint32_t seg, char* out) const;
  uint32_t contarLinhas(uint32_t seg, long desde);
  void descartarMaisAntigo();
  void avancarSegmento();
  void pularAteFimDeLinha(long tamanhoSeg);

  Armazenamento* arm_ = nullptr;
  uint16_t linhasSeg_ = 100, maxSeg_ = 30;
  long minLivre_ = 0;
  uint32_t primeiro_ = 1, ultimo_ = 1, linhasUltimo_ = 0;
  long posicao_ = 0;          // bytes já enviados do primeiro segmento
  long consumoEspiado_ = 0;   // tamanho da linha espiada (com o \n)
  uint32_t pendentes_ = 0, descartadas_ = 0, descartesNovos_ = 0, corrompidas_ = 0;
  uint8_t consumosSemSalvar_ = 0;
};
