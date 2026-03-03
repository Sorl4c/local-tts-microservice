# Plan de accion - Proxima sesion (otra terminal)

Objetivo: validar rendimiento real **sin wrapper Docker API** usando pipelines directos (official-like) para:

- Kokoro (espanol, baja latencia)
- Chatterbox Multilingual (espanol, calidad)

Este plan esta pensado para ejecutarse en otra sesion, de forma reproducible y con checkpoints.

---

## 0) Criterios de exito

Al terminar, debemos tener:

1. Dos servidores locales directos levantados:
   - Kokoro en `http://127.0.0.1:8882`
   - Chatterbox en `http://127.0.0.1:8002`
2. Medicion comparativa de latencia/throughput en un mismo corpus.
3. Evidencia en archivos (logs + resumen) para decidir arquitectura final.

---

## 1) Pre-flight (5 min)

Abrir **Terminal 1** (PowerShell):

```powershell
cd C:\local\microservicios\local-tts-service
```

Verificar Python 3.12:

```powershell
py -3.12 --version
```

Verificar GPU visible:

```powershell
nvidia-smi
```

Si falla alguno de estos checks, parar aqui y corregir entorno.

---

## 2) Preparar entorno v2 (solo primera vez)

En **Terminal 1**:

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
powershell -ExecutionPolicy Bypass -File .\setup_env.ps1
```

Nota: este paso puede tardar varios minutos.

---

## 3) Ajuste minimo de Chatterbox para usar multilingual oficial (ANTES de arrancar)

Archivo a revisar/ajustar:

- `C:\local\microservicios\local-tts-service\inference_v2\chatterbox\server.py`

Objetivo del ajuste:

1. Cargar `ChatterboxMultilingualTTS` (no modelo base ingles).
2. Usar `language_id="es"` en `generate(...)`.
3. Mantener endpoint local `/v1/audio/speech` para benchmark.

Referencia oficial:

- https://github.com/resemble-ai/chatterbox

Comportamiento esperado tras ajuste:

- El health endpoint responde `200`.
- Una frase corta en espanol genera audio sin error.

---

## 4) Arranque de motores en terminales separadas

### 4.1 Terminal 2 - Kokoro

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
powershell -ExecutionPolicy Bypass -File .\run_kokoro.ps1
```

Esperado: uvicorn escuchando en `:8882`.

### 4.2 Terminal 3 - Chatterbox multilingual

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
powershell -ExecutionPolicy Bypass -File .\run_chatterbox.ps1
```

Esperado: uvicorn escuchando en `:8002`.

---

## 5) Health checks y smoke tests (Terminal 1)

### 5.1 Health

```powershell
Invoke-RestMethod http://127.0.0.1:8882/healthz
Invoke-RestMethod http://127.0.0.1:8002/healthz
```

### 5.2 Frase corta de prueba

```powershell
$text = "Hola, esta es una prueba de latencia."

# Kokoro
$kBody = @{ text=$text; voice="ef_dora"; speed=1.0 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8882/v1/audio/speech" -Method Post -ContentType "application/json" -Body $kBody -OutFile ".\benchmark\outputs\kokoro_v2_smoke.wav"

# Chatterbox
$cBody = @{ text=$text; language="es" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8002/v1/audio/speech" -Method Post -ContentType "application/json" -Body $cBody -OutFile ".\benchmark\outputs\chatterbox_v2_smoke.wav"
```

Si alguno falla, revisar logs en Terminal 2/3 antes de seguir.

---

## 6) Benchmark comparativo v2 (Terminal 1)

Ejecutar benchmark directo:

```powershell
cd C:\local\microservicios\local-tts-service
.\.venv_v2\Scripts\python.exe .\inference_v2\benchmark_v2.py | Tee-Object .\benchmark\reports\v2_benchmark_console.log
```

Guardar copia timestamp:

```powershell
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item .\benchmark\reports\v2_benchmark_console.log ".\benchmark\reports\v2_benchmark_$ts.log"
```

---

## 7) Prueba dirigida con texto real (Terminal 1)

```powershell
$text = @"
Senora Marina, esto es una prueba diciendo que Ori es un gato gordo y duerme mucho.
"@

# Kokoro timing
$kBody = @{ text=$text; voice="ef_dora"; speed=1.0 } | ConvertTo-Json
Measure-Command {
  Invoke-RestMethod -Uri "http://127.0.0.1:8882/v1/audio/speech" -Method Post -ContentType "application/json" -Body $kBody -OutFile ".\benchmark\outputs\kokoro_v2_real.wav"
}

# Chatterbox timing
$cBody = @{ text=$text; language="es" } | ConvertTo-Json
Measure-Command {
  Invoke-RestMethod -Uri "http://127.0.0.1:8002/v1/audio/speech" -Method Post -ContentType "application/json" -Body $cBody -OutFile ".\benchmark\outputs\chatterbox_v2_real.wav"
}
```

---

## 8) Consolidar resultados de la sesion

Crear resumen en nuevo markdown (mismo dia):

- `C:\local\microservicios\local-tts-service\benchmark\reports\SESSION_NEXT_v2_RESULTS.md`

Contenido minimo:

1. Versiones (torch, python, GPU driver).
2. Latencias promedio por engine.
3. TTFA aproximado.
4. Comentario de calidad subjetiva (1-5) para cada engine.
5. Decision propuesta:
   - Telegram: motor recomendado
   - Audiolibros: motor recomendado

---

## 9) Decision gate final

Tomar decision solo con evidencia de esta corrida directa:

1. Si Kokoro << Chatterbox en latencia y calidad aceptable:
   - Kokoro para flujo interactivo/Telegram.
2. Si Chatterbox mantiene calidad claramente superior y latencia aceptable:
   - Chatterbox para lotes/audiolibros.
3. Si Chatterbox sigue demasiado lento:
   - Mantenerlo solo para casos premium de calidad, no para tiempo real.

---

## 10) Riesgos conocidos

1. `run_chatterbox.ps1` puede arrancar con configuracion no alineada a multilingual si `server.py` no se ajusta.
2. Primera inferencia (cold start) siempre penaliza latencia; hacer warmup antes de medir.
3. Mezclar entornos (`.venv312`, `.venv_v2`) puede generar falsos fallos.

---

## 11) Orden recomendado de ejecucion (resumen rapido)

1. Terminal 1: `setup_env.ps1` (si hace falta).
2. Ajustar `inference_v2/chatterbox/server.py` a multilingual.
3. Terminal 2: `run_kokoro.ps1`.
4. Terminal 3: `run_chatterbox.ps1`.
5. Terminal 1: health + smoke.
6. Terminal 1: `benchmark_v2.py`.
7. Terminal 1: prueba con texto real + guardar resultados.

