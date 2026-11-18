"""Curated lists of what WinForge can remove, disable or tweak, plus the built-in presets.

Names must match what DISM, PowerShell and the registry expect. If an item is
not in a particular image, Windows skips it and the build carries on.

Every note is written for someone who has never opened the registry: what the
change does, and what it costs you.
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
    Item("Microsoft.BingNews", "News", "Consumer", "Microsoft News app. Safe to remove.", True),
    Item("Microsoft.BingWeather", "Weather", "Consumer", "Weather app. Safe to remove.", True),
    Item("Microsoft.GetHelp", "Get Help", "Consumer", "Support app. Safe to remove.", True),
    Item("Microsoft.Getstarted", "Tips", "Consumer", "Tips and tutorials app. Safe to remove.", True),
    Item("Microsoft.MicrosoftOfficeHub", "Office promotion", "Consumer",
         "Shortcut app that advertises Office. It does not install Office.", True),
    Item("Microsoft.MicrosoftSolitaireCollection", "Solitaire Collection", "Games",
         "Preinstalled card game.", True),
    Item("Microsoft.ZuneVideo", "Movies & TV", "Media",
         "Video player app. Does not affect the older Windows Media Player.", True),
    Item("Microsoft.ZuneMusic", "Media Player (new)", "Media",
         "The new music app. The older Windows Media Player is a separate feature.", True),
    Item("Microsoft.WindowsFeedbackHub", "Feedback Hub", "System",
         "Sends feedback to Microsoft. Safe to remove.", True),
    Item("Microsoft.549981C3F5F10", "Cortana", "System", "Assistant app. Safe to remove.", True),
    Item("Microsoft.Clipchamp", "Clipchamp", "Media", "Video editor. Only needed if you edit video.", False),
    Item("Microsoft.People", "People", "Consumer", "Contacts app.", False),
    Item("Microsoft.Todos", "Microsoft To Do", "Productivity", "To-do list app.", False),
    Item("Microsoft.WindowsMaps", "Maps", "Consumer", "Maps app.", False),
    Item("Microsoft.YourPhone", "Phone Link", "Consumer",
         "Links an Android or iPhone to this PC. Removing it stops phone linking.", False),
)

FEATURES = (
    Item("SMB1Protocol", "SMBv1 protocol", "Security",
         "Old file-sharing protocol with known security holes. Keep it off unless an old device needs it.", True),
    Item("MediaPlayback", "Media Feature Pack", "Legacy media",
         "Codecs for some media apps. Remove only if you don't play media.", False),
    Item("WindowsMediaPlayer", "Windows Media Player (legacy)", "Legacy media",
         "The classic media player. The newer Media Player app is separate.", False),
    Item("Printing-XPSServices-Features", "XPS services", "Legacy",
         "Support for XPS documents. Few people need it.", False),
    Item("WorkFolders-Client", "Work Folders client", "Legacy",
         "Syncs company folders. Remove unless you use Work Folders.", False),
    Item("TelnetClient", "Telnet client", "Legacy",
         "Old remote-login tool. Unencrypted, so off is the safer choice.", True),
    Item("MicrosoftWindowsPowerShellV2Root", "PowerShell 2.0", "Legacy",
         "Old PowerShell. Safer to remove, but very old scripts may stop working.", False),
    Item("Microsoft-Hyper-V-All", "Hyper-V", "Virtualisation",
         "Runs virtual machines. Remove if you never use VMs.", False),
    Item("Containers-DisposableClientVM", "Windows Sandbox", "Virtualisation",
         "A throwaway test desktop. Needs virtualisation support.", False),
    Item("Microsoft-Windows-Subsystem-Linux", "Windows Subsystem for Linux", "Virtualisation",
         "Runs Linux tools inside Windows.", False),
    Item("VirtualMachinePlatform", "Virtual Machine Platform", "Virtualisation",
         "Needed by WSL 2 and Windows Sandbox.", False),
)

CAPABILITIES = (
    Item("App.StepsRecorder~~~~0.0.1.0", "Steps Recorder", "Legacy",
         "Records your clicks as screenshots. Rarely needed.", False),
    Item("Media.WindowsMediaPlayer~~~~0.0.12.0", "Windows Media Player capability", "Legacy media",
         "Needed by the legacy Media Player. Remove it together with that feature.", False),
)

SERVICES = (
    Item("DiagTrack", "Connected User Experiences and Telemetry", "Telemetry",
         "Sends diagnostic data to Microsoft. Turning it off does not stop Windows Update.", True),
    Item("dmwappushservice", "WAP push message routing", "Telemetry",
         "Telemetry helper that is rarely used.", True),
    Item("RetailDemo", "Retail demo", "Telemetry",
         "Only used on store display machines.", True),
    Item("RemoteRegistry", "Remote registry", "Security",
         "Lets other computers edit this PC's registry. Off is safer.", True),
    Item("MapsBroker", "Downloaded maps manager", "Optional",
         "Keeps offline maps updated. Not needed without the Maps app.", False),
    Item("lfsvc", "Geolocation", "Optional", "Lets apps ask for this PC's location.", False),
    Item("Fax", "Fax", "Optional", "Fax service.", False),
    Item("wuauserv", "Windows Update service", "Updates",
         "Stops Windows Update completely, including security fixes and Microsoft Store updates. "
         "Kiosks often want this off.", False),
    Item("UsoSvc", "Update Orchestrator", "Updates",
         "Schedules update installs. Turn it off together with Windows Update.", False),
    Item("edgeupdate", "Edge update service", "Updates", "Keeps Microsoft Edge updated.", False),
    Item("edgeupdatem", "Edge update (on-demand)", "Updates",
         "Lets other programs ask for an Edge update to run.", False),
)

TWEAKS = (
    Tweak("telemetry", "Basic diagnostic data only", "Privacy",
          "Limits diagnostic data to the basic level. This is the lowest level Home and Pro allow.", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", "REG_DWORD", "1"),)),
    Tweak("advertising_id", "Turn off advertising ID", "Privacy",
          "Stops apps from using an ID to show you targeted ads.", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\AdvertisingInfo", "DisabledByGroupPolicy", "REG_DWORD", "1"),)),
    Tweak("consumer_features", "Stop automatic app suggestions", "Privacy",
          "Stops Windows installing suggested apps for users.", True,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", "REG_DWORD", "1"),)),
    Tweak("sponsored_apps", "No sponsored content for new users", "Privacy",
          "Turns off promoted apps and tips on the Start menu and lock screen. Applies to new accounts only.", True,
          (
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SilentInstalledAppsEnabled", "REG_DWORD", "0"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SystemPaneSuggestionsEnabled", "REG_DWORD", "0"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager",
                 "SoftLandingEnabled", "REG_DWORD", "0"),
          )),
    Tweak("long_paths", "Enable long file paths", "System",
          "Lets Windows use file paths longer than 260 characters. Some older apps still can't.", True,
          (_e("SYSTEM", r"ControlSet001\Control\FileSystem", "LongPathsEnabled", "REG_DWORD", "1"),)),
    Tweak("classic_menu", "Classic right-click menu (Windows 11)", "Look",
          "Brings back the full right-click menu. Applies to new accounts only.", False,
          (_e("DEFAULT", r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32",
              "", "REG_SZ", ""),)),
    Tweak("search_web_off", "No web results in Start search", "Privacy",
          "Start menu search shows only this PC's results, not Bing results.", False,
          (_e("SOFTWARE", r"Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", "REG_DWORD", "1"),)),
    Tweak("windows_update_policy", "Never install updates automatically", "Updates",
          "Windows downloads and installs nothing on its own. You can still check for updates by hand. "
          "Pair with the Windows Update services above if you want it fully off.", False,
          (
              _e("SOFTWARE", r"Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Policies\Microsoft\Windows\WindowsUpdate\AU", "AUOptions", "REG_DWORD", "2"),
          )),
    Tweak("driver_updates_off", "Keep my drivers (no driver swaps from Windows Update)", "Updates",
          "Stops Windows Update replacing drivers you installed yourself with generic ones.", False,
          (
              _e("SOFTWARE", r"Policies\Microsoft\Windows\WindowsUpdate", "ExcludeWUDriversInQualityUpdate", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\DriverSearching", "SearchOrderConfig", "REG_DWORD", "0"),
          )),
    Tweak("pause_updates_long", "Pause feature and quality updates for a very long time", "Updates",
          "Sets the Windows Update pause dates far in the future (until 2076). Only use this on a machine "
          "you maintain by hand.", False,
          (
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "FlightSettingsMaxPauseDays", "REG_DWORD", "18250"),
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "PauseFeatureUpdatesStartTime", "REG_SZ", "2026-01-27T00:00:00Z"),
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "PauseFeatureUpdatesEndTime", "REG_SZ", "2076-01-27T00:00:00Z"),
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "PauseQualityUpdatesStartTime", "REG_SZ", "2026-01-27T00:00:00Z"),
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "PauseQualityUpdatesEndTime", "REG_SZ", "2076-01-27T00:00:00Z"),
              _e("SOFTWARE", r"Microsoft\WindowsUpdate\UX\Settings", "PauseUpdatesExpiryTime", "REG_SZ", "2076-01-27T00:00:00Z"),
          )),
    Tweak("eventlog_quiet", "Turn off two noisy event logs", "Logging",
          "Stops the Device Update Agent and Windows Update client from writing to their event logs.", False,
          (
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\WINEVT\Channels\Microsoft-Windows-DeviceUpdateAgent/Operational",
                 "Enabled", "REG_DWORD", "0"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\WINEVT\Channels\Microsoft-Windows-WindowsUpdateClient/Operational",
                 "Enabled", "REG_DWORD", "0"),
          )),
    Tweak("kiosk_lockdown", "Lock the desktop down: no Lock, Sign out or Change password", "Kiosk",
          "For a machine that should stay in one app. Removes Lock, Sign out and Change password from the "
          "Ctrl+Alt+Del screen and the Start menu, for every account.", False,
          (
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "DisableLockWorkstation", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "DisableChangePassword", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoLogoff", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\System", "DisableLockWorkstation", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\System", "DisableChangePassword", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoLogoff", "REG_DWORD", "1"),
          )),
    Tweak("kiosk_no_taskbar", "Hide taskbar and right-click menus, block Windows keys (new users)", "Kiosk",
          "Stops users changing the taskbar, opening right-click menus and using Windows key shortcuts. "
          "Applies to new accounts only.", False,
          (
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoViewContextMenu", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoTrayContextMenu", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoSetTaskbar", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoTrayItemsDisplay", "REG_DWORD", "1"),
              _e("DEFAULT", r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoWinKeys", "REG_DWORD", "1"),
          )),
    Tweak("builtin_admin_fix", "Fix Settings and Photos for the built-in Administrator", "Kiosk",
          "Lets Settings and Photos open when you sign in as the built-in Administrator. "
          "Also turns off admin consent prompts, which lowers security.", False,
          (
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "FilterAdministratorToken", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA", "REG_DWORD", "1"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "ConsentPromptBehaviorAdmin", "REG_DWORD", "0"),
              _e("SOFTWARE", r"Microsoft\Windows\CurrentVersion\Policies\System", "LocalAccountTokenFilterPolicy", "REG_DWORD", "1"),
          )),
)

BUILTIN_LABELS = {
    "lean": "Lean (recommended)",
    "kiosk": "Kiosk (your NTLite setup)",
    "everything": "Everything (aggressive)",
    "blank": "Blank",
}

KIOSK_SERVICES = ("wuauserv", "UsoSvc", "edgeupdate", "edgeupdatem")
KIOSK_TWEAKS = ("windows_update_policy", "driver_updates_off", "pause_updates_long", "eventlog_quiet",
                "kiosk_lockdown", "kiosk_no_taskbar", "builtin_admin_fix")


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


def _kiosk_preset() -> dict:
    """The setup from the NTLite presets: recommended cuts, update lockdown, kiosk lockdown, built-in admin."""
    rec = lambda items: [i.id for i in items if i.recommended]  # noqa: E731
    profile = make_profile(
        "kiosk",
        "Your kiosk setup from NTLite: trims apps and telemetry, stops Windows Update, locks the desktop, "
        "and signs in to the built-in Administrator. Review the Account page before building.",
        apps=rec(APPS),
        features=rec(FEATURES) + ["Microsoft-Hyper-V-All"],
        services=rec(SERVICES) + list(KIOSK_SERVICES),
        tweaks=[t.id for t in TWEAKS if t.recommended] + list(KIOSK_TWEAKS),
    )
    profile["account"].update(
        name="Administrator",
        display_name="Kiosk",
        autologon=True,
        skip_oobe=True,
        enable_builtin_admin=True,
    )
    profile["region"]["timezone"] = "Central Standard Time"
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
        "kiosk": _kiosk_preset(),
        "everything": make_profile(
            "everything",
            "Everything in the catalog. Expect some breakage, so test it in a VM first.",
            apps=[i.id for i in APPS], features=[i.id for i in FEATURES],
            capabilities=[i.id for i in CAPABILITIES], services=[i.id for i in SERVICES],
            tweaks=[t.id for t in TWEAKS],
        ),
        "blank": make_profile("blank", "No changes. A starting point for your own profile."),
    }
