"""Tests that run on any OS: profiles, generated XML, .reg parsing, edition parsing, presets,
dry-run plans, CLI. GUI smoke tests run only when PySide6 is installed."""
import contextlib
import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from winforge import catalog, presets
from winforge.__main__ import main
from winforge.editions import find_edition, parse_wim_info
from winforge.pipeline import BuildError, build, ps_quote
from winforge.profile import ProfileError, default_profile, normalise
from winforge.regfile import parse_reg_text, read_reg_file
from winforge.unattend import build_setupcomplete, build_unattend

try:
    import PySide6  # noqa: F401
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

DISM_SAMPLE = """Deployment Image Servicing and Management tool
Version: 10.0.26100.9549

Details for image : C:\\WinForge\\work\\src\\sources\\install.wim

Index : 1
Name : Windows 11 Home
Description : Windows 11 Home
Size : 25,730,139,683 bytes

Index : 6
Name : Windows 11 Pro
Description : Windows 11 Pro
Size : 26,770,709,765 bytes

The operation completed successfully.
"""


def _tags(root, suffix):
    return [el for el in root.iter() if el.tag.endswith(suffix)]


class ProfileTests(unittest.TestCase):
    def test_defaults_validate(self):
        normalise(default_profile())

    def test_bad_hive_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"registry": [{"hive": "HKCU", "key": "a", "name": "b", "type": "REG_SZ", "data": "x"}]})

    def test_registry_key_must_be_relative(self):
        with self.assertRaises(ProfileError):
            normalise({"registry": [{"hive": "SOFTWARE", "key": "HKLM\\SOFTWARE\\x", "name": "b",
                                     "type": "REG_SZ", "data": "x"}]})

    def test_dword_data_coerced_and_checked(self):
        p = normalise({"registry": [{"hive": "SYSTEM", "key": "a", "name": "b", "type": "REG_DWORD", "data": 0}]})
        self.assertEqual(p["registry"][0]["data"], "0")
        with self.assertRaises(ProfileError):
            normalise({"registry": [{"hive": "SYSTEM", "key": "a", "name": "b", "type": "REG_DWORD", "data": "many"}]})

    def test_empty_value_name_is_allowed(self):
        p = normalise({"registry": [{"hive": "DEFAULT", "key": "a", "name": "", "type": "REG_SZ", "data": ""}]})
        self.assertEqual(p["registry"][0]["name"], "")

    def test_unknown_phase_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"scripts": {"bogus": []}})

    def test_bad_names_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"remove": {"appx": ["Bad Name; rm -rf"]}})

    def test_unsupported_schema_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"schema": 99})

    def test_missing_name_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"name": "   "})

    def test_builtin_admin_needs_an_account_name(self):
        with self.assertRaises(ProfileError):
            normalise({"account": {"name": "", "enable_builtin_admin": True, "autologon": False}})

    def test_region_fields_must_be_text(self):
        with self.assertRaises(ProfileError):
            normalise({"region": {"timezone": 5}})

    def test_empty_reg_file_entry_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"reg_files": [""]})

    def test_new_fields_have_defaults(self):
        p = normalise({})
        self.assertEqual(p["reg_files"], [])
        self.assertEqual(p["region"]["locale"], "en-US")
        self.assertFalse(p["account"]["enable_builtin_admin"])


class RegFileTests(unittest.TestCase):
    SAMPLE = "\n".join([
        "Windows Registry Editor Version 5.00",
        "",
        "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Test]",
        '"Enabled"=dword:00000001',
        '"Name"="hello \\"world\\""',
        '@="default value"',
        '"Long"=hex(2):43,00,3a,00,00,00',
        '"Bin"=hex:01,02,ff',
        "",
        "[-HKEY_LOCAL_MACHINE\\SOFTWARE\\Old]",
        "[HKEY_LOCAL_MACHINE\\HARDWARE\\X]",
        '"Skip"="x"',
        "[HKEY_CURRENT_USER\\Software\\Test]",
        '"Cont"=hex:01,02,\\',
        "  03,04",
        '"Del"=-',
        '"Q"=hex(b):ff,00,00,00,00,00,00,00',
    ])

    def test_maps_hives_and_value_types(self):
        entries, _ = parse_reg_text(self.SAMPLE)
        by_name = {(e["hive"], e["key"], e["name"]): e for e in entries}
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Enabled")]["type"], "REG_DWORD")
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Enabled")]["data"], "1")
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Name")]["data"], 'hello "world"')
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "")]["data"], "default value")
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Long")]["type"], "REG_EXPAND_SZ")
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Long")]["data"], "C:")
        self.assertEqual(by_name[("SOFTWARE", r"Policies\Test", "Bin")]["data"], "0102ff")
        self.assertEqual(by_name[("DEFAULT", r"Software\Test", "Q")]["type"], "REG_QWORD")
        self.assertEqual(by_name[("DEFAULT", r"Software\Test", "Q")]["data"], "255")

    def test_joins_wrapped_hex_lines(self):
        entries, _ = parse_reg_text(self.SAMPLE)
        cont = [e for e in entries if e["name"] == "Cont"][0]
        self.assertEqual(cont["data"], "01020304")

    def test_deletions_and_other_hives_are_warned_not_applied(self):
        entries, warnings = parse_reg_text(self.SAMPLE)
        names = {e["name"] for e in entries}
        self.assertNotIn("Del", names)
        self.assertNotIn("Skip", names)
        text = "\n".join(warnings)
        self.assertIn("deleting a key", text)
        self.assertIn("deleting the value 'Del'", text)
        self.assertIn("HARDWARE", text)

    def test_utf16_file_with_bom_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.reg"
            path.write_bytes(self.SAMPLE.encode("utf-16"))
            entries, _ = read_reg_file(path)
            self.assertTrue(any(e["name"] == "Enabled" for e in entries))


class UnattendTests(unittest.TestCase):
    def test_commands_and_escaping_survive_xml(self):
        p = normalise({
            "account": {"name": "A&B", "password": "<x>"},
            "scripts": {"firstlogon": ["echo a && echo b"], "specialize": ["reg add x"]},
        })
        root = ET.fromstring(build_unattend(p).encode("utf-8"))
        self.assertEqual([el.text for el in _tags(root, "CommandLine")], ["cmd.exe /c echo a && echo b"])
        self.assertIn("A&B", [el.text for el in _tags(root, "Name")])
        self.assertEqual(len(_tags(root, "Path")), 1)

    def test_no_firstlogon_block_when_empty(self):
        root = ET.fromstring(build_unattend(normalise({})).encode("utf-8"))
        self.assertEqual(_tags(root, "FirstLogonCommands"), [])

    def test_setupcomplete_none_when_empty(self):
        self.assertIsNone(build_setupcomplete(normalise({})))

    def test_setupcomplete_has_commands(self):
        text = build_setupcomplete(normalise({"scripts": {"setupcomplete": ["echo hi"]}}))
        self.assertIn("echo hi", text)
        self.assertTrue(text.startswith("@echo off"))

    def test_timezone_written_only_when_set(self):
        p = normalise({"region": {"timezone": "India Standard Time"}})
        self.assertIn("<TimeZone>India Standard Time</TimeZone>", build_unattend(p))
        self.assertNotIn("<TimeZone>", build_unattend(normalise({})))

    def test_builtin_admin_commands_come_first_in_specialize(self):
        p = normalise({
            "account": {"name": "Administrator", "display_name": "Kiosk", "enable_builtin_admin": True,
                        "autologon": False},
            "scripts": {"specialize": ["echo later"]},
        })
        root = ET.fromstring(build_unattend(p).encode("utf-8"))
        paths = [el.text for el in _tags(root, "Path")]
        self.assertEqual(paths[0], "cmd.exe /c net user Administrator /active:Yes")
        self.assertIn('cmd.exe /c net user Administrator /fullname:"Kiosk"', paths)
        self.assertEqual(paths[-1], "cmd.exe /c echo later")

    def test_windowspe_installs_index_one_and_accepts_eula(self):
        xml = build_unattend(normalise({}))
        self.assertIn("<Key>/IMAGE/INDEX</Key><Value>1</Value>", xml)
        self.assertIn("<AcceptEula>true</AcceptEula>", xml)


class UnattendTests(unittest.TestCase):
    def test_commands_and_escaping_survive_xml(self):
        p = normalise({
            "account": {"name": "A&B", "password": "<x>"},
            "scripts": {"firstlogon": ["echo a && echo b"], "specialize": ["reg add x"]},
        })
        root = ET.fromstring(build_unattend(p).encode("utf-8"))
        self.assertEqual([el.text for el in _tags(root, "CommandLine")], ["cmd.exe /c echo a && echo b"])
        self.assertIn("A&B", [el.text for el in _tags(root, "Name")])
        self.assertEqual(len(_tags(root, "Path")), 1)

    def test_no_firstlogon_block_when_empty(self):
        root = ET.fromstring(build_unattend(normalise({})).encode("utf-8"))
        self.assertEqual(_tags(root, "FirstLogonCommands"), [])

    def test_setupcomplete_none_when_empty(self):
        self.assertIsNone(build_setupcomplete(normalise({})))

    def test_setupcomplete_has_commands(self):
        text = build_setupcomplete(normalise({"scripts": {"setupcomplete": ["echo hi"]}}))
        self.assertIn("echo hi", text)
        self.assertTrue(text.startswith("@echo off"))


class EditionTests(unittest.TestCase):
    def test_parses_real_dism_output(self):
        editions = parse_wim_info(DISM_SAMPLE)
        self.assertEqual([(e.index, e.name) for e in editions],
                         [(1, "Windows 11 Home"), (6, "Windows 11 Pro")])

    def test_find_by_name_is_case_insensitive(self):
        editions = parse_wim_info(DISM_SAMPLE)
        self.assertEqual(find_edition(editions, name="windows 11 pro").index, 6)

    def test_missing_edition_lists_available(self):
        with self.assertRaises(ValueError) as ctx:
            find_edition(parse_wim_info(DISM_SAMPLE), name="Windows 11 Enterprise")
        self.assertIn("Windows 11 Home", str(ctx.exception))

    def test_find_by_index(self):
        self.assertEqual(find_edition(parse_wim_info(DISM_SAMPLE), index=1).name, "Windows 11 Home")


class CatalogAndPresetTests(unittest.TestCase):
    def test_builtin_presets_validate(self):
        for key, profile in catalog.builtin_presets().items():
            normalise(profile)
            self.assertEqual(profile["name"], key)

    def test_lean_keeps_store_and_defender(self):
        lean = catalog.builtin_presets()["lean"]
        self.assertIn("Microsoft.BingNews", lean["remove"]["appx"])
        self.assertNotIn("Microsoft.WindowsStore", lean["remove"]["appx"])
        self.assertIn("DiagTrack", lean["services_disable"])
        self.assertEqual(lean["services_disable"].count("RemoteRegistry"), 1)

    def test_kiosk_preset_matches_the_ntlite_setup(self):
        kiosk = catalog.builtin_presets()["kiosk"]
        self.assertEqual(kiosk["account"]["name"], "Administrator")
        self.assertTrue(kiosk["account"]["enable_builtin_admin"])
        self.assertEqual(kiosk["region"]["timezone"], "Central Standard Time")
        self.assertIn("wuauserv", kiosk["services_disable"])
        self.assertIn("Microsoft-Hyper-V-All", kiosk["remove"]["features"])
        self.assertTrue(any(r["name"] == "DisableLockWorkstation" for r in kiosk["registry"]))

    def test_make_profile_expands_tweaks(self):
        p = catalog.make_profile("t", "", tweaks=["telemetry"])
        self.assertEqual(p["registry"][0]["key"], r"Policies\Microsoft\Windows\DataCollection")

    def test_preset_store_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            presets.save_preset("My setup", catalog.builtin_presets()["lean"], root=root)
            names = [p.name for p in presets.list_presets(root=root) if not p.builtin]
            self.assertEqual(names, ["My setup"])
            loaded = presets.load_preset("My setup", root=root)
            self.assertEqual(loaded["name"], "My setup")
            presets.delete_preset("My setup", root=root)
            with self.assertRaises(KeyError):
                presets.load_preset("My setup", root=root)

    def test_cannot_shadow_or_delete_builtin(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                presets.save_preset("lean", default_profile(), root=Path(d))
            with self.assertRaises(ValueError):
                presets.delete_preset("lean", root=Path(d))

    def test_bad_preset_name_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                presets.save_preset("../evil", default_profile(), root=Path(d))


class PipelineTests(unittest.TestCase):
    def test_ps_quote_doubles_single_quotes(self):
        self.assertEqual(ps_quote("a'b"), "'a''b'")

    def test_dry_run_prints_plan_without_touching_disk(self):
        profile = normalise({
            "edition": "Windows 11 Pro",
            "registry": [{"hive": "SOFTWARE", "key": "K", "name": "N", "type": "REG_DWORD", "data": "1"}],
            "services_disable": ["DiagTrack"],
            "remove": {"appx": ["Microsoft.BingNews"]},
        })
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "w"
            lines = []
            build(profile, base=d, source=Path(d) / "win.iso", work=work, out=Path(d) / "o.iso",
                  dry_run=True, log=lines.append)
            self.assertFalse(work.exists())
        text = "\n".join(lines)
        self.assertIn("reg.exe load HKLM\\WF_SOFTWARE", text)
        self.assertIn("ControlSet001", text)
        self.assertIn("/Commit", text)
        self.assertIn("oscdimg", text.lower())
        self.assertIn("Dry run complete", text)

    def test_real_build_refused_off_windows_before_changes(self):
        profile = normalise({})
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "w"
            lines = []
            with self.assertRaises(BuildError):
                build(profile, base=d, source=Path(d) / "win.iso", work=work, out=Path(d) / "o.iso",
                      dry_run=False, log=lines.append)
            self.assertFalse(work.exists())
        self.assertTrue(any(line.startswith("ERROR:") for line in lines))

    def _dry(self, profile, base, lines):
        build(profile, base=base, source=Path(base) / "win.iso", work=Path(base) / "w",
              out=Path(base) / "o.iso", dry_run=True, log=lines.append)

    def test_edition_is_always_re_exported_with_chosen_compression(self):
        with tempfile.TemporaryDirectory() as d:
            lines = []
            self._dry(normalise({"options": {"compress": True}}), d, lines)
            text = "\n".join(lines)
            self.assertIn("/Export-Image", text)
            self.assertIn("/Compress:max", text)
            lines = []
            self._dry(normalise({"options": {"compress": False}}), d, lines)
            self.assertIn("/Compress:fast", "\n".join(lines))

    def test_reset_base_option_reaches_the_cleanup_step(self):
        with tempfile.TemporaryDirectory() as d:
            lines = []
            self._dry(normalise({"options": {"reset_base": True}}), d, lines)
            self.assertIn("/ResetBase", "\n".join(lines))

    def test_reg_file_entries_reach_the_plan(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tweak.reg").write_text(
                '[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Test]\n"X"=dword:00000001\n', encoding="utf-8")
            lines = []
            self._dry(normalise({"reg_files": ["tweak.reg"]}), d, lines)
            text = "\n".join(lines)
            self.assertIn("WF_SOFTWARE\\Policies\\Test", text)
            self.assertIn("Dry run complete", text)

    def test_missing_reg_file_is_a_preflight_error(self):
        with tempfile.TemporaryDirectory() as d:
            lines = []
            with self.assertRaises(BuildError):
                self._dry(normalise({"reg_files": ["nope.reg"]}), d, lines)
        self.assertTrue(any(".reg file not found" in line for line in lines))

    def test_missing_driver_folder_is_a_preflight_error(self):
        profile = normalise({"drivers": ["does-not-exist"]})
        with tempfile.TemporaryDirectory() as d:
            lines = []
            with self.assertRaises(BuildError):
                build(profile, base=d, source=Path(d), work=Path(d) / "w", out=Path(d) / "o.iso",
                      dry_run=True, log=lines.append)
        self.assertTrue(any("driver folder not found" in line for line in lines))


class CliTests(unittest.TestCase):
    def _run(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out.getvalue()

    def test_validate_example_profile(self):
        code, out = self._run(["validate", str(Path(__file__).resolve().parents[1] / "profiles" / "example.json")])
        self.assertEqual(code, 0)
        self.assertIn("OK:", out)

    def test_presets_list_shows_builtins(self):
        code, out = self._run(["presets", "list"])
        self.assertEqual(code, 0)
        self.assertIn("lean", out)
        self.assertIn("everything", out)

    def test_dry_run_build_from_preset(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self._run(["build", "--preset", "lean", "--source", str(Path(d) / "x.iso"),
                                   "--out", str(Path(d) / "o.iso"), "--work", str(Path(d) / "w"), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("Dry run complete", out)

    def test_build_without_profile_or_preset_fails_cleanly(self):
        code, _ = self._run(["build", "--source", "x.iso", "--out", "o.iso"])
        self.assertEqual(code, 1)

    def test_unknown_preset_fails_cleanly(self):
        code, _ = self._run(["presets", "show", "no-such-preset"])
        self.assertEqual(code, 1)


@unittest.skipUnless(HAS_PYSIDE, "PySide6 is not installed; GUI smoke tests skipped")
class GuiSmokeTests(unittest.TestCase):
    """Builds the real window offscreen and checks that the profile survives a load and collect."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from winforge import gui
        cls.app = QApplication.instance() or QApplication([])
        cls.window = gui.MainWindow()

    def test_every_page_is_built(self):
        from winforge.gui import PAGES
        self.assertEqual(self.window.stack.count(), len(PAGES))

    def test_kiosk_preset_round_trips_through_the_editor(self):
        kiosk = catalog.builtin_presets()["kiosk"]
        self.window.load_ui(kiosk)
        out = self.window.collect()
        self.assertEqual(out["account"], kiosk["account"])
        self.assertEqual(out["region"], kiosk["region"])
        self.assertEqual(sorted(out["remove"]["appx"]), sorted(kiosk["remove"]["appx"]))
        self.assertEqual(sorted(out["services_disable"]), sorted(kiosk["services_disable"]))
        as_text = lambda rows: sorted(json.dumps(r, sort_keys=True) for r in rows)  # noqa: E731
        self.assertEqual(as_text(out["registry"]), as_text(kiosk["registry"]))

    def test_files_tree_round_trips(self):
        files = [{"from": "tools\\a.ps1", "to": "Windows\\Setup\\Scripts\\a.ps1"},
                 {"from": "b.txt", "to": "b.txt"}]
        self.window.files_tree.set_entries(files)
        key = lambda f: f["to"]  # noqa: E731
        self.assertEqual(sorted(self.window.files_tree.entries(), key=key), sorted(files, key=key))

    def test_destination_folders_are_checked(self):
        from winforge.gui import _clean_folder
        self.assertEqual(_clean_folder("/Windows/Setup/Scripts/"), "Windows\\Setup\\Scripts")
        self.assertEqual(_clean_folder(""), "")
        self.assertIsNone(_clean_folder("C:\\Windows"))
        self.assertIsNone(_clean_folder("..\\Windows"))

    def test_default_profile_collects_without_error(self):
        self.window.load_ui(default_profile())
        self.window.collect()


if __name__ == "__main__":
    unittest.main()
