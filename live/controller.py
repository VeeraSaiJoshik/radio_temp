"""Qt-free compatibility wrapper for the Gemini Live runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop_bridge.live_runtime import LiveRuntime


@dataclass
class Signal:
    """Minimal signal helper with a Qt-like `.connect()` interface."""

    _callbacks: list = field(default_factory=list)

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs) -> None:
        for callback in tuple(self._callbacks):
            callback(*args, **kwargs)


class GeminiLiveController:
    """Keep the old controller surface without importing PyQt."""

    def __init__(self, *, start_server: bool = False):
        self.status_changed = Signal()
        self.assistant_message = Signal()
        self.user_transcript = Signal()
        self.screenshot_event = Signal()
        self.session_running = Signal()
        self.connection_changed = Signal()
        self.mic_state_changed = Signal()

        self._runtime = LiveRuntime(
            start_server=start_server,
            status_sink=self.status_changed.emit,
            assistant_sink=self.assistant_message.emit,
            user_transcript_sink=self.user_transcript.emit,
            screenshot_sink=self.screenshot_event.emit,
            session_running_sink=self.session_running.emit,
            connection_sink=self.connection_changed.emit,
            mic_state_sink=self.mic_state_changed.emit,
        )

    def start(self) -> None:
        self._runtime.start()

    def stop(self) -> None:
        self._runtime.stop()

    def submit_text(self, text: str) -> None:
        self._runtime.submit_text(text)

    def set_mic_mode(self, mode: str) -> None:
        self._runtime.set_mic_mode(mode)

    def start_mic_capture(self) -> None:
        self._runtime.start_mic_capture()

    def stop_mic_capture(self) -> None:
        self._runtime.stop_mic_capture()
