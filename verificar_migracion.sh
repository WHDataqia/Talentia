#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED=0

ok() {
  echo -e "${GREEN}[OK]${NC} $1"
}

warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

fail() {
  echo -e "${RED}[FAIL]${NC} $1"
  FAILED=$((FAILED + 1))
}

echo "============================================"
echo "   VERIFICACION MIGRACION TALENTIA (LINUX)"
echo "============================================"

if command -v python3 >/dev/null 2>&1; then
  ok "python3 detectado: $(python3 --version 2>&1)"
else
  fail "python3 no está instalado"
fi

if [[ -d ".venv" || -d "venv" ]]; then
  ok "entorno virtual detectado"
else
  fail "no existe .venv ni venv"
fi

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || fail "no se pudo activar .venv"
elif [[ -d "venv" ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate || fail "no se pudo activar venv"
fi

if python3 -c "import flask, flask_cors, flask_jwt_extended, psycopg2" >/dev/null 2>&1; then
  ok "dependencias Python críticas importan correctamente"
else
  fail "faltan dependencias Python (instala backend/requirements.txt)"
fi

if [[ -f "backend/app.py" ]]; then
  ok "backend/app.py encontrado"
else
  fail "backend/app.py no encontrado"
fi

if [[ -f "backend/requirements.txt" ]]; then
  ok "backend/requirements.txt encontrado"
else
  fail "backend/requirements.txt no encontrado"
fi

if command -v curl >/dev/null 2>&1; then
  ok "curl detectado"
else
  warn "curl no detectado (probar_servidor.sh lo necesita)"
fi

if command -v psql >/dev/null 2>&1; then
  ok "psql detectado"
else
  warn "psql no detectado (recomendado para diagnóstico PostgreSQL)"
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  ok "DATABASE_URL configurada"
else
  warn "DATABASE_URL no está configurada; se usará valor por defecto en app.py"
fi

echo ""
if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}Verificación finalizada sin errores críticos.${NC}"
  exit 0
else
  echo -e "${RED}Se detectaron ${FAILED} error(es) crítico(s).${NC}"
  exit 1
fi
