#!/bin/sh
# Serviço "backup" — o papel dos backups automáticos do RDS.
#
# A cada BACKUP_INTERVAL_HOURS gera um dump do PostgreSQL em /backups e apaga os
# dumps com mais de BACKUP_KEEP_DAYS dias. O volume /backups deve ser copiado para
# fora do servidor (HD externo, nuvem da universidade) — backup no mesmo disco não
# protege contra perda do disco.
#
# Variáveis: PGHOST, PGUSER, PGPASSWORD, PGDATABASE (padrão do PostgreSQL),
#            BACKUP_INTERVAL_HOURS (24), BACKUP_KEEP_DAYS (14), BACKUP_DIR (/backups)
#            BACKUP_ONCE=1 faz um único backup e sai (útil para testar).
set -eu

: "${PGHOST:?defina PGHOST}"
: "${PGUSER:?defina PGUSER}"
: "${PGDATABASE:?defina PGDATABASE}"
INTERVAL_H="${BACKUP_INTERVAL_HOURS:-24}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
DIR="${BACKUP_DIR:-/backups}"

mkdir -p "$DIR"

run_backup() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  tmp="$DIR/.${PGDATABASE}-$stamp.dump.partial"
  final="$DIR/${PGDATABASE}-$stamp.dump"
  if pg_dump --format=custom --no-owner --file="$tmp"; then
    mv "$tmp" "$final"
    echo "backup: $(date -u +%FT%TZ) gravado $final ($(du -h "$final" | cut -f1))"
  else
    rm -f "$tmp"
    echo "backup: $(date -u +%FT%TZ) FALHOU" >&2
    return 1
  fi
  find "$DIR" -maxdepth 1 -name "${PGDATABASE}-*.dump" -mtime +"$KEEP_DAYS" -print -delete \
    | sed 's/^/backup: removido (antigo) /'
}

until pg_isready -q; do
  echo "backup: aguardando o PostgreSQL…"
  sleep 3
done

if [ "${BACKUP_ONCE:-0}" = "1" ]; then
  run_backup
  exit $?
fi

while true; do
  run_backup || true
  sleep "$((INTERVAL_H * 3600))"
done
