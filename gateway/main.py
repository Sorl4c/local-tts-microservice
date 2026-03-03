from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from config import get_settings
from routers import health_router, models_router, speech_router
from service import TTSGatewayService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    client = httpx.AsyncClient(timeout=timeout)
    app.state.http_client = client
    app.state.tts_service = TTSGatewayService(settings=settings, client=client)
    yield
    await client.aclose()


app = FastAPI(
    title="Local TTS Gateway",
    version="0.1.0",
    description="OpenAI-compatible local TTS gateway for Kokoro and Chatterbox.",
    lifespan=lifespan,
)

app.include_router(speech_router)
app.include_router(models_router)
app.include_router(health_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "local-tts-gateway"}
