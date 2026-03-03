# Tray TTS Qt (PySide6)

Implementacion de bandeja + popup visual usando PySide6.

## Caracteristicas

- Tray nativo con `QSystemTrayIcon`.
- Hotkeys globales:
  - `Ctrl+Shift+Y` (principal)
  - `Ctrl+Alt+Y` (fallback)
- Popup visual con:
  - Estado de reproduccion
  - `Stop`, `Pause`, `Play`
  - Barra de progreso con duracion total
  - Seek (adelantar/atrasar)
  - Slider de velocidad (`0.60x` a `2.00x`)
  - Selector de voz
- Persistencia de velocidad en `config.json`.
- TTS contra Kokoro (`/v1/audio/speech`) con `response_format=wav`.

## Arranque

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_tray_tts.ps1
```

## Notas

- Esta version reemplaza `winsound` por `QMediaPlayer` para soportar barra de duracion y seek real.
- Si el endpoint Kokoro no responde, el estado pasa a error y se notifica desde tray.
