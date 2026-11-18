"""Import an NTLite preset (.xml) into a WinForge profile.

NTLite presets describe the same job WinForge does, so the parts that map cleanly are carried over:
account, sign-in, region, first-boot commands, service switches, a handful of known registry tweaks and the
.reg files. Anything else is returned as a plain-language note, never dropped silently.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .profile import default_profile, normalise

_W = r"Policies\Microsoft\Windows"
# NTLite tweak name ("Key\Value") -> (hive, registry key, value name)
KNOWN_TWEAKS = {
    r"AU\NoAutoUpdate": ("SOFTWARE", _W + r"\WindowsUpdate\AU", "NoAutoUpdate"),
    r"AU\AUOptions": ("SOFTWARE", _W + r"\WindowsUpdate\AU", "AUOptions"),
    r"WindowsUpdate\ExcludeWUDriversInQualityUpdate": ("SOFTWARE", _W + r"\WindowsUpdate", "ExcludeWUDriversInQualityUpdate"),
    r"WindowsUpdate\DisableWUfBSafeguards": ("SOFTWARE", _W + r"\WindowsUpdate", "DisableWUfBSafeguards"),
    r"DriverSearching\SearchOrderConfig": ("SOFTWARE", r"Microsoft\Windows\CurrentVersion\DriverSearching", "SearchOrderConfig"),
    r"Device Metadata\PreventDeviceMetadataFromNetwork": ("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Device Metadata", "PreventDeviceMetadataFromNetwork"),
    r"MRT\DontOfferThroughWUAU": ("SOFTWARE", r"Policies\Microsoft\MRT", "DontOfferThroughWUAU"),
    r"WindowsStore\AutoDownload": ("SOFTWARE", r"Policies\Microsoft\WindowsStore", "AutoDownload"),
}


def _t(tag: str) -> str:
    return tag.split("}")[-1]


def _find(root, *path):
    node = root
    for name in path:
        node = next((c for c in node if _t(c.tag) == name), None)
        if node is None:
            return None
    return node


def _text(node, *path, default=""):
    n = _find(node, *path) if path else node
    return (n.text or "").strip() if n is not None and n.text else default


def _pass(un, name):
    for s in un:
        if _t(s.tag) == "settings" and s.get("pass") == name:
            return s
    return None


def _component(settings, name):
    if settings is None:
        return None
    return next((c for c in settings if _t(c.tag) == "component" and c.get("name", "").endswith(name)), None)


def import_ntlite(path, name: str | None = None) -> tuple[dict, list[str]]:
    """Return (profile, notes). Notes list everything that was not carried over."""
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"{path.name} is not a valid NTLite preset: {exc}") from exc
    if _t(root.tag) != "Preset":
        raise ValueError(f"{path.name} is not an NTLite preset (expected a Preset file)")

    p = default_profile()
    p["name"] = name or path.stem
    p["description"] = f"Imported from the NTLite preset {path.name}"
    notes: list[str] = []

    un = _find(root, "Unattended")
    if un is not None:
        oobe_pass = _pass(un, "oobeSystem")
        intl = _component(oobe_pass, "International-Core")
        if intl is not None:
            p["region"]["input"] = _text(intl, "InputLocale", default=p["region"]["input"])
            p["region"]["locale"] = _text(intl, "UserLocale", default=p["region"]["locale"])
            ui = _text(intl, "UILanguage")
            if ui and ui != p["region"]["locale"]:
                notes.append(f"Display language {ui} was not carried over. WinForge uses the language and format "
                             f"'{p['region']['locale']}' for both. Add the language to the image separately if needed.")
        shell = _component(oobe_pass, "Shell-Setup")
        if shell is not None:
            p["region"]["timezone"] = _text(shell, "TimeZone")
            al = _find(shell, "AutoLogon")
            if al is not None:
                p["account"]["autologon"] = _text(al, "Enabled").lower() == "true"
                p["account"]["name"] = _text(al, "Username")
                p["account"]["password"] = _text(al, "Password", "Value")
            oobe = _find(shell, "OOBE")
            if oobe is not None:
                p["account"]["skip_oobe"] = _text(oobe, "SkipMachineOOBE").lower() == "true"
            acct = _find(shell, "UserAccounts", "LocalAccounts", "LocalAccount")
            if acct is not None:
                p["account"]["name"] = _text(acct, "Name") or p["account"]["name"]
                p["account"]["display_name"] = _text(acct, "DisplayName")
                pw = _text(acct, "Password", "Value")
                if pw:
                    p["account"]["password"] = pw
        spec = _component(_pass(un, "specialize"), "Deployment")
        cmds = []
        if spec is not None:
            for c in sorted(spec.iter(), key=lambda e: 0):
                if _t(c.tag) == "RunSynchronousCommand":
                    cmds.append((int(_text(c, "Order", default="0") or 0), _text(c, "Path")))
        for _, cmd in sorted(cmds):
            if re.match(r"net user administrator /active:yes", cmd, re.I):
                p["account"]["enable_builtin_admin"] = True
            elif re.match(r"net user administrator /fullname:", cmd, re.I):
                continue  # WinForge writes the full name itself from the display name
            elif cmd:
                p["scripts"]["specialize"].append(cmd)

    tweaks = _find(root, "Tweaks")
    if tweaks is not None:
        services = _find(tweaks, "Services")
        for tw in (services.iter() if services is not None else []):
            if _t(tw.tag) == "Tweak":
                svc = tw.get("name", "").split("\\")[0]
                if (tw.text or "").strip() == "4":
                    p["services_disable"].append(svc)
                else:
                    notes.append(f"Service {svc} was set to start type {tw.text}. WinForge only disables services.")
        settings = _find(tweaks, "Settings")
        for tw in (settings.iter() if settings is not None else []):
            if _t(tw.tag) != "Tweak":
                continue
            key, value = tw.get("name", ""), (tw.text or "").strip()
            mapped = KNOWN_TWEAKS.get(key)
            if mapped and value.lstrip("-").isdigit():
                hive, reg_key, val = mapped
                p["registry"].append({"hive": hive, "key": reg_key, "name": val, "type": "REG_DWORD", "data": value})
            else:
                notes.append(f"Tweak '{key}' = {value} has no known registry location. Add it as a .reg file or "
                             "a custom registry entry if you still need it.")
        if (tasks := _find(tweaks, "ScheduledTasks")) is not None:
            for t in tasks.iter():
                if _t(t.tag) in ("Task", "Tweak") and (t.text or "").strip():
                    notes.append(f"Scheduled task '{t.text.strip()}' was not imported. Use Scan image on the Debloat "
                                 "page to pick real task names.")

    regs = _find(root, "Registry")
    for f in (regs if regs is not None else []):
        if _t(f.tag) == "File" and (f.text or "").strip():
            p["reg_files"].append(f.text.strip())

    off = [f.text.strip() for f in root.iter() if _t(f.tag) == "Feature" and f.get("enabled") == "no" and f.text]
    if off:
        notes.append(f"{len(off)} NTLite component groups were switched off ({', '.join(off[:6])}"
                     f"{'…' if len(off) > 6 else ''}). WinForge doesn't use these groups. Pick the matching apps and "
                     "features on the Debloat page.")
    for t in root.iter():
        if _t(t.tag) == "Task" and (t.text or "").startswith("deledition"):
            notes.append("Edition deletions were not carried over. Choose the edition on the Source page.")
            break
    if _find(root, "Drivers") is not None and any(True for _ in _find(root, "Drivers").iter() if _t(_.tag) in ("Driver", "File")):
        notes.append("Drivers listed in the preset were not carried over. Add them on Scripts > Drivers & updates.")
    return normalise(p), notes
