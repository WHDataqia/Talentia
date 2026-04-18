#!/bin/bash

# ============================================
# SCRIPT PRUEBAS FUNCIONALES - Talentia
# ============================================
# Prueba endpoints criticos del backend
# Ejecutar DESPUES de iniciar el servidor

set +e  # No salir en errores para mostrar todos los resultados

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================"
echo "   PRUEBAS FUNCIONALES TALENTIA"
echo "============================================"
echo ""

# ConfiguraciÃ³n
BASE_URL="http://localhost:5000"
PASSED=0
FAILED=0

# FunciÃ³n para test
test_endpoint() {
    local name=$1
    local url=$2
    local expected_code=$3
    local description=$4
    
    echo -e "${BLUE}[TEST]${NC} $name"
    echo "  â†’ $url"
    
    # Hacer request con timeout
    response=$(curl -s -w "\n%{http_code}" --max-time 5 "$url" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n -1)
    
    if [ "$http_code" = "$expected_code" ]; then
        echo -e "  ${GREEN}âœ“ PASS${NC} (HTTP $http_code)"
        ((PASSED++))
    else
        echo -e "  ${RED}âœ— FAIL${NC} (esperado HTTP $expected_code, recibido $http_code)"
        if [ ! -z "$body" ] && [ ${#body} -lt 200 ]; then
            echo "  Respuesta: $body"
        fi
        ((FAILED++))
    fi
    echo ""
}

# FunciÃ³n para test con JSON
test_json_endpoint() {
    local name=$1
    local url=$2
    local json_field=$3
    local description=$4
    
    echo -e "${BLUE}[TEST]${NC} $name"
    echo "  â†’ $url"
    
    response=$(curl -s --max-time 5 "$url" 2>/dev/null)
    http_code=$?
    
    if [ $http_code -eq 0 ] && echo "$response" | grep -q "$json_field"; then
        echo -e "  ${GREEN}âœ“ PASS${NC} (respuesta JSON vÃ¡lida)"
        ((PASSED++))
    else
        echo -e "  ${RED}âœ— FAIL${NC} (respuesta invÃ¡lida o timeout)"
        if [ ${#response} -lt 200 ]; then
            echo "  Respuesta: $response"
        fi
        ((FAILED++))
    fi
    echo ""
}

# Verificar que el servidor estÃ¡ corriendo
echo "Verificando que el servidor estÃ¡ arrancado..."
if ! curl -s --max-time 2 "$BASE_URL/api/health" > /dev/null 2>&1; then
    echo -e "${RED}âœ— ERROR:${NC} El servidor no estÃ¡ respondiendo en $BASE_URL"
    echo ""
    echo "AsegÃºrate de iniciar el servidor primero:"
    echo "  ./iniciar_servidor.sh"
    echo ""
    exit 1
fi

echo -e "${GREEN}âœ“ Servidor detectado${NC}"
echo ""
echo "============================================"
echo "   EJECUTANDO PRUEBAS"
echo "============================================"
echo ""

# ============================================
# PRUEBAS BÃSICAS
# ============================================

echo "=== ENDPOINTS ESTÃTICOS ==="
echo ""

test_endpoint \
    "Frontend Principal" \
    "$BASE_URL/" \
    "200" \
    "Debe cargar index.html o redirigir a login"

test_endpoint \
    "PÃ¡gina Login" \
    "$BASE_URL/login.html" \
    "200" \
    "Debe cargar la pÃ¡gina de login"

test_endpoint \
    "Estilos CSS" \
    "$BASE_URL/styles.css" \
    "200" \
    "Debe servir archivo CSS"

echo "=== ENDPOINTS API ==="
echo ""

test_json_endpoint \
    "Health Check" \
    "$BASE_URL/api/health" \
    "status" \
    "Debe retornar JSON con status"

test_json_endpoint \
    "Test Endpoint" \
    "$BASE_URL/api/test" \
    "message" \
    "Debe retornar JSON con mensaje de prueba"

# Login (sin credenciales debe fallar)
echo -e "${BLUE}[TEST]${NC} Login sin credenciales"
echo "  â†’ $BASE_URL/api/login"
response=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    --max-time 5 \
    "$BASE_URL/api/login" 2>/dev/null)

if echo "$response" | grep -qi "error\|invalid\|required"; then
    echo -e "  ${GREEN}âœ“ PASS${NC} (rechaza login sin credenciales)"
    ((PASSED++))
else
    echo -e "  ${RED}âœ— FAIL${NC} (deberÃ­a rechazar login sin credenciales)"
    ((FAILED++))
fi
echo ""

# Endpoint protegido (sin token debe fallar)
echo -e "${BLUE}[TEST]${NC} Endpoint protegido sin token"
echo "  â†’ $BASE_URL/api/empleados"
response=$(curl -s -w "\n%{http_code}" --max-time 5 "$BASE_URL/api/empleados" 2>/dev/null)
http_code=$(echo "$response" | tail -n1)

if [ "$http_code" = "401" ] || [ "$http_code" = "422" ]; then
    echo -e "  ${GREEN}âœ“ PASS${NC} (rechaza acceso sin token, HTTP $http_code)"
    ((PASSED++))
else
    echo -e "  ${RED}âœ— FAIL${NC} (deberÃ­a rechazar con 401/422, recibiÃ³ $http_code)"
    ((FAILED++))
fi
echo ""

# ============================================
# PRUEBA CON CREDENCIALES (si existen)
# ============================================

echo "=== PRUEBAS CON AUTENTICACIÃ“N ==="
echo ""

# Buscar credenciales de prueba
ADMIN_USER=""
ADMIN_PASS=""

if [ -f "CREDENCIALES_PRUEBA.md" ]; then
    echo "Buscando credenciales en CREDENCIALES_PRUEBA.md..."
    # Intentar extraer usuario admin (ajustar segÃºn tu formato)
    # Esto es un ejemplo, puede necesitar ajuste
    ADMIN_USER=$(grep -i "admin" CREDENCIALES_PRUEBA.md | grep -o "[a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]*\.[a-zA-Z]*" | head -1)
fi

if [ ! -z "$ADMIN_USER" ]; then
    echo "Usuario encontrado: $ADMIN_USER"
    echo ""
    echo -e "${YELLOW}NOTA:${NC} Para hacer login real, necesitas ejecutar manualmente:"
    echo "  curl -X POST -H 'Content-Type: application/json' \\"
    echo "    -d '{\"usuario\":\"$ADMIN_USER\",\"contrasena\":\"TU_PASSWORD\"}' \\"
    echo "    $BASE_URL/api/login"
else
    echo -e "${YELLOW}âš ${NC} No se encontraron credenciales automÃ¡ticamente"
    echo "Prueba login manualmente con tus usuarios de prueba"
fi

echo ""

# ============================================
# RESUMEN
# ============================================

echo "============================================"
echo "   RESUMEN DE PRUEBAS"
echo "============================================"
echo ""

TOTAL=$((PASSED + FAILED))
echo "Total ejecutadas: $TOTAL"
echo -e "Exitosas: ${GREEN}$PASSED${NC}"
echo -e "Fallidas: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}âœ“ TODAS LAS PRUEBAS PASARON${NC}"
    echo ""
    echo "El servidor estÃ¡ funcionando correctamente."
    echo "PrÃ³ximo paso: Probar manualmente en el navegador"
    echo "  â†’ $BASE_URL"
    exit 0
else
    echo -e "${RED}âœ— ALGUNAS PRUEBAS FALLARON${NC}"
    echo ""
    echo "Revisa los errores arriba y verifica:"
    echo "  1. El servidor estÃ¡ corriendo: ./iniciar_servidor.sh"
    echo "  2. No hay errores en la consola del servidor"
    echo "  3. PostgreSQL esta disponible y DATABASE_URL es correcta"
    echo "  4. Las dependencias estan instaladas: pip install -r backend/requirements.txt"
    exit 1
fi

