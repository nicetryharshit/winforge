"""Profile schema: defaults, validation, load and save. No Windows dependencies."""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA = 1
HIVES = ("SOFTWARE", "SYSTEM", "DEFAULT")
REG_TYPES = ("REG_SZ", "REG_DWORD", "REG_QWORD", "REG_EXPAND_SZ", "REG_MULTI_SZ", "REG_BINARY")
PHASES = ("specialize", "setupcomplete", "firstlogon")
APP_MODES = ("task", "run", "shell")

NAME_TOKEN = re.compile(r"^[A-Za-z0-9_.~-]+$")
HIVE_PREFIX = re.compile(r"^HK(LM|CU|EY_)", re.IGNORECASE)


class ProfileError(ValueError):
    """Raised when a profile is malformed. The message is written for humans."""


def default_profile() -> dict:
    return {
        "schema": SCHEMA,
        "name": "custom",
        "description": "",
        "edition": "Windows 11 Pro",
        "index": None,
        "options": {"reset_base": False, "compress": True, "oscdimg": ""},
        "remove": {"appx": [], "capabilities": [], "features": []},
        "drivers": [],
        "updates": [],
        "registry": [],
        "reg_files": [],
        "drivers_boot": [],
        "installers": [],
        "app": {"enabled": False, "name": "", "folder": "", "exe": "", "mode": "task",
                "grant_write": True, "launch_now": False},
        "services_disable": [],
        "tasks_remove": [],
        "files": [],
        "scripts": {phase: [] for phase in PHASES},
        "region": {"timezone": "", "locale": "en-US", "input": "0409:00000409", "geo_id": None},
        "account": {
            "name": "User",
            "display_name": "",
            "password": "",
            "autologon": True,
            "skip_oobe": True,
            "enable_builtin_admin": False,
        },
    }


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def normalise(data: dict) -> dict:
    """Merge user data over the defaults, validate, and return a new dict."""
    if not isinstance(data, dict):
        raise ProfileError("a profile must be a JSON object")
    profile = _merge(default_profile(), data)
    validate(profile)
    return profile


def _check_tokens(section: str, items) -> None:
    for item in items:
        if not isinstance(item, str) or not NAME_TOKEN.match(item):
            raise ProfileError(f"{section}: '{item}' is not a valid name (letters, digits, . _ ~ - only)")


def validate(p: dict) -> None:
    if p["schema"] != SCHEMA:
        raise ProfileError(f"unsupported profile schema {p['schema']}; this WinForge reads schema {SCHEMA}")
    if not str(p["name"]).strip():
        raise ProfileError("the profile needs a name")
    if not p["edition"] and p["index"] is None:
        raise ProfileError("choose an edition (or an index) on the Source page")
    idx = p["index"]
    if idx is not None and (isinstance(idx, bool) or not isinstance(idx, int) or idx < 1):
        raise ProfileError("the image index must be a positive whole number")

    _check_tokens("remove.appx", p["remove"]["appx"])
    _check_tokens("remove.features", p["remove"]["features"])
    _check_tokens("remove.capabilities", p["remove"]["capabilities"])
    _check_tokens("services_disable", p["services_disable"])

    for i, r in enumerate(p["registry"]):
        where = f"registry entry {i + 1}"
        if r.get("hive") not in HIVES:
            raise ProfileError(f"{where}: hive must be one of {', '.join(HIVES)}")
        if r.get("type") not in REG_TYPES:
            raise ProfileError(f"{where}: type must be one of {', '.join(REG_TYPES)}")
        key = str(r.get("key", "")).strip()
        if not key or HIVE_PREFIX.match(key):
            raise ProfileError(f"{where}: the key must be a path inside the hive, e.g. Policies\\Microsoft")
        r["key"] = key
        r["name"] = str(r.get("name", ""))  # empty name means the key's default value
        r["data"] = str(r.get("data", ""))
        if r["type"] in ("REG_DWORD", "REG_QWORD"):
            try:
                int(r["data"], 0)
            except ValueError:
                raise ProfileError(f"{where}: {r['type']} needs a number, e.g. 0 or 0x1") from None

    for i, path in enumerate(p["reg_files"]):
        if not isinstance(path, str) or not path.strip():
            raise ProfileError(f".reg file entry {i + 1} is empty")

    for i, f in enumerate(p["files"]):
        if not f.get("from") or not f.get("to"):
            raise ProfileError(f"file entry {i + 1}: both 'from' and 'to' are required")

    for i, item in enumerate(p["drivers_boot"]):
        if not isinstance(item, str) or not item.strip():
            raise ProfileError(f"first-boot driver folder {i + 1} is empty")
    for i, inst in enumerate(p["installers"]):
        if not isinstance(inst, dict) or not str(inst.get("file", "")).strip():
            raise ProfileError(f"first-boot installer {i + 1} needs a file")
        inst["args"] = str(inst.get("args", ""))

    app = p["app"]
    if app["enabled"]:
        if not NAME_TOKEN.match(str(app["name"])):
            raise ProfileError("the app needs a short name (letters, digits, . _ - only) on the App page")
        if not str(app["folder"]).strip():
            raise ProfileError("choose the app's folder on the App page")
        if not str(app["exe"]).strip():
            raise ProfileError("choose the app's .exe on the App page")
        if app["mode"] not in APP_MODES:
            raise ProfileError(f"app mode must be one of {', '.join(APP_MODES)}")

    unknown = set(p["scripts"]) - set(PHASES)
    if unknown:
        raise ProfileError(f"unknown script section(s): {', '.join(sorted(unknown))}")

    account = p["account"]
    if account["autologon"] and not str(account["name"]).strip():
        raise ProfileError("autologon needs an account name")
    if account["enable_builtin_admin"] and not str(account["name"]).strip():
        raise ProfileError("the account name is needed to set up the built-in Administrator")

    region = p["region"]
    for key in ("timezone", "locale", "input"):
        if not isinstance(region[key], str):
            raise ProfileError(f"region.{key} must be text")
    geo = region["geo_id"]
    if geo is not None and (isinstance(geo, bool) or not isinstance(geo, int) or geo < 1):
        raise ProfileError("region.geo_id must be a positive number (for example 244 for the United States)")


def load_profile(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalise(data)


def save_profile(profile: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
