"""Animated APNG must not be silently flattened by resize or web export."""

import shutil
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
