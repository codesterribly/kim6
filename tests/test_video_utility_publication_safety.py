"""Late destination-collision safety for derived video utility outputs."""

import shutil
import subprocess
import unittest

from support import Workspace


class VideoUtilityPublicationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("FFmpeg and ffprobe required")

        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.use_real_video_tools()
        self.w.env["KIM_POLICY"] = "overwrite"

        self.source = self.w.path("input/clip.mp4")
        self.source.parent.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [
                self.ffmpeg,
                "-hide_banner", "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i",
                "testsrc2=size=96x64:rate=10:duration=1.2",
                "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=8000:duration=1.2",
                "-c:v", "libx264",
                "-threads", "1",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                str(self.source),
            ],
            check=True,
            capture_output=True,
            timeout=15,
        )

        self.before = self.w.observe(self.source)

    def assert_late_collision(self, action, options, filename, numbered):
        contender = "created by another writer after encoding"

        self.w.sequence("ln", [
            {
                "status": 74,
                "writes": {
                    f"input/{filename}": contender,
                },
            },
            {"passthrough": True},
        ])

        result = self.w.dispatch(
            action, *options, "--", self.source
        )

        self.assertEqual(
            0,
            result.returncode,
            (result.stderr, result.events),
        )

        occupied = self.w.path(f"input/{filename}")
        replacement = self.w.path(f"input/{numbered}")

        self.assertEqual(
            contender.encode(),
            occupied.read_bytes(),
        )
        self.assertTrue(replacement.is_file(), replacement)
        self.assertGreater(replacement.stat().st_size, 0)

        self.assertEqual(
            self.w.observe(self.source),
            self.before,
        )

        attempts = [
            call
            for call in result.calls
            if call["tool"] == "ln"
        ]

        self.assertEqual(2, len(attempts), attempts)
        self.assertEqual(
            str(occupied),
            attempts[0]["argv"][-1],
        )
        self.assertEqual(
            str(replacement),
            attempts[1]["argv"][-1],
        )

        self.assertFalse(
            list(self.w.root.rglob(".kim6-stage.*"))
        )

    def test_video_thumbnail_late_collision_uses_numbered_file(self):
        self.assert_late_collision(
            "videoframes",
            ("--mode", "thumbnail", "--format", "png"),
            "clip_thumbnail.png",
            "clip_thumbnail_1.png",
        )

    def test_audio_extract_late_collision_uses_numbered_file(self):
        self.assert_late_collision(
            "videoaudio",
            ("--mode", "extract", "--format", "mp3"),
            "clip_audio.mp3",
            "clip_audio_1.mp3",
        )

    def test_audio_mute_late_collision_uses_numbered_file(self):
        self.assert_late_collision(
            "videoaudio",
            ("--mode", "mute"),
            "clip_muted.mp4",
            "clip_muted_1.mp4",
        )

    def test_video_gif_late_collision_uses_numbered_file(self):
        self.assert_late_collision(
            "videogif",
            (
                "--start", "00:00:00",
                "--duration", "0.5",
                "--fps", "10",
                "--width", "320",
                "--loop", "once",
            ),
            "clip_animated.gif",
            "clip_animated_1.gif",
        )


if __name__ == "__main__":
    unittest.main()
