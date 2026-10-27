"""Targeted animation publication safeguards (not run during patch preparation)."""
import base64
import shutil
import subprocess
import unittest
from support import Workspace


class AnimationContractTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"

    def assert_clean(self):
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.w.root.rglob(".kim6-publish.lock")))
        self.assertEqual(list((self.w.control / "tmp").iterdir()), [])

    def _assert_multiframe_sequence_rejected(self, coder, extension):
        source = self.w.ppm("input/collection.ppm")
        before = self.w.observe(source)
        self.w.respond("magick", stdout=f"{coder}* delegate rw+ multi-image\n")
        self.w.respond("identify", stdout=f"{coder}|3|2\n{coder}|3|2\n")
        result = self.w.dispatch("convert", extension, source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(source.with_suffix("." + extension).exists())
        self.assertFalse(any(call["tool"] == "magick" and "-list" not in call["argv"]
                             for call in result.calls))
        self.assertTrue(any("multi-image AVIF/HEIC" in " ".join(call["argv"])
                            for call in result.calls if call["tool"] == "kdialog"))
        self.assertEqual(self.w.observe(source), before)
        self.assert_clean()

    def test_multiframe_avif_fails_before_encoding(self):
        self._assert_multiframe_sequence_rejected("AVIF", "avif")

    def test_multiframe_heic_fails_before_encoding(self):
        self._assert_multiframe_sequence_rejected("HEIC", "heic")

    def test_webp_changed_loop_count_is_not_published(self):
        magick = shutil.which("magick")
        if not magick:
            self.skipTest("ImageMagick unavailable")
        first = self.w.ppm("input/webp-1.ppm")
        second = self.w.ppm("input/webp-2.ppm")
        # Distinct pixels prevent WebP from collapsing two identical frames.
        # Alter an existing pixel without rebuilding the PPM header.
        pixels = bytearray(second.read_bytes())
        pixels[-1] ^= 0xFF
        second.write_bytes(pixels)
        source = self.w.path("input/animated.webp")
        result = subprocess.run(
            [magick, "-delay", "12", str(first), "-delay", "34", str(second),
             "-loop", "3", "WEBP:" + str(source)],
            capture_output=True, timeout=25,
        )
        if result.returncode != 0:
            self.skipTest("ImageMagick WebP encoder unavailable")
        raw = bytearray(source.read_bytes())
        if raw.count(b"ANMF") < 2 or b"ANIM" not in raw:
            self.skipTest("Animated WebP fixture not supported by encoder")
        before = self.w.observe(source)
        anim = raw.index(b"ANIM") + 8
        raw[anim + 4] ^= 1  # modify ANIM loop count, leave image frames alone
        self.w.respond_to("magick", str(source),
                          {"output_base64": base64.b64encode(raw).decode()})
        converted = self.w.dispatch("convert", "webp", source)
        self.assertNotEqual(converted.returncode, 0)
        self.assertFalse(source.with_name("animated_1.webp").exists())
        self.assertEqual(self.w.observe(source), before)
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
