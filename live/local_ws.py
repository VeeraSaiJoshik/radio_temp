"""Persistent localhost websocket transport for screenshot delivery."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Mapping

import config

try:
    import websockets
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    websockets = None


class LocalWebSocketUnavailable(RuntimeError):
    """Raised when the localhost screenshot websocket is unavailable."""


class AckTimeoutError(TimeoutError):
    """Raised when the localhost websocket does not ack a screenshot in time."""


class LocalScreenshotWebSocketClient:
    """Maintains one localhost websocket connection and correlates screenshot acks."""

    def __init__(
        self,
        url: str = config.LIVE_SCREEN_WS_URL,
        *,
        ack_timeout: float = config.LIVE_SCREEN_ACK_TIMEOUT_SECONDS,
        retry_delay: float = config.LIVE_SCREEN_WS_RETRY_SECONDS,
        status_sink=None,
    ):
        self.url = url
        self.ack_timeout = ack_timeout
        self.retry_delay = retry_delay
        self.status_sink = status_sink or (lambda message: None)
        self._connection = None
        self._connected = asyncio.Event()
        self._closing = False
        self._connect_task: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}

    async def start(self):
        """Start the background connection loop."""
        if websockets is None:
            raise RuntimeError(
                "websockets is not installed. Run `pip install -r requirements.txt` before starting the Live scaffold."
            )

        if self._connect_task is None:
            self._connect_task = asyncio.create_task(self._connection_loop(), name="live-local-ws")
        await asyncio.sleep(0)

    async def close(self):
        """Close the connection loop and any active websocket."""
        self._closing = True
        self._connected.clear()

        if self._connection is not None:
            await self._connection.close()

        if self._connect_task is not None:
            self._connect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connect_task
            self._connect_task = None

        self._fail_pending(LocalWebSocketUnavailable("Screenshot websocket closed"))

    async def send_capture(self, message: Mapping[str, Any]) -> dict[str, Any]:
        """Send one screenshot payload and wait for the matching ack."""
        request_id = str(message.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("Screenshot websocket payload must include request_id")

        if self._connect_task is None:
            await self.start()

        if not self._connected.is_set() or self._connection is None:
            raise LocalWebSocketUnavailable(f"Screenshot websocket is not connected: {self.url}")

        loop = asyncio.get_running_loop()
        ack_future = loop.create_future()
        self._pending[request_id] = ack_future

        try:
            async with self._send_lock:
                if self._connection is None:
                    raise LocalWebSocketUnavailable(f"Screenshot websocket is not connected: {self.url}")
                await self._connection.send(json.dumps(dict(message)))

            ack = await asyncio.wait_for(ack_future, timeout=self.ack_timeout)
            return ack
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise AckTimeoutError(f"Timed out waiting for screenshot ack: {request_id}") from exc
        except Exception:
            self._pending.pop(request_id, None)
            raise

    async def _connection_loop(self):
        while not self._closing:
            try:
                async with websockets.connect(self.url, max_size=None) as websocket:
                    self._connection = websocket
                    self._connected.set()
                    self.status_sink(f"[live] Screenshot websocket connected: {self.url}")
                    await self._reader_loop(websocket)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status_sink(f"[live] Screenshot websocket unavailable: {exc}")
                self._connected.clear()
                self._connection = None
                self._fail_pending(LocalWebSocketUnavailable(str(exc)))
                if not self._closing:
                    await asyncio.sleep(self.retry_delay)
            finally:
                self._connected.clear()
                self._connection = None

    async def _reader_loop(self, websocket):
        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            request_id = message.get("request_id")
            if message.get("type") != "screenshot.ack" or not request_id:
                continue

            pending = self._pending.pop(request_id, None)
            if pending is not None and not pending.done():
                pending.set_result(message)

    def _fail_pending(self, exc: Exception):
        for request_id, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(exc)
            self._pending.pop(request_id, None)
