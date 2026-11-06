"""Regression tests for Dolphin error dialogs and email cancellation."""

import unittest
from pathlib import Path

from support import Workspace


class DolphinUIAuditTests(unittest.TestCase):

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

    def _simulate_email_options_cancel(self):
        """Simulate cancellation at the current Qt dialog boundary."""
        import shlex

        marker = self.w.control / "email-options-cancelled"
        executable = self.w.bin / "python3"

        executable.write_text(
            "#!/bin/sh\n"
            'if [ "$2" = "email-options" ]; then\n'
            f"  printf cancelled > {shlex.quote(str(marker))}\n"
            "  exit 130\n"
            "fi\n"
            "exit 97\n"
        )
        executable.chmod(0o700)
        return marker


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

    def test_email_options_cancellation_has_nonzero_status(self):
        source = self.w.ppm("input/photo.ppm")
        before = self.w.observe(source)
        marker = self._simulate_email_options_cancel()

        result = self.w.dispatch("resizeandsend", "--", source)

        self.assertTrue(marker.is_file())
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

    def test_email_explicit_size_cancellation_has_nonzero_status(self):
        source = self.w.ppm("input/photo.ppm")
        before = self.w.observe(source)
        marker = self._simulate_email_options_cancel()

        result = self.w.dispatch(
            "resizeandsend", "--size", "900x600", "--", source
        )

        self.assertTrue(marker.is_file())
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


    def test_file_independent_actions_handle_multiselection(self):
        """One informational invocation for a multi-image selection."""
        import configparser
        import shlex

        menu = (
            Path(__file__).resolve().parents[1]
            / "src/kim_information.desktop.in"
        )

        parser = configparser.RawConfigParser()
        parser.optionxform = str
        self.assertTrue(parser.read(menu, encoding="utf-8"))

        routes = {
            "01Settings": "settings",
            "02About": "about",
            "03License": "license",
            "04Manual": "manual",
        }

        for action_id, route in routes.items():
            with self.subTest(action=action_id):
                command = parser.get(
                    f"Desktop Action {action_id}", "Exec"
                )
                self.assertEqual(
                    shlex.split(command),
                    ["kim_all", route, "--", "%F"],
                )


if __name__ == "__main__":
    unittest.main()
