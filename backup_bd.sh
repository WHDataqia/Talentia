#!/usr/bin/env bash
set -euo pipefail

# Backup operativo para Talentia (PostgreSQL)
# - Crea dump en formato custom (.dump)
# - Exporta roles/globales (.sql)
# - Calcula checksums SHA-256
# - Elimina backups antiguos (retencion)
# - Verifica restauracion de forma opcional

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/.env}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/talentia}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
VERIFY_RESTORE="${VERIFY_RESTORE:-0}"

if [[ "${1:-}" == "--verify-restore" ]]; then
  VERIFY_RESTORE="1"
fi

log() {
  printf '[backup][%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: comando requerido no encontrado: $1"
    exit 1
  fi
}

# Cargar variables de .env si existe
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Permitir sobreescritura por env vars explicitas
DB_HOST="${DB_HOST:-${PGHOST:-}}"
DB_PORT="${DB_PORT:-${PGPORT:-5432}}"
DB_USER="${DB_USER:-${PGUSER:-}}"
DB_PASSWORD="${DB_PASSWORD:-${PGPASSWORD:-}}"
DB_NAME="${DB_NAME:-}"

# Intentar completar datos desde DATABASE_URL si faltan
DATABASE_URL="${DATABASE_URL:-}"
if [[ -n "$DATABASE_URL" ]]; then
  # Soporta: postgresql://user:pass@host:5432/dbname
  if [[ "$DATABASE_URL" =~ ^postgres(ql)?://([^:/@]+)(:([^@]*))?@([^:/?#]+)(:([0-9]+))?/([^?]+) ]]; then
    parsed_user="${BASH_REMATCH[2]}"
    parsed_pass="${BASH_REMATCH[4]:-}"
    parsed_host="${BASH_REMATCH[5]}"
    parsed_port="${BASH_REMATCH[7]:-5432}"
    parsed_db="${BASH_REMATCH[8]}"

    DB_USER="${DB_USER:-$parsed_user}"
    DB_PASSWORD="${DB_PASSWORD:-$parsed_pass}"
    DB_HOST="${DB_HOST:-$parsed_host}"
    DB_PORT="${DB_PORT:-$parsed_port}"
    DB_NAME="${DB_NAME:-$parsed_db}"
  fi
fi

if [[ -z "$DB_HOST" || -z "$DB_USER" || -z "$DB_NAME" ]]; then
  log "ERROR: faltan parametros de conexion. Define DB_HOST, DB_USER y DB_NAME, o configura DATABASE_URL en .env"
  exit 1
fi

require_cmd pg_dump
require_cmd pg_dumpall
require_cmd psql
require_cmd createdb
require_cmd dropdb
require_cmd sha256sum
require_cmd find

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/talentia_db_${TS}.dump"
GLOBALS_FILE="$BACKUP_DIR/globals_${TS}.sql"
CHECKSUM_FILE="$BACKUP_DIR/checksums_${TS}.txt"
LOG_FILE="$BACKUP_DIR/backup_${TS}.log"

# Redirige salida completa a log y consola
exec > >(tee -a "$LOG_FILE") 2>&1

log "Iniciando respaldo"
log "Destino: $BACKUP_DIR"
log "Base de datos: $DB_NAME"

export PGPASSWORD="$DB_PASSWORD"

log "Generando dump custom"
pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -F c \
  -Z 9 \
  -f "$DUMP_FILE"

log "Exportando roles/globales"
pg_dumpall \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  --globals-only \
  > "$GLOBALS_FILE"

log "Calculando checksums"
sha256sum "$DUMP_FILE" "$GLOBALS_FILE" > "$CHECKSUM_FILE"

if [[ "$VERIFY_RESTORE" == "1" ]]; then
  TEST_DB="talentia_restore_test_${TS}"
  log "Verificando restauracion en base temporal: $TEST_DB"

  createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEST_DB"
  trap 'dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true' EXIT

  pg_restore \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$TEST_DB" \
    "$DUMP_FILE"

  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TEST_DB" -c "SELECT NOW();" >/dev/null

  dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TEST_DB"
  trap - EXIT

  log "Verificacion de restauracion completada"
fi

log "Aplicando politica de retencion: $RETENTION_DAYS dias"
find "$BACKUP_DIR" -type f -name 'talentia_db_*.dump' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'globals_*.sql' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'checksums_*.txt' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'backup_*.log' -mtime +"$RETENTION_DAYS" -delete

unset PGPASSWORD

log "Respaldo finalizado correctamente"
log "Archivo dump: $DUMP_FILE"
log "Archivo globales: $GLOBALS_FILE"
log "Checksums: $CHECKSUM_FILE"
log "Log: $LOG_FILE"
