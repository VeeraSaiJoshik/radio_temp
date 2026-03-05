"""
Radiology Copilot — Screenshot Capture
Uses mss for fast screen capture, encodes to base64 JPEG.
"""

import base64
import hashlib
import io
import platform

import mss
from PIL import Image

import config


def check_screen_recording_permission() -> bool:
    """
    On macOS 10.15+, mss requires Screen Recording permission.
    Returns True if capture works, False if it fails (permission likely missing).
    """
    try:
        with mss.mss() as sct:
            sct.grab(sct.monitors[1])
        return True
    except Exception:
        return False


def capture_screen(monitor_index: int = 1) -> tuple[str, str]:
    """
    Capture the screen and return (base64_jpeg, image_hash).

    Args:
        monitor_index: Which monitor to capture (1 = primary, 0 = all).

    Returns:
        Tuple of (base64-encoded JPEG string, SHA256 hash of the image bytes).
    """
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        raw = sct.grab(monitor)

        # Convert to PIL Image → JPEG bytes
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=config.SCREENSHOT_JPEG_QUALITY)
        jpeg_bytes = buf.getvalue()

    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    img_hash = hashlib.sha256(jpeg_bytes).hexdigest()[:16]

    return b64, img_hash


def get_permission_instructions() -> str:
    """Return platform-specific instructions for granting screen capture permission."""
    if platform.system() == "Darwin":
        return (
            "Screen Recording permission required.\n"
            "Go to: System Settings → Privacy & Security → Screen Recording\n"
            "Enable access for this application, then restart."
        )
    return "Screen capture permission may be required by your OS."
