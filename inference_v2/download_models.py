import os
import sys

print("=== Descargando modelo Kokoro v1.0 ===")
try:
    from kokoro import KPipeline
    # Instanciar el pipeline fuerza la descarga de kokoro-v1_0.pth (pesos) y voces (voices/ef_dora.pt)
    pipeline = KPipeline(lang_code='e')
    # Forzar la carga de la voz que usaremos en la prueba para que se guarde en caché
    _ = pipeline.load_voice('ef_dora')
    print("Kokoro descargado y listo.")
except Exception as e:
    print(f"Error descargando Kokoro: {e}")

print("\n=== Descargando modelo Chatterbox Turbo ===")
try:
    from chatterbox.tts import ChatterboxTTS
    import torch
    # Forzar la descarga del modelo Turbo
    model = ChatterboxTTS.from_pretrained("ResembleAI/chatterbox-turbo")
    print("Chatterbox Turbo descargado y listo.")
except Exception as e:
    print(f"Error descargando Chatterbox: {e}")

print("\nTodas las descargas han finalizado.")
