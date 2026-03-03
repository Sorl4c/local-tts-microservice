from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from statistics import mean

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark A/B de TTS local (Kokoro vs Chatterbox).")
    parser.add_argument("--base-url", default="http://localhost:9000", help="URL del gateway")
    parser.add_argument("--engines", nargs="+", default=["kokoro", "chatterbox"], help="Motores a evaluar")
    parser.add_argument("--model", default="tts-1", help="Modelo OpenAI-style")
    parser.add_argument("--response-format", default="mp3", choices=["mp3", "wav", "flac", "aac", "opus"])
    parser.add_argument("--voice-kokoro", default="ef_dora")
    parser.add_argument("--voice-chatterbox", default="es_carlos")
    parser.add_argument(
        "--chatterbox-voice-mode",
        choices=["custom", "default", "omit"],
        default="custom",
        help="custom=usa --voice-chatterbox, default=fuerza 'default', omit=no envia campo voice",
    )
    parser.add_argument("--lang-code", default="es")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--corpus", default="benchmark/corpus_es.txt")
    parser.add_argument("--output-dir", default="benchmark/outputs")
    parser.add_argument("--report-dir", default="benchmark/reports")
    return parser.parse_args()


def load_corpus(path: Path) -> list[dict[str, str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [{"sample_id": f"s{i+1:02d}", "text": line} for i, line in enumerate(lines)]


def audio_duration_seconds(path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        return float(payload["format"]["duration"])
    except Exception:
        return None


def choose_voice(engine: str, args: argparse.Namespace) -> str:
    return args.voice_kokoro if engine == "kokoro" else args.voice_chatterbox


def build_payload(engine: str, sample_text: str, args: argparse.Namespace) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": args.model,
        "input": sample_text,
        "response_format": args.response_format,
        "engine": engine,
        "lang_code": args.lang_code,
    }
    if engine == "chatterbox":
        if args.chatterbox_voice_mode == "custom":
            payload["voice"] = args.voice_chatterbox
        elif args.chatterbox_voice_mode == "default":
            payload["voice"] = "default"
    else:
        payload["voice"] = args.voice_kokoro
    return payload


def main() -> None:
    args = parse_args()
    corpus_path = Path(args.corpus)
    output_dir = Path(args.output_dir)
    report_dir = Path(args.report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    samples = load_corpus(corpus_path)
    rows: list[dict[str, object]] = []

    with httpx.Client(timeout=args.timeout) as client:
        for engine in args.engines:
            engine_dir = output_dir / engine
            engine_dir.mkdir(parents=True, exist_ok=True)

            for sample in samples:
                payload = build_payload(engine, sample["text"], args)
                started = time.perf_counter()
                error = ""
                status = "ok"
                duration = None
                audio_path = engine_dir / f"{sample['sample_id']}.{args.response_format if args.response_format != 'opus' else 'ogg'}"
                response_size = 0
                chunk_count = ""
                ttfa_ms = None

                try:
                    audio_bytes = b""
                    with client.stream("POST", f"{args.base_url.rstrip('/')}/v1/audio/speech", json=payload) as response:
                        if response.status_code != 200:
                            elapsed = (time.perf_counter() - started) * 1000
                            status = "error"
                            error = f"HTTP {response.status_code}: {response.text[:200]}"
                        else:
                            first = True
                            for chunk in response.iter_bytes():
                                if first:
                                    ttfa_ms = (time.perf_counter() - started) * 1000
                                    first = False
                                audio_bytes += chunk
                            elapsed = (time.perf_counter() - started) * 1000
                            response_size = len(audio_bytes)
                            chunk_count = response.headers.get("X-TTS-Chunks", "")
                            audio_path.write_bytes(audio_bytes)
                            duration = audio_duration_seconds(audio_path)
                except Exception as exc:
                    elapsed = (time.perf_counter() - started) * 1000
                    status = "error"
                    error = str(exc)

                rtf = None
                chars_per_sec = None
                if duration and duration > 0:
                    rtf = (elapsed / 1000) / duration
                if elapsed > 0:
                    chars_per_sec = len(sample["text"]) / (elapsed / 1000)

                rows.append(
                    {
                        "sample_id": sample["sample_id"],
                        "engine": engine,
                        "chars": len(sample["text"]),
                        "latency_ms": round(elapsed, 2),
                        "ttfa_ms": round(ttfa_ms, 2) if ttfa_ms is not None else "",
                        "audio_seconds": round(duration, 3) if duration is not None else "",
                        "rtf": round(rtf, 4) if rtf is not None else "",
                        "chars_per_sec": round(chars_per_sec, 2) if chars_per_sec is not None else "",
                        "bytes": response_size,
                        "chunks": chunk_count,
                        "status": status,
                        "error": error,
                        "mos_subjective_1_5": "",
                        "audio_file": str(audio_path) if status == "ok" else "",
                    }
                )

    csv_path = report_dir / "benchmark_raw.csv"
    fields = [
        "sample_id",
        "engine",
        "chars",
        "latency_ms",
        "ttfa_ms",
        "audio_seconds",
        "rtf",
        "chars_per_sec",
        "bytes",
        "chunks",
        "status",
        "error",
        "mos_subjective_1_5",
        "audio_file",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    mos_sheet = report_dir / "mos_sheet.csv"
    with mos_sheet.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "engine",
                "audio_file",
                "naturalidad_1_5",
                "pronunciacion_1_5",
                "estabilidad_1_5",
                "comentarios",
            ],
        )
        writer.writeheader()
        for row in rows:
            if row["status"] != "ok":
                continue
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "engine": row["engine"],
                    "audio_file": row["audio_file"],
                    "naturalidad_1_5": "",
                    "pronunciacion_1_5": "",
                    "estabilidad_1_5": "",
                    "comentarios": "",
                }
            )

    summary_path = report_dir / "summary.md"
    summary_path.write_text(build_summary(rows), encoding="utf-8")

    print(f"Benchmark completado. Reporte CSV: {csv_path}")
    print(f"Resumen: {summary_path}")
    print(f"Hoja MOS: {mos_sheet}")


def build_summary(rows: list[dict[str, object]]) -> str:
    lines = ["# Benchmark Summary", ""]
    engines = sorted({str(row["engine"]) for row in rows})
    for engine in engines:
        ok_rows = [row for row in rows if row["engine"] == engine and row["status"] == "ok"]
        err_rows = [row for row in rows if row["engine"] == engine and row["status"] != "ok"]
        lines.append(f"## {engine}")
        if not ok_rows:
            lines.append("- No successful runs.")
            lines.append(f"- Errors: {len(err_rows)}")
            lines.append("")
            continue

        avg_latency = mean(float(row["latency_ms"]) for row in ok_rows)
        avg_rtf_values = [float(row["rtf"]) for row in ok_rows if row["rtf"] != ""]
        avg_rtf = mean(avg_rtf_values) if avg_rtf_values else None
        avg_ttfa_values = [float(row["ttfa_ms"]) for row in ok_rows if row["ttfa_ms"] != ""]
        avg_ttfa = mean(avg_ttfa_values) if avg_ttfa_values else None
        avg_cps_values = [float(row["chars_per_sec"]) for row in ok_rows if row["chars_per_sec"] != ""]
        avg_cps = mean(avg_cps_values) if avg_cps_values else None
        avg_size = mean(float(row["bytes"]) for row in ok_rows)

        lines.append(f"- Successful samples: {len(ok_rows)}")
        lines.append(f"- Errors: {len(err_rows)}")
        lines.append(f"- Avg latency (ms): {avg_latency:.2f}")
        lines.append(f"- Avg TTFA (ms): {avg_ttfa:.2f}" if avg_ttfa is not None else "- Avg TTFA (ms): n/a")
        lines.append(f"- Avg RTF: {avg_rtf:.4f}" if avg_rtf is not None else "- Avg RTF: n/a")
        lines.append(f"- Avg throughput (chars/s): {avg_cps:.2f}" if avg_cps is not None else "- Avg throughput (chars/s): n/a")
        lines.append(f"- Avg size (bytes): {avg_size:.0f}")
        lines.append("")

    lines.append("## MOS")
    lines.append("- Rellena `mos_sheet.csv` para comparativa subjetiva 1-5.")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
