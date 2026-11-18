"""Built-in presets plus your own, saved as JSON in %APPDATA%\\WinForge\\presets."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import catalog
from .profile import load_profile, normalise, save_profile

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.()-]{0,59}$")


@dataclass(frozen=True)
class PresetInfo:
    name: str
    label: str
    description: str
    builtin: bool


def user_root() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "WinForge" / "presets"


def _check_name(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise ValueError("preset names can use letters, digits, spaces and - _ . ( ) (max 60 characters)")


def list_presets(root: Path | None = None) -> list[PresetInfo]:
    root = root or user_root()
    out = [
        PresetInfo(key, catalog.BUILTIN_LABELS[key], profile["description"], True)
        for key, profile in catalog.builtin_presets().items()
    ]
    if root.exists():
        for path in sorted(root.glob("*.json")):
            try:
                profile = load_profile(path)
            except (ValueError, OSError):
                continue  # skip files that are not valid presets
            out.append(PresetInfo(path.stem, path.stem, profile["description"], False))
    return out


def load_preset(name: str, root: Path | None = None) -> dict:
    builtins = catalog.builtin_presets()
    if name in builtins:
        return builtins[name]
    path = (root or user_root()) / f"{name}.json"
    if not path.exists():
        raise KeyError(f"no preset named '{name}'. Run 'winforge presets list' to see them.")
    return load_profile(path)


def save_preset(name: str, profile: dict, root: Path | None = None) -> Path:
    _check_name(name)
    if name in catalog.builtin_presets():
        raise ValueError(f"'{name}' is a built-in preset name; choose another name")
    profile = normalise(profile)
    profile["name"] = name
    root = root or user_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.json"
    save_profile(profile, path)
    return path


def delete_preset(name: str, root: Path | None = None) -> None:
    if name in catalog.builtin_presets():
        raise ValueError("built-in presets cannot be deleted")
    path = (root or user_root()) / f"{name}.json"
    if not path.exists():
        raise KeyError(f"no preset named '{name}'")
    path.unlink()
