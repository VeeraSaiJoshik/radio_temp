"""
Radiology Copilot — Screenshot Capture
Uses mss for fast screen capture, encodes to base64 JPEG.
"""

from __future__ import annotations

import base64
import hashlib
import io
import platform

import mss
from PIL import Image

import config


class ScreenCapturePermissionError(RuntimeError):
    """Raised when the OS blocks screen capture."""


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


def _hash_image_bytes(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def _encode_jpeg_bytes(image: Image.Image, *, jpeg_quality: int, max_width: int | None = None) -> bytes:
    working = image.copy()
    if max_width and working.width > max_width:
        new_height = max(1, int(working.height * (max_width / working.width)))
        working = working.resize((max_width, new_height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    working.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return buf.getvalue()


def _grab_monitor_image(monitor_index: int = 1) -> Image.Image:
    with mss.mss() as sct:
        if monitor_index not in range(len(sct.monitors)):
            raise ValueError(f"Monitor index {monitor_index} is unavailable")

        raw = sct.grab(sct.monitors[monitor_index])

    return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def _capture_jpeg(
    monitor_index: int,
    *,
    jpeg_quality: int,
    max_width: int | None = None,
) -> tuple[bytes, str]:
    try:
        image = _grab_monitor_image(monitor_index)
    except ValueError:
        raise
    except Exception as exc:
        raise ScreenCapturePermissionError(get_permission_instructions()) from exc

    jpeg_bytes = _encode_jpeg_bytes(image, jpeg_quality=jpeg_quality, max_width=max_width)
    return jpeg_bytes, _hash_image_bytes(jpeg_bytes)


def encode_base64_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def capture_screen_preview(
    monitor_index: int = 1,
    *,
    max_width: int = config.LIVE_PREVIEW_MAX_WIDTH,
    jpeg_quality: int = config.LIVE_PREVIEW_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Capture a downscaled JPEG for the Gemini Live preview stream."""
    return _capture_jpeg(
        monitor_index,
        jpeg_quality=jpeg_quality,
        max_width=max_width,
    )


def capture_screen_full(
    monitor_index: int = 1,
    *,
    jpeg_quality: int = config.SCREENSHOT_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Capture a full-resolution JPEG for backend delivery."""
    return _capture_jpeg(monitor_index, jpeg_quality=jpeg_quality)


def capture_screen(monitor_index: int = 1) -> tuple[str, str]:
    """
    Capture the screen and return (base64_jpeg, image_hash).

    Args:
        monitor_index: Which monitor to capture (1 = primary, 0 = all).

    Returns:
        Tuple of (base64-encoded JPEG string, SHA256 hash of the image bytes).
    """
    jpeg_bytes, image_hash = capture_screen_full(
        monitor_index=monitor_index,
        jpeg_quality=config.SCREENSHOT_JPEG_QUALITY,
    )
    return encode_base64_image(jpeg_bytes), image_hash


def get_permission_instructions() -> str:
    """Return platform-specific instructions for granting screen capture permission."""
    if platform.system() == "Darwin":
        return (
            "Screen Recording permission required.\n"
            "Go to: System Settings → Privacy & Security → Screen Recording\n"
            "Enable access for this application, then restart."
        )
    return "Screen capture permission may be required by your OS."
