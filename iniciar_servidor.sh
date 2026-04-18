#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 no está instalado."
  exit 1
fi

if [[ ! -d ".venv" && ! -d "venv" ]]; then
  echo "[ERROR] No se encontró entorno virtual (.venv o venv)."
  echo "Ejecuta: python3 -m venv .venv"
  exit 1
fi

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

if [[ ! -f "backend/requirements.txt" ]]; then
  echo "[ERROR] No se encontró backend/requirements.txt"
  exit 1
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-5000}"
export FLASK_DEBUG="${FLASK_DEBUG:-0}"

echo "[INFO] Iniciando Talentia en http://${HOST}:${PORT}"
python3 backend/app.py
