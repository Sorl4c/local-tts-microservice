from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def concat_segments(segments: list[bytes], response_format: str) -> bytes:
    if not segments:
        raise ValueError("segments cannot be empty")
    if len(segments) == 1:
        return segments[0]

    input_ext = _extension_for_format(response_format)
    output_ext, output_codec = _ffmpeg_output_options(response_format)

    with tempfile.TemporaryDirectory(prefix="tts_concat_") as tmp:
        tmp_path = Path(tmp)
        list_path = tmp_path / "inputs.txt"
        output_path = tmp_path / f"output.{output_ext}"

        lines: list[str] = []
        for index, segment in enumerate(segments):
            file_name = f"segment_{index:04d}.{input_ext}"
            file_path = tmp_path / file_name
            file_path.write_bytes(segment)
            lines.append(f"file '{file_name}'")

        list_path.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path.name),
            "-c:a",
            output_codec,
            str(output_path.name),
        ]
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr.strip()}")

        return output_path.read_bytes()


def _extension_for_format(response_format: str) -> str:
    if response_format == "opus":
        return "ogg"
    return response_format


def _ffmpeg_output_options(response_format: str) -> tuple[str, str]:
    if response_format == "mp3":
        return ("mp3", "libmp3lame")
    if response_format == "wav":
        return ("wav", "pcm_s16le")
    if response_format == "flac":
        return ("flac", "flac")
    if response_format == "aac":
        return ("aac", "aac")
    if response_format == "opus":
        return ("ogg", "libopus")
    raise ValueError(f"unsupported response format: {response_format}")

