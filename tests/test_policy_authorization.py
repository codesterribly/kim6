"""Output policy authorization and cancellation contracts."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/bin/kim_all"


def source_function(source, name):
    start = source.index(f"{name}() {{\n")
    end = source.index("\n}\n", start) + 2
    return source[start:end]


class OutputPolicyAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT.read_text()
        cls.functions = "\n".join(
            source_function(source, name)
            for name in ("policy_mode", "choose_output_mode")
        )

    def check_mode(
        self, *, policy="prompt", configured="", choice="create",
        allow=False, gui=True, count="3"
    ):
        with tempfile.TemporaryDirectory() as folder:
            calls = Path(folder) / "dialogs"

            program = r'''
gettext() { printf '%s' "$1"; }
kdialog() {
  printf 'CALL %s\n' "$*" >> "$DIALOG_LOG"
  case " $* " in
    *' --radiolist '*)
      [ "$GUI_AVAILABLE" = yes ] || return 127
      [ "$DIALOG_CHOICE" != CLOSED ] || return 1
      printf '%s\n' "$DIALOG_CHOICE"
      ;;
    *' --warningyesno '*)
      [ "$GUI_AVAILABLE" = yes ] &&
        [ "$ALLOW_OVERWRITE" = yes ]
      ;;
    *) return 126 ;;
  esac
}
'''
            program += self.functions
            program += '\nchoose_output_mode "Kim" "Choose output" "$COUNT"\n'

            env = dict(
                os.environ,
                KIM_POLICY=policy,
                KIM_CFG_POLICY=configured,
                DIALOG_CHOICE=choice,
                ALLOW_OVERWRITE="yes" if allow else "no",
                GUI_AVAILABLE="yes" if gui else "no",
                COUNT=count,
                DIALOG_LOG=str(calls),
            )

            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", program],
                text=True,
                capture_output=True,
                env=env,
                timeout=5,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            logged = (
                [
                    line for line in calls.read_text().splitlines()
                    if line.startswith("CALL ")
                ]
                if calls.exists() else []
            )

            return result.stdout.strip(), logged

    def test_create_policy_never_prompts(self):
        value, calls = self.check_mode(policy="create")
        self.assertEqual(value, "create")
        self.assertEqual(calls, [])

    def test_legacy_overwrite_policy_cannot_auto_authorize(self):
        value, calls = self.check_mode(
            policy="overwrite", choice="create"
        )
        self.assertEqual(value, "create")
        self.assertEqual(len(calls), 1)
        self.assertIn("--radiolist", calls[0])

    def test_legacy_config_overwrite_cannot_auto_authorize(self):
        value, calls = self.check_mode(
            policy="", configured="overwrite", choice="create"
        )
        self.assertEqual(value, "create")
        self.assertEqual(len(calls), 1)

    def test_review_requires_second_explicit_approval(self):
        value, calls = self.check_mode(
            choice="review", allow=False
        )
        self.assertEqual(value, "cancel")
        self.assertEqual(len(calls), 2)
        self.assertIn("--warningyesno", calls[1])

    def test_review_and_warning_yes_authorizes_overwrite(self):
        value, calls = self.check_mode(
            choice="review", allow=True
        )
        self.assertEqual(value, "overwrite")
        self.assertEqual(len(calls), 2)
        self.assertIn("Yes, overwrite existing files", calls[1])

    def test_cancel_or_missing_gui_never_authorizes(self):
        scenarios = (
            ("CLOSED", True),
            ("review", False),
            ("unknown", True),
        )

        for choice, gui in scenarios:
            with self.subTest(choice=choice, gui=gui):
                value, _ = self.check_mode(
                    choice=choice, gui=gui
                )
                self.assertEqual(value, "cancel")


if __name__ == "__main__":
    unittest.main()
