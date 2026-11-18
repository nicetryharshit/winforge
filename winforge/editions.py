"""Read edition names and indexes from a Windows source (ISO, folder, WIM or ESD).

Reading works on the mounted ISO directly, so nothing is copied.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from .util import ps_quote, run_powershell

IMAGE_NAMES = ("install.wim", "install.esd")


@dataclass(frozen=True)
class Edition:
    index: int
    name: str
    description: str = ""


def parse_wim_info(text: str) -> list[Edition]:
    """Parse `dism /Get-WimInfo` output (English). Returns editions in index order."""
    editions: list[Edition] = []
    current: Edition | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if m := re.match(r"Index\s*:\s*(\d+)$", line):
            if current:
                editions.append(current)
            current = Edition(int(m.group(1)), "")
        elif current and (m := re.match(r"Name\s*:\s*(.+)$", line)):
            current = replace(current, name=m.group(1).strip())
        elif current and (m := re.match(r"Description\s*:\s*(.+)$", line)):
            current = replace(current, description=m.group(1).strip())
    if current:
        editions.append(current)
    return [e for e in editions if e.name]


def find_edition(editions: list[Edition], name: str | None = None, index: int | None = None) -> Edition:
    if index is not None:
        for e in editions:
            if e.index == index:
                return e
        raise ValueError(f"no image with index {index} in this source")
    wanted = (name or "").strip().lower()
    for e in editions:
        if e.name.lower() == wanted:
            return e
    available = ", ".join(e.name for e in editions) or "none found"
    raise ValueError(f"edition '{name}' not found. Available: {available}")


def read_editions(source: Path) -> list[Edition]:
    """Accepts an ISO file, an extracted folder, or a .wim/.esd file."""
    source = Path(source)
    if source.suffix.lower() == ".iso":
        return _from_iso(source)
    if source.suffix.lower() in (".wim", ".esd"):
        return _from_image(source)
    if source.is_dir():
        for name in IMAGE_NAMES:
            candidate = source / "sources" / name
            if candidate.exists():
                return _from_image(candidate)
        raise ValueError(f"no sources\\install.wim or install.esd under {source}")
    raise ValueError(f"not an ISO, folder, WIM or ESD: {source}")


def _from_image(image: Path) -> list[Edition]:
    result = subprocess.run(
        ["dism.exe", "/Get-WimInfo", f"/WimFile:{image}"],
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise ValueError(f"dism could not read {image}: {detail}")
    return parse_wim_info(result.stdout)


def _from_iso(iso: Path) -> list[Edition]:
    quoted = ps_quote(iso)
    try:
        letter = run_powershell(
            f"$img = Mount-DiskImage -ImagePath {quoted} -PassThru; ($img | Get-Volume).DriveLetter"
        )
        if not letter:
            raise ValueError(f"could not mount {iso}")
        return read_editions(Path(f"{letter}:\\"))
    finally:
        try:
            run_powershell(f"Dismount-DiskImage -ImagePath {quoted} | Out-Null")
        except RuntimeError:
            pass
