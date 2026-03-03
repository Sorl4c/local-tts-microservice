from __future__ import annotations

import sys

import torch


def main() -> int:
    print(f"torch_version={torch.__version__}")
    print(f"cuda_available={torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        print("ERROR: CUDA no disponible en este entorno.", file=sys.stderr)
        return 1

    device_name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    print(f"gpu_name={device_name}")
    print(f"gpu_capability=sm_{capability[0]}{capability[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

