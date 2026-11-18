"""Visual theme for WinForge, modelled on a dense dark DAW layout: flat charcoal panels,
hairline separators, small uppercase section labels, one amber accent for selection and
the primary action. Pure styling. No behaviour lives here.
"""

from PySide6.QtGui import QColor, QPalette

# Palette
BG = "#181818"          # window and chrome (a step darker than before)
PANEL = "#1f1f1f"       # page and panel background
PANEL_2 = "#282828"     # inputs, buttons
SUNKEN = "#121212"      # log and list wells
LINE = "#2f2f2f"        # hairline separators
LINE_STRONG = "#414141"
TEXT = "#d4d4d4"
MUTED = "#7f7f7f"
DIM = "#555555"
ACCENT = "#ffb13b"      # amber: selection, focus, primary action
ACCENT_HOVER = "#ffc566"
ACCENT_TEXT = "#1c1c1c"
OK = "#9ccc65"
WARN = "#ff7a6b"

STYLE = f"""
* {{
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 8.5pt;
    color: {TEXT};
}}
QWidget {{ background: transparent; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#page {{ background: {PANEL}; }}

/* Top bar */
QFrame#topbar {{ background: {BG}; border-bottom: 1px solid {LINE}; }}
QLabel#brand {{ font-size: 10pt; font-weight: 700; color: {ACCENT}; }}
QLabel#profile {{ color: {MUTED}; }}
QLabel#profileName {{ font-weight: 600; }}
QLabel#dirty {{ color: {ACCENT}; font-weight: 600; }}

/* Section header strip at the top of each page */
QFrame#pageHeader {{ background: {BG}; border-bottom: 1px solid {LINE}; }}
QLabel#pageTitle {{ font-size: 11pt; font-weight: 600; }}
QLabel#pageHint {{ color: {MUTED}; }}

/* Section labels inside pages */
QLabel#section {{
    color: {MUTED}; font-size: 7.5pt; font-weight: 700;
    padding: 14px 0 6px 0; border-bottom: 1px solid {LINE}; margin-bottom: 4px;
}}
QLabel#help {{ color: {MUTED}; }}
QLabel#banner {{
    background: rgba(255, 122, 107, 0.10); color: {WARN};
    border: 1px solid {WARN}; border-radius: 2px; padding: 8px 10px;
}}
QLabel#stage {{ color: {ACCENT}; font-weight: 600; }}

/* Browser (left nav) */
QListWidget#nav {{ background: {SUNKEN}; border: none; border-right: 1px solid {LINE}; outline: none; padding: 6px 0; }}
QListWidget#nav::item {{ padding: 7px 14px; color: {MUTED}; border-left: 3px solid transparent; }}
QListWidget#nav::item:hover:!selected {{ color: {TEXT}; background: {PANEL_2}; }}
QListWidget#nav::item:selected {{ color: {TEXT}; background: {PANEL_2}; border-left: 3px solid {ACCENT}; font-weight: 600; }}

/* Inputs */
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{
    background: {SUNKEN}; border: 1px solid {LINE}; border-radius: 2px; padding: 5px 7px;
    selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {DIM}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {PANEL_2}; border: 1px solid {LINE_STRONG}; selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT}; outline: none;
}}

/* Lists and tables */
QListWidget#well, QTreeWidget#well, QTableWidget {{
    background: {SUNKEN}; border: 1px solid {LINE}; border-radius: 2px; outline: none;
    selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT}; gridline-color: {LINE};
}}
QListWidget#well::item {{ padding: 3px 6px; }}
QTreeWidget#well::item {{ padding: 4px 4px; border-bottom: 1px solid {PANEL}; }}
QTreeWidget#well::item:hover {{ background: {PANEL_2}; }}
QTreeWidget#well::item:selected {{ background: {PANEL_2}; color: {TEXT}; }}
QListWidget#well::item:hover {{ background: {PANEL_2}; }}
QHeaderView::section {{
    background: {PANEL_2}; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
    padding: 5px 8px; font-weight: 600;
}}

/* Buttons */
QPushButton {{
    background: {PANEL_2}; border: 1px solid {LINE_STRONG}; border-radius: 2px; padding: 5px 12px; color: {TEXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {SUNKEN}; }}
QPushButton:disabled {{ color: {DIM}; background: {PANEL}; border-color: {LINE}; }}
QPushButton#primary {{
    background: {ACCENT}; color: {ACCENT_TEXT}; border: 1px solid {ACCENT}; font-weight: 700; padding: 6px 18px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; color: {ACCENT_TEXT}; }}
QPushButton#primary:disabled {{ background: {PANEL_2}; color: {DIM}; border-color: {LINE}; }}
QPushButton#danger:hover {{ border-color: {WARN}; color: {WARN}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED}; padding: 5px 8px; }}
QPushButton#ghost:hover {{ color: {TEXT}; background: {PANEL_2}; }}
QPushButton#chip {{ border-radius: 2px; padding: 3px 9px; font-size: 8pt; color: {MUTED}; }}

/* Checkboxes, including the ones inside lists */
QTreeView::indicator, QListView::indicator {{
    width: 13px; height: 13px; border: 1px solid {LINE_STRONG}; background: {SUNKEN}; border-radius: 2px;
}}
QTreeView::indicator:hover, QListView::indicator:hover {{ border-color: {ACCENT}; }}
QTreeView::indicator:checked, QListView::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* Checkboxes */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 13px; height: 13px; border: 1px solid {LINE_STRONG}; background: {SUNKEN}; border-radius: 2px; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* Tabs */
QTabWidget::pane {{ border: none; border-top: 1px solid {LINE}; background: {PANEL}; top: -1px; }}
QTabBar::tab {{ padding: 6px 12px; background: transparent; color: {MUTED}; border: none; border-bottom: 2px solid transparent; font-size: 8pt; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

/* Preset browser cards */
QFrame#card {{ background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 2px; }}
QFrame#card:hover {{ border: 1px solid {ACCENT}; }}
QLabel#cardTitle {{ font-size: 10pt; font-weight: 600; }}
QLabel#tag {{ color: {MUTED}; font-size: 7.5pt; font-weight: 700; }}
QLabel#tagAccent {{ color: {ACCENT}; font-size: 7.5pt; font-weight: 700; }}

/* Log well */
QPlainTextEdit#log {{
    background: {SUNKEN}; color: #c4c4c4; border: 1px solid {LINE}; border-radius: 2px; padding: 8px;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 8.5pt;
}}

/* Panel header strip */
QLabel#panelHead {{
    background: {BG}; color: {MUTED}; border: 1px solid {LINE}; border-radius: 2px; padding: 8px 12px;
}}

/* Info view (bottom strip) */
QFrame#info {{ background: {BG}; border-top: 1px solid {LINE}; }}
QLabel#infoCap {{ color: {DIM}; font-size: 7pt; font-weight: 700; }}
QLabel#infoText {{ color: {MUTED}; }}

/* Status bar and scrollbars */
QStatusBar {{ background: {BG}; color: {MUTED}; border-top: 1px solid {LINE}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QProgressBar {{ border: none; background: {SUNKEN}; border-radius: 1px; min-height: 3px; max-height: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE_STRONG}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QSplitter::handle {{ background: {LINE}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {LINE_STRONG}; padding: 5px 7px; }}
QMessageBox {{ background: {PANEL}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
QFileDialog QTreeView, QFileDialog QListView {{
    background: {SUNKEN}; border: 1px solid {LINE}; selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
}}

/* Window controls on the top bar (the window has no Windows title bar) */
QPushButton#winctl, QPushButton#winclose {{
    background: transparent; border: none; border-radius: 0; padding: 0;
    min-width: 46px; min-height: 30px; color: {MUTED}; font-size: 10pt; font-weight: 400;
}}
QPushButton#winctl:hover {{ background: {PANEL_2}; color: {TEXT}; }}
QPushButton#winclose:hover {{ background: #c42b1c; color: #ffffff; }}
"""


def apply_palette(app) -> None:
    """Dark palette so native widgets (dialogs, combo popups, checkboxes) match the stylesheet."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(SUNKEN))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(PANEL_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL_2))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(DIM))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    app.setPalette(pal)
