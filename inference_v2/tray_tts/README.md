# Tray TTS - README Tecnico

App de bandeja para Windows que permite leer texto del portapapeles usando Kokoro TTS.

## Objetivo

Proveer utilidad diaria con un flujo simple:

1. Copiar texto.
2. Pulsar hotkey global.
3. Escuchar audio inmediatamente.

## Endpoint objetivo

- `http://192.168.37.1:8882/v1`

Se asume que este endpoint es compartido con otros servicios.

## Caracteristicas implementadas

- Hotkeys globales:
  - `Ctrl+Shift+Y` (principal)
  - `Ctrl+Alt+Y` (fallback)
- Menu tray con:
  - Leer portapapeles
  - Probar lectura ahora
  - Probar audio local
  - Diagnostico endpoint Kokoro
  - Iniciar Kokoro
  - Parar Kokoro (con confirmacion fuerte)
  - Selector de voz (`ef_dora`, `em_alex`, `em_santa`)
- Lectura de portapapeles con fallback y reintentos.
- Reproduccion WAV mediante archivo temporal.
- Logs operativos.

## Estructura

- `app.py`: logica principal.
- `requirements.txt`: dependencias del modulo.
- `../run_tray_tts.ps1`: script de arranque.
- `tray_tts.log`: log runtime.
- `tmp_audio/`: archivos temporales de audio.

## Arranque

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_tray_tts.ps1
```

## Flujo interno resumido

1. Se inicia `pystray` con icono y menu.
2. Se crea listener Win32 de hotkeys (`RegisterHotKey`).
3. Hotkey dispara lectura de clipboard.
4. Se envia request TTS (`/v1/audio/speech` con `response_format=wav`).
5. Se guarda WAV en `tmp_audio/` y se reproduce con `winsound`.
6. Se actualiza estado y log.

## Confirmacion fuerte al parar Kokoro

Al elegir `Parar Kokoro`, aparece advertencia explicita:

- Detenera el servicio compartido en `192.168.37.1:8882`.
- Puede impactar otros clientes/servicios que dependan de ese endpoint.

## Troubleshooting

### 1) "Error de TTS, revisa estado del servicio"

Comprobar:
- Menu `Diagnostico: endpoint Kokoro`.
- Logs en `tray_tts.log`.
- Si hay 200 en POST pero no se oye audio, probar `Probar audio local`.

### 2) Hotkey no responde

Comprobar:
- Estado `Hotkey=on` en el texto del menu.
- Probar hotkey fallback `Ctrl+Alt+Y`.
- Reabrir la app tray.

### 3) Lee texto previo en vez de seleccion actual

Caso conocido:
- Si se pulsa hotkey justo tras seleccionar/copiar, puede capturar valor anterior.
- Hay mitigacion con delay y reintentos, pero queda pendiente ajuste UX fino.

## Logs

Ruta:
- `C:\local\microservicios\local-tts-service\inference_v2\tray_tts\tray_tts.log`

Buscar en log:
- `Hotkeys registered via RegisterHotKey`
- `HTTP Request: POST ... /v1/audio/speech`
- `TTS request/playback failed`

## Pendiente para proxima sesion (UX)

- Mejor flujo "seleccionar y leer" sin depender de clipboard manual.
- Ajustes de feedback visual/sonoro.
- Opciones de configuracion persistente (voz/hotkey/volumen).
