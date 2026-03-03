param(
    [string]$VenvPath = "..\.venv_v2"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path "$VenvPath\Scripts\python.exe")) {
    Write-Host "Creando entorno virtual en $VenvPath..."
    py -3.12 -m venv $VenvPath
}

$Pip = "$VenvPath\Scripts\pip.exe"

Write-Host "Instalando PyTorch para Blackwell (cu128)..."
& $Pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "Instalando dependencias base (misaki, soundfile, etc)..."
& $Pip install --extra-index-url https://pypi.org/simple misaki[en,es] soundfile fastapi uvicorn pydantic

Write-Host "Instalando Kokoro..."
& $Pip install -r ./kokoro/requirements.txt

Write-Host "Instalando Chatterbox..."
& $Pip install -r ./chatterbox/requirements.txt

Write-Host "¡Entorno v2 listo!"