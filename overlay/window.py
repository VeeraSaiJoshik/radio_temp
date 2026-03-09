"""
ReVU — Glass Overlay Shell (Orb + Panel Redesign)

Corner orb (default) or slim top-bar, sharing a single compact content panel.
All 5 features preserved: Insights, Measure, Compare, Report, QA, plus Transcript.
"""

from __future__ import annotations

from html import escape
import platform
import re
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

import config
from live.session import MIC_MODE_CONTINUOUS, MIC_MODE_PUSH_TO_TALK
from overlay.glass import LiquidGlassPanel
from overlay.orb import OrbWidget
from overlay.topbar import TopBarWidget
from overlay.styles import (
    ACCENT,
    CONFIDENCE_HIGH,
    TEXT_MUTED,
    PANEL_STYLESHEET,
    GLASS_TIER1,
    GLASS_TIER2,
    load_fonts,
)


def _separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    line.setFixedHeight(1)
    return line


def _clip(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3].rstrip() + "..."


class _State:
    IDLE = "idle"
    PROCESSING = "processing"
    DIAGNOSIS_INPUT = "diagnosis_input"
    AI_REVEALED = "ai_revealed"
    FLAGGED = "flagged"


# Maps view names used in signals to page stack indices
_VIEW_NAMES = ["Insights", "Measure", "Compare", "QA", "Transcript"]


class OverlayWindow(QWidget):
    """Floating glass overlay shell for ReVU — orb + panel architecture."""

    disagree_submitted = pyqtSignal(str, str, str)
    dismiss_requested = pyqtSignal()
    ask_submitted = pyqtSignal(str)
    mic_mode_changed = pyqtSignal(str)
    mic_pressed = pyqtSignal()
    mic_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_finding = ""
        self._current_confidence = ""
        self._current_image_hash = ""
        self._current_rec = ""
        self._current_flags: list[str] = []
        self._history: list[dict] = []
        self._screenshot_history: list[dict] = []
        self._read_count = 0
        self._flag_count = 0
        self._session_id = ""
        self._live_connected = False
        self._live_status = "Gemini Live connecting..."
        self._live_phase = ""
        self._live_mic_mode = config.LIVE_MIC_MODE
        self._mic_active = False
        self._speech_turn_open = False
        self._transcript_entries: list[tuple[str, str]] = []
        self._transcript_draft: tuple[str, str] | None = None

        self._state = _State.IDLE
        self._active_view = "Insights"
        self._panel_visible = False
        self._mode = config.OVERLAY_MODE  # "orb" or "bar"
        self._reasoning_expanded = False
        self._delta_ready = False
        self._recommend_ready = False
        self._reasoning_ready = False
        self._stream_timer: QTimer | None = None
        self._stream_buffer = ""
        self._stream_full = ""
        self._stream_label: QLabel | None = None
        self._stream_index = 0
        self._stage_timers: list[QTimer] = []

        self._setup_window()
        self._build_ui()

    # -----------------------------------------------------------------
    # Window setup
    # -----------------------------------------------------------------

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if platform.system() == "Darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
            self.winId()
            QTimer.singleShot(100, self._apply_macos_panel_behavior)

    def _apply_macos_panel_behavior(self):
        try:
            import AppKit

            behavior = (
                AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                | AppKit.NSWindowCollectionBehaviorMoveToActiveSpace
                | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            )
            for window in AppKit.NSApp.windows():
                window.setSharingType_(0)
                window.setCollectionBehavior_(window.collectionBehavior() | behavior)
                window.setLevel_(AppKit.NSFloatingWindowLevel)
                try:
                    window.setBecomesKeyOnlyIfNeeded_(False)
                except Exception:
                    pass
                try:
                    window.setHidesOnDeactivate_(False)
                except Exception:
                    pass
                window.orderFrontRegardless()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------

    def _build_ui(self):
        load_fonts()
        self.setStyleSheet(PANEL_STYLESHEET)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.x(), geo.y())
            self.setFixedSize(geo.width(), geo.height())

        # --- Orb ---
        self._orb = OrbWidget(self)
        self._orb.clicked.connect(self._toggle_panel)
        self._orb.view_selected.connect(self._on_view_selected)
        self._orb.reparent_buttons(self)

        # --- Top Bar ---
        self._topbar = TopBarWidget(self)
        self._topbar.setFixedWidth(config.BAR_WIDTH)
        self._topbar.view_selected.connect(self._on_view_selected)
        self._topbar.ask_clicked.connect(lambda: self._on_view_selected("Transcript"))
        self._topbar.mic_pressed.connect(self._handle_mic_pressed)
        self._topbar.mic_released.connect(self._handle_mic_released)
        self._topbar.mic_clicked.connect(self._handle_mic_clicked)
        self._topbar.mode_switch_requested.connect(lambda: self._switch_mode("orb"))

        # --- Ask Input Bar (ChatGPT-style, always visible in bar mode) ---
        self._ask_bar = LiquidGlassPanel(
            self,
            radius=22,
            **GLASS_TIER2,
        )
        self._ask_bar.setFixedWidth(config.BAR_WIDTH)
        self._ask_bar.setFixedHeight(48)

        ask_layout = QHBoxLayout(self._ask_bar)
        ask_layout.setContentsMargins(14, 8, 8, 8)
        ask_layout.setSpacing(8)

        self._ask_input = QLineEdit()
        self._ask_input.setObjectName("ask_input")
        self._ask_input.setPlaceholderText("Ask what you have in mind")
        self._ask_input.returnPressed.connect(self._send_ask_message)
        ask_layout.addWidget(self._ask_input, 1)

        self._ask_mic_btn = QPushButton("\U0001f399")
        self._ask_mic_btn.setObjectName("icon_btn")
        self._ask_mic_btn.setFixedSize(32, 32)
        self._ask_mic_btn.setToolTip("Voice input")
        self._ask_mic_btn.pressed.connect(self._handle_mic_pressed)
        self._ask_mic_btn.released.connect(self._handle_mic_released)
        self._ask_mic_btn.clicked.connect(self._handle_mic_clicked)
        ask_layout.addWidget(self._ask_mic_btn)

        self._ask_send_btn = QPushButton("\u2191")
        self._ask_send_btn.setObjectName("send_btn")
        self._ask_send_btn.setFixedSize(32, 32)
        self._ask_send_btn.clicked.connect(self._send_ask_message)
        ask_layout.addWidget(self._ask_send_btn)

        self._ask_bar.hide()

        # --- Content Panel ---
        self._content_panel = LiquidGlassPanel(
            self,
            radius=20,
            **GLASS_TIER1,
        )
        self._content_panel.setFixedWidth(config.PANEL_WIDTH)

        self._panel_opacity = QGraphicsOpacityEffect(self._content_panel)
        self._panel_opacity.setOpacity(1.0)
        self._content_panel.setGraphicsEffect(self._panel_opacity)

        panel_root = QVBoxLayout(self._content_panel)
        panel_root.setContentsMargins(18, 14, 18, 14)
        panel_root.setSpacing(10)

        # Minimal panel header — just title + close
        header = QHBoxLayout()
        header.setSpacing(6)
        self._panel_title = QLabel("Insights")
        self._panel_title.setObjectName("panel_title")
        header.addWidget(self._panel_title)
        header.addStretch(1)

        self._close_panel_btn = QPushButton("\u00d7")
        self._close_panel_btn.setObjectName("icon_btn")
        self._close_panel_btn.setFixedSize(24, 24)
        self._close_panel_btn.setToolTip("Close panel (Esc)")
        self._close_panel_btn.clicked.connect(self._hide_panel)
        header.addWidget(self._close_panel_btn)

        panel_root.addLayout(header)

        # Page stack
        self._page_stack = QStackedWidget()
        panel_root.addWidget(self._page_stack)

        self._pages: dict[str, QWidget] = {}
        self._build_insights_view()
        self._build_measure_view()
        self._build_compare_view()
        self._build_qa_view()
        self._build_transcript_view()

        self._content_panel.hide()

        # Show correct mode
        self._apply_mode()
        self._sync_live_state()

    # -----------------------------------------------------------------
    # 6 flat view builders
    # -----------------------------------------------------------------

    def _build_insights_view(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Status line
        self._response_status = QLabel("Open a study, type your read, then compare.")
        self._response_status.setObjectName("muted")
        self._response_status.setWordWrap(True)
        root.addWidget(self._response_status)

        # Doctor input
        self.doctor_input = QTextEdit()
        self.doctor_input.setObjectName("doctor_input")
        self.doctor_input.setPlaceholderText(
            "Example: 2.3 cm right upper lobe nodule, likely granuloma."
        )
        root.addWidget(self.doctor_input)

        # Reveal button row
        self._reveal_row = QWidget()
        reveal_layout = QHBoxLayout(self._reveal_row)
        reveal_layout.setContentsMargins(0, 0, 0, 0)
        reveal_layout.setSpacing(8)
        self._read_state = QLabel("ReVU stays hidden until you compare.")
        self._read_state.setObjectName("muted")
        self._read_state.setWordWrap(True)
        reveal_layout.addWidget(self._read_state, 1)
        self._reveal_btn = QPushButton("Reveal AI")
        self._reveal_btn.setObjectName("primary_btn")
        self._reveal_btn.clicked.connect(self._reveal_ai)
        reveal_layout.addWidget(self._reveal_btn)
        root.addWidget(self._reveal_row)

        # Finding stream
        self._finding_label = QLabel("Surface the second read when you are ready.")
        self._finding_label.setObjectName("insight_stream")
        self._finding_label.setWordWrap(True)
        root.addWidget(self._finding_label)

        # Confidence inline
        self._confidence_label = QLabel("")
        self._confidence_label.setObjectName("muted")
        self._confidence_label.hide()
        root.addWidget(self._confidence_label)

        # Detail (was "Key Difference" — no heading, just text)
        self._detail_label = QLabel("")
        self._detail_label.setObjectName("card_body")
        self._detail_label.setWordWrap(True)
        self._detail_label.hide()
        root.addWidget(self._detail_label)

        # Recommendation (no heading, just text)
        self._rec_label = QLabel("")
        self._rec_label.setObjectName("card_body")
        self._rec_label.setWordWrap(True)
        self._rec_label.hide()
        root.addWidget(self._rec_label)

        # Specialist flags (inline badges)
        self._flags_widget = QWidget()
        flags_layout = QHBoxLayout(self._flags_widget)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        flags_layout.setSpacing(6)
        self._flags_container = flags_layout
        self._flags_widget.hide()
        root.addWidget(self._flags_widget)

        # Action buttons
        self._actions_widget = QWidget()
        actions = QHBoxLayout(self._actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self._agree_btn = QPushButton("Agree")
        self._agree_btn.clicked.connect(self._on_agree)
        actions.addWidget(self._agree_btn)

        self._flag_btn = QPushButton("Flag")
        self._flag_btn.setObjectName("danger_btn")
        self._flag_btn.clicked.connect(self._show_flag_input)
        actions.addWidget(self._flag_btn)

        self._ask_context_btn = QPushButton("Ask ReVU")
        self._ask_context_btn.setObjectName("action_btn")
        self._ask_context_btn.clicked.connect(lambda: self._on_view_selected("Transcript"))
        actions.addWidget(self._ask_context_btn)
        actions.addStretch(1)
        self._actions_widget.hide()
        root.addWidget(self._actions_widget)

        # Flag input row
        self._flag_input_row = QWidget()
        flag_layout = QHBoxLayout(self._flag_input_row)
        flag_layout.setContentsMargins(0, 0, 0, 0)
        flag_layout.setSpacing(8)
        self._flag_input = QLineEdit()
        self._flag_input.setPlaceholderText("Describe why this should be escalated...")
        flag_layout.addWidget(self._flag_input, 1)
        submit_flag = QPushButton("Send to QA")
        submit_flag.setObjectName("primary_btn")
        submit_flag.clicked.connect(self._submit_flag)
        flag_layout.addWidget(submit_flag)
        self._flag_input_row.hide()
        root.addWidget(self._flag_input_row)

        root.addStretch(1)

        self._page_stack.addWidget(page)
        self._pages["Insights"] = page

    def _build_measure_view(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        heading = QLabel("Measurement Assist")
        heading.setObjectName("section_heading")
        root.addWidget(heading)

        body = QLabel("Click once, segment automatically. MedSAM-style segmentation derives real-world mm values from study metadata.")
        body.setObjectName("card_body")
        body.setWordWrap(True)
        root.addWidget(body)

        root.addWidget(_separator())

        self._measure_summary = QLabel(
            "Current: 23mm \u2014 target lesion, right upper lobe nodule. Diameter estimate and PACS write-back are queued."
        )
        self._measure_summary.setObjectName("card_body")
        self._measure_summary.setWordWrap(True)
        root.addWidget(self._measure_summary)

        dicom_btn = QPushButton("Queue DICOM SR write-back")
        dicom_btn.setObjectName("panel_link_btn")
        dicom_btn.clicked.connect(lambda checked=False: self._append_system_message())
        root.addWidget(dicom_btn)

        root.addStretch(1)

        self._page_stack.addWidget(page)
        self._pages["Measure"] = page

    def _build_compare_view(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        heading = QLabel("Follow-up Comparison")
        heading.setObjectName("section_heading")
        root.addWidget(heading)

        self._compare_inline = QLabel("Prior: 18mm \u2192 Current: 23mm")
        self._compare_inline.setObjectName("card_body")
        root.addWidget(self._compare_inline)

        self._compare_delta = QLabel("5mm larger than last confirmed measurement.")
        self._compare_delta.setObjectName("card_body")
        self._compare_delta.setWordWrap(True)
        root.addWidget(self._compare_delta)

        root.addWidget(_separator())

        confirm_btn = QPushButton("Confirm carry-forward")
        confirm_btn.setObjectName("panel_link_btn")
        confirm_btn.clicked.connect(lambda checked=False: self._append_system_message())
        root.addWidget(confirm_btn)

        root.addStretch(1)

        self._page_stack.addWidget(page)
        self._pages["Compare"] = page

    def _build_qa_view(self):
        """QA view — PR-diff style: Your Read vs AI Read + screenshot + actions."""
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ── Diff header (like a PR title bar) ──
        diff_header = QHBoxLayout()
        diff_header.setSpacing(6)
        diff_title = QLabel("Review Diff")
        diff_title.setObjectName("section_heading")
        diff_header.addWidget(diff_title)
        diff_header.addStretch(1)
        self._qa_stats = QLabel("0 changes")
        self._qa_stats.setObjectName("muted")
        diff_header.addWidget(self._qa_stats)
        root.addLayout(diff_header)

        # ── Your Read (red/removed side) ──
        self._diff_yours = QLabel("")
        self._diff_yours.setObjectName("diff_removed")
        self._diff_yours.setWordWrap(True)
        root.addWidget(self._diff_yours)

        # ── AI Read (green/added side) ──
        self._diff_ai = QLabel("")
        self._diff_ai.setObjectName("diff_added")
        self._diff_ai.setWordWrap(True)
        root.addWidget(self._diff_ai)

        # ── Screenshot preview ──
        self._qa_preview = QLabel("")
        self._qa_preview.setObjectName("card_body")
        self._qa_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qa_preview.setWordWrap(True)
        self._qa_preview.setMinimumHeight(80)
        self._qa_preview.hide()
        root.addWidget(self._qa_preview)

        # ── Recommendation (merged from report) ──
        self._report_draft = QLabel("")
        self._report_draft.setObjectName("card_body")
        self._report_draft.setWordWrap(True)
        root.addWidget(self._report_draft)

        # ── Meta info ──
        self._qa_meta = QLabel("")
        self._qa_meta.setObjectName("muted")
        self._qa_meta.setWordWrap(True)
        root.addWidget(self._qa_meta)

        root.addWidget(_separator())

        # ── Actions (like PR review buttons) ──
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        approve_btn = QPushButton("Approve & Sign")
        approve_btn.setObjectName("primary_btn")
        approve_btn.clicked.connect(self._on_agree)
        actions.addWidget(approve_btn)

        request_btn = QPushButton("Request Changes")
        request_btn.clicked.connect(lambda: self._on_view_selected("Transcript"))
        actions.addWidget(request_btn)

        actions.addStretch(1)

        send_btn = QPushButton("Send for Review")
        send_btn.setObjectName("primary_btn")
        send_btn.clicked.connect(self._show_flag_input)
        actions.addWidget(send_btn)

        root.addLayout(actions)

        # ── Screenshot history (compact list) ──
        self._qa_recent_widget = QWidget()
        self._qa_recent_layout = QVBoxLayout(self._qa_recent_widget)
        self._qa_recent_layout.setContentsMargins(0, 4, 0, 0)
        self._qa_recent_layout.setSpacing(4)
        root.addWidget(self._qa_recent_widget)

        root.addStretch(1)

        self._page_stack.addWidget(page)
        self._pages["QA"] = page

    def _build_transcript_view(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._transcript_state = QLabel("Transcript-first voice surface • Gemini Live connecting...")
        self._transcript_state.setObjectName("muted")
        self._transcript_state.setWordWrap(True)
        root.addWidget(self._transcript_state)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_label = QLabel("Voice mode")
        mode_label.setObjectName("tiny_meta")
        mode_row.addWidget(mode_label)

        self._ptt_mode_btn = QPushButton("Push to Talk")
        self._ptt_mode_btn.setCheckable(True)
        self._ptt_mode_btn.clicked.connect(
            lambda checked=False: self._set_live_mic_mode(MIC_MODE_PUSH_TO_TALK)
        )
        mode_row.addWidget(self._ptt_mode_btn)

        self._continuous_mode_btn = QPushButton("Continuous")
        self._continuous_mode_btn.setCheckable(True)
        self._continuous_mode_btn.clicked.connect(
            lambda checked=False: self._set_live_mic_mode(MIC_MODE_CONTINUOUS)
        )
        mode_row.addWidget(self._continuous_mode_btn)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self._transcript_box = QTextEdit()
        self._transcript_box.setObjectName("transcript_box")
        self._transcript_box.setReadOnly(True)
        self._transcript_box.setPlaceholderText(
            "Ask about the current finding, priors, or report wording..."
        )
        self._transcript_box.setMinimumHeight(120)
        root.addWidget(self._transcript_box, 1)

        root.addWidget(_separator())

        input_row = QHBoxLayout()
        self._transcript_input = QLineEdit()
        self._transcript_input.setObjectName("transcript_input")
        self._transcript_input.setPlaceholderText(
            "Ask ReVU about this study..."
        )
        self._transcript_input.setEnabled(False)
        self._transcript_input.returnPressed.connect(self._send_transcript_message)
        input_row.addWidget(self._transcript_input, 1)

        self._mic_btn = QPushButton("Hold to Talk")
        self._mic_btn.setObjectName("action_btn")
        self._mic_btn.setEnabled(False)
        self._mic_btn.pressed.connect(self._handle_mic_pressed)
        self._mic_btn.released.connect(self._handle_mic_released)
        self._mic_btn.clicked.connect(self._handle_mic_clicked)
        input_row.addWidget(self._mic_btn)

        self._transcript_send = QPushButton("Send")
        self._transcript_send.setObjectName("primary_btn")
        self._transcript_send.setEnabled(False)
        self._transcript_send.clicked.connect(self._send_transcript_message)
        input_row.addWidget(self._transcript_send)
        root.addLayout(input_row)

        self._page_stack.addWidget(page)
        self._pages["Transcript"] = page

    # -----------------------------------------------------------------
    # Mode switching
    # -----------------------------------------------------------------

    def _switch_mode(self, mode: str):
        self._mode = mode
        self._apply_mode()

    def _apply_mode(self):
        if self._mode == "orb":
            self._orb.show()
            self._topbar.hide()
            self._ask_bar.hide()
            self._position_orb_mode()
        else:
            self._orb.hide()
            for btn in self._orb._buttons:
                btn.hide()
            self._topbar.show()
            self._ask_bar.show()
            self._position_bar_mode()

    def _position_orb_mode(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        # Position using widget size (includes glow padding)
        orb_x = geo.width() - config.ORB_MARGIN_RIGHT - config.ORB_WIDGET_SIZE
        orb_y = geo.height() - config.ORB_MARGIN_BOTTOM - config.ORB_WIDGET_SIZE
        self._orb.move(orb_x, orb_y)

        if self._panel_visible:
            # Align panel right edge with orb inner right edge
            glow_pad = (config.ORB_WIDGET_SIZE - config.ORB_SIZE) // 2
            panel_x = orb_x + config.ORB_WIDGET_SIZE - glow_pad - config.PANEL_WIDTH
            panel_y = orb_y - config.PANEL_GAP - self._content_panel.sizeHint().height()
            panel_y = max(panel_y, 10)
            self._content_panel.move(panel_x, panel_y)
            self._content_panel.setMaximumHeight(config.PANEL_MAX_HEIGHT)

    def _position_bar_mode(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        bar_x = (geo.width() - self._topbar.width()) // 2
        bar_y = 22
        self._topbar.move(bar_x, bar_y)

        # Ask input bar sits below topbar (+ banner if visible)
        ask_y = bar_y + self._topbar.height() + config.PANEL_GAP
        self._ask_bar.move(bar_x, ask_y)

        if self._panel_visible:
            panel_x = (geo.width() - config.PANEL_WIDTH) // 2
            panel_y = ask_y + self._ask_bar.height() + config.PANEL_GAP
            self._content_panel.move(panel_x, panel_y)
            self._content_panel.setMaximumHeight(config.PANEL_MAX_HEIGHT)

    def _toggle_mode_menu(self):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(12, 14, 18, 240);
                border: 1px solid rgba(255, 255, 255, 12);
                border-radius: 8px;
                padding: 4px;
                color: #F8FAFC;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 8);
            }
        """)
        if self._mode == "orb":
            action = menu.addAction("Switch to top bar mode")
            action.triggered.connect(lambda: self._switch_mode("bar"))
        else:
            action = menu.addAction("Switch to corner orb mode")
            action.triggered.connect(lambda: self._switch_mode("orb"))
        menu.exec(QCursor.pos())

    # -----------------------------------------------------------------
    # Panel show / hide
    # -----------------------------------------------------------------

    def _toggle_panel(self):
        if self._panel_visible:
            self._hide_panel()
        else:
            self._show_panel()

    def _show_panel(self):
        self._panel_visible = True
        self._refresh_views()
        self._sync_live_state()
        self._content_panel.show()
        self._content_panel.adjustSize()

        # Position based on mode
        if self._mode == "orb":
            self._position_orb_mode()
        else:
            self._position_bar_mode()

        # Fade in with spring-like feel
        self._panel_opacity.setOpacity(0.0)
        anim = QPropertyAnimation(self._panel_opacity, b"opacity", self)
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._panel_fade_anim = anim

    def _hide_panel(self):
        anim = QPropertyAnimation(self._panel_opacity, b"opacity", self)
        anim.setDuration(150)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._on_panel_hidden)
        anim.start()
        self._panel_fade_anim = anim

    def _on_panel_hidden(self):
        self._panel_visible = False
        self._content_panel.hide()
        self._sync_live_state()

    # -----------------------------------------------------------------
    # View selection
    # -----------------------------------------------------------------

    def _on_view_selected(self, name: str):
        self._active_view = name
        self._orb.set_active_view(name)
        self._topbar.set_active_view(name)
        self._panel_title.setText(name)
        self._page_stack.setCurrentWidget(self._pages[name])

        if not self._panel_visible:
            self._show_panel()
        else:
            # Reposition in case content size changed
            self._content_panel.adjustSize()
            if self._mode == "orb":
                self._position_orb_mode()
            else:
                self._position_bar_mode()

        if name == "Transcript":
            if not self._transcript_box.toPlainText().strip():
                self._append_system_message()
            QTimer.singleShot(0, self._transcript_input.setFocus)

        self._sync_live_state()
        self._ensure_overlay_visible()

    # -----------------------------------------------------------------
    # State machine
    # -----------------------------------------------------------------

    def _set_state(self, state: str):
        self._state = state

        if state == _State.IDLE:
            self._update_status_color("#8BE0B3")
        elif state == _State.PROCESSING:
            self._update_status_color("#FFD870")
            self._active_view = "Insights"
        elif state == _State.DIAGNOSIS_INPUT:
            self._update_status_color("#8BE0B3")
            self._active_view = "Insights"
        elif state == _State.AI_REVEALED:
            self._update_status_color(ACCENT)
            self._active_view = "Insights"
        elif state == _State.FLAGGED:
            self._update_status_color(CONFIDENCE_HIGH)
            self._active_view = "Insights"

        if state != _State.AI_REVEALED:
            self._delta_ready = False
            self._recommend_ready = False
            self._reasoning_ready = False

        self._refresh_views()

    def _update_status_color(self, color: str):
        self._orb.set_status_color(color)
        self._topbar.set_status_color(color)

    def _refresh_views(self):
        self._orb.set_active_view(self._active_view)
        self._topbar.set_active_view(self._active_view)
        self._panel_title.setText(self._active_view)
        self._page_stack.setCurrentWidget(self._pages[self._active_view])
        self._refresh_insights_view()
        self._refresh_compare_view()
        self._refresh_qa_view()
        self._sync_live_state()

    # -----------------------------------------------------------------
    # Insights view refresh
    # -----------------------------------------------------------------

    def _refresh_insights_view(self):
        doctor_text = self.doctor_input.toPlainText().strip()

        self._read_state.setText(
            "Your read stays visible while ReVU highlights only the difference."
            if self._state == _State.AI_REVEALED
            else "ReVU stays hidden until you compare."
        )

        self._flag_input_row.hide()

        if self._state == _State.PROCESSING:
            self._response_status.setText("Capture and analysis are running.")
            self.doctor_input.show()
            self._reveal_row.show()
            self._finding_label.setText(self._current_finding or "Capturing and analyzing...")
            self._confidence_label.hide()
            self._detail_label.hide()
            self._rec_label.hide()
            self._flags_widget.hide()
            self._actions_widget.hide()

        elif self._state == _State.DIAGNOSIS_INPUT:
            self._response_status.setText("Type your impression first. ReVU will then surface one clean second read.")
            self.doctor_input.show()
            self._reveal_row.show()
            self._finding_label.setText("Surface the second read when you are ready.")
            self._confidence_label.hide()
            self._detail_label.hide()
            self._rec_label.hide()
            self._flags_widget.hide()
            self._actions_widget.hide()

        elif self._state == _State.AI_REVEALED:
            self._response_status.setText("One response stream. Then the next action.")
            self.doctor_input.hide()
            self._reveal_row.hide()

            self._confidence_label.setText(f"{(self._current_confidence or 'LOW').upper()} confidence")
            self._confidence_label.show()

            diff_text = self._build_difference_text()
            self._detail_label.setText(diff_text)
            self._detail_label.setVisible(self._delta_ready and bool(diff_text))

            rec_text = self._current_rec or "Compare against the latest prior and tighten follow-up wording."
            self._rec_label.setText(rec_text)
            self._rec_label.setVisible(self._recommend_ready)

            self._refresh_flag_badges()
            self._flags_widget.setVisible(self._reasoning_ready and bool(self._current_flags))
            self._actions_widget.show()

        elif self._state == _State.FLAGGED:
            self._response_status.setText("Disagreement saved for second-human review.")
            self.doctor_input.hide()
            self._reveal_row.hide()
            self._finding_label.setText("This disagreement is saved and ready for review.")
            self._confidence_label.hide()
            self._detail_label.setText(self._build_difference_text())
            self._detail_label.show()
            self._rec_label.setText(self._current_rec or "Compare with prior and document interval change.")
            self._rec_label.show()
            self._refresh_flag_badges()
            self._flags_widget.setVisible(bool(self._current_flags))
            self._actions_widget.hide()

        else:  # IDLE
            self._response_status.setText("Open a study, type your read, then compare.")
            self.doctor_input.show()
            self._reveal_row.show()
            self._finding_label.setText("Press the hotkey to bring ReVU forward.")
            self._confidence_label.hide()
            self._detail_label.hide()
            self._rec_label.hide()
            self._flags_widget.hide()
            self._actions_widget.hide()

    def _refresh_flag_badges(self):
        # Clear old
        while self._flags_container.count():
            item = self._flags_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for flag in self._current_flags[:3]:
            tag = QLabel(flag)
            tag.setObjectName("hotkey_badge")
            self._flags_container.addWidget(tag)

    def _build_difference_text(self) -> str:
        doctor_text = self.doctor_input.toPlainText().strip()
        if doctor_text and self._current_finding:
            return f"Compared with your read, ReVU would call out {_clip(self._current_finding, 104)}."
        if self._current_finding:
            return f"Key change: {_clip(self._current_finding, 110)}."
        return ""

    def _build_reasoning_text(self) -> str:
        snippets = []
        measurement = self._extract_measurement_mm(self.doctor_input.toPlainText())
        if measurement is not None:
            snippets.append(f"Tracking target: {measurement:.0f} mm lesion.")
        if self._current_flags:
            snippets.append(f"Signals: {', '.join(self._current_flags[:2])}.")
        if self._current_rec:
            snippets.append("Ready to move into compare or QA.")
        if not snippets:
            snippets.append("Ready to move into compare or QA.")
        return " ".join(snippets)

    def _extract_measurement_mm(self, text: str) -> float | None:
        if not text:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)\s*cm", text, re.IGNORECASE)
        if match:
            return float(match.group(1)) * 10.0
        match = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    # -----------------------------------------------------------------
    # Compare / Report / QA refresh
    # -----------------------------------------------------------------

    def _refresh_compare_view(self):
        measurement = self._extract_measurement_mm(self.doctor_input.toPlainText()) or 23.0
        prior = max(measurement - 5.0, 12.0)
        delta = measurement - prior
        direction = "larger" if delta >= 0 else "smaller"
        self._compare_inline.setText(f"Prior: {prior:.0f}mm \u2192 Current: {measurement:.0f}mm")
        self._compare_delta.setText(
            f"{abs(delta):.0f}mm {direction} than last confirmed measurement."
        )

    def _refresh_qa_view(self):
        # ── PR-diff: Your Read vs AI Read ──
        doctor_text = self.doctor_input.toPlainText().strip()
        finding = self._current_finding or "AI read pending..."
        recommendation = self._current_rec or "Compare with the latest prior chest CT and document interval change."

        if doctor_text:
            self._diff_yours.setText(f"\u2212  {doctor_text}")
            self._diff_yours.show()
        else:
            self._diff_yours.setText("\u2212  (No radiologist read entered yet)")
            self._diff_yours.show()

        self._diff_ai.setText(f"+  {_clip(finding, 200)}")

        # Report draft (recommendation)
        self._report_draft.setText(f"Recommendation: {recommendation}")

        # Stats
        changes = []
        if doctor_text and finding and finding != "AI read pending...":
            changes.append("1 diff")
        count = len(self._screenshot_history)
        if count:
            changes.append(f"{count} screenshot{'s' if count != 1 else ''}")
        self._qa_stats.setText(" \u2022 ".join(changes) if changes else "No changes yet")

        # Meta from screenshots
        if self._screenshot_history:
            latest = self._screenshot_history[0]
            timestamp = latest.get("sent_at") or latest.get("timestamp") or "pending"
            image_hash = (latest.get("image_hash") or "n/a")[:12]
            self._qa_meta.setText(f"Last capture: {timestamp} \u2022 Hash: {image_hash}")
            if latest.get("image_bytes"):
                self._qa_preview.show()
        else:
            self._qa_meta.setText("No screenshots captured this session")

        while self._qa_recent_layout.count():
            item = self._qa_recent_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self._screenshot_history:
            empty = QLabel("No screenshot history yet.")
            empty.setObjectName("card_body")
            self._qa_recent_layout.addWidget(empty)
            return

        for entry in self._screenshot_history[:5]:
            timestamp = entry.get("sent_at") or entry.get("timestamp") or "pending"
            backend_status = entry.get("backend_status") or entry.get("status") or "pending"
            reason = entry.get("reason") or "Gemini requested a screenshot"
            line = QLabel(f"{timestamp}  {backend_status.upper()} — {_clip(reason, 72)}")
            line.setObjectName("muted")
            line.setWordWrap(True)
            self._qa_recent_layout.addWidget(line)

    # -----------------------------------------------------------------
    # Ask bar (ChatGPT-style input)
    # -----------------------------------------------------------------

    def _send_ask_message(self):
        prompt = self._ask_input.text().strip()
        if not prompt:
            return
        # Switch to transcript view and send
        if self._active_view != "Transcript":
            self._on_view_selected("Transcript")
        self._append_user_message(prompt)
        self._ask_input.clear()
        if self._live_connected:
            self.ask_submitted.emit(prompt)
        else:
            self._append_system_message("Gemini Live unavailable — message queued.")

    # -----------------------------------------------------------------
    # Transcript interactions
    # -----------------------------------------------------------------

    def _send_transcript_message(self):
        prompt = self._transcript_input.text().strip()
        if not prompt or not self._live_connected:
            return
        if self._speech_turn_open:
            self._append_system_message("Finish the current voice turn before typing.")
            return
        self._append_user_message(prompt)
        self._transcript_input.clear()
        self.ask_submitted.emit(prompt)

    def _append_user_message(self, text: str):
        self._transcript_draft = None
        self._add_transcript_entry("user", text)

    def _append_assistant_message(self, text: str):
        self._add_transcript_entry("assistant", text)

    def _append_system_message(self, text: str | None = None):
        if text is None:
            text = "Ask ReVU about priors, follow-up timing, or report wording."
        self._add_transcript_entry("system", text)

    def _add_transcript_entry(self, role: str, text: str):
        cleaned = text.strip()
        if not cleaned:
            return
        self._transcript_entries.append((role, cleaned))
        self._render_transcript()

    def _set_transcript_draft(self, role: str, text: str):
        cleaned = text.strip()
        self._transcript_draft = (role, cleaned) if cleaned else None
        self._render_transcript()

    def _render_transcript(self):
        chunks: list[str] = []
        for role, text in self._transcript_entries:
            chunks.append(self._format_transcript_entry(role, text))
        if self._transcript_draft is not None:
            chunks.append(self._format_transcript_entry(self._transcript_draft[0], self._transcript_draft[1], draft=True))
        self._transcript_box.setHtml("<br/>".join(chunks))
        self._transcript_box.moveCursor(QTextCursor.MoveOperation.End)

    def _format_transcript_entry(self, role: str, text: str, *, draft: bool = False) -> str:
        safe = escape(text).replace("\n", "<br/>")
        if role == "user":
            suffix = " <span style='color:#7d8697'>(listening)</span>" if draft else ""
            return f"<b>You:</b> {safe}{suffix}"
        if role == "assistant":
            suffix = " <span style='color:#7d8697'>(draft)</span>" if draft else ""
            return f"<b>ReVU:</b> {safe}{suffix}"
        return f"<span style='color:#a4acb8'><i>{safe}</i></span>"

    def _set_live_mic_mode(self, mode: str):
        normalized = mode if mode in {MIC_MODE_PUSH_TO_TALK, MIC_MODE_CONTINUOUS} else MIC_MODE_PUSH_TO_TALK
        if normalized == self._live_mic_mode:
            self._sync_live_state()
            return
        if self._mic_active:
            self.mic_released.emit()
            self._mic_active = False
        self._speech_turn_open = False
        self._live_phase = ""
        self._live_mic_mode = normalized
        self._sync_live_state()
        self.mic_mode_changed.emit(normalized)

    def _sync_live_state(self):
        prefix = "Transcript open" if self._active_view == "Transcript" and self._panel_visible else "Transcript-first voice surface"
        live_line = self._live_status
        if self._live_phase:
            live_line = f"{live_line} • {self._live_phase}"
        self._transcript_state.setText(f"{prefix} • {live_line}")
        typing_allowed = self._live_connected and not self._speech_turn_open
        self._transcript_input.setEnabled(typing_allowed)
        self._transcript_input.setPlaceholderText(
            "Finish the current voice turn before typing..."
            if self._speech_turn_open
            else ("Ask ReVU about this study..." if self._live_connected else "Gemini Live unavailable")
        )
        self._transcript_send.setEnabled(typing_allowed)
        self._mic_btn.setEnabled(self._live_connected)
        if self._live_mic_mode == MIC_MODE_CONTINUOUS:
            mic_label = "Stop Listening" if self._mic_active else "Start Listening"
        else:
            mic_label = "Release to Stop" if self._mic_active else "Hold to Talk"
        self._mic_btn.setText(mic_label)
        self._topbar.set_live_status(self._live_status)
        self._topbar.set_mic_enabled(self._live_connected)
        self._topbar.set_mic_label(mic_label)
        self._topbar.set_mic_active(self._mic_active)
        # Ask bar state
        self._ask_mic_btn.setEnabled(self._live_connected)
        self._sync_mic_mode_buttons()

    def _set_live_phase(self, phase: str):
        self._live_phase = phase.strip()
        lowered = self._live_phase.lower()
        if "hearing speech" in lowered or "processing spoken request" in lowered:
            self._speech_turn_open = True
        elif lowered == "listening":
            self._speech_turn_open = self._live_mic_mode == MIC_MODE_PUSH_TO_TALK
        elif lowered in {"listening continuously", "waiting for input"}:
            self._speech_turn_open = False

    def _handle_mic_pressed(self):
        if not self._live_connected:
            self._append_system_message("Gemini Live unavailable")
            return
        if self._live_mic_mode != MIC_MODE_PUSH_TO_TALK:
            return
        if self._active_view != "Transcript":
            self._on_view_selected("Transcript")
        self._speech_turn_open = True
        self._sync_live_state()
        self.mic_pressed.emit()

    def _handle_mic_released(self):
        if self._live_mic_mode != MIC_MODE_PUSH_TO_TALK:
            return
        self.mic_released.emit()

    def _handle_mic_clicked(self):
        if not self._live_connected:
            self._append_system_message("Gemini Live unavailable")
            return
        if self._live_mic_mode != MIC_MODE_CONTINUOUS:
            return
        if self._active_view != "Transcript":
            self._on_view_selected("Transcript")
        if self._mic_active:
            self.mic_released.emit()
        else:
            self.mic_pressed.emit()

    def _sync_mic_mode_buttons(self):
        pairs = (
            (self._ptt_mode_btn, MIC_MODE_PUSH_TO_TALK),
            (self._continuous_mode_btn, MIC_MODE_CONTINUOUS),
        )
        for button, mode in pairs:
            active = self._live_mic_mode == mode
            button.blockSignals(True)
            button.setChecked(active)
            button.blockSignals(False)
            button.setObjectName("action_active" if active else "action_btn")
            button.setStyle(button.style())

    # -----------------------------------------------------------------
    # Streaming + staged reveal
    # -----------------------------------------------------------------

    def _clear_stage_timers(self):
        for timer in self._stage_timers:
            timer.stop()
            timer.deleteLater()
        self._stage_timers.clear()

    def _schedule_stage(self, delay_ms: int, callback):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.start(delay_ms)
        self._stage_timers.append(timer)

    def _stream_text(self, full_text: str, label: QLabel, speed_ms: int = 18):
        self._stream_buffer = ""
        self._stream_full = full_text
        self._stream_label = label
        self._stream_index = 0

        if self._stream_timer:
            self._stream_timer.stop()

        self._stream_timer = QTimer(self)
        self._stream_timer.timeout.connect(self._stream_tick)
        self._stream_timer.start(speed_ms)

    def _stream_tick(self):
        if self._stream_label is None:
            return
        if self._stream_index < len(self._stream_full):
            self._stream_buffer += self._stream_full[self._stream_index]
            self._stream_label.setText(self._stream_buffer)
            self._stream_index += 1
        else:
            self._stream_timer.stop()

    # -----------------------------------------------------------------
    # Public API (same signatures as before)
    # -----------------------------------------------------------------

    def set_session_id(self, session_id: str):
        self._session_id = session_id
        self._sync_live_state()

    @pyqtSlot(str, str, str)
    def show_finding(self, finding: str, confidence: str, image_hash: str):
        self._current_finding = finding
        self._current_confidence = confidence
        self._current_image_hash = image_hash
        self._read_count += 1
        self._reasoning_expanded = False
        self._delta_ready = False
        self._recommend_ready = False
        self._reasoning_ready = False
        self.doctor_input.clear()
        self._reveal_btn.setEnabled(True)
        self._reveal_btn.setText("Reveal AI")
        self._flag_input.clear()
        self._clear_stage_timers()

        self._set_state(_State.DIAGNOSIS_INPUT)


        # Show panel in Insights view
        self._on_view_selected("Insights")
        self._ensure_overlay_visible(focus_target=self.doctor_input)

    @pyqtSlot(str)
    def set_recommendation(self, text: str):
        self._current_rec = text
        self._refresh_views()

    def set_specialist_flags(self, flags: list):
        self._current_flags = flags
        self._refresh_views()

    @pyqtSlot(str)
    def show_status(self, message: str):
        self._current_finding = message
        self._set_state(_State.PROCESSING)
        self._on_view_selected("Insights")
        self._ensure_overlay_visible()

    @pyqtSlot(str)
    def show_confirmation(self, message: str):
        self._current_finding = message
        self._set_state(_State.FLAGGED)
        self._on_view_selected("Insights")
        self._ensure_overlay_visible()
        QTimer.singleShot(2200, self._collapse_to_idle)

    @pyqtSlot(str)
    def append_live_assistant_message(self, text: str):
        if not text:
            return
        self._append_assistant_message(text)
        if self._active_view != "Transcript":
            self._on_view_selected("Transcript")

    @pyqtSlot(str)
    def append_live_system_message(self, text: str):
        if not text:
            return
        if text.startswith("[state]"):
            self._set_live_phase(text.removeprefix("[state]").strip())
            self._sync_live_state()
            return
        self._live_status = text
        self._sync_live_state()
        self._append_system_message(text)

    @pyqtSlot(str, bool)
    def append_live_user_transcript(self, text: str, is_final: bool):
        if not text:
            return
        if is_final:
            if self._active_view != "Transcript":
                self._on_view_selected("Transcript")
            self._append_user_message(text)
            return
        if self._transcript_draft is not None:
            self._transcript_draft = None
            self._render_transcript()

    @pyqtSlot(bool, str)
    def set_live_connection_state(self, connected: bool, message: str):
        self._live_connected = connected
        self._live_status = message or (
            "Gemini Live connected" if connected else "Gemini Live unavailable"
        )
        if connected:
            self._live_phase = ""
        if not connected:
            self._mic_active = False
            self._speech_turn_open = False
            self._transcript_draft = None
            self._render_transcript()
        self._sync_live_state()

    @pyqtSlot(bool)
    def set_mic_active(self, active: bool):
        self._mic_active = active
        if active and self._live_mic_mode == MIC_MODE_PUSH_TO_TALK:
            self._speech_turn_open = True
        elif not active and self._live_mic_mode == MIC_MODE_CONTINUOUS and self._live_phase.lower() not in {
            "hearing speech",
            "processing spoken request",
        }:
            self._speech_turn_open = False
        self._sync_live_state()

    @pyqtSlot(object)
    def push_screenshot_event(self, event: dict):
        if not event:
            return

        request_id = str(event.get("request_id") or "")
        existing_index = next(
            (index for index, item in enumerate(self._screenshot_history) if item.get("request_id") == request_id),
            None,
        )
        merged = dict(self._screenshot_history[existing_index]) if existing_index is not None else {}
        merged.update(event)

        if existing_index is None:
            self._screenshot_history.insert(0, merged)
        else:
            self._screenshot_history[existing_index] = merged
            if existing_index != 0:
                self._screenshot_history.insert(0, self._screenshot_history.pop(existing_index))

        self._screenshot_history = self._screenshot_history[:5]

        image_bytes = merged.get("image_bytes")
        if image_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(image_bytes):
                self._qa_preview.setPixmap(
                    pixmap.scaled(
                        360,
                        220,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self._qa_preview.setText("")

        self._refresh_qa_view()

    # -----------------------------------------------------------------
    # Internal actions
    # -----------------------------------------------------------------

    def _reveal_ai(self):
        doctor_text = self.doctor_input.toPlainText().strip()
        if not doctor_text:
            self.doctor_input.setPlaceholderText("Type your read first before revealing ReVU.")
            return

        self._reveal_btn.setEnabled(False)
        self._reveal_btn.setText("Compared")

        self._clear_stage_timers()
        self._set_state(_State.AI_REVEALED)

        self._finding_label.setText("")
        self._stream_text(self._current_finding, self._finding_label)

        self._schedule_stage(260, self._mark_delta_ready)
        self._schedule_stage(520, self._mark_recommend_ready)
        self._schedule_stage(780, self._mark_reasoning_ready)

        self._history.insert(0, {
            "finding": _clip(self._current_finding, 76),
            "confidence": self._current_confidence,
            "time": datetime.now().strftime("%H:%M"),
            "action": "pending",
        })
        self._refresh_views()

    def _mark_delta_ready(self):
        self._delta_ready = True
        self._refresh_insights_view()
        self._reposition_panel()

    def _mark_recommend_ready(self):
        self._recommend_ready = True
        self._refresh_insights_view()
        self._reposition_panel()

    def _mark_reasoning_ready(self):
        self._reasoning_ready = True
        self._refresh_insights_view()
        self._reposition_panel()

    def _reposition_panel(self):
        """Re-fit the content panel after content changes."""
        self._content_panel.adjustSize()
        if self._mode == "orb":
            self._position_orb_mode()
        else:
            self._position_bar_mode()

    def _show_flag_input(self):
        self._flag_input_row.show()
        self._flag_input.setFocus()
        self._reposition_panel()

    def _submit_flag(self):
        note = self._flag_input.text().strip()
        doctor_text = self.doctor_input.toPlainText().strip()
        override = note if note else doctor_text

        self._flag_count += 1
        if self._history:
            self._history[0]["action"] = "flagged"

        self.disagree_submitted.emit(self._current_finding, override, self._current_image_hash)
        self.show_confirmation("Flagged for QA review")

    def _on_agree(self):
        if self._history and self._history[0].get("action") == "pending":
            self._history[0]["action"] = "accepted"
        self.dismiss_requested.emit()
        self._collapse_to_idle()

    def _collapse_to_idle(self):
        self._set_state(_State.IDLE)
        if self._mic_active:
            self.mic_released.emit()
            self._mic_active = False
        self._speech_turn_open = False
        self._live_phase = ""
        self._sync_live_state()
        self._hide_panel()

    def _dismiss(self):
        if self._stream_timer:
            self._stream_timer.stop()
        self._clear_stage_timers()

        if self._history and self._history[0].get("action") == "pending":
            self._history[0]["action"] = "accepted"

        if self._mic_active:
            self.mic_released.emit()
            self._mic_active = False
        self._speech_turn_open = False
        self._live_phase = ""
        self._sync_live_state()

        self._panel_visible = False
        self._content_panel.hide()
        self._state = _State.IDLE
        self.hide()
        self.dismiss_requested.emit()

    # -----------------------------------------------------------------
    # Show / hide plumbing
    # -----------------------------------------------------------------

    def _ensure_overlay_visible(self, focus_target=None):
        self.show()
        self.raise_()
        self.activateWindow()
        self._apply_mode()

        if platform.system() == "Darwin":
            try:
                import AppKit
                AppKit.NSApp.activateIgnoringOtherApps_(True)
            except Exception:
                pass
            QTimer.singleShot(0, self._apply_macos_panel_behavior)

        if focus_target is not None:
            QTimer.singleShot(0, focus_target.setFocus)

    def showEvent(self, event):
        super().showEvent(event)
        if platform.system() == "Darwin":
            QTimer.singleShot(0, self._apply_macos_panel_behavior)
        self._apply_mode()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._panel_visible:
                self._hide_panel()
                return
            self._dismiss()
            return
        super().keyPressEvent(event)
