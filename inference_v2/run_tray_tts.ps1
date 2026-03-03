param(
    [string]$VenvPath = "..\.venv_v2"
)

$ScriptDir = $PSScriptRoot
$VenvRoot = Join-Path $ScriptDir $VenvPath
$Python = Join-Path $VenvRoot "Scripts\python.exe"
$Pip = Join-Path $VenvRoot "Scripts\pip.exe"
$Req = Join-Path $ScriptDir "tray_tts\requirements.txt"
$App = Join-Path $ScriptDir "tray_tts\app.py"

if (-not (Test-Path $Python)) {
    Write-Error "No se encontro python en '$Python'. Revisa .venv_v2."
    exit 1
}

if (Test-Path $Pip) {
    Write-Host "Instalando dependencias de tray_tts..."
    & $Pip install -r $Req
}

Write-Host "Iniciando Kokoro Tray TTS..."
& $Python $App
