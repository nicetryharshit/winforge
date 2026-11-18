"""WinForge GUI (PySide6). Edit a profile, save it, and run a build.

Real builds need an elevated (Administrator) session on Windows.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from .profile import PHASES, default_profile, load_profile, normalise, save_profile

PHASE_HELP = {
    "specialize": "Runs as SYSTEM after install, before OOBE. One command per line.",
    "setupcomplete": "Written to SetupComplete.cmd. Runs as SYSTEM after setup, before first logon.",
    "firstlogon": "Runs in order at the first logon as the new account.",
}


def _lines(edit: QPlainTextEdit) -> list[str]:
    return [ln.strip() for ln in edit.toPlainText().splitlines() if ln.strip()]


def _set_lines(edit: QPlainTextEdit, items) -> None:
    edit.setPlainText("\n".join(items))


class RowTable(QWidget):
    """A simple editable grid with add and remove buttons."""

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
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def _remove(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def rows(self) -> list[list[str]]:
        out = []
        for r in range(self.table.rowCount()):
            vals = [
                self.table.item(r, c).text().strip() if self.table.item(r, c) else ""
                for c in range(self.table.columnCount())
            ]
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
        self.resize(1100, 800)
        self.path: Path | None = None
        self.proc: QProcess | None = None

        self.tabs = QTabWidget()
        self._build_general_tab()
        self._build_remove_tab()
        self._build_registry_tab()
        self._build_files_tab()
        self._build_scripts_tab()
        self._build_build_tab()

        self.status = QLabel()
        bar = QHBoxLayout()
        for label, fn in (("New", self.new_profile), ("Open...", self.open_profile),
                          ("Save", self.save_current), ("Save as...", self.save_as)):
            button = QPushButton(label)
            button.clicked.connect(fn)
            bar.addWidget(button)
        bar.addStretch()
        bar.addWidget(self.status)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(bar)
        layout.addWidget(self.tabs, 3)
        layout.addWidget(self.log, 1)
        self.setCentralWidget(root)

        self.load_ui(default_profile())
        self._update_status()

    # ---- tabs -------------------------------------------------------------

    def _box(self, layout: QVBoxLayout, label: str) -> QPlainTextEdit:
        layout.addWidget(QLabel(label))
        edit = QPlainTextEdit()
        layout.addWidget(edit)
        return edit

    def _build_general_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.edition = QLineEdit()
        self.index = QLineEdit()
        self.index.setPlaceholderText("optional; overrides edition")
        self.reset_base = QCheckBox("ResetBase (updates can no longer be uninstalled)")
        self.compress = QCheckBox("Re-export WIM to drop unused data")
        self.oscdimg = QLineEdit()
        self.oscdimg.setPlaceholderText("blank = default ADK path")
        self.acct_name = QLineEdit()
        self.acct_pw = QLineEdit()
        self.acct_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.autologon = QCheckBox("Autologon")
        self.skip_oobe = QCheckBox("Skip OOBE screens")
        form.addRow("Edition", self.edition)
        form.addRow("Index", self.index)
        form.addRow("", self.reset_base)
        form.addRow("", self.compress)
        form.addRow("oscdimg.exe", self.oscdimg)
        form.addRow("Account name", self.acct_name)
        form.addRow("Account password", self.acct_pw)
        form.addRow("", self.autologon)
        form.addRow("", self.skip_oobe)
        self.tabs.addTab(page, "General")

    def _build_remove_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.appx = self._box(layout, "Appx packages to remove (display names, one per line)")
        self.caps = self._box(layout, "Windows capabilities to remove")
        self.feats = self._box(layout, "Optional features to disable and remove")
        self.svc = self._box(layout, "Services to disable (Start = 4)")
        self.tasks = self._box(layout, "Scheduled task files to delete (relative to Windows\\System32\\Tasks)")
        self.tabs.addTab(page, "Remove")

    def _build_registry_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Hive: SOFTWARE, SYSTEM or DEFAULT (Default user). "
                                "Type: REG_SZ, REG_DWORD, REG_QWORD, REG_EXPAND_SZ, REG_MULTI_SZ, REG_BINARY."))
        self.registry = RowTable(["Hive", "Key", "Name", "Type", "Data"])
        layout.addWidget(self.registry)
        self.tabs.addTab(page, "Registry")

    def _build_files_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.files = RowTable(["From (relative to profile)", "To (relative to image root)"])
        layout.addWidget(self.files)
        self.drivers = self._box(layout, "Driver folders to inject (one per line, relative to profile)")
        self.updates = self._box(layout, "Update packages to add (.msu/.cab, relative to profile)")
        self.tabs.addTab(page, "Files")

    def _build_scripts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.scripts: dict[str, QPlainTextEdit] = {}
        for phase in PHASES:
            self.scripts[phase] = self._box(layout, f"{phase}: {PHASE_HELP[phase]}")
        self.tabs.addTab(page, "Scripts")

    def _build_build_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)
        self.source = QLineEdit()
        iso_btn = QPushButton("ISO...")
        iso_btn.clicked.connect(self._pick_iso)
        dir_btn = QPushButton("Folder...")
        dir_btn.clicked.connect(self._pick_dir)
        src_row = QHBoxLayout()
        src_row.addWidget(self.source)
        src_row.addWidget(iso_btn)
        src_row.addWidget(dir_btn)
        self.work = QLineEdit(r"C:\WinForge\work")
        self.out = QLineEdit(r"C:\WinForge\out\custom.iso")
        self.dry = QCheckBox("Dry run (print commands only)")
        self.dry.setChecked(True)
        build_btn = QPushButton("Build")
        build_btn.clicked.connect(self.build)
        form.addRow("Source", src_row)
        form.addRow("Work folder", self.work)
        form.addRow("Output ISO", self.out)
        form.addRow("", self.dry)
        form.addRow("", build_btn)
        self.tabs.addTab(page, "Build")

    def _pick_iso(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose Windows ISO", "", "ISO (*.iso)")
        if path:
            self.source.setText(path)

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose extracted Windows folder")
        if path:
            self.source.setText(path)

    # ---- UI <-> profile ---------------------------------------------------

    def load_ui(self, p: dict) -> None:
        self.edition.setText(p["edition"] or "")
        self.index.setText("" if p["index"] is None else str(p["index"]))
        self.reset_base.setChecked(p["options"]["reset_base"])
        self.compress.setChecked(p["options"]["compress"])
        self.oscdimg.setText(p["options"]["oscdimg"])
        acct = p["account"]
        self.acct_name.setText(acct["name"])
        self.acct_pw.setText(acct["password"])
        self.autologon.setChecked(acct["autologon"])
        self.skip_oobe.setChecked(acct["skip_oobe"])
        _set_lines(self.appx, p["remove"]["appx"])
        _set_lines(self.caps, p["remove"]["capabilities"])
        _set_lines(self.feats, p["remove"]["features"])
        _set_lines(self.svc, p["services_disable"])
        _set_lines(self.tasks, p["tasks_remove"])
        _set_lines(self.drivers, p["drivers"])
        _set_lines(self.updates, p["updates"])
        self.registry.set_rows([[r["hive"], r["key"], r["name"], r["type"], r["data"]] for r in p["registry"]])
        self.files.set_rows([[f["from"], f["to"]] for f in p["files"]])
        for phase, edit in self.scripts.items():
            _set_lines(edit, p["scripts"][phase])

    def collect(self, name: str) -> dict:
        index = self.index.text().strip()
        raw = {
            "name": name,
            "edition": self.edition.text().strip(),
            "index": int(index) if index else None,
            "options": {
                "reset_base": self.reset_base.isChecked(),
                "compress": self.compress.isChecked(),
                "oscdimg": self.oscdimg.text().strip(),
            },
            "remove": {
                "appx": _lines(self.appx),
                "capabilities": _lines(self.caps),
                "features": _lines(self.feats),
            },
            "drivers": _lines(self.drivers),
            "updates": _lines(self.updates),
            "registry": [dict(zip(("hive", "key", "name", "type", "data"), row))
                         for row in self.registry.rows()],
            "services_disable": _lines(self.svc),
            "tasks_remove": _lines(self.tasks),
            "files": [{"from": a, "to": b} for a, b in self.files.rows()],
            "scripts": {phase: _lines(edit) for phase, edit in self.scripts.items()},
            "account": {
                "name": self.acct_name.text().strip(),
                "password": self.acct_pw.text(),
                "autologon": self.autologon.isChecked(),
                "skip_oobe": self.skip_oobe.isChecked(),
            },
        }
        return normalise(raw)

    # ---- file actions -----------------------------------------------------

    def _update_status(self) -> None:
        self.status.setText(str(self.path) if self.path else "Unsaved profile")

    def new_profile(self) -> None:
        self.path = None
        self.load_ui(default_profile())
        self._update_status()

    def open_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open profile", "", "Profile (*.json)")
        if not path:
            return
        try:
            profile = load_profile(Path(path))
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Could not open profile", str(exc))
            return
        self.path = Path(path)
        self.load_ui(profile)
        self._update_status()

    def _write(self, path: Path) -> bool:
        try:
            profile = self.collect(path.stem)
        except (ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Invalid profile", str(exc))
            return False
        save_profile(profile, path)
        self.path = path
        self._update_status()
        self.log.appendPlainText(f"Saved {path}")
        return True

    def save_current(self) -> bool:
        return self._write(self.path) if self.path else self.save_as()

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save profile", "profile.json", "Profile (*.json)")
        return self._write(Path(path)) if path else False

    # ---- build ------------------------------------------------------------

    def build(self) -> None:
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "A build is already running.")
            return
        source = self.source.text().strip()
        if not source:
            QMessageBox.information(self, "Missing source", "Choose a Windows ISO or extracted folder first.")
            return
        if not self.save_current():
            return
        args = ["-u", "-m", "winforge", "build", str(self.path),
                "--source", source, "--work", self.work.text().strip(), "--out", self.out.text().strip()]
        if self.dry.isChecked():
            args.append("--dry-run")
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_output)
        self.proc.finished.connect(self._on_finished)
        self.log.appendPlainText("> python " + " ".join(args))
        self.proc.start(sys.executable, args)

    def _on_output(self) -> None:
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace").rstrip()
        if text:
            self.log.appendPlainText(text)

    def _on_finished(self, code: int, _status) -> None:
        self.log.appendPlainText(f"Build finished with exit code {code}")
        self.proc.deleteLater()
        self.proc = None


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
