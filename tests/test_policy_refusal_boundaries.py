"""Fail-closed overwrite authorization at real dispatcher entry points."""

import unittest

from support import Workspace


class PolicyRefusalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.first = self.w.jpeg("input/first.jpg")
        self.second = self.w.jpeg("input/second.jpg")

        self.before = {
            path: self.w.observe(path)
            for path in (self.first, self.second)
        }

    def assert_refused(self, command, *args):
        result = self.w.dispatch(command, *args)

        self.assertNotEqual(
            result.returncode, 0, result.events
        )

        for path, snapshot in self.before.items():
            self.assertEqual(
                self.w.observe(path), snapshot, path
            )

        self.assertFalse(
            any(
                call["tool"] in ("magick", "mogrify", "ffmpeg")
                for call in result.calls
            ),
            result.events,
        )

        return result

    @staticmethod
    def dialogs(result, option):
        return [
            call for call in result.calls
            if call["tool"] == "kdialog"
            and option in call["argv"]
        ]

    def test_env_legacy_overwrite_and_missing_gui_never_convert(self):
        self.w.env["KIM_POLICY"] = "overwrite"

        self.w.respond_to(
            "kdialog", "--radiolist", {"status": 127}
        )

        result = self.assert_refused(
            "convert", "jpg", self.first
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 0
        )

    def test_kconfig_legacy_overwrite_and_missing_gui_never_edit_metadata(self):
        self.w.configure("KIM_POLICY", "overwrite")

        self.w.respond_to(
            "kdialog", "--radiolist", {"status": 127}
        )

        result = self.assert_refused(
            "copyright",
            "--creator", "Example",
            "--", self.first,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 0
        )

    def test_closed_first_dialog_does_not_resize(self):
        self.w.env["KIM_POLICY"] = "prompt"

        self.w.respond_to(
            "kdialog", "--radiolist", {"status": 1}
        )

        result = self.assert_refused(
            "resize",
            "--size", "100x100",
            "--", self.first,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 0
        )

    def test_unexpected_choice_does_not_strip_metadata(self):
        self.w.env["KIM_POLICY"] = "prompt"

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "overwrite\n"},
        )

        result = self.assert_refused(
            "stripmeta",
            "--mode", "all",
            "--", self.first,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 0
        )

    def test_declined_warning_does_not_rename_originals(self):
        self.w.env["KIM_POLICY"] = "prompt"

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"},
        )

        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 1},
        )

        result = self.assert_refused(
            "rename",
            "lowercase",
            "--",
            self.first, self.second,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 1
        )

    def test_unavailable_warning_does_not_rotate_originals(self):
        self.w.env["KIM_POLICY"] = "overwrite"

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"},
        )

        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 127},
        )

        result = self.assert_refused(
            "rotate",
            "--angle", "90",
            "--", self.first,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 1
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 1
        )

    def test_create_policy_never_authorizes_inplace_flip(self):
        self.w.env["KIM_POLICY"] = "create"

        result = self.assert_refused(
            "flipflop",
            "flip",
            "--", self.first,
        )

        self.assertEqual(
            len(self.dialogs(result, "--radiolist")), 0
        )
        self.assertEqual(
            len(self.dialogs(result, "--warningyesno")), 0
        )


if __name__ == "__main__":
    unittest.main()
