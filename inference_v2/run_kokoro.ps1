param(
    [string]$VenvPath = "..\.venv_v2"
)

$ScriptDir = $PSScriptRoot
$VenvRoot = Join-Path $ScriptDir $VenvPath
$Uvicorn = Join-Path $VenvRoot "Scripts\uvicorn.exe"

Write-Host "Iniciando Kokoro Fast Inference v2 (OpenAI-Compatible) en puerto 8882 (Todas las interfaces)..."
if (-not (Test-Path $Uvicorn)) {
    Write-Warning "No se encontro uvicorn en '$Uvicorn'. Probando fallback con python -m uvicorn."
}

$KokoroDir = Join-Path $ScriptDir "kokoro"
Push-Location $KokoroDir
try {
    if (Test-Path $Uvicorn) {
        & $Uvicorn server:app --host 0.0.0.0 --port 8882
    }
    else {
        & py -3 -m uvicorn server:app --host 0.0.0.0 --port 8882
    }
}
finally {
    Pop-Location
}
