"""
Radiology Copilot — Configuration
All settings in one place. Change BACKEND_URL to point to your real MCP server when ready.
"""

import os
from pathlib import Path


def _load_local_env() -> None:
    """Load simple KEY=VALUE pairs from the repo-local .env file if present."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

# ── Backend ──────────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("RADCOPILOT_BACKEND_URL", "http://127.0.0.1:8100")
ANALYZE_ENDPOINT = f"{BACKEND_URL}/analyze"
FLAG_ENDPOINT = f"{BACKEND_URL}/flag"
REQUEST_TIMEOUT = 8  # seconds

# ── Electron Bridge ──────────────────────────────────────────────────────────
DESKTOP_BRIDGE_HOST = os.getenv("RADCOPILOT_BRIDGE_HOST", "127.0.0.1")
DESKTOP_BRIDGE_PORT = int(os.getenv("RADCOPILOT_BRIDGE_PORT", "38100"))
DESKTOP_HOTKEY = os.getenv("RADCOPILOT_HOTKEY", "CommandOrControl+Shift+R")

# ── Overlay (compact floating panel) ─────────────────────────────────────────
PANEL_WIDTH = 700
PANEL_IDLE_HEIGHT = 44
OVERLAY_MARGIN_RIGHT = 30   # px from right edge of screen
AUTO_DISMISS_SECONDS = 15   # overlay auto-hides after this many seconds (0 = never)

# ── Orb + Panel Mode ────────────────────────────────────────────────────────
ORB_SIZE = 52              # inner orb diameter
ORB_WIDGET_SIZE = 72       # total size including glow halo
ORB_MARGIN_RIGHT = 30
ORB_MARGIN_BOTTOM = 60
PANEL_GAP = 12
PANEL_MAX_HEIGHT = 560
OVERLAY_MODE = "orb"       # "orb" or "bar"
BAR_WIDTH = 700            # Horizon-style wide top bar
ANIM_FPS = 30              # orb animation framerate

# Legacy aliases (used by older code paths)
OVERLAY_WIDTH = PANEL_WIDTH
OVERLAY_HEIGHT = PANEL_IDLE_HEIGHT
OVERLAY_OPACITY = 0.92
OVERLAY_MARGIN_BOTTOM = 60

# ── Capture ──────────────────────────────────────────────────────────────────
HOTKEY = "<cmd>+<shift>+r"  # legacy PyQt/pynput accelerator
TIMER_INTERVAL_SECONDS = 0  # 0 = timer disabled; set e.g. 30 for auto-capture every 30s
SCREENSHOT_JPEG_QUALITY = 85

# ── Gemini Live Scaffold ─────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_LIVE_MODEL = os.getenv(
    "GEMINI_LIVE_MODEL",
    "gemini-2.5-flash-native-audio-preview-12-2025",
)
GEMINI_TRANSCRIBE_MODEL = os.getenv("GEMINI_TRANSCRIBE_MODEL", "gemini-2.5-flash")
LIVE_TRANSCRIBE_BACKEND = os.getenv("LIVE_TRANSCRIBE_BACKEND", "auto")  # auto | gemini | google_cloud_speech
LIVE_TRANSCRIBE_LANGUAGE_CODES = tuple(
    code.strip() for code in os.getenv("LIVE_TRANSCRIBE_LANGUAGE_CODES", "").split(",") if code.strip()
)
GOOGLE_CLOUD_SPEECH_MODEL = os.getenv("GOOGLE_CLOUD_SPEECH_MODEL", "latest_short")
LIVE_SCREEN_WS_URL = os.getenv("LIVE_SCREEN_WS_URL", "ws://127.0.0.1:8100/live/screenshot")
LIVE_PREVIEW_FPS = float(os.getenv("LIVE_PREVIEW_FPS", "2"))
LIVE_PREVIEW_MAX_WIDTH = int(os.getenv("LIVE_PREVIEW_MAX_WIDTH", "960"))
LIVE_PREVIEW_JPEG_QUALITY = int(os.getenv("LIVE_PREVIEW_JPEG_QUALITY", "70"))
LIVE_SCREEN_MONITOR_INDEX = int(os.getenv("LIVE_SCREEN_MONITOR_INDEX", "1"))
LIVE_SCREEN_ACK_TIMEOUT_SECONDS = float(os.getenv("LIVE_SCREEN_ACK_TIMEOUT_SECONDS", "5"))
LIVE_SCREEN_WS_RETRY_SECONDS = float(os.getenv("LIVE_SCREEN_WS_RETRY_SECONDS", "1.5"))
LIVE_VOICE_NAME = os.getenv("LIVE_VOICE_NAME", "Kore")
LIVE_MIC_MODE = os.getenv("LIVE_MIC_MODE", "continuous")  # "continuous" (always-on voice agent)
LIVE_MIC_SAMPLE_RATE = int(os.getenv("LIVE_MIC_SAMPLE_RATE", "16000"))
LIVE_MIC_CAPTURE_SAMPLE_RATE = int(os.getenv("LIVE_MIC_CAPTURE_SAMPLE_RATE", "0"))
LIVE_MIC_CHUNK_MS = int(os.getenv("LIVE_MIC_CHUNK_MS", "20"))
LIVE_VAD_MIN_RMS = int(os.getenv("LIVE_VAD_MIN_RMS", "180"))
LIVE_VAD_START_MULTIPLIER = float(os.getenv("LIVE_VAD_START_MULTIPLIER", "2.8"))
LIVE_VAD_END_MULTIPLIER = float(os.getenv("LIVE_VAD_END_MULTIPLIER", "1.8"))
LIVE_VAD_START_CHUNKS = int(os.getenv("LIVE_VAD_START_CHUNKS", "3"))
LIVE_VAD_PREROLL_MS = int(os.getenv("LIVE_VAD_PREROLL_MS", "180"))
LIVE_VAD_MIN_SPEECH_MS = int(os.getenv("LIVE_VAD_MIN_SPEECH_MS", "120"))
LIVE_VAD_SILENCE_MS = int(os.getenv("LIVE_VAD_SILENCE_MS", "700"))
LIVE_VAD_MAX_SPEECH_MS = int(os.getenv("LIVE_VAD_MAX_SPEECH_MS", "12000"))
LIVE_CONTEXT_TRIGGER_TOKENS = int(os.getenv("LIVE_CONTEXT_TRIGGER_TOKENS", "24576"))
LIVE_CONTEXT_TARGET_TOKENS = int(os.getenv("LIVE_CONTEXT_TARGET_TOKENS", "16384"))

# ── Storage ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("RADCOPILOT_DB", os.path.join(os.path.dirname(__file__), "radcopilot.db"))

# ── Mock Server ──────────────────────────────────────────────────────────────
MOCK_SERVER_PORT = 8100
