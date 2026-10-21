"""Safe FFmpeg video transcoding tests using disposable media fixtures."""
import shutil
import subprocess
import json
import os
import unittest

from support import Workspace


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("FFmpeg and ffprobe are required for video tests")
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "create"
        self.source = self.w.path("input/short clip.mp4")
        self.source.parent.mkdir(parents=True)
        subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc=size=64x48:rate=5:duration=0.4",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000:duration=0.4",
            "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(self.source),
        ], check=True, timeout=15)
        self.w.use_real_video_tools()

    def make_video(self, relative, width=64, height=48, audio=False, codec="libx264"):
        path = self.w.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=5:duration=0.4"]
        if audio:
            command += ["-f", "lavfi", "-i", "sine=frequency=700:sample_rate=8000:duration=0.4"]
        command += ["-c:v", codec, "-pix_fmt", "yuv420p"]
        if audio:
            command += ["-c:a", "aac", "-shortest"]
        command.append(str(path))
        subprocess.run(command, check=True, timeout=15)
        return path

    def probe_text(self, path):
        return subprocess.run([
            self.ffprobe, "-v", "error", "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,width,height,nb_frames,display_aspect_ratio",
            "-of", "compact=p=0:nk=0", str(path),
        ], check=True, capture_output=True, text=True, timeout=10).stdout

    def plan_update(self, **values):
        plan = json.loads(self.w.plan.read_text())
        plan.update(values)
        self.w.plan.write_text(json.dumps(plan))

    def transcode(self, source=None, size="hd720", crf="23", codec="libx264", container="mp4"):
        return self.w.dispatch("video", "--size", size, "--crf", crf, "--codec", codec,
                               "--container", container, "--", source or self.source)

    def ffmpeg_calls(self, result):
        return [call["argv"] for call in result.calls
                if call["tool"] == "ffmpeg" and "-progress" in call["argv"]]

    def test_real_create_transcodes_video_and_audio_to_requested_mp4(self):
        source_before = self.w.observe(self.source)
        result = self.w.dispatch(
            "video", "--size", "hd720", "--crf", "23", "--codec", "libx264",
            "--container", "mp4", "--", self.source,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_name("short clip-transcoded.mp4")
        self.assertTrue(output.is_file())
        self.assertEqual(self.w.observe(self.source), source_before)
        probe = subprocess.run([
            self.ffprobe, "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height", "-of", "compact=p=0:nk=0", str(output),
        ], check=True, capture_output=True, text=True, timeout=10).stdout
        self.assertIn("codec_name=h264", probe)
        self.assertIn("codec_name=aac", probe)
        self.assertIn("width=64", probe)
        self.assertIn("height=48", probe)

    def test_real_hd_presets_fit_source_to_requested_bounds_without_upscaling(self):
        source = self.make_video("hd/source.mp4", width=1920, height=1080)
        hd720 = self.transcode(source, size="hd720")
        self.assertEqual(hd720.returncode, 0, f"{hd720.stderr}\n{hd720.calls}")
        output720 = source.with_name("source-transcoded.mp4")
        details720 = self.probe_text(output720)
        self.assertIn("width=1280", details720)
        self.assertIn("height=720", details720)
        hd1080 = self.transcode(source, size="hd1080")
        self.assertEqual(hd1080.returncode, 0, f"{hd1080.stderr}\n{hd1080.calls}")
        output1080 = source.with_name("source-transcoded_1.mp4")
        details1080 = self.probe_text(output1080)
        self.assertIn("width=1920", details1080)
        self.assertIn("height=1080", details1080)

    def test_all_24_menu_presets_reach_ffmpeg_without_state_leaking(self):
        self.plan_update(video_fail_encoding=True)
        source_before = self.w.observe(self.source)
        options = []
        for size in ("hd720", "hd1080"):
            for crf in ("17", "23", "29"):
                for codec in ("libx264", "libx265"):
                    for container in ("orig", "mp4"):
                        options.append((size, crf, codec, container))
        self.assertEqual(len(options), 24)
        for size, crf, codec, container in options:
            with self.subTest(size=size, crf=crf, codec=codec, container=container):
                result = self.transcode(size=size, crf=crf, codec=codec, container=container)
                self.assertNotEqual(result.returncode, 0)
                calls = self.ffmpeg_calls(result)
                self.assertEqual(len(calls), 1)
                args = calls[0]
                self.assertEqual(args[args.index("-c:v") + 1], codec)
                self.assertEqual(args[args.index("-crf") + 1], crf)
                self.assertEqual(args[args.index("-f") + 1], "mp4")
                scale = args[args.index("-vf") + 1]
                self.assertIn("1280" if size == "hd720" else "1920", scale)
                self.assertEqual(self.w.observe(self.source), source_before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())

    def test_real_h265_original_matroska_keeps_portrait_dimensions_without_upscaling(self):
        source = self.make_video("portrait/雪 portrait.mkv", width=96, height=128, codec="libx264")
        result = self.transcode(source, size="hd1080", crf="29", codec="libx265", container="orig")
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.calls}")
        output = source.with_name("雪 portrait-transcoded.mkv")
        self.assertTrue(output.is_file())
        details = self.probe_text(output)
        self.assertIn("codec_name=hevc", details)
        self.assertIn("width=96", details)
        self.assertIn("height=128", details)
        self.assertIn("format_name=matroska", details)
        self.assertEqual(self.w.observe(source).sha256, result.before_entries["portrait/雪 portrait.mkv"].sha256)

    def test_leading_dash_unicode_filename_is_a_safe_input_after_separator(self):
        source = self.make_video("odd/-film [雪].mp4")
        before = self.w.observe(source)
        result = self.transcode(source)
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.calls}")
        output = source.with_name("-film [雪]-transcoded.mp4")
        self.assertTrue(output.is_file())
        self.assertIn("codec_name=h264", self.probe_text(output))
        self.assertEqual(self.w.observe(source), before)

    def test_original_container_and_mp4_selection_are_independent_in_one_batch(self):
        mkv = self.make_video("other/clip [雪].mkv", width=48, height=64, audio=True)
        first_before = self.w.observe(self.source)
        second_before = self.w.observe(mkv)
        result = self.w.dispatch("video", "--size", "hd720", "--crf", "17", "--codec", "libx264",
                                 "--container", "orig", "--", self.source, mkv)
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.calls}")
        mp4_output = self.source.with_name("short clip-transcoded.mp4")
        mkv_output = mkv.with_name("clip [雪]-transcoded.mkv")
        self.assertIn("format_name=mov,mp4", self.probe_text(mp4_output))
        self.assertIn("format_name=matroska", self.probe_text(mkv_output))
        self.assertIn("codec_name=aac", self.probe_text(mkv_output))
        self.assertEqual(self.w.observe(self.source), first_before)
        self.assertEqual(self.w.observe(mkv), second_before)

    def test_real_authorized_overwrite_replaces_only_after_validated_encoding(self):
        self.w.env["KIM_POLICY"] = "overwrite"
        before = self.w.observe(self.source)
        result = self.transcode(self.source, codec="libx265", container="orig")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.w.observe(self.source).sha256, before.sha256)
        details = self.probe_text(self.source)
        self.assertIn("codec_name=hevc", details)
        self.assertIn("codec_name=aac", details)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_create_collision_and_dangling_symlink_are_never_replaced(self):
        target = self.source.with_name("short clip-transcoded.mp4")
        target.symlink_to("missing-video-target")
        before = os.readlink(target)
        source_before = self.w.observe(self.source)
        result = self.transcode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(target), before)
        numbered = target.with_name("short clip-transcoded_1.mp4")
        self.assertTrue(numbered.is_file())
        self.assertEqual(self.w.observe(self.source), source_before)

    def test_av1_real_encode_uses_supported_encoder_and_validates_result(self):
        encoders = subprocess.run([self.ffmpeg, "-hide_banner", "-encoders"],
                                  capture_output=True, text=True, check=True).stdout
        encoder = "libsvtav1" if "libsvtav1" in encoders else "libaom-av1" if "libaom-av1" in encoders else ""
        if not encoder:
            self.skipTest("FFmpeg has neither supported software AV1 encoder")
        before = self.w.observe(self.source)
        result = self.w.dispatch("video", "--size", "hd720", "--codec", "av1",
                                 "--av1-quality", "high", "--container", "mp4", "--", self.source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = self.source.with_name("short clip-transcoded.mp4")
        details = self.probe_text(output)
        self.assertIn("codec_name=av1", details)
        self.assertIn("width=64", details)
        self.assertIn("height=48", details)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertIn("codec_type=audio", details)
        args = self.ffmpeg_calls(result)[0]
        self.assertEqual(args[args.index("-c:v") + 1], encoder)
        self.assertEqual(args[args.index("-crf") + 1], "28")

    def test_av1_balanced_preset_uses_its_own_quality_and_missing_encoder_fails_closed(self):
        self.plan_update(video_fail_encoding=True)
        result = self.w.dispatch("video", "--size", "hd1080", "--codec", "av1",
                                 "--av1-quality", "balanced", "--container", "mp4", "--", self.source)
        self.assertNotEqual(result.returncode, 0)
        args = self.ffmpeg_calls(result)[0]
        self.assertEqual(args[args.index("-crf") + 1], "35")
        self.plan_update(video_fail_encoding=False)
        self.w.respond("ffmpeg", stdout=" V..... libx264 H.264 encoder\n")
        rejected = self.w.dispatch("video", "--size", "hd720", "--codec", "av1",
                                   "--av1-quality", "high", "--container", "mp4", "--", self.source)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.ffmpeg_calls(rejected), [])
        self.assertFalse(self.source.with_name("short clip-transcoded_1.mp4").exists())

    def test_av1_falls_back_to_libaom_only_when_svt_is_not_advertised(self):
        self.w.sequence("ffmpeg", [
            {"stdout": " V..... libaom-av1 AV1 encoder\n"},
            {"status": 19, "stderr": "injected producer failure\n"},
        ])
        result = self.w.dispatch("video", "--size", "hd720", "--codec", "av1",
                                 "--av1-quality", "balanced", "--container", "mp4", "--", self.source)
        self.assertNotEqual(result.returncode, 0)
        args = self.ffmpeg_calls(result)[0]
        self.assertEqual(args[args.index("-c:v") + 1], "libaom-av1")
        self.assertEqual(args[args.index("-crf") + 1], "35")
        self.assertIn("-cpu-used", args)

    def test_destination_created_during_transcode_survives_and_uses_next_collision_number(self):
        self.plan_update(video_create_collision=True)
        source_before = self.w.observe(self.source)
        target = self.source.with_name("short clip-transcoded.mp4")
        result = self.transcode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), b"created during transcode; preserve me")
        self.assertTrue(target.with_name("short clip-transcoded_1.mp4").is_file())
        self.assertEqual(self.w.observe(self.source), source_before)

    def test_refuses_symlink_hardlink_and_duplicate_source_selections(self):
        symlink = self.w.path("input/linked.mp4")
        symlink.symlink_to(self.source)
        hardlink = self.w.path("input/hardlinked.mp4")
        os.link(self.source, hardlink)
        source_before = self.w.observe(self.source)
        for selection in ((symlink,), (hardlink,), (self.source, self.source)):
            with self.subTest(selection=selection):
                result = self.w.dispatch("video", "--size", "hd720", "--crf", "23", "--codec", "libx264",
                                         "--container", "mp4", "--", *selection)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.ffmpeg_calls(result))
        self.assertEqual(self.w.observe(self.source), source_before)

    def test_corrupt_or_partial_producer_output_is_never_published(self):
        import base64
        for status, content in ((19, b"partial video bytes"), (0, b"not a video")):
            with self.subTest(status=status, content=content):
                self.w.respond_to("ffmpeg", "-progress", {
                    "status": status, "output_base64": base64.b64encode(content).decode(),
                })
                before = self.w.observe(self.source)
                result = self.transcode()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.w.observe(self.source), before)
                self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
                self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_valid_but_wrong_reported_container_is_rejected(self):
        self.plan_update(video_force_output_format="mpegts")
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call["tool"] == "kdialog" and "--error" in call["argv"] and
                            "output validation failed" in call["argv"][-1] for call in result.calls))
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_valid_truncated_prefix_is_rejected_before_publication(self):
        self.plan_update(video_limit_output_duration="0.2")
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call["tool"] == "kdialog" and "--error" in call["argv"] and
                            "output validation failed" in call["argv"][-1] for call in result.calls))
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_invalid_source_is_reported_and_batch_continues(self):
        invalid = self.w.path("input/not-a-video [x].mp4")
        invalid.write_bytes(b"invalid video bytes")
        result = self.w.dispatch("video", "--size", "hd720", "--crf", "23", "--codec", "libx264",
                                 "--container", "mp4", "--", invalid, self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.source.with_name("short clip-transcoded.mp4").is_file())
        encoded = [args for args in self.ffmpeg_calls(result) if args[-1] != "-"]
        self.assertEqual(len(encoded), 1)
        self.assertEqual(self.w.observe(self.source).sha256, result.before_entries["input/short clip.mp4"].sha256)

    def test_missing_encoder_fails_before_processing(self):
        self.w.respond_to("ffmpeg", "-encoders", {"stdout": " V..... unavailable encoder\n"})
        result = self.transcode(codec="libx265")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ffmpeg_calls(result), [])

    def test_missing_ffmpeg_is_reported_without_starting_ffprobe_or_publication(self):
        (self.w.bin / "ffmpeg").unlink()
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call["tool"] == "ffprobe" for call in result.calls))
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_missing_ffprobe_is_reported_without_starting_encoder(self):
        (self.w.bin / "ffprobe").unlink()
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ffmpeg_calls(result), [])
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())

    def test_create_publication_failure_preserves_source_and_publishes_nothing(self):
        self.w.respond_to("ln", "-T", {"status": 23})
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertTrue(any(call["tool"] == "kdialog" and "--error" in call["argv"] and
                            "publication failed" in call["argv"][-1] for call in result.calls))

    def test_cancel_before_processing_does_not_start_encoder(self):
        (self.w.control / "progress-state").write_text("cancelled")
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ffmpeg_calls(result), [])
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())

    def test_service_loss_during_encoding_terminates_only_owned_process(self):
        self.plan_update(video_hold_process=True, video_interrupt_during_encode="gone")
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
        child_file = self.w.control / "video-child.pid"
        self.assertTrue(child_file.exists(), f"{result.stderr}\n{result.calls}")
        child_pid = int(child_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_service_loss_after_encoding_prevents_publication(self):
        self.plan_update(video_interrupt_after_encode="gone")
        before = self.w.observe(self.source)
        result = self.transcode()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(self.source.with_name("short clip-transcoded.mp4").exists())
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))

    def test_interruption_after_first_batch_item_keeps_it_and_stops_the_next(self):
        first = self.make_video("batch/a-first.mp4")
        second = self.make_video("batch/z-second.mp4")
        self.plan_update(video_interrupt_after_first_item=True)
        first_before = self.w.observe(first)
        second_before = self.w.observe(second)
        result = self.w.dispatch("video", "--size", "hd720", "--crf", "23", "--codec", "libx264",
                                 "--container", "mp4", "--", first, second)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(first.with_name("a-first-transcoded.mp4").is_file())
        self.assertFalse(second.with_name("z-second-transcoded.mp4").exists())
        encoded = [args for args in self.ffmpeg_calls(result) if args[-1] != "-"]
        self.assertEqual(len(encoded), 1)
        self.assertEqual(self.w.observe(first), first_before)
        self.assertEqual(self.w.observe(second), second_before)
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.w.root.rglob("progress.refs")))

    def test_original_webm_container_rejects_incompatible_h264_without_forcing_mp4(self):
        webm = self.w.path("input/incompatible.webm")
        subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=64x48:rate=5:duration=0.4",
            "-c:v", "libvpx", "-deadline", "realtime", str(webm),
        ], check=True, timeout=15)
        result = self.transcode(webm, codec="libx264", container="orig")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.ffmpeg_calls(result))
        self.assertFalse(webm.with_name("incompatible-transcoded.webm").exists())

    def test_exif_rotation_metadata_is_applied_to_video_pixels_and_not_doubled(self):
        rotated = self.w.path("input/rotated.mp4")
        subprocess.run([
            self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-display_rotation", "90", "-i", str(self.source), "-c", "copy", str(rotated),
        ], check=True, timeout=15)
        before = self.w.observe(rotated)
        result = self.transcode(rotated, container="orig")
        self.assertEqual(result.returncode, 0, f"{result.stderr}\n{result.calls}")
        output = rotated.with_name("rotated-transcoded.mp4")
        details = self.probe_text(output)
        self.assertIn("width=48", details)
        self.assertIn("height=64", details)
        self.assertEqual(self.w.observe(rotated), before)
        rotation = subprocess.run([
            self.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream_tags=rotate:stream_side_data=rotation", "-of", "default=noprint_wrappers=1", "-i", str(output),
        ], check=True, capture_output=True, text=True, timeout=10).stdout
        self.assertNotRegex(rotation, r"(?:rotation|rotate)=\s*-?90(?:\.0+)?")
