"""Conversion collision, source ownership and decoded-format safety."""

import base64
import shutil
import subprocess
import unittest

from support import Workspace


class ConversionCollisionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.approve_overwrite()

    def test_uppercase_same_format_noop_never_touches_lowercase_neighbor(self):
        source = self.w.jpeg("input/photo.JPG")
        neighbor = self.w.jpeg("input/photo.jpg")
        before_source = self.w.observe(source)
        before_neighbor = self.w.observe(neighbor)

        result = self.w.dispatch("convert", "jpg", source)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(source), before_source)
        self.assertEqual(self.w.observe(neighbor), before_neighbor)
        self.assertFalse(any(
            call["tool"] == "magick" for call in result.calls
        ))

    def test_uppercase_reencode_targets_selected_not_lowercase_neighbor(self):
        source = self.w.jpeg("input/photo.JPG")
        neighbor = self.w.jpeg("input/photo.jpg")
        before_source = self.w.observe(source)
        before_neighbor = self.w.observe(neighbor)

        self.w.use_real_conversion()
        self.w.use_real_mv()
        self.w.respond_to("exiftool", "-ICC_Profile", {"stdout": ""})
        self.w.respond(
            "magick",
            output_base64=base64.b64encode(source.read_bytes()).decode(),
        )

        result = self.w.dispatch(
            "convert", "--format", "jpg",
            "--jpeg-progressive", "--", source,
        )

        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertEqual(self.w.observe(neighbor), before_neighbor)
        self.assertNotEqual(self.w.observe(source).inode, before_source.inode)

    def test_mislabeled_image_is_reencoded_instead_of_false_success(self):
        source = self.w.png("input/incorrect.jpg")
        before = self.w.observe(source)

        self.w.use_real_conversion()
        self.w.use_real_mv()
        self.w.respond_to("exiftool", "-ICC_Profile", {"stdout": ""})

        reference = self.w.jpeg(".control/reference.jpg")
        self.w.respond(
            "magick",
            output_base64=base64.b64encode(reference.read_bytes()).decode(),
        )

        result = self.w.dispatch("convert", "jpg", source)

        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertNotEqual(self.w.observe(source).inode, before.inode)

        actual = subprocess.run(
            [shutil.which("identify"), "-format", "%m", str(source)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        self.assertEqual(actual, "JPEG")

    def test_create_numbers_occupied_files_and_dangling_symlinks(self):
        self.w.env["KIM_POLICY"] = "create"

        source = self.w.jpeg("input/photo.JPG")
        occupied = self.w.jpeg("input/photo.jpg")
        dangling = self.w.path("input/photo_1.jpg")
        dangling.symlink_to("absent.jpg")

        before = {
            path: self.w.observe(path)
            for path in (source, occupied, dangling)
        }

        self.w.use_real_conversion()
        self.w.respond_to("exiftool", "-ICC_Profile", {"stdout": ""})

        result = self.w.dispatch("convert", "jpg", source)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.w.path("input/photo_2.jpg").is_file())

        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state)

    def test_overwrite_rejects_hardlinked_selected_source(self):
        source = self.w.jpeg("input/photo.JPG")
        other = self.w.path("input/alias.bin")
        other.hardlink_to(source)

        before = self.w.observe(source)
        result = self.w.dispatch("convert", "jpg", source)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(source), before)


if __name__ == "__main__":
    unittest.main()
