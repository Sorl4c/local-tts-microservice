from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import logging
import math
import struct
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx
import pyperclip
from PySide6.QtCore import QObject, QPoint, QSize, Qt, QTimer, Signal, Slot, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
INFERENCE_DIR = ROOT_DIR / "inference_v2"
RUN_KOKORO_SCRIPT = INFERENCE_DIR / "run_kokoro.ps1"
BASE_DIR = INFERENCE_DIR / "tray_tts_qt"
LOG_PATH = BASE_DIR / "tray_tts_qt.log"
TEMP_AUDIO_DIR = BASE_DIR / "tmp_audio"
CONFIG_PATH = BASE_DIR / "config.json"

KOKORO_BASE_URL = "http://192.168.37.1:8882/v1"
KOKORO_HEALTH_URL = "http://192.168.37.1:8882/healthz"

VOICE_OPTIONS = [
    ("ef_dora", "ef_dora (Femenino)"),
    ("em_alex", "em_alex (Masculino)"),
    ("em_santa", "em_santa (Especial)"),
]
VOICE_LABEL_TO_ID = {label: voice for voice, label in VOICE_OPTIONS}
VOICE_ID_TO_LABEL = {voice: label for voice, label in VOICE_OPTIONS}

PRIMARY_HOTKEY = "ctrl+shift+y"
FALLBACK_HOTKEY = "ctrl+alt+y"

DEFAULT_SPEED = 1.0
MIN_SPEED = 0.60
MAX_SPEED = 2.00
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
    playback_speed: float = DEFAULT_SPEED
    last_error: str = ""
    tts_ms: str = "-"
    hotkeys_registered: bool = False
    duration_ms: int = 0
    position_ms: int = 0


class HotkeyListener(threading.Thread):
    def __init__(
        self,
        on_hotkey: Callable[[], None],
        on_registered: Callable[[bool], None],
        on_error: Callable[[str], None],
    ) -> None:
        super().__init__(daemon=True)
        self._on_hotkey = on_hotkey
        self._on_registered = on_registered
        self._on_error = on_error
        self._running = True
        self._thread_id: Optional[int] = None

    def run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            self._thread_id = int(kernel32.GetCurrentThreadId())
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
            self._on_registered(ok1 or ok2)
            logging.info("Hotkeys registered via RegisterHotKey: primary=%s fallback=%s", ok1, ok2)
            if not (ok1 or ok2):
                self._on_error("No se pudieron registrar hotkeys globales")
                return

            msg = wintypes.MSG()
            while self._running:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY and msg.wParam in (HOTKEY_ID_PRIMARY, HOTKEY_ID_FALLBACK):
                    self._on_hotkey()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self._on_registered(False)
            self._on_error(f"No se pudieron registrar hotkeys: {exc}")
            logging.exception("Win32 hotkey loop failed")
        finally:
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID_PRIMARY)
            except Exception:
                pass
            try:
                user32.UnregisterHotKey(None, HOTKEY_ID_FALLBACK)
            except Exception:
                pass

    def stop(self) -> None:
        self._running = False
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass


class AudioControlPopup(QWidget):
    stop_clicked = Signal()
    pause_clicked = Signal()
    play_clicked = Signal()
    speed_changed = Signal(float)
    voice_changed = Signal(str)
    seek_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._suppress_speed_emit = False
        self._is_dragging_seek = False
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        self.setWindowTitle("Kokoro Audio")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(430, 250)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        self.card = QWidget(self)
        self.card.setObjectName("popupCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 102))
        shadow.setOffset(0, 4)
        self.card.setGraphicsEffect(shadow)
        root.addWidget(self.card)

        content = QVBoxLayout(self.card)
        content.setContentsMargins(20, 20, 20, 20)
        content.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.status_dot = QLabel("")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(10, 10)
        self.status_text = QLabel("DETENIDO")
        self.status_text.setObjectName("statusText")
        self.close_button = QPushButton("x")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedWidth(28)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.hide)
        header.addWidget(self.status_dot)
        header.addWidget(self.status_text, 1)
        header.addWidget(self.close_button)

        controls = QHBoxLayout()
        controls.setSpacing(16)
        controls.setAlignment(Qt.AlignCenter)
        self.stop_button = self._build_media_button("stop")
        self.pause_button = self._build_media_button("pause")
        self.play_button = self._build_media_button("play", primary=True)
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        self.play_button.clicked.connect(self.play_clicked.emit)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.play_button)

        times = QHBoxLayout()
        times.setSpacing(8)
        self.time_current = QLabel("00:00")
        self.time_current.setObjectName("timeLabel")
        self.time_total = QLabel("00:00")
        self.time_total.setObjectName("timeLabel")
        times.addWidget(self.time_current)
        times.addStretch(1)
        times.addWidget(self.time_total)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.valueChanged.connect(self._on_seek_value_changed)

        speed_line = QHBoxLayout()
        speed_line.setSpacing(8)
        speed_title = QLabel("Velocidad")
        speed_title.setObjectName("captionLabel")
        self.speed_label = QLabel("1.00x")
        self.speed_label.setObjectName("speedValue")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setObjectName("speedSlider")
        self.speed_slider.setRange(int(MIN_SPEED * 100), int(MAX_SPEED * 100))
        self.speed_slider.setSingleStep(int(SPEED_STEP * 100))
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        speed_line.addWidget(speed_title)
        speed_line.addWidget(self.speed_slider, 1)
        speed_line.addWidget(self.speed_label)

        voice_line = QHBoxLayout()
        voice_line.setSpacing(8)
        voice_title = QLabel("Voz")
        voice_title.setObjectName("captionLabel")
        voice_line.addWidget(voice_title)
        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("voiceCombo")
        for _, label in VOICE_OPTIONS:
            self.voice_combo.addItem(label)
        self.voice_combo.currentTextChanged.connect(self._on_voice_changed)
        voice_line.addWidget(self.voice_combo, 1)

        content.addLayout(header)
        content.addLayout(controls)
        content.addLayout(times)
        content.addWidget(self.seek_slider)
        content.addLayout(speed_line)
        content.addLayout(voice_line)
        self._apply_styles()

    def _build_media_button(self, kind: str, primary: bool = False) -> QPushButton:
        button = QPushButton("")
        button.setObjectName("primaryMediaButton" if primary else "mediaButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedSize(56, 56)
        button.setIcon(self._build_media_icon(kind, QColor("#00FF66")))
        button.setIconSize(QSize(22, 22))
        return button

    def _build_media_icon(self, kind: str, color: QColor) -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(color, 2))
        painter.setBrush(Qt.NoBrush)
        if kind == "stop":
            painter.drawRoundedRect(6, 6, 12, 12, 2, 2)
        elif kind == "pause":
            painter.drawRoundedRect(7, 5, 4, 14, 2, 2)
            painter.drawRoundedRect(13, 5, 4, 14, 2, 2)
        else:
            painter.drawPolygon(QPolygon([QPoint(8, 5), QPoint(18, 12), QPoint(8, 19)]))
        painter.end()
        return QIcon(pixmap)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                color: #EFEFEF;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QWidget#popupCard {
                background-color: #0D0D0D;
                border: 1px solid #1F1F1F;
                border-radius: 22px;
            }
            QLabel#statusText {
                color: #DADADA;
                font-size: 12px;
                letter-spacing: 1px;
            }
            QLabel#statusDot {
                background-color: #00FF66;
                border-radius: 5px;
            }
            QLabel#timeLabel {
                color: #9A9A9A;
                font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
            QLabel#captionLabel {
                color: #666666;
                min-width: 60px;
            }
            QLabel#speedValue {
                color: #EFEFEF;
                font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
                font-size: 12px;
                min-width: 52px;
            }
            QPushButton#closeButton {
                background: transparent;
                color: #5A5A5A;
                border: none;
                font-size: 14px;
                border-radius: 8px;
            }
            QPushButton#closeButton:hover {
                background: #1A1A1A;
                color: #B0B0B0;
            }
            QPushButton#mediaButton {
                background-color: #161616;
                border: 1px solid #242424;
                border-radius: 28px;
                padding: 0px;
            }
            QPushButton#mediaButton:hover {
                background-color: #1D1D1D;
                border-color: #2F2F2F;
            }
            QPushButton#primaryMediaButton {
                background-color: #152217;
                border: 1px solid #24532E;
                border-radius: 28px;
                padding: 0px;
            }
            QPushButton#primaryMediaButton:hover {
                background-color: #19321F;
                border-color: #2C7A3C;
            }
            QSlider#seekSlider::groove:horizontal,
            QSlider#speedSlider::groove:horizontal {
                border: none;
                background: #222222;
                border-radius: 2px;
            }
            QSlider#seekSlider::groove:horizontal {
                height: 4px;
            }
            QSlider#speedSlider::groove:horizontal {
                height: 3px;
            }
            QSlider#seekSlider::sub-page:horizontal,
            QSlider#speedSlider::sub-page:horizontal {
                background: #00FF66;
                border-radius: 2px;
            }
            QSlider#seekSlider::add-page:horizontal,
            QSlider#speedSlider::add-page:horizontal {
                background: #222222;
                border-radius: 2px;
            }
            QSlider#seekSlider::handle:horizontal,
            QSlider#speedSlider::handle:horizontal {
                background: #00FF66;
                border: none;
                width: 12px;
                margin: -5px 0;
                border-radius: 6px;
            }
            QComboBox#voiceCombo {
                background-color: #141414;
                color: #EFEFEF;
                border: 1px solid #232323;
                border-radius: 10px;
                padding: 7px 12px;
            }
            QComboBox#voiceCombo:hover {
                border-color: #2F2F2F;
            }
            QComboBox#voiceCombo:focus {
                border-color: #00FF66;
            }
            QComboBox#voiceCombo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#voiceCombo QAbstractItemView {
                background: #0D0D0D;
                border: 1px solid #232323;
                color: #EFEFEF;
                selection-background-color: #1A1A1A;
                selection-color: #EFEFEF;
                outline: 0;
            }
            """
        )

    def _format_ms(self, ms: int) -> str:
        sec = max(0, int(ms / 1000))
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def _status_color(self, status: str) -> str:
        colors = {
            "idle": "#6B7280",
            "requesting": "#FBBF24",
            "playing": "#34D399",
            "paused": "#60A5FA",
            "error": "#F87171",
        }
        return colors.get(status, "#6B7280")

    def set_popup_state(
        self,
        speech_status: str,
        last_error: str,
        playback_speed: float,
        selected_voice: str,
        position_ms: int,
        duration_ms: int,
    ) -> None:
        status_label = {
            "idle": "DETENIDO",
            "requesting": "GENERANDO...",
            "playing": "REPRODUCIENDO",
            "paused": "PAUSADO",
            "error": "ERROR",
        }.get(speech_status, speech_status)
        if speech_status == "error" and last_error:
            status_label = f"ERROR: {last_error[:36]}"

        self.status_text.setText(status_label)
        self.status_dot.setStyleSheet(
            f"background-color: {self._status_color(speech_status)}; border-radius: 5px;"
        )

        speed_value = int(round(playback_speed * 100))
        self._suppress_speed_emit = True
        self.speed_slider.setValue(speed_value)
        self._suppress_speed_emit = False
        self.speed_label.setText(f"{playback_speed:.2f}x")

        voice_label = VOICE_ID_TO_LABEL.get(selected_voice, selected_voice)
        if self.voice_combo.currentText() != voice_label:
            self.voice_combo.setCurrentText(voice_label)

        safe_duration = max(0, int(duration_ms))
        safe_position = max(0, int(position_ms))
        self.time_current.setText(self._format_ms(safe_position))
        self.time_total.setText(self._format_ms(safe_duration))
        if not self._is_dragging_seek:
            self.seek_slider.setRange(0, safe_duration if safe_duration > 0 else 0)
            self.seek_slider.setValue(min(safe_position, safe_duration))

    def show_near_cursor(self) -> None:
        screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 16
            y = geo.bottom() - self.height() - 16
            self.move(max(0, x), max(0, y))
        self.show()
        self.raise_()
        self.activateWindow()

    def auto_hide_in_idle(self, ms: int = 1500) -> None:
        if self.underMouse():
            return
        self._auto_hide_timer.start(ms)

    def cancel_auto_hide(self) -> None:
        self._auto_hide_timer.stop()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.cancel_auto_hide()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)

    def _on_speed_slider_changed(self, value: int) -> None:
        speed = max(MIN_SPEED, min(MAX_SPEED, value / 100.0))
        self.speed_label.setText(f"{speed:.2f}x")
        if not self._suppress_speed_emit:
            self.speed_changed.emit(speed)

    def _on_voice_changed(self, text: str) -> None:
        voice = VOICE_LABEL_TO_ID.get(text)
        if voice:
            self.voice_changed.emit(voice)

    def _on_seek_pressed(self) -> None:
        self._is_dragging_seek = True

    def _on_seek_released(self) -> None:
        self._is_dragging_seek = False
        self.seek_requested.emit(int(self.seek_slider.value()))

    def _on_seek_value_changed(self, value: int) -> None:
        if self._is_dragging_seek:
            self.time_current.setText(self._format_ms(value))

class TrayTTSQtApp(QObject):
    ui_refresh = Signal()
    hotkey_activated = Signal()
    playback_requested = Signal(int, str)

    def __init__(self) -> None:
        super().__init__()
        self._configure_logging()
        self.lock = threading.RLock()
        self.state = AppState()
        self.http = httpx.Client(timeout=30.0)
        self.running = True

        self.kokoro_process: Optional[subprocess.Popen] = None
        self.started_by_app = False

        self.current_request_id = 0
        self.current_audio_file: Optional[Path] = None
        self.last_text_spoken = ""
        self.last_hotkey_ts = 0.0
        self.last_speech_status = "idle"

        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        self.popup = AudioControlPopup()
        self.popup.stop_clicked.connect(self._on_popup_stop)
        self.popup.pause_clicked.connect(self._on_popup_pause)
        self.popup.play_clicked.connect(self._on_popup_play)
        self.popup.speed_changed.connect(self._on_speed_changed)
        self.popup.voice_changed.connect(self._on_voice_changed_from_popup)
        self.popup.seek_requested.connect(self._on_seek_requested)

        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.media_player.errorOccurred.connect(self._on_media_error)

        self.tray_icon = QSystemTrayIcon(self._build_icon("off"), self.qt_app)
        self.tray_icon.setToolTip("Kokoro Tray TTS (Qt)")
        self.tray_menu = QMenu()
        self._build_menu()
        self.tray_icon.setContextMenu(self.tray_menu)

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(3000)
        self.health_timer.timeout.connect(self._health_tick)

        self._load_config()
        self.ui_refresh.connect(self._refresh_ui)
        self.hotkey_activated.connect(self._on_hotkey_activated)
        self.playback_requested.connect(self._on_playback_requested)

        self.hotkey_listener = HotkeyListener(
            on_hotkey=self._on_hotkey,
            on_registered=self._on_hotkey_registered,
            on_error=self._on_hotkey_error,
        )

    def _configure_logging(self) -> None:
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(LOG_PATH),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.info("Tray Qt app starting")

    def _normalize_speed(self, value: float) -> float:
        try:
            numeric = float(value)
        except Exception:
            numeric = DEFAULT_SPEED
        numeric = max(MIN_SPEED, min(MAX_SPEED, numeric))
        stepped = round(numeric / SPEED_STEP) * SPEED_STEP
        return round(max(MIN_SPEED, min(MAX_SPEED, stepped)), 2)

    def _load_config(self) -> None:
        speed = DEFAULT_SPEED
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
                speed = self._normalize_speed(data.get("playback_speed", DEFAULT_SPEED))
            except Exception:
                logging.exception("Config load failed; using defaults")
                speed = DEFAULT_SPEED
        with self.lock:
            self.state.playback_speed = speed
        self._save_config()

    def _save_config(self) -> None:
        try:
            with self.lock:
                payload = {"playback_speed": self.state.playback_speed}
            CONFIG_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            logging.exception("Config save failed")

    def _build_icon(self, status: str) -> QIcon:
        color_map = {
            "on": QColor(0, 170, 80),
            "off": QColor(120, 120, 120),
            "starting": QColor(220, 150, 0),
            "playing": QColor(0, 120, 220),
            "error": QColor(200, 30, 30),
        }
        color = color_map.get(status, QColor(120, 120, 120))
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QColor(255, 255, 255, 210))
        painter.drawEllipse(20, 20, 24, 24)
        painter.end()
        return QIcon(pixmap)

    def _build_menu(self) -> None:
        self.action_status = QAction("Estado", self.tray_menu)
        self.action_status.setEnabled(False)
        self.tray_menu.addAction(self.action_status)
        self.tray_menu.addSeparator()

        action_read = QAction(f"Leer portapapeles ({PRIMARY_HOTKEY} / {FALLBACK_HOTKEY})", self.tray_menu)
        action_read.triggered.connect(self._trigger_speak_clipboard)
        self.tray_menu.addAction(action_read)

        action_stop_audio = QAction("Detener audio", self.tray_menu)
        action_stop_audio.triggered.connect(self._on_popup_stop)
        self.tray_menu.addAction(action_stop_audio)

        action_show_popup = QAction("Mostrar control de audio", self.tray_menu)
        action_show_popup.triggered.connect(self._show_audio_control_popup)
        self.tray_menu.addAction(action_show_popup)

        action_diagnose = QAction("Diagnostico: endpoint Kokoro", self.tray_menu)
        action_diagnose.triggered.connect(self._diagnose_endpoint)
        self.tray_menu.addAction(action_diagnose)

        action_start = QAction("Iniciar Kokoro", self.tray_menu)
        action_start.triggered.connect(self._start_kokoro)
        self.tray_menu.addAction(action_start)

        action_stop = QAction("Parar Kokoro", self.tray_menu)
        action_stop.triggered.connect(self._stop_kokoro)
        self.tray_menu.addAction(action_stop)

        voice_menu = self.tray_menu.addMenu("Voz")
        self.voice_group = QActionGroup(self.tray_menu)
        self.voice_group.setExclusive(True)
        self.voice_actions = {}
        for voice, label in VOICE_OPTIONS:
            action = QAction(label, voice_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, v=voice: self._set_voice(v, restart_if_active=False))
            voice_menu.addAction(action)
            self.voice_group.addAction(action)
            self.voice_actions[voice] = action

        self.tray_menu.addSeparator()
        action_quit = QAction("Salir", self.tray_menu)
        action_quit.triggered.connect(self._quit)
        self.tray_menu.addAction(action_quit)

    def _status_text(self) -> str:
        with self.lock:
            err = f" | Error: {self.state.last_error}" if self.state.last_error else ""
            hk = "on" if self.state.hotkeys_registered else "off"
            return (
                f"Servicio={self.state.service_status} | Habla={self.state.speech_status} "
                f"| Voz={self.state.selected_voice} | Vel={self.state.playback_speed:.2f}x "
                f"| Hotkey={hk} | TTSms={self.state.tts_ms}{err}"
            )

    @Slot()
    def _refresh_ui(self) -> None:
        self.action_status.setText(self._status_text())
        with self.lock:
            speech = self.state.speech_status
            voice = self.state.selected_voice
            err = self.state.last_error
            speed = self.state.playback_speed
            pos = self.state.position_ms
            dur = self.state.duration_ms
            service = self.state.service_status

        if voice in self.voice_actions:
            self.voice_actions[voice].setChecked(True)

        self.popup.set_popup_state(speech, err, speed, voice, pos, dur)
        if speech in ("requesting", "playing", "paused"):
            self.popup.cancel_auto_hide()
        elif speech == "idle" and self.last_speech_status in ("requesting", "playing", "paused"):
            self.popup.auto_hide_in_idle(1500)
        elif speech == "error":
            self.popup.cancel_auto_hide()

        icon_status = service
        if speech == "playing":
            icon_status = "playing"
        elif speech == "error":
            icon_status = "error"
        self.tray_icon.setIcon(self._build_icon(icon_status))
        self.last_speech_status = speech

    def _emit_refresh(self) -> None:
        self.ui_refresh.emit()

    def _notify(self, text: str) -> None:
        self.tray_icon.showMessage("Kokoro Tray TTS", text, QSystemTrayIcon.Information, 2500)

    def _on_hotkey_registered(self, ok: bool) -> None:
        with self.lock:
            self.state.hotkeys_registered = ok
            if ok:
                self.state.last_error = ""
        self._emit_refresh()

    def _on_hotkey_error(self, message: str) -> None:
        self._set_error(message)

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.state.last_error = message
            if self.state.speech_status != "requesting":
                self.state.speech_status = "error"
        logging.error(message)
        self._emit_refresh()

    def _cancel_current_request(self) -> None:
        with self.lock:
            self.current_request_id += 1

    def _set_voice(self, voice: str, restart_if_active: bool) -> None:
        should_restart = False
        restart_text = ""
        with self.lock:
            self.state.selected_voice = voice
            self.state.last_error = ""
            should_restart = restart_if_active and self.state.speech_status in ("playing", "requesting", "paused") and bool(self.last_text_spoken)
            restart_text = self.last_text_spoken
        self._emit_refresh()
        if should_restart and restart_text:
            self._cancel_current_request()
            self._stop_audio(reset_state=True)
            threading.Thread(target=self._speak_text, args=(restart_text,), daemon=True).start()

    def _show_audio_control_popup(self) -> None:
        self.popup.cancel_auto_hide()
        self.popup.show_near_cursor()
        self._emit_refresh()

    def _on_hotkey(self) -> None:
        now = time.perf_counter()
        if now - self.last_hotkey_ts < 0.12:
            return
        self.last_hotkey_ts = now
        self.hotkey_activated.emit()

    @Slot()
    def _on_hotkey_activated(self) -> None:
        self._show_audio_control_popup()
        QApplication.beep()
        # Delay avoids race with Ctrl+C/selection updates in some apps.
        threading.Timer(0.18, self._trigger_speak_clipboard).start()

    def _trigger_speak_clipboard(self) -> None:
        threading.Thread(target=self._speak_clipboard, daemon=True).start()

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
        self._emit_refresh()

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

            target = self._persist_wav(response.content)
            self.playback_requested.emit(request_id, str(target))
        except Exception as exc:
            self._set_error(f"TTS fallo: {exc}")
            self._notify("Error de TTS. Revisa estado del servicio.")
            logging.exception("TTS request/playback failed")

    def _persist_wav(self, wav_bytes: bytes) -> Path:
        self._cleanup_old_audio_files(max_keep=12)
        target = TEMP_AUDIO_DIR / f"tts_{int(time.time() * 1000)}.wav"
        target.write_bytes(wav_bytes)
        return target

    def _start_playback(self, request_id: int, wav_path: Path) -> None:
        with self.lock:
            if request_id != self.current_request_id:
                try:
                    wav_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return
            old = self.current_audio_file
            self.current_audio_file = wav_path
            self.state.speech_status = "playing"
            self.state.position_ms = 0
            self.state.duration_ms = 0

        if old and old != wav_path:
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass

        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(str(wav_path)))
        self.media_player.play()
        logging.info("TTS played; file=%s", wav_path.name)
        self._emit_refresh()

    @Slot(int, str)
    def _on_playback_requested(self, request_id: int, wav_path: str) -> None:
        self._start_playback(request_id, Path(wav_path))

    @Slot()
    def _on_popup_stop(self) -> None:
        self._cancel_current_request()
        self._stop_audio(reset_state=True)
        logging.info("Audio stopped by user")

    @Slot()
    def _on_popup_pause(self) -> None:
        with self.lock:
            if self.state.speech_status != "playing":
                return
            self.state.speech_status = "paused"
        self.media_player.pause()
        self._emit_refresh()

    @Slot()
    def _on_popup_play(self) -> None:
        with self.lock:
            status = self.state.speech_status
            has_media = self.current_audio_file is not None
            resume_text = self.last_text_spoken
        if status == "paused" and has_media:
            self.media_player.play()
            with self.lock:
                self.state.speech_status = "playing"
            self._emit_refresh()
            return
        if resume_text:
            threading.Thread(target=self._speak_text, args=(resume_text,), daemon=True).start()

    @Slot(float)
    def _on_speed_changed(self, new_speed: float) -> None:
        speed = self._normalize_speed(new_speed)
        should_restart = False
        restart_text = ""
        with self.lock:
            old_speed = self.state.playback_speed
            if abs(old_speed - speed) < 1e-6:
                return
            self.state.playback_speed = speed
            should_restart = self.state.speech_status in ("playing", "requesting", "paused") and bool(self.last_text_spoken)
            restart_text = self.last_text_spoken
        self._save_config()
        self._emit_refresh()
        logging.info("Playback speed changed to %.2fx", speed)

        if should_restart and restart_text:
            self._cancel_current_request()
            self._stop_audio(reset_state=True)
            threading.Thread(target=self._speak_text, args=(restart_text,), daemon=True).start()

    @Slot(str)
    def _on_voice_changed_from_popup(self, voice: str) -> None:
        self._set_voice(voice, restart_if_active=True)

    @Slot(int)
    def _on_seek_requested(self, position_ms: int) -> None:
        self.media_player.setPosition(max(0, int(position_ms)))

    @Slot(int)
    def _on_position_changed(self, position_ms: int) -> None:
        with self.lock:
            self.state.position_ms = int(position_ms)
        self._emit_refresh()

    @Slot(int)
    def _on_duration_changed(self, duration_ms: int) -> None:
        with self.lock:
            self.state.duration_ms = int(duration_ms)
        self._emit_refresh()

    @Slot(int)
    def _on_playback_state_changed(self, _state: int) -> None:
        # State transitions are consolidated in media status and explicit user actions.
        pass

    @Slot(int)
    def _on_media_status_changed(self, status: int) -> None:
        if status == QMediaPlayer.EndOfMedia:
            with self.lock:
                self.state.speech_status = "idle"
                self.state.position_ms = self.state.duration_ms
            self._cleanup_current_audio_file()
            self._emit_refresh()

    @Slot(QMediaPlayer.Error, str)
    def _on_media_error(self, _err, err_string: str) -> None:
        if err_string:
            self._set_error(f"Audio error: {err_string}")

    def _cleanup_current_audio_file(self) -> None:
        with self.lock:
            old = self.current_audio_file
            self.current_audio_file = None
        if old is not None:
            try:
                old.unlink(missing_ok=True)
            except Exception:
                pass

    def _stop_audio(self, reset_state: bool = True) -> None:
        self.media_player.stop()
        self._cleanup_current_audio_file()
        with self.lock:
            self.state.duration_ms = 0
            self.state.position_ms = 0
            if reset_state:
                self.state.speech_status = "idle"
        self._emit_refresh()

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

    @Slot()
    def _start_kokoro(self) -> None:
        threading.Thread(target=self._start_kokoro_worker, daemon=True).start()

    def _start_kokoro_worker(self) -> None:
        if self._is_kokoro_healthy():
            with self.lock:
                self.state.service_status = "on"
            self._emit_refresh()
            self._notify("Kokoro ya estaba operativo.")
            return

        if not RUN_KOKORO_SCRIPT.exists():
            self._set_error(f"No existe {RUN_KOKORO_SCRIPT}")
            return

        with self.lock:
            self.state.service_status = "starting"
            self.state.last_error = ""
        self._emit_refresh()

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
                with self.lock:
                    self.state.service_status = "on"
                    self.state.last_error = ""
                self._emit_refresh()
                self._notify("Kokoro iniciado.")
                return
            time.sleep(1)

        self._set_error("Timeout iniciando Kokoro")

    @Slot()
    def _stop_kokoro(self) -> None:
        if not self._confirm_stop():
            return
        threading.Thread(target=self._stop_kokoro_worker, daemon=True).start()

    def _stop_kokoro_worker(self) -> None:
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
            self._set_error("No se pudo detener Kokoro o no habia proceso en 8882")
            logging.warning("Kokoro stop failed")
        self._emit_refresh()

    def _confirm_stop(self) -> bool:
        msg = QMessageBox()
        msg.setWindowTitle("Confirmacion fuerte - Parar Kokoro")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "Vas a detener Kokoro en 192.168.37.1:8882.\n"
            "Esto afectara a todos los servicios que usan ese endpoint.\n\n"
            "Quieres continuar?"
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        return msg.exec() == QMessageBox.Yes

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

    def _is_kokoro_healthy(self) -> bool:
        try:
            response = self.http.get(KOKORO_HEALTH_URL, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    @Slot()
    def _diagnose_endpoint(self) -> None:
        healthy = self._is_kokoro_healthy()
        if healthy:
            self._notify("Kokoro OK en 192.168.37.1:8882")
            logging.info("Endpoint diagnose: healthy")
        else:
            self._notify("Kokoro NO responde en 192.168.37.1:8882")
            logging.warning("Endpoint diagnose: unhealthy")

    @Slot()
    def _health_tick(self) -> None:
        healthy = self._is_kokoro_healthy()
        with self.lock:
            if self.state.service_status != "starting":
                self.state.service_status = "on" if healthy else "off"
            if self.state.speech_status in ("playing", "requesting") and not healthy:
                self.state.speech_status = "error"
                self.state.last_error = "Servicio no disponible"
        self._emit_refresh()

    @Slot()
    def _quit(self) -> None:
        self.running = False
        try:
            self.hotkey_listener.stop()
        except Exception:
            pass
        self.health_timer.stop()
        self._stop_audio(reset_state=True)
        try:
            self.http.close()
        except Exception:
            pass
        self.tray_icon.hide()
        self.popup.hide()
        self.qt_app.quit()

    def run(self) -> int:
        self.tray_icon.show()
        self._emit_refresh()
        self.health_timer.start()
        self.hotkey_listener.start()
        return self.qt_app.exec()


def main() -> int:
    app = TrayTTSQtApp()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())

