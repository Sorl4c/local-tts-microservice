from fastapi import FastAPI
from pydantic import BaseModel
import torchaudio
import time
import io
import torch
from fastapi.responses import Response
from chatterbox.tts import ChatterboxTTS

app = FastAPI(title="Chatterbox Turbo Fast Inference v2")

print("Loading Chatterbox model onto GPU...")
try:
    from chatterbox.tts import ChatterboxTTS
    # Use the public model on the specified device
    model = ChatterboxTTS.from_pretrained("cuda")
    print("Model loaded successfully!")
    
    # Warmup step to initialize CUDA graphs / memory allocators
    print("Running warmup pass...")
    _ = model.generate("Warmup.")
    print("Warmup done.")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

class TTSRequest(BaseModel):
    text: str
    language: str = "es"
    exaggeration: float = 0.5
    cfg_weight: float = 0.3

@app.post("/v1/audio/speech")
async def generate_speech(request: TTSRequest):
    start_time = time.time()
    
    if model is None:
        return Response(content="Model failed to load", status_code=500)

    # Generate
    with torch.inference_mode():
        wav = model.generate(
            text=request.text,
            exaggeration=request.exaggeration,
            cfg_weight=request.cfg_weight
        )
    
    out_io = io.BytesIO()
    # Ensure it's on CPU before saving
    torchaudio.save(out_io, wav.cpu(), model.sr, format="wav")
    out_io.seek(0)
    
    ttfa = time.time() - start_time
    print(f"Chatterbox-Turbo -> Generated {len(request.text)} chars in {ttfa:.3f}s")
    
    return Response(content=out_io.read(), media_type="audio/wav")

@app.get("/healthz")
def health():
    return {"status": "ok", "engine": "chatterbox-turbo"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
