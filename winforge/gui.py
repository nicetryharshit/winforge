"""WinForge editor (PySide6).

Layout follows a dense dark DAW: a top transport bar, a browser-style page list on the
left, one section per page with a title strip, and a status bar at the bottom.

The GUI edits a profile and runs the same `python -m winforge` commands you can type
yourself, so GUI builds and headless builds behave the same way. Real builds need an
Administrator session on Windows.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QProcess, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QListView, QProgressBar, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QAbstractItemView, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import catalog, presets
from .appsetup import describe_app
from .recipes import for_stage
from .ntlite import import_ntlite
from .profile import PHASES, ProfileError, default_profile, load_profile, normalise, save_profile
from .theme import ACCENT, DIM, MUTED, STYLE, apply_palette

TOP_H = 34          # title bar height
WIN_BTN_W = 46      # window control button width
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK = r"C:\WinForge\work"
DEFAULT_OUT = r"C:\WinForge\out\custom.iso"

INFO_DEFAULT = "Hover over anything to see what it does."

PAGES = ("Start", "Source", "Debloat", "Tweaks", "Files", "Account", "App",
         "Before setup finishes", "After setup, once", "First sign-in", "Every sign-in", "Every boot", "Build")

# Sidebar groups. Settings describe the PC; the stages are things that run on it, in the order Windows reaches them.
NAV = (
    ("SETTINGS", PAGES[0:7]),
    ("RUN ON THE PC", PAGES[7:12]),
    (None, PAGES[12:]),
)

PAGE_PHASE = {
    "Before setup finishes": "specialize",
    "After setup, once": "setupcomplete",
    "First sign-in": "firstlogon",
    "Every sign-in": "everylogon",
    "Every boot": "everyboot",
}

PAGE_TIP = {
    "Start": "Presets and saved profiles",
    "Source": "Pick the Windows ISO or folder, the edition, and output options",
    "Debloat": "Apps, optional features and services to remove or switch off",
    "Tweaks": "Registry changes, .reg files and custom registry entries",
    "Files": "Files and drivers added to the image while it is built",
    "Account": "The first account, sign-in, time zone and language",
    "App": "Copy your own program to the new PC and choose how it starts",
    "Before setup finishes": "Runs as SYSTEM right after Windows is copied to the PC, before setup screens",
    "After setup, once": "Runs once, as SYSTEM, after Windows setup finishes. Drivers and system changes go here",
    "First sign-in": "Runs once for each user, the first time that user signs in",
    "Every sign-in": "Runs every time a user signs in",
    "Every boot": "Runs every time Windows starts, before anyone signs in",
    "Build": "Preview the plan or build the ISO",
}

PHASE_TITLES = {
    "specialize": ("Before setup finishes",
                   "Runs as SYSTEM right after Windows is copied to the PC, before the setup screens. Rarely needed."),
    "setupcomplete": ("After setup, once",
                      "Runs once, as SYSTEM, after Windows setup finishes and before anyone signs in. Install drivers "
                      "here, remove services and make system-wide changes. WinForge writes SetupComplete.cmd for you."),
    "firstlogon": ("First sign-in",
                   "Runs once for each user, the first time that user signs in. Good for per-user settings."),
    "everylogon": ("Every sign-in",
                   "Runs every time a user signs in, as that user. WinForge creates a scheduled task for it."),
    "everyboot": ("Every boot",
                  "Runs every time Windows starts, before anyone signs in, as SYSTEM. WinForge creates a scheduled task for it."),
}

SNIPPETS = {
    "Insert a snippet…": "",
    "Silently install an EXE and wait": 'start /wait "" "C:\\Drivers\\setup.exe" /s',
    "Disable a service": "sc config <ServiceName> start= disabled",
    "Create a logon scheduled task": 'schtasks /create /tn "MyApp" /tr "C:\\Apps\\app.exe" /sc onlogon /rl highest /f',
    "Add a Wi-Fi profile from XML": 'netsh wlan add profile filename="C:\\Drivers\\WifiProfile.xml" user=all',
    "Set a registry value (HKLM)": 'reg add "HKLM\\SOFTWARE\\<Path>" /v <Name> /t REG_DWORD /d 1 /f',
    "Install with winget": "winget install --id <Publisher.App> -e --silent --accept-package-agreements --accept-source-agreements",
    "Run a PowerShell script file": 'powershell -NoProfile -ExecutionPolicy Bypass -File "C:\\Windows\\Setup\\Scripts\\myscript.ps1"',
    "Delete a folder": 'rd /s /q "C:\\<Path>"',
}

TIMEZONES = ["", "Central Standard Time", "Eastern Standard Time", "Pacific Standard Time",
             "India Standard Time", "GMT Standard Time", "W. Europe Standard Time",
             "Singapore Standard Time", "Tokyo Standard Time", "AUS Eastern Standard Time"]
LOCALES = ["en-US", "en-GB", "en-IN"]
INPUT_LOCALES = ["0409:00000409", "0809:00000809", "4009:00004009"]


# ------------------------------------------------------------------ small helpers

def _lines(edit: QPlainTextEdit) -> list[str]:
    return [ln.strip() for ln in edit.toPlainText().splitlines() if ln.strip()]


def _set_lines(edit: QPlainTextEdit, items) -> None:
    edit.setPlainText("\n".join(items))


def _button(text: str, fn, kind: str = "", tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(lambda _checked=False: fn())
    return b


def _chip(text: str, fn, tip: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("chip")
    b.setToolTip(tip)
    b.clicked.connect(lambda _checked=False: fn())
    return b


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section")
    return label


def _help(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("help")
    label.setWordWrap(True)
    label.setContentsMargins(0, 8, 0, 6)
    return label


def _panel_head(text: str) -> QLabel:
    """A header strip at the top of a panel: says what the panel is for."""
    label = QLabel(text)
    label.setObjectName("panelHead")
    label.setWordWrap(True)
    return label


def _row(form: QFormLayout, label: str, widget: QWidget, tip: str = "") -> None:
    caption = QLabel(label)
    caption.setObjectName("help")
    if tip:
        widget.setToolTip(tip)
        caption.setToolTip(tip)
    form.addRow(caption, widget)


def _wrap(*widgets, stretch: bool = True) -> QWidget:
    """Put widgets in a row, stretching the first one (or leaving them packed left when stretch is False)."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for i, w in enumerate(widgets):
        row.addWidget(w, 1 if i == 0 and stretch else 0)
    if not stretch:
        row.addStretch(1)
    return box


def _page(title: str, hint: str, scroll: bool) -> tuple[QWidget, QVBoxLayout]:
    """A page with a title strip. Form pages scroll; tabbed pages fill the window."""
    page = QWidget()
    page.setObjectName("page")
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    head = QFrame()
    head.setObjectName("pageHeader")
    hl = QVBoxLayout(head)
    hl.setContentsMargins(20, 14, 20, 12)
    hl.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    sub = QLabel(hint)
    sub.setObjectName("pageHint")
    sub.setWordWrap(True)
    hl.addWidget(heading)
    hl.addWidget(sub)
    outer.addWidget(head)

    if scroll:
        inner = QWidget()
        inner.setObjectName("page")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(20, 10, 20, 20)
        lay.setSpacing(8)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        outer.addWidget(area, 1)
    else:
        lay = QVBoxLayout()
        lay.setContentsMargins(20, 10, 20, 20)
        lay.setSpacing(8)
        outer.addLayout(lay, 1)
    return page, lay


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setHorizontalSpacing(18)
    form.setVerticalSpacing(10)
    return form


_NONATIVE = QFileDialog.Option(0)  # native Windows Explorer dialogs


def _qt_open_file(parent, title, directory="", flt=""):
    """Qt's own file dialog, so it matches the rest of the app (no Windows-style dialogs)."""
    return QFileDialog.getOpenFileName(parent, title, directory, flt, options=_NONATIVE)


def _qt_open_files(parent, title, directory="", flt=""):
    return QFileDialog.getOpenFileNames(parent, title, directory, flt, options=_NONATIVE)


def _qt_save_file(parent, title, directory="", flt=""):
    return QFileDialog.getSaveFileName(parent, title, directory, flt, options=_NONATIVE)


def _qt_dir(parent, title, directory=""):
    return QFileDialog.getExistingDirectory(parent, title, directory, options=_NONATIVE)


def _entry_key(r: dict) -> tuple:
    return (r["hive"], r["key"], r["name"], r["type"], str(r["data"]))


# ------------------------------------------------------------------- widgets

class DropDown(QComboBox):
    """A combo box that looks like a dropdown: a chevron on the right and a styled list that opens below it."""

    def __init__(self):
        super().__init__()
        self.setView(QListView())
        self.setMaxVisibleItems(12)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(DIM if not self.isEnabled() else ACCENT if self.hasFocus() else MUTED)
        x, y = self.width() - 15, self.height() / 2
        p.setPen(QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline(QPolygonF([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)]))


class BusyOverlay(QWidget):
    """Covers the pages while something is loading. It swallows every click, and tells the user why."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("busyOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.BusyCursor)
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame()
        card.setObjectName("busyCard")
        card.setFixedWidth(380)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("busyTitle")
        self.detail = QLabel()
        self.detail.setObjectName("help")
        self.detail.setWordWrap(True)
        self.note = QLabel("The window is locked until this finishes. Progress is shown at the bottom.")
        self.note.setWordWrap(True)
        self.note.setObjectName("help")
        self.cancel = QPushButton("Cancel")
        self.cancel.setToolTip("Stop this and unlock the window")
        cl.addWidget(self.title)
        cl.addWidget(self.detail)
        cl.addSpacing(4)
        cl.addWidget(self.note)
        cl.addWidget(self.cancel, 0, Qt.AlignmentFlag.AlignRight)
        outer.addWidget(card)
        self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(10, 10, 10, 170))

    def mousePressEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        event.accept()


class CheckList(QWidget):
    """A searchable checklist. Name is bright, the plain-English description is dim, and ★ marks recommended items."""

    def __init__(self, items):
        super().__init__()
        self._items = list(items)
        self._recommended = {it.id: it.recommended for it in items}

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name or description…")
        self.search.setToolTip("Type to filter the list. Matches the name, the description and the group.")
        self.search.textChanged.connect(self._filter)

        self.count = QLabel()
        self.count.setObjectName("help")
        self.count.setToolTip("How many items are ticked. Ticked items are applied to the image.")

        self.list = QTreeWidget()
        self.list.setObjectName("well")
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setColumnCount(3)
        self.list.setHeaderLabels(["", "Name", "What it does"])
        self.list.setColumnWidth(0, 54)
        self.list.setColumnWidth(1, 250)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for it in items:
            self._add_row(it)
        self.list.itemChanged.connect(lambda _item, _col: self._update_count())
        self.list.itemClicked.connect(self._clicked)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.count)
        bar.addWidget(_chip("Recommended", self.select_recommended,
                            "Tick only the items marked ★, the ones that are safe for most machines."))
        bar.addWidget(_chip("All", lambda: self.set_checked({it.id for it in self._items}),
                            "Tick every item in this list. Read the descriptions first."))
        bar.addWidget(_chip("None", lambda: self.set_checked(set()),
                            "Untick everything in this list."))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(bar)
        layout.addWidget(self.list, 1)
        self._update_count()

    def _add_row(self, it) -> None:
        row = QTreeWidgetItem(["★" if it.recommended else "", it.label, it.note])
        row.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        row.setCheckState(0, Qt.CheckState.Unchecked)
        row.setData(0, Qt.ItemDataRole.UserRole, it.id)
        if it.recommended:
            row.setForeground(0, QColor(ACCENT))
        row.setForeground(2, QColor(MUTED))
        tip = f"{it.label}: {it.note or 'No extra notes.'}"
        tip += f"\nGroup: {it.group}. Recommended: {'yes' if it.recommended else 'no'}. Internal name: {it.id}"
        for col in range(3):
            row.setToolTip(col, tip)
        self.list.addTopLevelItem(row)

    def add_items(self, items) -> int:
        """Add items that are not in the list yet (used by Scan image). Returns how many were added."""
        known = {it.id for it in self._items}
        added = 0
        for it in items:
            if it.id not in known:
                known.add(it.id)
                self._items.append(it)
                self._recommended[it.id] = it.recommended
                self._add_row(it)
                added += 1
        self._update_count()
        return added

    def _clicked(self, item, column) -> None:
        # Clicking the box toggles it already. Clicking anywhere else on the row toggles it too.
        if column != 0:
            on = item.checkState(0) == Qt.CheckState.Checked
            item.setCheckState(0, Qt.CheckState.Unchecked if on else Qt.CheckState.Checked)

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for i in range(self.list.topLevelItemCount()):
            row = self.list.topLevelItem(i)
            hay = (row.text(1) + " " + row.text(2) + " " + row.toolTip(1)).lower()
            row.setHidden(bool(t) and t not in hay)

    def _update_count(self) -> None:
        self.count.setText(f"{len(self.checked())} of {len(self._items)} ticked")

    def checked(self) -> list[str]:
        out = []
        for i in range(self.list.topLevelItemCount()):
            row = self.list.topLevelItem(i)
            if row.checkState(0) == Qt.CheckState.Checked:
                out.append(row.data(0, Qt.ItemDataRole.UserRole))
        return out

    def set_checked(self, ids: set) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.topLevelItemCount()):
            row = self.list.topLevelItem(i)
            on = row.data(0, Qt.ItemDataRole.UserRole) in ids
            row.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.list.blockSignals(False)
        self._update_count()

    def select_recommended(self) -> None:
        self.set_checked({k for k, rec in self._recommended.items() if rec})


class TitleBar(QFrame):
    """The top bar. It is also the drag handle, because the window has no Windows title bar."""

    def __init__(self, window: QMainWindow):
        super().__init__()
        self._window = window
        self.setObjectName("topbar")

    def mousePressEvent(self, event):
        handle = self._window.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class RowTable(QWidget):
    """An editable grid with add and remove buttons."""

    def __init__(self, headers: list[str], add_tip: str, remove_tip: str):
        super().__init__()
        self.table = QTableWidget(0, len(headers))
        self.table.setObjectName("well")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        add = _button("Add row", lambda: self.table.insertRow(self.table.rowCount()), tip=add_tip)
        remove = _button("Remove selected", self._remove, tip=remove_tip)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table, 1)
        layout.addLayout(buttons)

    def _remove(self) -> None:
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def rows(self) -> list[list[str]]:
        out = []
        for r in range(self.table.rowCount()):
            vals = [self.table.item(r, c).text().strip() if self.table.item(r, c) else ""
                    for c in range(self.table.columnCount())]
            if any(vals):
                out.append(vals)
        return out

    def set_rows(self, rows) -> None:
        self.table.setRowCount(0)
        for vals in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))


def _clean_folder(text: str) -> str | None:
    """Turn typed text into a folder path inside the image, or None if it is not allowed."""
    folder = text.strip().replace("/", "\\").strip("\\")
    parts = [p for p in folder.split("\\") if p]
    if ":" in folder or ".." in parts:
        return None
    return "\\".join(parts)


class FileTree(QTreeWidget):
    """Files and folders copied into the image. Each top-level row is a folder inside the image.

    Drag files or folders from Explorer onto a folder row. Drop on empty space and you will be asked for
    the folder. A folder row appears when it has at least one file, and disappears when its last file is removed.
    """

    def __init__(self, store_path, ask_folder):
        super().__init__()
        self._store = store_path   # turns an absolute path into the form saved in the profile
        self._ask = ask_folder     # asks which folder to use when nothing was picked
        self.setObjectName("well")
        self.setColumnCount(2)
        self.setHeaderLabels(["Folder inside the image", "Copied from"])
        self.setColumnWidth(0, 340)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setToolTip("Each file is copied to the folder on the left. Drag files in from Explorer, "
                        "or use the buttons below.")

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.topLevelItemCount() == 0:
            p = QPainter(self.viewport())
            p.setPen(QColor(DIM))
            p.drawText(self.viewport().rect().adjusted(0, 30, 0, 0), Qt.AlignmentFlag.AlignCenter,
                       "Drop files or folders here\nor use Add files… and Add folder…")
            p.end()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        folder = self._folder_at(event.position().toPoint())
        if folder is None:
            folder = self._ask()
        if folder is not None:
            for path in paths:
                self.add_path(folder, path)
        event.acceptProposedAction()

    def _folder_at(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        while item.parent() is not None:
            item = item.parent()
        return item.data(0, Qt.ItemDataRole.UserRole)

    def selected_folder(self):
        items = self.selectedItems()
        if not items:
            return None
        item = items[0]
        while item.parent() is not None:
            item = item.parent()
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _top(self, folder: str) -> QTreeWidgetItem:
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            if top.data(0, Qt.ItemDataRole.UserRole) == folder:
                return top
        top = QTreeWidgetItem([folder or "(image root)", ""])
        top.setData(0, Qt.ItemDataRole.UserRole, folder)
        top.setToolTip(0, f"Files here are copied to {folder}\\" if folder
                       else "Files here are copied to the root of the image")
        self.addTopLevelItem(top)
        top.setExpanded(True)
        return top

    def _add(self, folder: str, name: str, source: str) -> bool:
        top = self._top(folder)
        for j in range(top.childCount()):
            if top.child(j).text(0).lower() == name.lower():
                return False
        child = QTreeWidgetItem(top, [name, source])
        child.setToolTip(0, f"{folder}\\{name}" if folder else name)
        child.setToolTip(1, source)
        return True

    def add_path(self, folder: str, path: str) -> None:
        name = os.path.basename(os.path.normpath(path))
        if not self._add(folder, name, self._store(path)):
            QMessageBox.information(self, "Already added",
                                    f"'{name}' is already in {folder or 'the image root'}.")

    def set_entries(self, entries) -> None:
        self.clear()
        for e in entries:
            folder, _, name = e["to"].rpartition("\\")
            self._add(folder, name, e["from"])

    def entries(self) -> list[dict]:
        out = []
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            folder = top.data(0, Qt.ItemDataRole.UserRole)
            for j in range(top.childCount()):
                child = top.child(j)
                name = child.text(0)
                out.append({"from": child.text(1), "to": f"{folder}\\{name}" if folder else name})
        return out

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            parent = item.parent()
            if parent is None:
                self.takeTopLevelItem(self.indexOfTopLevelItem(item))
            else:
                parent.removeChild(item)
                if parent.childCount() == 0:
                    self.takeTopLevelItem(self.indexOfTopLevelItem(parent))


# -------------------------------------------------------------------- window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WinForge")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1200, 820)
        self._path: Path | None = None
        self._name = "custom"
        self._description = ""
        self._index: int | None = None
        self._loaded: dict = default_profile()
        self._baseline: str | None = None
        self._proc: QProcess | None = None
        self._partial = ""
        self._scan_proc = None
        self._scan = None
        self._ed_proc = None
        self._locked = False
        self._editions_source = None
        self._pstate: dict = {}
        self._last_kind = ""

        self.setStyleSheet(STYLE)
        self.setCentralWidget(self._build_shell())

        self.stack = QStackedWidget()
        self.step_checks: dict[str, list] = {}
        self._overlay_cancel = None
        self.scripts: dict[str, QPlainTextEdit] = {}
        builders = {
            "Start": self._page_start, "Source": self._page_source, "Debloat": self._page_debloat,
            "Tweaks": self._page_tweaks, "Files": self._page_files, "Account": self._page_account,
            "App": self._page_app, "Build": self._page_build,
        }
        for phase in PHASE_TITLES:
            page_name = next(n for n, ph in PAGE_PHASE.items() if ph == phase)
            builders[page_name] = (lambda ph=phase: self._page_stage(ph))
        for name in PAGES:
            self.stack.addWidget(builders[name]())
        self.nav.currentRowChanged.connect(self._on_page_changed)
        self.nav_body.addWidget(self.stack, 1)

        self.validity = QLabel()
        self.validity.setToolTip("Whether the current settings can be built. Fix the message before building.")
        self.statusBar().addPermanentWidget(self.validity)
        self.statusBar().showMessage("Ready")

        save_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        save_shortcut.activated.connect(self.save_current)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh)
        self._tick.start(400)

        QApplication.instance().installEventFilter(self)
        self.refresh_presets()
        self.load_ui(default_profile())
        self._baseline = self._snapshot(default_profile())
        self.go("Start")

    # ------------------------------------------------------------- shell

    def _build_shell(self) -> QWidget:
        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = TitleBar(self)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 0, 0, 0)
        tl.setSpacing(8)
        top.setFixedHeight(TOP_H)
        brand = QLabel("WINFORGE")
        brand.setObjectName("brand")
        brand.setToolTip("WinForge: build a customised Windows ISO")
        self.profile_name = QLabel()
        self.profile_name.setObjectName("profileName")
        self.profile_name.setToolTip("The profile you are editing and where it is saved")
        self.dirty = QLabel("● unsaved changes")
        self.dirty.setObjectName("dirty")
        self.dirty.setToolTip("You have changes that are not saved to the profile file yet. Ctrl+S saves them.")
        tl.addWidget(brand)
        tl.addSpacing(16)
        tl.addWidget(self.profile_name)
        tl.addWidget(self.dirty)
        self.busy_tag = QLabel("● working, the window is locked")
        self.busy_tag.setObjectName("dirty")
        self.busy_tag.setToolTip("WinForge is busy. Editing is switched off until it finishes.")
        self.busy_tag.hide()
        tl.addWidget(self.busy_tag)
        tl.addStretch()
        self._top_actions = [
            _button("Open…", self.open_profile, tip="Open a saved profile file (.json)"),
            _button("Save", self.save_current, tip="Save the profile to its file (Ctrl+S)"),
            _button("Save as…", self.save_as, tip="Save a copy of this profile to a new file"),
            _button("Build…", lambda: self.go("Build"), "primary",
                    tip="Open the build page to preview or build the ISO"),
        ]
        for b in self._top_actions:
            tl.addWidget(b)
        tl.addSpacing(10)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(0)
        for label, slot, name, tip in (("–", self.showMinimized, "winctl", "Minimise"),
                                       ("▢", self.toggle_maximize, "winctl", "Maximise or restore"),
                                       ("✕", self.close, "winclose", "Close WinForge")):
            b = _button(label, slot, name, tip)
            b.setFixedSize(WIN_BTN_W, TOP_H - 1)
            controls.addWidget(b)
        for b in self._top_actions:
            b.setFixedHeight(24)
        tl.addLayout(controls)
        tl.setAlignment(controls, Qt.AlignmentFlag.AlignTop)
        outer.addWidget(top)
        self._top = top
        self._root = root

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(176)
        self.nav.setToolTip("Pages, in the order you normally use them")
        for header, names in NAV:
            if header:
                h = QListWidgetItem(header)
                h.setFlags(Qt.ItemFlag.NoItemFlags)
                h.setForeground(QColor(DIM))
                self.nav.addItem(h)
            for name in names:
                item = QListWidgetItem("    " + name)
                item.setData(Qt.ItemDataRole.UserRole, name)
                item.setToolTip(PAGE_TIP[name])
                self.nav.addItem(item)
        self.nav_body = QVBoxLayout()
        self.nav_body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.nav)
        body.addLayout(self.nav_body, 1)
        outer.addLayout(body, 1)

        info = QFrame()
        info.setObjectName("info")
        info.setFixedHeight(64)
        self.info_height = 64
        il = QVBoxLayout(info)
        il.setContentsMargins(14, 8, 14, 8)
        il.setSpacing(3)
        cap = QLabel("INFO")
        cap.setObjectName("infoCap")
        self.info_text = QLabel(INFO_DEFAULT)
        self.info_text.setObjectName("infoText")
        self.info_text.setWordWrap(True)
        self.info_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        il.addWidget(cap)
        il.addWidget(self.info_text, 1)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(4)
        self.percent = QLabel("")
        self.percent.setObjectName("percent")
        self.percent.setFixedWidth(46)
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress_row = QFrame()
        self.progress_row.setObjectName("progressRow")
        self.progress_row.setFixedHeight(22)
        self.progress_row.setToolTip("Progress while WinForge reads, scans or builds. Shows a percentage when it "
                                     "can be measured, and a moving bar when it can't.")
        pl = QHBoxLayout(self.progress_row)
        pl.setContentsMargins(14, 0, 10, 0)
        pl.setSpacing(10)
        pl.addWidget(self.progress, 1, Qt.AlignmentFlag.AlignVCenter)
        pl.addWidget(self.percent)
        outer.addWidget(self.progress_row)
        outer.addWidget(info)
        self.overlay = BusyOverlay(root)
        return root

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()

    def _place_overlay(self) -> None:
        if getattr(self, "overlay", None) is not None:
            top = self._top.height()
            bottom = self.progress_row.height() + self.info_height
            self.overlay.setGeometry(0, top, self._root.width(), self._root.height() - top - bottom)

    def _lock(self, title: str, detail: str = "", cancel=None, overlay: bool = True) -> None:
        """Switch editing off while work runs, and show that it is off.

        overlay=True dims the pages behind a card (short jobs). overlay=False keeps the Build page usable so
        its log and Cancel button stay reachable, and locks everything else.
        """
        self._locked = True
        self.busy_tag.show()
        self.nav.setEnabled(False)
        for b in self._top_actions:
            b.setEnabled(False)
        for i in range(self.stack.count()):
            keep = (not overlay) and PAGES[i] == "Build"
            self.stack.widget(i).setEnabled(keep)
        if overlay:
            self.overlay.title.setText(title)
            self.overlay.detail.setText(detail)
            if self._overlay_cancel is not None:
                self.overlay.cancel.clicked.disconnect(self._overlay_cancel)
            self._overlay_cancel = cancel
            self.overlay.cancel.setVisible(cancel is not None)
            if cancel is not None:
                self.overlay.cancel.clicked.connect(cancel)
            self._place_overlay()
            self.overlay.show()
            self.overlay.raise_()
            self.overlay.setFocus()
        else:
            self.go("Build")

    def _unlock(self) -> None:
        self._locked = False
        self.busy_tag.hide()
        self.overlay.hide()
        self.nav.setEnabled(True)
        for b in self._top_actions:
            b.setEnabled(True)
        for i in range(self.stack.count()):
            self.stack.widget(i).setEnabled(True)

    def eventFilter(self, obj, event):
        """Live-style Info View: show the description of whatever is under the mouse."""
        kind = event.type()
        if isinstance(obj, QWidget) and obj.window() is self:
            tip = ""
            parent = obj.parent()
            if kind == QEvent.Type.MouseMove and isinstance(parent, QAbstractItemView):
                index = parent.indexAt(event.position().toPoint())
                tip = index.data(Qt.ItemDataRole.ToolTipRole) if index.isValid() else ""
            elif kind == QEvent.Type.Enter:
                tip = obj.toolTip()
            if tip:
                self.info_text.setText(str(tip).replace("\n\n", "  ").replace("\n", "  "))
        return False

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def go(self, name: str) -> None:
        for row in range(self.nav.count()):
            if self.nav.item(row).data(Qt.ItemDataRole.UserRole) == name:
                self.nav.setCurrentRow(row)
                return

    def _on_page_changed(self, row: int) -> None:
        name = self.nav.item(row).data(Qt.ItemDataRole.UserRole) if row >= 0 else None
        if name is None:
            return
        self.stack.setCurrentIndex(PAGES.index(name))
        if name == "Start":
            self.refresh_presets()

    # -------------------------------------------------------------- pages

    def _page_start(self) -> QWidget:
        page, lay = _page("Start",
                          "Pick a preset to begin, or open a profile you saved before. Presets are starting points. "
                          "Everything can be changed on the other pages.", scroll=False)
        lay.addWidget(_section("Presets"))
        holder = QWidget()
        self.preset_box = QVBoxLayout(holder)
        self.preset_box.setContentsMargins(0, 0, 0, 0)
        self.preset_box.setSpacing(6)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(holder)
        lay.addWidget(area, 1)

        lay.addWidget(_section("Profiles"))
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(_button("Open profile file…", self.open_profile,
                              tip="Open a profile you saved earlier (a .json file)"))
        row.addWidget(_button("New blank profile", self.new_profile,
                              tip="Start from nothing. Every option stays at its default."))
        row.addWidget(_button("Import NTLite preset…", self.import_ntlite,
                              tip="Turn an NTLite preset (.xml) into a WinForge profile. Anything that can't be carried "
                                  "over is listed afterwards."))
        row.addWidget(_button("Save current as preset…", self.save_as_preset,
                              tip="Save the settings you have now as a named preset you can reuse"))
        row.addStretch()
        lay.addLayout(row)
        return page

    def _page_source(self) -> QWidget:
        page, lay = _page("Source",
                          "The Windows ISO or extracted folder you start from. WinForge never edits your original. "
                          "It copies the source into the work folder and changes that copy.", scroll=True)
        form = _form()
        lay.addLayout(form)

        form.addRow(_section("Input"))
        self.source = QLineEdit()
        self.source.setPlaceholderText("Pick an ISO file or an extracted folder")
        self.source.editingFinished.connect(self._source_edited)
        _row(form, "Windows ISO or folder", _wrap(
            self.source,
            _button("ISO…", self._pick_iso, tip="Choose a Windows ISO file downloaded from Microsoft"),
            _button("Folder…", self._pick_folder, tip="Choose a folder that already contains the Windows files"),
        ), "The ISO or folder with sources\\install.wim or install.esd inside.")
        self.edition = DropDown()
        self.edition.setMinimumWidth(340)
        self.edition.setPlaceholderText("Choose a source first")
        self.edition.setToolTip("The Windows edition to keep. Every other edition is removed from the output ISO.")
        self.edition.activated.connect(lambda _i: setattr(self, "_index", None))
        _row(form, "Edition to keep", _wrap(self.edition, _button(
            "Reload list", self.read_editions, tip="Read the editions from the source again"), stretch=False),
             "Only this edition is kept in the output. Other editions are removed.")
        self.edition_hint = _help("The list fills in when you choose a source. Only the list is read at this stage, "
                                  "nothing is copied.")
        self.edition_hint.setWordWrap(False)
        form.addRow(QLabel(""), self.edition_hint)

        form.addRow(_section("Output"))
        self.work = QLineEdit(DEFAULT_WORK)
        self.work.setToolTip("Scratch folder for the copy and the mounted image. Needs plenty of free space.")
        _row(form, "Work folder", _wrap(
            self.work, _button("Browse…", lambda: self._pick_dir(self.work),
                               tip="Choose the scratch folder for the build")),
            "Scratch space for the build. Needs about 3 times the ISO size plus 10 GB free.")
        self.out = QLineEdit(DEFAULT_OUT)
        self.out.setToolTip("Where the finished ISO is written. An existing file here is replaced.")
        _row(form, "Output ISO", _wrap(
            self.out, _button("Browse…", self._pick_out, tip="Choose where to save the finished ISO")),
            "The finished ISO file. Any existing file with this name is replaced.")
        self.oscdimg = QLineEdit()
        self.oscdimg.setPlaceholderText("Leave blank to use the Windows ADK default")
        _row(form, "oscdimg.exe (advanced)", self.oscdimg,
             "The tool that writes the ISO. It comes with the Windows ADK, Deployment Tools.")

        form.addRow(_section("Image"))
        self.reset_base = QCheckBox("Shrink the component store (cannot uninstall updates later)")
        self.reset_base.setToolTip(
            "Runs DISM ResetBase. Makes the image smaller, but the installed updates can no longer be removed.")
        self.compress = QCheckBox("Maximum compression (slower build, smaller ISO)")
        self.compress.setToolTip(
            "Compresses the image as much as possible. Off uses fast compression, which builds sooner but gives a larger ISO.")
        form.addRow(QLabel(""), self.reset_base)
        form.addRow(QLabel(""), self.compress)
        lay.addWidget(_help("Only the edition you chose is kept in the image, whatever these options are."))
        lay.addStretch()
        return page

    def _page_debloat(self) -> QWidget:
        self.apps = CheckList(catalog.APPS)
        self.features = CheckList(catalog.FEATURES + catalog.CAPABILITIES)
        self.services = CheckList(catalog.SERVICES)
        self.tasks_remove = QPlainTextEdit()
        self.tasks_remove.setPlaceholderText("Microsoft\\Windows\\Maintenance\\WinSAT")
        self.tasks_remove.setToolTip("One scheduled task per line, as a path under Windows\\System32\\Tasks.")

        tabs = QTabWidget()
        tabs.addTab(self._tab(self.apps, "Apps built into Windows. Removing one only affects the image you build."),
                    "Apps")
        tabs.addTab(self._tab(self.features, "Optional Windows features and the capabilities they depend on. "
                                             "Removing a feature takes it out of the image."), "Features")
        tabs.addTab(self._tab(self.services, "Background services. Disabled services stay installed, "
                                             "but they will not start."), "Services")
        tabs.addTab(self._tab(self.tasks_remove,
                              "Scheduled tasks to delete from the image, one path per line. Only add a task "
                              "after you have checked its exact name on a real machine (Task Scheduler)."),
                    "Scheduled tasks")
        page, lay = _page("Debloat",
                          "Choose what to remove or switch off. ★ marks the choices that suit most machines. "
                          "Items missing from your edition are skipped, not treated as errors.", scroll=False)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(_button("Scan image…", self.scan_image,
                              tip="Read the Windows image chosen on the Source page and list the apps, features, "
                                  "services and scheduled tasks it really contains. Takes a few minutes. Needs Windows "
                                  "and administrator rights."))
        self.scan_label = QLabel("Not scanned yet. The lists show WinForge's built-in choices.")
        self.scan_label.setObjectName("help")
        bar.addWidget(self.scan_label, 1)
        bar.addWidget(_button("Pick scheduled tasks…", self.pick_tasks,
                              tip="Choose scheduled tasks from the last scan instead of typing their names."))
        lay.addLayout(bar)
        lay.addWidget(tabs, 1)
        return page

    def _page_tweaks(self) -> QWidget:
        self.tweaks = CheckList(catalog.TWEAKS)
        self.custom = RowTable(["Hive", "Key", "Name", "Type", "Data"],
                               add_tip="Add an empty registry entry row",
                               remove_tip="Delete the selected rows")
        self.reg_files = QPlainTextEdit()
        self.reg_files.setPlaceholderText("Paths to .reg files, one per line (relative to the profile, or absolute)")
        self.reg_files.setToolTip("Each file is read and applied to the image. Regedit exports work well.")

        tabs = QTabWidget()
        tabs.addTab(self._tab(self.tweaks, "Named tweaks. Each tick applies a set of registry values. "
                                           "Hover over a row for the full explanation."), "Tweaks")
        custom_page = QWidget()
        cl = QVBoxLayout(custom_page)
        cl.setContentsMargins(0, 10, 0, 0)
        cl.setSpacing(8)
        cl.addWidget(_panel_head("For registry values you know exactly. Hive is SOFTWARE, SYSTEM or DEFAULT "
                           "(DEFAULT is the new-user profile). Key is a path inside the hive. "
                           "Leave Name empty to set the key's default value."))
        cl.addWidget(self.custom, 1)
        tabs.addTab(custom_page, "Custom entries")

        files_page = QWidget()
        fl = QVBoxLayout(files_page)
        fl.setContentsMargins(0, 10, 0, 0)
        fl.setSpacing(8)
        fl.addWidget(_panel_head("Regedit exports (.reg). Their keys must be under HKEY_LOCAL_MACHINE\\SOFTWARE, "
                           "HKEY_LOCAL_MACHINE\\SYSTEM or HKEY_CURRENT_USER. Other keys and deletions are skipped "
                           "and listed as warnings in the build log."))
        fl.addWidget(self.reg_files, 1)
        fl.addWidget(_button("Add .reg file…", self._add_reg,
                             tip="Choose a .reg file to apply to the image"), 0)
        tabs.addTab(files_page, ".reg files")

        page, lay = _page("Tweaks",
                          "Registry changes applied to the image. Nothing changes until you build.", scroll=False)
        lay.addWidget(tabs, 1)
        return page

    def _page_files(self) -> QWidget:
        page, lay = _page("Files and drivers",
                          "Files and drivers that go into the image while it is built. Everything here lands at an exact "
                          "place on the PC. Things that run on the PC are on the stage pages under Run on the PC.",
                          scroll=False)
        tabs = QTabWidget()
        files = QWidget()
        fl = QVBoxLayout(files)
        fl.setContentsMargins(0, 10, 0, 0)
        fl.setSpacing(8)
        fl.addWidget(_panel_head("Files and folders copied into the image before setup runs. Each folder row is a folder "
                           "inside the image. Drag files from Explorer onto a folder, or use the buttons. "
                           "To make a new folder, add a file and type its name. Folders appear only when they hold files."))
        self.files_tree = FileTree(self._store_path, self._ask_folder)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(_button("Add files…", self._add_files,
                              tip="Choose files to copy. They go into the folder selected above, or you are asked for one."))
        bar.addWidget(_button("Add folder…", self._add_folder,
                              tip="Copy a whole folder, with everything in it, into the image."))
        bar.addWidget(_button("Remove selected", self.files_tree.remove_selected,
                              tip="Remove the selected files or folders from the list. Nothing on your disk is deleted."))
        bar.addStretch()
        fl.addLayout(bar)
        fl.addWidget(self.files_tree, 1)
        fl.addWidget(_help("Paths start at the system drive (C:). Windows\\Setup\\Scripts is where SetupComplete.cmd "
                           "lives. WinForge doesn't use $OEM$ folders. Every file here has one exact destination, "
                           "so nothing has to be placed by hand."))
        tabs.addTab(files, "Files")

        drivers = QWidget()
        dl = QVBoxLayout(drivers)
        dl.setContentsMargins(0, 10, 0, 0)
        dl.setSpacing(8)
        dl.addWidget(_panel_head("Drivers: folders that contain .inf files. They are added recursively. "
                           "Updates: .msu or .cab packages installed into the image."))
        self.drivers = QPlainTextEdit()
        self.drivers.setToolTip("One driver folder per line.")
        dl.addWidget(_button("Add driver folder…", self._add_driver, tip="Choose a folder of drivers to add"), 0)
        dl.addWidget(self.drivers, 1)
        self.updates = QPlainTextEdit()
        self.updates.setToolTip("One update package per line.")
        dl.addWidget(_button("Add update package…", self._add_update,
                             tip="Choose a .msu or .cab update package to add"), 0)
        dl.addWidget(self.updates, 1)
        tabs.addTab(drivers, "Drivers && updates")

        lay.addWidget(tabs, 1)
        return page

    def _page_stage(self, phase: str) -> QWidget:
        title, help_text = PHASE_TITLES[phase]
        page, lay = _page(title, help_text, scroll=True)
        if phase == "setupcomplete":
            lay.addWidget(_section("Drivers and installers"))
            lay.addWidget(_help("Installed on the new PC during this stage. Driver folders are copied to C:\\Drivers "
                                "and installed with pnputil. Installers run silently; add switches after the | bar."))
            self.drivers_boot = QPlainTextEdit()
            self.drivers_boot.setToolTip("One driver folder per line. Installed on the new PC with pnputil.")
            self.drivers_boot.setMaximumHeight(90)
            lay.addWidget(_button("Add driver folder…", self._add_driver_boot,
                                  tip="Choose a folder of .inf drivers to install on the new PC"), 0)
            lay.addWidget(self.drivers_boot)
            self.installers = QPlainTextEdit()
            self.installers.setToolTip("One installer per line. Add silent switches after a | bar, for example nvidia.exe|/s /quiet")
            self.installers.setMaximumHeight(90)
            lay.addWidget(_button("Add installer…", self._add_installer,
                                  tip="Choose an .exe or .msi to run silently on the new PC"), 0)
            lay.addWidget(self.installers)

        lay.addWidget(_section("Ready-made steps"))
        recipes = for_stage(phase)
        self.step_checks[phase] = []
        if not recipes:
            lay.addWidget(_help("No ready-made steps for this stage yet. Use the commands box below."))
        for recipe in recipes:
            box = QCheckBox(recipe.title)
            box.setToolTip(recipe.note)
            lay.addWidget(box)
            lay.addWidget(_help(recipe.note))
            self.step_checks[phase].append((recipe.id, box))

        lay.addWidget(_section("Your commands"))
        row = QHBoxLayout()
        row.setSpacing(6)
        combo = DropDown()
        combo.addItems(list(SNIPPETS))
        combo.setToolTip("Insert a ready-made command at the cursor. Replace the <angle brackets> with real values.")
        row.addWidget(combo, 1)
        row.addWidget(_button("Add my own script…", lambda: self._add_stage_script(phase),
                              tip="Pick a .ps1, .cmd or .exe file. It is copied into Windows\\Setup\\Scripts and runs in this stage."))
        lay.addLayout(row)
        editor = QPlainTextEdit()
        editor.setMinimumHeight(160)
        editor.setToolTip("One command per line. Commands run in order, after the ready-made steps above.")
        self.scripts[phase] = editor
        combo.activated.connect(lambda i, e=editor, c=combo: self._insert_snippet(e, c, i))
        lay.addWidget(editor, 1)
        return page

    def _add_stage_script(self, phase: str) -> None:
        path, _ = _qt_open_file(self, "Choose a script", "", "Scripts (*.ps1 *.cmd *.bat *.exe)")
        if not path:
            return
        name = os.path.basename(path)
        entries = self.files_tree.entries()
        entries.append({"from": self._store_path(path), "to": f"Windows\\Setup\\Scripts\\{name}"})
        self.files_tree.set_entries(entries)
        where = f"%WINDIR%\\Setup\\Scripts\\{name}"
        lower = name.lower()
        if lower.endswith(".ps1"):
            line = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{where}"'
        elif lower.endswith((".cmd", ".bat")):
            line = f'call "{where}"'
        else:
            line = f'start /wait "" "{where}"'
        self.scripts[phase].appendPlainText(line)
        self._refresh()

    def _page_app(self) -> QWidget:
        page, lay = _page("App",
                          "Your own program, for example a kiosk app. WinForge copies its folder to the new PC and "
                          "starts it for you. This replaces the hand-written copy, permission and scheduled-task steps.",
                          scroll=True)
        form = _form()
        lay.addLayout(form)
        self.app_on = QCheckBox("Install an app on the new PC")
        self.app_on.setToolTip("Turn this on to copy a program into the image and have it start automatically.")
        form.addRow(QLabel(""), self.app_on)
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("for example AVReelsKiosk")
        _row(form, "Folder name on the PC", self.app_name,
             "The app lands in C:\\<this name>. Letters, digits, dot, underscore and dash only.")
        self.app_folder = QLineEdit()
        browse_folder = _button("Browse…", self._pick_app_folder, tip="Choose the folder that holds your app")
        row = QHBoxLayout()
        row.addWidget(self.app_folder, 1)
        row.addWidget(browse_folder)
        form.addRow(self._caption("App folder", "The folder on this computer with your app and everything it needs."), row)
        self.app_exe = QLineEdit()
        self.app_exe.setPlaceholderText("for example AVReelsKiosk.exe")
        _row(form, "Program to start", self.app_exe,
             "The .exe inside the app folder, relative to it. Choosing a folder fills this in when it finds one .exe.")
        self.app_mode = DropDown()
        self.app_mode.addItem("Scheduled task at sign-in (runs elevated)", "task")
        self.app_mode.addItem("Run entry at sign-in", "run")
        self.app_mode.addItem("Replace the Windows desktop (shell)", "shell")
        _row(form, "How it starts", self.app_mode,
             "Scheduled task: starts at every sign-in with full rights. Run entry: simple start at sign-in. "
             "Shell: your app becomes the desktop, so there is no taskbar or Start menu.")
        self.app_grant = QCheckBox("Let every user write to the app folder")
        self.app_grant.setToolTip("Gives Everyone full control of the folder so the app can save settings and logs.")
        self.app_now = QCheckBox("Also start it as soon as setup finishes")
        self.app_now.setToolTip("Launches the app at the end of first-boot setup, before anyone signs in again.")
        form.addRow(QLabel(""), self.app_grant)
        form.addRow(QLabel(""), self.app_now)
        self.app_summary = _help("")
        lay.addWidget(self.app_summary)
        lay.addStretch()
        self.app_mode.currentIndexChanged.connect(self._update_app_summary)
        self.app_name.textChanged.connect(self._update_app_summary)
        return page

    @staticmethod
    def _caption(text: str, tip: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("help")
        label.setToolTip(tip)
        return label

    def _pick_app_folder(self) -> None:
        path = _qt_dir(self, "Choose the app folder")
        if not path:
            return
        self.app_folder.setText(self._store_path(path))
        if not self.app_name.text().strip():
            self.app_name.setText(re.sub(r"[^A-Za-z0-9._-]", "", os.path.basename(path)))
        exes = [f for f in os.listdir(path) if f.lower().endswith(".exe")]
        if len(exes) == 1 and not self.app_exe.text().strip():
            self.app_exe.setText(exes[0])

    def _update_app_summary(self) -> None:
        mode = self.app_mode.currentData()
        self.app_summary.setText(describe_app({"name": self.app_name.text().strip() or "<name>", "mode": mode}))

    def _page_account(self) -> QWidget:
        page, lay = _page("Account",
                          "The account the new machine signs in to, sign-in behaviour, and region. "
                          "These go into autounattend.xml.", scroll=True)
        form = _form()
        lay.addLayout(form)

        form.addRow(_section("Account"))
        self.acct_name = QLineEdit()
        self.acct_name.setToolTip("The account name Windows creates. Use Administrator with the built-in option below.")
        self.acct_display = QLineEdit()
        self.acct_display.setToolTip("The name shown on the sign-in screen. Leave blank to use the account name.")
        self.acct_pw = QLineEdit()
        self.acct_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.acct_pw.setToolTip("Leave blank for no password. The password is saved in the profile in plain text.")
        self.enable_builtin = QCheckBox("Use the built-in Administrator account")
        self.enable_builtin.setToolTip(
            "Turns on the built-in Administrator during setup and sets its full name. "
            "Set the account name to Administrator when you use this.")
        _row(form, "Account name", self.acct_name)
        _row(form, "Display name", self.acct_display)
        _row(form, "Password", self.acct_pw)
        form.addRow(QLabel(""), self.enable_builtin)

        form.addRow(_section("Sign-in"))
        self.autologon = QCheckBox("Sign in automatically")
        self.autologon.setToolTip("Signs the account in without asking for a password at boot.")
        self.skip_oobe = QCheckBox("Skip the out-of-box setup screens")
        self.skip_oobe.setToolTip("Skips the privacy, sign-in and welcome screens so the machine goes straight to the desktop.")
        form.addRow(QLabel(""), self.autologon)
        form.addRow(QLabel(""), self.skip_oobe)

        form.addRow(_section("Region"))
        self.timezone = DropDown()
        self.timezone.setEditable(True)
        self.timezone.addItems(TIMEZONES)
        _row(form, "Time zone", self.timezone,
             "Windows time zone ID, for example India Standard Time. Blank keeps Windows' default.")
        self.locale = DropDown()
        self.locale.setEditable(True)
        self.locale.addItems(LOCALES)
        _row(form, "Language and format", self.locale,
             "Language and date/number format for the system and the first account (e.g. en-US).")
        self.input_locale = DropDown()
        self.input_locale.setEditable(True)
        self.input_locale.addItems(INPUT_LOCALES)
        _row(form, "Keyboard layout", self.input_locale,
             "Keyboard layout ID. 0409:00000409 is US English, 0809:00000809 is UK, 4009:00004009 is English (India).")
        self.geo_id = QLineEdit()
        self.geo_id.setPlaceholderText("blank = leave unchanged, 244 = United States, 113 = India")
        _row(form, "Home location ID", self.geo_id,
             "Windows GeoID for the home location. Applied on first sign-in. Blank leaves it unchanged.")
        form.addRow(QLabel(""), _help("The password is saved in the profile in plain text. Keep profile files private."))
        return page

    def _page_build(self) -> QWidget:
        page, lay = _page("Build",
                          "Preview runs the plan without changing anything. Build copies the source, applies every "
                          "change, and writes the ISO. Real builds need an Administrator PowerShell on Windows.",
                          scroll=False)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setToolTip("What this profile will do")
        self.problems = QLabel()
        self.problems.setObjectName("banner")
        self.problems.setWordWrap(True)
        self.problems.setVisible(False)
        lay.addWidget(self.summary)
        lay.addWidget(self.problems)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_preview = _button("Preview (dry run)", lambda: self._run_build(dry=True),
                                   tip="Print every step without changing anything. Safe on any machine.")
        self.btn_build = _button("Build ISO", lambda: self._run_build(dry=False), "primary",
                                 tip="Apply every change and write the ISO. Takes a long time.")
        self.btn_cancel = _button("Cancel", self._cancel,
                                  tip="Stop the build. Use Clean up leftovers before the next build.")
        self.btn_cleanup = _button("Clean up leftovers", self._run_cleanup,
                                   tip="Unmount an image left behind by a cancelled or crashed build")
        self.btn_open = _button("Open output folder", self._open_output,
                                tip="Open the folder that contains the finished ISO")
        self.btn_cancel.setEnabled(False)
        self.btn_open.setEnabled(False)
        for b in (self.btn_preview, self.btn_build, self.btn_cancel, self.btn_cleanup, self.btn_open):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        self.stage = QLabel("Idle")
        self.stage.setObjectName("stage")
        lay.addWidget(self.stage)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setToolTip("Output from the build. The first ERROR line says what went wrong.")
        lay.addWidget(self.log, 1)
        return page

    def _tab(self, widget: QWidget, note: str) -> QWidget:
        tab = QWidget()
        tl = QVBoxLayout(tab)
        tl.setContentsMargins(0, 10, 0, 0)
        tl.setSpacing(8)
        tl.addWidget(_panel_head(note))
        tl.addWidget(widget, 1)
        return tab

    # ----------------------------------------------------------- UI <-> data

    def load_ui(self, p: dict) -> None:
        self._loaded = p
        self._name = p["name"]
        self._description = p.get("description", "")
        self._index = p["index"]
        self._set_edition(p["edition"] or "")
        self.reset_base.setChecked(p["options"]["reset_base"])
        self.compress.setChecked(p["options"]["compress"])
        self.oscdimg.setText(p["options"]["oscdimg"])

        acct = p["account"]
        self.acct_name.setText(acct["name"])
        self.acct_display.setText(acct.get("display_name", ""))
        self.acct_pw.setText(acct["password"])
        self.enable_builtin.setChecked(acct.get("enable_builtin_admin", False))
        self.autologon.setChecked(acct["autologon"])
        self.skip_oobe.setChecked(acct["skip_oobe"])

        region = p["region"]
        self.timezone.setCurrentText(region["timezone"])
        self.locale.setCurrentText(region["locale"])
        self.input_locale.setCurrentText(region["input"])
        self.geo_id.setText("" if region["geo_id"] is None else str(region["geo_id"]))
        app = p["app"]
        self.app_on.setChecked(app["enabled"])
        self.app_name.setText(app["name"])
        self.app_folder.setText(app["folder"])
        self.app_exe.setText(app["exe"])
        self.app_mode.setCurrentIndex(max(0, self.app_mode.findData(app["mode"])))
        self.app_grant.setChecked(app["grant_write"])
        self.app_now.setChecked(app["launch_now"])
        self._update_app_summary()
        _set_lines(self.drivers_boot, p["drivers_boot"])
        _set_lines(self.installers, [i["file"] + ("|" + i["args"] if i["args"] else "") for i in p["installers"]])

        self.apps.set_checked(set(p["remove"]["appx"]))
        self.features.set_checked(set(p["remove"]["features"]) | set(p["remove"]["capabilities"]))
        self.services.set_checked(set(p["services_disable"]))
        _set_lines(self.tasks_remove, p["tasks_remove"])

        present = {_entry_key(r) for r in p["registry"]}
        self.tweaks.set_checked({
            t.id for t in catalog.TWEAKS
            if all(_entry_key(dict(e)) in present for e in t.entries)
        })
        catalog_keys = {_entry_key(dict(e)) for t in catalog.TWEAKS for e in t.entries}
        self.custom.set_rows([[r["hive"], r["key"], r["name"], r["type"], r["data"]]
                              for r in p["registry"] if _entry_key(r) not in catalog_keys])
        _set_lines(self.reg_files, p["reg_files"])

        self.files_tree.set_entries(p["files"])
        _set_lines(self.drivers, p["drivers"])
        _set_lines(self.updates, p["updates"])
        for phase, editor in self.scripts.items():
            editor.setPlainText("\n".join(p["scripts"][phase]))
        for phase, boxes in self.step_checks.items():
            saved = {s["recipe"]: bool(s["enabled"]) for s in p["steps"].get(phase, [])}
            for recipe_id, box in boxes:
                box.setChecked(saved.get(recipe_id, False))
        self._update_profile_label()
        self._refresh()

    def collect(self) -> dict:
        cap_ids = {i.id for i in catalog.CAPABILITIES}
        feats = self.features.checked()
        tweak_map = {t.id: t for t in catalog.TWEAKS}
        registry: list[dict] = []
        seen: set = set()

        def add(entry: dict) -> None:
            key = _entry_key(entry)
            if key not in seen:
                seen.add(key)
                registry.append(entry)

        for tid in self.tweaks.checked():
            for e in tweak_map[tid].entries:
                add(dict(e))
        for hive, key, name, reg_type, data in self.custom.rows():
            add({"hive": hive, "key": key, "name": name, "type": reg_type, "data": data})

        raw = {
            "schema": 1,
            "name": self._name or "custom",
            "description": self._description,
            "edition": self.edition.currentText().strip() if self.edition.currentIndex() >= 0 else "",
            "index": self._index,
            "options": {
                "reset_base": self.reset_base.isChecked(),
                "compress": self.compress.isChecked(),
                "oscdimg": self.oscdimg.text().strip(),
            },
            "remove": {
                "appx": self.apps.checked(),
                "features": [f for f in feats if f not in cap_ids],
                "capabilities": [f for f in feats if f in cap_ids],
            },
            "drivers": _lines(self.drivers),
            "updates": _lines(self.updates),
            "registry": registry,
            "reg_files": _lines(self.reg_files),
            "services_disable": self.services.checked(),
            "tasks_remove": _lines(self.tasks_remove),
            "files": self.files_tree.entries(),
            "scripts": {phase: _lines(editor) for phase, editor in self.scripts.items()},
            "steps": {phase: [{"recipe": rid, "enabled": box.isChecked()} for rid, box in boxes]
                      for phase, boxes in self.step_checks.items()},
            "region": {
                "timezone": self.timezone.currentText().strip(),
                "locale": self.locale.currentText().strip() or "en-US",
                "input": self.input_locale.currentText().strip() or "0409:00000409",
                "geo_id": self._geo(),
            },
            "app": {
                "enabled": self.app_on.isChecked(),
                "name": self.app_name.text().strip(),
                "folder": self.app_folder.text().strip(),
                "exe": self.app_exe.text().strip(),
                "mode": self.app_mode.currentData(),
                "grant_write": self.app_grant.isChecked(),
                "launch_now": self.app_now.isChecked(),
            },
            "drivers_boot": _lines(self.drivers_boot),
            "installers": [{"file": a.strip(), "args": b.strip()} for a, _, b in
                           (line.partition("|") for line in _lines(self.installers))],
            "account": {
                "name": self.acct_name.text().strip(),
                "display_name": self.acct_display.text().strip(),
                "password": self.acct_pw.text(),
                "autologon": self.autologon.isChecked(),
                "skip_oobe": self.skip_oobe.isChecked(),
                "enable_builtin_admin": self.enable_builtin.isChecked(),
            },
        }
        return normalise(raw)

    def _geo(self):
        text = self.geo_id.text().strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return -1

    @staticmethod
    def _snapshot(p: dict) -> str:
        return json.dumps(p, sort_keys=True)

    def _refresh(self) -> None:
        """Re-check the profile, and update the summary, the banner, the status bar and the dirty marker."""
        try:
            p = self.collect()
        except ProfileError as exc:
            self.problems.setText(f"Fix this before building: {exc}")
            self.problems.setVisible(True)
            self.summary.setText("")
            self._set_build_enabled(False)
            self.validity.setText(f"Problem: {exc}")
            self.dirty.setVisible(self._snapshot_dirty())
            return
        self.problems.setVisible(False)
        self.problems.setText("")
        self.summary.setText(
            f"<b>{p['name']}</b> · {p['edition'] or 'index ' + str(p['index'])}<br>"
            f"Remove {len(p['remove']['appx'])} apps, {len(p['remove']['features'])} features and "
            f"{len(p['remove']['capabilities'])} capabilities. Disable {len(p['services_disable'])} services. "
            f"Delete {len(p['tasks_remove'])} scheduled tasks.<br>"
            f"{len(p['registry'])} registry edits · {len(p['reg_files'])} .reg files · {len(p['files'])} files · "
            f"{len(p['drivers'])} driver folders · {len(p['updates'])} update packages · "
            f"{sum(len(v) for v in p['scripts'].values())} script lines<br>"
            f"Account: {p['account']['name']}"
            f"{' (built-in Administrator)' if p['account']['enable_builtin_admin'] else ''}"
            f"{' · signs in automatically' if p['account']['autologon'] else ''}<br>"
            f"Time zone: {p['region']['timezone'] or 'Windows default'} · "
            f"Language: {p['region']['locale']}"
        )
        self._set_build_enabled(self._proc is None)
        self.validity.setText("Profile is valid")
        self.dirty.setVisible(self._snapshot_dirty())

    def _snapshot_dirty(self) -> bool:
        try:
            current = self._snapshot(self.collect())
        except ProfileError:
            return True
        # No baseline means the profile has never been saved (for example, a preset that was just loaded).
        return self._baseline is None or current != self._baseline

    def _set_build_enabled(self, on: bool) -> None:
        self.btn_preview.setEnabled(on)
        self.btn_build.setEnabled(on)

    def _update_profile_label(self) -> None:
        where = str(self._path) if self._path else "not saved yet"
        self.profile_name.setText(f"{self._name}")
        self.profile_name.setToolTip(where)

    # ----------------------------------------------------------- source picks

    def _pick_iso(self) -> None:
        path, _ = _qt_open_file(self, "Choose a Windows ISO", "", "ISO image (*.iso)")
        if path:
            self.source.setText(path)
            self.read_editions()

    def _pick_folder(self) -> None:
        path = _qt_dir(self, "Choose the extracted Windows folder")
        if path:
            self.source.setText(path)
            self.read_editions()

    def _pick_dir(self, target: QLineEdit) -> None:
        path = _qt_dir(self, "Choose a folder")
        if path:
            target.setText(path)

    def _pick_out(self) -> None:
        path, _ = _qt_save_file(self, "Output ISO", self.out.text(), "ISO image (*.iso)")
        if path:
            self.out.setText(path)

    def _source_edited(self) -> None:
        source = self.source.text().strip()
        if source and source != getattr(self, "_editions_source", None) and Path(source).exists():
            self.read_editions()

    def _set_edition(self, name: str) -> None:
        """Select an edition by name. A saved name that is not in the list yet stays visible until the list loads."""
        pos = self.edition.findText(name)
        if pos < 0:
            self.edition.clear()
            if name:
                self.edition.addItem(name)
        self.edition.setCurrentIndex(max(0, self.edition.findText(name)) if name else -1)

    def read_editions(self) -> None:
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Choose a source", "Pick a Windows ISO or extracted folder first.")
            return
        if getattr(self, "_ed_proc", None) is not None:
            return
        self._editions_source = source
        self._ed_out = ""
        self.edition_hint.setText("Reading the editions…")
        self._cancelled = False
        self._lock("Reading the editions", "Opening the source…", cancel=self._cancel_editions)
        self._progress_busy("Reading the editions from the source…")
        proc = QProcess(self)
        proc.setWorkingDirectory(str(PROJECT_ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc.readyReadStandardOutput.connect(
            lambda: setattr(self, "_ed_out", self._ed_out + bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")))
        proc.finished.connect(self._editions_done)
        self._ed_proc = proc
        proc.start(sys.executable, ["-u", "-m", "winforge", "editions", source, "--json"])

    def _cancel_editions(self) -> None:
        self._cancelled = True
        if self._ed_proc is not None:
            self._ed_proc.kill()

    def _editions_done(self, code: int, _status) -> None:
        proc, self._ed_proc = self._ed_proc, None
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace").strip()
        proc.deleteLater()
        self._progress_done()
        self._unlock()
        if code != 0 and getattr(self, "_cancelled", False):
            self._editions_source = None
            self.edition_hint.setText("Cancelled. Use Reload list to try again.")
            return
        if code != 0:
            self._editions_source = None
            self.edition_hint.setText("Could not read the source. Check the path and try Reload list.")
            QMessageBox.warning(self, "Could not read the source", err or self._ed_out.strip() or "Unknown error.")
            return
        editions = json.loads(self._ed_out)
        current = self.edition.currentText()
        self.edition.blockSignals(True)
        self.edition.clear()
        for e in editions:
            self.edition.addItem(e["name"])
            self.edition.setItemData(self.edition.count() - 1, f"Image index {e['index']}", Qt.ItemDataRole.ToolTipRole)
        pos = self.edition.findText(current)
        self.edition.setCurrentIndex(pos)
        self.edition.blockSignals(False)
        if pos >= 0:
            self.edition_hint.setText(f"{len(editions)} editions found. Only the selected one is kept.")
        else:
            self.edition_hint.setText(f"{len(editions)} editions found. Pick the one to keep.")
        self.statusBar().showMessage("Editions loaded")
        self._refresh()

    # ------------------------------------------------------------ progress

    def _progress_busy(self, text: str) -> None:
        """Indeterminate bar for work with no measurable progress."""
        self._busy_jobs = getattr(self, "_busy_jobs", 0) + 1
        self.progress.setRange(0, 0)
        self.percent.setText("")
        self.overlay.detail.setText(text)
        self.statusBar().showMessage(text)

    def _progress_set(self, fraction: float, text: str = "") -> None:
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.percent.setText(f"{self.progress.value() // 10}%")
        if text:
            self.overlay.detail.setText(text)
            self.statusBar().showMessage(text)

    def _progress_done(self) -> None:
        self._busy_jobs = max(0, getattr(self, "_busy_jobs", 1) - 1)
        if self._busy_jobs == 0:
            self.progress.setRange(0, 1000)
            self.progress.setValue(0)
            self.percent.setText("")

    def _progress_line(self, line: str, stages: int, state: dict) -> None:
        """Turn '== 3. Mount…' and DISM '[==== 42.0% ====]' lines into one smooth bar."""
        m = re.match(r"== (\d+)\.", line)
        if m:
            state["stage"], state["pct"] = int(m.group(1)), 0.0
            self._progress_set(state["stage"] / stages, line[3:])
            return
        m = re.search(r"(\d+(?:\.\d+)?)%", line)
        if m and line.lstrip().startswith("["):
            state["pct"] = float(m.group(1)) / 100
            self._progress_set((state.get("stage", 0) + state["pct"]) / stages)

    # ------------------------------------------------- import and scan

    def import_ntlite(self) -> None:
        path, _ = _qt_open_file(self, "Choose an NTLite preset", "", "NTLite presets (*.xml)")
        if not path:
            return
        try:
            profile, notes = import_ntlite(path)
        except (ValueError, ProfileError) as exc:
            QMessageBox.warning(self, "Could not import", str(exc))
            return
        self._path = None
        self.load_ui(profile)
        self._baseline = None
        self._update_profile_label()
        self._refresh()
        self.go("Account")
        text = "Imported. Check the Account and Tweaks pages."
        if notes:
            text += "\n\nNot carried over:\n- " + "\n- ".join(notes)
        QMessageBox.information(self, "NTLite preset imported", text)

    def _scan_file(self) -> Path:
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "WinForge" / "scan.json"

    def scan_image(self) -> None:
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Choose a source", "Pick a Windows ISO or folder on the Source page first.")
            return
        if self._proc is not None or getattr(self, "_scan_proc", None) is not None:
            QMessageBox.information(self, "Busy", "Wait for the current job to finish.")
            return
        args = ["-u", "-m", "winforge", "scan", "--source", source, "--work", self.work.text().strip() or DEFAULT_WORK,
                "--out", str(self._scan_file())]
        edition = self.edition.currentText().strip()
        if edition:
            args += ["--edition", edition]
        proc = QProcess(self)
        proc.setWorkingDirectory(str(PROJECT_ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._scan_output)
        proc.finished.connect(self._scan_done)
        self._scan_proc = proc
        self._scan_tail = ""
        self.scan_label.setText("Scanning…")
        self._scan_state = {}
        self._cancelled = False
        self._lock("Scanning the image", "Copying the image file…", cancel=self._cancel_scan)
        self._progress_busy("Scanning the image…")
        proc.start(sys.executable, args)

    def _cancel_scan(self) -> None:
        self._cancelled = True
        if self._scan_proc is not None:
            self._scan_proc.kill()
            QMessageBox.information(self, "Cancelled", "If the image stayed mounted, use Clean up leftovers "
                                    "on the Build page.")

    def _scan_output(self) -> None:
        text = bytes(self._scan_proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        for line in lines:
            self._progress_line(line.strip(), 5, self._scan_state)
        if lines:
            self._scan_tail = lines[-1]
            self.scan_label.setText(self._scan_tail[:120])

    def _scan_done(self, code: int, _status) -> None:
        self._scan_proc = None
        self._progress_done()
        self._unlock()
        if code != 0 and getattr(self, "_cancelled", False):
            self.scan_label.setText("Scan cancelled.")
            return
        if code != 0:
            self.scan_label.setText("Scan failed.")
            QMessageBox.warning(self, "Scan failed", self._scan_tail or "The scan stopped with an error. "
                                "Run WinForge as administrator and try again.")
            return
        self.apply_scan(json.loads(self._scan_file().read_text(encoding="utf-8")))

    def apply_scan(self, data: dict) -> None:
        self._scan = data
        group = "In your image"
        apps = self.apps.add_items(catalog.Item(a["name"], a["name"], group, "Found in your image.") for a in data["apps"])
        feats = self.features.add_items(
            catalog.Item(f["name"], f["name"], group, "Found in your image.")
            for f in data["features"] + data["capabilities"])
        svcs = self.services.add_items(
            catalog.Item(s["name"], s["name"], group, f"Found in your image. Start type {s['start']}.")
            for s in data["services"] if s["start"] != 4)
        self.scan_label.setText(
            f"Scanned: {len(data['apps'])} apps, {len(data['features']) + len(data['capabilities'])} features, "
            f"{len(data['services'])} services, {len(data['tasks'])} scheduled tasks. "
            f"Added {apps + feats + svcs} new items to the lists.")

    def pick_tasks(self) -> None:
        data = getattr(self, "_scan", None)
        if data is None and self._scan_file().exists():
            data = self._scan = json.loads(self._scan_file().read_text(encoding="utf-8"))
        if not data or not data.get("tasks"):
            QMessageBox.information(self, "No scan yet", "Run Scan image first. It lists the real scheduled tasks.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Scheduled tasks in your image")
        dialog.resize(720, 520)
        lay = QVBoxLayout(dialog)
        picker = CheckList([catalog.Item(t, t.rsplit("\\", 1)[-1], t.rsplit("\\", 1)[0] if "\\" in t else "",
                                         t.rsplit("\\", 1)[0] if "\\" in t else "") for t in data["tasks"]])
        lay.addWidget(picker, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        lay.addWidget(buttons)
        if dialog.exec():
            have = set(_lines(self.tasks_remove))
            for t in picker.checked():
                if t not in have:
                    self.tasks_remove.appendPlainText(t)

    # --------------------------------------------------------------- scripts

    def _insert_snippet(self, editor: QPlainTextEdit, combo: QComboBox, index: int) -> None:
        text = SNIPPETS.get(combo.itemText(index), "")
        if text:
            editor.insertPlainText(text + "\n")
        combo.setCurrentIndex(0)

    def _add_driver(self) -> None:
        path = _qt_dir(self, "Choose a driver folder")
        if path:
            self.drivers.appendPlainText(self._store_path(path))

    def _add_driver_boot(self) -> None:
        path = _qt_dir(self, "Choose a driver folder")
        if path:
            self.drivers_boot.appendPlainText(self._store_path(path))

    def _add_installer(self) -> None:
        path, _ = _qt_open_file(self, "Choose an installer", "", "Installers (*.exe *.msi)")
        if path:
            self.installers.appendPlainText(self._store_path(path) + "|/s /quiet")

    def _add_update(self) -> None:
        path, _ = _qt_open_file(self, "Choose an update", "", "Update packages (*.msu *.cab)")
        if path:
            self.updates.appendPlainText(self._store_path(path))

    def _ask_folder(self) -> str | None:
        text, ok = QInputDialog.getText(
            self, "Folder inside the image",
            "Which folder inside the image should it go in?\n"
            "Use a path under the system drive, for example Windows\\Setup\\Scripts.\n"
            "Leave it blank for the root of the drive (C:\\).",
            text="Windows\\Setup\\Scripts")
        if not ok:
            return None
        folder = _clean_folder(text)
        if folder is None:
            QMessageBox.warning(self, "Folder not allowed", "Use a folder path without a drive letter or '..'.")
        return folder

    def _target_folder(self) -> str | None:
        folder = self.files_tree.selected_folder()
        return folder if folder is not None else self._ask_folder()

    def _add_files(self) -> None:
        folder = self._target_folder()
        if folder is None:
            return
        paths, _ = _qt_open_files(self, "Choose files to copy into the image")
        for path in paths:
            self.files_tree.add_path(folder, path)

    def _add_folder(self) -> None:
        folder = self._target_folder()
        if folder is None:
            return
        path = _qt_dir(self, "Choose a folder to copy into the image")
        if path:
            self.files_tree.add_path(folder, path)

    def _add_reg(self) -> None:
        path, _ = _qt_open_file(self, "Choose a .reg file", "", "Registry files (*.reg)")
        if path:
            self.reg_files.appendPlainText(self._store_path(path))

    def _store_path(self, path: str) -> str:
        """Store paths relative to the profile when possible, so profiles stay portable."""
        if self._path:
            try:
                return os.path.relpath(path, self._path.parent)
            except ValueError:
                pass
        return path

    # ------------------------------------------------------------- presets

    def refresh_presets(self) -> None:
        while self.preset_box.count():
            item = self.preset_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for info in presets.list_presets():
            self.preset_box.addWidget(self._preset_row(info))
        self.preset_box.addStretch(1)

    def _preset_row(self, info) -> QWidget:
        frame = QFrame()
        frame.setObjectName("card")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel(info.label)
        title.setObjectName("cardTitle")
        desc = QLabel(info.description)
        desc.setObjectName("help")
        desc.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(desc)

        tag = QLabel("BUILT-IN" if info.builtin else "YOURS")
        tag.setObjectName("tagAccent" if info.builtin else "tag")
        tag.setToolTip("Built-in presets ship with WinForge. Your own presets are saved under your user folder.")

        lay.addLayout(text, 1)
        lay.addWidget(tag, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(_button("Load", lambda n=info.name: self.use_preset(n), "primary",
                              tip="Load these settings into the editor. Nothing is built yet."), 0,
                      Qt.AlignmentFlag.AlignTop)
        if not info.builtin:
            lay.addWidget(_button("Delete", lambda n=info.name: self.delete_preset(n), "danger",
                                  tip="Delete this saved preset. Its profile file is removed."), 0,
                          Qt.AlignmentFlag.AlignTop)
        return frame

    def use_preset(self, name: str) -> None:
        profile = presets.load_preset(name)
        self._path = None
        self.load_ui(profile)
        self._baseline = None  # a preset is not on disk yet, so it always counts as unsaved
        self.statusBar().showMessage(f"Loaded preset '{name}'. Save before building.")
        self.go("Source")

    def save_as_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:", text=self._name)
        if not ok:
            return
        try:
            presets.save_preset(name.strip(), self.collect())
        except (ValueError, ProfileError) as exc:
            QMessageBox.warning(self, "Could not save preset", str(exc))
            return
        self.refresh_presets()
        self.statusBar().showMessage(f"Saved preset '{name.strip()}'")

    def delete_preset(self, name: str) -> None:
        if name in catalog.builtin_presets():
            QMessageBox.information(self, "Built-in preset", "Built-in presets can't be deleted.")
            return
        if QMessageBox.question(self, "Delete preset", f"Delete the preset '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        presets.delete_preset(name)
        self.refresh_presets()

    # ------------------------------------------------------------- files

    def new_profile(self) -> None:
        self._path = None
        self.load_ui(default_profile())
        self._baseline = None
        self.go("Source")

    def open_profile(self) -> None:
        path, _ = _qt_open_file(self, "Open a profile", "", "Profile (*.json)")
        if not path:
            return
        try:
            profile = load_profile(Path(path))
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Could not open profile", str(exc))
            return
        self._path = Path(path)
        self.load_ui(profile)
        self._baseline = self._snapshot(profile)
        self.go("Source")

    def _write(self, path: Path) -> bool:
        try:
            profile = self.collect()
        except ProfileError as exc:
            QMessageBox.critical(self, "Fix the profile first", str(exc))
            return False
        if profile["name"] == "custom":
            profile["name"] = path.stem
        save_profile(profile, path)
        self._path = path
        self._name = profile["name"]
        self._baseline = self._snapshot(profile)
        self._update_profile_label()
        self._refresh()
        self.statusBar().showMessage(f"Saved {path}")
        return True

    def save_current(self) -> bool:
        if getattr(self, "_locked", False):
            return False
        return self._write(self._path) if self._path else self.save_as()

    def save_as(self) -> bool:
        path, _ = _qt_save_file(self, "Save profile", f"{self._name}.json", "Profile (*.json)")
        return self._write(Path(path)) if path else False

    # -------------------------------------------------------------- builds

    def _ensure_saved(self) -> bool:
        if self._path is None:
            QMessageBox.information(self, "Save first",
                                    "Builds read the profile from a saved file, so save it first.")
            return self.save_as()
        return self.save_current()

    def _run_build(self, dry: bool) -> None:
        if self._proc is not None:
            return
        if not self._ensure_saved():
            return
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Choose a source", "Pick a Windows ISO or folder on the Source page.")
            self.go("Source")
            return
        if not dry and QMessageBox.question(
                self, "Build the ISO",
                "This copies the source into the work folder and changes that copy.\n"
                "Your original ISO is not modified. Continue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        args = ["build", str(self._path), "--source", source,
                "--work", self.work.text().strip(), "--out", self.out.text().strip()]
        if self.oscdimg.text().strip():
            args += ["--oscdimg", self.oscdimg.text().strip()]
        if dry:
            args.append("--dry-run")
        self._start(args, "preview" if dry else "build", "Preview (dry run)" if dry else "Build ISO")

    def _run_cleanup(self) -> None:
        if self._proc is not None:
            return
        self._start(["cleanup", "--work", self.work.text().strip()], "cleanup", "Clean up leftovers")

    def _start(self, args: list[str], kind: str, title: str) -> None:
        self._last_kind = kind
        self._partial = ""
        self._pstate = {}
        self.stage.setText("Starting…")
        self._lock(title, overlay=False)
        self._progress_busy("Starting…")
        self.log.appendPlainText(f"\n===== {title} =====")
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(str(PROJECT_ROOT))
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._set_busy(True)
        self._proc.start(sys.executable, ["-u", "-m", "winforge", *args])

    def _set_busy(self, busy: bool) -> None:
        self.btn_cancel.setEnabled(busy)
        self.btn_cleanup.setEnabled(not busy)
        self.btn_open.setEnabled(False)
        self._set_build_enabled(not busy)

    def _on_output(self) -> None:
        if self._proc is None:
            return
        text = self._partial + bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        lines = text.split("\n")
        self._partial = lines.pop()
        for line in lines:
            line = line.rstrip("\r")
            if line.startswith("== "):
                self.stage.setText(line[3:])
            if self._last_kind == "build":
                self._progress_line(line, 8, self._pstate)
            self.log.appendPlainText(line)

    def _on_finished(self, code: int, _status) -> None:
        if self._partial:
            self.log.appendPlainText(self._partial)
            self._partial = ""
        if self._proc is not None:
            self._proc.deleteLater()
        self._proc = None
        ok = code == 0
        self.log.appendPlainText(f"Finished with exit code {code}")
        self.stage.setText("Finished" if ok else "Stopped with an error")
        if ok and self._last_kind == "build":
            self._progress_set(1.0, "Build finished")
            self._busy_jobs = 0
        else:
            self._progress_done()
        self._set_busy(False)
        self._unlock()
        if ok and self._last_kind == "build":
            self.btn_open.setEnabled(True)
        if not ok and self._last_kind == "build":
            QMessageBox.warning(self, "Build stopped",
                                "The build did not finish. Read the log for the first ERROR line. "
                                "If a build was interrupted, use Clean up leftovers before trying again.")
        self._refresh()

    def _cancel(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self.log.appendPlainText("Cancelled. Use Clean up leftovers before the next build if an image stayed mounted.")

    def _open_output(self) -> None:
        folder = Path(self.out.text().strip()).parent
        if sys.platform == "win32" and folder.exists():
            os.startfile(folder)  # type: ignore[attr-defined]


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_palette(app)
    window = MainWindow()
    window.show()
    return app.exec()
