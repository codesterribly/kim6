"""Reject conversion outputs that silently discard an embedded ICC profile."""

import base64
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class ConversionICCLossTests(unittest.TestCase):
    def setUp(self):
        self.magick = shutil.which("magick")
        self.exiftool = shutil.which("exiftool")
        self.adobe = Path("/usr/share/color/icc/colord/AdobeRGB1998.icc")
        if not self.magick or not self.exiftool or not self.adobe.is_file():
            self.skipTest("ImageMagick, ExifTool, and Adobe RGB ICC profile required")

        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"
        self.w.use_real_conversion()

        self.ppm = self.w.ppm("input/colors.ppm")
        self.source = self.w.path("input/colors.tif")
        subprocess.run(
            [self.magick, str(self.ppm), "-profile", str(self.adobe), str(self.source)],
            check=True, capture_output=True, timeout=20,
        )
        self.assertTrue(self.icc(self.source), "source must have an embedded ICC profile")
        self.before = self.w.observe(self.source)

        self.formats = subprocess.run(
            [self.magick, "-list", "format"],
            check=True, capture_output=True, text=True, timeout=20,
        ).stdout

    def icc(self, path):
        return subprocess.run(
            [self.exiftool, "-b", "-ICC_Profile", str(path)],
            check=True, capture_output=True, timeout=20,
        ).stdout

    def verify_rejection(self, extension, coder):
        if not any(
            re.search(r"^\s*" + coder + r"\*?\s", line)
            and len(line.split()) > 2
            and "w" in line.split()[2]
            for line in self.formats.splitlines()
        ):
            self.skipTest(f"ImageMagick {coder} encoder unavailable")

        # Produce valid encoded bytes from the same pixels, but without the
        # Adobe RGB profile. Inject them as a successful encoder result.
        fake_output = self.w.path(f"input/encoder-without-icc.{extension}")
        subprocess.run(
            [self.magick, str(self.ppm), "-strip", str(fake_output)],
            check=True, capture_output=True, timeout=30,
        )
        self.assertFalse(self.icc(fake_output), "injected output must lack ICC")

        self.w.respond_to(
            "magick", str(self.source),
            {"output_base64": base64.b64encode(fake_output.read_bytes()).decode("ascii")},
        )
        destination = self.source.with_suffix(f".{extension}")
        result = self.w.dispatch("convert", extension, self.source)

        self.assertNotEqual(result.returncode, 0, "silent ICC loss must fail conversion")
        self.assertFalse(destination.exists(), "ICC-less conversion must not be published")
        self.assertEqual(self.w.observe(self.source), self.before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_avif_encoder_dropping_icc_fails_closed(self):
        self.verify_rejection("avif", "AVIF")

    def test_heic_encoder_dropping_icc_fails_closed(self):
        self.verify_rejection("heic", "HEIC")

    def test_heif_encoder_dropping_icc_fails_closed(self):
        self.verify_rejection("heif", "HEIC")


    def test_png_encoder_dropping_icc_fails_closed(self):
        self.verify_rejection("png", "PNG")

    def test_webp_encoder_dropping_icc_fails_closed(self):
        self.verify_rejection("webp", "WEBP")


if __name__ == "__main__":
    unittest.main()
