"""
ReVU — Overlay Style Tokens

Horizon-quality aesthetic: warm amber accents over dark glass with depth.
Three material tiers for visual hierarchy. Inter font with clear weight system.
"""

# ── Typography ────────────────────────────────────────────────────────────────

FONT_FAMILY = '"Helvetica Neue", Arial'
FONT_BODY = 12
FONT_SMALL = 11
FONT_TINY = 9
FONT_HEADLINE = 13


def load_fonts():
    """Placeholder — load bundled fonts if available in fonts/ directory."""
    pass


# ── Text Colors ───────────────────────────────────────────────────────────────

TEXT_PRIMARY = "#F8FAFC"
TEXT_SECONDARY = "rgba(248, 250, 252, 210)"
TEXT_MUTED = "rgba(248, 250, 252, 140)"
TEXT_SOFT = "rgba(248, 250, 252, 100)"

# ── Amber Accent System ──────────────────────────────────────────────────────

ACCENT_AMBER = "#FFCA94"               # primary warm — text highlights, orb
ACCENT_AMBER_STRONG = "#FF8000"        # borders, active states, banner accent
ACCENT_AMBER_GLOW = "rgba(255, 180, 80, 40)"   # orb halo
ACCENT_AMBER_SOFT = "rgba(255, 160, 60, 15)"   # banner bg
ACCENT_AMBER_BORDER = "rgba(255, 160, 60, 40)" # banner border
ACCENT_AMBER_TEXT = "rgba(255, 202, 148, 220)"  # banner text

# ── Cool Clinical Accents (kept for content) ─────────────────────────────────

ACCENT = "#D8E6FF"
ACCENT_STRONG = "#BFD7FF"

# ── Confidence / Status ───────────────────────────────────────────────────────

CONFIDENCE_HIGH = "#FF857A"
CONFIDENCE_MEDIUM = "#FFD870"
CONFIDENCE_LOW = "#8BE0B3"

CONFIDENCE_COLORS = {
    "high": CONFIDENCE_HIGH,
    "medium": CONFIDENCE_MEDIUM,
    "low": CONFIDENCE_LOW,
}

DANGER_COLOR = CONFIDENCE_HIGH
WARNING_COLOR = CONFIDENCE_MEDIUM
SUCCESS_COLOR = CONFIDENCE_LOW
MUTED_COLOR = TEXT_MUTED

# ── Glass Surface Tokens ─────────────────────────────────────────────────────

GLASS_EDGE = "rgba(255, 255, 255, 30)"
GLASS_INNER = "rgba(255, 255, 255, 6)"
GLASS_WIDGET = "transparent"
GLASS_WIDGET_BORDER = "transparent"

# Material tier presets (fill_rgba, border_alpha, shadow_alpha)
GLASS_TIER1 = {"fill_rgba": (12, 14, 18, 200), "border_alpha": 18, "shadow_alpha": 16}   # frosted — content panel
GLASS_TIER2 = {"fill_rgba": (16, 18, 24, 190), "border_alpha": 14, "shadow_alpha": 12}   # frosted — top bar
GLASS_TIER3 = {"fill_rgba": (255, 255, 255, 8), "border_alpha": 10, "shadow_alpha": 0}   # light — pill buttons

# ── Master Stylesheet ─────────────────────────────────────────────────────────

PANEL_STYLESHEET = f"""
    /* ── Base ──────────────────────────────────────────── */
    QWidget {{
        color: {TEXT_PRIMARY};
        background: transparent;
        font-family: {FONT_FAMILY};
        font-size: {FONT_BODY}px;
    }}
    QLabel {{
        color: {TEXT_PRIMARY};
        background: transparent;
    }}

    /* ── Status / Header ──────────────────────────────── */
    QLabel#status_text {{
        font-size: {FONT_SMALL}px;
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}
    QLabel#status_dot {{
        font-size: 10px;
        color: {SUCCESS_COLOR};
    }}
    QLabel#hotkey_badge {{
        color: {TEXT_MUTED};
        font-size: {FONT_TINY}px;
        font-weight: 600;
        background-color: rgba(255, 255, 255, 4);
        border: 1px solid rgba(255, 255, 255, 8);
        border-radius: 6px;
        padding: 2px 5px;
    }}

    /* ── Panel Content ────────────────────────────────── */
    QLabel#panel_icon {{
        color: {TEXT_MUTED};
        font-size: {FONT_TINY}px;
        font-weight: 700;
        background: transparent;
        padding: 0;
    }}
    QLabel#panel_title {{
        font-size: {FONT_HEADLINE}px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QLabel#panel_meta {{
        font-size: {FONT_SMALL}px;
        color: {TEXT_MUTED};
    }}
    QLabel#read_echo {{
        font-size: {FONT_SMALL}px;
        color: {TEXT_SECONDARY};
        background: transparent;
        padding: 2px 0;
    }}

    /* ── Cards ─────────────────────────────────────────── */
    QLabel#card_title {{
        font-size: {FONT_HEADLINE}px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QLabel#card_body {{
        font-size: {FONT_BODY}px;
        color: {TEXT_SECONDARY};
    }}

    /* ── Insight Stream ───────────────────────────────── */
    QLabel#insight_stream {{
        font-size: {FONT_HEADLINE}px;
        font-weight: 600;
        color: {TEXT_PRIMARY};
    }}
    QLabel#stream_detail {{
        font-size: {FONT_BODY}px;
        color: {TEXT_SECONDARY};
    }}
    QLabel#delta_text {{
        font-size: {FONT_BODY}px;
        font-weight: 500;
        color: {TEXT_PRIMARY};
    }}
    QLabel#reasoning_text {{
        font-size: {FONT_BODY}px;
        color: {TEXT_SECONDARY};
    }}

    /* ── Meta / Misc Labels ───────────────────────────── */
    QLabel#muted {{
        font-size: {FONT_SMALL}px;
        color: {TEXT_MUTED};
    }}
    QLabel#tiny_meta {{
        font-size: {FONT_TINY}px;
        color: {TEXT_SOFT};
    }}
    QLabel#list_item {{
        font-size: {FONT_BODY}px;
        color: {TEXT_SECONDARY};
    }}
    QLabel#section_heading {{
        font-size: {FONT_HEADLINE}px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QLabel#confidence_badge {{
        font-size: {FONT_TINY}px;
        font-weight: 600;
        color: {TEXT_MUTED};
        background: transparent;
        padding: 0;
    }}

    /* ── PR-Diff Labels (QA review view) ────────────── */
    QLabel#diff_removed {{
        font-size: {FONT_BODY}px;
        color: rgba(255, 130, 120, 220);
        background-color: rgba(255, 80, 60, 8);
        border-left: 3px solid rgba(255, 80, 60, 80);
        border-radius: 6px;
        padding: 8px 10px;
        font-family: "Menlo", "Courier New", monospace;
    }}
    QLabel#diff_added {{
        font-size: {FONT_BODY}px;
        color: rgba(130, 230, 160, 220);
        background-color: rgba(60, 200, 100, 8);
        border-left: 3px solid rgba(60, 200, 100, 80);
        border-radius: 6px;
        padding: 8px 10px;
        font-family: "Menlo", "Courier New", monospace;
    }}

    /* ── Shortcut Label (inside pill buttons) ─────────── */
    QLabel#shortcut_label {{
        font-size: {FONT_TINY}px;
        font-weight: 500;
        color: rgba(248, 250, 252, 50);
        background: transparent;
        padding: 0;
    }}

    /* ── Generic Buttons (unified frosted glass) ────── */
    QPushButton {{
        color: {TEXT_SECONDARY};
        background-color: rgba(255, 255, 255, 8);
        border: 1px solid rgba(255, 255, 255, 10);
        border-radius: 10px;
        padding: 5px 10px;
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 14);
        border: 1px solid rgba(255, 255, 255, 16);
        color: {TEXT_PRIMARY};
    }}

    /* ── Pill Buttons (Horizon-style top bar) ─────────── */
    QPushButton#pill_btn {{
        background-color: rgba(255, 255, 255, 10);
        border: 1px solid rgba(255, 255, 255, 14);
        border-radius: 14px;
        padding: 4px 10px;
        color: {TEXT_SECONDARY};
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}
    QPushButton#pill_btn:hover {{
        background-color: rgba(255, 255, 255, 16);
        border: 1px solid rgba(255, 255, 255, 20);
        color: {TEXT_PRIMARY};
    }}
    QPushButton#pill_btn_active {{
        background-color: rgba(255, 160, 60, 18);
        border: 1px solid rgba(255, 160, 60, 40);
        border-radius: 14px;
        padding: 4px 10px;
        color: {TEXT_PRIMARY};
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}
    QPushButton#pill_btn_active:hover {{
        background-color: rgba(255, 160, 60, 25);
        border: 1px solid rgba(255, 160, 60, 50);
    }}

    /* ── Orb Radial Ring Buttons ──────────────────────── */
    QPushButton#nav_ring_btn {{
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
        border-radius: 15px;
        padding: 0;
        background-color: rgba(255, 255, 255, 10);
        border: 1px solid rgba(255, 255, 255, 16);
        color: {TEXT_MUTED};
        font-size: 10px;
        font-weight: 700;
    }}
    QPushButton#nav_ring_btn:hover {{
        color: {TEXT_PRIMARY};
        background-color: rgba(255, 255, 255, 16);
        border: 1px solid rgba(255, 255, 255, 22);
    }}
    QPushButton#nav_ring_btn_active {{
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
        border-radius: 15px;
        padding: 0;
        background-color: rgba(255, 160, 60, 18);
        border: 1px solid rgba(255, 160, 60, 40);
        color: {TEXT_PRIMARY};
        font-size: 10px;
        font-weight: 700;
    }}

    /* ── Top Bar Buttons (legacy compat) ──────────────── */
    QPushButton#topbar_btn {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 4px 8px;
        color: {TEXT_MUTED};
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}
    QPushButton#topbar_btn:hover {{
        color: {TEXT_SECONDARY};
        background-color: rgba(255, 255, 255, 4);
    }}
    QPushButton#topbar_btn_active {{
        background-color: rgba(255, 255, 255, 6);
        border: 1px solid rgba(255, 255, 255, 8);
        border-radius: 8px;
        padding: 4px 8px;
        color: {TEXT_PRIMARY};
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}

    /* ── Panel Link / Action Buttons ──────────────────── */
    QPushButton#panel_link_btn {{
        background: transparent;
        border: none;
        padding: 2px 0;
        color: {TEXT_MUTED};
        text-align: left;
        font-size: {FONT_SMALL}px;
    }}
    QPushButton#panel_link_btn:hover {{
        color: {TEXT_PRIMARY};
    }}
    QPushButton#action_btn {{
        background-color: rgba(255, 255, 255, 3);
        border: 1px solid rgba(255, 255, 255, 6);
        border-radius: 10px;
        padding: 4px 10px;
        color: {TEXT_SECONDARY};
    }}
    QPushButton#action_active {{
        background-color: rgba(255, 255, 255, 6);
        border: 1px solid rgba(255, 255, 255, 10);
        border-radius: 10px;
        padding: 4px 10px;
        color: {TEXT_PRIMARY};
    }}
    QPushButton#icon_btn {{
        min-width: 24px;
        max-width: 32px;
        min-height: 24px;
        max-height: 32px;
        border-radius: 12px;
        padding: 0;
        font-size: {FONT_SMALL}px;
        background-color: rgba(255, 255, 255, 4);
        border: 1px solid rgba(255, 255, 255, 6);
    }}
    QPushButton#icon_btn:hover {{
        background-color: rgba(255, 255, 255, 10);
        border: 1px solid rgba(255, 255, 255, 12);
    }}
    QPushButton#primary_btn {{
        background-color: rgba(255, 255, 255, 6);
        border: 1px solid rgba(255, 255, 255, 10);
        color: {TEXT_PRIMARY};
    }}
    QPushButton#danger_btn {{
        background-color: rgba(255, 255, 255, 3);
        border: 1px solid rgba(255, 255, 255, 6);
        color: {TEXT_PRIMARY};
    }}

    /* ── Amber Banner ─────────────────────────────────── */
    QLabel#amber_banner {{
        background-color: {ACCENT_AMBER_SOFT};
        border: 1px solid {ACCENT_AMBER_BORDER};
        border-left: 3px solid {ACCENT_AMBER_STRONG};
        border-radius: 10px;
        padding: 6px 12px;
        color: {ACCENT_AMBER_TEXT};
        font-size: {FONT_SMALL}px;
        font-weight: 600;
    }}

    /* ── Toggle Pill (Notes / Transcription) ──────────── */
    QPushButton#toggle_pill {{
        background-color: rgba(255, 255, 255, 4);
        border: 1px solid rgba(255, 255, 255, 8);
        border-radius: 10px;
        padding: 3px 8px;
        color: {TEXT_MUTED};
        font-size: {FONT_TINY}px;
        font-weight: 600;
    }}
    QPushButton#toggle_pill:hover {{
        background-color: rgba(255, 255, 255, 8);
        color: {TEXT_SECONDARY};
    }}
    QPushButton#toggle_pill_active {{
        background-color: rgba(255, 255, 255, 8);
        border: 1px solid rgba(255, 255, 255, 14);
        border-radius: 10px;
        padding: 3px 8px;
        color: {TEXT_PRIMARY};
        font-size: {FONT_TINY}px;
        font-weight: 600;
    }}

    /* ── Separators ───────────────────────────────────── */
    QFrame#separator {{
        background-color: rgba(255, 255, 255, 4);
        min-height: 1px;
        max-height: 1px;
    }}
    QFrame#v_separator {{
        background-color: rgba(255, 255, 255, 4);
        min-width: 1px;
        max-width: 1px;
    }}

    /* ── Text Input (frosted glass, unified) ──────────── */
    QTextEdit, QLineEdit {{
        color: {TEXT_PRIMARY};
        background-color: rgba(255, 255, 255, 6);
        border: 1px solid rgba(255, 255, 255, 10);
        border-radius: 12px;
        padding: 8px 12px;
        font-size: {FONT_BODY}px;
        selection-background-color: rgba(255, 200, 148, 50);
        selection-color: {TEXT_PRIMARY};
    }}
    QTextEdit#doctor_input {{
        min-height: 46px;
        max-height: 56px;
    }}
    QTextEdit#transcript_box {{
        background-color: rgba(255, 255, 255, 4);
        border: 1px solid rgba(255, 255, 255, 8);
        border-radius: 12px;
        padding: 8px 12px;
    }}
    QLineEdit#transcript_input {{
        min-height: 34px;
    }}

    /* ── Ask Input (ChatGPT-style wide bar) ────────── */
    QLineEdit#ask_input {{
        background: transparent;
        border: none;
        padding: 4px 8px;
        font-size: {FONT_BODY}px;
        color: {TEXT_PRIMARY};
        min-height: 28px;
    }}
    QLineEdit#ask_input::placeholder {{
        color: {TEXT_MUTED};
    }}

    /* ── Send Button (circular, white bg) ──────────── */
    QPushButton#send_btn {{
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
        border-radius: 16px;
        background-color: rgba(255, 255, 255, 200);
        border: none;
        color: #0C0E12;
        font-size: 16px;
        font-weight: 700;
        padding: 0;
    }}
    QPushButton#send_btn:hover {{
        background-color: rgba(255, 255, 255, 240);
    }}
"""
