"""
Radiology Copilot — Frosted Glass Overlay (PyQt6)
Transparent background with floating glass panels.
AI never shows before the radiologist makes their diagnosis.

Workflow:
  1. Radiologist opens a study and reads it
  2. Radiologist presses Cmd+Shift+R → overlay appears
  3. Overlay shows: patient context, prior studies, report draft tools
  4. Radiologist types their finding first
  5. THEN AI reveals its analysis for comparison (second opinion)
  6. If they disagree → flag it → logged for end-of-day diff
"""

import platform
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QApplication, QGraphicsDropShadowEffect,
    QFrame, QTextEdit, QSizePolicy, QGridLayout,
)
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath, QLinearGradient

from overlay.styles import CONFIDENCE_COLORS, DANGER_COLOR, WARNING_COLOR, SUCCESS_COLOR, MUTED_COLOR
import config


# ── Glass Panel Helper ───────────────────────────────────────────────────────

class GlassPanel(QWidget):
    """A frosted glass panel with translucent background and subtle border."""

    def __init__(self, parent=None, opacity=0.35, border_opacity=0.15, radius=16):
        super().__init__(parent)
        self._opacity = opacity
        self._border_opacity = border_opacity
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())

        # Glass background
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        # Fill with semi-transparent dark
        glass_color = QColor(14, 15, 30, int(255 * self._opacity))
        painter.fillPath(path, QBrush(glass_color))

        # Subtle top highlight (glass reflection)
        highlight = QLinearGradient(0, 0, 0, rect.height() * 0.4)
        highlight.setColorAt(0, QColor(255, 255, 255, 12))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(highlight))

        # Border
        border_color = QColor(255, 255, 255, int(255 * self._border_opacity))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)

        painter.end()


# ── Stylesheet ───────────────────────────────────────────────────────────────

GLASS_STYLESHEET = """
    QLabel {
        color: #d0d0e8;
        background: transparent;
        font-family: "Helvetica Neue", Arial, sans-serif;
    }
    QLabel#glass_title {
        font-size: 11px;
        font-weight: 700;
        color: #89b4fa;
        letter-spacing: 3px;
    }
    QLabel#glass_subtitle {
        font-size: 10px;
        color: #666688;
    }
    QLabel#section_header {
        font-size: 9px;
        font-weight: 700;
        color: #666688;
        letter-spacing: 2px;
    }
    QLabel#big_text {
        font-size: 16px;
        font-weight: 500;
        color: #f0f0ff;
    }
    QLabel#body_text {
        font-size: 12px;
        color: #b0b0cc;
    }
    QLabel#stat_number {
        font-size: 24px;
        font-weight: 700;
        color: #e0e0f0;
    }
    QLabel#stat_label {
        font-size: 9px;
        font-weight: 600;
        color: #555577;
        letter-spacing: 1px;
    }
    QLabel#confidence_badge {
        font-size: 10px;
        font-weight: bold;
        padding: 4px 12px;
        border-radius: 6px;
    }
    QLabel#tag {
        font-size: 9px;
        font-weight: 600;
        color: #89b4fa;
        background-color: rgba(137, 180, 250, 0.08);
        border: 1px solid rgba(137, 180, 250, 0.15);
        border-radius: 4px;
        padding: 3px 8px;
    }
    QLabel#muted {
        font-size: 10px;
        color: #444466;
    }
    QLabel#history_text {
        font-size: 11px;
        color: #999aaa;
    }
    QLabel#history_time {
        font-size: 9px;
        color: #444466;
    }
    QPushButton {
        background-color: rgba(40, 42, 74, 0.6);
        color: #ccccee;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 10px 24px;
        font-size: 12px;
        font-weight: 600;
        font-family: "Helvetica Neue", Arial, sans-serif;
    }
    QPushButton:hover {
        background-color: rgba(58, 60, 106, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    QPushButton#primary_btn {
        background-color: rgba(137, 180, 250, 0.15);
        color: #89b4fa;
        border: 1px solid rgba(137, 180, 250, 0.25);
    }
    QPushButton#primary_btn:hover {
        background-color: rgba(137, 180, 250, 0.25);
    }
    QPushButton#danger_btn {
        background-color: rgba(243, 139, 168, 0.1);
        color: #f38ba8;
        border: 1px solid rgba(243, 139, 168, 0.2);
    }
    QPushButton#danger_btn:hover {
        background-color: rgba(243, 139, 168, 0.2);
    }
    QPushButton#close_btn {
        background: transparent;
        border: none;
        color: #555577;
        font-size: 20px;
        padding: 4px 12px;
    }
    QPushButton#close_btn:hover {
        color: #f38ba8;
    }
    QLineEdit, QTextEdit {
        background-color: rgba(10, 11, 24, 0.5);
        color: #e0e0f0;
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 13px;
        font-family: "Helvetica Neue", Arial, sans-serif;
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid rgba(137, 180, 250, 0.4);
    }
"""


class OverlayWindow(QWidget):
    """Full-screen transparent overlay with floating glass panels."""

    disagree_submitted = pyqtSignal(str, str, str)
    dismiss_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_finding = ""
        self._current_confidence = ""
        self._current_image_hash = ""
        self._current_rec = ""
        self._current_flags = []
        self._history = []
        self._read_count = 0
        self._flag_count = 0
        self._ai_revealed = False
        self._setup_window()
        self._build_ui()
        self._setup_auto_dismiss()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())

        if platform.system() == "Darwin":
            try:
                from AppKit import NSApp
                QTimer.singleShot(100, self._apply_macos_panel_behavior)
            except ImportError:
                pass

    def _apply_macos_panel_behavior(self):
        try:
            from AppKit import NSApp
            for window in NSApp.windows():
                window.setSharingType_(0)
        except Exception:
            pass

    def paintEvent(self, event):
        """Draw a very subtle dark scrim over the entire screen."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))  # light scrim
        painter.end()

    def _build_ui(self):
        self.setStyleSheet(GLASS_STYLESHEET)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)

        # ═══════════════════════════════════════════════════════════
        # LEFT COLUMN — Session stats + History
        # ═══════════════════════════════════════════════════════════
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # ── Title panel ──────────────────────────────────────────
        title_panel = GlassPanel(self, opacity=0.45, radius=14)
        title_panel.setFixedWidth(240)
        tp_layout = QVBoxLayout(title_panel)
        tp_layout.setContentsMargins(20, 18, 20, 18)
        tp_layout.setSpacing(4)

        app_title = QLabel("RADIOLOGY\nCOPILOT")
        app_title.setObjectName("glass_title")
        tp_layout.addWidget(app_title)

        app_sub = QLabel("AI-Assisted Reading")
        app_sub.setObjectName("glass_subtitle")
        tp_layout.addWidget(app_sub)

        left_col.addWidget(title_panel)

        # ── Stats panel ──────────────────────────────────────────
        stats_panel = GlassPanel(self, opacity=0.3, radius=14)
        stats_panel.setFixedWidth(240)
        sp_layout = QGridLayout(stats_panel)
        sp_layout.setContentsMargins(20, 18, 20, 18)
        sp_layout.setSpacing(4)

        l1 = QLabel("READS")
        l1.setObjectName("stat_label")
        sp_layout.addWidget(l1, 0, 0)
        self.stat_reads = QLabel("0")
        self.stat_reads.setObjectName("stat_number")
        sp_layout.addWidget(self.stat_reads, 1, 0)

        l2 = QLabel("FLAGGED")
        l2.setObjectName("stat_label")
        sp_layout.addWidget(l2, 0, 1)
        self.stat_flagged = QLabel("0")
        self.stat_flagged.setObjectName("stat_number")
        self.stat_flagged.setStyleSheet("font-size: 24px; font-weight: 700; color: #f38ba8;")
        sp_layout.addWidget(self.stat_flagged, 1, 1)

        l3 = QLabel("AGREEMENT")
        l3.setObjectName("stat_label")
        sp_layout.addWidget(l3, 2, 0)
        self.stat_agreement = QLabel("—")
        self.stat_agreement.setObjectName("stat_number")
        self.stat_agreement.setStyleSheet("font-size: 24px; font-weight: 700; color: #a6e3a1;")
        sp_layout.addWidget(self.stat_agreement, 3, 0)

        left_col.addWidget(stats_panel)

        # ── History panel ────────────────────────────────────────
        self.history_panel = GlassPanel(self, opacity=0.25, radius=14)
        self.history_panel.setFixedWidth(240)
        self.hp_layout = QVBoxLayout(self.history_panel)
        self.hp_layout.setContentsMargins(20, 16, 20, 16)
        self.hp_layout.setSpacing(8)

        hist_title = QLabel("RECENT READS")
        hist_title.setObjectName("section_header")
        self.hp_layout.addWidget(hist_title)

        self.history_items_layout = QVBoxLayout()
        self.history_items_layout.setSpacing(6)
        self.hp_layout.addLayout(self.history_items_layout)

        no_reads = QLabel("No reads yet this session")
        no_reads.setObjectName("muted")
        self.history_items_layout.addWidget(no_reads)

        self.hp_layout.addStretch()
        left_col.addWidget(self.history_panel)

        left_col.addStretch()
        main_layout.addLayout(left_col)

        # ═══════════════════════════════════════════════════════════
        # CENTER — Main content area
        # ═══════════════════════════════════════════════════════════
        center_col = QVBoxLayout()
        center_col.setSpacing(16)

        # ── Top bar (floating glass) ─────────────────────────────
        topbar = GlassPanel(self, opacity=0.4, radius=12)
        topbar.setFixedHeight(48)
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(20, 0, 12, 0)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #a6e3a1; font-size: 8px; background: transparent;")
        tb_layout.addWidget(self.status_dot)

        self.status_text = QLabel("READY")
        self.status_text.setObjectName("section_header")
        self.status_text.setStyleSheet("font-size: 10px; font-weight: 600; color: #a6e3a1; letter-spacing: 2px;")
        tb_layout.addWidget(self.status_text)

        tb_layout.addStretch()

        self.session_label = QLabel("")
        self.session_label.setObjectName("muted")
        tb_layout.addWidget(self.session_label)

        self.time_label = QLabel("")
        self.time_label.setObjectName("muted")
        self.time_label.setStyleSheet("font-size: 10px; color: #444466; margin-left: 12px;")
        tb_layout.addWidget(self.time_label)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("close_btn")
        close_btn.setFixedSize(36, 36)
        close_btn.clicked.connect(self._dismiss)
        tb_layout.addWidget(close_btn)

        center_col.addWidget(topbar)

        # ── Step 1: Your Diagnosis (radiologist inputs first) ────
        self.input_panel = GlassPanel(self, opacity=0.35, radius=16)
        ip_layout = QVBoxLayout(self.input_panel)
        ip_layout.setContentsMargins(28, 22, 28, 22)
        ip_layout.setSpacing(10)

        step1_header = QLabel("STEP 1 — YOUR DIAGNOSIS")
        step1_header.setObjectName("section_header")
        ip_layout.addWidget(step1_header)

        step1_desc = QLabel("Enter your finding before seeing the AI analysis to avoid confirmation bias.")
        step1_desc.setObjectName("body_text")
        step1_desc.setWordWrap(True)
        ip_layout.addWidget(step1_desc)

        self.doctor_input = QTextEdit()
        self.doctor_input.setPlaceholderText("Type your finding here... e.g. \"2.3cm nodule RUL, likely granuloma, recommend 3-month follow-up CT\"")
        self.doctor_input.setFixedHeight(70)
        ip_layout.addWidget(self.doctor_input)

        reveal_row = QHBoxLayout()
        reveal_row.addStretch()
        self.reveal_btn = QPushButton("Reveal AI Analysis")
        self.reveal_btn.setObjectName("primary_btn")
        self.reveal_btn.clicked.connect(self._reveal_ai)
        reveal_row.addWidget(self.reveal_btn)
        ip_layout.addLayout(reveal_row)

        center_col.addWidget(self.input_panel)

        # ── Step 2: AI Analysis (hidden until radiologist inputs) ─
        self.ai_panel = GlassPanel(self, opacity=0.3, radius=16)
        ap_layout = QVBoxLayout(self.ai_panel)
        ap_layout.setContentsMargins(28, 22, 28, 22)
        ap_layout.setSpacing(8)

        step2_row = QHBoxLayout()
        step2_header = QLabel("STEP 2 — AI ANALYSIS")
        step2_header.setObjectName("section_header")
        step2_row.addWidget(step2_header)
        step2_row.addStretch()
        self.confidence_label = QLabel("")
        self.confidence_label.setObjectName("confidence_badge")
        step2_row.addWidget(self.confidence_label)
        ap_layout.addLayout(step2_row)

        self.finding_label = QLabel("")
        self.finding_label.setObjectName("big_text")
        self.finding_label.setWordWrap(True)
        ap_layout.addWidget(self.finding_label)

        ap_layout.addSpacing(8)

        rec_header = QLabel("RECOMMENDED ACTION")
        rec_header.setObjectName("section_header")
        ap_layout.addWidget(rec_header)

        self.rec_label = QLabel("")
        self.rec_label.setObjectName("body_text")
        self.rec_label.setWordWrap(True)
        ap_layout.addWidget(self.rec_label)

        ap_layout.addSpacing(6)

        flags_header = QLabel("SPECIALIST MODELS INVOKED")
        flags_header.setObjectName("section_header")
        ap_layout.addWidget(flags_header)

        self.flags_container = QHBoxLayout()
        self.flags_container.setSpacing(6)
        ap_layout.addLayout(self.flags_container)

        ap_layout.addSpacing(10)

        # Comparison verdict
        self.comparison_label = QLabel("")
        self.comparison_label.setObjectName("body_text")
        self.comparison_label.setWordWrap(True)
        ap_layout.addWidget(self.comparison_label)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.addStretch()

        self.accept_btn = QPushButton("Agree — Dismiss")
        self.accept_btn.clicked.connect(self._dismiss)
        action_row.addWidget(self.accept_btn)

        self.flag_btn = QPushButton("Disagree / Flag")
        self.flag_btn.setObjectName("danger_btn")
        self.flag_btn.clicked.connect(self._show_flag_input)
        action_row.addWidget(self.flag_btn)
        ap_layout.addLayout(action_row)

        # Flag input (hidden)
        self.flag_row = QWidget()
        fr_layout = QHBoxLayout(self.flag_row)
        fr_layout.setContentsMargins(0, 8, 0, 0)
        fr_layout.setSpacing(10)
        self.flag_input = QLineEdit()
        self.flag_input.setPlaceholderText("What do you think this is instead?")
        self.flag_input.setFixedHeight(44)
        fr_layout.addWidget(self.flag_input)
        submit_btn = QPushButton("Submit Flag")
        submit_btn.setObjectName("primary_btn")
        submit_btn.setFixedHeight(44)
        submit_btn.clicked.connect(self._submit_flag)
        fr_layout.addWidget(submit_btn)
        self.flag_row.hide()
        ap_layout.addWidget(self.flag_row)

        self.ai_panel.hide()  # Hidden until radiologist reveals
        center_col.addWidget(self.ai_panel)

        # ── Waiting / status panel ───────────────────────────────
        self.status_panel = GlassPanel(self, opacity=0.25, radius=16)
        stp_layout = QVBoxLayout(self.status_panel)
        stp_layout.setContentsMargins(28, 28, 28, 28)
        stp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_msg = QLabel("Press Cmd+Shift+R to capture")
        self.status_msg.setObjectName("big_text")
        self.status_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stp_layout.addWidget(self.status_msg)

        self.status_panel.hide()
        center_col.addWidget(self.status_panel)

        center_col.addStretch()

        # ── Esc hint ─────────────────────────────────────────────
        esc_hint = QLabel("Press Esc or Cmd+Shift+R to close")
        esc_hint.setObjectName("muted")
        esc_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_col.addWidget(esc_hint)

        main_layout.addLayout(center_col, stretch=1)

    def _setup_auto_dismiss(self):
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss)

    # ── Public API ───────────────────────────────────────────────────

    def set_session_id(self, session_id: str):
        self.session_label.setText(f"Session {session_id[:8]}")

    @pyqtSlot(str, str, str)
    def show_finding(self, finding: str, confidence: str, image_hash: str):
        """Store the AI finding but DON'T show it yet — wait for radiologist input."""
        self._current_finding = finding
        self._current_confidence = confidence
        self._current_image_hash = image_hash
        self._ai_revealed = False
        self._read_count += 1

        # Update stats
        self.stat_reads.setText(str(self._read_count))
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))

        # Update status
        self.status_dot.setStyleSheet("color: #a6e3a1; font-size: 8px; background: transparent;")
        self.status_text.setText("ANALYSIS READY")
        self.status_text.setStyleSheet("font-size: 10px; font-weight: 600; color: #a6e3a1; letter-spacing: 2px;")

        # Show input panel, hide others
        self.status_panel.hide()
        self.input_panel.show()
        self.ai_panel.hide()
        self.reveal_btn.setEnabled(True)
        self.reveal_btn.setText("Reveal AI Analysis")
        self.doctor_input.clear()
        self.doctor_input.setFocus()

        self.show()
        self.raise_()
        self.activateWindow()

    @pyqtSlot(str)
    def set_recommendation(self, text: str):
        self._current_rec = text

    def set_specialist_flags(self, flags: list):
        self._current_flags = flags

    @pyqtSlot(str)
    def show_status(self, message: str):
        self.status_msg.setText(message)
        self.status_dot.setStyleSheet("color: #f9e2af; font-size: 8px; background: transparent;")
        self.status_text.setText("PROCESSING")
        self.status_text.setStyleSheet("font-size: 10px; font-weight: 600; color: #f9e2af; letter-spacing: 2px;")
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))
        self.input_panel.hide()
        self.ai_panel.hide()
        self.status_panel.show()
        self.show()
        self.raise_()
        self.activateWindow()

    @pyqtSlot(str)
    def show_confirmation(self, message: str):
        self.status_msg.setText(message)
        self.status_dot.setStyleSheet("color: #f38ba8; font-size: 8px; background: transparent;")
        self.status_text.setText("FLAGGED")
        self.status_text.setStyleSheet("font-size: 10px; font-weight: 600; color: #f38ba8; letter-spacing: 2px;")
        self.input_panel.hide()
        self.ai_panel.hide()
        self.status_panel.show()
        QTimer.singleShot(2500, self._dismiss)

    # ── Internal ─────────────────────────────────────────────────────

    def _reveal_ai(self):
        """Radiologist clicked 'Reveal' — now show the AI analysis."""
        doctor_text = self.doctor_input.toPlainText().strip()
        if not doctor_text:
            self.doctor_input.setPlaceholderText("Please type your finding first before revealing AI analysis...")
            return

        self._ai_revealed = True

        # Populate AI panel
        self.finding_label.setText(self._current_finding)
        self.rec_label.setText(self._current_rec if self._current_rec else "—")

        # Confidence badge
        conf = self._current_confidence.lower()
        color = CONFIDENCE_COLORS.get(conf, MUTED_COLOR)
        self.confidence_label.setText(f"  {self._current_confidence.upper()}  ")
        self.confidence_label.setStyleSheet(
            f"background-color: {color}; color: #0c0d1c; "
            f"border-radius: 6px; padding: 4px 12px; font-weight: bold; font-size: 10px;"
        )

        # Specialist flags
        while self.flags_container.count():
            item = self.flags_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._current_flags:
            for flag in self._current_flags:
                lbl = QLabel(flag)
                lbl.setObjectName("tag")
                self.flags_container.addWidget(lbl)
        else:
            lbl = QLabel("none")
            lbl.setObjectName("muted")
            self.flags_container.addWidget(lbl)
        self.flags_container.addStretch()

        # Simple comparison hint
        self.comparison_label.setText(
            f"Your finding: \"{doctor_text[:80]}{'...' if len(doctor_text) > 80 else ''}\"\n"
            f"Review the AI analysis above. If you agree, dismiss. If not, flag for diff."
        )

        # Reset flag UI
        self.flag_row.hide()
        self.flag_input.clear()

        # Show AI panel
        self.ai_panel.show()

        # Disable reveal button
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.setText("AI Revealed ✓")

        # Add to history
        self._history.insert(0, {
            "finding": self._current_finding[:45] + ("..." if len(self._current_finding) > 45 else ""),
            "confidence": self._current_confidence,
            "time": datetime.now().strftime("%H:%M"),
            "action": "pending",
        })
        self._update_history()

    def _show_flag_input(self):
        self._dismiss_timer.stop()
        self.flag_row.show()
        self.flag_input.setFocus()

    def _submit_flag(self):
        note = self.flag_input.text().strip()
        doctor_text = self.doctor_input.toPlainText().strip()
        override = note if note else doctor_text

        self._flag_count += 1
        self.stat_flagged.setText(str(self._flag_count))

        if self._history:
            self._history[0]["action"] = "flagged"
            self._update_history()

        if self._read_count > 0:
            rate = ((self._read_count - self._flag_count) / self._read_count) * 100
            self.stat_agreement.setText(f"{rate:.0f}%")

        self.disagree_submitted.emit(self._current_finding, override, self._current_image_hash)
        self.show_confirmation("Flagged for review ✓")

    def _update_history(self):
        while self.history_items_layout.count():
            item = self.history_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for entry in self._history[:6]:
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)

            time_lbl = QLabel(entry["time"])
            time_lbl.setObjectName("history_time")
            time_lbl.setFixedWidth(36)
            rl.addWidget(time_lbl)

            conf = entry["confidence"].lower()
            dot_color = CONFIDENCE_COLORS.get(conf, MUTED_COLOR)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {dot_color}; font-size: 6px; background: transparent;")
            dot.setFixedWidth(10)
            rl.addWidget(dot)

            text = QLabel(entry["finding"])
            text.setObjectName("history_text")
            text.setWordWrap(True)
            rl.addWidget(text, stretch=1)

            if entry["action"] == "flagged":
                flag_dot = QLabel("✗")
                flag_dot.setStyleSheet("color: #f38ba8; font-size: 10px; background: transparent;")
                rl.addWidget(flag_dot)

            self.history_items_layout.addWidget(row)

    def _dismiss(self):
        self._dismiss_timer.stop()

        if self._history and self._history[0].get("action") == "pending":
            self._history[0]["action"] = "accepted"

        if self._read_count > 0:
            rate = ((self._read_count - self._flag_count) / self._read_count) * 100
            self.stat_agreement.setText(f"{rate:.0f}%")

        self.hide()
        self.dismiss_requested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._dismiss()
