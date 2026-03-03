from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from adapters.base import AdapterError
from schemas import SpeechRequest
from service import TTSGatewayService
from utils import chunk_text, concat_segments

router = APIRouter(tags=["speech"])


@router.post("/v1/audio/speech")
async def synthesize_speech(payload: SpeechRequest, request: Request) -> Response:
    service: TTSGatewayService = request.app.state.tts_service
    settings = service.settings

    if len(payload.input) > settings.max_input_chars:
        raise HTTPException(
            status_code=400,
            detail=f"input too long: {len(payload.input)} chars (limit {settings.max_input_chars})",
        )

    try:
        engine = service.resolve_engine(payload.engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    voice = service.resolve_voice(engine, payload.voice)
    lang_code = (payload.lang_code or settings.default_lang_code).strip() if (payload.lang_code or settings.default_lang_code) else None
    response_format = payload.response_format or settings.output_format
    chunks = chunk_text(payload.input, settings.chunk_max_chars, settings.chunk_language)

    adapter = service.adapters[engine]
    segments: list[bytes] = []
    media_type = _media_type_for_format(response_format)

    for chunk in chunks:
        try:
            result = await adapter.synthesize(
                chunk,
                model=payload.model,
                voice=voice,
                lang_code=lang_code,
                response_format=response_format,
                speed=payload.speed,
            )
        except AdapterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        segments.append(result.audio)
        media_type = result.media_type or media_type

    audio = concat_segments(segments, response_format=response_format)

    headers = {
        "X-TTS-Engine": engine,
        "X-TTS-Chunks": str(len(chunks)),
        "Content-Disposition": f'attachment; filename="speech.{_ext_for_format(response_format)}"',
    }
    return Response(content=audio, media_type=media_type, headers=headers)


def _media_type_for_format(response_format: str) -> str:
    mapping = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "aac": "audio/aac",
        "opus": "audio/ogg",
    }
    return mapping.get(response_format, "application/octet-stream")


def _ext_for_format(response_format: str) -> str:
    return "ogg" if response_format == "opus" else response_format
