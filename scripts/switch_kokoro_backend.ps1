param(
    [ValidateSet("local", "docker")]
    [string]$Mode = "local",
    [string]$EnvFile = ".env",
    [string]$LocalUrl = "http://host.docker.internal:8881",
    [string]$DockerUrl = "http://kokoro:8880"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "No existe $EnvFile"
}

$targetUrl = if ($Mode -eq "local") { $LocalUrl } else { $DockerUrl }
$lines = Get-Content $EnvFile

if ($lines -match "^KOKORO_URL=") {
    $lines = $lines -replace "^KOKORO_URL=.*$", "KOKORO_URL=$targetUrl"
} else {
    $lines += "KOKORO_URL=$targetUrl"
}

Set-Content -Path $EnvFile -Value $lines

docker compose up -d --force-recreate gateway
if ($Mode -eq "docker") {
    docker compose up -d kokoro
}

Write-Host "KOKORO_URL => $targetUrl"

