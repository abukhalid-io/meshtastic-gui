"""Meshtastic-inspired color palette + Qt stylesheet.

Colors follow the dark, mint-green look of the official Meshtastic web
client (client.meshtastic.org) — a near-black chrome with a bright green
accent for active/primary elements.
"""

BG = "#15171c"          # window background
PANEL = "#1b1e25"        # tab pages, group boxes
ELEVATED = "#242830"     # inputs, table headers, rows
BORDER = "#333844"
TEXT = "#e7e9ec"
TEXT_MUTED = "#93999e"
ACCENT = "#67ea94"       # Meshtastic green
ACCENT_HOVER = "#7ff2a8"
ACCENT_PRESSED = "#4fcf7d"
ACCENT_TEXT = "#0d1410"  # dark text on top of the green accent
DANGER = "#ff6b6b"
DANGER_HOVER = "#ff8686"


def stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {BG};
        color: {TEXT};
        font-size: 13px;
    }}

    QMainWindow {{
        background-color: {BG};
    }}

    QTabWidget::pane {{
        border: 1px solid {BORDER};
        background-color: {PANEL};
        border-radius: 6px;
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {TEXT_MUTED};
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}

    QTabBar::tab:selected {{
        color: {ACCENT};
        border-bottom: 2px solid {ACCENT};
    }}

    QTabBar::tab:hover:!selected {{
        color: {TEXT};
    }}

    QGroupBox {{
        border: 1px solid {BORDER};
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 12px;
        font-weight: 600;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {ACCENT};
    }}

    QPushButton {{
        background-color: {ELEVATED};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 6px 14px;
    }}

    QPushButton:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
    }}

    QPushButton:pressed {{
        background-color: {ACCENT_PRESSED};
        color: {ACCENT_TEXT};
    }}

    QPushButton:disabled {{
        color: {TEXT_MUTED};
        border-color: {BORDER};
    }}

    QPushButton#primary {{
        background-color: {ACCENT};
        color: {ACCENT_TEXT};
        border: none;
        font-weight: 600;
    }}

    QPushButton#primary:hover {{
        background-color: {ACCENT_HOVER};
    }}

    QPushButton#primary:pressed {{
        background-color: {ACCENT_PRESSED};
    }}

    QPushButton#danger {{
        color: {DANGER};
        border-color: {DANGER};
    }}

    QPushButton#danger:hover {{
        color: {DANGER_HOVER};
        border-color: {DANGER_HOVER};
    }}

    QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {{
        background-color: {ELEVATED};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_TEXT};
    }}

    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border-color: {ACCENT};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}

    QTableWidget {{
        background-color: {PANEL};
        alternate-background-color: {ELEVATED};
        gridline-color: {BORDER};
        border: 1px solid {BORDER};
        border-radius: 4px;
    }}

    QHeaderView::section {{
        background-color: {ELEVATED};
        color: {TEXT_MUTED};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px;
        font-weight: 600;
    }}

    QTableWidget::item:selected {{
        background-color: {ACCENT};
        color: {ACCENT_TEXT};
    }}

    QRadioButton, QLabel {{
        background: transparent;
    }}

    QRadioButton::indicator:checked {{
        background-color: {ACCENT};
        border: 2px solid {ACCENT};
        border-radius: 7px;
    }}

    QRadioButton::indicator:unchecked {{
        background-color: transparent;
        border: 2px solid {BORDER};
        border-radius: 7px;
    }}

    QStatusBar {{
        background-color: {PANEL};
        color: {TEXT_MUTED};
        border-top: 1px solid {BORDER};
    }}

    QScrollBar:vertical {{
        background: {PANEL};
        width: 10px;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 24px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}

    QMessageBox {{
        background-color: {PANEL};
    }}
    """
