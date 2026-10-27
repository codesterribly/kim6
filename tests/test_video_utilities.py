"""Public-dispatcher tests for derived video frame, audio and GIF utilities."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class VideoUtilityTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("FFmpeg and ffprobe are required for video utility tests")
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"
        self.w.use_real_video_tools()
        self.source = self.make_video("input/clip [雪].mp4", audio=True)

    def make_video(self, relative, audio=False, duration="1.2", rotation=None):
        path = self.w.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10:duration=" + duration]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000:duration=" + duration]
        command += ["-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac", "-shortest"]
        if rotation is not None:
            command += ["-metadata:s:v:0", "rotate=" + str(rotation)]
        command.append(str(path))
        subprocess.run(command, check=True, timeout=15)
        return path

    def make_vfr_video(self, relative):
        path = self.w.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10:duration=1.2",
                   "-vf", "select='eq(n,0)+eq(n,2)+eq(n,7)'", "-fps_mode", "vfr",
                   "-c:v", "ffv1", str(path)]
        subprocess.run(command, check=True, timeout=15)
        return path

    def dispatch(self, action, *args, source=None):
        return self.w.dispatch(action, *args, "--", source or self.source)

    def probe(self, path):
        result = subprocess.run([self.ffprobe, "-v", "error", "-show_streams", "-show_format",
                                "-of", "json", str(path)], check=True, capture_output=True,
                               text=True, timeout=10)
        return json.loads(result.stdout)

    def video_streams(self, path):
        return [s for s in self.probe(path)["streams"] if s["codec_type"] == "video"]

    def test_single_frame_at_fractional_time_publishes_decoded_png_and_preserves_source(self):
        before = self.w.observe(self.source)
        result = self.dispatch("videoframes", "--mode", "single", "--at", "00:00:00.500",
                               "--format", "png")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_frame-00-00-00.500.png")
        self.assertTrue(output.is_file())
        self.assertEqual(1, len(self.video_streams(output)))
        self.assertEqual("png", self.video_streams(output)[0]["codec_name"])
        self.assertEqual((96, 64), (self.video_streams(output)[0]["width"], self.video_streams(output)[0]["height"]))
        self.assertEqual(self.w.observe(self.source), before)

    def test_automatic_thumbnail_uses_nonzero_sample_time(self):
        result = self.dispatch("videoframes", "--mode", "thumbnail", "--format", "jpg")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_thumbnail.jpg")
        self.assertTrue(output.is_file())
        frame_calls = [c["argv"] for c in result.calls if c["tool"] == "ffmpeg" and "-ss" in c["argv"]]
        self.assertTrue(frame_calls)
        sample_time = frame_calls[0][frame_calls[0].index("-ss") + 1]
        self.assertGreater(float(sample_time), 0)

    def test_contact_sheet_creates_one_labeled_png_artifact(self):
        for grid, width in (("3x3", 960), ("4x4", 1280), ("5x5", 1600)):
            with self.subTest(grid=grid):
                result = self.dispatch("videoframes", "--mode", "contact", "--grid", grid, "--format", "png")
                self.assertEqual(0, result.returncode, (result.stderr, result.events))
                output = self.source.with_name("clip [雪]_contact-sheet.png" if grid == "3x3"
                                              else f"clip [雪]_contact-sheet_{1 if grid == '4x4' else 2}.png")
                image = self.video_streams(output)[0]
                self.assertEqual(width, image["width"])
                self.assertEqual(width // 320 * 180 + 40, image["height"])

    def test_audio_extract_encodes_mp3_without_video_and_preserves_source(self):
        before = self.w.observe(self.source)
        result = self.dispatch("videoaudio", "--mode", "extract", "--format", "mp3")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_audio.mp3")
        probe = self.probe(output)
        self.assertEqual({"audio"}, {s["codec_type"] for s in probe["streams"]})
        self.assertEqual("mp3", probe["streams"][0]["codec_name"])
        self.assertEqual(self.w.observe(self.source), before)

    def test_materially_truncated_audio_output_is_rejected(self):
        plan = json.loads(self.w.plan.read_text())
        plan["video_limit_output_duration"] = "0.5"
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(self.source)
        result = self.dispatch("videoaudio", "--mode", "extract", "--format", "mp3")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_audio.mp3").exists())
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_short_audio_truncation_beyond_one_codec_frame_is_rejected(self):
        short = self.make_video("input/short-audio.mkv", audio=True, duration="0.2")
        plan = json.loads(self.w.plan.read_text())
        plan["video_limit_output_duration"] = "0.02"
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(short)
        result = self.dispatch("videoaudio", "--mode", "extract", "--format", "mp3", source=short)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(short.with_name("short-audio_audio.mp3").exists())
        self.assertEqual(self.w.observe(short), before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_gif_interval_may_not_extend_past_source_end(self):
        result = self.dispatch("videogif", "--start", "00:00:00.800", "--duration", "0.5",
                               "--fps", "10", "--width", "320", "--loop", "infinite")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_animated.gif").exists())

    def test_gif_scaled_pixel_frame_work_is_bounded_for_tall_inputs(self):
        plan = json.loads(self.w.plan.read_text())
        plan["video_force_input_dimensions"] = {"width": 10000, "height": 100000}
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(self.source)
        result = self.dispatch("videogif", "--start", "00:00:00", "--duration", "60",
                               "--fps", "24", "--width", "800", "--loop", "infinite")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_animated.gif").exists())
        self.assertFalse(any(call["tool"] == "ffmpeg" and "-progress" in call["argv"]
                             for call in result.calls))
        self.assertEqual(self.w.observe(self.source), before)

    def test_contact_sheet_contains_source_and_timestamp_labels_when_ocr_is_available(self):
        tesseract = shutil.which("tesseract")
        if not tesseract:
            self.skipTest("tesseract is optional; image layout is covered separately")
        result = self.dispatch("videoframes", "--mode", "contact", "--grid", "3x3", "--format", "png")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_contact-sheet.png")
        recognized = subprocess.run([tesseract, str(output), "stdout"], check=True,
                                    capture_output=True, text=True, timeout=15).stdout.lower()
        self.assertIn("clip", recognized)
        self.assertRegex(recognized, r"00[:.]00[:.]00")

    def test_contact_sheets_handle_vfr_and_sources_shorter_than_the_grid(self):
        short = self.make_video("input/very-short.mkv", duration="0.2")
        vfr = self.make_vfr_video("input/variable-rate.mkv")
        frames = subprocess.run([self.ffprobe, "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0",
                                 str(vfr)], check=True, capture_output=True, text=True, timeout=10)
        timestamps = [float(value) for value in frames.stdout.splitlines() if value.strip()]
        self.assertGreaterEqual(len(timestamps), 3)
        gaps = [round(right - left, 3) for left, right in zip(timestamps, timestamps[1:])]
        self.assertNotEqual(len(set(gaps)), 1, "fixture must have variable frame intervals")
        for source, output_name in ((short, "very-short_contact-sheet.png"),
                                    (vfr, "variable-rate_contact-sheet.png")):
            result = self.dispatch("videoframes", "--mode", "contact", "--grid", "3x3",
                                   "--format", "png", source=source)
            self.assertEqual(0, result.returncode, (result.stderr, result.events))
            image = self.video_streams(source.with_name(output_name))[0]
            self.assertEqual((960, 580), (image["width"], image["height"]))

    def test_audio_formats_and_compatible_aac_m4a_stream_copy(self):
        before = self.w.observe(self.source)
        cases = (("m4a", "aac"), ("flac", "flac"), ("wav", "pcm_s16le"))
        for fmt, codec in cases:
            with self.subTest(format=fmt):
                result = self.dispatch("videoaudio", "--mode", "extract", "--format", fmt)
                self.assertEqual(0, result.returncode, (result.stderr, result.events))
                output = self.source.with_name(f"clip [雪]_audio.{fmt}")
                probe = self.probe(output)
                self.assertEqual(codec, probe["streams"][0]["codec_name"])
                self.assertEqual({"audio"}, {s["codec_type"] for s in probe["streams"]})
                if fmt == "m4a":
                    producer = next(call["argv"] for call in result.calls
                                    if call["tool"] == "ffmpeg" and "-progress" in call["argv"])
                    self.assertEqual("copy", producer[producer.index("-c:a") + 1])
        self.assertEqual(self.w.observe(self.source), before)

    def test_mute_stream_copies_video_without_audio_and_silent_input_is_noop(self):
        before = self.w.observe(self.source)
        result = self.dispatch("videoaudio", "--mode", "mute")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_muted.mp4")
        probe = self.probe(output)
        self.assertEqual(["video"], [s["codec_type"] for s in probe["streams"]])
        self.assertEqual("h264", probe["streams"][0]["codec_name"])
        self.assertEqual(self.w.observe(self.source), before)
        silent = self.make_video("input/silent.mkv")
        no_op = self.dispatch("videoaudio", "--mode", "mute", source=silent)
        self.assertEqual(0, no_op.returncode, no_op.stderr)
        self.assertFalse(silent.with_name("silent-muted.mkv").exists())
        no_audio = self.dispatch("videoaudio", "--mode", "extract", "--format", "m4a", source=silent)
        self.assertNotEqual(0, no_audio.returncode)
        self.assertFalse(silent.with_name("silent-audio.m4a").exists())

    def test_muting_preserves_video_packet_payloads(self):
        result = self.dispatch("videoaudio", "--mode", "mute")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        muted = self.source.with_name("clip [雪]_muted.mp4")
        def packet_hashes(path):
            probe = subprocess.run([self.ffprobe, "-v", "error", "-select_streams", "v:0",
                                    "-show_packets", "-show_data_hash", "sha256",
                                    "-show_entries", "packet=data_hash", "-of", "csv=p=0", str(path)],
                                   check=True, capture_output=True, text=True, timeout=10)
            return probe.stdout.splitlines()
        self.assertEqual(packet_hashes(self.source), packet_hashes(muted))

    def test_video_gif_encodes_requested_interval_and_infinite_loop(self):
        result = self.dispatch("videogif", "--start", "00:00:00.200", "--duration", "0.6",
                               "--fps", "10", "--width", "320", "--loop", "infinite")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_animated.gif")
        probe = self.probe(output)
        self.assertEqual("gif", probe["streams"][0]["codec_name"])
        self.assertLessEqual(probe["streams"][0]["width"], 96)
        self.assertGreater(int(probe["streams"][0].get("nb_frames", 1)), 1)
        full_decode = subprocess.run([self.ffmpeg, "-v", "error", "-xerror", "-i", str(output),
                                      "-f", "null", "-"], capture_output=True, timeout=10)
        self.assertEqual(0, full_decode.returncode, full_decode.stderr)

    def test_gif_once_omits_loop_extension_and_overwrite_policy_still_creates_derivative(self):
        self.w.approve_overwrite()
        before = self.w.observe(self.source)
        result = self.dispatch("videogif", "--start", "00:00:00", "--duration", "0.5",
                               "--fps", "12", "--width", "480", "--loop", "once")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        output = self.source.with_name("clip [雪]_animated.gif")
        self.assertTrue(output.is_file())
        self.assertNotIn(b"NETSCAPE2.0", output.read_bytes())
        self.assertEqual(self.w.observe(self.source), before)

    def test_create_collision_preserves_existing_entry_and_uses_numbered_output(self):
        occupied = self.source.with_name("clip [雪]_thumbnail.jpg")
        occupied.write_bytes(b"owned by user")
        before = self.w.observe(self.source)
        result = self.dispatch("videoframes", "--mode", "thumbnail", "--format", "jpg")
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        self.assertEqual(b"owned by user", occupied.read_bytes())
        self.assertTrue(occupied.with_name("clip [雪]_thumbnail_1.jpg").is_file())
        self.assertEqual(self.w.observe(self.source), before)

    def test_cancellation_after_producer_failure_stops_batch_before_publication(self):
        second = self.make_video("input/second.mkv", duration="0.5")
        plan = json.loads(self.w.plan.read_text())
        plan["video_interrupt_after_encode"] = "gone"
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(self.source)
        result = self.w.dispatch("videoframes", "--mode", "thumbnail", "--format", "png",
                                 "--", self.source, second)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_thumbnail.png").exists())
        self.assertFalse(second.with_name("second_thumbnail.png").exists())
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_zero_exit_with_corrupt_frame_bytes_is_rejected(self):
        self.w.respond("ffmpeg", status=0, output_base64="bm90IGFuIGltYWdl")
        result = self.dispatch("videoframes", "--mode", "thumbnail", "--format", "png")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_thumbnail.png").exists())

    def test_nonempty_partial_output_after_producer_failure_is_not_published(self):
        self.w.respond("ffmpeg", status=19, output_base64="cGFydGlhbCBhcnRpZmFjdA==")
        before = self.w.observe(self.source)
        result = self.dispatch("videoframes", "--mode", "thumbnail", "--format", "png")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_thumbnail.png").exists())
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_missing_ffmpeg_and_symlinked_source_fail_closed(self):
        before = self.w.observe(self.source)
        (self.w.bin / "ffmpeg").unlink()
        missing = self.dispatch("videoaudio", "--mode", "mute")
        self.assertNotEqual(0, missing.returncode)
        self.assertEqual(self.w.observe(self.source), before)
        self.w.bin.joinpath("ffmpeg").symlink_to(shutil.which("ffmpeg"))
        linked = self.w.path("input/alias.mp4")
        linked.symlink_to(self.source)
        rejected = self.dispatch("videoaudio", "--mode", "extract", "--format", "m4a", source=linked)
        self.assertNotEqual(0, rejected.returncode)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("clip [雪]_audio.m4a").exists())

    def test_dbus_service_loss_on_staged_output_probe_prevents_publication(self):
        second = self.make_video("input/second.mp4", audio=True, duration="0.5")
        plan = json.loads(self.w.plan.read_text())
        plan["video_interrupt_on_probe_output"] = "gone"
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(self.source)
        result = self.w.dispatch("videoaudio", "--mode", "extract", "--format", "flac",
                                 "--", self.source, second)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_audio.flac").exists())
        self.assertFalse(second.with_name("second_audio.flac").exists())
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertTrue(any(call["tool"] == "qdbus" and call["argv"][-1] == "close"
                            for call in result.calls))

    def test_successful_batch_and_partial_failure_keep_earlier_artifacts(self):
        second = self.make_video("input/second [β].mkv", duration="0.5")
        result = self.w.dispatch("videoframes", "--mode", "thumbnail", "--format", "png",
                                 "--", self.source, second)
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        self.assertTrue(self.source.with_name("clip [雪]_thumbnail.png").is_file())
        self.assertTrue(second.with_name("second [β]_thumbnail.png").is_file())
        invalid = self.w.path("input/not-video.mp4")
        invalid.write_bytes(b"not a video")
        partial = self.w.dispatch("videoframes", "--mode", "thumbnail", "--format", "jpg",
                                  "--", self.source, invalid)
        self.assertNotEqual(0, partial.returncode)
        self.assertTrue(self.source.with_name("clip [雪]_thumbnail.jpg").is_file())
        self.assertFalse(invalid.with_name("not-video_thumbnail.jpg").exists())

    def test_owned_ffmpeg_process_is_stopped_on_cancellation(self):
        plan = json.loads(self.w.plan.read_text())
        plan.update({"video_hold_process": True, "video_interrupt_during_encode": "cancelled"})
        self.w.plan.write_text(json.dumps(plan))
        before = self.w.observe(self.source)
        result = self.dispatch("videoframes", "--mode", "thumbnail", "--format", "png")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("clip [雪]_thumbnail.png").exists())
        child_file = self.w.control / "video-child.pid"
        self.assertTrue(child_file.is_file())
        child_pid = int(child_file.read_text())
        self.assertFalse(Path(f"/proc/{child_pid}").exists())

    def test_out_of_range_frame_and_invalid_gif_request_fail_without_publishing(self):
        bad_frame = self.dispatch("videoframes", "--mode", "single", "--at", "00:00:09",
                                  "--format", "png")
        self.assertNotEqual(0, bad_frame.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_frame-00-00-09.png").exists())
        bad_gif = self.dispatch("videogif", "--start", "00:00:00", "--duration", "90",
                                "--fps", "10", "--width", "320", "--loop", "once")
        self.assertNotEqual(0, bad_gif.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_animated.gif").exists())

    def test_producer_exit_before_progress_pipe_open_fails_without_hanging_or_publishing(self):
        plan = json.loads(self.w.plan.read_text())
        plan["video_fail_before_progress"] = True
        self.w.plan.write_text(json.dumps(plan))
        source_before = self.w.observe(self.source)
        result = self.dispatch("videoaudio", "--mode", "extract", "--format", "mp3")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.source.with_name("clip [雪]_audio.mp3").exists())
        self.assertEqual(self.w.observe(self.source), source_before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_menu_contract_exposes_six_video_utility_actions(self):
        menu = (self.w.production.parents[1] / "kim_compressandresizevideo.desktop.in").read_text()
        commands = [line.removeprefix("Exec=") for line in menu.splitlines() if line.startswith("Exec=")]
        utility_commands = [command for command in commands
                            if command.startswith("kim_all videoframes ")
                            or command.startswith("kim_all videoaudio ")
                            or command.startswith("kim_all videogif ")]
        self.assertEqual(6, len(utility_commands))
        self.assertTrue(all(command.endswith("-- %F") for command in utility_commands))
