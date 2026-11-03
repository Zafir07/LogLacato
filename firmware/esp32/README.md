# Firmware da T-Beam V1.2 (Etapa 5)

Uma placa só faz tudo no caminhão:

1. **Lê os sensores** a cada 5 s: pH (HW-828 no VP / GPIO 36), ar (DHT22 no GPIO 13,
   alimentado pelo GPIO 14) e leite (DS18B20 no GPIO 25, a integrar).
2. **Confere** as faixas físicas e marca falhas em `sensor_flags`.
3. **Carimba a hora** da medição (NTP → GPS → estimada) e gera o `msg_id` único.
4. **Grava na fila** em LittleFS **antes** de enviar.
5. **Publica no MQTT** com QoS 1 e só apaga da fila depois da confirmação do broker.
6. **Publica o estado** (retido) e usa Last Will para sinalizar desconexão.

Ponto de partida: o código do relatório (Quadro 1), que já faz o passo 1 e os
diagnósticos do passo 2.

Credenciais de Wi-Fi e MQTT ficam em `secrets.h`, que está no `.gitignore`
(será fornecido um `secrets.example.h`).

Especificações: [leitura dos sensores](../../docs/architecture/leitura-sensores.md) e
[protocolo MQTT](../../docs/architecture/protocolo-mqtt.md).
