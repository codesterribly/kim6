"""Infrastructure contracts, not K02 action-preservation acceptance tests."""
from pathlib import Path
import base64
import subprocess
import sys
import unittest

from support import Workspace


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def test_intentional_assertion_failure_fails_a_runner(self):
        probe = self.workspace.path("test_failure_probe.py")
        probe.write_text(
            "import unittest\n"
            "class Probe(unittest.TestCase):\n"
            "    def test_deliberate_failure(self):\n"
            "        self.assertEqual('actual', 'expected', 'K01 intentional failure')\n"
        )
        runner = self.workspace.path("run.py")
        runner.write_bytes(Path(__file__).with_name("run.py").read_bytes())
        result = subprocess.run(
            [sys.executable, "-B", str(runner), "--pattern", probe.name],
            cwd=self.workspace.root, env=self.workspace.env,
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("K01 intentional failure", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)

    def test_workspaces_are_unique_and_cleanup_is_local(self):
        other = Workspace()
        self.addCleanup(other.close)
        sentinel = other.path("untouched.ppm")
        sentinel.write_bytes(b"other workspace")
        self.assertNotEqual(self.workspace.root, other.root)
        own_root = self.workspace.root
        self.workspace.close()
        self.assertFalse(own_root.exists())
        self.assertEqual(sentinel.read_bytes(), b"other workspace")

    def test_dispatcher_help_is_an_isolated_real_subprocess(self):
        result = self.workspace.dispatch("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: kim_all", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.outputs, {})
        self.assertEqual(self.workspace.dispatcher.read_bytes(),
                         self.workspace.production.read_bytes())

    def test_adapter_captures_status_streams_and_argument_boundaries(self):
        self.workspace.respond("magick", stdout="producer output\n",
                               stderr="producer error\n", status=7)
        arguments = ["a space", "雪.jpg", "", "-leading", "quote'\"", "line\nbreak"]
        result = self.workspace.command("magick", *arguments)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "producer output\n")
        self.assertEqual(result.stderr, "producer error\n")
        self.assertEqual(result.calls[-1]["argv"], arguments)

    def test_qdbus_adapter_requires_separate_service_and_object_path(self):
        dialog = self.workspace.command("kdialog", "--progressbar", "Working", "2")
        self.assertEqual(dialog.stdout, "org.kde.kdialog-test /ProgressDialog\n")
        bad = self.workspace.command("qdbus", dialog.stdout.strip(), "wasCancelled")
        self.assertNotEqual(bad.returncode, 0)
        good = self.workspace.command("qdbus", *dialog.stdout.split(), "wasCancelled")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(good.stdout, "false\n")

    def test_asymmetric_fixture_can_be_flipped_with_real_imagemagick(self):
        source = self.workspace.ppm("input/asymmetric 雪.ppm")
        self.workspace.use_real_magick()
        destination = self.workspace.path("out/flipped image.ppm")
        result = self.workspace.command("magick", str(source), "-flip", str(destination))
        self.assertEqual(result.returncode, 0, result.stderr)
        pixels = destination.read_bytes().split(b"\n", 3)[-1]
        self.assertEqual(pixels, bytes.fromhex("ffff00ff00ff00ffff ff000000ff000000ff"))
        self.assertEqual(result.calls[-1]["argv"],
                         [str(source), "-flip", str(destination)])
        self.assertEqual(result.outputs["out/flipped image.ppm"], destination.read_bytes())

    def test_dialog_responses_can_model_cancel_and_multiple_prompts(self):
        self.workspace.sequence("kdialog", [
            {"stdout": "1600x1600\n"}, {"status": 1},
        ])
        accepted = self.workspace.command("kdialog", "--inputbox", "Size", "800x800")
        cancelled = self.workspace.command("kdialog", "--inputbox", "Quality", "75")
        exhausted = self.workspace.command("kdialog", "--inputbox", "Unexpected", "")
        self.assertEqual(accepted.stdout, "1600x1600\n")
        self.assertEqual(cancelled.returncode, 1)
        self.assertEqual(cancelled.stdout, "")
        self.assertNotEqual(exhausted.returncode, 0)

    def test_dispatcher_outputs_and_media_arguments_are_observable(self):
        source = self.workspace.ppm("input/space 雪.ppm")
        payload = self.workspace.png(".control/reference.png").read_bytes()
        self.workspace.respond("magick", output_base64=base64.b64encode(payload).decode())
        self.workspace.env["KIM_POLICY"] = "create"
        result = self.workspace.dispatch("convert", "png", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.outputs, {"input/space 雪.png": payload})
        media = [call for call in result.calls if call["tool"] == "magick"]
        self.assertEqual(media[0]["argv"][:2], ["--", str(source)])
        stage = Path(media[0]["argv"][-1])
        self.assertNotEqual(stage, source.with_suffix(".png"))
        self.assertEqual(stage.suffix, ".png")
        self.assertEqual(stage.parent.parent, source.parent)
        self.assertTrue(stage.parent.name.startswith(".kim6-stage."))
        self.assertEqual(list((self.workspace.control / "tmp").iterdir()), [])

    def test_unconfigured_media_and_desktop_tools_fail_without_forwarding(self):
        for tool in ("magick", "mogrify", "montage", "identify", "exiftool",
                     "ffmpeg", "xdg-email", "xdg-open", "kmail", "okular"):
            with self.subTest(tool=tool):
                result = self.workspace.command(tool, "unused")
                self.assertEqual(result.returncode, 97)
                self.assertIn("unconfigured external command", result.stderr)

    def test_outside_paths_and_symlink_escapes_are_refused(self):
        other = Workspace()
        self.addCleanup(other.close)
        sentinel = other.path("sentinel")
        sentinel.write_text("untouched")
        self.workspace.path("escape").symlink_to(other.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.workspace.path("escape/sentinel")
        with self.assertRaises(ValueError):
            self.workspace.dispatch("convert", "png", sentinel)
        for tool, args in (("rm", ["-f", str(sentinel)]),
                           ("cp", [str(sentinel), "copy"]),
                           ("touch", [str(sentinel)])):
            with self.subTest(tool=tool):
                result = self.workspace.command(tool, *args)
                self.assertEqual(result.returncode, 97)
        self.workspace.respond("exiftool", writes={str(sentinel): "bad"})
        self.assertEqual(self.workspace.command("exiftool").returncode, 97)
        self.assertEqual(sentinel.read_text(), "untouched")

    def test_runner_rejects_an_empty_selection(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("run.py")),
             "--pattern", "no_tests_exist_*.py"],
            cwd=self.workspace.root, env=self.workspace.env,
            capture_output=True, text=True, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No tests matched", result.stderr)

    def test_kconfig_adapter_isolated_from_other_workspaces(self):
        self.workspace.configure("NAME_AFFIX_POSITION", "prefix")
        args = ["--file", self.workspace.env["KIM_CONFIG_FILE"],
                "--group", "<default>", "--key", "NAME_AFFIX_POSITION"]
        configured = self.workspace.command("kreadconfig6", *args)
        self.assertEqual(configured.stdout, "prefix\n")
        other = Workspace()
        self.addCleanup(other.close)
        args[1] = other.env["KIM_CONFIG_FILE"]
        self.assertEqual(other.command("kreadconfig6", *args).stdout, "\n")

    def test_exiftool_adapter_can_write_owned_output_then_report_failure(self):
        self.workspace.respond("exiftool", writes={"out/result.jpg": "partial"},
                               stderr="injected failure\n", status=9)
        result = self.workspace.command("exiftool", "-all=", "fixture")
        self.assertEqual(result.returncode, 9)
        self.assertEqual(result.stderr, "injected failure\n")
        self.assertEqual(result.outputs, {"out/result.jpg": b"partial"})


if __name__ == "__main__":
    unittest.main()
