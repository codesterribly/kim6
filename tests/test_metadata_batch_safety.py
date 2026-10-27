"""Mixed-batch publication safety for copyright and camera-time edits."""

import shutil
import subprocess
import unittest

from support import Workspace


class MetadataBatchSafetyTests(unittest.TestCase):

    def setUp(self):
        if not shutil.which("exiftool") or not shutil.which("magick"):
            self.skipTest("ExifTool and ImageMagick required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        self.w.env["KIM_POLICY"] = "overwrite"

        self.good = self.w.jpeg("input/first.jpg")

        subprocess.run(
            [
                shutil.which("exiftool"),
                "-overwrite_original",
                "-Artist=Original Artist",
                "-DateTimeOriginal=2024:02:28 23:30:00",
                str(self.good),
            ],
            check=True,
            capture_output=True,
        )

        # Valid JPEG bytes under a RAW extension. KIM6 must refuse
        # metadata editing of this source, even if ExifTool can read it.
        self.unsupported = self.w.path("input/second.dng")
        self.unsupported.write_bytes(self.good.read_bytes())

    def tag(self, path, name):
        result = subprocess.run(
            [shutil.which("exiftool"), "-s3", name, str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def assert_clean(self):
        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )

    def test_copyright_overwrite_preserves_failed_second_file(self):
        before_bad = self.w.observe(self.unsupported)
        before_good = self.w.observe(self.good)

        result = self.w.dispatch(
            "copyright",
            "--creator", "Updated Artist",
            "--",
            self.good,
            self.unsupported,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.w.observe(self.good), before_good)
        self.assertEqual(
            self.tag(self.good, "-Artist"),
            "Updated Artist",
        )
        self.assertEqual(
            self.w.observe(self.unsupported),
            before_bad,
        )
        self.assert_clean()

    def test_timeshift_overwrite_preserves_failed_second_file(self):
        before_bad = self.w.observe(self.unsupported)
        before_good = self.w.observe(self.good)

        result = self.w.dispatch(
            "timeshift",
            "--offset", "+01:00:00",
            "--fields", "capture",
            "--",
            self.good,
            self.unsupported,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.w.observe(self.good), before_good)
        self.assertEqual(
            self.tag(self.good, "-DateTimeOriginal"),
            "2024:02:29 00:30:00",
        )
        self.assertEqual(
            self.w.observe(self.unsupported),
            before_bad,
        )
        self.assert_clean()

    def test_timeshift_create_keeps_sources_and_completed_output(self):
        self.w.env["KIM_POLICY"] = "create"

        before_good = self.w.observe(self.good)
        before_bad = self.w.observe(self.unsupported)

        result = self.w.dispatch(
            "timeshift",
            "--offset", "+01:00:00",
            "--fields", "capture",
            "--",
            self.good,
            self.unsupported,
        )

        output = self.good.with_name("first_timeshift.jpg")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.good), before_good)
        self.assertEqual(self.w.observe(self.unsupported), before_bad)

        self.assertTrue(output.is_file())
        self.assertEqual(
            self.tag(output, "-DateTimeOriginal"),
            "2024:02:29 00:30:00",
        )
        self.assertEqual(
            self.tag(self.good, "-DateTimeOriginal"),
            "2024:02:28 23:30:00",
        )
        self.assert_clean()


    def test_copyright_chmod_failure_preserves_overwrite_source(self):
        before = self.w.observe(self.good)
        self.w.respond("chmod", status=71, stderr="injected stage permission failure")

        result = self.w.dispatch("copyright", "--creator", "New Artist", "--", self.good)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.good), before)
        self.assertEqual(self.tag(self.good, "-Artist"), "Original Artist")
        self.assertTrue(any(call["tool"] == "chmod" for call in result.calls))
        self.assert_clean()

    def test_timeshift_touch_failure_preserves_overwrite_source(self):
        before = self.w.observe(self.good)
        self.w.respond("touch", status=72, stderr="injected stage timestamp failure")

        result = self.w.dispatch(
            "timeshift", "--offset", "+01:00:00", "--fields", "capture",
            "--", self.good,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.good), before)
        self.assertEqual(self.tag(self.good, "-DateTimeOriginal"), "2024:02:28 23:30:00")
        self.assertTrue(any(call["tool"] == "touch" and "-r" in call["argv"]
                            for call in result.calls))
        self.assert_clean()

    def test_failed_create_keeps_occupied_destination_and_source(self):
        self.w.env["KIM_POLICY"] = "create"
        target = self.good.with_name("first_copyright.jpg")
        target.write_bytes(b"unrelated existing destination")
        before_source = self.w.observe(self.good)
        before_target = self.w.observe(target)
        self.w.respond("chmod", status=73, stderr="injected stage permission failure")

        result = self.w.dispatch("copyright", "--creator", "New Artist", "--", self.good)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.good), before_source)
        self.assertEqual(self.w.observe(target), before_target)
        self.assertFalse(self.good.with_name("first_copyright-1.jpg").exists())
        self.assert_clean()

    def test_stage_failure_in_batch_does_not_block_later_valid_photo(self):
        second = self.w.path("input/second-valid.jpg")
        second.write_bytes(self.good.read_bytes())
        before_first = self.w.observe(self.good)
        self.w.sequence("chmod", [
            {"status": 74, "stderr": "injected first-item permission failure"},
            {"passthrough": True},
        ])

        result = self.w.dispatch(
            "copyright", "--creator", "New Artist", "--", self.good, second,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.good), before_first)
        self.assertEqual(self.tag(self.good, "-Artist"), "Original Artist")
        self.assertEqual(self.tag(second, "-Artist"), "New Artist")
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
