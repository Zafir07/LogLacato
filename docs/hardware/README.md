# Hardware

O projeto usa **apenas a LilyGO T-Beam V1.2** (ESP32 + Wi-Fi + LoRa + GPS): ela lê os
sensores e publica no MQTT ([ADR-01](../architecture/decisoes.md#adr-01)).
As ligações do pH e do DHT22 são as do protótipo do relatório (Tabela 4) e **não mudam**.
Falta integrar a DS18B20. O passo a passo de montagem com esquemas vem na **Etapa 5**.

## 1. Componentes

| Componente | Situação | Papel |
|------------|----------|-------|
| LilyGO T-Beam V1.2 | ✅ montada no protótipo | Lê os sensores, relógio (NTP/GPS), fila offline, Wi-Fi/MQTT |
| Módulo de pH HW-828 + sonda BNC | ✅ montado | pH do leite |
| DHT22 (AM2302) | ✅ montado | Temperatura e umidade do **ar** |
| DS18B20 (sonda à prova d'água) | ⏳ o grupo tem da primeira versão, **não ligada** | Temperatura do **leite** |
| 2 resistores de 560 Ω (R1, R2) | ✅ montados | Divisor do Po (÷2) |
| 4 resistores de 560 Ω em série | ✅ montados | Pull-up do DHT22 (~2,2 kΩ) |
| Resistor de ~4,7 kΩ | ⚠️ conferir | Pull-up da DS18B20 |
| Soluções-tampão pH 4 e pH 7 | ✅ | Calibração |

## 2. Ligações

| Origem | Destino na T-Beam | Situação |
|--------|-------------------|----------|
| HW-828 V+ / G | 5V / GND | ✅ como no protótipo |
| HW-828 Po → R1 → ponto médio → R2 → GND | ponto médio no **VP (GPIO 36)** | ✅ como no protótipo |
| DHT22 pino 1 (VCC) | **GPIO 14** (alimentação por software) | ✅ como no protótipo |
| DHT22 pino 2 (DATA) | **GPIO 13**, com pull-up de 4 × 560 Ω até o VCC | ✅ como no protótipo |
| DHT22 pino 4 (GND) | GND | ✅ como no protótipo |
| DS18B20 vermelho (VCC) | **3V3** | ⏳ proposta |
| DS18B20 preto (GND) | GND | ⏳ proposta |
| DS18B20 amarelo (DATA) | **GPIO 25**, com pull-up de ~4,7 kΩ até o 3V3 | ⏳ proposta |

```
             3V3 ───────────┬──────────────── DS18B20 vermelho
                            │
                         [4,7 kΩ]
                            │
   T-Beam GPIO 25 ──────────┴──────────────── DS18B20 amarelo (DATA)

             GND ──────────────────────────── DS18B20 preto
```

**Pinos que não podem ser usados:** GPIO 33 e 32 (rádio LoRa), 34 e 12 (GPS),
21 e 22 (gerenciador de energia, barramento I²C).

A DS18B20 é alimentada pelo 3V3, e não pelo 5V, para que a linha de dados nunca passe
de 3,3 V no pino do ESP32.

## 3. Alimentação

- **Bancada:** cabo USB da T-Beam no computador ou num carregador.
- **Caminhão (futuro):** fonte 12 V → regulador 5 V, ou bateria 18650 no suporte da
  própria T-Beam. A dimensionar na Etapa 5.

## 4. O que ainda depende do hardware físico

1. Ligar a DS18B20 no GPIO 25 e conferir o resistor de pull-up.
2. Confirmar que o GPIO 25 está livre e acessível no conector da placa de vocês.
3. Conferir a calibração do pH com os tampões pH 4 e pH 7.
4. Testar o Wi-Fi da T-Beam com o broker rodando no computador (porta 1883 liberada no
   firewall do Windows).
5. Medir o consumo para dimensionar a alimentação no caminhão.
