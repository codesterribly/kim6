"""Publication-safety regressions for derived MP4 slideshows."""

import json
import shutil
import subprocess
import unittest

from support import Workspace


class SlideshowPublicationSafetyTests(unittest.TestCase):
    def setUp(self):
        required = ("ffmpeg", "ffprobe", "magick", "exiftool")
        if not all(shutil.which(tool) for tool in required):
            self.skipTest("FFmpeg, ffprobe, ImageMagick and ExifTool required")

        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "overwrite"
        self.w.use_real_slideshow_tools()

        self.source = self.w.png("input/photo.png")

        subprocess.run(
            [
                shutil.which("magick"),
                "-size", "8x8",
                "xc:red",
                str(self.source),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )

        self.before = self.w.observe(self.source)

    def run_slideshow(self, *options):
        return self.w.dispatch(
            "slideshow",
            "--seconds-per-photo", "1",
            "--size", "160x120",
            "--fps", "1",
            *options,
            "--",
            self.source,
        )

    def assert_no_stages(self):
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertEqual(self.w.observe(self.source), self.before)

    def test_explicit_destination_created_at_publish_is_preserved(self):
        destination = self.w.path("input/late-race.mp4")
        contender = b"created by another writer during encoding"

        # Inject a competing destination at the final publication call,
        # after encoding and output validation.
        self.w.respond(
            "ln",
            status=74,
            writes={
                "input/late-race.mp4": contender.decode("ascii"),
            },
        )

        result = self.run_slideshow("--output", destination)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_bytes(), contender)
        self.assertEqual(
            1,
            sum(call["tool"] == "ln" for call in result.calls),
        )
        self.assertTrue(
            any(call["tool"] == "ffprobe" for call in result.calls)
        )
        self.assert_no_stages()

    def test_implicit_destination_collision_retries_numbered_output(self):
        occupied = self.w.path("input/photo_slideshow.mp4")
        numbered = self.w.path("input/photo_slideshow_1.mp4")
        contender = b"other writer's output"

        # The first publication attempt encounters a new file.
        # The second attempt must use a numbered destination.
        self.w.sequence("ln", [
            {
                "status": 74,
                "writes": {
                    "input/photo_slideshow.mp4": contender.decode("ascii"),
                },
            },
            {"passthrough": True},
        ])

        result = self.run_slideshow()

        self.assertEqual(
            result.returncode,
            0,
            (result.stderr, result.events),
        )
        self.assertEqual(occupied.read_bytes(), contender)
        self.assertTrue(numbered.is_file())
        self.assertEqual(
            2,
            sum(call["tool"] == "ln" for call in result.calls),
        )
        self.assert_no_stages()

    def test_wrong_reported_container_refuses_publication(self):
        plan = json.loads(self.w.plan.read_text())
        plan["video_force_output_format"] = "mpegts"
        self.w.plan.write_text(json.dumps(plan))

        destination = self.w.path("input/invalid.mp4")

        result = self.run_slideshow("--output", destination)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(destination.exists())

        self.assertTrue(any(
            call["tool"] == "ffprobe"
            and any(
                "format=format_name" in arg
                for arg in call["argv"]
            )
            for call in result.calls
        ))

        self.assertFalse(
            any(call["tool"] == "ln" for call in result.calls)
        )
        self.assert_no_stages()

    def test_preexisting_destination_symlink_is_refused(self):
        sentinel = self.w.path("input/sentinel.bin")
        sentinel.write_bytes(b"keep this content")

        destination = self.w.path("input/existing.mp4")
        destination.symlink_to(sentinel)

        before_link = self.w.observe(destination)
        before_sentinel = self.w.observe(sentinel)

        result = self.run_slideshow("--output", destination)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(destination), before_link)
        self.assertEqual(self.w.observe(sentinel), before_sentinel)

        self.assertFalse(
            any(call["tool"] == "ln" for call in result.calls)
        )
        self.assert_no_stages()


if __name__ == "__main__":
    unittest.main()
