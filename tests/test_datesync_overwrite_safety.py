"""Overwrite-safety tests for direct filesystem timestamp edits."""

import os
import shutil
import subprocess
import unittest

from support import Workspace


class DateSyncOverwriteSafetyTests(unittest.TestCase):

    def setUp(self):
        exiftool = shutil.which("exiftool")
        if not exiftool or not shutil.which("magick"):
            self.skipTest("ExifTool and ImageMagick are required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.env["TZ"] = "America/New_York"
        self.w.approve_overwrite()
        self.w.use_real_metadata_tools()

        self.source = self.w.jpeg("input/date-rollback.jpg")

        subprocess.run(
            [
                exiftool,
                "-overwrite_original",
                "-DateTimeOriginal=2024:02:29 23:59:58",
                "-SubSecTimeOriginal=123456789",
                str(self.source),
            ],
            check=True,
            capture_output=True,
        )

        # Existing filesystem time differs from EXIF capture time.
        os.utime(
            self.source,
            ns=(1_700_000_000_123_456_789,
                1_700_000_001_987_654_321),
        )

    def run_sync(self):
        return self.w.dispatch(
            "datesync",
            "--direction",
            "exif-to-file",
            "--",
            self.source,
        )

    def touch_calls(self, result):
        return [
            call["argv"]
            for call in result.calls
            if call["tool"] == "touch"
        ]

    def test_failed_mtime_write_preserves_original(self):
        before = self.w.observe(self.source)

        self.w.sequence("touch", [
            {"status": 71, "stderr": "injected mtime failure"},
            {"passthrough": True},
            {"passthrough": True},
        ])

        result = self.run_sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)

        calls = self.touch_calls(result)
        self.assertEqual(len(calls), 3, calls)
        self.assertEqual(
            [args[0] for args in calls],
            ["-m", "-m", "-a"],
        )

        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )

    def test_failed_atime_restoration_rolls_back_mtime(self):
        before = self.w.observe(self.source)

        self.w.sequence("touch", [
            {"passthrough": True},
            {"status": 72, "stderr": "injected atime failure"},
            {"passthrough": True},
            {"passthrough": True},
        ])

        result = self.run_sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)

        calls = self.touch_calls(result)
        self.assertEqual(len(calls), 4, calls)
        self.assertEqual(
            [args[0] for args in calls],
            ["-m", "-a", "-m", "-a"],
        )

        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )


if __name__ == "__main__":
    unittest.main()
