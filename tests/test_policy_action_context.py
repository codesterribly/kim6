"""Destructive-operation prompts distinguish renamed sources from replacements."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from support import Workspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/bin/kim_all"


def source_function(source, name):
    start = source.index(f"{name}() {{\n")
    end = source.index("\n}\n", start) + 2
    return source[start:end]


class ActionContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT.read_text()
        cls.functions = "\n".join(
            source_function(source, name)
            for name in ("policy_mode", "choose_output_mode")
        )

    def confirm(self, context):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "dialogs"

            program = r'''
gettext() { printf '%s' "$1"; }
kdialog() {
  printf '%s\n' "$(printf '%s' "$*" | tr '\n' ' ')" >> "$DIALOG_LOG"
  case " $* " in
    *' --radiolist '*) printf '%s\n' review ;;
    *' --warningyesno '*) return 1 ;;
    *) return 1 ;;
  esac
}
'''
            program += self.functions
            program += (
                f'\nchoose_output_mode "Kim" "Output mode" "5" "{context}"\n'
            )

            result = subprocess.run(
                ["bash", "-c", program],
                capture_output=True,
                text=True,
                timeout=5,
                env={
                    **os.environ,
                    "DIALOG_LOG": str(log),
                    "KIM_POLICY": "prompt",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "cancel")

            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 2)
            self.assertIn("Selected files: 5", calls[0])
            self.assertIn("Selected files: 5", calls[1])

            return calls[1]

    def test_rename_warning_describes_source_removal(self):
        message = self.confirm("rename")
        self.assertIn("old filenames", message)
        self.assertIn("Yes, rename selected originals", message)

    def test_original_replacement_warning_is_explicit(self):
        message = self.confirm("originals")
        self.assertIn("selected original files", message)
        self.assertIn("Yes, overwrite selected originals", message)

    def test_derived_output_warning_is_distinct(self):
        message = self.confirm("output")
        self.assertIn("derived output files", message)
        self.assertIn("Yes, replace existing outputs", message)

    def test_rename_dispatch_displays_batch_count_before_changes(self):
        w = Workspace()
        self.addCleanup(w.close)

        first = w.ppm("input/First.ppm")
        second = w.ppm("input/Second.ppm")
        before = [w.observe(first), w.observe(second)]

        w.env["KIM_POLICY"] = "prompt"
        result = w.dispatch(
            "rename", "lowercase", "--", first, second,
        )

        dialogs = [
            call for call in result.calls
            if call["tool"] == "kdialog"
            and "--radiolist" in call["argv"]
        ]

        self.assertTrue(dialogs, result.events)
        self.assertIn(
            "Selected files: 2",
            " ".join(dialogs[0]["argv"]),
        )
        self.assertEqual(
            [w.observe(first), w.observe(second)],
            before,
        )

    def test_metadata_dispatch_shows_batch_count_before_changes(self):
        w = Workspace()
        self.addCleanup(w.close)

        first = w.ppm("input/First.ppm")
        second = w.ppm("input/Second.ppm")
        before = [w.observe(first), w.observe(second)]

        w.env["KIM_POLICY"] = "prompt"
        result = w.dispatch(
            "copyright", "--creator", "Example",
            "--", first, second,
        )

        dialogs = [
            call for call in result.calls
            if call["tool"] == "kdialog"
            and "--radiolist" in call["argv"]
        ]

        self.assertTrue(dialogs, result.events)
        self.assertIn(
            "Selected files: 2",
            " ".join(dialogs[0]["argv"]),
        )
        self.assertEqual(
            [w.observe(first), w.observe(second)],
            before,
        )


if __name__ == "__main__":
    unittest.main()
