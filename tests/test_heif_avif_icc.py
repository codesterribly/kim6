"""ICC preservation across AVIF/HEIC/HEIF encode and decode."""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class HeifAvifICCConversionTests(unittest.TestCase):
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

        ppm = self.w.ppm("input/profile-source.ppm")
        self.source = self.w.path("input/profile-source.tif")
        subprocess.run(
            [self.magick, str(ppm), "-profile", str(self.adobe), str(self.source)],
            check=True, capture_output=True, timeout=15,
        )
        self.source_icc = self.icc(self.source)
        self.assertTrue(self.source_icc, "TIFF fixture must contain Adobe RGB ICC")
        self.source_before = self.w.observe(self.source)

        self.formats = subprocess.run(
            [self.magick, "-list", "format"],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout

    def icc(self, path):
        return subprocess.run(
            [self.exiftool, "-b", "-ICC_Profile", str(path)],
            check=True, capture_output=True, timeout=15,
        ).stdout

    def assert_coder_available(self, coder):
        available = any(
            re.search(r"^\s*" + coder + r"\*?\s", line)
            and len(line.split()) > 2
            and "w" in line.split()[2]
            for line in self.formats.splitlines()
        )
        if not available:
            self.skipTest(f"ImageMagick {coder} encoder unavailable")

    def check_format(self, extension, coder):
        self.assert_coder_available(coder)

        # Encode from profiled TIFF.
        encoded = self.source.with_suffix("." + extension)
        result = self.w.dispatch("convert", extension, self.source)

        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertTrue(encoded.is_file())
        self.assertEqual(self.icc(encoded), self.source_icc)
        self.assertEqual(self.w.observe(self.source), self.source_before)

        # Decode to PNG and verify the ICC survives the return trip.
        encoded_before = self.w.observe(encoded)
        decoded = encoded.with_suffix(".png")
        result = self.w.dispatch("convert", "png", encoded)

        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertTrue(decoded.is_file())
        self.assertEqual(self.icc(decoded), self.source_icc)
        self.assertEqual(self.w.observe(encoded), encoded_before)
        self.assertEqual(self.w.observe(self.source), self.source_before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_avif_profile_survives_encode_and_decode(self):
        self.check_format("avif", "AVIF")

    def test_heic_profile_survives_encode_and_decode(self):
        self.check_format("heic", "HEIC")

    def test_heif_profile_survives_encode_and_decode(self):
        self.check_format("heif", "HEIC")


if __name__ == "__main__":
    unittest.main()
