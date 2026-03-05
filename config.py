"""
Radiology Copilot — Configuration
All settings in one place. Change BACKEND_URL to point to your real MCP server when ready.
"""

import os

# ── Backend ──────────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("RADCOPILOT_BACKEND_URL", "http://127.0.0.1:8100")
ANALYZE_ENDPOINT = f"{BACKEND_URL}/analyze"
FLAG_ENDPOINT = f"{BACKEND_URL}/flag"
REQUEST_TIMEOUT = 8  # seconds

# ── Overlay ──────────────────────────────────────────────────────────────────
OVERLAY_WIDTH = 420
OVERLAY_HEIGHT = 220
OVERLAY_OPACITY = 0.92
AUTO_DISMISS_SECONDS = 15  # overlay auto-hides after this many seconds (0 = never)
OVERLAY_MARGIN_RIGHT = 30  # px from right edge
OVERLAY_MARGIN_BOTTOM = 60  # px from bottom edge

# ── Capture ──────────────────────────────────────────────────────────────────
HOTKEY = "<cmd>+<shift>+r"  # pynput format
TIMER_INTERVAL_SECONDS = 0  # 0 = timer disabled; set e.g. 30 for auto-capture every 30s
SCREENSHOT_JPEG_QUALITY = 85

# ── Storage ──────────────────────────────────────────────────────────────────
DB_PATH = os.getenv("RADCOPILOT_DB", os.path.join(os.path.dirname(__file__), "radcopilot.db"))

# ── Mock Server ──────────────────────────────────────────────────────────────
MOCK_SERVER_PORT = 8100
