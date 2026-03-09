"""Application service layer for the Electron desktop bridge."""

from __future__ import annotations

import asyncio
import multiprocessing
import platform
import time
import uuid
from typing import Any

import config
from backend.client import BackendClient
from backend.mock_server import MOCK_FINDINGS
from capture.screenshot import (
    capture_screen,
    check_screen_recording_permission,
    get_permission_instructions,
)
from desktop_bridge.event_bus import EventBus
from storage.db import CopilotDB


def _start_mock_server():
    from backend.mock_server import run_mock_server

    process = multiprocessing.Process(target=run_mock_server, daemon=True)
    process.start()
    time.sleep(1.0)
    return process


class BridgeService:
    """Own the reusable Python application logic for the Electron frontend."""

    def __init__(self, *, start_backend_server: bool, demo_mode: bool):
        self.start_backend_server = start_backend_server
        self.demo_mode = demo_mode
        self.session_id = str(uuid.uuid4())
        self.client = BackendClient(self.session_id)
        self.db = CopilotDB()
        self.events = EventBus()

        self._server_process = None
        self._lock = asyncio.Lock()
        self._current_read_id: int | None = None
        self._current_analysis: dict[str, Any] | None = None
        self._state = self._initial_state()

    def _initial_state(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "backend_url": config.BACKEND_URL,
            "hotkey": config.DESKTOP_HOTKEY,
            "status_message": "Ready",
            "permission_warning": "",
            "confirmation_message": "",
            "analysis": None,
            "demo_mode": self.demo_mode,
        }

    async def start(self) -> None:
        if self.start_backend_server and not self.demo_mode:
            self._server_process = _start_mock_server()

        if platform.system() == "Darwin" and not self.demo_mode:
            permitted = await asyncio.to_thread(check_screen_recording_permission)
            if not permitted:
                await self._emit(
                    {
                        "type": "permission.warning",
                        "message": get_permission_instructions(),
                    }
                )

        if self.demo_mode:
            await self._emit({"type": "analysis", **self._demo_analysis()})
            return

    async def stop(self) -> None:
        if self._server_process is not None:
            self._server_process.terminate()
            self._server_process = None
        await self.client.close()
        self.db.close()

    async def get_state(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._state)

    async def capture_and_analyze(self) -> dict[str, Any]:
        if self.demo_mode:
            return self._demo_analysis()

        await self._emit({"type": "status", "message": "Capturing..."})
        try:
            image_b64, image_hash = await asyncio.to_thread(capture_screen)
        except Exception as exc:
            message = f"Capture failed: {exc}"
            await self._emit({"type": "status", "message": message})
            raise RuntimeError(message) from exc

        await self._emit({"type": "status", "message": "Analyzing..."})
        result = await self.client.analyze(image_b64, "")
        read_id = await asyncio.to_thread(
            self.db.log_read,
            self.session_id,
            image_hash,
            result["findings"],
            result["confidence"],
            result.get("specialist_flags", []),
            result.get("recommended_action", ""),
        )

        payload = {
            "finding": result["findings"],
            "confidence": result["confidence"],
            "image_hash": image_hash,
            "recommendation": result.get("recommended_action", ""),
            "specialist_flags": result.get("specialist_flags", []),
        }

        async with self._lock:
            self._current_read_id = read_id
            self._current_analysis = dict(payload)

        await self._emit({"type": "analysis", **payload})
        return payload

    async def dismiss_current_read(self) -> dict[str, bool]:
        async with self._lock:
            read_id = self._current_read_id
            self._current_read_id = None

        if read_id:
            await asyncio.to_thread(self.db.mark_accepted, read_id)

        return {"ok": True}

    async def flag_current_read(self, override_note: str) -> dict[str, str]:
        async with self._lock:
            analysis = dict(self._current_analysis or {})
            image_hash = analysis.get("image_hash", "")

        if not analysis or not image_hash:
            raise RuntimeError("No active analysis is available to flag.")

        override = override_note.strip()
        await asyncio.to_thread(self.db.mark_flagged_by_hash, image_hash, override)
        result = await self.client.flag(
            analysis.get("finding", ""),
            override,
            image_hash,
        )
        message = (
            "Flagged for review"
            if result.get("status") == "received"
            else "Flag saved locally"
        )
        await self._emit({"type": "confirmation", "message": message})
        return {"message": message}

    async def _emit(self, event: dict[str, Any]) -> None:
        async with self._lock:
            self._apply_event_to_state(event)
        await self.events.publish(event)

    def _apply_event_to_state(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "status":
            self._state["status_message"] = event["message"]
            self._state["confirmation_message"] = ""
            if event["message"] == "Capturing...":
                self._state["analysis"] = None
        elif event_type == "permission.warning":
            self._state["permission_warning"] = event["message"]
        elif event_type == "analysis":
            self._state["analysis"] = {
                "finding": event["finding"],
                "confidence": event["confidence"],
                "image_hash": event["image_hash"],
                "recommendation": event.get("recommendation", ""),
                "specialist_flags": list(event.get("specialist_flags", [])),
            }
            self._state["status_message"] = "Analysis ready"
            self._state["confirmation_message"] = ""
        elif event_type == "confirmation":
            self._state["confirmation_message"] = event["message"]
            self._state["status_message"] = event["message"]

    def _demo_analysis(self) -> dict[str, Any]:
        finding = MOCK_FINDINGS[0]
        return {
            "finding": finding["findings"],
            "confidence": finding["confidence"],
            "image_hash": "demo-image-hash",
            "recommendation": finding["recommended_action"],
            "specialist_flags": finding["specialist_flags"],
        }
