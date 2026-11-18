"""Visual theme for the WinForge window. Pure styling; no behaviour lives here."""

ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
TEXT = "#1f2937"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
PANEL = "#ffffff"
WINDOW = "#f3f4f6"

STYLE = f"""
* {{
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QWidget#root {{ background: {WINDOW}; }}
QLabel#appname {{ font-size: 15pt; font-weight: 700; }}
QLabel#profile {{ color: {MUTED}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#title {{ font-size: 18pt; font-weight: 600; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#stage {{ font-weight: 600; color: {ACCENT_DARK}; }}
QLabel#banner {{
    background: #fef2f2; color: #991b1b; border: 1px solid #fecaca;
    border-radius: 8px; padding: 10px 14px;
}}

QGroupBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
    margin-top: 18px; padding: 16px 14px 14px 14px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 14px; padding: 0 6px; color: #374151; background: {PANEL};
}}

QLineEdit, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {{
    background: {PANEL}; border: 1px solid #d1d5db; border-radius: 6px; padding: 6px 8px;
    selection-background-color: #dbeafe; selection-color: #1e3a8a;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}

QPushButton {{
    background: {PANEL}; border: 1px solid #d1d5db; border-radius: 6px; padding: 7px 14px;
}}
QPushButton:hover {{ background: #f9fafb; border-color: #9ca3af; }}
QPushButton:pressed {{ background: #f3f4f6; }}
QPushButton:disabled {{ color: #9ca3af; background: #f9fafb; border-color: {BORDER}; }}
QPushButton#primary {{
    background: {ACCENT}; color: #ffffff; border: 1px solid {ACCENT_DARK};
    font-weight: 600; padding: 8px 18px;
}}
QPushButton#primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#primary:disabled {{ background: #bfdbfe; border-color: #bfdbfe; color: #ffffff; }}
QPushButton#danger {{ color: #b91c1c; }}
QPushButton#flat {{ border: none; background: transparent; padding: 6px 10px; }}
QPushButton#flat:hover {{ background: {BORDER}; border-radius: 6px; }}

QListWidget#nav {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px;
}}
QListWidget#nav::item {{ padding: 10px 12px; border-radius: 6px; margin: 2px 0; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: #ffffff; }}
QListWidget#nav::item:hover:!selected {{ background: #eef2ff; }}
QListWidget::item {{ padding: 5px 4px; }}
QListWidget#presets::item {{ padding: 14px 12px; border-bottom: 1px solid {BORDER}; }}
QListWidget#presets::item:selected {{ background: #eff6ff; color: {TEXT}; }}

QTabWidget::pane {{
    border: 1px solid {BORDER}; border-radius: 10px; background: {PANEL}; top: -1px; padding: 10px;
}}
QTabBar::tab {{
    padding: 8px 16px; background: transparent; color: {MUTED};
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {ACCENT_DARK}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QPlainTextEdit#log {{
    background: #111827; color: #e5e7eb; border: none; border-radius: 10px; padding: 12px;
    font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt;
}}
QProgressBar {{ border: none; background: {BORDER}; border-radius: 3px; min-height: 6px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
"""
