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
- Popup visual nativo (Tkinter) al lanzar lectura por hotkey:
  - Estado de lectura
  - Boton `Stop`
  - Botones `Pause` y `Play`
  - Combo de voz (`ef_dora`, `em_alex`, `em_santa`)
  - Slider de velocidad `0.60x` a `2.00x` (paso `0.05`)
- Menu tray con:
  - Leer portapapeles
  - Probar lectura ahora
  - Detener audio
  - Pausar audio
  - Reanudar audio
  - Mostrar control de audio
  - Probar audio local
  - Diagnostico endpoint Kokoro
  - Iniciar Kokoro
  - Parar Kokoro (con confirmacion fuerte)
  - Selector de voz (`ef_dora`, `em_alex`, `em_santa`)
- Lectura de portapapeles con fallback y reintentos.
- Cambio de velocidad durante lectura: corta audio y relanza lectura completa con nueva velocidad.
- Velocidad persistente en `config.json`.
- Reproduccion WAV mediante archivo temporal.
- Logs operativos.

## Estructura

- `app.py`: logica principal.
- `requirements.txt`: dependencias del modulo.
- `../run_tray_tts.ps1`: script de arranque.
- `config.json`: configuracion local (`playback_speed`).
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
3. Hotkey abre popup visual de control y dispara lectura de clipboard.
4. Se envia request TTS (`/v1/audio/speech` con `response_format=wav` y `speed`).
5. Se guarda WAV en `tmp_audio/` y se reproduce con `winsound`.
6. Si cambias `speed` durante lectura, se detiene y relanza el texto completo.
7. Si cambias voz durante lectura, se relanza con la nueva voz.
8. `Pause` detiene audio actual y `Play` relanza el texto actual.
9. Se actualiza estado, popup, icono y log.

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

### 4) No aparece el popup visual

Comprobar:
- Iniciar lectura usando hotkey (`Ctrl+Shift+Y` o `Ctrl+Alt+Y`).
- Abrir popup manual con menu `Mostrar control de audio`.
- Revisar log por errores de Tkinter.

## Logs

Ruta:
- `C:\local\microservicios\local-tts-service\inference_v2\tray_tts\tray_tts.log`

Buscar en log:
- `Hotkeys registered via RegisterHotKey`
- `HTTP Request: POST ... /v1/audio/speech`
- `TTS request/playback failed`
