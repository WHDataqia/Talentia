#!/usr/bin/env bash
set -euo pipefail

# Backup solo de PostgreSQL para Talentia
# Datos preconfigurados de este proyecto:
# - Host: localhost
# - Puerto: 5432
# - Usuario: postgres
# - Base: talentia_db

DB_HOST="localhost"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="talentia_db"
BACKUP_DIR="/var/backups/talentia"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if [[ -z "${PGPASSWORD:-}" ]]; then
  read -r -s -p "Contrasena PostgreSQL para $DB_USER: " PGPASSWORD
  echo
  export PGPASSWORD
fi

TS="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="$BACKUP_DIR/talentia_db_${TS}.dump"

pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -F c \
  -Z 9 \
  -f "$DUMP_FILE"

sha256sum "$DUMP_FILE" > "$DUMP_FILE.sha256"

echo "Backup creado: $DUMP_FILE"
echo "Checksum: $DUMP_FILE.sha256"
