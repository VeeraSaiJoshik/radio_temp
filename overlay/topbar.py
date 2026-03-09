"""
ReVU — Top Bar Widget (Horizon-style)

Wide glass strip (~700x40) with golden mini-orb, pill-shaped nav buttons
with keyboard shortcuts, amber suggestion banner, and mode switching.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu, QWidget,
    QGraphicsOpacityEffect,
)

import config
from overlay.glass import LiquidGlassPanel
from overlay.orb import MiniOrbWidget
from overlay.styles import GLASS_TIER2


# ── Nav items: (view_name, icon, shortcut_display) ────────────────────────────

_NAV_ITEMS = [
    ("Insights", "\u2022", "\u2318\u2325A"),
    ("Measure",  "\u2022", "\u2318\u2325M"),
    ("Compare",  "\u2022", "\u2318\u2325C"),
    ("QA",       "\u2022", "\u2318\u2325Q"),
]


class PillButton(QPushButton):
    """Frosted glass pill with icon + label + keyboard shortcut."""

    def __init__(self, name: str, icon: str, shortcut: str, parent=None):
        super().__init__(parent)
        self._name = name
        self.setObjectName("pill_btn")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(28)

        # Build rich text label: icon + name + shortcut
        self.setText(f" {icon}  {name}  {shortcut} ")
        self.setToolTip(f"{name} ({shortcut})")

    def set_active(self, active: bool):
        self.setObjectName("pill_btn_active" if active else "pill_btn")
        self.setStyle(self.style())


class TopBarWidget(LiquidGlassPanel):
    """Wide glass strip with mini-orb, pill buttons, ask, and amber banner."""

    view_selected = pyqtSignal(str)
    ask_clicked = pyqtSignal()
    mic_pressed = pyqtSignal()
    mic_released = pyqtSignal()
    mic_clicked = pyqtSignal()
    mode_switch_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            radius=20,
            **GLASS_TIER2,
        )
        self.setFixedHeight(40)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        self._active_view = "Insights"
        self._build_layout()

    def _build_layout(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Button strip ──
        strip = QWidget()
        strip.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(10, 4, 10, 4)
        strip_layout.setSpacing(5)

        # Mini orb
        self._mini_orb = MiniOrbWidget()
        self._mini_orb.clicked.connect(self.mode_switch_requested.emit)
        strip_layout.addWidget(self._mini_orb)
        strip_layout.addSpacing(6)

        # Nav pill buttons
        self._nav_buttons: dict[str, PillButton] = {}
        for name, icon, shortcut in _NAV_ITEMS:
            btn = PillButton(name, icon, shortcut)
            btn.clicked.connect(lambda checked=False, n=name: self._on_nav(n))
            self._nav_buttons[name] = btn
            strip_layout.addWidget(btn)

        strip_layout.addStretch(1)

        # Mic button
        self._mic_btn = QPushButton("Mic")
        self._mic_btn.setObjectName("pill_btn")
        self._mic_btn.setFixedHeight(28)
        self._mic_btn.setEnabled(False)
        self._mic_btn.pressed.connect(self.mic_pressed.emit)
        self._mic_btn.released.connect(self.mic_released.emit)
        self._mic_btn.clicked.connect(self.mic_clicked.emit)
        strip_layout.addWidget(self._mic_btn)

        # Ask button
        self._ask_btn = PillButton("Ask", "\u2022", "\u2303Space")
        self._ask_btn.clicked.connect(self.ask_clicked.emit)
        strip_layout.addWidget(self._ask_btn)

        root.addWidget(strip)

        self._sync_styles()

    # ── Public API ────────────────────────────────────────────────────

    def set_active_view(self, name: str):
        self._active_view = name
        self._sync_styles()

    def set_status_color(self, color: str):
        # Mini orb doesn't change color dynamically (static gradient)
        pass

    def set_live_status(self, text: str):
        # Could show in a tooltip on the mini-orb
        self._mini_orb.setToolTip(text)

    def set_mic_enabled(self, enabled: bool):
        self._mic_btn.setEnabled(enabled)

    def set_mic_label(self, text: str):
        self._mic_btn.setText(f" {text} ")

    def set_mic_active(self, active: bool):
        self._mic_btn.setObjectName("pill_btn_active" if active else "pill_btn")
        self._mic_btn.setStyle(self._mic_btn.style())

    def set_banner_visible(self, visible: bool):
        pass

    def set_banner_text(self, text: str):
        pass

    # ── Internal ──────────────────────────────────────────────────────

    def _on_nav(self, name: str):
        self._active_view = name
        self._sync_styles()
        self.view_selected.emit(name)

    def _sync_styles(self):
        for name, btn in self._nav_buttons.items():
            btn.set_active(name == self._active_view)
