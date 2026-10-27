"""Fail-closed publication when a derived result aliases a selected source."""

import unittest

from support import Workspace


class FinalPublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "prompt"
        self.source = self.w.png("input/original.png")
        self.before = self.w.observe(self.source)

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"},
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 0},
        )

    def collage(self, destination):
        return self.w.dispatch(
            "pelemele", "--layout", "grid",
            "--canvas", "400x300",
            "--fit", "fit", "--gap", "12",
            "--frame", "none", "--no-shadow",
            "--output", destination,
            "--", self.source,
        )

    def assert_rejected_before_rendering(
        self, destination, extra=(), confirm_expected=True
    ):
        snapshots = {
            path: self.w.observe(path)
            for path in (self.source, *extra)
        }

        result = self.collage(destination)
        self.assertNotEqual(result.returncode, 0, result.events)

        for path, snapshot in snapshots.items():
            self.assertEqual(self.w.observe(path), snapshot)

        if confirm_expected:
            self.assertTrue(any(
                call["tool"] == "kdialog"
                and "--warningyesno" in call["argv"]
                for call in result.calls
            ))

        self.assertFalse(any(
            call["tool"] == "magick"
            for call in result.calls
        ))
        self.assertFalse(list(
            self.w.root.rglob(".kim6-stage.*")
        ))

    def test_explicit_approval_does_not_overwrite_selected_original(self):
        self.assert_rejected_before_rendering(self.source)

    def test_hardlink_alias_of_selected_original_cannot_be_overwritten(self):
        target = self.w.path("input/alias.png")
        target.hardlink_to(self.source)

        # Hardlinked inputs are rejected during input preflight.
        self.assert_rejected_before_rendering(
            target, (target,), confirm_expected=False
        )

    def test_symlink_output_cannot_replace_an_unrelated_file(self):
        protected = self.w.png("input/other.png")
        target = self.w.path("input/symlink.png")
        target.symlink_to(protected.name)

        self.assert_rejected_before_rendering(
            target, (target, protected)
        )

    def test_create_mode_refuses_selected_source_as_output(self):
        self.w.env["KIM_POLICY"] = "create"

        result = self.collage(self.source)

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assertEqual(
            self.w.observe(self.source), self.before
        )
        self.assertFalse(any(
            call["tool"] == "kdialog"
            and "--warningyesno" in call["argv"]
            for call in result.calls
        ))
        self.assertFalse(any(
            call["tool"] == "magick"
            for call in result.calls
        ))
        self.assertFalse(list(
            self.w.root.rglob(".kim6-stage.*")
        ))


if __name__ == "__main__":
    unittest.main()
