"""Build pipeline: Windows ISO or extracted folder -> mounted WIM -> customisations -> ISO.

Needs Windows (DISM, reg.exe, oscdimg, PowerShell). With dry_run=True every
command is printed instead of executed, so the plan can be checked anywhere.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .profile import load_profile
from .unattend import build_setupcomplete, build_unattend

OSCDIMG_DEFAULT = (
    r"C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit"
    r"\Deployment Tools\amd64\Oscdimg\oscdimg.exe"
)

HIVE_FILES = {
    "SOFTWARE": r"Windows\System32\config\SOFTWARE",
    "SYSTEM": r"Windows\System32\config\SYSTEM",
    "DEFAULT": r"Users\Default\NTUSER.DAT",
}


class BuildError(RuntimeError):
    pass


def ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class Runner:
    def __init__(self, dry_run: bool, log: Callable[[str], None]):
        self.dry_run = dry_run
        self.log = log

    def run(self, args: list, check: bool = True) -> str:
        args = [str(a) for a in args]
        self.log("$ " + subprocess.list2cmdline(args))
        if self.dry_run:
            return ""
        result = subprocess.run(args, capture_output=True, text=True, errors="replace")
        output = (result.stdout + result.stderr).strip()
        if output:
            self.log(output)
        if check and result.returncode != 0:
            raise BuildError(f"{args[0]} exited with code {result.returncode}")
        return output

    def ps(self, script: str) -> str:
        return self.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])


def find_index(runner: Runner, wim: Path, edition: str, fallback: int | None) -> int:
    """An explicit index wins. Otherwise look the edition up in DISM's output (English output expected)."""
    if fallback:
        return fallback
    if runner.dry_run:
        return 1
    output = runner.run(["dism.exe", "/Get-WimInfo", f"/WimFile:{wim}"])
    current = None
    for line in output.splitlines():
        if m := re.match(r"\s*Index\s*:\s*(\d+)", line):
            current = int(m.group(1))
        elif m := re.match(r"\s*Name\s*:\s*(.+?)\s*$", line):
            if current is not None and m.group(1).lower() == edition.lower():
                return current
    raise BuildError(f"edition '{edition}' not found in {wim.name}; set 'index' in the profile")


def apply_registry(R: Runner, p: dict, mount: Path) -> None:
    needed = {r["hive"] for r in p["registry"]}
    if p["services_disable"]:
        needed.add("SYSTEM")
    loaded: list[str] = []
    try:
        for hive in sorted(needed):
            R.run(["reg.exe", "load", f"HKLM\\WF_{hive}", str(mount / HIVE_FILES[hive])])
            loaded.append(hive)
        for r in p["registry"]:
            R.run(["reg.exe", "add", f"HKLM\\WF_{r['hive']}\\{r['key']}", "/v", r["name"],
                   "/t", r["type"], "/d", r["data"], "/f"])
        for svc in p["services_disable"]:
            R.run(["reg.exe", "add", f"HKLM\\WF_SYSTEM\\ControlSet001\\Services\\{svc}",
                   "/v", "Start", "/t", "REG_DWORD", "/d", "4", "/f"], check=False)
    finally:
        for hive in reversed(loaded):
            R.run(["reg.exe", "unload", f"HKLM\\WF_{hive}"], check=False)


def customise(R: Runner, p: dict, base: Path, mount: Path, src: Path) -> None:
    m = str(mount)
    rm = p["remove"]

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
    for d in p["drivers"]:
        R.run(["dism.exe", f"/Image:{m}", "/Add-Driver", f"/Driver:{base / d}", "/Recurse"])
    for u in p["updates"]:
        R.run(["dism.exe", f"/Image:{m}", "/Add-Package", f"/PackagePath:{base / u}"])

    apply_registry(R, p, mount)

    for rel in p["tasks_remove"]:
        target = mount / "Windows" / "System32" / "Tasks" / rel
        R.log(f"remove scheduled task {target}")
        if not R.dry_run and target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

    for entry in p["files"]:
        dst = mount / entry["to"]
        srcf = base / entry["from"]
        R.log(f"copy {srcf} -> {dst}")
        if not R.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if srcf.is_dir():
                shutil.copytree(srcf, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(srcf, dst)

    setup = build_setupcomplete(p)
    if setup:
        target = mount / "Windows" / "Setup" / "Scripts" / "SetupComplete.cmd"
        R.log(f"write {target}")
        if not R.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(setup.encode("utf-8"))

    unattend = src / "autounattend.xml"
    R.log(f"write {unattend}")
    if not R.dry_run:
        unattend.write_text(build_unattend(p), encoding="utf-8")

    R.run(["dism.exe", f"/Image:{m}", "/Cleanup-Image", "/StartComponentCleanup"]
          + (["/ResetBase"] if p["options"]["reset_base"] else []))


def build(profile_path, source, work, out, oscdimg: str | None = None,
          dry_run: bool = False, log: Callable[[str], None] = print) -> None:
    profile_path = Path(profile_path).resolve()
    base = profile_path.parent
    p = load_profile(profile_path)
    R = Runner(dry_run, log)
    source, work, out = Path(source), Path(work), Path(out)
    src = work / "src"
    mount = work / "mount"
    wim = src / "sources" / "install.wim"
    esd = src / "sources" / "install.esd"
    oscdimg = oscdimg or p["options"]["oscdimg"] or OSCDIMG_DEFAULT

    log("== 0. Clear stale mount points")
    R.run(["dism.exe", "/Cleanup-Wim"], check=False)

    log("== 1. Stage source")
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
        log(f"copy {source} -> {src}")
        if not dry_run:
            shutil.copytree(source, src, dirs_exist_ok=True)
    if not dry_run:
        work.mkdir(parents=True, exist_ok=True)
        mount.mkdir(parents=True, exist_ok=True)

    if esd.exists() and not wim.exists():
        log("== 2. Convert install.esd to install.wim")
        idx = find_index(R, esd, p["edition"], p["index"])
        R.run(["dism.exe", "/Export-Image", f"/SourceImageFile:{esd}", f"/SourceIndex:{idx}",
               f"/DestinationImageFile:{wim}", "/Compress:max"])
        if not dry_run:
            esd.unlink()
    if not dry_run and not wim.exists():
        raise BuildError("source has no sources\\install.wim or install.esd")
    R.run(["attrib.exe", "-r", str(wim)])

    idx = find_index(R, wim, p["edition"], p["index"])
    log(f"== 3. Mount index {idx}")
    R.run(["dism.exe", "/Mount-Image", f"/ImageFile:{wim}", f"/Index:{idx}", f"/MountDir:{mount}"])
    try:
        log("== 4. Customise")
        customise(R, p, base, mount, src)
        log("== 5. Commit and unmount")
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Commit"])
    except Exception:
        log("== Error: discarding changes and unmounting")
        R.run(["dism.exe", "/Unmount-Image", f"/MountDir:{mount}", "/Discard"], check=False)
        raise

    if p["options"]["compress"]:
        log("== 6. Re-export WIM to drop unused data")
        tmp = src / "sources" / "install.wim.new"
        R.run(["dism.exe", "/Export-Image", f"/SourceImageFile:{wim}", f"/SourceIndex:{idx}",
               f"/DestinationImageFile:{tmp}", "/Compress:max"])
        if not dry_run:
            tmp.replace(wim)

    log("== 7. Build ISO")
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
    etfs = src / "boot" / "etfsboot.com"
    efisys = src / "efi" / "microsoft" / "boot" / "efisys.bin"
    R.run([oscdimg, "-m", "-o", "-u2", "-udfver102",
           f"-bootdata:2#p0,e,b{etfs}#pEF,e,b{efisys}", src, out])
    if dry_run:
        log("Dry run complete. Nothing was executed and no ISO was created.")
        log("Run again without --dry-run (as Administrator) to build the ISO.")
    else:
        log(f"Done: {out}")
