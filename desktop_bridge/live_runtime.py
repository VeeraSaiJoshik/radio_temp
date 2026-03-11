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