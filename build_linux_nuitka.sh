#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BUILD_DIR="$ROOT_DIR/build_linux"
DIST_DIR="$BUILD_DIR/app.dist"
RELEASE_DIR="$ROOT_DIR/release_linux"

echo "[1/6] Limpiando artefactos previos..."
rm -rf "$BUILD_DIR" "$RELEASE_DIR"

echo "[2/6] Creando/activando entorno virtual de build..."
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install nuitka ordered-set zstandard
python -m pip install -r backend/requirements.txt

echo "[3/6] Compilando backend con Nuitka..."
python -m nuitka \
  --standalone \
  --remove-output \
  --output-dir="$BUILD_DIR" \
  --output-filename=talentia \
  --follow-imports \
  backend/app.py

# Nuitka crea carpeta con nombre del output-filename + .dist
if [[ ! -d "$DIST_DIR" ]]; then
  echo "[ERROR] No se encontro salida esperada en $DIST_DIR"
  exit 1
fi

echo "[4/6] Copiando assets necesarios (sin fuentes Python)..."
# Frontend y assets estáticos estrictamente necesarios
cp -f login.html index.html historial.html detalle-evaluacion.html informe-comparativo.html "$DIST_DIR"/
cp -f evaluacion-competencias.html autoevaluacion.html crear-evaluacion.html empleados.html "$DIST_DIR"/
cp -f admin.html admin-maestras.html styles.css competencia-estilos.css "$DIST_DIR"/
cp -f keep-alive.js competencia-evaluador.js config-loader.js config.json "$DIST_DIR"/
cp -rf Logo "$DIST_DIR"/

# Plantilla de entorno para producción
if [[ -f ".env.example.postgres" ]]; then
  cp -f .env.example.postgres "$DIST_DIR/.env.example"
elif [[ -f ".env.ejemplo" ]]; then
  cp -f .env.ejemplo "$DIST_DIR/.env.example"
fi

echo "[5/6] Preparando paquete de release..."
mkdir -p "$RELEASE_DIR"
cp -rf "$DIST_DIR" "$RELEASE_DIR/"

cat > "$RELEASE_DIR/README_RUN.txt" << 'EOF'
Talentia Linux Binary (Nuitka)

1) Entrar a carpeta:
   cd talentia.dist

2) Crear .env (copiar desde .env.example y ajustar valores):
   cp .env.example .env

3) Activar seguridad:
   SECURITY_HARDENING=1

4) Ejecutar binario:
   ./talentia

5) Abrir:
   http://127.0.0.1:5000

Nota:
- El backend está compilado. No se despliegan archivos .py del servidor.
- Si quieres usar otra ruta de estáticos, define TALENTIA_STATIC_DIR.
EOF

echo "[6/6] Listo. Paquete generado en: $RELEASE_DIR/app.dist"
