from __future__ import annotations

import io
import wave
from dataclasses import dataclass

from fastapi.testclient import TestClient

from adapters.base import HealthStatus, SynthesisResult
from main import app


def _tiny_wav_bytes(duration_ms: int = 120) -> bytes:
    sample_rate = 24000
    frame_count = int(sample_rate * duration_ms / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        silence = b"\x00\x00" * frame_count
        wav_file.writeframes(silence)
    return buffer.getvalue()


class FakeAdapter:
    async def synthesize(
        self,
        text: str,
        *,
        model: str,
        voice: str,
        lang_code: str | None,
        response_format: str,
        speed: float,
    ) -> SynthesisResult:
        return SynthesisResult(audio=_tiny_wav_bytes(), media_type="audio/wav", response_format="wav")

    async def list_models(self) -> list[dict]:
        return [{"id": "tts-1", "object": "model", "owned_by": "local"}]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="ok")


@dataclass
class FakeSettings:
    default_engine: str = "kokoro"
    default_voice_kokoro: str = "af_sarah"
    default_voice_chatterbox: str = "alloy"
    output_format: str = "mp3"
    request_timeout_seconds: float = 5.0
    chunk_max_chars: int = 50
    chunk_language: str = "es"
    default_lang_code: str = "es"
    max_input_chars: int = 500


class FakeService:
    def __init__(self) -> None:
        self.settings = FakeSettings()
        adapter = FakeAdapter()
        self.adapters = {"kokoro": adapter, "chatterbox": adapter}

    def resolve_engine(self, requested_engine: str | None) -> str:
        return requested_engine or self.settings.default_engine

    def resolve_voice(self, engine: str, requested_voice: str | None) -> str:
        return requested_voice or "af_sarah"


def test_speech_endpoint_chunking_and_concat() -> None:
    with TestClient(app) as client:
        client.app.state.tts_service = FakeService()
        payload = {
            "model": "tts-1",
            "input": "Primera frase. Segunda frase con mas texto para forzar chunking.",
            "response_format": "wav",
            "engine": "kokoro",
        }
        response = client.post("/v1/audio/speech", json=payload)
        assert response.status_code == 200
        assert response.headers["x-tts-engine"] == "kokoro"
        assert int(response.headers["x-tts-chunks"]) >= 2
        assert response.content.startswith(b"RIFF")


def test_models_and_health_endpoints() -> None:
    with TestClient(app) as client:
        client.app.state.tts_service = FakeService()
        models_response = client.get("/v1/models")
        health_response = client.get("/healthz")

        assert models_response.status_code == 200
        assert health_response.status_code == 200
        assert models_response.json()["object"] == "list"
        assert health_response.json()["status"] == "ok"
