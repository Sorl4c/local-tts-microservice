# Start Here - Tray TTS (Windows)

Esta guia resume como arrancar y usar la implementacion actual de lectura por portapapeles con hotkeys globales.

## 1) Requisitos

- Windows 10/11.
- Entorno virtual `C:\local\microservicios\local-tts-service\.venv_v2`.
- Endpoint Kokoro operativo en:
  - `http://192.168.37.1:8882/v1`

## 2) Arranque rapido

```powershell
cd C:\local\microservicios\local-tts-service\inference_v2
.\run_tray_tts.ps1
```

Al arrancar, aparecera un icono en la bandeja del sistema (al lado del reloj).

## 3) Flujo basico de uso

1. Clic derecho en el icono tray.
2. Opcion `Iniciar Kokoro` (si no esta ya activo).
3. Copia texto al portapapeles.
4. Pulsa hotkey global:
   - `Ctrl+Shift+Y` (principal)
   - `Ctrl+Alt+Y` (fallback)
5. Deberia reproducirse audio directamente.
6. Aparecera popup `Kokoro Audio` con controles:
   - `Stop`
   - `Pause`
   - `Play`
   - slider de velocidad
   - combo de voz

## 4) Pruebas recomendadas

1. `Probar audio local`: valida que el reproductor de audio de la app funciona.
2. `Diagnostico: endpoint Kokoro`: valida conectividad con el servicio TTS.
3. `Probar lectura ahora`: fuerza lectura del portapapeles sin usar hotkey.
4. `Mostrar control de audio`: abre popup manualmente.

## 5) Nota de comportamiento Pause/Play

- `Pause` detiene audio actual y deja estado pausado.
- `Play` relanza lectura del ultimo texto desde el inicio.
- No hay reanudacion sample-perfect en esta iteracion (limitacion de `winsound`).

## 6) Cierre

- Opcion `Salir` desde el menu del tray.

## 7) Nota sobre UX pendiente

- Si seleccionas texto y pulsas hotkey "demasiado rapido", puede tomar el valor previo del portapapeles.
- En esta version hay mitigacion (delay + reintentos), pero queda pendiente un ajuste fino de experiencia para la siguiente sesion.
