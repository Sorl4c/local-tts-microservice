from __future__ import annotations

import httpx

from adapters import ChatterboxAdapter, KokoroAdapter
from adapters.base import BackendAdapter
from config import Settings


class TTSGatewayService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.adapters: dict[str, BackendAdapter] = {
            "kokoro": KokoroAdapter(settings.kokoro_url, client),
            "chatterbox": ChatterboxAdapter(settings.chatterbox_url, client),
        }

    def resolve_engine(self, requested_engine: str | None) -> str:
        engine = (requested_engine or self.settings.default_engine).lower()
        if engine not in self.adapters:
            raise ValueError(f"unsupported engine: {engine}")
        return engine

    def resolve_voice(self, engine: str, requested_voice: str | None) -> str:
        if requested_voice:
            return requested_voice
        if engine == "kokoro":
            return self.settings.default_voice_kokoro
        return self.settings.default_voice_chatterbox

