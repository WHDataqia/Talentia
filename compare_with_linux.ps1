#!/usr/bin/env pwsh
# compare_with_linux.ps1
# Compara los archivos del workspace local con los instalados en el servidor Linux.
# Los archivos estaticos (HTML/CSS/JS/JSON) se comparan por checksum SHA-256.
# Los archivos Python del backend se comparan contra el codigo fuente remoto
# si el servidor tiene disponible ~/talentia-build-temp (post-despliegue parcial).
#
# Uso: .\compare_with_linux.ps1
# Uso (solo estaticos): .\compare_with_linux.ps1 -SoloEstaticos
# Uso (mostrar diff completo): .\compare_with_linux.ps1 -MostrarDiff

param(
    [switch]$SoloEstaticos,
    [switch]$MostrarDiff,
    [string]$Servidor = "blue@SRV-CORP-ENCUESTAS",
    [int]$PuertoSSH = 22
)

# ==================== CONFIGURACION ====================
$RUTA_LOCAL   = "c:\dataQIA\Talentia"
$RUTA_RUNTIME = "~/talentia-runtime"
# =======================================================

function Log($msg)  { Write-Host "[compare] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[=] $msg" -ForegroundColor Green }
function Dif($msg)  { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Sec($msg)  { Write-Host "`n--- $msg ---" -ForegroundColor Magenta }

$SSH_OPTS = @("-p", "$PuertoSSH", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=8")

# ---- 0. Validar conectividad ----
Log "Conectando a $Servidor ..."
$ping = & ssh @SSH_OPTS $Servidor "echo ok" 2>&1
if ($LASTEXITCODE -ne 0) {
    Err "No se pudo conectar a '$Servidor'."
    Err "Verifica IP/usuario/llave SSH o prueba: ssh $Servidor"
    exit 1
}
Log "Conexion SSH OK."

# ============================================================
# PARTE 1: ARCHIVOS ESTATICOS (HTML / CSS / JS / config.json)
# ============================================================
Sec "ARCHIVOS ESTATICOS (HTML / CSS / JS / config.json)"

$extensionesEstaticas = @('.html', '.css', '.js')

# Recolectar archivos estaticos locales (solo raiz, sin subdirectorios de frameworks)
$archivosLocales = Get-ChildItem -Path $RUTA_LOCAL -File |
    Where-Object { $_.Extension -in $extensionesEstaticas -or $_.Name -eq 'config.json' } |
    Select-Object -ExpandProperty Name

$totalArchivos    = $archivosLocales.Count
$iguales          = 0
$diferentes       = 0
$soloLocal        = 0
$soloRemoto       = 0
$archivosConDiff  = @()

Log "Comparando $totalArchivos archivos estaticos..."

foreach ($archivo in ($archivosLocales | Sort-Object)) {
    # Checksum local (SHA-256, primeros 16 hex)
    $hashLocal = (Get-FileHash -Path (Join-Path $RUTA_LOCAL $archivo) -Algorithm SHA256).Hash.Substring(0, 16)

    # Checksum remoto via SSH
    $hashRemotoRaw = & ssh @SSH_OPTS $Servidor "sha256sum $RUTA_RUNTIME/$archivo 2>/dev/null | awk '{print substr(`$1,1,16)}'" 2>&1
    $hashRemoto    = ($hashRemotoRaw -join "").Trim()

    if ([string]::IsNullOrEmpty($hashRemoto)) {
        Dif "  [SOLO LOCAL]    $archivo"
        $soloLocal++
        $archivosConDiff += $archivo
    } elseif ($hashLocal -eq $hashRemoto) {
        Ok  "  [IDENTICO]      $archivo"
        $iguales++
    } else {
        Dif "  [DIFERENTE]     $archivo  (local: $hashLocal  remoto: $hashRemoto)"
        $diferentes++
        $archivosConDiff += $archivo
    }
}

# Archivos que existen solo en remoto (no en local)
$remotosRaw = & ssh @SSH_OPTS $Servidor @"
cd $RUTA_RUNTIME 2>/dev/null && find . -maxdepth 1 -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' -o -name 'config.json' \) | sed 's|^\./||'
"@ 2>&1

$remotos = $remotosRaw -split "`n" | Where-Object { $_.Trim() -ne "" } | ForEach-Object { $_.Trim() }

foreach ($archivoRemoto in $remotos) {
    if ($archivoRemoto -notin $archivosLocales) {
        Dif "  [SOLO REMOTO]   $archivoRemoto"
        $soloRemoto++
    }
}

Write-Host ""
Write-Host "  Resumen estaticos: $iguales identicos, $diferentes diferentes, $soloLocal solo-local, $soloRemoto solo-remoto" -ForegroundColor White

# ============================================================
# PARTE 2: ARCHIVOS PYTHON DEL BACKEND
# ============================================================
if (-not $SoloEstaticos) {
    Sec "ARCHIVOS PYTHON DEL BACKEND"

    # Archivos Python relevantes del backend
    $pyLocales = Get-ChildItem -Path (Join-Path $RUTA_LOCAL "backend") -File -Filter "*.py" |
        Where-Object { $_.Name -notmatch "__pycache__|\.pyc" } |
        Select-Object -ExpandProperty Name

    # Verificar si el servidor tiene el codigo fuente Python (solo si no fue limpiado)
    $tieneSource = & ssh @SSH_OPTS $Servidor "test -f ~/talentia-build-temp/backend/app.py && echo si || echo no" 2>&1
    $tieneSource = ($tieneSource -join "").Trim()

    if ($tieneSource -eq "si") {
        Log "Fuente Python encontrado en ~/talentia-build-temp en el servidor."
        $igualesPy   = 0
        $diferentesPy = 0
        $soloLocalPy = 0

        foreach ($pyFile in ($pyLocales | Sort-Object)) {
            $hashLocal  = (Get-FileHash -Path (Join-Path $RUTA_LOCAL "backend" $pyFile) -Algorithm SHA256).Hash.Substring(0, 16)
            $hashRemoto = & ssh @SSH_OPTS $Servidor "sha256sum ~/talentia-build-temp/backend/$pyFile 2>/dev/null | awk '{print substr(`$1,1,16)}'" 2>&1
            $hashRemoto = ($hashRemoto -join "").Trim()

            if ([string]::IsNullOrEmpty($hashRemoto)) {
                Dif "  [SOLO LOCAL]    backend/$pyFile"
                $soloLocalPy++
            } elseif ($hashLocal -eq $hashRemoto) {
                Ok  "  [IDENTICO]      backend/$pyFile"
                $igualesPy++
            } else {
                Dif "  [DIFERENTE]     backend/$pyFile  (local: $hashLocal  remoto: $hashRemoto)"
                $diferentesPy++
                $archivosConDiff += "backend/$pyFile"
            }
        }
        Write-Host ""
        Write-Host "  Resumen Python: $igualesPy identicos, $diferentesPy diferentes, $soloLocalPy solo-local" -ForegroundColor White
    } else {
        Write-Host ""
        Write-Host "  El servidor no tiene el codigo fuente Python disponible." -ForegroundColor DarkYellow
        Write-Host "  (~/talentia-build-temp fue limpiado despues de compilar con Nuitka)" -ForegroundColor DarkYellow
        Write-Host "  El backend corre como binario compilado: $RUTA_RUNTIME/talentia" -ForegroundColor DarkYellow
        Write-Host ""

        # Al menos verificar fecha del binario
        $infoBinario = & ssh @SSH_OPTS $Servidor "stat -c '%n  tamano=%s bytes  modificado=%y' $RUTA_RUNTIME/talentia 2>/dev/null || echo 'binario no encontrado'" 2>&1
        Log "Info binario remoto: $($infoBinario -join ' ')"
    }

    # requirements.txt siempre puede compararse
    Sec "requirements.txt"
    $hashReqLocal  = (Get-FileHash -Path (Join-Path $RUTA_LOCAL "backend\requirements.txt") -Algorithm SHA256).Hash.Substring(0, 16)
    $hashReqRemoto = & ssh @SSH_OPTS $Servidor "sha256sum $RUTA_RUNTIME/requirements.txt 2>/dev/null | awk '{print substr(`$1,1,16)}'" 2>&1
    $hashReqRemoto = ($hashReqRemoto -join "").Trim()

    if ([string]::IsNullOrEmpty($hashReqRemoto)) {
        Dif "  requirements.txt no existe en runtime remoto"
    } elseif ($hashReqLocal -eq $hashReqRemoto) {
        Ok "  requirements.txt IDENTICO"
    } else {
        Dif "  requirements.txt DIFERENTE"
        $archivosConDiff += "backend/requirements.txt"
    }
}

# ============================================================
# PARTE 3: DIFF DETALLADO (si se pide y hay diferencias)
# ============================================================
if ($MostrarDiff -and $archivosConDiff.Count -gt 0) {
    Sec "DIFF DETALLADO"

    foreach ($archivo in $archivosConDiff) {
        Write-Host "`n=== $archivo ===" -ForegroundColor Magenta

        $rutaRemota = if ($archivo.StartsWith("backend/")) {
            "~/talentia-build-temp/$archivo"
        } else {
            "$RUTA_RUNTIME/$archivo"
        }

        # Obtener contenido remoto
        $contenidoRemoto = & ssh @SSH_OPTS $Servidor "cat $rutaRemota 2>/dev/null" 2>&1

        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty(($contenidoRemoto -join ""))) {
            Write-Host "  (archivo no existe en remoto, es solo-local)" -ForegroundColor DarkYellow
            continue
        }

        # Guardar temporal
        $tmpRemoto = Join-Path $env:TEMP "talentia_diff_remoto_$([System.IO.Path]::GetFileName($archivo))"
        $contenidoRemoto | Set-Content -Path $tmpRemoto -Encoding UTF8

        $rutaLocal = if ($archivo.StartsWith("backend/")) {
            Join-Path $RUTA_LOCAL $archivo.Replace("/", "\")
        } else {
            Join-Path $RUTA_LOCAL $archivo
        }

        # Diff con git diff --no-index si git esta disponible
        if (Get-Command git -ErrorAction SilentlyContinue) {
            & git diff --no-index --stat $tmpRemoto $rutaLocal 2>&1
            & git diff --no-index $tmpRemoto $rutaLocal 2>&1
        } else {
            Compare-Object (Get-Content $tmpRemoto) (Get-Content $rutaLocal) |
                ForEach-Object {
                    if ($_.SideIndicator -eq "<=") { Write-Host "- $($_.InputObject)" -ForegroundColor Red }
                    else                            { Write-Host "+ $($_.InputObject)" -ForegroundColor Green }
                }
        }

        Remove-Item $tmpRemoto -Force -ErrorAction SilentlyContinue
    }
}

# ============================================================
# RESUMEN FINAL
# ============================================================
Sec "RESUMEN FINAL"

if ($archivosConDiff.Count -eq 0) {
    Write-Host "  Todo sincronizado: no hay diferencias entre local y remoto." -ForegroundColor Green
} else {
    Write-Host "  $($archivosConDiff.Count) archivo(s) con diferencias:" -ForegroundColor Yellow
    foreach ($a in $archivosConDiff) {
        Write-Host "    - $a" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "  Para ver el diff completo: .\compare_with_linux.ps1 -MostrarDiff" -ForegroundColor Cyan
    Write-Host "  Para desplegar cambios:    .\deploy.ps1" -ForegroundColor Cyan
    Write-Host "  Para desplegar solo HTML:  .\deploy.ps1 -SoloEstaticos" -ForegroundColor Cyan
}
Write-Host ""
