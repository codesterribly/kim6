"""Authorization before in-place rotation and reflection."""

import unittest

from support import Workspace


class InPlaceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.source = self.w.ppm("input/original.ppm")
        self.before = self.w.observe(self.source)

    def dispatch(self, command, *options):
        result = self.w.dispatch(
            command, *options, "--", self.source
        )
        self.assertEqual(
            self.w.observe(self.source), self.before
        )
        return result

    def test_create_policy_refuses_inplace_rotation(self):
        self.w.env["KIM_POLICY"] = "create"

        result = self.dispatch(
            "rotate", "--angle", "90"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(
            c["tool"] in ("magick", "identify")
            for c in result.calls
        ))
        self.assertFalse(any(
            "--radiolist" in c["argv"]
            for c in result.calls
        ))

    def test_default_prompt_cancellation_refuses_flip(self):
        self.w.env["KIM_POLICY"] = "prompt"

        result = self.dispatch(
            "flipflop", "flip"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(
            "--radiolist" in c["argv"]
            for c in result.calls
        ))
        self.assertFalse(any(
            c["tool"] == "magick"
            for c in result.calls
        ))

    def test_legacy_overwrite_cannot_bypass_confirmation(self):
        self.w.env["KIM_POLICY"] = "overwrite"

        result = self.dispatch(
            "rotate", "--exif"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(
            "--radiolist" in c["argv"]
            for c in result.calls
        ))
        self.assertFalse(any(
            c["tool"] == "magick"
            for c in result.calls
        ))

    def test_refusing_final_confirmation_preserves_source(self):
        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"}
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 1}
        )

        result = self.dispatch(
            "flipflop", "flop"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(
            "--warningyesno" in c["argv"]
            for c in result.calls
        ))
        self.assertFalse(any(
            c["tool"] == "magick"
            for c in result.calls
        ))

    def test_confirmation_occurs_once_for_batch(self):
        second = self.w.ppm("input/second.ppm")

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"}
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 0}
        )

        result = self.w.dispatch(
            "flipflop", "flip", "--",
            self.source, second
        )

        dialogs = [
            c for c in result.calls
            if c["tool"] == "kdialog"
        ]

        self.assertEqual(
            sum("--radiolist" in c["argv"] for c in dialogs),
            1
        )
        self.assertEqual(
            sum("--warningyesno" in c["argv"] for c in dialogs),
            1
        )

        # Execution reached image validation only after approval.
        self.assertTrue(any(
            c["tool"] == "identify"
            for c in result.calls
        ))


if __name__ == "__main__":
    unittest.main()
