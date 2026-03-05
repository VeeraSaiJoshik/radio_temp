"""
Radiology Copilot — UI Style Constants
"""

# ── Colors ───────────────────────────────────────────────────────────────────
BG_COLOR = "#1E1E2E"          # dark charcoal
BG_COLOR_RGB = (30, 30, 46)
TEXT_COLOR = "#CDD6F4"         # soft white-blue
ACCENT_COLOR = "#89B4FA"       # blue accent
SUCCESS_COLOR = "#A6E3A1"      # green
WARNING_COLOR = "#F9E2AF"      # yellow
DANGER_COLOR = "#F38BA8"       # red / urgent
MUTED_COLOR = "#6C7086"        # grey for secondary text
BORDER_COLOR = "#45475A"       # subtle border

# ── Confidence Colors ────────────────────────────────────────────────────────
CONFIDENCE_COLORS = {
    "high": DANGER_COLOR,      # high confidence finding = needs attention
    "medium": WARNING_COLOR,
    "low": SUCCESS_COLOR,
}

# ── Fonts ────────────────────────────────────────────────────────────────────
FONT_FAMILY = "Helvetica Neue, Arial, sans-serif"
FONT_SIZE_TITLE = 13
FONT_SIZE_BODY = 12
FONT_SIZE_SMALL = 10

# ── Stylesheet ───────────────────────────────────────────────────────────────
OVERLAY_STYLESHEET = f"""
    QWidget#overlay {{
        background-color: {BG_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 12px;
    }}
    QLabel {{
        color: {TEXT_COLOR};
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_BODY}px;
        background: transparent;
    }}
    QLabel#title {{
        font-size: {FONT_SIZE_TITLE}px;
        font-weight: bold;
        color: {ACCENT_COLOR};
    }}
    QLabel#confidence {{
        font-size: {FONT_SIZE_SMALL}px;
        font-weight: bold;
        padding: 2px 8px;
        border-radius: 4px;
    }}
    QLabel#muted {{
        color: {MUTED_COLOR};
        font-size: {FONT_SIZE_SMALL}px;
    }}
    QPushButton {{
        background-color: {BORDER_COLOR};
        color: {TEXT_COLOR};
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_SMALL}px;
    }}
    QPushButton:hover {{
        background-color: {ACCENT_COLOR};
        color: {BG_COLOR};
    }}
    QPushButton#danger {{
        background-color: {DANGER_COLOR};
        color: {BG_COLOR};
    }}
    QPushButton#danger:hover {{
        background-color: #EF6F92;
    }}
    QLineEdit {{
        background-color: #313244;
        color: {TEXT_COLOR};
        border: 1px solid {BORDER_COLOR};
        border-radius: 6px;
        padding: 5px 8px;
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_SMALL}px;
    }}
"""
