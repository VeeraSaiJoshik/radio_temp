"""Threaded Gemini Live runtime without Qt dependencies."""

from __future__ import annotations

import asyncio
import multiprocessing
import threading
import time
import uuid

import config
from live.audio import AudioPlayer, PushToTalkMicrophone
from live.local_ws import LocalScreenshotWebSocketClient
from live.session import LiveSessionManager, MIC_MODE_CONTINUOUS
from live.tool_bridge import ScreenshotToolBridge


def _kill_port(port: int) -> None:
    """Kill any stale process holding the given port."""
    import subprocess

    try:
        pids = subprocess.check_output(
            ["lsof", "-ti", f":{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return

    if not pids:
        return

    for pid in pids.splitlines():
        subprocess.call(["kill", pid.strip()], stderr=subprocess.DEVNULL)
    time.sleep(0.3)


def _start_mock_server():
    from backend.mock_server import run_mock_server

    _kill_port(config.MOCK_SERVER_PORT)
    process = multiprocessing.Process(target=run_mock_server, daemon=True)
    process.start()
    time.sleep(1.0)
    return process


class LiveRuntime:
    """Own one Gemini Live session and expose callback sinks instead of Qt signals."""

    def __init__(
        self,
        *,
        start_server: bool = False,
        status_sink=None,
        assistant_sink=None,
        user_transcript_sink=None,
        screenshot_sink=None,
        session_running_sink=None,
        connection_sink=None,
        mic_state_sink=None,
    ):
        self.start_server = start_server
        self.status_sink = status_sink or (lambda message: None)
        self.assistant_sink = assistant_sink or (lambda message: None)
        self.user_transcript_sink = user_transcript_sink or (lambda text, is_final: None)
        self.screenshot_sink = screenshot_sink or (lambda event: None)
        self.session_running_sink = session_running_sink or (lambda running: None)
        self.connection_sink = connection_sink or (lambda connected, message: None)
        self.mic_state_sink = mic_state_sink or (lambda active: None)

        self._thread: threading.Thread | None = None
        self._manager: LiveSessionManager | None = None
        self._server_process = None
        self._capture_events: dict[str, dict] = {}
        self._microphone = PushToTalkMicrophone(status_sink=self.status_sink)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self.status_sink("Gemini Live starting...")
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_mic_capture()
        if self._manager is not None:
            self._manager.request_stop()
        if (
            self._thread is not None
            and self._thread.is_alive()
            and threading.current_thread() is not self._thread
        ):
            self._thread.join(timeout=3.0)

    def submit_text(self, text: str) -> None:
        if self._manager is None:
            raise RuntimeError("Gemini Live session is not running")
        self._manager.submit_user_message(text)

    def set_mic_mode(self, mode: str) -> None:
        """No-op for parity with the old controller API."""
        _ = mode

    def start_mic_capture(self) -> None:
        if self._manager is None:
            raise RuntimeError("Gemini Live session is not running")
        if self._microphone.active:
            return

        try:
            self._microphone.start(self._stream_audio_chunk)
        except Exception as exc:
            self.status_sink(f"[live] Mic unavailable: {exc}")
            self.mic_state_sink(False)
            return

        self.status_sink("[state] Listening continuously")
        self.mic_state_sink(True)

    def stop_mic_capture(self) -> None:
        was_active = self._microphone.active
        if was_active:
            self._microphone.stop()
            self.status_sink("[state] Waiting for input")
        self.mic_state_sink(False)

    def _stream_audio_chunk(self, pcm_bytes: bytes) -> None:
        if self._manager is None:
            return
        try:
            self._manager.push_audio_chunk(pcm_bytes)
        except RuntimeError:
            pass

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        self._server_process = _start_mock_server() if self.start_server else None
        session_id = str(uuid.uuid4())

        screenshot_transport = LocalScreenshotWebSocketClient(
            url=config.LIVE_SCREEN_WS_URL,
            status_sink=self.status_sink,
        )
        screenshot_bridge = ScreenshotToolBridge(
            session_id=session_id,
            transport=screenshot_transport,
            capture_sink=self._handle_capture_event,
            result_sink=self._handle_capture_result,
        )
        self._manager = LiveSessionManager(
            session_id=session_id,
            screenshot_transport=screenshot_transport,
            status_sink=self.status_sink,
            assistant_sink=self.assistant_sink,
            user_transcript_sink=self.user_transcript_sink,
            connection_sink=self.connection_sink,
            screenshot_tool_bridge=screenshot_bridge,
            audio_player=AudioPlayer(status_sink=self.status_sink),
            mic_mode=MIC_MODE_CONTINUOUS,
        )
        self.session_running_sink(True)

        try:
            loop.run_until_complete(self._manager.run())
        except Exception as exc:
            self.status_sink(f"[live] Error: {exc}")
            self.connection_sink(False, str(exc))
        finally:
            self._manager = None
            self.stop_mic_capture()
            if self._server_process is not None:
                self._server_process.terminate()
                self._server_process = None
            self._thread = None
            self.session_running_sink(False)

    def _handle_capture_event(self, event: dict) -> None:
        merged = dict(event)
        self._capture_events[event["request_id"]] = merged
        self.screenshot_sink(dict(merged))

    def _handle_capture_result(self, result: dict) -> None:
        request_id = result.get("request_id")
        if request_id:
            existing = dict(self._capture_events.get(request_id, {}))
            existing.update(result)
            self._capture_events[request_id] = existing
            self.screenshot_sink(dict(existing))
        else:
            self.screenshot_sink(dict(result))

        status = result.get("status", "unknown")
        backend_status = result.get("backend_status", "unknown")
        image_hash = result.get("image_hash") or "n/a"
        self.status_sink(
            f"[tool] take_screenshot -> {status} ({backend_status}) hash={image_hash}"
        )
