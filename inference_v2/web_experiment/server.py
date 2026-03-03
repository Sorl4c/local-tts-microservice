from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

KOKORO_BASE_URL = "http://192.168.37.1:8882/v1"
app = FastAPI(title="Kokoro Simple Web TTS")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=6000)
    voice: str = Field(default="ef_dora")
    response_format: str = Field(default="opus")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.post("/api/tts")
async def synthesize_tts(payload: TTSRequest) -> Response:
    url = f"{KOKORO_BASE_URL}/audio/speech"
    started = time.perf_counter()

    request_json = {
        "model": "tts-1",
        "input": payload.text,
        "voice": payload.voice,
        "response_format": payload.response_format,
        "speed": payload.speed,
    }

    timeout = httpx.Timeout(90.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(url, json=request_json)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"kokoro upstream error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000

    if upstream.status_code != 200:
        detail = upstream.text[:400]
        raise HTTPException(
            status_code=502,
            detail=f"kokoro status {upstream.status_code}: {detail}",
        )

    media_type = upstream.headers.get("content-type", "application/octet-stream")
    headers = {
        "X-TTS-Ms": f"{elapsed_ms:.2f}",
        "Cache-Control": "no-store",
    }
    return Response(content=upstream.content, media_type=media_type, headers=headers)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "kokoro-simple-web-tts"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8890)
