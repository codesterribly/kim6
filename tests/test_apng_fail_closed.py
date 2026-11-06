"""Animated APNG must not be silently flattened by resize or web export."""

import shutil
import sys
import subprocess
import unittest

from support import Workspace


class APNGFailClosedTests(unittest.TestCase):

    def setUp(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("FFmpeg required for real APNG fixture")

        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"
        self.w.env["KIM_WEB_COLOR_MODE"] = "preserve"

        self.source = self.w.path("input/moving.png")
        self.source.parent.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi",
                "-i", "testsrc2=size=16x16:rate=2",
                "-frames:v", "2",
                "-plays", "0",
                "-f", "apng",
                str(self.source),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )

        self.before = self.w.observe(self.source)

        # Simulate only the Qt review boundaries exercised by this suite.
        # Real processing helpers still run through the test adapters.
        python_shim = self.w.bin / "python3"
        python_shim.write_text(
            f"#!{sys.executable}\n" + """
import os
from pathlib import Path
import sys

helper = Path(sys.argv[1]).name if len(sys.argv) > 1 else ""
kind = sys.argv[2] if len(sys.argv) > 2 else ""
control = Path(os.environ["KIM_TEST_ROOT"]) / ".control"
nul = bytes([0])

if helper == "kim_action_dialog.py":
    if kind == "resize":
        if sys.argv[4:6] != ["--preset", "8x8"]:
            sys.exit(97)
        Path(sys.argv[3]).write_bytes(b"8x8" + nul)
        sys.exit(0)

    if kind == "resize-output-review":
        fields = Path(sys.argv[3]).read_bytes().split(nul)
        if (b"Blocked" not in fields
                or b"Animated PNG cannot be resized safely." not in fields):
            sys.exit(97)
        (control / "apng-resize-blocked").write_text("blocked")
        # Bypass the UI to verify the processing engine also refuses APNG.
        sys.exit(0)

    if kind == "email-options":
        if sys.argv[4] not in ("8x8", "full"):
            sys.exit(97)
        Path(sys.argv[3]).write_bytes(
            sys.argv[4].encode("ascii") + nul + b"xdg-email" + nul
        )
        sys.exit(0)

    if kind == "email-ready-review":
        if not Path(sys.argv[3]).is_file() or sys.argv[4] != "xdg-email":
            sys.exit(97)
        sys.exit(0)

if helper == "kim_webexport_review.py":
    fields = Path(sys.argv[2]).read_bytes().split(nul)
    if b"Animated PNG export is unsupported" not in fields:
        sys.exit(97)
    (control / "apng-webexport-blocked").write_text("blocked")
    sys.exit(130)

os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
"""
        )
        python_shim.chmod(0o700)

    def assert_refused(self, command, *args):
        result = self.w.dispatch(command, *args)

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assertEqual(self.w.observe(self.source), self.before)
        self.assertFalse(result.outputs)
        self.assertFalse(any(
            call["tool"] == "magick"
            for call in result.calls
        ))
        self.assertFalse(list(
            self.w.root.rglob(".kim6-stage.*")
        ))

        if command == "webexport":
            self.assertTrue(
                (self.w.control / "apng-webexport-blocked").is_file(),
                result.events,
            )
        else:
            self.assertTrue(
                (self.w.control / "apng-resize-blocked").is_file(),
                result.events,
            )
            self.assertTrue(any(
                "Animated PNG" in " ".join(call["argv"])
                for call in result.calls
                if call["tool"] == "kdialog"
            ), result.events)

    def test_resize_refuses_real_animated_png(self):
        self.assert_refused(
            "resize", "--size", "8x8", "--", self.source
        )

    def test_resize_refuses_apng_extension(self):
        alternate = self.w.path("input/moving.apng")
        alternate.write_bytes(self.source.read_bytes())

        self.source = alternate
        self.before = self.w.observe(alternate)

        self.assert_refused(
            "resize", "--size", "8x8", "--", alternate
        )

    def test_email_resize_refuses_real_animated_png(self):
        result = self.w.dispatch(
            "resizeandsend", "--size", "8x8", "--", self.source,
        )
        self.assertNotEqual(result.returncode, 0, result.events)
        self.assertEqual(self.w.observe(self.source), self.before)
        self.assertFalse(any(
            c["tool"] in ("magick", "identify") for c in result.calls
        ))
        self.assertFalse(result.outputs)
        storage = self.w.control / "data" / "kim6" / "email-attachments"
        self.assertFalse(list(storage.glob("*")))
        self.assertTrue(any(
            "Animated PNG email resizing" in str(event)
            for event in result.events
        ), result.events)

    def test_email_full_size_keeps_apng_bytes(self):
        self.w.use_real_web_email()
        result = self.w.dispatch(
            "resizeandsend", "--size", "full", "--", self.source,
        )
        self.assertEqual(
            result.returncode, 0, (result.stderr, result.events)
        )
        self.assertEqual(self.w.observe(self.source), self.before)
        storage = self.w.control / "data" / "kim6" / "email-attachments"
        attachments = list(storage.rglob("moving__send_1.png"))
        self.assertEqual(len(attachments), 1)
        self.assertEqual(
            attachments[0].read_bytes(), self.source.read_bytes()
        )

    def test_webexport_refuses_animated_png(self):
        destination = self.w.path("exports")
        destination.mkdir()

        self.w.respond(
            "identify",
            stdout="PNG|16|16|TopLeft|1|sRGB\n",
        )

        self.assert_refused(
            "webexport",
            "--output-dir", destination,
            "--size", "8x8",
            "--quality", "80",
            "--format", "keep",
            "--", self.source,
        )


if __name__ == "__main__":
    unittest.main()
