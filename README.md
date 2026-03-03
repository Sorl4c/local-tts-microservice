# Local TTS Service - V2 (Bare Metal / Inferencia Pura)

Este proyecto implementa un microservicio de Text-to-Speech (TTS) **ultra-rÃ¡pido** diseÃ±ado especÃ­ficamente para hardware NVIDIA moderno (RTX 5070 Ti - Arquitectura Blackwell `sm_120`), minimizando la latencia para interacciones de voz en tiempo real con agentes y bots de Telegram.

## Estado de la Arquitectura (V2)

La arquitectura actual prescinde del entorno Docker (`wsl2`) para eliminar el overhead de red y virtualizaciÃ³n que penalizaba los Tiempos de Respuesta (TTFA). 

Hemos desarrollado un servidor FastAPI nativo ("Bare Metal") 100% compatible con la API de OpenAI, permitiendo tiempos de respuesta de **~200 ms** para frases cortas, haciÃ©ndolo indistinguible de la interacciÃ³n humana.

### Motores disponibles:
- **Kokoro (V2 Fast):** Principal motor recomendado para chat en tiempo real. Soporta streaming interno y generaciÃ³n atÃ³mica de audio en milisegundos.
- **Chatterbox-Turbo (WIP):** Ideal en el futuro para audiolibros y tareas de clonaciÃ³n de voz asÃ­ncronas.

---

## ðŸš€ Arranque RÃ¡pido (Kokoro OpenAI-Compatible)

El servidor utiliza un entorno virtual dedicado con binarios de PyTorch (`cu128`) compilados especÃ­ficamente para tu arquitectura Blackwell.

**1. Activar el servidor**
Abre una terminal de PowerShell y ejecuta:
```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_kokoro.ps1
```
*(El servidor quedarÃ¡ escuchando en `http://127.0.0.1:8882`)*

**2. InstalaciÃ³n inicial (Solo si es la primera vez)**
Si aÃºn no tienes el entorno creado, ejecuta antes: `.\setup_env.ps1`

---

## ðŸ¤– IntegraciÃ³n con Second Brain (Telegram / OpenAI SDK)

Dado que el microservicio expone exactamente la misma API que OpenAI, puedes usar la librerÃ­a oficial de Python de `openai` en tu bot de Telegram sin usar librerÃ­as raras ni hacer peticiones manuales.

**CÃ³digo de ejemplo (Python):**

```python
from openai import OpenAI

# 1. Apunta el cliente al microservicio local
client = OpenAI(
    base_url="http://127.0.0.1:8882/v1",
    api_key="sk-local-not-needed" # Ignorado localmente
)

# 2. Solicita el audio
response = client.audio.speech.create(
    model="tts-1",           # Ignorado, pero requerido por el SDK
    voice="ef_dora",         # Voz en espaÃ±ol de Kokoro
    input="Este es tu Second Brain hablÃ¡ndote en tiempo real con latencia de 200 milisegundos.",
    response_format="opus"   # Formato nativo comprimido Ã³ptimo para notas de voz en Telegram
)

# 3. Guarda o envÃ­a directamente a la API de Telegram
with open("respuesta.ogg", "wb") as f:
    f.write(response.content)
```

### Formatos Soportados (`response_format`)
El servidor gestiona internamente la conversiÃ³n de audio en la memoria RAM, soportando:
- `opus` (Se guarda en un contenedor OGG, ideal para Telegram).
- `mp3` (Por defecto).
- `wav` (Calidad PCM_16 en crudo).
- `flac`.

---

## ðŸ“Š Benchmarks y Rendimiento

El repositorio incluye un script para probar la velocidad pura (`ttfa_ms`, latencia y throughput) de tu grÃ¡fica enviÃ¡ndole peticiones masivas.

Para ejecutar la prueba automatizada sobre tu corpus de espaÃ±ol:
```powershell
cd C:\local\microservicios\local-tts-service
.\.venv_v2\Scripts\python.exe benchmark\run_benchmark_v2.py
```
*Los audios de prueba generados se guardarÃ¡n en `benchmark/outputs_v2` y los reportes en `benchmark/reports_v2/summary_v2.md`.*

---
---

## ðŸ›‘ Docker y Gateway Antiguo (Legacy)

*La antigua implementaciÃ³n basada en contenedores Docker y un Gateway enrutador sigue existiendo en el cÃ³digo fuente por razones histÃ³ricas, pero **estÃ¡ deprecada** debido al lÃ­mite de rendimiento (aumentaba la latencia de ~200ms a >2.000ms en Windows).*

Si necesitas arrancar la estructura antigua por compatibilidad:

```powershell
cd C:\local\microservicios\local-tts-service
docker compose up -d chatterbox gateway kokoro
```
*El viejo gateway escuchaba en el puerto `9000` (`http://localhost:9000/v1/audio/speech`).*
## Web Experiment (HTML + Medicion de Latencia)

Se incluye un experimento web minimo para Texto -> Audio con Kokoro V2.`r`n`r`n- Escribes texto en la interfaz.`r`n- Generas audio desde Kokoro.`r`n- Reproduces con play directamente en el navegador.`r`n`r`n### Arranque

En una terminal:
```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_kokoro.ps1
```

En otra terminal:
```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_web_experiment.ps1
```

Abrir en navegador:
- `http://127.0.0.1:8890`

### Variables usadas por el experimento

- Endpoint fijo en backend: `http://192.168.37.1:8882/v1`

El backend del experimento carga automaticamente el `.env` de la raiz del repo.


## Tray App Windows (Ctrl+Shift+Y)

Se incluye una app de bandeja para leer el portapapeles con Kokoro:

- Hotkey global: `Ctrl+Shift+Y`
- Voz seleccionable: `ef_dora`, `em_alex`, `em_santa`
- Control operativo desde tray: iniciar/parar Kokoro
- Confirmacion fuerte al parar (impacta servicios que usan `192.168.37.1:8882`)

### Arranque del tray

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_tray_tts.ps1
```

Notas:
- El endpoint usado por el tray es `http://192.168.37.1:8882/v1`.
- Si la hotkey global no se captura, abre PowerShell como administrador.
