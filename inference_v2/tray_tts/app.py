from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import io
import json
import logging
import math
import queue
import struct
import subprocess
import threading
import time
import wave
import winsound
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import pyperclip
import pystray
from PIL import Image, ImageDraw
from pystray import Menu, MenuItem

ROOT_DIR = Path(__file__).resolve().parents[2]
INFERENCE_DIR = ROOT_DIR / "inference_v2"
RUN_KOKORO_SCRIPT = INFERENCE_DIR / "run_kokoro.ps1"
KOKORO_BASE_URL = "http://192.168.37.1:8882/v1"
KOKORO_HEALTH_URL = "http://192.168.37.1:8882/healthz"

VOICE_OPTIONS = [
    ("ef_dora", "ef_dora (Femenino)"),
    ("em_alex", "em_alex (Masculino)"),
    ("em_santa", "em_santa (Especial)"),
]
PRIMARY_HOTKEY = "ctrl+shift+y"
FALLBACK_HOTKEY = "ctrl+alt+y"
LOG_PATH = INFERENCE_DIR / "tray_tts" / "tray_tts.log"
TEMP_AUDIO_DIR = INFERENCE_DIR / "tray_tts" / "tmp_audio"
CONFIG_PATH = INFERENCE_DIR / "tray_tts" / "config.json"
DEFAULT_SPEED = 1.0
MIN_SPEED = 0.6
MAX_SPEED = 2.0
SPEED_STEP = 0.05
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_Y = 0x59
HOTKEY_ID_PRIMARY = 1
HOTKEY_ID_FALLBACK = 2


@dataclass
class AppState:
    service_status: str = "off"
    speech_status: str = "idle"
    selected_voice: str = "em_santa"
    last_error: str = ""
    tts_ms: str = "-"
    hotkeys_registered: bool = False
    playback_speed: float = DEFAULT_SPEED


class AudioControlPopup:
    def __init__(
        self,
        on_stop,
        on_pause,
        on_play,
        on_speed_change,
        on_voice_change,
        normalize_speed,
        voice_options,
    ) -> None:
        self._on_stop = on_stop
        self._on_pause = on_pause
        self._on_play = on_play
        self._on_speed_change = on_speed_change
        self._on_voice_change = on_voice_change
        self._normalize_speed = normalize_speed
        self._voice_options = list(voice_options)
        self._voice_by_label = {label: voice for voice, label in self._voice_options}
        self._label_by_voice = {voice: label for voice, label in self._voice_options}
        self._tasks: queue.Queue = queue.Queue()
        self._running = True
        self.available = False
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.5)

    def _run(self) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk
        except Exception:
            logging.exception("Tkinter unavailable; popup disabled")
            self._ready.set()
            return

        self._root = tk.Tk()
        self._root.title("Kokoro Audio")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._root.protocol("WM_DELETE_WINDOW", self._hide)

        frame = ttk.Frame(self._root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")

        self._status_var = tk.StringVar(value="Detenido")
        self._speed_text_var = tk.StringVar(value=f"{DEFAULT_SPEED:.2f}x")
        self._voice_var = tk.StringVar(value="")

        title = ttk.Label(frame, text="Kokoro Audio")
        title.grid(row=0, column=0, columnspan=2, sticky="w")

        status_label = ttk.Label(frame, textvariable=self._status_var)
        status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 8))

        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)
        controls.columnconfigure(3, weight=1)

        stop_button = ttk.Button(controls, text="Stop", command=self._handle_stop)
        stop_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        pause_button = ttk.Button(controls, text="Pause", command=self._handle_pause)
        pause_button.grid(row=0, column=1, sticky="ew", padx=2)

        play_button = ttk.Button(controls, text="Play", command=self._handle_play)
        play_button.grid(row=0, column=2, sticky="ew", padx=2)

        self._voice_combo = ttk.Combobox(
            controls,
            values=[label for _, label in self._voice_options],
            textvariable=self._voice_var,
            state="readonly",
            width=20,
        )
        self._voice_combo.grid(row=0, column=3, sticky="ew", padx=(4, 0))
        self._ignore_voice_change = False
        self._voice_combo.bind("<<ComboboxSelected>>", self._handle_voice_selected)

        speed_label = ttk.Label(frame, textvariable=self._speed_text_var)
        speed_label.grid(row=2, column=1, sticky="e", pady=(0, 8))

        self._ignore_slider = False
        self._speed_scale = tk.Scale(
            frame,
            from_=MIN_SPEED,
            to=MAX_SPEED,
            resolution=SPEED_STEP,
            orient="horizontal",
            length=220,
            command=self._handle_slider,
        )
        self._speed_scale.grid(row=3, column=0, columnspan=2, sticky="ew")
        self._speed_scale.set(DEFAULT_SPEED)

        self._hide_timer = None
        self._center_popup()
        self._root.withdraw()
        self.available = True
        self._ready.set()

        self._root.after(60, self._drain_tasks)
        self._root.mainloop()

    def _center_popup(self) -> None:
        try:
            self._root.update_idletasks()
            width = self._root.winfo_reqwidth()
            height = self._root.winfo_reqheight()
            x = self._root.winfo_screenwidth() - width - 40
            y = self._root.winfo_screenheight() - height - 100
            self._root.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        except Exception:
            logging.exception("Popup geometry update failed")

    def _drain_tasks(self) -> None:
        while True:
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                break

            fn, done, holder = task
            try:
                holder["result"] = fn()
            except Exception as exc:
                holder["error"] = exc
            finally:
                if done is not None:
                    done.set()

        if self._running and getattr(self, "_root", None) is not None:
            self._root.after(60, self._drain_tasks)

    def _invoke(self, fn, wait: bool = False, timeout: float = 1.0):
        if not self.available:
            return None
        done = threading.Event() if wait else None
        holder = {}
        self._tasks.put((fn, done, holder))
        if not wait:
            return None
        if not done.wait(timeout=timeout):
            return None
        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    def _hide(self) -> None:
        if not self.available:
            return
        self._root.withdraw()

    def _status_to_label(self, speech_status: str, last_error: str) -> str:
        if last_error:
            return f"Error: {last_error}"
        mapping = {
            "idle": "Detenido",
            "requesting": "Solicitando...",
            "playing": "Leyendo...",
            "paused": "Pausado",
            "error": "Error",
        }
        return mapping.get(speech_status, speech_status)

    def _set_speed_widget(self, speed: float) -> None:
        if not self.available:
            return
        speed = self._normalize_speed(speed)
        self._ignore_slider = True
        self._speed_scale.set(speed)
        self._ignore_slider = False
        self._speed_text_var.set(f"{speed:.2f}x")

    def _set_voice_widget(self, selected_voice: str) -> None:
        if not self.available:
            return
        label = self._label_by_voice.get(selected_voice)
        if not label:
            return
        self._ignore_voice_change = True
        self._voice_var.set(label)
        self._ignore_voice_change = False

    def _set_state(self, speed: float, speech_status: str, last_error: str, selected_voice: str) -> None:
        if not self.available:
            return
        self._set_speed_widget(speed)
        self._set_voice_widget(selected_voice)
        self._status_var.set(self._status_to_label(speech_status, last_error))

    def show_popup(self, speed: float, speech_status: str, selected_voice: str, last_error: str = "") -> None:
        def _do_show() -> None:
            if not self.available:
                return
            self._set_state(speed, speech_status, last_error, selected_voice)
            self._root.deiconify()
            self._root.lift()
            self._root.attributes("-topmost", True)
            self._center_popup()

        self._invoke(_do_show)

    def update_state(self, speed: float, speech_status: str, selected_voice: str, last_error: str = "") -> None:
        self._invoke(lambda: self._set_state(speed, speech_status, last_error, selected_voice))

    def hide_popup_after_idle(self, timeout_ms: int = 1500) -> None:
        def _do_hide_later() -> None:
            if not self.available:
                return
            if self._hide_timer is not None:
                self._root.after_cancel(self._hide_timer)
            self._hide_timer = self._root.after(timeout_ms, self._hide)

        self._invoke(_do_hide_later)

    def _handle_stop(self) -> None:
        threading.Thread(target=self._on_stop, daemon=True).start()

    def _handle_pause(self) -> None:
        threading.Thread(target=self._on_pause, daemon=True).start()

    def _handle_play(self) -> None:
        threading.Thread(target=self._on_play, daemon=True).start()

    def _handle_slider(self, raw_value: str) -> None:
        if self._ignore_slider:
            return
        try:
            value = float(raw_value)
        except Exception:
            return
        normalized = self._normalize_speed(value)
        self._speed_text_var.set(f"{normalized:.2f}x")
        if abs(normalized - value) > 1e-6:
            self._set_speed_widget(normalized)
        threading.Thread(target=self._on_speed_change, args=(normalized,), daemon=True).start()

    def _handle_voice_selected(self, _event=None) -> None:
        if self._ignore_voice_change:
            return
        label = self._voice_var.get().strip()
        if not label:
            return
        voice = self._voice_by_label.get(label)
        if not voice:
            return
        threading.Thread(target=self._on_voice_change, args=(voice,), daemon=True).start()

    def shutdown(self) -> None:
        self._running = False
        if not self.available:
            return

        def _do_shutdown() -> None:
            try:
                self._root.destroy()
            except Exception:
                pass

        self._invoke(_do_shutdown)


class TrayTTSApp:
    def __init__(self) -> None:
        self._configure_logging()
        self.state = AppState()
        self.icon: Optional[pystray.Icon] = None
        self.lock = threading.RLock()
        self.http = httpx.Client(timeout=30.0)
        self.kokoro_process: Optional[subprocess.Popen] = None
        self.started_by_app = False
        self.current_request_id = 0
        self.current_audio_file: Optional[Path] = None
        self.running = True
        self.hotkey_thread_id: Optional[int] = None
        self.last_hotkey_ts = 0.0
        self.last_text_spoken = ""
        self._load_config()
        self.audio_popup = AudioControlPopup(
            on_stop=self._on_popup_stop,
            on_pause=self._on_popup_pause,
            on_play=self._on_popup_play,
            on_speed_change=self._on_speed_changed,
            on_voice_change=self._on_voice_changed_from_popup,
            normalize_speed=self._normalize_speed,
            voice_options=VOICE_OPTIONS,
        )

    def _configure_logging(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(LOG_PATH),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.info("Tray app starting")

    def _normalize_speed(self, value: float) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = DEFAULT_SPEED
        numeric = max(MIN_SPEED, min(MAX_SPEED, numeric))
        stepped = round(numeric / SPEED_STEP) * SPEED_STEP
        stepped = max(MIN_SPEED, min(MAX_SPEED, stepped))
        return round(stepped, 2)

    def _load_config(self) -> None:
        speed = DEFAULT_SPEED
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                speed = self._normalize_speed(data.get("playback_speed", DEFAULT_SPEED))
            except Exception:
                logging.exception("Config load failed; using defaults")
                speed = DEFAULT_SPEED
        with self.lock:
            self.state.playback_speed = speed
        self._save_config()

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with self.lock:
                speed = self.state.playback_speed
            payload = {"playback_speed": speed}
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            logging.exception("Config save failed")

    def run(self) -> None:
        self.icon = pystray.Icon(
            "kokoro-tray-tts",
            self._build_icon("off"),
            "Kokoro Tray TTS",
            menu=self._build_menu(),
        )
        self._start_hotkey_listener()
        threading.Thread(target=self._health_loop, daemon=True).start()
        self.icon.run()

    def _start_hotkey_listener(self) -> None:
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    def _hotkey_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            self.hotkey_thread_id = int(kernel32.GetCurrentThreadId())
            ok1 = bool(
                user32.RegisterHotKey(
                    None,
                    HOTKEY_ID_PRIMARY,
                    MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
                    VK_Y,
                )
            )
            ok2 = bool(
                user32.RegisterHotKey(
                    None,
                    HOTKEY_ID_FALLBACK,
                    MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
                    VK_Y,
                )
            )
            with self.lock:
                self.state.hotkeys_registered = ok1 or ok2
                self.state.last_error = ""
            logging.info(
                "Hotkeys registered via RegisterHotKey: primary=%s fallback=%s",
                ok1,
                ok2,
            )
            if not (ok1 or ok2):
                self._set_error("No se pudieron registrar hotkeys globales")
                return

            msg = wintypes.MSG()
            while self.running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam in (HOTKEY_ID_PRIMARY, HOTKEY_ID_FALLBACK):
                    self._on_hotkey()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            with self.lock:
                self.state.hotkeys_registered = False
            self._set_error(f"No se pudieron registrar hotkeys: {exc}")
            logging.exception("Win32 hotkey registration failed")
        finally:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID_PRIMARY)
            except Exception:
                pass
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID_FALLBACK)
            except Exception:
                pass

    def _build_menu(self) -> Menu:
        voice_items = [
            MenuItem(
                label,
                lambda _, v=voice: self._set_voice(v),
                checked=lambda item, v=voice: self.state.selected_voice == v,
                radio=True,
            )
            for voice, label in VOICE_OPTIONS
        ]

        return Menu(
            MenuItem(lambda _: self._status_text(), lambda _: None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(
                lambda _: f"Leer portapapeles ({PRIMARY_HOTKEY} / {FALLBACK_HOTKEY})",
                lambda _: self._speak_clipboard(),
            ),
            MenuItem("Probar lectura ahora", lambda _: self._speak_clipboard()),
            MenuItem("Detener audio", lambda _: self._on_popup_stop()),
            MenuItem("Pausar audio", lambda _: self._on_popup_pause()),
            MenuItem("Reanudar audio", lambda _: self._on_popup_play()),
            MenuItem("Mostrar control de audio", lambda _: self._show_audio_control_popup()),
            MenuItem("Probar audio local", lambda _: self._play_local_test_audio()),
            MenuItem("Diagnostico: endpoint Kokoro", lambda _: self._diagnose_endpoint()),
            MenuItem("Iniciar Kokoro", lambda _: self._start_kokoro()),
            MenuItem("Parar Kokoro", lambda _: self._stop_kokoro()),
            MenuItem("Voz", Menu(*voice_items)),
            Menu.SEPARATOR,
            MenuItem("Salir", lambda _: self._quit()),
        )

    def _status_text(self) -> str:
        with self.lock:
            err = f" | Error: {self.state.last_error}" if self.state.last_error else ""
            hk = "on" if self.state.hotkeys_registered else "off"
            return (
                f"Servicio={self.state.service_status} | Habla={self.state.speech_status} "
                f"| Voz={self.state.selected_voice} | Vel={self.state.playback_speed:.2f}x "
                f"| Hotkey={hk} | TTSms={self.state.tts_ms}{err}"
            )

    def _set_voice(self, voice: str, restart_if_active: bool = False) -> None:
        should_restart = False
        restart_text = ""
        with self.lock:
            if self.state.selected_voice == voice:
                return
            self.state.selected_voice = voice
            self.state.last_error = ""
            should_restart = (
                restart_if_active
                and self.state.speech_status in ("playing", "requesting")
                and bool(self.last_text_spoken)
            )
            restart_text = self.last_text_spoken
        self._refresh_icon()
        self._update_audio_popup()
        self._notify(f"Voz activa: {voice}")

        if should_restart and restart_text:
            self._cancel_current_request()
            self._stop_audio(reset_state=True)
            self._notify(f"Reiniciando lectura con voz {voice}")
            threading.Thread(target=self._speak_text, args=(restart_text,), daemon=True).start()

    def _on_hotkey(self) -> None:
        now = time.perf_counter()
        if now - self.last_hotkey_ts < 0.12:
            return
        self.last_hotkey_ts = now
        self._show_audio_control_popup()
        winsound.MessageBeep(0x00000040)
        # Delay avoids race with Ctrl+C/selection updates in some apps.
        threading.Timer(0.18, lambda: threading.Thread(target=self._speak_clipboard, daemon=True).start()).start()

    def _show_audio_control_popup(self) -> None:
        if not getattr(self, "audio_popup", None):
            return
        with self.lock:
            speed = self.state.playback_speed
            speech = self.state.speech_status
            voice = self.state.selected_voice
            err = self.state.last_error
        self.audio_popup.show_popup(speed, speech, voice, err)

    def _update_audio_popup(self) -> None:
        if not getattr(self, "audio_popup", None):
            return
        with self.lock:
            speed = self.state.playback_speed
            speech = self.state.speech_status
            voice = self.state.selected_voice
            err = self.state.last_error
        self.audio_popup.update_state(speed, speech, voice, err)
        if speech == "idle":
            self.audio_popup.hide_popup_after_idle(timeout_ms=1500)

    def _cancel_current_request(self) -> None:
        with self.lock:
            self.current_request_id += 1

    def _on_popup_stop(self) -> None:
        self._cancel_current_request()
        self._stop_audio(reset_state=True)
        logging.info("Audio stopped by user")

    def _on_popup_pause(self) -> None:
        should_pause = False
        with self.lock:
            should_pause = self.state.speech_status == "playing"
        if not should_pause:
            return
        self._cancel_current_request()
        self._stop_audio(reset_state=False)
        with self.lock:
            self.state.speech_status = "paused"
        self._refresh_icon()
        self._update_audio_popup()
        logging.info("Audio paused by user")

    def _on_popup_play(self) -> None:
        with self.lock:
            can_resume = self.state.speech_status == "paused" and bool(self.last_text_spoken)
            resume_text = self.last_text_spoken
        if not can_resume:
            self._notify("No hay audio pausado para reanudar.")
            return
        with self.lock:
            self.state.speech_status = "idle"
        self._refresh_icon()
        self._update_audio_popup()
        threading.Thread(target=self._speak_text, args=(resume_text,), daemon=True).start()
        logging.info("Audio resumed by user")

    def _on_voice_changed_from_popup(self, voice: str) -> None:
        self._set_voice(voice, restart_if_active=True)

    def _on_speed_changed(self, new_speed: float) -> None:
        speed = self._normalize_speed(new_speed)
        should_restart = False
        restart_text = ""
        with self.lock:
            old_speed = self.state.playback_speed
            if abs(old_speed - speed) < 1e-6:
                return
            self.state.playback_speed = speed
            should_restart = self.state.speech_status in ("playing", "requesting") and bool(self.last_text_spoken)
            restart_text = self.last_text_spoken

        self._save_config()
        self._refresh_icon()
        self._update_audio_popup()
        logging.info("Playback speed changed to %.2fx", speed)

        if should_restart and restart_text:
            self._cancel_current_request()
            self._stop_audio(reset_state=True)
            self._notify(f"Reiniciando lectura a {speed:.2f}x")
            threading.Thread(target=self._speak_text, args=(restart_text,), daemon=True).start()

    def _speak_clipboard(self) -> None:
        text = self._read_clipboard_text()
        if not text:
            self._set_error("Portapapeles vacio")
            self._notify("No hay texto en el portapapeles.")
            logging.warning("Clipboard empty when hotkey triggered")
            return
        self._speak_text(text)

    def _speak_text(self, text: str) -> None:
        clean_text = (text or "").replace("\x00", "").strip()
        if not clean_text:
            self._set_error("Texto vacio")
            return

        if not self._is_kokoro_healthy():
            self._set_error("Kokoro no operativo")
            self._notify("Kokoro no responde. Usa 'Iniciar Kokoro' o revisa endpoint.")
            logging.warning("Kokoro unhealthy before TTS request")
            return

        with self.lock:
            self.last_text_spoken = clean_text
            self.current_request_id += 1
            request_id = self.current_request_id
            voice = self.state.selected_voice
            speed = self.state.playback_speed
            self.state.speech_status = "requesting"
            self.state.last_error = ""
            self.state.tts_ms = "-"

        self._stop_audio(reset_state=False)
        self._refresh_icon()
        self._update_audio_popup()

        payload = {
            "model": "tts-1",
            "input": clean_text,
            "voice": voice,
            "response_format": "wav",
            "speed": speed,
        }
        url = f"{KOKORO_BASE_URL}/audio/speech"

        try:
            response = self.http.post(url, json=payload)
            if response.status_code != 200:
                detail = (response.text or "")[:250]
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            with self.lock:
                if request_id != self.current_request_id:
                    return
                self.state.tts_ms = response.headers.get("X-TTS-Ms", "-")
                self.state.speech_status = "playing"
            self._refresh_icon()
            self._update_audio_popup()
            self._play_wav_bytes(response.content, request_id)
        except Exception as exc:
            self._set_error(f"TTS fallo: {exc}")
            self._notify("Error de TTS. Revisa estado del servicio.")
            logging.exception("TTS request/playback failed")
            return

        logging.info("TTS played; chars=%s voice=%s speed=%.2f", len(clean_text), voice, speed)

    def _play_local_test_audio(self) -> None:
        try:
            wav_bytes = self._build_test_tone_wav()
            with self.lock:
                self.current_request_id += 1
                request_id = self.current_request_id
                self.state.speech_status = "playing"
                self.state.last_error = ""
            self._refresh_icon()
            self._update_audio_popup()
            self._play_wav_bytes(wav_bytes, request_id)
            self._notify("Audio local OK")
            logging.info("Local test audio played")
        except Exception as exc:
            self._set_error(f"Test audio fallo: {exc}")
            self._notify("No se pudo reproducir audio local")
            logging.exception("Local test audio failed")

    def _build_test_tone_wav(self, duration_ms: int = 450, frequency_hz: float = 660.0) -> bytes:
        sample_rate = 24000
        n_samples = int(sample_rate * duration_ms / 1000)
        amp = 11000
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = bytearray()
            for i in range(n_samples):
                v = int(amp * math.sin(2 * math.pi * frequency_hz * (i / sample_rate)))
                frames.extend(struct.pack("<h", v))
            wf.writeframes(bytes(frames))
        return buffer.getvalue()

    def _wav_duration_seconds(self, wav_bytes: bytes) -> float:
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                frame_rate = wf.getframerate() or 1
                frames = wf.getnframes()
                return max(0.05, frames / float(frame_rate))
        except Exception:
            return 1.0

    def _play_wav_bytes(self, wav_bytes: bytes, request_id: int) -> None:
        self._stop_audio(reset_state=False)
        self._cleanup_old_audio_files(max_keep=12)
        target = TEMP_AUDIO_DIR / f"tts_{int(time.time() * 1000)}.wav"
        target.write_bytes(wav_bytes)
        duration = self._wav_duration_seconds(wav_bytes)
        with self.lock:
            self.current_audio_file = target
        winsound.PlaySound(
            str(target),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
        threading.Thread(
            target=self._finish_playback_after_delay,
            args=(request_id, target, duration),
            daemon=True,
        ).start()

    def _finish_playback_after_delay(self, request_id: int, target: Path, duration: float) -> None:
        time.sleep(max(0.10, duration + 0.10))
        should_refresh = False
        with self.lock:
            if request_id != self.current_request_id:
                return
            if self.current_audio_file != target:
                return
            self.current_audio_file = None
            if self.state.speech_status == "playing":
                self.state.speech_status = "idle"
            should_refresh = True
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        if should_refresh:
            self._refresh_icon()
            self._update_audio_popup()

    def _cleanup_old_audio_files(self, max_keep: int = 12) -> None:
        try:
            files = sorted(
                TEMP_AUDIO_DIR.glob("tts_*.wav"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for f in files[max_keep:]:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception:
            pass

    def _read_clipboard_text(self) -> str:
        # Clipboard can take a few milliseconds to update after Ctrl+C.
        for _ in range(8):
            text = self._read_clipboard_text_once()
            if text:
                return text
            time.sleep(0.15)
        return ""

    def _read_clipboard_text_once(self) -> str:
        try:
            text = (pyperclip.paste() or "").replace("\x00", "").strip()
            if text:
                return text
        except Exception:
            logging.exception("pyperclip.paste failed")

        # Fallback for environments where pyperclip hook is unreliable.
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            text = (result.stdout or "").replace("\x00", "").strip()
            if text:
                return text
        except Exception:
            logging.exception("Get-Clipboard fallback failed")
        return ""

    def _start_kokoro(self) -> None:
        if self._is_kokoro_healthy():
            self._set_service_status("on")
            self._notify("Kokoro ya estaba operativo.")
            return

        if not RUN_KOKORO_SCRIPT.exists():
            self._set_error(f"No existe {RUN_KOKORO_SCRIPT}")
            return

        with self.lock:
            self.state.service_status = "starting"
            self.state.last_error = ""
        self._refresh_icon()

        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUN_KOKORO_SCRIPT),
        ]
        try:
            self.kokoro_process = subprocess.Popen(
                cmd,
                cwd=str(INFERENCE_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self.started_by_app = True
            logging.info("Kokoro start requested; pid=%s", self.kokoro_process.pid)
        except Exception as exc:
            self._set_error(f"No se pudo iniciar Kokoro: {exc}")
            logging.exception("Kokoro start failed")
            return

        for _ in range(30):
            if self._is_kokoro_healthy():
                self._set_service_status("on")
                self._notify("Kokoro iniciado.")
                return
            time.sleep(1)

        self._set_error("Timeout iniciando Kokoro")
        logging.error("Kokoro start timeout")

    def _stop_kokoro(self) -> None:
        if not self._confirm_stop():
            return

        stopped = False
        if self.started_by_app and self.kokoro_process and self.kokoro_process.poll() is None:
            stopped = self._kill_pid_tree(self.kokoro_process.pid)

        if not stopped:
            pid = self._pid_listening_on_8882()
            if pid:
                stopped = self._kill_pid_tree(pid)

        if stopped:
            with self.lock:
                self.state.service_status = "off"
                self.state.last_error = ""
            self._notify("Kokoro detenido.")
            logging.info("Kokoro stopped")
        else:
            self._set_error("No se pudo detener Kokoro o no habia proceso escuchando en 8882")
            logging.warning("Kokoro stop failed")

        self._refresh_icon()

    def _health_loop(self) -> None:
        previous = None
        while self.running:
            healthy = self._is_kokoro_healthy()
            status = "on" if healthy else "off"
            with self.lock:
                if self.state.service_status != "starting":
                    self.state.service_status = status
                if self.state.speech_status == "playing" and not healthy:
                    self.state.speech_status = "error"
                    self.state.last_error = "Servicio no disponible"
            if previous != status:
                self._refresh_icon()
                self._update_audio_popup()
                previous = status
            time.sleep(3)

    def _is_kokoro_healthy(self) -> bool:
        try:
            response = self.http.get(KOKORO_HEALTH_URL, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    def _diagnose_endpoint(self) -> None:
        healthy = self._is_kokoro_healthy()
        if healthy:
            self._notify("Kokoro OK en 192.168.37.1:8882")
            logging.info("Endpoint diagnose: healthy")
        else:
            self._notify("Kokoro NO responde en 192.168.37.1:8882")
            logging.warning("Endpoint diagnose: unhealthy")

    def _pid_listening_on_8882(self) -> Optional[int]:
        try:
            output = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return None

        for line in output.splitlines():
            row = " ".join(line.split())
            if ":8882" in row and "LISTENING" in row:
                parts = row.split(" ")
                try:
                    return int(parts[-1])
                except Exception:
                    return None
        return None

    def _kill_pid_tree(self, pid: int) -> bool:
        try:
            subprocess.check_call(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def _confirm_stop(self) -> bool:
        message = (
            "Vas a detener Kokoro en 192.168.37.1:8882.\n"
            "Esto afectara a todos los servicios que usan ese endpoint.\n\n"
            "Quieres continuar?"
        )
        title = "Confirmacion fuerte - Parar Kokoro"
        flags = 0x00000004 | 0x00000030 | 0x00000100  # YESNO + ICONWARNING + DEFBUTTON2
        result = ctypes.windll.user32.MessageBoxW(None, message, title, flags)
        return result == 6  # IDYES

    def _stop_audio(self, reset_state: bool = True) -> None:
        winsound.PlaySound(None, 0)
        with self.lock:
            old = self.current_audio_file
            self.current_audio_file = None
            if reset_state:
                self.state.speech_status = "idle"
        if old is not None:
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass
        if reset_state:
            self._refresh_icon()
            self._update_audio_popup()

    def _set_service_status(self, status: str) -> None:
        with self.lock:
            self.state.service_status = status
            self.state.last_error = ""
        self._refresh_icon()
        self._update_audio_popup()

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.state.last_error = message
            if self.state.speech_status != "requesting":
                self.state.speech_status = "error"
        logging.error(message)
        self._refresh_icon()
        self._update_audio_popup()

    def _refresh_icon(self) -> None:
        if not self.icon:
            return
        # Avoid heavy icon/menu mutations from worker threads (can throw WinError 1402 on pystray/win32).
        try:
            self.icon.title = self._status_text()
        except Exception:
            logging.exception("Icon refresh failed")

    def _notify(self, message: str) -> None:
        if not self.icon:
            return
        try:
            self.icon.notify(message, "Kokoro Tray TTS")
        except Exception:
            pass

    def _quit(self) -> None:
        self.running = False
        self._cancel_current_request()
        self._stop_audio(reset_state=True)
        try:
            if self.hotkey_thread_id:
                ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, WM_QUIT, 0, 0)
        except Exception:
            pass
        try:
            self.http.close()
        except Exception:
            pass
        try:
            if getattr(self, "audio_popup", None):
                self.audio_popup.shutdown()
        except Exception:
            logging.exception("Popup shutdown failed")
        if self.icon:
            self.icon.stop()

    def _build_icon(self, status: str) -> Image.Image:
        color_map = {
            "on": (0, 170, 80),
            "off": (100, 100, 100),
            "starting": (220, 150, 0),
            "playing": (0, 120, 220),
            "paused": (160, 110, 0),
            "error": (200, 30, 30),
        }
        color = color_map.get(status, (100, 100, 100))
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=color)
        draw.ellipse((20, 20, 44, 44), fill=(255, 255, 255, 210))
        return img


if __name__ == "__main__":
    TrayTTSApp().run()
