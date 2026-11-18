"""Profile schema: load, validate, save. Pure Python, no Windows dependencies."""
from __future__ import annotations

import json
from pathlib import Path

HIVES = ("SOFTWARE", "SYSTEM", "DEFAULT")
REG_TYPES = ("REG_SZ", "REG_DWORD", "REG_QWORD", "REG_EXPAND_SZ", "REG_MULTI_SZ", "REG_BINARY")
PHASES = ("specialize", "setupcomplete", "firstlogon")


class ProfileError(ValueError):
    """Raised when a profile is malformed."""


def default_profile() -> dict:
    return {
        "name": "custom",
        "edition": "Windows 11 Pro",
        "index": None,
        "options": {"reset_base": False, "compress": True, "oscdimg": ""},
        "remove": {"appx": [], "capabilities": [], "features": []},
        "drivers": [],
        "updates": [],
        "registry": [],
        "services_disable": [],
        "tasks_remove": [],
        "files": [],
        "scripts": {phase: [] for phase in PHASES},
        "account": {"name": "User", "password": "", "autologon": True, "skip_oobe": True},
    }


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def normalise(data: dict) -> dict:
    """Merge user data over the defaults, validate, and return the result."""
    profile = _merge(default_profile(), data)
    validate(profile)
    return profile


def validate(p: dict) -> None:
    if not p["edition"] and p["index"] is None:
        raise ProfileError("set either 'edition' or 'index'")
    if p["index"] is not None and (not isinstance(p["index"], int) or p["index"] < 1):
        raise ProfileError("'index' must be a positive integer")
    for i, r in enumerate(p["registry"]):
        if r.get("hive") not in HIVES:
            raise ProfileError(f"registry[{i}]: hive must be one of {', '.join(HIVES)}")
        if r.get("type") not in REG_TYPES:
            raise ProfileError(f"registry[{i}]: type must be one of {', '.join(REG_TYPES)}")
        if not r.get("key") or not r.get("name"):
            raise ProfileError(f"registry[{i}]: 'key' and 'name' are required")
        r["data"] = str(r.get("data", ""))
    for i, f in enumerate(p["files"]):
        if not f.get("from") or not f.get("to"):
            raise ProfileError(f"files[{i}]: 'from' and 'to' are required")
    unknown = set(p["scripts"]) - set(PHASES)
    if unknown:
        raise ProfileError(f"unknown script phase(s): {', '.join(sorted(unknown))}")
    if p["account"]["autologon"] and not p["account"]["name"]:
        raise ProfileError("autologon needs an account name")


def load_profile(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalise(data)


def save_profile(profile: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
