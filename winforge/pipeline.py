"""Build pipeline: Windows ISO or folder -> mounted WIM -> customisations -> ISO.

Needs Windows (DISM, reg.exe, oscdimg, PowerShell) for a real build. With
dry_run=True every command is printed instead of run, so the plan can be
checked on any OS.

Stages are logged as lines starting with "== " so the GUI can show progress.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Callable

from .editions import find_edition, parse_wim_info
from .profile import save_profile
from .regfile import load_reg_files
from .unattend import build_setupcomplete, build_unattend
from .util import is_admin, is_windows, ps_quote

OSCDIMG_DEFAULT = (
    r"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit"
    r"\Deployment Tools\amd64\Oscdimg\oscdimg.exe"
)

HIVE_FILES = {
    "SOFTWARE": r"Windows\System32\config\SOFTWARE",
    "SYSTEM": r"Windows\System32\config\SYSTEM",
    "DEFAULT": r"Users\Default\NTUSER.DAT",
}

GB = 1024 ** 3


class BuildError(RuntimeError):
    pass


class Runner:
    """Runs external commands, streams their output to the log, and honours dry runs."""

    def __init__(self, dry_run: bool, log: Callable[[str], None]):
        self.dry_run = dry_run
        self.log = log
        self._last_pct: int | None = None

    def _emit_line(self, line: str) -> None:
        # DISM redraws a progress bar with carriage returns. Only log each whole-percent step.
        m = re.search(r"(\d+(?:\.\d+)?)%", line)
        if m and line.lstrip().startswith("["):
            pct = int(float(m.group(1)))
            if pct == self._last_pct and pct != 100:
                return
            self._last_pct = pct
        self.log(line)

    def run(self, args: list, check: bool = True) -> str:
        args = [str(a) for a in args]
        self.log("$ " + subprocess.list2cmdline(args))
        if self.dry_run:
            return ""
        self._last_pct = None
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace")
        captured: list[str] = []
        buf = ""
        while True:
            ch = proc.stdout.read(1)
            if ch == "":
                break
            if ch in "\r\n":
                if buf.strip():
                    self._emit_line(buf.rstrip())
                    captured.append(buf.rstrip())
                buf = ""
            else:
                buf += ch
        if buf.strip():
            self._emit_line(buf.rstrip())
            captured.append(buf.rstrip())
        code = proc.wait()
        if check and code != 0:
            raise BuildError(f"{args[0]} failed with exit code {code}")
        return "\n".join(captured)

    def ps(self, script: str) -> str:
        return self.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


def _existing_parent(path: Path) -> Path:
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def _size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def preflight(profile: dict, base: Path, source: Path, work: Path, out: Path,
              oscdimg: str, dry_run: bool) -> tuple[list[str], list[str]]:
    """Check everything that can be checked before touching the image. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    if not dry_run:
        if not is_windows():
            errors.append("a real build needs Windows (DISM, reg.exe, oscdimg). Use --dry-run on this system.")
        else:
            if not is_admin():
                errors.append("run this from an Administrator PowerShell (right-click it and choose Run as administrator)")
            if not Path(oscdimg).exists():
                errors.append(f"oscdimg.exe not found at {oscdimg}. Install the Windows ADK 'Deployment Tools' "
                              "or pass the correct path with --oscdimg")

    if not source.exists():
        (warnings if dry_run else errors).append(f"source not found: {source}")

    for d in profile["drivers"]:
        if not (base / d).exists():
            errors.append(f"driver folder not found: {base / d}")
    for u in profile["updates"]:
        if not (base / u).exists():
            errors.append(f"update package not found: {base / u}")
    for f in profile["files"]:
        if not (base / f["from"]).exists():
            errors.append(f"file to copy not found: {base / f['from']}")
    for r in profile["reg_files"]:
        if not (base / r).exists():
            errors.append(f".reg file not found: {base / r}")
    _, reg_warnings = load_reg_files(base, profile["reg_files"])
    warnings.extend(reg_warnings)

    if not dry_run and source.exists():
        # Rough need: the extracted source, the mounted image, and the rebuilt ISO. Folders are not measured.
        need = (_size(source) * 3 if source.is_file() else 25 * GB) + 10 * GB
        free = shutil.disk_usage(_existing_parent(work)).free
        if free < need:
            errors.append(f"not enough free space for the work folder: about {need // GB} GB needed, "
                          f"{free // GB} GB free on that drive")

    if out.exists():
        warnings.append(f"{out} already exists and will be replaced")
    return errors, warnings


def _force_writable(func, path, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _resolve_index(R: Runner, image: Path, profile: dict, dry_run: bool) -> int:
    if profile["index"]:
        return profile["index"]
    if dry_run:
        return 1
    editions = parse_wim_info(R.run(["dism.exe", "/Get-WimInfo", f"/WimFile:{image}"]))
    return find_edition(editions, name=profile["edition"]).index


def _reg_value_args(name: str) -> list[str]:
    return ["/ve"] if name in ("", "(Default)") else ["/v", name]


def apply_registry(R: Runner, profile: dict, mount: Path, entries: list[dict]) -> None:
    needed = {r["hive"] for r in entries}
    if profile["services_disable"]:
        needed.add("SYSTEM")
    loaded: list[str] = []
    try:
        for hive in sorted(needed):
            R.run(["reg.exe", "load", f"HKLM\\WF_{hive}", str(mount / HIVE_FILES[hive])])
            loaded.append(hive)
        for r in entries:
            R.run(["reg.exe", "add", f"HKLM\\WF_{r['hive']}\\{r['key']}", *_reg_value_args(r["name"]),
                   "/t", r["type"], "/d", r["data"], "/f"])
        for svc in profile["services_disable"]:
            R.run(["reg.exe", "add", f"HKLM\\WF_SYSTEM\\ControlSet001\\Services\\{svc}",
                   "/v", "Start", "/t", "REG_DWORD", "/d", "4", "/f"], check=False)
    finally:
        for hive in reversed(loaded):
            R.run(["reg.exe", "unload", f"HKLM\\WF_{hive}"], check=False)


def customise(R: Runner, profile: dict, base: Path, mount: Path, src: Path) -> None:
    m = str(mount)
    rm = profile["remove"]

    if rm["appx"]:
        names = ",".join(ps_quote(n) for n in rm["appx"])
        R.ps(
            f"Get-AppxProvisionedPackage -Path {ps_quote(m)} | "
            f"Where-Object {{ @({names}) -contains $_.DisplayName }} | "
            f"ForEach-Object {{ Remove-AppxProvisionedPackage -Path {ps_quote(m)} "
            f"-PackageName $_.PackageName | Out-Null }}"
        )
    for name in rm["capabilities"]:
        R.run(["dism.exe", f"/Image:{m}", "/Remove-Capability", f"/CapabilityName:{name}"], check=False)
    for name in rm["features"]:
        R.run(["dism.exe", f"/Image:{m}", "/Disable-Feature", f"/FeatureName:{name}", "/Remove"], check=False)
    for d in profile["drivers"]:
        R.run(["dism.exe", f"/Image:{m}", "/Add-Driver", f"/Driver:{base / d}", "/Recurse"])
    for u in profile["updates"]:
        R.run(["dism.exe", f"/Image:{m}", "/Add-Package", f"/PackagePath:{base / u}"])

    reg_entries, reg_warnings = load_reg_files(base, profile["reg_files"])
    for note in reg_warnings:
        R.log(f"WARNING: {note}")
    apply_registry(R, profile, mount, list(profile["registry"]) + reg_entries)

    for rel in profile["tasks_remove"]:
        target = mount / "Windows" / "System32" / "Tasks" / rel
        R.log(f"remove scheduled task {target}")
        if not R.dry_run and target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

    for entry in profile["files"]:
        dst = mount / entry["to"]
        src_file = base / entry["from"]
        R.log(f"copy {src_file} -> {dst}")
        if not R.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src_file.is_dir():
                shutil.copytree(src_file, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src_file, dst)

    setup = build_setupcomplete(profile)
    if setup:
        target = mount / "Windows" / "Setup" / "Scripts" / "SetupComplete.cmd"
        R.log(f"write {target}")
        if not R.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(setup.encode("utf-8"))

    unattend = src / "autounattend.xml"
    R.log(f"write {unattend}")
    if not R.dry_run:
        unattend.write_text(build_unattend(profile), encoding="utf-8")

    R.run(["dism.exe", f"/Image:{m}", "/Cleanup-Image", "/StartComponentCleanup"]
          + (["/ResetBase"] if profile["options"]["reset_base"] else []))


def _steps(profile: dict, base: Path, source: Path, work: Path, out: Path,
           oscdimg: str, R: Runner, dry_run: bool) -> None:
    emit = R.log
    src = work / "src"
    mount = work / "mount"
    wim = src / "sources" / "install.wim"
    esd = src / "sources" / "install.esd"

    emit("== 0. Clear stale mount points")
    R.run(["dism.exe", "/Cleanup-Wim"], check=False)

    emit("== 1. Stage source")
    if not dry_run and src.exists():
        shutil.rmtree(src, onerror=_force_writable)
    if source.suffix.lower() == ".iso":
        iso = ps_quote(source)
        R.ps(
            f"$img = Mount-DiskImage -ImagePath {iso} -PassThru; "
            "$drv = ($img | Get-Volume).DriveLetter; "
            f"robocopy ($drv + ':\\') {ps_quote(src)} /E /R:1 /W:1 | Out-Null; "
            "$rc = $LASTEXITCODE; "
            f"Dismount-DiskImage -ImagePath {iso} | Out-Null; "
            "if ($rc -ge 8) { throw 'robocopy failed' }"
        )
    else:
        emit(f"copy {source} -> {src}")
        if not dry_run:
            shutil.copytree(source, src)
    if not dry_run:
        mount.mkdir(parents=True, exist_ok=True)

    if esd.exists() and not wim.exists():
        emit("== 2. Convert install.esd to install.wim")
        idx = _resolve_index(R, esd, profile, dry_run)
        R.run(["dism.exe", "/Export-Image", f"/SourceImageFile:{esd}", f"/SourceIndex:{idx}",
               f"/DestinationImageFile:{wim}", "/Compress:max"])
        if not dry_run:
            esd.unlink()
    if not dry_run and not wim.exists():
        raise BuildError("the source has neither sources\\install.wim nor sources\\install.esd")
    R.run(["attrib.exe", "-r", str(wim)])

    idx = _resolve_index(R, wim, profile, dry_run)
    emit(f"== 3. Mount image index {idx}")
    R.run(["dism.exe", "/Mount-Image", f"/ImageFile:{wim}", f"/Index:{idx}", f"/MountDir:{mount}"])
    try:
        emit("== 4. Customise")
        customise(R, profile, base, mount, src)
        emit("== 5. Commit and unmount")
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Commit"])
    except BaseException:
        emit("== Error: discarding changes and unmounting")
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Discard"], check=False)
        raise

    # Always re-export the chosen edition alone. This drops the other editions from the ISO,
    # and it makes the chosen edition index 1, which the generated autounattend.xml relies on.
    emit("== 6. Keep only the chosen edition and re-export")
    tmp = src / "sources" / "install.wim.new"
    compression = "max" if profile["options"]["compress"] else "fast"
    R.run(["dism.exe", "/Export-Image", f"/SourceImageFile:{wim}", f"/SourceIndex:{idx}",
           f"/DestinationImageFile:{tmp}", f"/Compress:{compression}"])
    if not dry_run:
        tmp.replace(wim)

    emit("== 7. Build ISO")
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        save_profile(profile, out.with_suffix(".profile.json"))
    etfs = src / "boot" / "etfsboot.com"
    efisys = src / "efi" / "microsoft" / "boot" / "efisys.bin"
    R.run([oscdimg, "-m", "-o", "-u2", "-udfver102",
           f"-bootdata:2#p0,e,b{etfs}#pEF,e,b{efisys}", src, out])


def build(profile: dict, base, source, work, out, oscdimg: str | None = None,
          dry_run: bool = False, log: Callable[[str], None] = print) -> None:
    """Build an ISO from a normalised profile. `base` is the folder that relative paths start from."""
    base, source, work, out = Path(base), Path(source), Path(work), Path(out)
    oscdimg = oscdimg or profile["options"]["oscdimg"] or OSCDIMG_DEFAULT

    errors, warnings = preflight(profile, base, source, work, out, oscdimg, dry_run)
    for w in warnings:
        log(f"WARNING: {w}")
    if errors:
        for e in errors:
            log(f"ERROR: {e}")
        raise BuildError(f"{len(errors)} problem(s) found. Nothing was changed.")

    logfile = None
    if not dry_run:
        logs = work / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        logfile = (logs / f"build-{dt.datetime.now():%Y%m%d-%H%M%S}.log").open("w", encoding="utf-8")

    def emit(msg: str) -> None:
        log(msg)
        if logfile:
            logfile.write(msg + "\n")
            logfile.flush()

    try:
        emit(f"WinForge build '{profile['name']}' ({'dry run' if dry_run else 'real build'})")
        R = Runner(dry_run, emit)
        _steps(profile, base, source, work, out, oscdimg, R, dry_run)
        if dry_run:
            emit("Dry run complete. Nothing was executed and no ISO was created.")
        else:
            emit(f"Done: {out}")
    finally:
        if logfile:
            logfile.close()


def cleanup(work, log: Callable[[str], None] = print, dry_run: bool = False) -> None:
    """Discard any image left mounted by an interrupted build, and clear stale mount points."""
    work = Path(work)
    R = Runner(dry_run, log)
    mount = work / "mount"
    if mount.exists():
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Discard"], check=False)
    R.run(["dism.exe", "/Cleanup-Wim"], check=False)
    log("Cleanup finished.")
