import requests
import time
import subprocess
import os
import sys

KOKORO_URL = "http://127.0.0.1:8882/v1/audio/speech"
CHATTERBOX_URL = "http://127.0.0.1:8002/v1/audio/speech"

sentences = [
    "Hola, esta es una prueba rápida.",
    "El rendimiento de la tarjeta gráfica parece excelente hoy.",
    "Un texto un poco más largo para medir cómo se comportan los motores de inferencia bajo carga.",
    "¿Podrá este motor responder en menos de doscientos milisegundos?",
    "Terminamos la prueba con esta frase."
]

def wait_for_server(url, name):
    print(f"Waiting for {name} to be ready...")
    for _ in range(300): # 5 minutes timeout
        try:
            res = requests.get(url.replace("/v1/audio/speech", "/healthz"))
            if res.status_code == 200:
                print(f"{name} is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    print(f"Timeout waiting for {name}.")
    return False

def run_benchmark(engine_url, engine_name, payload_maker):
    print(f"\n--- Benchmarking {engine_name} ---")
    
    # Warmup
    print("Running warmup pass...")
    try:
        requests.post(engine_url, json=payload_maker("Calentamiento"), timeout=10)
    except Exception as e:
        print(f"Warmup failed: {e}")
        return

    total_latency = 0
    total_chars = 0
    results = []

    for i, text in enumerate(sentences):
        payload = payload_maker(text)
        
        start_time = time.time()
        res = requests.post(engine_url, json=payload)
        latency = time.time() - start_time
        
        if res.status_code == 200:
            results.append(latency)
            total_latency += latency
            total_chars += len(text)
            print(f"  Sentence {i+1} ({len(text)} chars): {latency:.3f} s")
        else:
            print(f"  Sentence {i+1}: Failed with status {res.status_code}")

    if results:
        avg_latency = total_latency / len(results)
        throughput = total_chars / total_latency
        print(f"Resultados {engine_name}:")
        print(f" - Latencia media (TTFA): {avg_latency:.3f} s")
        print(f" - Throughput: {throughput:.1f} chars/s")

if __name__ == "__main__":
    if not wait_for_server(KOKORO_URL, "Kokoro v2"):
        sys.exit(1)
    if not wait_for_server(CHATTERBOX_URL, "Chatterbox Turbo v2"):
        sys.exit(1)

    # Kokoro payload
    run_benchmark(KOKORO_URL, "Kokoro v2", lambda t: {"text": t, "voice": "ef_dora"})
    
    # Chatterbox payload
    run_benchmark(CHATTERBOX_URL, "Chatterbox Turbo v2", lambda t: {"text": t, "language": "es"})
