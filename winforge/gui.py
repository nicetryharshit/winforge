"""WinForge editor (PySide6).

The GUI edits a profile and runs the same `python -m winforge` commands you can
type yourself, so GUI builds and headless builds behave the same way.
Real builds need an Administrator session on Windows.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import catalog, presets
from .profile import PHASES, ProfileError, default_profile, load_profile, normalise, save_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK = r"C:\WinForge\work"
DEFAULT_OUT = r"C:\WinForge\out\custom.iso"

PHASE_TITLES = {
    "specialize": ("Specialize", "Runs as SYSTEM after the install finishes copying, before the first setup screens. One command per line."),
    "setupcomplete": ("SetupComplete", "Runs as SYSTEM once setup finishes, before the first login. Good for system-wide changes."),
    "firstlogon": ("First logon", "Runs in order the first time the new account signs in. Good for installing apps with winget."),
}

SNIPPETS = {
    "Insert a snippet…": "",
    "Disable a service": "sc config <ServiceName> start= disabled",
    "Set a registry value (HKLM)": 'reg add "HKLM\\SOFTWARE\\<Path>" /v <Name> /t REG_DWORD /d 1 /f',
    "Install with winget": "winget install --id <Publisher.App> -e --silent --accept-package-agreements --accept-source-agreements",
    "Run a PowerShell script file": 'powershell -NoProfile -ExecutionPolicy Bypass -File "C:\\Windows\\Setup\\Scripts\\myscript.ps1"',
    "Delete a folder": 'rd /s /q "C:\\<Path>"',
}

PAGES = ("Start", "Source", "Debloat", "Tweaks", "Scripts & files", "Account", "Build")


def _lines(edit: QPlainTextEdit) -> list[str]:
    return [ln.strip() for ln in edit.toPlainText().splitlines() if ln.strip()]


def _set_lines(edit: QPlainTextEdit, items) -> None:
    edit.setPlainText("\n".join(items))


def _entry_key(r: dict) -> tuple:
    return (r["hive"], r["key"], r["name"], r["type"], str(r["data"]))


def _wrap(*widgets) -> QWidget:
    """Put widgets in a row, stretching the first one."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    for i, w in enumerate(widgets):
        row.addWidget(w, 1 if i == 0 else 0)
    return box


class CheckList(QWidget):
    """A searchable list of checkboxes with recommended, all and none shortcuts."""

    def __init__(self, items):
        super().__init__()
        self._recommended = {it.id: it.recommended for it in items}
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._filter)
        self.list = QListWidget()
        for it in items:
            text = ("★ " if it.recommended else "") + it.label
            if it.note:
                text += f"  —  {it.note}"
            li = QListWidgetItem(text)
            li.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Unchecked)
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            li.setToolTip(f"{it.id}  ·  {it.group}")
            self.list.addItem(li)

        buttons = QHBoxLayout()
        for label, fn in (("Select recommended", self.select_recommended),
                          ("Select all", lambda: self.set_checked(set(self._recommended))),
                          ("Clear", lambda: self.set_checked(set()))):
            b = QPushButton(label)
            b.clicked.connect(fn)
            buttons.addWidget(b)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addLayout(buttons)

    def _filter(self, text: str) -> None:
        t = text.lower()
        for i in range(self.list.count()):
            li = self.list.item(i)
            li.setHidden(t not in li.text().lower() and t not in li.toolTip().lower())

    def checked(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def set_checked(self, ids: set) -> None:
        for i in range(self.list.count()):
            li = self.list.item(i)
            on = li.data(Qt.ItemDataRole.UserRole) in ids
            li.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def select_recommended(self) -> None:
        self.set_checked({k for k, rec in self._recommended.items() if rec})


class RowTable(QWidget):
    """An editable grid with add and remove buttons."""

    def __init__(self, headers: list[str]):
        super().__init__()
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setStretchLastSection(True)
        add = QPushButton("Add row")
        remove = QPushButton("Remove selected")
        add.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        remove.clicked.connect(self._remove)
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WinForge")
        self.resize(1150, 820)
        self._path: Path | None = None
        self._name = "custom"
        self._description = ""
        self._index: int | None = None
        self._loaded: dict = default_profile()
        self._proc: QProcess | None = None
        self._partial = ""
        self._last_kind = ""

        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.addItems(PAGES)
        self.stack = QStackedWidget()
        for page in (self._page_start(), self._page_source(), self._page_debloat(),
                     self._page_tweaks(), self._page_scripts(), self._page_account(), self._page_build()):
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._on_page_changed)

        self.current_label = QLabel()
        self.current_label.setStyleSheet("color: #666;")
        top = QHBoxLayout()
        for label, fn in (("Save", self.save_current), ("Save as…", self.save_as)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addStretch()
        top.addWidget(self.current_label)

        body = QHBoxLayout()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(top)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)

        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.save_current)
        self.statusBar().showMessage("Ready")
        self.refresh_presets()
        self.load_ui(default_profile())
        self.nav.setCurrentRow(0)

    # ------------------------------------------------------------------ pages

    def _page_start(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<h2>Start</h2><p>Pick a preset to begin, or open a profile you saved before. "
                             "Presets are starting points; everything can be changed afterwards.</p>"))
        self.preset_list = QListWidget()
        self.preset_list.itemDoubleClicked.connect(lambda _item: self.use_preset())
        lay.addWidget(self.preset_list, 1)
        row = QHBoxLayout()
        for label, fn in (("Use preset", self.use_preset),
                          ("Save current as preset…", self.save_as_preset),
                          ("Delete preset", self.delete_preset),
                          ("Open profile file…", self.open_profile),
                          ("New blank", self.new_profile)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        return page

    def _page_source(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.source = QLineEdit()
        iso = QPushButton("ISO…")
        iso.clicked.connect(self._pick_iso)
        folder = QPushButton("Folder…")
        folder.clicked.connect(self._pick_folder)
        form.addRow("Windows ISO or folder", _wrap(self.source, iso, folder))

        read = QPushButton("Read editions from this source")
        read.clicked.connect(self.read_editions)
        form.addRow("", read)
        self.edition = QComboBox()
        self.edition.setEditable(True)
        self.edition.setMinimumWidth(340)
        self.edition.activated.connect(lambda _i: setattr(self, "_index", None))
        form.addRow("Edition", self.edition)
        self.edition_hint = QLabel("Choose a source above and click Read editions. "
                                   "Nothing is copied; WinForge only reads the image list.")
        self.edition_hint.setWordWrap(True)
        form.addRow("", self.edition_hint)

        self.work = QLineEdit(DEFAULT_WORK)
        work_btn = QPushButton("Browse…")
        work_btn.clicked.connect(lambda: self._pick_dir(self.work))
        form.addRow("Work folder", _wrap(self.work, work_btn))
        self.out = QLineEdit(DEFAULT_OUT)
        out_btn = QPushButton("Browse…")
        out_btn.clicked.connect(self._pick_out)
        form.addRow("Output ISO", _wrap(self.out, out_btn))

        self.reset_base = QCheckBox("ResetBase: smaller image, but updates can't be uninstalled later")
        self.compress = QCheckBox("Re-export the image to drop unused data (slower, smaller)")
        form.addRow("", self.reset_base)
        form.addRow("", self.compress)
        self.oscdimg = QLineEdit()
        self.oscdimg.setPlaceholderText("leave blank for the default ADK location")
        form.addRow("oscdimg.exe (advanced)", self.oscdimg)
        return page

    def _page_debloat(self) -> QWidget:
        self.apps = CheckList(catalog.APPS)
        self.features = CheckList(catalog.FEATURES + catalog.CAPABILITIES)
        self.services = CheckList(catalog.SERVICES)
        tabs = QTabWidget()
        tabs.addTab(self.apps, "Apps")
        tabs.addTab(self.features, "Features & capabilities")
        tabs.addTab(self.services, "Services")
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Tick what to remove or switch off. ★ marks the recommended choices. "
                             "Items missing from your image are skipped, not treated as errors."))
        lay.addWidget(tabs, 1)
        return page

    def _page_tweaks(self) -> QWidget:
        self.tweaks = CheckList(catalog.TWEAKS)
        self.custom = RowTable(["Hive", "Key", "Name", "Type", "Data"])
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("<b>Registry tweaks</b>. Each tick applies a set of registry values to the image."))
        lay.addWidget(self.tweaks, 2)
        lay.addWidget(QLabel("<b>Custom registry entries (advanced)</b>. Hive is SOFTWARE, SYSTEM or DEFAULT. "
                             "Key is a path inside the hive. Leave Name empty to set the default value."))
        lay.addWidget(self.custom, 1)
        return page

    def _page_scripts(self) -> QWidget:
        tabs = QTabWidget()
        self.scripts: dict[str, QPlainTextEdit] = {}
        for phase in PHASES:
            title, help_text = PHASE_TITLES[phase]
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.addWidget(QLabel(help_text))
            combo = QComboBox()
            combo.addItems(list(SNIPPETS))
            editor = QPlainTextEdit()
            self.scripts[phase] = editor
            combo.activated.connect(lambda i, e=editor, c=combo: self._insert_snippet(e, c, i))
            lay.addWidget(combo)
            lay.addWidget(editor, 1)
            tabs.addTab(page, title)

        files_page = QWidget()
        files_lay = QVBoxLayout(files_page)
        files_lay.addWidget(QLabel("<b>Files to copy into Windows</b>. From is a file or folder (absolute, or relative "
                                   "to the profile). To is the path inside the image, e.g. Windows\\Setup\\Scripts\\tweak.ps1"))
        self.files = RowTable(["From", "To"])
        files_lay.addWidget(self.files, 1)
        tabs.addTab(files_page, "Files")

        drivers_page = QWidget()
        drv_lay = QVBoxLayout(drivers_page)
        self.drivers = QPlainTextEdit()
        drv_btn = QPushButton("Add driver folder…")
        drv_btn.clicked.connect(self._add_driver)
        drv_lay.addWidget(QLabel("<b>Drivers</b> (folders containing .inf files, added recursively)"))
        drv_lay.addWidget(drv_btn)
        drv_lay.addWidget(self.drivers, 1)
        self.updates = QPlainTextEdit()
        upd_btn = QPushButton("Add update package…")
        upd_btn.clicked.connect(self._add_update)
        drv_lay.addWidget(QLabel("<b>Updates</b> (.msu or .cab packages added to the image)"))
        drv_lay.addWidget(upd_btn)
        drv_lay.addWidget(self.updates, 1)
        tabs.addTab(drivers_page, "Drivers & updates")

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(tabs)
        return page

    def _page_account(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.acct_name = QLineEdit()
        self.acct_pw = QLineEdit()
        self.acct_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.autologon = QCheckBox("Sign in automatically on first boot")
        self.skip_oobe = QCheckBox("Skip the out-of-box setup screens")
        form.addRow("Local account name", self.acct_name)
        form.addRow("Password (blank for none)", self.acct_pw)
        form.addRow("", self.autologon)
        form.addRow("", self.skip_oobe)
        note = QLabel("The password is saved in the profile in plain text. Keep profile files private.")
        note.setWordWrap(True)
        form.addRow("", note)
        return page

    def _page_build(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet("color: #b00020; font-weight: bold;")
        lay.addWidget(self.summary)
        lay.addWidget(self.problems)

        row = QHBoxLayout()
        self.btn_preview = QPushButton("Preview (dry run)")
        self.btn_preview.clicked.connect(lambda: self._run_build(dry=True))
        self.btn_build = QPushButton("Build ISO")
        self.btn_build.clicked.connect(lambda: self._run_build(dry=False))
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_cleanup = QPushButton("Clean up leftovers")
        self.btn_cleanup.setToolTip("Unmount an image left behind by a cancelled or crashed build")
        self.btn_cleanup.clicked.connect(self._run_cleanup)
        self.btn_open = QPushButton("Open output folder")
        self.btn_open.clicked.connect(self._open_output)
        self.btn_open.setEnabled(False)
        for b in (self.btn_preview, self.btn_build, self.btn_cancel, self.btn_cleanup, self.btn_open):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        self.stage = QLabel("Idle")
        self.stage.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.stage)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family: Consolas, monospace;")
        lay.addWidget(self.log, 1)
        self.btn_cancel.setEnabled(False)
        return page

    # ----------------------------------------------------------- UI <-> data

    def load_ui(self, p: dict) -> None:
        self._loaded = p
        self._name = p["name"]
        self._description = p.get("description", "")
        self._index = p["index"]
        self.edition.setCurrentText(p["edition"] or "")
        self.reset_base.setChecked(p["options"]["reset_base"])
        self.compress.setChecked(p["options"]["compress"])
        self.oscdimg.setText(p["options"]["oscdimg"])
        acct = p["account"]
        self.acct_name.setText(acct["name"])
        self.acct_pw.setText(acct["password"])
        self.autologon.setChecked(acct["autologon"])
        self.skip_oobe.setChecked(acct["skip_oobe"])

        self.apps.set_checked(set(p["remove"]["appx"]))
        self.features.set_checked(set(p["remove"]["features"]) | set(p["remove"]["capabilities"]))
        self.services.set_checked(set(p["services_disable"]))

        catalog_keys = {_entry_key(dict(e)) for t in catalog.TWEAKS for e in t.entries}
        present = {_entry_key(r) for r in p["registry"]}
        self.tweaks.set_checked({
            t.id for t in catalog.TWEAKS
            if all(_entry_key(dict(e)) in present for e in t.entries)
        })
        self.custom.set_rows([[r["hive"], r["key"], r["name"], r["type"], r["data"]]
                              for r in p["registry"] if _entry_key(r) not in catalog_keys])

        self.files.set_rows([[f["from"], f["to"]] for f in p["files"]])
        _set_lines(self.drivers, p["drivers"])
        _set_lines(self.updates, p["updates"])
        for phase, editor in self.scripts.items():
            editor.setPlainText("\n".join(p["scripts"][phase]))
        self._update_current_label()
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
            "edition": self.edition.currentText().strip(),
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
            "services_disable": self.services.checked(),
            "tasks_remove": list(self._loaded.get("tasks_remove", [])),
            "files": [{"from": a, "to": b} for a, b in self.files.rows()],
            "scripts": {phase: _lines(editor) for phase, editor in self.scripts.items()},
            "account": {
                "name": self.acct_name.text().strip(),
                "password": self.acct_pw.text(),
                "autologon": self.autologon.isChecked(),
                "skip_oobe": self.skip_oobe.isChecked(),
            },
        }
        return normalise(raw)

    def _refresh(self) -> None:
        """Re-check the profile and update the status line, the summary and the build buttons."""
        try:
            p = self.collect()
        except ProfileError as exc:
            self.problems.setText(f"Fix this before building: {exc}")
            self.summary.setText("")
            self._set_build_enabled(False)
            self.statusBar().showMessage(f"Problem: {exc}")
            return
        self.problems.setText("")
        self.summary.setText(
            f"<b>{p['name']}</b> · {p['edition'] or 'index ' + str(p['index'])}<br>"
            f"Remove {len(p['remove']['appx'])} apps, {len(p['remove']['features'])} features, "
            f"{len(p['remove']['capabilities'])} capabilities. Disable {len(p['services_disable'])} services.<br>"
            f"{len(p['registry'])} registry edits · {len(p['files'])} files · {len(p['drivers'])} driver folders · "
            f"{len(p['updates'])} update packages · {sum(len(v) for v in p['scripts'].values())} script lines<br>"
            f"Account: {p['account']['name']}"
            f"{' (signs in automatically)' if p['account']['autologon'] else ''}"
        )
        self._set_build_enabled(self._proc is None)
        self.statusBar().showMessage("Profile is valid")

    def _set_build_enabled(self, on: bool) -> None:
        self.btn_preview.setEnabled(on)
        self.btn_build.setEnabled(on)

    def _update_current_label(self) -> None:
        where = str(self._path) if self._path else "unsaved profile"
        self.current_label.setText(f"{self._name}  ·  {where}")

    def _on_page_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        if PAGES[row] == "Build":
            self._refresh()
        if PAGES[row] == "Start":
            self.refresh_presets()

    # ----------------------------------------------------------------- source

    def _pick_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a Windows ISO", "", "ISO image (*.iso)")
        if path:
            self.source.setText(path)

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose the extracted Windows folder")
        if path:
            self.source.setText(path)

    def _pick_dir(self, target: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if path:
            target.setText(path)

    def _pick_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Output ISO", self.out.text(), "ISO image (*.iso)")
        if path:
            self.out.setText(path)

    def read_editions(self) -> None:
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Choose a source", "Pick a Windows ISO or extracted folder first.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("Reading editions…")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "winforge", "editions", source, "--json"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Timed out", "Reading the source took too long.")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if result.returncode != 0:
            QMessageBox.warning(self, "Could not read the source", (result.stderr or result.stdout).strip())
            return
        editions = json.loads(result.stdout)
        current = self.edition.currentText()
        self.edition.clear()
        for e in editions:
            self.edition.addItem(e["name"])
        pos = self.edition.findText(current)
        if pos >= 0:
            self.edition.setCurrentIndex(pos)
        else:
            self.edition.setCurrentText(current)
        self.edition_hint.setText(f"Found {len(editions)} editions. Pick the one to customise.")
        self.statusBar().showMessage("Editions loaded")
        self._refresh()

    # --------------------------------------------------------------- scripts

    def _insert_snippet(self, editor: QPlainTextEdit, combo: QComboBox, index: int) -> None:
        text = SNIPPETS.get(combo.itemText(index), "")
        if text:
            editor.insertPlainText(text + "\n")
        combo.setCurrentIndex(0)

    def _add_driver(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a driver folder")
        if path:
            self.drivers.appendPlainText(self._store_path(path))

    def _add_update(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose an update", "", "Update packages (*.msu *.cab)")
        if path:
            self.updates.appendPlainText(self._store_path(path))

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
        self.preset_list.clear()
        for info in presets.list_presets():
            tag = "built-in" if info.builtin else "yours"
            li = QListWidgetItem(f"{info.label}  [{tag}]\n    {info.description}")
            li.setData(Qt.ItemDataRole.UserRole, (info.name, info.builtin))
            self.preset_list.addItem(li)

    def _selected_preset(self):
        item = self.preset_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Pick a preset", "Select a preset in the list first.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def use_preset(self) -> None:
        selected = self._selected_preset()
        if not selected:
            return
        name, _builtin = selected
        profile = presets.load_preset(name)
        self._path = None
        self.load_ui(profile)
        self.statusBar().showMessage(f"Loaded preset '{name}'. Save before building.")
        self.nav.setCurrentRow(PAGES.index("Source"))

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

    def delete_preset(self) -> None:
        selected = self._selected_preset()
        if not selected:
            return
        name, builtin = selected
        if builtin:
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
        self.nav.setCurrentRow(PAGES.index("Source"))

    def open_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open a profile", "", "Profile (*.json)")
        if not path:
            return
        try:
            profile = load_profile(Path(path))
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Could not open profile", str(exc))
            return
        self._path = Path(path)
        self.load_ui(profile)
        self.nav.setCurrentRow(PAGES.index("Source"))

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
        self._update_current_label()
        self.statusBar().showMessage(f"Saved {path}")
        return True

    def save_current(self) -> bool:
        return self._write(self._path) if self._path else self.save_as()

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save profile", f"{self._name}.json", "Profile (*.json)")
        return self._write(Path(path)) if path else False

    # -------------------------------------------------------------- builds

    def _ensure_saved(self) -> bool:
        if self._path is None:
            QMessageBox.information(self, "Save first",
                                    "Builds read the profile from a saved file, so save it first.")
            return self.save_as()
        return self.save_current()

    def _run_build(self, dry: bool) -> None:
        if not self._ensure_saved():
            return
        if self._proc is not None:
            return
        if not self._ensure_saved():
            return
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Choose a source", "Pick a Windows ISO or folder on the Source page.")
            self.nav.setCurrentRow(PAGES.index("Source"))
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
        self.stage.setText("Starting…")
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
        self._set_busy(False)
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
    window = MainWindow()
    window.show()
    return app.exec()
