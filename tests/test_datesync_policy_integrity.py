"""Date synchronization cannot bypass original-file authorization."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from support import Workspace


SCRIPT = Path(__file__).resolve().parents[1] / "src/bin/kim_all"


class DateSyncPolicyIntegrityTests(unittest.TestCase):

    def test_direct_timestamp_write_has_identity_guard(self):
        source = SCRIPT.read_text()
        start = source.index("action_datesync() {")
        end = source.index("\naction_webexport() {", start)
        body = source[start:end]

        self.assertIn("original_identities=()", body)
        self.assertIn(
            "selected original changed before processing", body
        )
        self.assertIn(
            "selected original changed before timestamp update", body
        )
        self.assertIn(
            'if [ "$policy" = overwrite ]; then', body
        )

    def setUp(self):
        if not shutil.which("exiftool") or not shutil.which("magick"):
            self.skipTest("ExifTool and ImageMagick required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.env["TZ"] = "America/New_York"
        self.w.use_real_metadata_tools()

        self.source = self.w.jpeg("input/original.jpg")

        subprocess.run(
            [
                shutil.which("exiftool"),
                "-overwrite_original",
                "-DateTimeOriginal=2024:02:29 23:59:58",
                "-SubSecTimeOriginal=123456789",
                str(self.source),
            ],
            check=True,
            capture_output=True,
        )

        os.utime(
            self.source,
            ns=(
                1_700_000_000_123_456_789,
                1_700_000_001_987_654_321,
            ),
        )

    def sync(self):
        return self.w.dispatch(
            "datesync", "--direction", "exif-to-file",
            "--", self.source,
        )

    def test_create_mode_does_not_explicitly_touch_source(self):
        self.w.env["KIM_POLICY"] = "create"
        before = self.w.observe(self.source)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(self.source), before)

        output = self.source.with_name("original_datesync.jpg")
        self.assertTrue(output.is_file())

        source_touches = [
            call for call in result.calls
            if call["tool"] == "touch"
            and str(self.source) in call["argv"]
        ]
        self.assertEqual(source_touches, [])

    def test_legacy_overwrite_with_unavailable_gui_never_touches_source(self):
        self.w.env["KIM_POLICY"] = "overwrite"
        before = self.w.observe(self.source)

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"status": 127},
        )

        result = self.sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)

        self.assertFalse(any(
            call["tool"] == "touch"
            for call in result.calls
        ))


if __name__ == "__main__":
    unittest.main()
