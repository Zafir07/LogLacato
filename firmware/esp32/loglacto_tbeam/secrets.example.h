// Copie este arquivo para secrets.h e preencha. O secrets.h NÃO vai para o Git.
//
//   Windows (PowerShell, dentro desta pasta):  Copy-Item secrets.example.h secrets.h
#pragma once
#include <stdint.h>

// ---------------------------------------------------------------- identidade
// O id é o usuário MQTT e aparece no tópico smartmilk/device/<id>/...
// Tem que estar no .env do servidor:  MQTT_DEVICE_CREDENTIALS=esp32-001:<senha>,...
#define DEVICE_ID      "esp32-001"
#define MQTT_SENHA     "troque-senha-esp32"   // a MESMA senha do .env

// ---------------------------------------------------------------- redes Wi-Fi
// A placa tenta na ordem e fica na primeira que responder.
// Ponha a rede onde o servidor está e o roteador do celular (para usar o 4G).
// Para testar só o modo offline, deixe uma única linha { nullptr, nullptr }.
struct RedeWifi { const char* ssid; const char* senha; };
static const RedeWifi REDES_WIFI[] = {
  { "Wi-Fi-da-casa-ou-fazenda", "senha-do-wifi" },
  { "Celular-do-motorista",     "senha-do-roteador" },
};

// ---------------------------------------------------------------- brokers MQTT
// Tenta na ordem. O primeiro que conectar recebe as leituras.
//   local: o computador que roda o docker compose (IP dele na rede; veja com ipconfig)
//   nuvem: opcional, para o caminhão longe do servidor (ponte do Mosquitto, ver o guia)
// usuario/senha = nullptr usa DEVICE_ID / MQTT_SENHA.
struct BrokerMqtt { const char* nome; const char* host; uint16_t porta; bool tls; const char* usuario; const char* senha; };
static const BrokerMqtt BROKERS[] = {
  { "local", "192.168.0.10", 1883, false, nullptr, nullptr },
  // { "nuvem", "xxxxxxxx.s1.eu.hivemq.cloud", 8883, true, "esp32-001", "senha-no-hivemq" },
};

// ---------------------------------------------------------------- Wi-Fi da própria placa
// Rede "LogLacto-esp32-001" que a placa cria para você ver as leituras sem rede nenhuma
// (abra http://192.168.4.1 no celular). Mínimo 8 caracteres.
#define AP_SENHA       "loglacto123"

// ---------------------------------------------------------------- TLS (só para brokers com tls = true)
// Certificado raiz ISRG Root X1 (Let's Encrypt). Serve para o HiveMQ Cloud e para
// servidores com certificado Let's Encrypt. Se o seu broker usa a CA própria do
// docs/installation (TLS no broker), cole aqui o ca.crt dela.
static const char CA_CERT[] = R"PEM(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)PEM";
