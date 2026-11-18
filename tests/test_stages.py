"""Tests for the stage model: ready-made steps, the every-sign-in and every-boot stages, and the new sidebar."""
import os
import unittest

from winforge import recipes
from winforge.appsetup import apply_extras, stage_lines
from winforge.profile import ProfileError, default_profile, normalise
from winforge.unattend import build_setupcomplete


def profile_with(**kw):
    p = default_profile()
    for key, value in kw.items():
        section, phase = key.split("__")
        p[section][phase] = value
    return normalise(p)


class RecipeTests(unittest.TestCase):
    def test_every_recipe_belongs_to_a_known_stage(self):
        for r in recipes.RECIPES:
            self.assertIn(r.phase, recipes.STAGES)
            self.assertTrue(r.lines)
            self.assertTrue(r.note)

    def test_ticked_recipe_runs_before_typed_commands(self):
        p = default_profile()
        p["steps"]["setupcomplete"] = [{"recipe": "refresh_policy", "enabled": True},
                                       {"recipe": "nvidia_silent", "enabled": False}]
        p["scripts"]["setupcomplete"] = ["echo typed"]
        lines = stage_lines(normalise(p), "setupcomplete")
        self.assertIn("gpupdate /force", lines[0])
        self.assertEqual(lines[-1], "echo typed")
        self.assertFalse(any("nvidia.exe" in line for line in lines))

    def test_unknown_recipe_and_wrong_stage_are_rejected(self):
        p = default_profile()
        p["steps"]["setupcomplete"] = [{"recipe": "does_not_exist", "enabled": True}]
        with self.assertRaises(ProfileError):
            normalise(p)
        p = default_profile()
        p["steps"]["firstlogon"] = [{"recipe": "refresh_policy", "enabled": True}]
        with self.assertRaises(ProfileError):
            normalise(p)

    def test_old_profiles_without_steps_still_load(self):
        old = default_profile()
        old.pop("steps")
        for phase in ("everylogon", "everyboot"):
            old["scripts"].pop(phase)
        out = normalise(old)
        self.assertEqual(out["steps"]["setupcomplete"], [])
        self.assertEqual(out["scripts"]["everyboot"], [])


class EverySignInAndBootTests(unittest.TestCase):
    def test_every_sign_in_writes_script_and_task(self):
        p = default_profile()
        p["scripts"]["everylogon"] = ['echo signed in']
        out = apply_extras(normalise(p))
        self.assertIn("Windows\\Setup\\Scripts\\WinForge-every-sign-in.cmd", out["generated"])
        self.assertIn("echo signed in", out["generated"]["Windows\\Setup\\Scripts\\WinForge-every-sign-in.cmd"])
        setup = "\n".join(out["scripts"]["setupcomplete"])
        self.assertIn('/sc onlogon /ru "BUILTIN\\Users"', setup)

    def test_every_boot_writes_script_and_system_task(self):
        p = default_profile()
        p["scripts"]["everyboot"] = ['echo booted']
        out = apply_extras(normalise(p))
        self.assertIn("Windows\\Setup\\Scripts\\WinForge-every-boot.cmd", out["generated"])
        setup = "\n".join(out["scripts"]["setupcomplete"])
        self.assertIn('/sc onstart /ru "SYSTEM"', setup)

    def test_empty_stages_create_nothing(self):
        out = apply_extras(normalise(default_profile()))
        self.assertEqual(out["generated"], {})
        self.assertNotIn("onlogon", build_setupcomplete(out) or "")

    def test_task_is_created_only_after_its_files_are_copied(self):
        p = default_profile()
        p["scripts"]["everylogon"] = ["echo hi"]
        out = apply_extras(normalise(p))
        self.assertTrue(out["generated"])
        self.assertTrue(any("WinForge every sign-in" in line for line in out["scripts"]["setupcomplete"]))


class SidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from winforge import gui
        cls.app = QApplication.instance() or QApplication([])
        cls.gui = gui
        cls.window = gui.MainWindow()

    def test_every_page_has_a_tip_and_a_sidebar_row(self):
        names = [self.window.nav.item(r).data(0x0100) for r in range(self.window.nav.count())]
        selectable = [n for n in names if n]
        self.assertEqual(sorted(selectable), sorted(self.gui.PAGES))
        for name in self.gui.PAGES:
            self.assertIn(name, self.gui.PAGE_TIP)

    def test_go_selects_the_stage_page(self):
        self.window.go("Every boot")
        self.assertEqual(self.window.stack.currentIndex(), self.gui.PAGES.index("Every boot"))

    def test_stage_steps_round_trip(self):
        p = default_profile()
        p["steps"]["setupcomplete"] = [{"recipe": "nvidia_silent", "enabled": True},
                                       {"recipe": "refresh_policy", "enabled": False}]
        p["scripts"]["everylogon"] = ["echo a"]
        self.window.load_ui(normalise(p))
        out = self.window.collect()
        steps = {s["recipe"]: s["enabled"] for s in out["steps"]["setupcomplete"]}
        self.assertTrue(steps["nvidia_silent"])
        self.assertFalse(steps["refresh_policy"])
        self.assertEqual(out["scripts"]["everylogon"], ["echo a"])


if __name__ == "__main__":
    unittest.main()
