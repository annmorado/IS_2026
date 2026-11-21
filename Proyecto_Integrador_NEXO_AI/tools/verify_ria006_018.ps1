# RIA-006..RIA-018 - Windows/Neon/Next/Expo verification. DOES NOT PUSH TO GITHUB.
$ErrorActionPreference = 'Stop'
$root = "$HOME\Projects\nexo-ai"
$api = Join-Path $root 'services\api'
$web = Join-Path $root 'apps\web'
$mobile = Join-Path $root 'apps\mobile'
$python = Join-Path $api '.venv\Scripts\python.exe'

function RunNative([string]$label,[scriptblock]$work) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    & $work
    if ($LASTEXITCODE -ne 0) { throw "$label FALLO (exit $LASTEXITCODE)" }
}

if (-not (Test-Path $python)) { throw "Python virtual no encontrado: $python" }
Set-Location $root
if ((git branch --show-current) -ne 'main') { throw 'Ejecuta desde la rama main' }
if ((git rev-parse --short=7 HEAD) -ne '0e89c00') {
    throw 'La version base esperada es RIA-001..005 (0e89c00); revisa git log antes de seguir'
}

Set-Location $api
RunNative '1/8 PRUEBAS BACKEND' { & $python -m pytest -q }
RunNative '2/8 EVALUACION TEMPORAL SIN FUGA' { & $python -m scripts.evaluate_ria006_007 }

Write-Host "`n=== 3/8 MIGRACION NEON ===" -ForegroundColor Cyan
Write-Host 'ADVERTENCIA: confirma respaldo/rama de tu Neon antes de continuar' -ForegroundColor Yellow
RunNative 'Alembic upgrade' { & $python -m alembic -c alembic.ini upgrade head }
$revision = & $python -m alembic -c alembic.ini current
if ($LASTEXITCODE -ne 0 -or ($revision -join ' ') -notmatch 'ai_0018 \(head\)') {
    throw "La revision no es ai_0018 (head): $revision"
}
Write-Host ($revision -join "`n") -ForegroundColor Green

Write-Host "`n=== 4/8 PRUEBA DE INTEGRACION NEON (EMPRESAS TEMPORALES) ===" -ForegroundColor Cyan
$previousFlag = [Environment]::GetEnvironmentVariable('NEXO_ALLOW_RIA_SMOKE','Process')
try {
    $env:NEXO_ALLOW_RIA_SMOKE = '1'
    & $python -m scripts.smoke_ria006_018_postgres
    $smokeResult = $LASTEXITCODE
} finally {
    if ($null -eq $previousFlag) { Remove-Item Env:\NEXO_ALLOW_RIA_SMOKE -ErrorAction SilentlyContinue }
    else { $env:NEXO_ALLOW_RIA_SMOKE = $previousFlag }
}
if ($smokeResult -ne 0) { throw 'La prueba temporal de Neon falló' }

Set-Location $web
RunNative '5/8 PRUEBAS WEB' { npm run check }
RunNative '6/8 COMPILACION NEXT.JS' { npm run build }

Set-Location $mobile
RunNative '7/8 TYPESCRIPT MOVIL' { npm run check }
RunNative 'DEPENDENCIAS EXPO' { npx expo install --check }
RunNative '8/8 EXPO DOCTOR' { npx expo-doctor@latest }

Set-Location $root
Write-Host "`nCAMBIOS LOCALES:" -ForegroundColor Cyan
git status --short
Write-Host "`nRIA-006 A RIA-018: PRUEBAS TECNICAS FINALIZADAS" -ForegroundColor Green
Write-Host 'NO publiques aun: valida interfaz web/iPhone y luego revisa el commit.' -ForegroundColor Yellow
