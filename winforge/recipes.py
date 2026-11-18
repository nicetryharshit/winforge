"""Ready-made steps for each stage. A recipe is just a tidy set of command lines with a plain-language title.

Recipes never run on their own: a stage runs its ticked recipes first, then any commands the user typed in
that stage. Add a recipe here and it appears on that stage's page automatically.

Paths assume the files are copied in on the Files page (for example the NVIDIA installer in C:\\Drivers).
"""
from __future__ import annotations

from dataclasses import dataclass

LOG = r"C:\WinForge-setup.log"

# The stages, in the order Windows reaches them. Keys match the profile's script and step names.
STAGES = {
    "specialize": "Before setup finishes",
    "setupcomplete": "After setup, once",
    "firstlogon": "First sign-in",
    "everylogon": "Every sign-in",
    "everyboot": "Every boot",
}


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    phase: str
    note: str
    lines: tuple


RECIPES = (
    Recipe("nvidia_silent", "Install the NVIDIA driver silently", "setupcomplete",
           "Runs C:\\Drivers\\nvidia.exe with /s /quiet. Copy the installer to C:\\Drivers on the Files page first.",
           (f'start /wait "" "%SystemDrive%\\Drivers\\nvidia.exe" /s /quiet >> {LOG} 2>&1',)),
    Recipe("nvidia_services_off", "Remove the NVIDIA background services", "setupcomplete",
           "Stops and deletes the NvContainer and NvTelemetry services the installer leaves behind. "
           "Run it after the NVIDIA installer.",
           tuple(f"sc {verb} {svc} >> {LOG} 2>&1"
                 for svc in ("NvContainerLocalSystem", "NvContainerNetworkService", "NvTelemetryContainer")
                 for verb in ("stop", "delete"))),
    Recipe("install_all_drivers", "Install every driver in C:\\Drivers", "setupcomplete",
           "Adds every .inf file found under C:\\Drivers with pnputil. Copy driver folders there on the Files page.",
           (f'pnputil /add-driver "%SystemDrive%\\Drivers\\*.inf" /subdirs /install >> {LOG} 2>&1',)),
    Recipe("wifi_profile", "Add and connect a saved Wi-Fi network", "setupcomplete",
           "Imports C:\\Drivers\\WifiProfile.xml and asks Windows to connect. Copy the XML to C:\\Drivers first, "
           "and change the name inside the command if it differs.",
           ('netsh wlan add profile filename="C:\\Drivers\\WifiProfile.xml" user=all',)),
    Recipe("refresh_policy", "Apply Group Policy now", "setupcomplete",
           "Runs gpupdate /force so the policies set in this stage apply straight away.",
           (f"gpupdate /force >> {LOG} 2>&1",)),
)

RECIPES_BY_ID = {r.id: r for r in RECIPES}


def for_stage(phase: str) -> list[Recipe]:
    return [r for r in RECIPES if r.phase == phase]
