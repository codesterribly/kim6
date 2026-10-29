"""Real TIFF metadata preservation and publication regressions."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class TIFFMetadataSafetyTests(unittest.TestCase):

    def setUp(self):
        self.magick = shutil.which("magick")
        self.exiftool = shutil.which("exiftool")
        self.identify = shutil.which("identify")

        if not all((self.magick, self.exiftool, self.identify)):
            self.skipTest("ImageMagick and ExifTool required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        # Selective GPS uses the general metadata adapter, not the
        # legacy full-strip-only ExifTool adapter.
        self.w.env["KIM_TIFF_VERIFY"] = "native"
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()

        pixels = self.w.ppm("input/pixels.ppm")
        self.source = self.w.path("input/landscape.tiff")

        subprocess.run(
            [
                self.magick,
                str(pixels),
                "-compress", "LZW",
                str(self.source),
            ],
            check=True, capture_output=True, timeout=30,
        )

        subprocess.run(
            [
                self.exiftool,
                "-overwrite_original",
                "-GPSLatitude=42.5",
                "-GPSLatitudeRef=N",
                "-GPSLongitude=71.25",
                "-GPSLongitudeRef=W",
                "-Artist=Photographer",
                "-Copyright=All rights reserved",
                "-XMP-dc:Description=Landscape caption",
                str(self.source),
            ],
            check=True, capture_output=True, timeout=30,
        )

    def tag(self, path, name):
        return subprocess.run(
            [self.exiftool, "-s3", name, str(path)],
            check=True, capture_output=True,
            text=True, timeout=30,
        ).stdout.strip()

    def pixels(self, path):
        return subprocess.run(
            [
                self.identify,
                "-format", "%#",
                str(path),
            ],
            check=True, capture_output=True, timeout=30,
        ).stdout

    def run_strip(self, mode):
        return self.w.dispatch(
            "stripmeta", "--mode", mode,
            "--", self.source,
        )

    def derived(self):
        paths = [
            p for p in self.source.parent.glob("*.tiff")
            if p != self.source
        ]
        self.assertEqual(len(paths), 1, paths)
        return paths[0]

    def assert_clean(self):
        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )

    def assert_rights(self, path):
        self.assertEqual(
            self.tag(path, "-Artist"), "Photographer"
        )
        self.assertEqual(
            self.tag(path, "-Copyright"),
            "All rights reserved",
        )
        self.assertEqual(
            self.tag(path, "-XMP-dc:Description"),
            "Landscape caption",
        )

    def assert_gps_removed(self, path):
        for tag in (
            "-GPSLatitude", "-GPSLongitude",
            "-GPSLatitudeRef", "-GPSLongitudeRef",
        ):
            self.assertEqual(
                self.tag(path, tag), "", (path, tag)
            )

    def test_gps_overwrite_preserves_pixels_and_rights(self):
        self.w.approve_overwrite()

        original_pixels = self.pixels(self.source)
        self.assertNotEqual(
            self.tag(self.source, "-GPSLatitude"), ""
        )
        self.assert_rights(self.source)

        result = self.run_strip("gps")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )
        self.assert_gps_removed(self.source)
        self.assert_rights(self.source)
        self.assertEqual(
            self.pixels(self.source), original_pixels
        )
        self.assert_clean()

    def test_gps_create_preserves_original(self):
        self.w.env["KIM_POLICY"] = "create"

        before = self.w.observe(self.source)
        original_pixels = self.pixels(self.source)

        result = self.run_strip("gps")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        derived = self.derived()

        self.assertEqual(
            self.w.observe(self.source), before
        )
        self.assertEqual(
            self.pixels(derived), original_pixels
        )
        self.assert_gps_removed(derived)
        self.assert_rights(derived)
        self.assert_clean()

    def test_overwrite_preserves_mtime_and_permissions(self):
        self.w.approve_overwrite()

        os.chmod(self.source, 0o640)
        stamp = 1_600_000_001_234_567_891
        os.utime(
            self.source,
            ns=(stamp, stamp),
        )

        original_pixels = self.pixels(self.source)

        result = self.run_strip("gps")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )
        self.assertEqual(
            self.source.stat().st_mtime_ns, stamp
        )
        self.assertEqual(
            self.source.stat().st_mode & 0o777,
            0o640,
        )
        self.assertEqual(
            self.pixels(self.source), original_pixels
        )
        self.assert_gps_removed(self.source)
        self.assert_clean()

    def test_full_strip_preserves_decoded_pixels(self):
        self.w.env["KIM_POLICY"] = "create"

        before = self.w.observe(self.source)
        original_pixels = self.pixels(self.source)

        result = self.run_strip("all")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        derived = self.derived()

        self.assertEqual(
            self.w.observe(self.source), before
        )
        self.assertEqual(
            self.pixels(derived), original_pixels
        )
        self.assert_clean()

    def test_corrupted_tiff_preserves_original(self):
        self.w.env["KIM_POLICY"] = "create"

        self.source.write_bytes(
            b"II*\x00\x08\x00\x00\x00\xff\xff\xff"
        )
        before = self.w.observe(self.source)

        result = self.run_strip("all")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.w.observe(self.source), before
        )
        self.assertEqual(
            list(self.source.parent.glob("*.tiff")),
            [self.source],
        )
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
