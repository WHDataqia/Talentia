#!/usr/bin/env pwsh
# deploy.ps1 - Compilar y desplegar Talentia en servidor Linux
# Uso: .\deploy.ps1
# Uso solo HTML/JS/CSS: .\deploy.ps1 -SoloEstaticos

param(
    [switch]$SoloEstaticos,
    [string]$Servidor = "blue@SRV-CORP-ENCUESTAS",
    [int]$PuertoSSH = 22
)

# ==================== CONFIGURACION ====================
$SERVIDOR        = $Servidor
$RUTA_LOCAL      = "c:\dataQIA\Talentia"
$RUTA_RUNTIME    = "~/talentia-runtime"
$RUTA_BUILD_TEMP = "~/talentia-build-temp"   # carpeta temporal solo para compilar
$RUTA_TMP_LOCAL  = Join-Path $env:TEMP "talentia-deploy"
# =======================================================

function Log($msg) { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Ok($msg)  { Write-Host "[OK] $msg" -ForegroundColor Green }
function Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
    Err "No se encontro 'tar' en Windows. Instala/activa bsdtar o usa una version de Windows con tar.exe disponible."
}

New-Item -ItemType Directory -Force -Path $RUTA_TMP_LOCAL | Out-Null

$SSH_OPTS = @("-p", "$PuertoSSH", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8")
$SCP_OPTS = @("-P", "$PuertoSSH", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8")

$hostMostrado = $SERVIDOR
if ($SERVIDOR.Contains('@')) {
    $hostMostrado = $SERVIDOR.Split('@')[1]
}

# ---- 0. Validar conectividad SSH antes de iniciar ----
Log "Validando conectividad SSH con $SERVIDOR ..."
$sshSalida = & ssh @SSH_OPTS $SERVIDOR "echo ok" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[SSH] $sshSalida" -ForegroundColor DarkYellow
    Err "No se pudo conectar a '$SERVIDOR'. Verifica IP/usuario/red/llave SSH y prueba: ssh $SERVIDOR"
}
Ok "Conectividad SSH OK."

# ---- 1. Subir archivos estaticos (siempre) ----
$staticBundle = Join-Path $RUTA_TMP_LOCAL "talentia_static.tar.gz"
if (Test-Path $staticBundle) { Remove-Item $staticBundle -Force }

Log "Empaquetando estaticos (HTML, CSS, JS, JSON, Logo)..."
$staticItems = Get-ChildItem -Path $RUTA_LOCAL -File |
    Where-Object { $_.Extension -in '.html', '.css', '.js' -or $_.Name -eq 'config.json' } |
    ForEach-Object { $_.Name }
$staticItems += 'Logo'

Push-Location $RUTA_LOCAL
& tar -czf $staticBundle @staticItems
$tarExit = $LASTEXITCODE
Pop-Location
if ($tarExit -ne 0) { Err "Fallo empaquetando archivos estaticos" }

Log "Subiendo bundle de estaticos..."
& scp @SCP_OPTS $staticBundle "${SERVIDOR}:${RUTA_RUNTIME}/talentia_static.tar.gz" 2>&1
if ($LASTEXITCODE -ne 0) { Err "Fallo subiendo bundle de estaticos" }

Log "Extrayendo bundle de estaticos en runtime..."
& ssh @SSH_OPTS $SERVIDOR "cd $RUTA_RUNTIME && tar -xzf talentia_static.tar.gz && rm -f talentia_static.tar.gz" 2>&1
if ($LASTEXITCODE -ne 0) { Err "Fallo extrayendo bundle de estaticos en runtime" }

Ok "Estaticos subidos."

if ($SoloEstaticos) {
    Log "Limpiando carpeta temporal remota de builds previos..."
    & ssh @SSH_OPTS $SERVIDOR "rm -rf $RUTA_BUILD_TEMP"
    if ($LASTEXITCODE -ne 0) { Err "Fallo limpiando $RUTA_BUILD_TEMP" }
    Ok "Servidor limpio: sin carpeta temporal de build."
    Ok "Despliegue de estaticos completado. No se recompilo el backend."
    exit 0
}

# ---- 2. Subir codigo fuente Python ----
Log "Creando carpeta temporal de build en servidor..."
& ssh @SSH_OPTS $SERVIDOR "rm -rf $RUTA_BUILD_TEMP && mkdir -p $RUTA_BUILD_TEMP"

Log "Empaquetando codigo fuente para build temporal..."
$sourceBundle = Join-Path $RUTA_TMP_LOCAL "talentia_build.tar.gz"
if (Test-Path $sourceBundle) { Remove-Item $sourceBundle -Force }
$sourceTarArgs = @(
    "-czf", $sourceBundle,
    "--exclude=backend/venv",
    "--exclude=backend/.venv",
    "--exclude=backend/__pycache__",
    "--exclude=backend/*.pyc",
    "--exclude=backend/temp/__pycache__",
    "backend",
    "build_linux_nuitka.sh"
)

# Agregar estaticos que build_linux_nuitka.sh necesita en la raiz
$staticFiles = Get-ChildItem -Path $RUTA_LOCAL -File |
    Where-Object { $_.Extension -in '.html', '.css', '.js' -or $_.Name -eq 'config.json' } |
    ForEach-Object { $_.Name }
foreach ($sf in $staticFiles) { $sourceTarArgs += $sf }
$sourceTarArgs += 'Logo'
if (Test-Path "$RUTA_LOCAL\.env.example.postgres") { $sourceTarArgs += '.env.example.postgres' }
elseif (Test-Path "$RUTA_LOCAL\.env.ejemplo") { $sourceTarArgs += '.env.ejemplo' }

Push-Location $RUTA_LOCAL
& tar @sourceTarArgs
$tarExit = $LASTEXITCODE
Pop-Location
if ($tarExit -ne 0) { Err "Fallo empaquetando codigo fuente para build" }

Log "Subiendo bundle de build al servidor (carpeta temporal)..."
& scp @SCP_OPTS $sourceBundle "${SERVIDOR}:${RUTA_BUILD_TEMP}/talentia_build.tar.gz" 2>&1
if ($LASTEXITCODE -ne 0) { Err "Fallo subiendo bundle de build" }

Log "Extrayendo bundle de build temporal..."
& ssh @SSH_OPTS $SERVIDOR "cd $RUTA_BUILD_TEMP && tar -xzf talentia_build.tar.gz && rm -f talentia_build.tar.gz" 2>&1
if ($LASTEXITCODE -ne 0) { Err "Fallo extrayendo bundle de build" }
Ok "Fuente subido."

# ---- 3. Compilar en Linux con Nuitka ----
Log "Compilando en Linux desde carpeta temporal (esto puede tardar unos minutos)..."
$cmdCompilar = "set -e; cd $RUTA_BUILD_TEMP; chmod +x build_linux_nuitka.sh; ./build_linux_nuitka.sh"
& ssh @SSH_OPTS $SERVIDOR $cmdCompilar
if ($LASTEXITCODE -ne 0) { Err "Fallo la compilacion en Linux" }
Ok "Compilacion exitosa."

# ---- 4. Parar servicio, copiar binario, reiniciar ----
Log "Parando servicio Talentia antes de copiar binario..."
& ssh @SSH_OPTS $SERVIDOR "sudo systemctl stop talentia"
Start-Sleep -Seconds 2

Log "Copiando nuevo binario a talentia-runtime y limpiando build temporal..."
$cmdPublicar = "cp $RUTA_BUILD_TEMP/release_linux/app.dist/talentia $RUTA_RUNTIME/talentia; chmod +x $RUTA_RUNTIME/talentia; rm -rf $RUTA_BUILD_TEMP"
& ssh @SSH_OPTS $SERVIDOR $cmdPublicar
if ($LASTEXITCODE -ne 0) { Err "Fallo copiando el binario" }
Ok "Binario actualizado."

# ---- 5. Iniciar servicio ----
Log "Iniciando servicio Talentia..."
& ssh @SSH_OPTS $SERVIDOR "sudo systemctl start talentia"
if ($LASTEXITCODE -ne 0) { Err "Fallo iniciando el servicio" }

Start-Sleep -Seconds 3

# ---- 6. Verificar que levanto ----
Log "Verificando que el servicio esta activo..."
$estado = & ssh @SSH_OPTS $SERVIDOR "systemctl is-active talentia"
if ($estado -eq "active") {
    Ok "Servicio activo y corriendo."
} else {
    Err "El servicio no quedo activo. Revisa: sudo journalctl -u talentia -n 50"
}

Ok "Despliegue completado exitosamente."
Write-Host ""
Write-Host "  Accede en: http://$hostMostrado`:5000/login.html" -ForegroundColor Yellow
