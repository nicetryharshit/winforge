"""Turn the App page, first-boot installs and home location into plain files, registry edits and commands.

The result is a copy of the profile with those extras folded into `files`, `registry` and `scripts`, so the
rest of the pipeline stays simple. The copy keeps the untouched profile under `_original`, which is what gets
saved next to the ISO.
"""
from __future__ import annotations

import copy
from pathlib import PureWindowsPath

LOG = r"C:\WinForge-setup.log"


def _quote(path: str) -> str:
    return f'"{path}"'


def app_target(app: dict) -> str:
    exe = str(app["exe"]).replace("/", "\\").lstrip("\\")
    return f"C:\\{app['name']}\\{exe}"


def describe_app(app: dict) -> str:
    """One plain sentence for the App page: exactly what will happen on the new PC."""
    where = f"C:\\{app['name']}"
    if app["mode"] == "task":
        how = "A scheduled task starts it every time the account signs in."
    elif app["mode"] == "run":
        how = "A Run entry starts it every time the account signs in."
    else:
        how = ("On the first sign-in a one-time step makes it the Windows shell and restarts the PC. "
               "From then on it replaces the desktop.")
    return f"The app folder is copied to {where}. {how}"


def apply_extras(profile: dict) -> dict:
    p = copy.deepcopy(profile)
    first_boot: list[str] = []
    after: list[str] = []

    for folder in p["drivers_boot"]:
        name = PureWindowsPath(folder).name or "drivers"
        p["files"].append({"from": folder, "to": f"Drivers\\{name}"})
        first_boot.append(f'pnputil /add-driver "%SystemDrive%\\Drivers\\{name}\\*.inf" /subdirs /install >> {LOG} 2>&1')
    for inst in p["installers"]:
        name = PureWindowsPath(inst["file"]).name
        p["files"].append({"from": inst["file"], "to": f"Drivers\\{name}"})
        args = f" {inst['args']}" if inst["args"].strip() else ""
        first_boot.append(f'start /wait "" "%SystemDrive%\\Drivers\\{name}"{args} >> {LOG} 2>&1')

    app = p["app"]
    if app["enabled"]:
        target = app_target(app)
        p["files"].append({"from": app["folder"], "to": app["name"]})
        if app["grant_write"]:
            after.append(f'icacls "C:\\{app["name"]}" /grant "Everyone":(OI)(CI)F /T >> {LOG} 2>&1')
        if app["mode"] == "task":
            after.append(f'schtasks /create /tn "{app["name"]}Launcher" /tr "\\"{target}\\"" /sc onlogon /rl highest /f >> {LOG} 2>&1')
        elif app["mode"] == "run":
            p["registry"].append({"hive": "SOFTWARE", "key": r"Microsoft\Windows\CurrentVersion\Run",
                                  "name": app["name"], "type": "REG_SZ", "data": _quote(target)})
        else:
            p["registry"].append({
                "hive": "SOFTWARE", "key": r"Microsoft\Windows\CurrentVersion\RunOnce",
                "name": f"{app['name']}SetShell", "type": "REG_SZ",
                "data": ('cmd /c reg add "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" '
                         f'/v Shell /t REG_SZ /d "{target}" /f & shutdown /r /t 0'),
            })
        if app["launch_now"]:
            after.append(f'start "" "{target}"')

    p["scripts"]["setupcomplete"] = first_boot + list(p["scripts"]["setupcomplete"]) + after

    geo = p["region"]["geo_id"]
    if geo:
        p["scripts"]["firstlogon"] = list(p["scripts"]["firstlogon"]) + [
            f'powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-WinHomeLocation -GeoId {geo}"'
        ]
    p["_original"] = profile
    return p
