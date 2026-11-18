"""Scan a Windows image and list what is really in it: apps, features, capabilities, services, scheduled tasks.

The parsers work on plain DISM / reg.exe text so they can be tested anywhere. `scan_image` needs Windows.
The result is saved as JSON; the GUI uses it to show real items next to the built-in catalog.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Callable

from .editions import find_edition, parse_wim_info
from .pipeline import Runner, _force_writable
from .util import ps_quote


def parse_appx(text: str) -> list[dict]:
    """Output of `dism /Get-ProvisionedAppxPackages`."""
    apps, current = [], {}
    for line in text.splitlines():
        m = re.match(r"\s*(DisplayName|PackageName|Version)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if key == "DisplayName" and current.get("name"):
            apps.append(current)
            current = {}
        if key == "DisplayName":
            current["name"] = value
        elif key == "Version":
            current["version"] = value
    if current.get("name"):
        apps.append(current)
    return apps


def parse_table(text: str) -> list[dict]:
    """Output of `dism /Get-Features /Format:Table` or `/Get-Capabilities /Format:Table`."""
    rows = []
    for line in text.splitlines():
        if "|" not in line:
            continue
        name, _, state = (part.strip() for part in line.partition("|"))
        state = state.split("|")[0].strip()
        if not name or name.lower().startswith(("feature name", "capability identity")) or set(name) <= {"-", " "}:
            continue
        rows.append({"name": name, "state": state})
    return rows


def parse_services(text: str) -> list[dict]:
    """Output of `reg query HKLM\\WF_SYSTEM\\ControlSet001\\Services /s /v Start`."""
    out, name = [], None
    for line in text.splitlines():
        m = re.match(r"HKEY_LOCAL_MACHINE\\WF_SYSTEM\\ControlSet001\\Services\\([^\\]+)\s*$", line.strip(), re.I)
        if m:
            name = m.group(1)
            continue
        m = re.match(r"\s*Start\s+REG_DWORD\s+0x([0-9a-fA-F]+)", line)
        if m and name:
            out.append({"name": name, "start": int(m.group(1), 16)})
            name = None
    return out


def list_tasks(mount: Path) -> list[str]:
    root = Path(mount) / "Windows" / "System32" / "Tasks"
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(root)).replace("/", "\\") for p in root.rglob("*") if p.is_file())


def scan_image(source, work, out, edition: str = "", index: int = 0,
               log: Callable[[str], None] = print) -> dict:
    source, work, out = Path(source), Path(work), Path(out)
    R = Runner(False, log)
    stage = work / "scan"
    mount = stage / "mount"
    wim = stage / "install.wim"
    if stage.exists():
        shutil.rmtree(stage, onerror=_force_writable)
    mount.mkdir(parents=True)
    log("== 1. Copy the Windows image file")
    if source.suffix.lower() == ".iso":
        iso = ps_quote(source)
        R.ps(f"$img = Mount-DiskImage -ImagePath {iso} -PassThru; $drv = ($img | Get-Volume).DriveLetter; "
             f"$s = ($drv + ':\\sources\\'); "
             f"$f = Get-ChildItem $s -Filter 'install.*' | Where-Object {{ $_.Extension -in '.wim','.esd' }} | Select-Object -First 1; "
             f"Copy-Item $f.FullName ({ps_quote(stage)} + '\\' + $f.Name); "
             f"Dismount-DiskImage -ImagePath {iso} | Out-Null")
    else:
        src = source / "sources"
        found = next((src / n for n in ("install.wim", "install.esd") if (src / n).exists()), None)
        if found is None:
            raise RuntimeError("the source has no sources\\install.wim or install.esd")
        shutil.copy2(found, stage / found.name)
    image = next(p for p in stage.glob("install.*") if p.suffix.lower() in (".wim", ".esd"))
    if not index:
        editions = parse_wim_info(R.run(["dism.exe", "/Get-WimInfo", f"/WimFile:{image}"]))
        index = find_edition(editions, name=edition).index
    log(f"== 2. Mount index {index} read-only")
    R.run(["dism.exe", "/Mount-Image", f"/ImageFile:{image}", f"/Index:{index}", f"/MountDir:{mount}", "/ReadOnly"])
    result: dict = {}
    try:
        log("== 3. Read apps, features and capabilities")
        result["apps"] = parse_appx(R.run(["dism.exe", f"/Image:{mount}", "/Get-ProvisionedAppxPackages"]))
        result["features"] = parse_table(R.run(["dism.exe", f"/Image:{mount}", "/Get-Features", "/Format:Table"]))
        result["capabilities"] = parse_table(R.run(["dism.exe", f"/Image:{mount}", "/Get-Capabilities", "/Format:Table"]))
        log("== 4. Read services and scheduled tasks")
        R.run(["reg.exe", "load", "HKLM\\WF_SYSTEM", str(mount / "Windows" / "System32" / "config" / "SYSTEM")])
        try:
            result["services"] = parse_services(R.run(
                ["reg.exe", "query", "HKLM\\WF_SYSTEM\\ControlSet001\\Services", "/s", "/v", "Start"], check=False))
        finally:
            R.run(["reg.exe", "unload", "HKLM\\WF_SYSTEM"], check=False)
        result["tasks"] = list_tasks(mount)
    finally:
        log("== 5. Unmount")
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Discard"], check=False)
        shutil.rmtree(stage, onerror=_force_writable)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log(f"== Done: {len(result['apps'])} apps, {len(result['features'])} features, "
        f"{len(result['capabilities'])} capabilities, {len(result['services'])} services, {len(result['tasks'])} tasks")
    return result
