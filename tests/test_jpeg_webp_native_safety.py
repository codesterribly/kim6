"""Native JPEG/WebP atomic-publication safety regressions."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from support import Workspace


class NativeSafetyTests(unittest.TestCase):

    def setUp(self):
        if not shutil.which("exiftool"):
            self.skipTest("ExifTool required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.env["KIM_JPEG_WEBP_ENGINE"] = "native"
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()

    def run_strip(self, source):
        return self.w.dispatch(
            "stripmeta", "--mode", "all",
            "--", source,
        )

    def assert_clean(self):
        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )

    def malicious_engine(self, body):
        engine = (
            self.w.control
            / "kim_jpeg_webp_metadata.py"
        )

        engine.write_text(
            "import argparse\n"
            "p=argparse.ArgumentParser()\n"
            "p.add_argument('--format')\n"
            "p.add_argument('--input')\n"
            "p.add_argument('--output')\n"
            "a=p.parse_args()\n"
            "from pathlib import Path\n"
            + body
        )

    def test_corrupt_native_output_refuses_overwrite(self):
        source = self.w.jpeg("input/corrupt.jpg")
        self.w.approve_overwrite()

        before = self.w.observe(source)

        self.malicious_engine(
            "Path(a.output).write_bytes(b'not a JPEG')\n"
            "print('removed=1 bytes=100->10')\n"
        )

        result = self.run_strip(source)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.w.observe(source), before
        )
        self.assert_clean()

    def test_partial_native_output_refuses_create(self):
        source = self.w.jpeg("input/partial.jpg")
        self.w.env["KIM_POLICY"] = "create"

        before = self.w.observe(source)

        self.malicious_engine(
            "Path(a.output).write_bytes("
            "Path(a.input).read_bytes()[:24])\n"
            "print('removed=1 bytes=409->24')\n"
        )

        result = self.run_strip(source)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.w.observe(source), before
        )
        self.assertFalse(
            source.with_name(
                "partial_stripped.jpg"
            ).exists()
        )
        self.assert_clean()

    def test_native_engine_failure_preserves_original(self):
        source = self.w.jpeg("input/failure.jpg")
        self.w.approve_overwrite()

        before = self.w.observe(source)

        self.malicious_engine(
            "Path(a.output).write_bytes(b'partial')\n"
            "raise SystemExit(7)\n"
        )

        result = self.run_strip(source)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.w.observe(source), before
        )
        self.assert_clean()

    def test_native_jpeg_overwrite_preserves_properties(self):
        source = self.w.jpeg("input/overwrite.jpg")
        self.w.approve_overwrite()

        os.chmod(source, 0o640)
        before = self.w.observe(source)
        original = source.read_bytes()

        result = self.run_strip(source)

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        self.assertEqual(
            source.stat().st_mtime_ns,
            before.mtime_ns,
        )
        self.assertEqual(
            source.stat().st_mode & 0o777,
            0o640,
        )
        self.assertEqual(
            source.read_bytes(), original
        )
        self.assert_clean()

    def test_native_webp_create_preserves_original(self):
        magick = shutil.which("magick")
        if not magick:
            self.skipTest("ImageMagick required")

        pixels = self.w.ppm("input/webp-source.ppm")
        source = self.w.path("input/native.webp")

        subprocess.run(
            [magick, str(pixels), str(source)],
            check=True,
            capture_output=True,
            timeout=20,
        )

        self.w.env["KIM_POLICY"] = "create"

        before = self.w.observe(source)

        result = self.run_strip(source)

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        target = source.with_name(
            "native_stripped.webp"
        )

        self.assertTrue(target.is_file())
        self.assertEqual(
            self.w.observe(source), before
        )

        self.assert_clean()

    def test_native_jpeg_icc_preserved(self):
        magick = shutil.which("magick")
        exiftool = shutil.which("exiftool")
        profile = Path(
            "/usr/share/color/icc/colord/AdobeRGB1998.icc"
        )

        if (
            not magick
            or not exiftool
            or not profile.is_file()
        ):
            self.skipTest(
                "Adobe RGB profile and tools required"
            )

        pixels = self.w.ppm("input/icc.ppm")
        source = self.w.path("input/icc.jpg")

        subprocess.run(
            [
                magick,
                str(pixels),
                "-profile",
                str(profile),
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )

        def icc(path):
            return subprocess.run(
                [
                    exiftool,
                    "-b",
                    "-ICC_Profile",
                    str(path),
                ],
                check=True,
                capture_output=True,
                timeout=20,
            ).stdout

        original_icc = icc(source)
        self.assertTrue(original_icc)

        self.w.env["KIM_POLICY"] = "create"
        before = self.w.observe(source)

        result = self.run_strip(source)

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        target = source.with_name(
            "icc_stripped.jpg"
        )

        self.assertTrue(target.is_file())
        self.assertEqual(
            icc(target), original_icc
        )
        self.assertEqual(
            self.w.observe(source), before
        )
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
