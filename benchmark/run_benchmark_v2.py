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
    parser = argparse.ArgumentParser(description="Benchmark V2 de Inferencia Pura Bare Metal (Kokoro vs Chatterbox).")
    parser.add_argument("--kokoro-url", default="http://127.0.0.1:8882", help="URL base del servidor Kokoro V2")
    parser.add_argument("--chatterbox-url", default="http://127.0.0.1:8002", help="URL base del servidor Chatterbox V2")
    parser.add_argument("--engines", nargs="+", default=["kokoro", "chatterbox"], help="Motores a evaluar")
    parser.add_argument("--voice-kokoro", default="ef_dora")
    parser.add_argument("--lang-chatterbox", default="es")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--corpus", default="benchmark/corpus_es.txt")
    parser.add_argument("--output-dir", default="benchmark/outputs_v2")
    parser.add_argument("--report-dir", default="benchmark/reports_v2")
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

def build_payload(engine: str, sample_text: str, args: argparse.Namespace) -> dict[str, object]:
    if engine == "kokoro":
        return {
            "text": sample_text,
            "voice": args.voice_kokoro
        }
    else:
        return {
            "text": sample_text,
            "language": args.lang_chatterbox,
            "exaggeration": 0.5,
            "cfg_weight": 0.3
        }

def get_engine_url(engine: str, args: argparse.Namespace) -> str:
    if engine == "kokoro":
        return f"{args.kokoro_url.rstrip('/')}/v1/audio/speech"
    return f"{args.chatterbox_url.rstrip('/')}/v1/audio/speech"

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
            engine_url = get_engine_url(engine, args)
            
            print(f"\n[{engine.upper()}] Comenzando benchmark en {engine_url}...")

            for sample in samples:
                payload = build_payload(engine, sample["text"], args)
                started = time.perf_counter()
                error = ""
                status = "ok"
                duration = None
                # V2 servers return standard wav files
                audio_path = engine_dir / f"{sample['sample_id']}.wav"
                response_size = 0
                ttfa_ms = None

                try:
                    audio_bytes = b""
                    with client.stream("POST", engine_url, json=payload) as response:
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
                            
                            if not audio_bytes:
                                raise Exception("Empty audio response")
                                
                            elapsed = (time.perf_counter() - started) * 1000
                            response_size = len(audio_bytes)
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
                        "status": status,
                        "error": error,
                        "audio_file": str(audio_path) if status == "ok" else "",
                    }
                )
                print(f"  {sample['sample_id']} ({len(sample['text'])} chars) -> "
                      f"TTFA: {ttfa_ms if ttfa_ms else 0:.0f}ms | "
                      f"Total: {elapsed:.0f}ms | Status: {status}")

    csv_path = report_dir / "benchmark_raw_v2.csv"
    fields = [
        "sample_id", "engine", "chars", "latency_ms", "ttfa_ms", 
        "audio_seconds", "rtf", "chars_per_sec", "bytes", 
        "status", "error", "audio_file"
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary_path = report_dir / "summary_v2.md"
    summary_path.write_text(build_summary(rows), encoding="utf-8")

    print(f"\nBenchmark V2 completado.")
    print(f"Reporte CSV: {csv_path}")
    print(f"Resumen: {summary_path}")

def build_summary(rows: list[dict[str, object]]) -> str:
    lines = ["# Benchmark Summary V2 (Bare Metal Inferencia Pura)", ""]
    engines = sorted({str(row["engine"]) for row in rows})
    for engine in engines:
        ok_rows = [row for row in rows if row["engine"] == engine and row["status"] == "ok"]
        err_rows = [row for row in rows if row["engine"] == engine and row["status"] != "ok"]
        lines.append(f"## {engine.upper()}")
        if not ok_rows:
            lines.append("- No successful runs.")
            lines.append(f"- Errors: {len(err_rows)}")
            lines.append("")
            continue

        avg_latency = mean(float(row["latency_ms"]) for row in ok_rows)
        avg_ttfa_values = [float(row["ttfa_ms"]) for row in ok_rows if row["ttfa_ms"] != ""]
        avg_ttfa = mean(avg_ttfa_values) if avg_ttfa_values else None
        avg_cps_values = [float(row["chars_per_sec"]) for row in ok_rows if row["chars_per_sec"] != ""]
        avg_cps = mean(avg_cps_values) if avg_cps_values else None
        
        # Calculate max TTFA to see worst case
        max_ttfa = max(avg_ttfa_values) if avg_ttfa_values else None

        lines.append(f"- Successful samples: {len(ok_rows)}")
        lines.append(f"- Errors: {len(err_rows)}")
        lines.append(f"- **Avg TTFA (ms): {avg_ttfa:.2f}**" if avg_ttfa is not None else "- Avg TTFA (ms): n/a")
        lines.append(f"- Max TTFA (ms): {max_ttfa:.2f}" if max_ttfa is not None else "- Max TTFA (ms): n/a")
        lines.append(f"- Avg Total Latency (ms): {avg_latency:.2f}")
        lines.append(f"- Avg throughput (chars/s): {avg_cps:.2f}" if avg_cps is not None else "- Avg throughput (chars/s): n/a")
        lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    main()
