# Documentación de Sesión - Implementación TTS V2 (Bare Metal)

**Fecha:** 1 de Marzo de 2026
**Objetivo:** Crear un microservicio TTS de latencia ultrabaja para Telegram usando hardware Blackwell (RTX 5070 Ti) fuera de Docker y con compatibilidad total con la API de OpenAI.

## 📁 Ficheros Tocados y Creados

1. **`inference_v2/setup_env.ps1` (Nuevo):** Script para crear un entorno virtual e instalar PyTorch (`cu128`) asegurando la compatibilidad nativa con la arquitectura `sm_120` de Blackwell.
2. **`inference_v2/run_kokoro.ps1` (Nuevo):** Script de arranque del servidor Kokoro escuchando en `0.0.0.0:8882`.
3. **`inference_v2/kokoro/server.py` (Nuevo):** El microservicio núcleo. Implementa FastAPI con las rutas estándar de OpenAI (`/v1/audio/speech`, `/v1/models`). Incluye un **interceptor de voces** que fuerza `ef_dora` si recibe `alloy` u otras voces por defecto, y convierte el audio nativamente a OGG/Opus.
4. **`inference_v2/chatterbox/server.py` (Nuevo):** Microservicio paralelo para Chatterbox-Turbo.
5. **`benchmark/run_benchmark_v2.py` (Nuevo):** Script de pruebas de carga y medición de latencia adaptado a los nuevos endpoints, con salida separada en `outputs_v2/`.
6. **`README.md` (Modificado):** Se reescribió completamente para poner la arquitectura V2 como la principal, moviendo Docker a "Legacy", e incluyendo el código de integración de Python (OpenAI SDK).

## 🚀 Avances y Logros

- **Latencia Destruida:** Se logró bajar el TTFA (Time to First Audio) de ~3.8 segundos (o >9s en Docker) a **~200-250 milisegundos**, logrando el objetivo de tiempo real estricto.
- **Microservicio Estandarizado:** Kokoro ahora expone un clon de la API de OpenAI. Se puede interactuar con él usando la librería oficial de Python sin usar código a medida.
- **Transcodificación al vuelo:** Se configuró el servidor para devolver formato `opus` encapsulado en OGG, ideal para mandar directamente a la API de notas de voz de Telegram sin pasar por FFmpeg.
- **Filtro Anti-Guiris:** Se añadió lógica defensiva. Si el SDK de OpenAI intenta usar su voz por defecto (`alloy`), el servidor la intercepta y la cambia a nuestra voz española, evitando fallos de pronunciación.

## 🚧 Próximos Pasos

### 1. Telegram / OpenClaw (Prioridad Inmediata)
El bot de Telegram de OpenClaw está utilizando su propio `tool tts` en lugar de enrutar el tráfico a nuestro puente. 
**Acción:** Reconfigurar el flujo del agente/bot en OpenClaw para que el cliente TTS utilice estrictamente `base_url="http://192.168.37.1:8882/v1"`.

### 2. Chatterbox (Audiolibros)
Chatterbox en el puerto 8002 no completó las pruebas satisfactoriamente debido a que la librería moderna requiere configuración adicional y acceso al repositorio privado `chatterbox-multilingual` para hablar bien en español.
**Acción (Futura Sesión):** Configurar el token de HuggingFace en el entorno local (`huggingface-cli login`), descargar el modelo multilingüe y afinar los parámetros para generación de largo formato asíncrona.

### 3. Ajuste de Voces (Opcional)
Investigar e instalar voces masculinas (`em_alex`, `em_santa`) u otras comunitarias en la carpeta `voices/` de Kokoro para tener variedad en el bot de Telegram, las cuales ya son soportadas por nuestro nuevo interceptor API.
