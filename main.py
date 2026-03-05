"""
Radiology Copilot — Main Entry Point

Usage:
    python main.py              # Launch the copilot overlay
    python main.py --diff       # Print today's disagreement diff report
    python main.py --no-server  # Launch overlay without starting the mock server
"""

import argparse
import asyncio
import multiprocessing
import platform
import sys
import uuid
import threading

from PyQt6.QtCore import QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication, QMessageBox

import config
from overlay.window import OverlayWindow
from overlay.hotkey_listener import HotkeyListener
from capture.screenshot import capture_screen, check_screen_recording_permission, get_permission_instructions
from backend.client import BackendClient
from storage.db import CopilotDB, print_diff


class AsyncBridge(QObject):
    """Bridges async backend calls and hotkey events into the Qt event loop."""

    finding_ready = pyqtSignal(str, str, str)       # finding, confidence, image_hash
    recommendation_ready = pyqtSignal(str)           # recommended_action
    specialist_flags_ready = pyqtSignal(list)        # specialist_flags
    status_update = pyqtSignal(str)
    flag_confirmed = pyqtSignal(str)
    hotkey_pressed = pyqtSignal()                    # thread-safe hotkey signal

    def __init__(self, client: BackendClient, db: CopilotDB):
        super().__init__()
        self.client = client
        self.db = db
        self._loop = asyncio.new_event_loop()
        self._current_read_id = None

    def run_analyze(self, image_b64: str, image_hash: str, patient_context: str = ""):
        threading.Thread(
            target=self._run_async_analyze,
            args=(image_b64, image_hash, patient_context),
            daemon=True,
        ).start()

    def _run_async_analyze(self, image_b64: str, image_hash: str, patient_context: str):
        try:
            result = self._loop.run_until_complete(
                self.client.analyze(image_b64, patient_context)
            )
        except Exception as e:
            self.status_update.emit(f"Analysis error: {e}")
            return

        self._current_read_id = self.db.log_read(
            session_id=self.client.session_id,
            image_hash=image_hash,
            ai_finding=result["findings"],
            confidence=result["confidence"],
            specialist_flags=result.get("specialist_flags", []),
            recommended_action=result.get("recommended_action", ""),
        )

        self.finding_ready.emit(result["findings"], result["confidence"], image_hash)
        self.recommendation_ready.emit(result.get("recommended_action", ""))
        self.specialist_flags_ready.emit(result.get("specialist_flags", []))

    def run_flag(self, ai_finding: str, override_note: str, image_hash: str):
        threading.Thread(
            target=self._run_async_flag,
            args=(ai_finding, override_note, image_hash),
            daemon=True,
        ).start()

    def _run_async_flag(self, ai_finding: str, override_note: str, image_hash: str):
        self.db.mark_flagged_by_hash(image_hash, override_note)
        try:
            result = self._loop.run_until_complete(
                self.client.flag(ai_finding, override_note, image_hash)
            )
            if result.get("status") == "received":
                self.flag_confirmed.emit("Flagged for review ✓")
            else:
                self.flag_confirmed.emit("Flag saved locally (backend unavailable)")
        except Exception:
            self.flag_confirmed.emit("Flag saved locally")

    def mark_dismissed(self):
        if self._current_read_id:
            self.db.mark_accepted(self._current_read_id)
            self._current_read_id = None


class CopilotApp:
    """Main application controller."""

    def __init__(self, start_server: bool = True):
        self.session_id = str(uuid.uuid4())
        self.db = CopilotDB()
        self.client = BackendClient(self.session_id)

        self._server_process = None
        if start_server:
            self._start_mock_server()

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.bridge = AsyncBridge(self.client, self.db)
        self.overlay = OverlayWindow()

        self.overlay.set_session_id(self.session_id)

        # Wire signals
        self.bridge.finding_ready.connect(self.overlay.show_finding)
        self.bridge.recommendation_ready.connect(self.overlay.set_recommendation)
        self.bridge.specialist_flags_ready.connect(self.overlay.set_specialist_flags)
        self.bridge.status_update.connect(self.overlay.show_status)
        self.bridge.flag_confirmed.connect(self.overlay.show_confirmation)
        self.overlay.disagree_submitted.connect(self.bridge.run_flag)
        self.overlay.dismiss_requested.connect(self.bridge.mark_dismissed)

        # Hotkey → signal → toggle overlay (thread-safe)
        self.bridge.hotkey_pressed.connect(self._on_hotkey_toggle)
        self.hotkey = HotkeyListener(on_trigger=self._on_hotkey_thread)
        self.hotkey.start()

        # Timer capture
        if config.TIMER_INTERVAL_SECONDS > 0:
            self._capture_timer = QTimer()
            self._capture_timer.timeout.connect(self._on_capture)
            self._capture_timer.start(config.TIMER_INTERVAL_SECONDS * 1000)

    def _start_mock_server(self):
        from backend.mock_server import run_mock_server
        self._server_process = multiprocessing.Process(target=run_mock_server, daemon=True)
        self._server_process.start()
        import time
        time.sleep(1.0)

    def _on_hotkey_thread(self):
        """Called from hotkey background thread — emits signal to Qt main thread."""
        print("[HOTKEY] Cmd+Shift+R pressed")
        self.bridge.hotkey_pressed.emit()

    def _on_hotkey_toggle(self):
        """Toggle overlay: if visible, hide it. If hidden, capture and show."""
        if self.overlay.isVisible():
            self.overlay._dismiss()
        else:
            self._on_capture()

    def _on_capture(self):
        """Runs on Qt main thread — capture screen and send to backend."""
        self.overlay.show_status("Capturing...")

        try:
            image_b64, image_hash = capture_screen()
        except Exception as e:
            self.overlay.show_status(f"Capture failed: {e}")
            return

        self.overlay.show_status("Analyzing...")
        self.bridge.run_analyze(image_b64, image_hash)

    def run(self):
        if platform.system() == "Darwin":
            if not check_screen_recording_permission():
                msg = QMessageBox()
                msg.setWindowTitle("Permission Required")
                msg.setText(get_permission_instructions())
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.exec()

        print(f"Radiology Copilot running — Session: {self.session_id[:8]}")
        print(f"Hotkey: {config.HOTKEY}")
        if config.TIMER_INTERVAL_SECONDS > 0:
            print(f"Auto-capture every {config.TIMER_INTERVAL_SECONDS}s")
        print(f"Backend: {config.BACKEND_URL}")
        print("Press Cmd+Shift+R to capture and analyze.\n")

        exit_code = self.app.exec()

        self.hotkey.stop()
        if self._server_process:
            self._server_process.terminate()
        self.db.close()
        sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(description="Radiology Copilot")
    parser.add_argument("--diff", action="store_true", help="Print today's disagreement diff report")
    parser.add_argument("--no-server", action="store_true", help="Don't start the mock backend server")
    args = parser.parse_args()

    if args.diff:
        print_diff()
        return

    copilot = CopilotApp(start_server=not args.no_server)
    copilot.run()


if __name__ == "__main__":
    main()
