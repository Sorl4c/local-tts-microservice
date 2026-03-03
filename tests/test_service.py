import httpx
import pytest
import asyncio

from config import Settings
from service import TTSGatewayService


def test_resolve_engine_uses_default() -> None:
    settings = Settings(DEFAULT_ENGINE="kokoro")
    client = httpx.AsyncClient()
    service = TTSGatewayService(settings=settings, client=client)
    assert service.resolve_engine(None) == "kokoro"
    asyncio.run(client.aclose())


def test_resolve_engine_rejects_unknown() -> None:
    settings = Settings(DEFAULT_ENGINE="kokoro")
    client = httpx.AsyncClient()
    service = TTSGatewayService(settings=settings, client=client)
    with pytest.raises(ValueError):
        service.resolve_engine("nope")
    asyncio.run(client.aclose())


def test_resolve_voice_fallbacks() -> None:
    settings = Settings(DEFAULT_VOICE_KOKORO="a", DEFAULT_VOICE_CHATTERBOX="b")
    client = httpx.AsyncClient()
    service = TTSGatewayService(settings=settings, client=client)
    assert service.resolve_voice("kokoro", None) == "a"
    assert service.resolve_voice("chatterbox", None) == "b"
    assert service.resolve_voice("kokoro", "custom") == "custom"
    asyncio.run(client.aclose())
