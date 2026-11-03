#!/bin/sh
# Gera o arquivo de senhas e a ACL do Mosquitto a partir do .env e inicia o broker.
#
# Variáveis:
#   MQTT_BACKEND_USER, MQTT_BACKEND_PASSWORD   usuário da API
#   MQTT_QUALITY_PASSWORD                      senha do serviço svc-quality
#   MQTT_NOTIFIER_PASSWORD                     senha do serviço svc-notifier
#   MQTT_DEVICE_CREDENTIALS                    "esp32-001:senha1,sim-001:senha2"
#                                              (a senha não pode conter vírgula)
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

if id mosquitto >/dev/null 2>&1; then
  chown mosquitto:mosquitto "$DATA_DIR" "$PASSWD" "$ACL"
fi

echo "Mosquitto: api '$MQTT_BACKEND_USER', svc-quality, svc-notifier + $count dispositivo(s) cadastrados."
exec mosquitto -c "$CONFIG_DIR/mosquitto.conf"
