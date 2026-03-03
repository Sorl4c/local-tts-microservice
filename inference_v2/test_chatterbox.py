import traceback
try:
    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained('cuda')
    print('OK')
except Exception as e:
    traceback.print_exc()
