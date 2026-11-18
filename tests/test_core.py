"""Tests that run on any OS: profile validation, XML generation, and a dry-run build plan."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from winforge.pipeline import build, ps_quote
from winforge.profile import ProfileError, default_profile, normalise
from winforge.unattend import build_setupcomplete, build_unattend


def _tags(root, suffix):
    return [el for el in root.iter() if el.tag.endswith(suffix)]


class ProfileTests(unittest.TestCase):
    def test_defaults_validate(self):
        normalise(default_profile())

    def test_bad_hive_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"registry": [{"hive": "HKCU", "key": "a", "name": "b", "type": "REG_SZ", "data": "x"}]})

    def test_dword_data_coerced_to_string(self):
        p = normalise({"registry": [{"hive": "SYSTEM", "key": "a", "name": "b", "type": "REG_DWORD", "data": 0}]})
        self.assertEqual(p["registry"][0]["data"], "0")

    def test_unknown_phase_rejected(self):
        with self.assertRaises(ProfileError):
            normalise({"scripts": {"bogus": []}})


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


class PipelineTests(unittest.TestCase):
    def test_ps_quote_doubles_single_quotes(self):
        self.assertEqual(ps_quote("a'b"), "'a''b'")

    def test_dry_run_prints_plan_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "p.json"
            prof.write_text(json.dumps({
                "edition": "Windows 11 Pro",
                "registry": [{"hive": "SOFTWARE", "key": "K", "name": "N", "type": "REG_DWORD", "data": "1"}],
                "services_disable": ["DiagTrack"],
            }), encoding="utf-8")
            lines = []
            build(prof, source=Path(d) / "win.iso", work=Path(d) / "w", out=Path(d) / "o.iso",
                  dry_run=True, log=lines.append)
            self.assertFalse((Path(d) / "w").exists())
        text = "\n".join(lines)
        self.assertIn("reg.exe load HKLM\\WF_SOFTWARE", text)
        self.assertIn("ControlSet001", text)
        self.assertIn("/Commit", text)
        self.assertIn("oscdimg", text.lower())


if __name__ == "__main__":
    unittest.main()
