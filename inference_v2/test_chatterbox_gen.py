import traceback
import torchaudio
import torch
import io

try:
    from chatterbox.tts import ChatterboxTTS
    print("Cargando modelo...")
    model = ChatterboxTTS.from_pretrained('cuda')
    print("Generando audio...")
    wav = model.generate(text="Hola", exaggeration=0.5, cfg=0.3)
    print("Guardando audio...")
    out_io = io.BytesIO()
    torchaudio.save(out_io, wav.cpu(), model.sr, format="wav")
    print("Éxito!")
except Exception as e:
    traceback.print_exc()
