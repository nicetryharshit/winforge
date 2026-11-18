"""Visual theme for WinForge: a dark palette for native widgets plus a stylesheet for the details.

Pure styling. No behaviour lives here.
"""

from PySide6.QtGui import QColor, QPalette

# Palette
BG = "#0b1020"          # window background
PANEL = "#131a2e"       # cards and panels
PANEL_2 = "#1a2340"     # inputs and hover
BORDER = "#263252"
TEXT = "#e6e9f2"
MUTED = "#8b93a7"
ACCENT = "#5b8cff"
ACCENT_HOVER = "#7aa2ff"
ACCENT_TEXT = "#0b1020"
WARN = "#f87171"
LOG_BG = "#070b16"

STYLE = f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QWidget {{ background: transparent; }}
QMainWindow, QWidget#root {{ background: {BG}; }}

QLabel#appname {{ font-size: 16pt; font-weight: 700; }}
QLabel#profile {{ color: {MUTED}; padding-right: 6px; }}
QLabel#title {{ font-size: 20pt; font-weight: 650; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 10.5pt; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#stage {{ font-weight: 600; color: {ACCENT}; }}
QLabel#banner {{
    background: rgba(248, 113, 113, 0.12); color: {WARN};
    border: 1px solid rgba(248, 113, 113, 0.45); border-radius: 10px; padding: 12px 14px;
}}

QGroupBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px;
    margin-top: 22px; padding: 18px 16px 16px 16px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 16px; padding: 0 4px; color: {MUTED}; background: {PANEL};
    font-size: 8.5pt; font-weight: 600;
}}

QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 9px; padding: 8px 10px;
    selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {MUTED}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT}; outline: none; padding: 4px;
}}
QHeaderView::section {{
    background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px; font-weight: 600;
}}
QTableWidget {{ gridline-color: {BORDER}; }}

QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 9px 16px; color: {TEXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {PANEL}; }}
QPushButton:disabled {{ color: {MUTED}; background: {PANEL}; border-color: {BORDER}; }}
QPushButton#primary {{
    background: {ACCENT}; color: {ACCENT_TEXT}; border: none; font-weight: 650; padding: 10px 20px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: {PANEL_2}; color: {MUTED}; }}
QPushButton#danger {{ color: {WARN}; }}
QPushButton#danger:hover {{ border-color: {WARN}; }}
QPushButton#flat {{ border: none; background: transparent; color: {MUTED}; padding: 8px 12px; }}
QPushButton#flat:hover {{ color: {TEXT}; background: {PANEL_2}; border-radius: 9px; }}

QListWidget#nav {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; padding: 10px;
}}
QListWidget#nav::item {{ padding: 11px 14px; border-radius: 9px; margin: 2px 0; color: {MUTED}; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: {ACCENT_TEXT}; font-weight: 650; }}
QListWidget#nav::item:hover:!selected {{ background: {PANEL_2}; color: {TEXT}; }}

QListWidget::item {{ padding: 6px 4px; }}
QListWidget#presets {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; padding: 6px; }}
QListWidget#presets::item {{ padding: 16px 14px; border-radius: 10px; margin: 4px; }}
QListWidget#presets::item:selected {{ background: {PANEL_2}; color: {TEXT}; }}
QListWidget#presets::item:hover:!selected {{ background: {PANEL_2}; }}

QFrame#presetCard {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px;
}}
QFrame#presetCard:hover {{ border: 1px solid {ACCENT}; }}
QLabel#cardTitle {{ font-size: 13pt; font-weight: 650; }}
QLabel#badge {{
    background: rgba(91, 140, 255, 0.16); color: {ACCENT}; border-radius: 9px; padding: 3px 10px; font-size: 8.5pt;
}}
QLabel#badgeUser {{
    background: rgba(52, 211, 153, 0.16); color: #34d399; border-radius: 9px; padding: 3px 10px; font-size: 8.5pt;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER}; border-radius: 14px; background: {PANEL}; top: -1px; padding: 14px;
}}
QTabBar::tab {{
    padding: 10px 18px; background: transparent; color: {MUTED};
    border: none; border-bottom: 2px solid transparent; margin-right: 4px;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; font-weight: 650; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid #3a4666; background: {PANEL_2};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4666; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

QPlainTextEdit#log {{
    background: {LOG_BG}; color: #cfd6e6; border: 1px solid {BORDER}; border-radius: 12px; padding: 14px;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt;
}}
QProgressBar {{ border: none; background: {PANEL_2}; border-radius: 3px; min-height: 6px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: {BG}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QMessageBox {{ background: {PANEL}; }}
"""


def apply_palette(app) -> None:
    """Dark palette so native widgets (dialogs, combo popups, checkboxes) match the stylesheet."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(PANEL_2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(PANEL_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    app.setPalette(pal)
