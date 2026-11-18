"""Small helpers shared by the build, editions and GUI code."""
from __future__ import annotations

import ctypes
import subprocess
import sys


def ps_quote(value) -> str:
    """Quote a value as a PowerShell single-quoted string."""
    return "'" + str(value).replace("'", "''") + "'"


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_powershell(script: str) -> str:
    """Run a PowerShell snippet and return its stdout. Raises RuntimeError on failure."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "PowerShell command failed")
    return result.stdout.strip()
