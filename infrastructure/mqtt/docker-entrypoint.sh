#!/bin/sh
# Gera o arquivo de senhas e a ACL do Mosquitto a partir do .env e inicia o broker.
#
# Variáveis:
#   MQTT_BACKEND_USER, MQTT_BACKEND_PASSWORD   usuário da API
#   MQTT_QUALITY_PASSWORD                      senha do serviço svc-quality
#   MQTT_NOTIFIER_PASSWORD                     senha do serviço svc-notifier
#   MQTT_DEVICE_CREDENTIALS                    "esp32-001:senha1,sim-001:senha2"
#                                              (a senha não pode conter vírgula)
#   MQTT_BRIDGE_HOST, MQTT_BRIDGE_PORT         (opcional) broker na nuvem de onde buscar a
#   MQTT_BRIDGE_USER, MQTT_BRIDGE_PASSWORD     telemetria das T-Beams que estão longe
#   MQTT_BRIDGE_CAFILE                         CA para o TLS da ponte (padrão: a do sistema)
set -eu

CONFIG_DIR="${MOSQUITTO_CONFIG_DIR:-/mosquitto/config}"
DATA_DIR="${MOSQUITTO_DATA_DIR:-/mosquitto/data}"
PASSWD="$DATA_DIR/passwd"
ACL="$DATA_DIR/acl"

: "${MQTT_BACKEND_USER:?defina MQTT_BACKEND_USER no .env}"
: "${MQTT_BACKEND_PASSWORD:?defina MQTT_BACKEND_PASSWORD no .env}"
: "${MQTT_QUALITY_PASSWORD:?defina MQTT_QUALITY_PASSWORD no .env}"
: "${MQTT_NOTIFIER_PASSWORD:?defina MQTT_NOTIFIER_PASSWORD no .env}"

mkdir -p "$DATA_DIR"
rm -f "$PASSWD"
touch "$PASSWD"
chmod 0700 "$PASSWD"

mosquitto_passwd -b "$PASSWD" "$MQTT_BACKEND_USER" "$MQTT_BACKEND_PASSWORD"
mosquitto_passwd -b "$PASSWD" svc-quality "$MQTT_QUALITY_PASSWORD"
mosquitto_passwd -b "$PASSWD" svc-notifier "$MQTT_NOTIFIER_PASSWORD"

count=0
OLD_IFS=$IFS
IFS=','
for pair in ${MQTT_DEVICE_CREDENTIALS:-}; do
  IFS=$OLD_IFS
  user=$(echo "${pair%%:*}" | tr -d ' ')
  pass=${pair#*:}
  if [ -z "$user" ] || [ "$user" = "$pair" ]; then
    echo "MQTT_DEVICE_CREDENTIALS: item inválido ignorado (use dispositivo:senha)" >&2
    continue
  fi
  # Um dispositivo nunca pode usar o nome de um serviço (herdaria as permissões dele).
  case "$user" in
    svc-*|"$MQTT_BACKEND_USER")
      echo "MQTT_DEVICE_CREDENTIALS: '$user' é nome reservado de serviço; ignorado" >&2
      continue ;;
  esac
  mosquitto_passwd -b "$PASSWD" "$user" "$pass"
  count=$((count + 1))
done
IFS=$OLD_IFS

sed "s/__BACKEND_USER__/$MQTT_BACKEND_USER/" "$CONFIG_DIR/acl.template" > "$ACL"
chmod 0700 "$ACL"

# ---------- Ponte com o broker na nuvem (opcional) ----------
# Só TRAZ mensagens dos dispositivos (direção "in"). Nada do servidor sobe para a nuvem.
CONF_D="$DATA_DIR/conf.d"
mkdir -p "$CONF_D"
rm -f "$CONF_D/ponte-nuvem.conf"
if [ -n "${MQTT_BRIDGE_HOST:-}" ]; then
  : "${MQTT_BRIDGE_USER:?defina MQTT_BRIDGE_USER no .env (usuário da ponte no broker da nuvem)}"
  : "${MQTT_BRIDGE_PASSWORD:?defina MQTT_BRIDGE_PASSWORD no .env}"
  CAFILE="${MQTT_BRIDGE_CAFILE:-/etc/ssl/certs/ca-certificates.crt}"
  if [ ! -f "$CAFILE" ]; then
    echo "Ponte MQTT: certificado $CAFILE não encontrado (ajuste MQTT_BRIDGE_CAFILE)" >&2
    exit 1
  fi
  {
    echo "connection loglacto-nuvem"
    echo "address ${MQTT_BRIDGE_HOST}:${MQTT_BRIDGE_PORT:-8883}"
    echo "bridge_protocol_version mqttv311"
    echo "remote_clientid ${MQTT_BRIDGE_CLIENT_ID:-loglacto-ponte}"
    echo "remote_username ${MQTT_BRIDGE_USER}"
    echo "remote_password ${MQTT_BRIDGE_PASSWORD}"
    echo "bridge_cafile ${CAFILE}"
    echo "bridge_insecure false"
    echo "try_private false"
    echo "notifications false"
    echo "cleansession false"
    echo "restart_timeout 5 60"
    echo "topic smartmilk/device/+/telemetry in 1"
    echo "topic smartmilk/device/+/status in 1"
    echo "topic smartmilk/device/+/alerts in 1"
  } > "$CONF_D/ponte-nuvem.conf"
  chmod 0600 "$CONF_D/ponte-nuvem.conf"
  echo "Mosquitto: ponte com ${MQTT_BRIDGE_HOST}:${MQTT_BRIDGE_PORT:-8883} ativada (só entrada de telemetria, status e alertas)."
fi

if id mosquitto >/dev/null 2>&1; then
  chown -R mosquitto:mosquitto "$DATA_DIR"
fi

echo "Mosquitto: api '$MQTT_BACKEND_USER', svc-quality, svc-notifier + $count dispositivo(s) cadastrados."
exec mosquitto -c "$CONFIG_DIR/mosquitto.conf"
