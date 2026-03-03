param(
    [string]$VenvPath = "..\.venv_v2",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8890
)

$ScriptDir = $PSScriptRoot
$VenvRoot = Join-Path $ScriptDir $VenvPath
$Uvicorn = Join-Path $VenvRoot "Scripts\uvicorn.exe"

if (-not (Test-Path $Uvicorn)) {
    Write-Warning "No se encontro uvicorn en '$Uvicorn'. Probando fallback con python -m uvicorn."
}

Write-Host "Iniciando Web Experiment en http://$BindHost`:$Port"
$WebDir = Join-Path $ScriptDir "web_experiment"
Push-Location $WebDir
try {
    if (Test-Path $Uvicorn) {
        & $Uvicorn server:app --host $BindHost --port $Port
    }
    else {
        & py -3 -m uvicorn server:app --host $BindHost --port $Port
    }
}
finally {
    Pop-Location
}
