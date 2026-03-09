"""Standalone Gemini Live scaffold for screen-aware experimentation."""

from live.local_ws import AckTimeoutError, LocalScreenshotWebSocketClient, LocalWebSocketUnavailable
from live.prompts import BOOTSTRAP_PROMPT, SYSTEM_PROMPT
from live.screen_feed import ScreenFeedPublisher
from live.session import LiveSessionManager
from live.tool_bridge import ScreenshotToolBridge, TAKE_SCREENSHOT_DECLARATION

__all__ = [
    "AckTimeoutError",
    "BOOTSTRAP_PROMPT",
    "GeminiLiveController",
    "LocalScreenshotWebSocketClient",
    "LocalWebSocketUnavailable",
    "LiveSessionManager",
    "ScreenFeedPublisher",
    "ScreenshotToolBridge",
    "SYSTEM_PROMPT",
    "TAKE_SCREENSHOT_DECLARATION",
]


def __getattr__(name: str):
    if name == "GeminiLiveController":
        from live.controller import GeminiLiveController

        return GeminiLiveController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
