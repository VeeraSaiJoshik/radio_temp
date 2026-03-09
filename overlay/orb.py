"""
ReVU — Glowing Animated Orb + Radial Ring

Golden amber orb with radial gradient body, specular highlight, animated
energy streaks, and breathing glow pulse. On hover, 4 radial satellite
buttons fan out in an arc.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QPointF,
    pyqtSignal, QRectF,
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QPainterPath, QCursor,
    QRadialGradient, QConicalGradient,
)
from PyQt6.QtWidgets import QWidget, QPushButton, QGraphicsOpacityEffect

import config


# ── Radial ring: 4 satellite buttons ──────────────────────────────────────────

_RING_ICONS = [
    ("AI", "Insights"),
    ("MM", "Measure"),
    ("PR", "Compare"),
    ("QA", "QA"),
]

_RING_RADIUS = 56
_RING_START_DEG = 100
_RING_END_DEG = 210
_ANIM_DURATION = 180


class RadialButton(QPushButton):
    """30x30 frosted glass circle for the radial ring."""

    def __init__(self, label: str, tooltip: str, parent: QWidget | None = None):
        super().__init__(label, parent)
        self.setObjectName("nav_ring_btn")
        self.setToolTip(tooltip)
        self.setFixedSize(30, 30)
        self._target_pos = QPoint(0, 0)
        self._center_pos = QPoint(0, 0)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self.hide()

    def set_active(self, active: bool):
        self.setObjectName("nav_ring_btn_active" if active else "nav_ring_btn")
        self.setStyle(self.style())

    def animate_show(self, center: QPoint, target: QPoint, delay_ms: int = 0):
        self._center_pos = center
        self._target_pos = target
        self.move(center)
        self.show()

        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(_ANIM_DURATION)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)  # spring settle
        anim.setStartValue(center)
        anim.setEndValue(target)

        fade = QPropertyAnimation(self._opacity, b"opacity", self)
        fade.setDuration(_ANIM_DURATION)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, lambda: (anim.start(), fade.start()))
        else:
            anim.start()
            fade.start()

        self._pos_anim = anim
        self._fade_anim = fade

    def animate_hide(self):
        fade = QPropertyAnimation(self._opacity, b"opacity", self)
        fade.setDuration(120)
        fade.setStartValue(self._opacity.opacity())
        fade.setEndValue(0.0)
        fade.finished.connect(self.hide)
        fade.start()
        self._fade_anim = fade


# ── Mini Orb (static, for top bar) ────────────────────────────────────────────

class MiniOrbWidget(QWidget):
    """24x24 static golden orb for the top bar — gradient + specular, no animation."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = QRectF(2, 2, 20, 20)
        center = r.center()

        # Body gradient
        body_grad = QRadialGradient(center, 10)
        body_grad.setFocalPoint(QPointF(center.x() - 1, center.y() - 2))
        body_grad.setColorAt(0.0, QColor(255, 220, 160))
        body_grad.setColorAt(0.4, QColor(255, 170, 60))
        body_grad.setColorAt(0.8, QColor(200, 100, 20))
        body_grad.setColorAt(1.0, QColor(160, 70, 10))

        body = QPainterPath()
        body.addEllipse(r)
        p.fillPath(body, QBrush(body_grad))

        # Specular highlight
        spec_r = QRectF(r.left() + 3, r.top() + 2, 8, 7)
        spec_grad = QRadialGradient(spec_r.center(), 5)
        spec_grad.setColorAt(0.0, QColor(255, 255, 240, 100))
        spec_grad.setColorAt(1.0, QColor(255, 255, 240, 0))
        spec = QPainterPath()
        spec.addEllipse(spec_r)
        p.fillPath(spec, QBrush(spec_grad))

        # Border
        p.setPen(QPen(QColor(255, 180, 80, 50), 0.5))
        p.drawEllipse(r.adjusted(0.25, 0.25, -0.25, -0.25))

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── Main Orb (animated, for corner mode) ──────────────────────────────────────

class OrbWidget(QWidget):
    """Glowing animated golden orb with radial satellite ring on hover."""

    clicked = pyqtSignal()
    view_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Widget size includes glow padding
        self._orb_size = config.ORB_SIZE  # inner orb diameter
        self._widget_size = config.ORB_WIDGET_SIZE  # total with glow
        self.setFixedSize(self._widget_size, self._widget_size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._status_color = QColor("#8BE0B3")
        self._ring_visible = False
        self._active_view: str = ""
        self._phase: float = 0.0

        # Animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)  # ~30fps
        self._anim_timer.timeout.connect(self._tick)

        # Leave timer for ring
        self._leave_timer = QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(200)
        self._leave_timer.timeout.connect(self._do_hide_ring)

        # Satellite buttons
        self._buttons: list[RadialButton] = []
        for label, tooltip in _RING_ICONS:
            btn = RadialButton(label, tooltip, parent=self.parent() if self.parent() else self)
            btn.clicked.connect(lambda checked=False, name=tooltip: self._on_ring_click(name))
            self._buttons.append(btn)

    def reparent_buttons(self, parent: QWidget):
        for btn in self._buttons:
            btn.setParent(parent)

    def set_status_color(self, color: str):
        self._status_color = QColor(color)
        self.update()

    def set_active_view(self, name: str):
        self._active_view = name
        for btn, (_, tooltip) in zip(self._buttons, _RING_ICONS):
            btn.set_active(tooltip == name)

    # ── Animation lifecycle ───────────────────────────────────────────

    def start_animation(self):
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def stop_animation(self):
        self._anim_timer.stop()

    def _tick(self):
        if not self.isVisible():
            return
        self._phase += 0.03
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.start_animation()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.stop_animation()

    # ── Paint ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self._widget_size
        orb_r = self._orb_size / 2
        pad = (w - self._orb_size) / 2
        center = QPointF(w / 2, w / 2)
        orb_rect = QRectF(pad, pad, self._orb_size, self._orb_size)

        # ── 1. Ambient glow halo (pulsating) ──
        pulse = math.sin(self._phase) * 0.5 + 0.5  # 0..1
        glow_alpha = int(30 + 25 * pulse)
        glow_radius = orb_r * 1.4
        glow_grad = QRadialGradient(center, glow_radius)
        glow_grad.setColorAt(0.0, QColor(255, 160, 60, glow_alpha))
        glow_grad.setColorAt(0.5, QColor(255, 140, 40, int(glow_alpha * 0.4)))
        glow_grad.setColorAt(1.0, QColor(255, 120, 20, 0))

        glow_size = glow_radius * 2
        glow_rect = QRectF(
            center.x() - glow_radius, center.y() - glow_radius,
            glow_size, glow_size,
        )
        glow_path = QPainterPath()
        glow_path.addEllipse(glow_rect)
        p.fillPath(glow_path, QBrush(glow_grad))

        # ── 2. Outer ring ──
        p.setPen(QPen(QColor(255, 180, 80, 50 + int(15 * pulse)), 1.0))
        p.drawEllipse(orb_rect.adjusted(0.5, 0.5, -0.5, -0.5))

        # ── 3. Body sphere (radial gradient with offset focal) ──
        body_grad = QRadialGradient(center, orb_r)
        body_grad.setFocalPoint(QPointF(center.x() - 2, center.y() - 4))
        body_grad.setColorAt(0.0, QColor(255, 220, 160))
        body_grad.setColorAt(0.35, QColor(255, 175, 65))
        body_grad.setColorAt(0.7, QColor(210, 110, 25))
        body_grad.setColorAt(1.0, QColor(160, 70, 10))

        body = QPainterPath()
        body.addEllipse(orb_rect)
        p.fillPath(body, QBrush(body_grad))

        # ── 4. Energy streaks (rotating arcs) ──
        p.save()
        streak_pen = QPen(QColor(255, 240, 200, 65), 1.5, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap)
        p.setPen(streak_pen)
        streak_rect = orb_rect.adjusted(orb_r * 0.35, orb_r * 0.35,
                                         -orb_r * 0.35, -orb_r * 0.35)
        for i in range(4):
            base_angle = i * 90
            phase_offset = self._phase * (180 / math.pi)  # radians → degrees-ish
            start = base_angle + phase_offset * (1.0 + i * 0.15)
            span = 40 + 15 * math.sin(self._phase * 1.3 + i * 1.2)
            p.drawArc(streak_rect, int(start * 16), int(span * 16))
        p.restore()

        # ── 5. Specular highlight (upper-left) ──
        spec_w = orb_r * 0.65
        spec_h = orb_r * 0.5
        spec_cx = center.x() - orb_r * 0.22
        spec_cy = center.y() - orb_r * 0.30
        spec_rect = QRectF(spec_cx - spec_w / 2, spec_cy - spec_h / 2, spec_w, spec_h)

        spec_grad = QRadialGradient(QPointF(spec_cx, spec_cy), spec_w * 0.6)
        spec_grad.setColorAt(0.0, QColor(255, 255, 240, 95))
        spec_grad.setColorAt(0.5, QColor(255, 255, 220, 35))
        spec_grad.setColorAt(1.0, QColor(255, 255, 200, 0))
        spec_path = QPainterPath()
        spec_path.addEllipse(spec_rect)
        p.fillPath(spec_path, QBrush(spec_grad))

        # ── 6. Status dot (bottom-right of inner orb) ──
        dot_size = 8
        dot_x = orb_rect.right() - dot_size - 2
        dot_y = orb_rect.bottom() - dot_size - 2
        # Dark ring for contrast
        p.setBrush(QBrush(QColor(0, 0, 0, 120)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(dot_x - 1, dot_y - 1, dot_size + 2, dot_size + 2))
        # Status color
        p.setBrush(QBrush(self._status_color))
        p.setPen(QPen(QColor(0, 0, 0, 60), 0.5))
        p.drawEllipse(QRectF(dot_x, dot_y, dot_size, dot_size))

        p.end()

    # ── Hit testing (only inner orb is clickable) ─────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is within the inner orb circle
            center = QPointF(self._widget_size / 2, self._widget_size / 2)
            dx = event.position().x() - center.x()
            dy = event.position().y() - center.y()
            if dx * dx + dy * dy <= (self._orb_size / 2) ** 2:
                self.clicked.emit()
        super().mousePressEvent(event)

    # ── Hover → radial ring ───────────────────────────────────────────

    def enterEvent(self, event):
        self._leave_timer.stop()
        if not self._ring_visible:
            self._show_ring()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._leave_timer.start()
        super().leaveEvent(event)

    # ── Ring show / hide ──────────────────────────────────────────────

    def _show_ring(self):
        self._ring_visible = True
        n = len(self._buttons)
        center = self._orb_center_in_parent()

        for i, btn in enumerate(self._buttons):
            angle_deg = _RING_START_DEG + (_RING_END_DEG - _RING_START_DEG) * i / max(n - 1, 1)
            angle_rad = math.radians(angle_deg)
            tx = center.x() + int(_RING_RADIUS * math.cos(angle_rad)) - 15
            ty = center.y() - int(_RING_RADIUS * math.sin(angle_rad)) - 15
            target = QPoint(tx, ty)
            start = QPoint(center.x() - 15, center.y() - 15)
            btn.animate_show(start, target, delay_ms=i * 20)

    def _do_hide_ring(self):
        cursor_pos = QCursor.pos()
        for btn in self._buttons:
            if btn.isVisible() and btn.geometry().contains(btn.parent().mapFromGlobal(cursor_pos)):
                self._leave_timer.start()
                return
        if self.geometry().contains(self.parent().mapFromGlobal(cursor_pos)):
            return

        self._ring_visible = False
        for btn in self._buttons:
            btn.animate_hide()

    def _orb_center_in_parent(self) -> QPoint:
        return self.pos() + QPoint(self.width() // 2, self.height() // 2)

    def _on_ring_click(self, name: str):
        self.view_selected.emit(name)
