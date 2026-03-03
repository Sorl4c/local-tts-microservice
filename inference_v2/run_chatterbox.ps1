param(
    [string]$VenvPath = "..\.venv_v2"
)

$Uvicorn = "$VenvPath\Scripts\uvicorn.exe"

Write-Host "Iniciando Chatterbox Turbo v2 en puerto 8002..."
cd .\chatterbox
& $Uvicorn server:app --host 0.0.0.0 --port 8002
