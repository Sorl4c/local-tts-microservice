from __future__ import annotations

import argparse
import os
import subprocess

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prueba sendVoice (Telegram) usando el gateway TTS local.")
    parser.add_argument("--base-url", default="http://localhost:9000")
    parser.add_argument("--engine", default="kokoro", choices=["kokoro", "chatterbox"])
    parser.add_argument("--voice", default=None)
    parser.add_argument("--lang-code", default="es")
    parser.add_argument("--model", default="tts-1")
    parser.add_argument("--text", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def mp3_to_ogg(mp3_bytes: bytes) -> bytes:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-c:a",
        "libopus",
        "-f",
        "ogg",
        "pipe:1",
    ]
    result = subprocess.run(cmd, input=mp3_bytes, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr.decode('utf-8', errors='ignore').strip()}")
    return result.stdout


def main() -> None:
    args = parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en el entorno.")

    payload = {
        "model": args.model,
        "input": args.text,
        "voice": args.voice,
        "lang_code": args.lang_code,
        "engine": args.engine,
        "response_format": "mp3",
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    with httpx.Client(timeout=args.timeout) as client:
        tts_response = client.post(f"{args.base_url.rstrip('/')}/v1/audio/speech", json=payload)
        tts_response.raise_for_status()
        ogg_bytes = mp3_to_ogg(tts_response.content)

        telegram_url = f"https://api.telegram.org/bot{token}/sendVoice"
        files = {"voice": ("response.ogg", ogg_bytes, "audio/ogg")}
        data = {"chat_id": chat_id}
        telegram_response = client.post(telegram_url, data=data, files=files)
        telegram_response.raise_for_status()

    print("Voice enviado correctamente a Telegram.")


if __name__ == "__main__":
    main()
