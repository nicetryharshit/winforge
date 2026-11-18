"""Curated lists of what WinForge can remove, disable or tweak, plus the built-in presets.

Names must match what DISM, PowerShell and the registry expect. If an item is
not in a particular image, Windows skips it and the build carries on.
"""
from __future__ import annotations

from dataclasses import dataclass

from .profile import default_profile, normalise


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    group: str
    note: str = ""
    recommended: bool = False


@dataclass(frozen=True)
class Tweak:
    id: str
    label: str
    group: str
    note: str
    recommended: bool
    entries: tuple  # tuples of (hive, key, name, type, data)


def _e(hive: str, key: str, name: str, reg_type: str, data: str) -> dict:
    return {"hive": hive, "key": key, "name": name, "type": reg_type, "data": data}


APPS = (
    Item("Microsoft.BingNews", "News", "Consumer", "Microsoft News app", True),
    Item("Microsoft.BingWeather", "Weather", "Consumer", "Weather app", True),
    Item("Microsoft.GetHelp", "Get Help", "Consumer", "Support app", True),
    Item("Microsoft.Getstarted", "Tips", "Consumer", "Tips app", True),
    Item("Microsoft.MicrosoftOfficeHub", "Office promotion", "Consumer", "Office ads", True),
    Item("Microsoft.MicrosoftSolitaireCollection", "Solitaire Collection", "Games", "Preinstalled games", True),
    Item("Microsoft.ZuneVideo", "Movies & TV", "Media", "Video app", True),
    Item("Microsoft.ZuneMusic", "Media Player (new)", "Media", "New music app, separate from legacy Windows Media Player", True),
    Item("Microsoft.WindowsFeedbackHub", "Feedback Hub", "System", "", True),
    Item("Microsoft.549981C3F5F10", "Cortana", "System", "Assistant app", True),
    Item("Microsoft.Clipchamp", "Clipchamp", "Media", "Video editor", False),
    Item("Microsoft.People", "People", "Consumer", "", False),
    Item("Microsoft.Todos", "Microsoft To Do", "Productivity", "", False),
    Item("Microsoft.WindowsMaps", "Maps", "Consumer", "", False),
    Item("Microsoft.YourPhone", "Phone Link", "Consumer", "Breaks phone linking if removed", False),
)

FEATURES = (
    Item("SMB1Protocol", "SMBv1 protocol", "Security", "Legacy and insecure. Off is the safer choice", True),
    Item("MediaPlayback", "Media Feature Pack", "Legacy media", "Some media apps depend on it", False),
    Item("WindowsMediaPlayer", "Windows Media Player (legacy)", "Legacy media", "", False),
    Item("Printing-XPSServices-Features", "XPS services", "Legacy", "", False),
    Item("WorkFolders-Client", "Work Folders client", "Legacy", "", False),
    Item("TelnetClient", "Telnet client", "Legacy", "", False),
)

CAPABILITIES = (
    Item("App.StepsRecorder~~~~0.0.1.0", "Steps Recorder", "Legacy", "", False),
    Item("Media.WindowsMediaPlayer~~~~0.0.12.0", "Windows Media Player capability", "Legacy media", "", False),
)

SERVICES = (
    Item("DiagTrack", "Connected User Experiences and Telemetry", "Telemetry", "Main telemetry service", True),
    Item("dmwappushservice", "WAP push message routing", "Telemetry", "", True),
    Item("RetailDemo", "Retail demo", "Telemetry", "Only needed on store display units", True),
    Item("RemoteRegistry", "Remote registry", "Security", "Lets other computers edit this registry", True),
    Item("MapsBroker", "Downloaded maps manager", "Optional", "", False),
    Item("lfsvc", "Geolocation", "Optional", "", False),
    Item("Fax", "Fax", "Optional", "", False),
)

TWEAKS = (
    Tweak("telemetry", "Basic diagnostic data only", "Privacy",
          "Telemetry policy set to Basic, the lowest level on Home and Pro", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", "REG_DWORD", "1"),)),
    Tweak("advertising_id", "Turn off advertising ID", "Privacy", "", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\AdvertisingInfo", "DisabledByGroupPolicy", "REG_DWORD", "1"),)),
    Tweak("consumer_features", "Stop automatic app suggestions", "Privacy",
          "Stops Windows installing suggested apps for users", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", "REG_DWORD", "1"),)),
    Tweak("sponsored_apps", "No sponsored content for new users", "Privacy",
          "Applies to the Default user profile, so only new accounts are affected", True,
          (
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SilentInstalledAppsEnabled", "REG_DWORD", "0"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SystemPaneSuggestionsEnabled", "REG_DWORD", "0"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SoftLandingEnabled", "REG_DWORD", "0"),
          )),
    Tweak("long_paths", "Enable long file paths", "System",
          "Allows file paths longer than 260 characters", True,
          (_e("SYSTEM", r"ControlSet001\Control\FileSystem", "LongPathsEnabled", "REG_DWORD", "1"),)),
    Tweak("classic_menu", "Classic right-click menu (Windows 11)", "Look",
          "Applies to the Default user profile, so only new accounts are affected", False,
          (_e("DEFAULT", r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32",
              "", "REG_SZ", ""),)),
    Tweak("search_web_off", "No web results in Start search", "Privacy", "", False,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", "REG_DWORD", "1"),)),
)

BUILTIN_LABELS = {
    "lean": "Lean (recommended)",
    "everything": "Everything (aggressive)",
    "blank": "Blank",
}


def make_profile(name: str, description: str, *, apps=(), features=(), capabilities=(),
                 services=(), tweaks=()) -> dict:
    """Build a normalised profile from catalog ids."""
    tweak_map = {t.id: t for t in TWEAKS}
    registry = []
    for tid in tweaks:
        registry.extend(dict(entry) for entry in tweak_map[tid].entries)
    profile = default_profile()
    profile.update(
        name=name,
        description=description,
        remove={"appx": list(apps), "features": list(features), "capabilities": list(capabilities)},
        services_disable=list(services),
        registry=registry,
    )
    return normalise(profile)


def builtin_presets() -> dict[str, dict]:
    """Fresh copies of the built-in presets on every call."""
    rec = lambda items: [i.id for i in items if i.recommended]  # noqa: E731
    return {
        "lean": make_profile(
            "lean",
            "Removes the bundled apps, telemetry and sponsored content. Keeps the Store, "
            "Defender and Windows Update.",
            apps=rec(APPS), features=rec(FEATURES), services=rec(SERVICES),
            tweaks=[t.id for t in TWEAKS if t.recommended],
        ),
        "everything": make_profile(
            "everything",
            "Everything in the catalog. Expect some breakage, so test it in a VM first.",
            apps=[i.id for i in APPS], features=[i.id for i in FEATURES],
            capabilities=[i.id for i in CAPABILITIES], services=[i.id for i in SERVICES],
            tweaks=[t.id for t in TWEAKS],
        ),
        "blank": make_profile("blank", "No changes. A starting point for your own profile."),
    }
