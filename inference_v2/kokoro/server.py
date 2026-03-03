from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from kokoro import KPipeline
import soundfile as sf
import io
import time
import numpy as np
from typing import Literal, Optional

app = FastAPI(title="Local OpenAI-Compatible TTS API (Kokoro V2 Fast)")

print("Initializing Kokoro Pipeline (GPU)...")
try:
    # 'e' for Spanish in Kokoro v1.0
    pipeline = KPipeline(lang_code='e')
    print("Pipeline ready.")
except Exception as e:
    print(f"Error initializing pipeline: {e}")
    pipeline = None

# OpenAI Standard Formats
SupportedFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]

class SpeechRequest(BaseModel):
    model: str = Field(default="tts-1")
    input: str = Field(..., min_length=1)
    voice: Optional[str] = Field(default="ef_dora")
    response_format: SupportedFormat = Field(default="mp3")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)

@app.post("/v1/audio/speech")
async def generate_speech(request: SpeechRequest):
    start_time = time.time()
    
    if pipeline is None:
        raise HTTPException(status_code=500, detail="TTS Engine failed to load.")

    # Intercept OpenAI default voice names and map to Spanish Kokoro voice
    target_voice = request.voice
    # Known Kokoro Spanish voices
    valid_kokoro_voices = ["ef_dora", "em_alex", "em_santa"]
    
    if not target_voice or target_voice not in valid_kokoro_voices:
        print(f"[VOICE INTERCEPTOR] Received voice '{target_voice}'. Forcing fallback to 'ef_dora' (Spanish)")
        target_voice = "ef_dora"
    else:
        print(f"[VOICE INTERCEPTOR] Using native Kokoro voice '{target_voice}'")

    # Generator with soft chunking by newlines to keep it atomic but handle long texts gracefully
    generator = pipeline(
        request.input, 
        voice=target_voice, 
        speed=request.speed, 
        split_pattern=r'\n+'
    )
    
    audio_chunks = []
    for _, _, audio in generator:
        if audio is not None:
            audio_chunks.append(audio)
    
    if not audio_chunks:
        raise HTTPException(status_code=500, detail="No audio generated from text.")
        
    final_audio = np.concatenate(audio_chunks)
    
    out_io = io.BytesIO()
    
    # Map OpenAI format to Soundfile format
    media_type = "audio/mpeg"
    sf_format = 'MP3'
    sf_subtype = None
    
    if request.response_format == "wav":
        sf_format = 'WAV'
        sf_subtype = 'PCM_16'
        media_type = "audio/wav"
    elif request.response_format == "flac":
        sf_format = 'FLAC'
        media_type = "audio/flac"
    elif request.response_format == "opus":
        sf_format = 'OGG'
        sf_subtype = 'OPUS'
        media_type = "audio/ogg"
    elif request.response_format == "aac":
        # Soundfile lacks native AAC, fallback to MP3
        sf_format = 'MP3'
        media_type = "audio/aac" 
    
    sf.write(out_io, final_audio, 24000, format=sf_format, subtype=sf_subtype)
    out_io.seek(0)
    
    elapsed = time.time() - start_time
    print(f"[{request.model}] Generated {len(request.input)} chars in {elapsed:.3f}s -> format: {request.response_format}")
    
    return Response(content=out_io.read(), media_type=media_type)

@app.get("/v1/models")
def list_models():
    # Standard OpenAI models response
    return JSONResponse({
        "object": "list",
        "data": [
            {
                "id": "tts-1",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-kokoro"
            },
            {
                "id": "tts-1-hd",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-kokoro"
            }
        ]
    })

@app.get("/healthz")
def health():
    return {"status": "ok", "engine": "kokoro-fast-openai"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8882)
