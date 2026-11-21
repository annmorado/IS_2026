# NEXO AI — RIA-001..005: verify after extracting ZIP from the repository root.
# Run on a trusted network, only after backing up/branching Neon.
$ErrorActionPreference = 'Stop'
$root = Join-Path $HOME 'Projects\nexo-ai'
$api = Join-Path $root 'services\api'
$web = Join-Path $root 'apps\web'
$mobile = Join-Path $root 'apps\mobile'
Set-Location $root
if ((git branch --show-current) -ne 'main') { throw 'Se requiere rama main' }
if ((git rev-parse --short=7 HEAD) -ne '1389fe1') { throw 'El punto base esperado es 1389fe1; revisar version' }

Write-Host "`n1 / 7 PRUEBAS BACKEND" -ForegroundColor Cyan
Set-Location $api
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Pruebas backend fallaron' }

Write-Host "`n2 / 7 EVALUACION 50 EJEMPLOS" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m scripts.evaluate_ria002
if ($LASTEXITCODE -ne 0) { throw 'Evaluacion RIA-002 fallida' }

Write-Host "`n3 / 7 MIGRACION POSTGRES NEON" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migracion fallida' }
$current = & .\.venv\Scripts\python.exe -m alembic -c alembic.ini current
if ($LASTEXITCODE -ne 0 -or ($current -join ' ') -notmatch 'ai_0017 \(head\)') {
    throw ('Head inesperado: ' + ($current -join ' '))
}
Write-Host ($current -join ' ') -ForegroundColor Green

Write-Host "`n4 / 7 SMOKE NEON (DOS EMPRESAS TEMPORALES)" -ForegroundColor Cyan
$env:NEXO_ALLOW_AI_SMOKE = '1'
try {
    & .\.venv\Scripts\python.exe -m scripts.smoke_ria001_005_postgres
    if ($LASTEXITCODE -ne 0) { throw 'Fallo smoke de Neon' }
} finally {
    Remove-Item Env:\NEXO_ALLOW_AI_SMOKE -ErrorAction SilentlyContinue
}

Write-Host "`n5 / 7 WEB" -ForegroundColor Cyan
Set-Location $web
npm run check
if ($LASTEXITCODE -ne 0) { throw 'Tests web fallaron' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Build web fallo' }

Write-Host "`n6 / 7 EXPO" -ForegroundColor Cyan
Set-Location $mobile
npm run check
if ($LASTEXITCODE -ne 0) { throw 'TypeScript Expo fallo' }
npx expo install --check
if ($LASTEXITCODE -ne 0) { throw 'Dependencias Expo no coinciden' }
npx expo-doctor@latest
if ($LASTEXITCODE -ne 0) { throw 'Expo Doctor fallo' }

Write-Host "`n7 / 7 ESTADO DE ARCHIVOS" -ForegroundColor Cyan
Set-Location $root
git status --short
Write-Host "`nRIA-001..RIA-005: PRUEBAS TECNICAS COMPLETADAS" -ForegroundColor Green
Write-Host 'Todavia faltan prueba de Whisper real (optativa), web, iPhone y confirmacion antes de publicar.' -ForegroundColor Yellow
