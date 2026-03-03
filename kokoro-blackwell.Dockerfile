FROM ghcr.io/remsky/kokoro-fastapi-gpu:latest

# Blackwell (RTX 50xx, sm_120) needs PyTorch builds with cu128+.
RUN pip install --no-cache-dir --upgrade torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu128

# Runtime self-check (printed at build time).
RUN python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
PY

