param(
    [string]$VoiceName = "es_carlos",
    [string]$Language = "es",
    [string]$VoiceFile
)

$ErrorActionPreference = "Stop"

if (-not $VoiceFile) {
    throw "Debes pasar -VoiceFile con ruta a un .ogg/.wav"
}
if (-not (Test-Path $VoiceFile)) {
    throw "No existe el archivo de voz: $VoiceFile"
}

$voicesResponse = Invoke-RestMethod -Uri "http://localhost:8000/voices" -Method GET
$existing = @($voicesResponse.voices) | Where-Object { $_.name -eq $VoiceName }

if (-not $existing) {
    & curl.exe -sS -X POST "http://localhost:8000/voices" `
        -F "voice_name=$VoiceName" `
        -F "language=$Language" `
        -F "voice_file=@$VoiceFile" | Out-Null
}

& curl.exe -sS -X POST "http://localhost:8000/voices/default" `
    -H "Content-Type: application/x-www-form-urlencoded" `
    -d "voice_name=$VoiceName" | Out-Null

$defaultVoice = Invoke-RestMethod -Uri "http://localhost:8000/voices/default" -Method GET
Write-Host "Default voice:" $defaultVoice.default_voice

