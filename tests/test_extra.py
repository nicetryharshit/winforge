"""Tests for the app launcher, first-boot installs, home location, NTLite import and image scan parsing."""
import os
import tempfile
import unittest
from pathlib import Path

from winforge import catalog
from winforge.appsetup import apply_extras
from winforge.ntlite import import_ntlite
from winforge.profile import ProfileError, default_profile, normalise
from winforge.scan import parse_appx, parse_services, parse_table, list_tasks
from winforge.unattend import build_setupcomplete

PRESET = """<?xml version="1.0" encoding="utf-8"?>
<Preset xmlns="urn:schemas-nliteos-com:pn.v1">
 <Features><Feature enabled="no">Docker</Feature><Feature enabled="yes">Printing</Feature></Features>
 <Unattended mode="1">
  <settings pass="oobeSystem">
   <component name="Microsoft-Windows-International-Core">
    <InputLocale>0409:00000409</InputLocale><SystemLocale>en-US</SystemLocale>
    <UILanguage>en-GB</UILanguage><UserLocale>en-US</UserLocale>
   </component>
   <component name="Microsoft-Windows-Shell-Setup">
    <TimeZone>India Standard Time</TimeZone>
    <AutoLogon><Enabled>true</Enabled><Username>Administrator</Username>
     <Password><PlainText>true</PlainText><Value /></Password></AutoLogon>
    <OOBE><SkipMachineOOBE>true</SkipMachineOOBE></OOBE>
    <UserAccounts><LocalAccounts><LocalAccount>
     <DisplayName>Kiosk</DisplayName><Group>Administrators</Group><Name>Administrator</Name>
     <Password><PlainText>true</PlainText><Value /></Password>
    </LocalAccount></LocalAccounts></UserAccounts>
   </component>
  </settings>
  <settings pass="specialize"><component name="Microsoft-Windows-Deployment"><RunSynchronous>
   <RunSynchronousCommand><Order>1</Order><Path>net user Administrator /active:Yes</Path></RunSynchronousCommand>
   <RunSynchronousCommand><Order>2</Order><Path>net user Administrator /fullname:"Kiosk"</Path></RunSynchronousCommand>
   <RunSynchronousCommand><Order>3</Order><Path>echo hi</Path></RunSynchronousCommand>
  </RunSynchronous></component></settings>
 </Unattended>
 <Tweaks>
  <Settings><TweakGroup name="WindowsUpdate">
   <Tweak name="AU\\NoAutoUpdate">1</Tweak>
   <Tweak name="Settings\\HideMCTLink">1</Tweak>
  </TweakGroup></Settings>
  <Services><TweakGroup name="services">
   <Tweak name="wuauserv\\wuauserv">4</Tweak>
  </TweakGroup></Services>
 </Tweaks>
 <ApplyOptions><ImageTasks><Task>deledition_install.wim_01_Home</Task></ImageTasks></ApplyOptions>
 <Registry><File>C:\\x\\a.reg</File></Registry>
</Preset>
"""


def app_profile(**app):
    p = default_profile()
    p["app"].update({"enabled": True, "name": "Kiosk", "folder": "C:\\k", "exe": "k.exe"}, **app)
    return normalise(p)


class AppSetupTests(unittest.TestCase):
    def test_task_mode_copies_grants_and_schedules(self):
        p = apply_extras(app_profile(launch_now=True))
        self.assertIn({"from": "C:\\k", "to": "Kiosk"}, p["files"])
        text = "\n".join(p["scripts"]["setupcomplete"])
        self.assertIn('icacls "C:\\Kiosk" /grant "Everyone":(OI)(CI)F /T', text)
        self.assertIn('schtasks /create /tn "KioskLauncher"', text)
        self.assertIn('/sc onlogon /rl highest', text)
        self.assertIn('start "" "C:\\Kiosk\\k.exe"', text)

    def test_run_mode_writes_run_key(self):
        p = apply_extras(app_profile(mode="run"))
        self.assertTrue(any(r["key"].endswith("CurrentVersion\\Run") and r["data"] == '"C:\\Kiosk\\k.exe"'
                            for r in p["registry"]))

    def test_shell_mode_sets_shell_once_then_restarts(self):
        p = apply_extras(app_profile(mode="shell"))
        entry = next(r for r in p["registry"] if r["key"].endswith("RunOnce"))
        self.assertIn("Winlogon", entry["data"])
        self.assertIn("shutdown /r", entry["data"])

    def test_original_profile_is_kept_for_saving(self):
        orig = app_profile()
        self.assertEqual(apply_extras(orig)["_original"], orig)
        self.assertEqual(orig["scripts"]["setupcomplete"], [])

    def test_first_boot_drivers_and_installers(self):
        p = default_profile()
        p["drivers_boot"] = ["C:\\d\\WifiDriver"]
        p["installers"] = [{"file": "C:\\d\\nvidia.exe", "args": "/s /quiet"}]
        out = apply_extras(normalise(p))
        text = "\n".join(out["scripts"]["setupcomplete"])
        self.assertIn('pnputil /add-driver "%SystemDrive%\\Drivers\\WifiDriver\\*.inf" /subdirs /install', text)
        self.assertIn('start /wait "" "%SystemDrive%\\Drivers\\nvidia.exe" /s /quiet', text)
        self.assertIn({"from": "C:\\d\\nvidia.exe", "to": "Drivers\\nvidia.exe"}, out["files"])
        self.assertIn("pnputil", build_setupcomplete(out))

    def test_geo_id_runs_at_first_logon(self):
        p = default_profile()
        p["region"]["geo_id"] = 244
        out = apply_extras(normalise(p))
        self.assertIn("Set-WinHomeLocation -GeoId 244", "\n".join(out["scripts"]["firstlogon"]))

    def test_validation(self):
        with self.assertRaises(ProfileError):
            app_profile(exe="") 
        with self.assertRaises(ProfileError):
            app_profile(name="bad name!")
        with self.assertRaises(ProfileError):
            app_profile(mode="nope")
        p = default_profile()
        p["region"]["geo_id"] = 0
        with self.assertRaises(ProfileError):
            normalise(p)

    def test_old_profiles_still_load(self):
        old = default_profile()
        for key in ("app", "drivers_boot", "installers"):
            old.pop(key)
        old["region"].pop("geo_id")
        out = normalise(old)
        self.assertFalse(out["app"]["enabled"])
        self.assertIsNone(out["region"]["geo_id"])

    def test_new_kiosk_tweaks_exist(self):
        ids = {t.id for t in catalog.TWEAKS}
        self.assertLessEqual({"task_manager_off", "edge_swipe_off", "lockscreen_power_only"}, ids)


class NTLiteTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.path = Path(d) / "preset.xml"
        self.path.write_text(PRESET, encoding="utf-8")

    def test_import_maps_account_region_services_and_reg_files(self):
        p, notes = import_ntlite(self.path)
        self.assertEqual(p["account"]["name"], "Administrator")
        self.assertEqual(p["account"]["display_name"], "Kiosk")
        self.assertTrue(p["account"]["enable_builtin_admin"] and p["account"]["autologon"] and p["account"]["skip_oobe"])
        self.assertEqual(p["region"]["timezone"], "India Standard Time")
        self.assertEqual(p["services_disable"], ["wuauserv"])
        self.assertEqual(p["reg_files"], ["C:\\x\\a.reg"])
        self.assertEqual(p["scripts"]["specialize"], ["echo hi"])
        self.assertTrue(any(r["name"] == "NoAutoUpdate" and r["data"] == "1" for r in p["registry"]))

    def test_unmapped_items_are_reported_not_dropped(self):
        _, notes = import_ntlite(self.path)
        joined = "\n".join(notes)
        for fragment in ("HideMCTLink", "en-GB", "Docker", "Edition deletions"):
            self.assertIn(fragment, joined)

    def test_rejects_other_files(self):
        bad = self.path.with_name("bad.xml")
        bad.write_text("<html/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_ntlite(bad)
        bad.write_text("not xml", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_ntlite(bad)


class ScanParserTests(unittest.TestCase):
    def test_appx(self):
        text = ("Image Version: 10.0\n\nDisplayName : Microsoft.BingNews\nVersion : 4.5\nArchitecture : neutral\n"
                "PackageName : Microsoft.BingNews_4.5_neutral\n\nDisplayName : Microsoft.Todos\nVersion : 2.0\n")
        self.assertEqual([a["name"] for a in parse_appx(text)], ["Microsoft.BingNews", "Microsoft.Todos"])

    def test_table(self):
        text = ("Feature Name | State\n-------- | ----\nTelnetClient | Disabled\nMediaPlayback | Enabled\n")
        self.assertEqual(parse_table(text), [{"name": "TelnetClient", "state": "Disabled"},
                                             {"name": "MediaPlayback", "state": "Enabled"}])

    def test_services(self):
        text = ("HKEY_LOCAL_MACHINE\\WF_SYSTEM\\ControlSet001\\Services\\wuauserv\n    Start    REG_DWORD    0x3\n\n"
                "HKEY_LOCAL_MACHINE\\WF_SYSTEM\\ControlSet001\\Services\\wuauserv\\Parameters\n    ServiceDll    REG_SZ    x\n\n"
                "HKEY_LOCAL_MACHINE\\WF_SYSTEM\\ControlSet001\\Services\\Fax\n    Start    REG_DWORD    0x4\n")
        self.assertEqual(parse_services(text), [{"name": "wuauserv", "start": 3}, {"name": "Fax", "start": 4}])

    def test_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "Windows" / "System32" / "Tasks" / "Microsoft" / "Windows" / "WinSAT"
            t.parent.mkdir(parents=True)
            t.write_text("x")
            self.assertEqual(list_tasks(Path(d)), ["Microsoft\\Windows\\WinSAT"])


class GuiExtraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from winforge import gui
        cls.app = QApplication.instance() or QApplication([])
        cls.window = gui.MainWindow()

    def test_app_and_drivers_round_trip(self):
        p = app_profile(mode="shell", launch_now=True)
        p["region"]["geo_id"] = 244
        p["drivers_boot"] = ["C:\\d"]
        p["installers"] = [{"file": "C:\\d\\n.exe", "args": "/s"}]
        self.window.load_ui(p)
        out = self.window.collect()
        for key in ("app", "drivers_boot", "installers"):
            self.assertEqual(out[key], p[key])
        self.assertEqual(out["region"]["geo_id"], 244)

    def test_apply_scan_adds_real_items(self):
        self.window.apply_scan({"apps": [{"name": "Contoso.Thing"}], "features": [{"name": "F1", "state": "Enabled"}],
                                "capabilities": [], "services": [{"name": "MySvc", "start": 2}], "tasks": ["A\\B"]})
        self.assertIn("Contoso.Thing", {i.id for i in self.window.apps._items})
        self.assertIn("MySvc", {i.id for i in self.window.services._items})


if __name__ == "__main__":
    unittest.main()


class EditionPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from winforge import gui
        cls.app = QApplication.instance() or QApplication([])
        cls.window = gui.MainWindow()

    def test_edition_is_a_fixed_list_and_saved_name_survives(self):
        w = self.window
        self.assertFalse(w.edition.isEditable())
        p = default_profile()
        p["edition"] = "Windows 11 Pro"
        w.load_ui(normalise(p))
        self.assertEqual(w.collect()["edition"], "Windows 11 Pro")
        w._ed_out = '[{"index": 1, "name": "Windows 11 Home"}, {"index": 6, "name": "Windows 11 Pro"}]'
        w._ed_proc = type("P", (), {"readAllStandardError": lambda s: b"", "deleteLater": lambda s: None})()
        w._editions_done(0, None)
        self.assertEqual([w.edition.itemText(i) for i in range(w.edition.count())],
                         ["Windows 11 Home", "Windows 11 Pro"])
        self.assertEqual(w.edition.currentText(), "Windows 11 Pro")

    def test_progress_lines_drive_the_bar(self):
        w = self.window
        state = {}
        w._progress_line("== 4. Customise", 8, state)
        self.assertEqual(w.progress.value(), 500)
        w._progress_line("[==== 50.0% ====]", 8, state)
        self.assertEqual(w.progress.value(), int(4.5 / 8 * 1000))
