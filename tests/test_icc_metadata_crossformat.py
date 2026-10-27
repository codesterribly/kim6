"""Cross-format ICC and selective-metadata regressions for KIM6."""

import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class ICCMetadataCrossFormatTests(unittest.TestCase):
    def setUp(self):
        self.magick = shutil.which("magick")
        self.exiftool = shutil.which("exiftool")
        self.adobe = Path("/usr/share/color/icc/colord/AdobeRGB1998.icc")
        if not self.magick or not self.exiftool or not self.adobe.is_file():
            self.skipTest("ImageMagick, ExifTool and Adobe RGB ICC profile required")
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"

    def profile(self, path):
        return subprocess.run(
            [self.exiftool, "-b", "-ICC_Profile", str(path)],
            check=True, capture_output=True, timeout=15,
        ).stdout

    def tag(self, path, name):
        return subprocess.run(
            [self.exiftool, "-s3", name, str(path)],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip()

    def fixture(self, name, extension):
        pixels = self.w.ppm(f"input/{name}.ppm")
        result = self.w.path(f"input/{name}.{extension}")
        subprocess.run(
            [self.magick, str(pixels), "-profile", str(self.adobe), str(result)],
            check=True, capture_output=True, timeout=15,
        )
        self.assertTrue(self.profile(result), "fixture must carry an embedded ICC profile")
        return result

    def assert_no_stages(self):
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_conversion_preserves_profile_in_png_and_webp(self):
        source = self.fixture("convert-source", "tif")
        original = self.w.observe(source)
        icc = self.profile(source)
        self.w.use_real_conversion()
        for extension in ("png", "webp"):
            with self.subTest(format=extension):
                result = self.w.dispatch("convert", extension, source)
                output = source.with_suffix("." + extension)
                self.assertEqual(result.returncode, 0, (result.stderr, result.events))
                self.assertTrue(output.is_file())
                self.assertEqual(self.profile(output), icc,
                                 f"{extension.upper()} must retain the input ICC profile")
                self.assertEqual(self.w.observe(source), original)
                self.assert_no_stages()

    def test_webexport_preserve_profile_across_tiff_to_webp(self):
        source = self.fixture("export-source", "tif")
        original = self.w.observe(source)
        icc = self.profile(source)
        output_dir = self.w.path("web-exports")
        output_dir.mkdir()
        self.w.use_real_web_email()
        result = self.w.dispatch(
            "webexport", "--size", "3x2", "--format", "webp",
            "--color", "preserve", "--output-dir", output_dir, "--", source,
        )
        output = output_dir / "export-source_web.webp"
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertTrue(output.is_file())
        self.assertEqual(self.profile(output), icc)
        self.assertEqual(self.w.observe(source), original)
        self.assert_no_stages()

    def test_png_gps_removal_preserves_icc_pixels_and_caption(self):
        source = self.fixture("gps-source", "png")
        subprocess.run(
            [self.exiftool, "-overwrite_original",
             "-XMP-exif:GPSLatitude=42.5", "-XMP-exif:GPSLongitude=3.25",
             "-XMP-dc:Description=Keep this caption", str(source)],
            check=True, capture_output=True, timeout=15,
        )
        self.assertTrue(self.tag(source, "-XMP-exif:GPSLatitude"),
                        "fixture must contain GPS metadata before removal")
        before_icc = self.profile(source)
        before_pixels = subprocess.run(
            [self.magick, str(source), "-format", "%#", "info:"],
            check=True, capture_output=True, timeout=15,
        ).stdout
        before = self.w.observe(source)
        self.w.approve_overwrite()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        result = self.w.dispatch("stripmeta", "--mode", "gps", "--", source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertEqual(self.tag(source, "-XMP-exif:GPSLatitude"), "")
        self.assertEqual(self.tag(source, "-XMP-exif:GPSLongitude"), "")
        self.assertEqual(self.tag(source, "-XMP-dc:Description"), "Keep this caption")
        self.assertEqual(self.profile(source), before_icc)
        after_pixels = subprocess.run(
            [self.magick, str(source), "-format", "%#", "info:"],
            check=True, capture_output=True, timeout=15,
        ).stdout
        self.assertEqual(after_pixels, before_pixels)
        self.assertEqual(source.stat().st_mtime_ns, before.mtime_ns)
        self.assert_no_stages()

    def test_png_ai_removal_preserves_non_ai_rights_and_icc(self):
        self.w.approve_overwrite()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        for source_kind in ("negativeFilm", "trainedAlgorithmicMedia"):
            with self.subTest(digital_source_type=source_kind):
                source = self.fixture(f"ai-{source_kind}", "png")
                subprocess.run(
                    [self.exiftool, "-overwrite_original",
                     f"-XMP-iptcExt:DigitalSourceType={source_kind}",
                     "-XMP-iptcExt:AIPromptInformation=private prompt",
                     "-XMP-dc:Description=Preserve this caption",
                     str(source)],
                    check=True, capture_output=True, timeout=15,
                )
                self.assertEqual(
                    self.tag(source, "-XMP-iptcExt:AIPromptInformation"),
                    "private prompt", "fixture must contain an AI prompt",
                )
                icc = self.profile(source)
                before = self.w.observe(source)
                result = self.w.dispatch("stripmeta", "--mode", "ai", "--", source)
                self.assertEqual(result.returncode, 0, (result.stderr, result.events))
                self.assertEqual(self.tag(source, "-XMP-iptcExt:AIPromptInformation"), "")
                expected = "negativeFilm" if source_kind == "negativeFilm" else ""
                self.assertEqual(self.tag(source, "-XMP-iptcExt:DigitalSourceType"), expected)
                self.assertEqual(self.tag(source, "-XMP-dc:Description"),
                                 "Preserve this caption")
                self.assertEqual(self.profile(source), icc)
                self.assertEqual(source.stat().st_mtime_ns, before.mtime_ns)
                self.assert_no_stages()


if __name__ == "__main__":
    unittest.main()
