"""Read .reg files (as exported by Regedit) into WinForge registry entries.

Only HKEY_LOCAL_MACHINE\\SOFTWARE, HKEY_LOCAL_MACHINE\\SYSTEM and HKEY_CURRENT_USER can be
applied to an offline image, so anything else is skipped and reported as a warning.
Key deletions ("-" values and [-Key] headers) are skipped too. No Windows dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path

HIVE_MAP = {
    "HKEY_LOCAL_MACHINE\\SOFTWARE": "SOFTWARE",
    "HKEY_LOCAL_MACHINE\\SYSTEM": "SYSTEM",
    "HKEY_CURRENT_USER": "DEFAULT",  # the offline Default user profile, which new accounts copy
}

VALUE_LINE = re.compile(r'^("(?:[^"\\]|\\.)*"|@)=(.*)$')


def _unquote(text: str) -> str:
    """Undo .reg escaping: \\\\ becomes \\ and \\" becomes "."""
    return re.sub(r"\\(.)", r"\1", text)


def _join_continuations(lines: list[str]) -> list[str]:
    """Regedit wraps long hex values with a trailing backslash. Join those back together."""
    out: list[str] = []
    pending = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        out.append((pending + line.lstrip()) if pending else line)
        pending = ""
    if pending:
        out.append(pending)
    return out


def _map_key(header: str) -> tuple[str | None, str]:
    for prefix, hive in HIVE_MAP.items():
        if header == prefix or header.startswith(prefix + "\\"):
            return hive, header[len(prefix):].lstrip("\\")
    return None, ""


def _hex_bytes(text: str) -> bytes:
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return bytes(int(p, 16) for p in parts)


def _value(text: str) -> tuple[str, str]:
    """Return (registry type, data for reg.exe). Raises ValueError for anything unsupported."""
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return "REG_SZ", _unquote(text[1:-1])
    if text.startswith("dword:"):
        return "REG_DWORD", str(int(text[len("dword:"):], 16))
    if text.startswith("hex(4):"):
        return "REG_DWORD", str(int.from_bytes(_hex_bytes(text[len("hex(4):"):]), "little"))
    if text.startswith("hex(b):"):
        return "REG_QWORD", str(int.from_bytes(_hex_bytes(text[len("hex(b):"):]), "little"))
    if text.startswith("hex(2):"):
        raw = _hex_bytes(text[len("hex(2):"):])
        return "REG_EXPAND_SZ", raw.decode("utf-16-le", errors="replace").rstrip("\x00")
    if text.startswith("hex:"):
        return "REG_BINARY", "".join(f"{b:02x}" for b in _hex_bytes(text[len("hex:"):]))
    raise ValueError("this value type is not supported")


def parse_reg_text(text: str, source: str = "reg file") -> tuple[list[dict], list[str]]:
    """Parse .reg text. Returns (entries, warnings). Entries match profile['registry'] items."""
    entries: list[dict] = []
    warnings: list[str] = []
    lines = _join_continuations(text.splitlines())
    current: tuple[str, str] | None = None  # (hive, key) for the section being read

    if lines and not any(lines[0].strip().lower().startswith(h) for h in ("windows registry editor", "regedit4")):
        warnings.append(f"{source} does not start with a Regedit header; reading it anyway")

    for number, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith(";") or s.lower().startswith(("windows registry editor", "regedit4")):
            continue

        if s.startswith("["):
            header = s[1:-1] if s.endswith("]") else s[1:]
            if header.startswith("-"):
                warnings.append(f"line {number}: deleting a key ({header[1:]}) is not supported and was skipped")
                current = None
                continue
            hive, rel = _map_key(header)
            if hive is None:
                warnings.append(f"line {number}: {header} is outside SOFTWARE, SYSTEM and HKCU; skipped")
                current = None
            elif not rel:
                warnings.append(f"line {number}: a key with no path ({header}) was skipped")
                current = None
            else:
                current = (hive, rel)
            continue

        if current is None:
            continue

        match = VALUE_LINE.match(s)
        if not match:
            warnings.append(f"line {number}: could not read '{s[:50]}'")
            continue
        name = "" if match.group(1) == "@" else _unquote(match.group(1)[1:-1])
        value = match.group(2).strip()
        if value == "-":
            warnings.append(f"line {number}: deleting the value '{name}' is not supported and was skipped")
            continue
        try:
            reg_type, data = _value(value)
        except ValueError as exc:
            warnings.append(f"line {number}: value '{name}': {exc}; skipped")
            continue
        entries.append({"hive": current[0], "key": current[1], "name": name, "type": reg_type, "data": data})

    return entries, warnings


def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def read_reg_file(path: Path) -> tuple[list[dict], list[str]]:
    return parse_reg_text(_decode(Path(path).read_bytes()), str(path))


def load_reg_files(base: Path, rel_paths) -> tuple[list[dict], list[str]]:
    """Parse every .reg file listed in a profile. Missing files are reported by the preflight, not here."""
    entries: list[dict] = []
    warnings: list[str] = []
    for rel in rel_paths:
        path = Path(base) / rel
        if not path.exists():
            continue
        found, notes = read_reg_file(path)
        entries.extend(found)
        warnings.extend(f"{rel}: {note}" for note in notes)
    return entries, warnings
