"""
Radiology Copilot — Global Hotkey Listener
Registers Cmd+Shift+R (macOS) to trigger screenshot capture.
Uses GlobalHotKeys for reliable macOS support.
"""

from pynput import keyboard

import config


class HotkeyListener:
    """Listens for a global hotkey and fires a callback."""

    def __init__(self, on_trigger: callable):
        self._on_trigger = on_trigger
        self._hotkeys = None

    def start(self):
        self._hotkeys = keyboard.GlobalHotKeys({
            config.HOTKEY: self._on_activate,
        })
        self._hotkeys.daemon = True
        self._hotkeys.start()

    def _on_activate(self):
        print("[HOTKEY] Cmd+Shift+R pressed")
        self._on_trigger()

    def stop(self):
        if self._hotkeys:
            self._hotkeys.stop()
