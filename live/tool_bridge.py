"""Gemini Live tool handler for discrete full-resolution screenshots."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Mapping

import config
from capture.screenshot import (
    ScreenCapturePermissionError,
    capture_screen_full,
    encode_base64_image,
)
from live.local_ws import AckTimeoutError, LocalWebSocketUnavailable

TAKE_SCREENSHOT_DECLARATION = {
    "name": "take_screenshot",
    "description": (
        "Capture a full-resolution screenshot of the current user screen and send it "
        "to the local backend. Returns only delivery status and metadata, never image data."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
        },
        "required": ["reason"],
    },
}


class ScreenshotToolBridge:
    """Executes Gemini `take_screenshot` tool calls against the local backend."""

    def __init__(
        self,
        session_id: str,
        transport,
        *,
        monitor_index: int = config.LIVE_SCREEN_MONITOR_INDEX,
        capture_func=capture_screen_full,
        capture_sink=None,
        result_sink=None,
    ):
        self.session_id = session_id
        self.transport = transport
        self.monitor_index = monitor_index
        self.capture_func = capture_func
        self.capture_sink = capture_sink or (lambda event: None)
        self.result_sink = result_sink or (lambda result: None)

    async def handle_tool_call(self, args: Mapping[str, Any] | None) -> dict[str, Any]:
        """Capture and ship one screenshot to the localhost websocket backend."""
        request_id = str(uuid.uuid4())
        sent_at = datetime.now(timezone.utc).isoformat()
        reason = str((args or {}).get("reason") or "Gemini requested a screenshot")

        try:
            image_bytes, image_hash = self.capture_func(monitor_index=self.monitor_index)
        except Exception as exc:
            return self._error_response(request_id, sent_at, exc)

        payload = {
            "type": "screenshot.capture",
            "request_id": request_id,
            "session_id": self.session_id,
            "timestamp": sent_at,
            "reason": reason,
            "mime_type": "image/jpeg",
            "image_b64": encode_base64_image(image_bytes),
            "image_hash": image_hash,
            "source": "gemini_live_tool",
        }
        self.capture_sink(
            {
                "request_id": request_id,
                "sent_at": sent_at,
                "reason": reason,
                "image_hash": image_hash,
                "image_bytes": image_bytes,
                "backend_status": "pending",
                "error": None,
            }
        )

        try:
            ack = await self.transport.send_capture(payload)
        except Exception as exc:
            result = self._error_response(request_id, sent_at, exc, image_hash=image_hash)
            self.result_sink(result)
            return result

        backend_status = str(ack.get("status", "ok"))
        if backend_status != "ok":
            result = {
                "status": "error",
                "request_id": request_id,
                "image_hash": image_hash,
                "sent_at": sent_at,
                "backend_status": backend_status,
                "error": ack.get("error") or "Local backend returned an error ack",
            }
            self.result_sink(result)
            return result

        result = {
            "status": "ok",
            "request_id": request_id,
            "image_hash": image_hash,
            "sent_at": sent_at,
            "backend_status": backend_status,
            "error": None,
        }
        self.result_sink(result)
        return result

    def _error_response(
        self,
        request_id: str,
        sent_at: str,
        exc: Exception,
        *,
        image_hash: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "request_id": request_id,
            "image_hash": image_hash,
            "sent_at": sent_at,
            "backend_status": self._classify_error(exc),
            "error": str(exc),
        }

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, (ScreenCapturePermissionError, PermissionError)):
            return "permission_denied"
        if isinstance(exc, AckTimeoutError):
            return "ack_timeout"
        if isinstance(exc, (LocalWebSocketUnavailable, ConnectionError)):
            return "socket_unavailable"
        return "capture_failed"
