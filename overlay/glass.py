"""
ReVU — Liquid Glass Surface Widgets

Translucent glass panels with native macOS vibrancy blur, 3-layer shadows,
inner edge highlights, and subtle body gradients for depth. Falls back to
enhanced QPainter rendering on non-macOS or when vibrancy is disabled.
"""

import os
import platform

from PyQt6.QtCore import Qt, QRectF, QRect, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QPainterPath,
    QLinearGradient,
)


class LiquidGlassPanel(QWidget):
    """Painted glass card with native blur, depth shadows, and edge highlights."""

    def __init__(
        self,
        parent=None,
        *,
        radius: int = 22,
        fill_rgba: tuple[int, int, int, int] = (12, 14, 18, 200),
        border_alpha: int = 22,
        shadow_alpha: int = 22,
        vibrancy_material: str = "HUDWindow",
        **_kwargs,
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._radius = radius
        self._anim = None
        self._fill_rgba = fill_rgba
        self._border_alpha = border_alpha
        self._shadow_alpha = shadow_alpha
        self._vibrancy_material = vibrancy_material
        self._vibrancy_applied = False

        # Native vibrancy: opt-in only (full-window NSVisualEffectView
        # conflicts with our full-screen transparent overlay architecture)
        self._use_vibrancy = (
            platform.system() == "Darwin"
            and os.getenv("RADCOPILOT_ENABLE_VIBRANCY", "0") == "1"
        )

    # ── Native Vibrancy ──────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if self._use_vibrancy and not self._vibrancy_applied:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._apply_vibrancy)

    def _apply_vibrancy(self):
        """Apply native macOS backdrop blur via NSVisualEffectView."""
        if self._vibrancy_applied:
            return
        try:
            import AppKit
            import objc

            for window in AppKit.NSApp.windows():
                content = window.contentView()
                if content is None:
                    continue
                # Skip if already applied
                for sub in content.subviews():
                    if isinstance(sub, AppKit.NSVisualEffectView):
                        self._vibrancy_applied = True
                        return

                effect_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(
                    content.bounds()
                )

                # Pick material based on config
                material_map = {
                    "HUDWindow": AppKit.NSVisualEffectMaterialHUDWindow,
                    "Dark": AppKit.NSVisualEffectMaterialDark,
                }
                material = material_map.get(
                    self._vibrancy_material,
                    AppKit.NSVisualEffectMaterialHUDWindow,
                )
                effect_view.setMaterial_(material)
                effect_view.setBlendingMode_(
                    AppKit.NSVisualEffectBlendingModeBehindWindow
                )
                effect_view.setState_(AppKit.NSVisualEffectStateActive)
                effect_view.setAutoresizingMask_(
                    AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
                )

                # Enable layer-backed for corner radius
                effect_view.setWantsLayer_(True)
                layer = effect_view.layer()
                if layer:
                    layer.setCornerRadius_(self._radius)
                    layer.setMasksToBounds_(True)

                content.addSubview_positioned_relativeTo_(
                    effect_view, AppKit.NSWindowBelow, None
                )
                self._vibrancy_applied = True
        except Exception:
            pass

    # ── Paint — Liquid Glass with Depth ──────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        inset = rect.adjusted(3, 3, -3, -3)

        # ── 3-layer shadow stack ──
        for i, (offset, alpha_base) in enumerate([(2, 22), (5, 14), (10, 6)]):
            if self._shadow_alpha == 0:
                break
            alpha = max(int(alpha_base * self._shadow_alpha / 22), 0)
            if alpha <= 0:
                continue
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect(
                rect.adjusted(offset, offset + 2, -offset, -offset + offset),
                self._radius, self._radius,
            )
            painter.fillPath(shadow_path, QBrush(QColor(0, 0, 0, alpha)))

        # ── Main body ──
        body = QPainterPath()
        body.addRoundedRect(inset, self._radius, self._radius)

        # Flat fill (reduced opacity when vibrancy is active)
        r, g, b, a = self._fill_rgba
        if self._vibrancy_applied:
            a = max(int(a * 0.55), 80)  # let native blur show through while keeping text readable
        painter.fillPath(body, QBrush(QColor(r, g, b, a)))

        # ── Subtle body gradient (top lighter → bottom darker) ──
        body_grad = QLinearGradient(inset.topLeft(), inset.bottomLeft())
        body_grad.setColorAt(0.0, QColor(255, 255, 255, 5))
        body_grad.setColorAt(1.0, QColor(0, 0, 0, 8))
        painter.fillPath(body, QBrush(body_grad))

        # ── Inner edge highlight (top lit edge) ──
        highlight_grad = QLinearGradient(inset.topLeft(), inset.bottomLeft())
        highlight_grad.setColorAt(0.0, QColor(255, 255, 255, 14))
        highlight_grad.setColorAt(0.03, QColor(255, 255, 255, 5))
        highlight_grad.setColorAt(0.12, QColor(255, 255, 255, 0))
        highlight_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(body, QBrush(highlight_grad))

        # ── Directional border (top/left brighter, bottom/right dimmer) ──
        # Top-left arc (lit side)
        painter.setPen(QPen(QColor(255, 255, 255, min(self._border_alpha + 6, 40)), 0.5))
        top_half = inset.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setClipRect(QRectF(top_half.left(), top_half.top(),
                                    top_half.width(), top_half.height() / 2))
        painter.drawRoundedRect(top_half, self._radius, self._radius)

        # Bottom-right arc (shadow side)
        painter.setPen(QPen(QColor(255, 255, 255, max(self._border_alpha - 8, 4)), 0.5))
        painter.setClipRect(QRectF(top_half.left(), top_half.top() + top_half.height() / 2,
                                    top_half.width(), top_half.height() / 2))
        painter.drawRoundedRect(top_half, self._radius, self._radius)

        painter.setClipping(False)
        painter.end()

    # ── Smooth Expand / Collapse ─────────────────────────────────────

    def animate_to_height(self, target_height: int, duration: int = 250):
        """Animate the panel height with spring-like easing."""
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

        current = self.geometry()
        target = QRect(current.x(), current.y(), current.width(), target_height)
        self._anim.setStartValue(current)
        self._anim.setEndValue(target)
        self._anim.start()
