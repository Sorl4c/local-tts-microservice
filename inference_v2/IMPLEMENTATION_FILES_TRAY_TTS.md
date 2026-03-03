# Implementacion Actual - Inventario de Ficheros

Este documento lista los ficheros creados/ajustados para la implementacion de:

- Web minima `Texto -> Audio`.
- App de bandeja (tray) con hotkeys globales y control de Kokoro.

## 1) Ficheros de bandeja (nueva implementacion principal)

### `inference_v2/tray_tts/app.py`

Archivo principal de la app tray.

Incluye:
- Registro de hotkeys globales via Win32 `RegisterHotKey`.
- Lectura de portapapeles con fallback.
- Llamada a endpoint Kokoro (`/v1/audio/speech`).
- Reproduccion de audio WAV temporal.
- Menu tray:
  - Leer portapapeles
  - Probar lectura
  - Probar audio local
  - Diagnostico endpoint
  - Iniciar/Parar Kokoro
  - Seleccion de voz
- Logging operativo en `tray_tts.log`.

### `inference_v2/tray_tts/requirements.txt`

Dependencias Python para la app tray:
- `httpx`
- `Pillow`
- `pyperclip`
- `pystray`

### `inference_v2/run_tray_tts.ps1`

Script de arranque para tray app.

Hace:
1. Resolucion de rutas con `$PSScriptRoot`.
2. Instalacion de dependencias de `tray_tts/requirements.txt`.
3. Arranque de `tray_tts/app.py`.

### Artefactos runtime (no codigo fuente)

- `inference_v2/tray_tts/tray_tts.log`: log operativo.
- `inference_v2/tray_tts/tmp_audio/*.wav`: audio temporal para reproduccion.

## 2) Ficheros web (experimento texto -> audio)

### `inference_v2/web_experiment/server.py`

Backend FastAPI simple:
- `GET /`
- `POST /api/tts`
- `GET /healthz`

Endpoint Kokoro configurado fijo a:
- `http://192.168.37.1:8882/v1`

### `inference_v2/web_experiment/index.html`

Interfaz web minima para:
- Introducir texto
- Elegir voz/formato/velocidad
- Generar y reproducir audio

### `inference_v2/run_web_experiment.ps1`

Script de arranque del web experiment.

## 3) Script de arranque Kokoro existente usado por la app

### `inference_v2/run_kokoro.ps1`

No es nuevo, pero es pieza clave porque la app tray lo usa para `Iniciar Kokoro`.

## 4) Documentacion nueva de esta sesion

- `inference_v2/START_HERE_TRAY_TTS.md`
- `inference_v2/IMPLEMENTATION_FILES_TRAY_TTS.md`
- `inference_v2/tray_tts/README.md`
