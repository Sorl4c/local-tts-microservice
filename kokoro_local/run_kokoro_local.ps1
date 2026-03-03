param(
    [string]$VenvPath = ".venv312",
    [string]$RepoDir = "kokoro_local\Kokoro-FastAPI",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8881,
    [switch]$SkipSetup
)

$ErrorActionPreference = "Stop"

function Invoke-VenvPython {
    param([string]$ArgsLine)
    & "$VenvPath\Scripts\python.exe" -c $ArgsLine
}

if (-not (Test-Path "$VenvPath\Scripts\python.exe")) {
    py -3.12 -m venv $VenvPath
}

if (-not $SkipSetup) {
    & "$VenvPath\Scripts\python.exe" -m pip install --upgrade pip
    & "$VenvPath\Scripts\python.exe" -m pip install -r "kokoro_local\requirements.txt"

    if (-not (Test-Path $RepoDir)) {
        git clone https://github.com/remsky/Kokoro-FastAPI.git $RepoDir
    }

    Push-Location $RepoDir
    try {
        if (Test-Path "requirements.txt") {
            & "..\..\$VenvPath\Scripts\python.exe" -m pip install -r requirements.txt
        } elseif (Test-Path "pyproject.toml") {
            & "..\..\$VenvPath\Scripts\python.exe" -m pip install -e .
        }
    }
    finally {
        Pop-Location
    }
}

& "$VenvPath\Scripts\python.exe" "kokoro_local\verify_kokoro_gpu.py"
if ($LASTEXITCODE -ne 0) {
    throw "CUDA no detectada correctamente en el entorno local."
}

Push-Location $RepoDir
try {
    $env:HOST = $BindHost
    $env:PORT = "$Port"
    $env:DEVICE = "cuda"

    if (Test-Path "app.py") {
        & "..\..\$VenvPath\Scripts\python.exe" app.py
    } elseif (Test-Path "main.py") {
        & "..\..\$VenvPath\Scripts\python.exe" main.py
    } else {
        throw "No se encontro entrypoint esperado en Kokoro-FastAPI (app.py/main.py)."
    }
}
finally {
    Pop-Location
}
