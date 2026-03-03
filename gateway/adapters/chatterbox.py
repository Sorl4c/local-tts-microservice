from __future__ import annotations

import httpx

from adapters.base import AdapterError, BackendAdapter, HealthStatus, SynthesisResult


class ChatterboxAdapter(BackendAdapter):
    name = "chatterbox"
    _speech_paths = ("/v1/audio/speech", "/audio/speech")
    _models_paths = ("/v1/models", "/models")

    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client

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
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": response_format,
            "speed": speed,
        }
        if lang_code:
            payload["lang_code"] = lang_code
            payload["language"] = lang_code

        response = await self._request_with_fallback("POST", self._speech_paths, json=payload)
        media_type = response.headers.get("content-type", _guess_media_type(response_format))
        return SynthesisResult(audio=response.content, media_type=media_type, response_format=response_format)

    async def list_models(self) -> list[dict]:
        try:
            response = await self._request_with_fallback("GET", self._models_paths)
            payload = response.json()
            data = payload.get("data")
            if isinstance(data, list):
                return [entry for entry in data if isinstance(entry, dict)]
        except Exception:
            pass

        return [
            {"id": "tts-1", "object": "model", "owned_by": "local"},
            {"id": "tts-1-hd", "object": "model", "owned_by": "local"},
            {"id": "chatterbox", "object": "model", "owned_by": "local"},
        ]

    async def health_check(self) -> HealthStatus:
        try:
            await self._request_with_fallback("GET", self._models_paths)
            return HealthStatus(healthy=True, detail="ok")
        except Exception as exc:
            return HealthStatus(healthy=False, detail=str(exc))

    async def _request_with_fallback(self, method: str, paths: tuple[str, ...], **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for path in paths:
            try:
                response = await self.client.request(method, f"{self.base_url}{path}", **kwargs)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    last_error = exc
                    continue
                raise AdapterError(f"{self.name} backend error: {exc.response.status_code}") from exc
            except Exception as exc:
                last_error = exc
                break

        raise AdapterError(f"{self.name} endpoint unavailable: {last_error}")


def _guess_media_type(response_format: str) -> str:
    mapping = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "aac": "audio/aac",
        "opus": "audio/ogg",
    }
    return mapping.get(response_format, "application/octet-stream")
