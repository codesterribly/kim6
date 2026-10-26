"""Regression tests for Dolphin error dialogs and email cancellation."""

import unittest
from pathlib import Path

from support import Workspace


class DolphinUIAuditTests(unittest.TestCase):

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

    def test_invalid_option_shows_gui_error_and_preserves_cli_stderr(self):
        source = self.w.ppm("input/photo.ppm")
        before = self.w.observe(source)
        self.w.env["WAYLAND_DISPLAY"] = "wayland-test"

        result = self.w.dispatch("resize", "--what", source)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("resize: unknown option --what", result.stderr)

        dialogs = [
            call for call in result.calls
            if call["tool"] == "kdialog"
            and "--error" in call["argv"]
        ]
        self.assertEqual(len(dialogs), 1)
        self.assertIn("resize: unknown option --what", dialogs[0]["argv"])
        self.assertEqual(self.w.observe(source), before)

    def test_email_size_dialog_cancellation_has_nonzero_status(self):
        source = self.w.ppm("input/photo.ppm")
        before = self.w.observe(source)
        self.w.respond("kdialog", status=1)

        result = self.w.dispatch("resizeandsend", "--", source)

        self.assertEqual(result.returncode, 130)
        self.assertFalse(any(
            call["tool"] in ("kmail", "thunderbird", "xdg-email")
            for call in result.calls
        ))
        self.assertEqual(self.w.observe(source), before)
        self.assertFalse(
            (Path(self.w.env["XDG_DATA_HOME"]) /
             "kim6/email-attachments").exists()
        )

    def test_email_custom_size_cancellation_has_nonzero_status(self):
        source = self.w.ppm("input/photo.ppm")
        before = self.w.observe(source)
        self.w.sequence("kdialog", [
            {"stdout": "7", "status": 0},
            {"status": 1},
        ])

        result = self.w.dispatch("resizeandsend", "--", source)

        self.assertEqual(result.returncode, 130)
        self.assertEqual(self.w.observe(source), before)
        self.assertFalse(any(
            call["tool"] in ("kmail", "thunderbird", "xdg-email")
            for call in result.calls
        ))
        self.assertFalse(
            (Path(self.w.env["XDG_DATA_HOME"]) /
             "kim6/email-attachments").exists()
        )


if __name__ == "__main__":
    unittest.main()
