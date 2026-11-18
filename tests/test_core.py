"""Tests that run on any OS: profiles, generated XML, edition parsing, presets, dry-run plans, CLI."""
import contextlib
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from winforge import catalog, presets
from winforge.__main__ import main
from winforge.editions import find_edition, parse_wim_info
from winforge.pipeline import BuildError, build, ps_quote
from winforge.profile import ProfileError, default_profile, normalise
from winforge.unattend import build_setupcomplete, build_unattend

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


if __name__ == "__main__":
    unittest.main()
