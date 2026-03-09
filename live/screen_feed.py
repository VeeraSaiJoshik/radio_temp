"""Continuous low-resolution screen publisher for Gemini Live vision input."""

from __future__ import annotations

import asyncio

import config
from capture.screenshot import capture_screen_preview
from live.sdk import make_blob


class ScreenFeedPublisher:
    """Publishes lightweight preview frames to an active Gemini Live session."""

    def __init__(
        self,
        session,
        *,
        fps: float = config.LIVE_PREVIEW_FPS,
        monitor_index: int = config.LIVE_SCREEN_MONITOR_INDEX,
        max_width: int = config.LIVE_PREVIEW_MAX_WIDTH,
        jpeg_quality: int = config.LIVE_PREVIEW_JPEG_QUALITY,
        capture_func=capture_screen_preview,
    ):
        if fps <= 0:
            raise ValueError("Preview FPS must be greater than zero")

        self.session = session
        self.interval_seconds = 1.0 / fps
        self.monitor_index = monitor_index
        self.max_width = max_width
        self.jpeg_quality = jpeg_quality
        self.capture_func = capture_func
        self._refresh_event = asyncio.Event()

    async def publish_frame(self) -> str:
        """Capture and send one preview frame to Gemini Live."""
        image_bytes, image_hash = self.capture_func(
            monitor_index=self.monitor_index,
            max_width=self.max_width,
            jpeg_quality=self.jpeg_quality,
        )
        await self.session.send_realtime_input(
            video=make_blob(data=image_bytes, mime_type="image/jpeg")
        )
        self._frames_sent = getattr(self, "_frames_sent", 0) + 1
        if self._frames_sent == 1:
            print(f"[screen-feed] First frame sent ({len(image_bytes)} bytes, hash={image_hash})")
        elif self._frames_sent % 100 == 0:
            print(f"[screen-feed] {self._frames_sent} frames sent")
        return image_hash

    def request_refresh(self):
        """Request an immediate preview frame outside the steady-state cadence."""
        self._refresh_event.set()

    async def run(self, stop_event: asyncio.Event):
        """Send preview frames until the stop event is set."""
        while not stop_event.is_set():
            try:
                await self.publish_frame()
            except Exception as exc:
                print(f"[screen-feed] Frame error (non-fatal): {exc}")
                await asyncio.sleep(self.interval_seconds)
                continue
            try:
                await asyncio.wait_for(
                    self._wait_for_refresh_or_stop(stop_event),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def _wait_for_refresh_or_stop(self, stop_event: asyncio.Event):
        stop_task = asyncio.create_task(stop_event.wait())
        refresh_task = asyncio.create_task(self._refresh_event.wait())
        done, pending = await asyncio.wait(
            {stop_task, refresh_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if refresh_task in done:
            self._refresh_event.clear()
