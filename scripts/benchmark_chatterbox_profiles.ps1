param(
    [int]$RunsPerProfile = 5,
    [string]$VoiceCustom = "es_carlos",
    [string]$BaseUrl = "http://localhost:9000",
    [switch]$DoNotApplyBest
)

$ErrorActionPreference = "Stop"

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content -Path $Path
    }

    if ($lines -match "^$Key=") {
        $lines = $lines -replace "^$Key=.*$", "$Key=$Value"
    } else {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) { return $null }
    $match = Get-Content -Path $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $match) { return $null }
    return $match.Substring($Key.Length + 1)
}

function Wait-ChatterboxHealthy {
    param([int]$TimeoutSeconds = 600)
    $started = Get-Date
    while ($true) {
        $status = docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" tts-chatterbox 2>$null
        if ($LASTEXITCODE -eq 0 -and ($status -eq "healthy" -or $status -eq "running")) {
            try {
                Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5 | Out-Null
                return
            } catch {
            }
        }
        if (((Get-Date) - $started).TotalSeconds -gt $TimeoutSeconds) {
            throw "Timeout esperando a tts-chatterbox healthy/running (ultimo estado: $status)"
        }
        Start-Sleep -Seconds 2
    }
}

function Invoke-Warmup {
    param(
        [string]$BaseUrl,
        [string]$VoiceMode,
        [string]$VoiceCustom
    )

    $voice = if ($VoiceMode -eq "custom") { $VoiceCustom } else { "default" }
    $payload = @{
        model = "tts-1"
        input = "Prueba de calentamiento para medir latencia de Chatterbox."
        engine = "chatterbox"
        lang_code = "es"
        voice = $voice
        response_format = "mp3"
    } | ConvertTo-Json -Depth 6

    $tmp = Join-Path $env:TEMP "chatterbox_warmup_$VoiceMode.mp3"
    $deadline = (Get-Date).AddMinutes(10)
    while ($true) {
        try {
            Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/v1/audio/speech" -Method Post -ContentType "application/json" -Body $payload -OutFile $tmp | Out-Null
            return
        } catch {
            if ((Get-Date) -gt $deadline) {
                throw "Warmup fallo para voice_mode=$VoiceMode tras varios reintentos: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds 4
        }
    }
}

function Invoke-ProfileRun {
    param(
        [string]$RepoRoot,
        [string]$BaseUrl,
        [string]$VoiceMode,
        [string]$VoiceCustom,
        [string]$ProfileName,
        [int]$RunIndex
    )

    $outputDir = "benchmark/outputs/chatterbox_matrix/$ProfileName/$VoiceMode/run_$RunIndex"
    $reportDir = "benchmark/reports/chatterbox_matrix/$ProfileName/$VoiceMode/run_$RunIndex"
    $outputDirAbs = Join-Path $RepoRoot $outputDir
    $reportDirAbs = Join-Path $RepoRoot $reportDir
    New-Item -Path $outputDirAbs -ItemType Directory -Force | Out-Null
    New-Item -Path $reportDirAbs -ItemType Directory -Force | Out-Null

    $args = @(
        ".\benchmark\run_benchmark.py",
        "--base-url", $BaseUrl,
        "--engines", "chatterbox",
        "--lang-code", "es",
        "--corpus", "benchmark/corpus_es.txt",
        "--output-dir", $outputDir,
        "--report-dir", $reportDir
    )
    if ($VoiceMode -eq "custom") {
        $args += @("--voice-chatterbox", $VoiceCustom, "--chatterbox-voice-mode", "custom")
    } else {
        $args += @("--chatterbox-voice-mode", "default")
    }

    & python @args
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark fallo para perfil=$ProfileName voice=$VoiceMode run=$RunIndex"
    }

    $rawCsv = Join-Path $reportDirAbs "benchmark_raw.csv"
    $row = Import-Csv -Path $rawCsv | Where-Object { $_.engine -eq "chatterbox" } | Select-Object -First 1
    if (-not $row) {
        throw "No se encontro fila chatterbox en $rawCsv"
    }

    [pscustomobject]@{
        profile = $ProfileName
        voice_mode = $VoiceMode
        run_index = $RunIndex
        chars = [int]$row.chars
        latency_ms = [double]$row.latency_ms
        ttfa_ms = [double]$row.ttfa_ms
        audio_seconds = [double]$row.audio_seconds
        rtf = [double]$row.rtf
        chars_per_sec = [double]$row.chars_per_sec
        bytes = [int]$row.bytes
        chunks = [int]$row.chunks
        status = $row.status
        error = $row.error
        audio_file = $row.audio_file
    }
}

function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$P
    )
    if (-not $Values -or $Values.Count -eq 0) { return [double]::NaN }
    $sorted = $Values | Sort-Object
    $idx = [math]::Ceiling($P * $sorted.Count) - 1
    if ($idx -lt 0) { $idx = 0 }
    if ($idx -ge $sorted.Count) { $idx = $sorted.Count - 1 }
    return [double]$sorted[$idx]
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$envPath = Join-Path $repoRoot ".env"
if (-not (Test-Path $envPath)) {
    throw "No existe .env en $repoRoot"
}

$profiles = @(
    @{
        name = "A_base_defaults"
        vars = @{
            CHATTERBOX_USE_MULTILINGUAL_MODEL = "true"
            CHATTERBOX_EXAGGERATION = "0.5"
            CHATTERBOX_CFG_WEIGHT = "0.5"
            CHATTERBOX_TEMPERATURE = "0.8"
            CHATTERBOX_MAX_CHUNK_LENGTH = "280"
            CHATTERBOX_MEMORY_CLEANUP_INTERVAL = "5"
            CHATTERBOX_CUDA_CACHE_CLEAR_INTERVAL = "3"
            CHATTERBOX_ENABLE_MEMORY_MONITORING = "true"
        }
    },
    @{
        name = "B_balance"
        vars = @{
            CHATTERBOX_USE_MULTILINGUAL_MODEL = "true"
            CHATTERBOX_EXAGGERATION = "0.4"
            CHATTERBOX_CFG_WEIGHT = "0.3"
            CHATTERBOX_TEMPERATURE = "0.6"
            CHATTERBOX_MAX_CHUNK_LENGTH = "280"
            CHATTERBOX_MEMORY_CLEANUP_INTERVAL = "20"
            CHATTERBOX_CUDA_CACHE_CLEAR_INTERVAL = "20"
            CHATTERBOX_ENABLE_MEMORY_MONITORING = "false"
        }
    },
    @{
        name = "C_aggressive"
        vars = @{
            CHATTERBOX_USE_MULTILINGUAL_MODEL = "true"
            CHATTERBOX_EXAGGERATION = "0.35"
            CHATTERBOX_CFG_WEIGHT = "0.25"
            CHATTERBOX_TEMPERATURE = "0.5"
            CHATTERBOX_MAX_CHUNK_LENGTH = "280"
            CHATTERBOX_MEMORY_CLEANUP_INTERVAL = "20"
            CHATTERBOX_CUDA_CACHE_CLEAR_INTERVAL = "20"
            CHATTERBOX_ENABLE_MEMORY_MONITORING = "false"
        }
    }
)

$voiceModes = @("custom", "default")
$allResults = New-Object System.Collections.Generic.List[object]

Write-Host "Iniciando matrix Chatterbox: $RunsPerProfile corridas por perfil y modo de voz..."

foreach ($profile in $profiles) {
    $profileName = $profile.name
    Write-Host "==> Aplicando perfil $profileName"
    foreach ($entry in $profile.vars.GetEnumerator()) {
        Set-EnvValue -Path $envPath -Key $entry.Key -Value $entry.Value
    }

    docker compose up -d --force-recreate chatterbox | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose fallo recreando chatterbox para perfil $profileName"
    }
    Wait-ChatterboxHealthy

    foreach ($voiceMode in $voiceModes) {
        Write-Host "  -> Warmup $voiceMode"
        Invoke-Warmup -BaseUrl $BaseUrl -VoiceMode $voiceMode -VoiceCustom $VoiceCustom
    }

    foreach ($voiceMode in $voiceModes) {
        for ($run = 1; $run -le $RunsPerProfile; $run++) {
            Write-Host "  -> Run perfil=$profileName voice=$voiceMode n=$run/$RunsPerProfile"
            $result = Invoke-ProfileRun -RepoRoot $repoRoot -BaseUrl $BaseUrl -VoiceMode $voiceMode -VoiceCustom $VoiceCustom -ProfileName $profileName -RunIndex $run
            $allResults.Add($result) | Out-Null
        }
    }
}

$matrixDir = Join-Path $repoRoot "benchmark/reports/chatterbox_matrix"
New-Item -Path $matrixDir -ItemType Directory -Force | Out-Null
$rawOut = Join-Path $matrixDir "matrix_raw.csv"
$summaryOut = Join-Path $matrixDir "matrix_summary.csv"
$mdOut = Join-Path $matrixDir "summary.md"

$allResults | Export-Csv -Path $rawOut -NoTypeInformation -Encoding UTF8

$summary = foreach ($group in ($allResults | Group-Object -Property profile, voice_mode)) {
    $valsLatency = @($group.Group | ForEach-Object { [double]$_.latency_ms })
    $valsTtfa = @($group.Group | ForEach-Object { [double]$_.ttfa_ms })
    $valsRtf = @($group.Group | ForEach-Object { [double]$_.rtf })
    $valsTh = @($group.Group | ForEach-Object { [double]$_.chars_per_sec })

    [pscustomobject]@{
        profile = $group.Group[0].profile
        voice_mode = $group.Group[0].voice_mode
        runs = $group.Count
        avg_latency_ms = [math]::Round(($valsLatency | Measure-Object -Average).Average, 2)
        p95_latency_ms = [math]::Round((Get-Percentile -Values $valsLatency -P 0.95), 2)
        avg_ttfa_ms = [math]::Round(($valsTtfa | Measure-Object -Average).Average, 2)
        avg_rtf = [math]::Round(($valsRtf | Measure-Object -Average).Average, 4)
        avg_chars_per_sec = [math]::Round(($valsTh | Measure-Object -Average).Average, 2)
    }
}

$summary = $summary | Sort-Object -Property avg_latency_ms
$summary | Export-Csv -Path $summaryOut -NoTypeInformation -Encoding UTF8

$mdLines = @()
$mdLines += "# Chatterbox Profile Matrix Summary"
$mdLines += ""
$mdLines += "| profile | voice_mode | runs | avg_latency_ms | p95_latency_ms | avg_ttfa_ms | avg_rtf | avg_chars_per_sec |"
$mdLines += "|---|---:|---:|---:|---:|---:|---:|---:|"
foreach ($row in $summary) {
    $mdLines += "| $($row.profile) | $($row.voice_mode) | $($row.runs) | $($row.avg_latency_ms) | $($row.p95_latency_ms) | $($row.avg_ttfa_ms) | $($row.avg_rtf) | $($row.avg_chars_per_sec) |"
}
Set-Content -Path $mdOut -Value $mdLines -Encoding UTF8

$bestCustom = $summary | Where-Object { $_.voice_mode -eq "custom" } | Sort-Object -Property avg_latency_ms | Select-Object -First 1
if (-not $bestCustom) {
    throw "No se pudo determinar best profile para voice_mode=custom"
}

$bestProfile = $profiles | Where-Object { $_.name -eq $bestCustom.profile } | Select-Object -First 1
if (-not $bestProfile) {
    throw "No se encontro definicion de perfil ganador: $($bestCustom.profile)"
}

if (-not $DoNotApplyBest) {
    Write-Host "Aplicando perfil ganador para custom voice: $($bestCustom.profile)"
    foreach ($entry in $bestProfile.vars.GetEnumerator()) {
        Set-EnvValue -Path $envPath -Key $entry.Key -Value $entry.Value
    }
    docker compose up -d --force-recreate chatterbox | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo aplicar perfil ganador en chatterbox"
    }
    Wait-ChatterboxHealthy
}

Write-Host ""
Write-Host "Listo."
Write-Host "Raw matrix: $rawOut"
Write-Host "Summary CSV: $summaryOut"
Write-Host "Summary MD: $mdOut"
Write-Host "Best custom profile: $($bestCustom.profile) (avg_latency_ms=$($bestCustom.avg_latency_ms))"
