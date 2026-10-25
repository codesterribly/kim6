"""K13: conversion preserves originals and validates actual encoded output."""
import base64
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from support import Workspace


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.source = self.workspace.ppm("input/photo 雪.ppm")
        self.workspace.env["KIM_POLICY"] = "create"

    def assert_clean(self):
        self.assertFalse(list(self.workspace.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.workspace.root.rglob(".kim6-publish.lock")))
        self.assertEqual(list((self.workspace.control / "tmp").iterdir()), [])

    def assert_real_image(self, path, fmt):
        result = subprocess.run([shutil.which("identify"), "-regard-warnings", "+ping",
                                 "-format", "%m %wx%h", "-"], input=path.read_bytes(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode(), fmt + " 3x2")

    def test_real_successful_create_is_destination_locally_staged(self):
        before = self.workspace.observe(self.source)
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_suffix(".png")
        self.assert_real_image(output, "PNG")
        self.assertEqual(set(result.outputs), {"input/photo 雪.png"})
        producer = next(e for e in result.events if e["tool"] == "magick")
        stage = Path(producer["argv"][-1])
        self.assertNotEqual(stage, output)
        self.assertEqual(stage.parent.parent, output.parent)
        self.assertTrue(stage.parent.name.startswith(".kim6-stage."))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_wrong_encoded_format_is_rejected(self):
        before = self.workspace.observe(self.source)
        self.workspace.respond("magick", output_base64=base64.b64encode(self.source.read_bytes()).decode())
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertFalse(self.source.with_suffix(".png").exists())
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertTrue(any("Failed: 1" in " ".join(c["argv"]) for c in result.calls))
        self.assert_clean()

    def test_dangling_collision_is_numbered_and_preserved(self):
        occupied = self.source.with_suffix(".png")
        occupied.symlink_to("missing")
        before = self.workspace.observe(occupied)
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(self.source.with_name("photo 雪_1.png"), "PNG")
        self.assertEqual(self.workspace.observe(occupied), before)
        self.assert_clean()

    def test_overwrite_rejects_destination_aliasing_selected_source(self):
        selected = self.workspace.png("input/selected.png")
        target = self.source.with_suffix(".png")
        os.link(selected, target)
        before = {p: self.workspace.observe(p) for p in (self.source, selected, target)}
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", self.source, selected)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c["tool"] == "magick" for c in result.calls))
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        self.assert_clean()

    def test_cancel_after_output_does_not_publish(self):
        payload = self.workspace.png(".control/reference.png").read_bytes()
        self.workspace.respond("magick", output_base64=base64.b64encode(payload).decode(), cancel=True)
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertFalse(self.source.with_suffix(".png").exists())
        self.assertTrue(any("Failed: 1" in " ".join(c["argv"]) for c in result.calls))
        self.assert_clean()

    def test_real_authorized_overwrite_keeps_mode_and_fresh_timestamp(self):
        target = self.workspace.png("input/photo 雪.png")
        target.chmod(0o640)
        os.utime(target, (1_600_000_000, 1_600_000_000))
        old = self.workspace.observe(target)
        source_before = self.workspace.observe(self.source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.use_real_conversion()
        self.workspace.use_real_mv()
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assert_real_image(target, "PNG")
        self.assertNotEqual(self.workspace.observe(target).inode, old.inode)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertNotEqual(target.stat().st_mtime_ns, old.mtime_ns)
        self.assertEqual(self.workspace.observe(self.source), source_before)
        self.assertTrue(any(e["tool"] == "mv" and e["status"] == 0 for e in result.events))
        self.assert_clean()

    def test_create_collisions_and_duplicate_basenames_batch(self):
        second = self.workspace.ppm("input/photo 雪.pnm")
        occupied = self.workspace.png("input/photo 雪.png")
        directory = self.workspace.path("input/photo 雪_1.png")
        directory.mkdir()
        link = self.workspace.path("input/photo 雪_2.png")
        link.symlink_to(occupied.name)
        before = {p: self.workspace.observe(p) for p in (self.source, second, occupied, directory, link)}
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", self.source, second)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("photo 雪_3.png", "photo 雪_4.png"):
            self.assert_real_image(self.source.with_name(name), "PNG")
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        self.assert_clean()

    def test_duplicate_overwrite_mappings_rejected_before_processing(self):
        second = self.workspace.ppm("input/photo 雪.pnm")
        self.workspace.env["KIM_POLICY"] = "overwrite"
        result = self.workspace.dispatch("convert", "png", self.source, second)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c["tool"] == "magick" for c in result.calls))
        self.assert_clean()

    def test_symlinked_parent_mapping_duplicates_rejected(self):
        alias = self.workspace.path("alias")
        alias.symlink_to(self.source.parent, target_is_directory=True)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        result = self.workspace.dispatch("convert", "png", self.source, alias / self.source.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c["tool"] == "magick" for c in result.calls))
        self.assert_clean()

    def test_symlinked_parent_is_supported_for_create(self):
        alias = self.workspace.path("alias")
        alias.symlink_to(self.source.parent, target_is_directory=True)
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", alias / self.source.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(self.source.with_suffix(".png"), "PNG")
        self.assert_clean()

    def test_same_format_overwrite_is_unchanged_noop(self):
        before = self.workspace.observe(self.source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        result = self.workspace.dispatch("convert", "PPM", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c["tool"] == "magick" for c in result.calls))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_same_format_create_keeps_numbering(self):
        before = self.workspace.observe(self.source)
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "ppm", self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(self.source.with_name("photo 雪_1.ppm"), "PPM")
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_same_format_overwrite_reencodes_when_a_jpeg_scan_option_is_requested(self):
        source = self.workspace.jpeg("input/same.jpg")
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.use_real_conversion()
        self.workspace.use_real_mv()
        before = self.workspace.observe(source)
        result = self.workspace.dispatch("convert", "--format", "jpg", "--jpeg-baseline", "--", source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any(call["tool"] == "magick" for call in result.calls))
        self.assertNotEqual(before.inode, self.workspace.observe(source).inode)
        details = subprocess.run([shutil.which("identify"), "-verbose", str(source)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertRegex(details, r"Interlace:\s+None")
        self.assert_clean()

    def test_jfif_alias_applies_jpeg_scan_options(self):
        source = self.workspace.jpeg("input/jfif-alias.jpg")
        self.workspace.env["KIM_POLICY"] = "create"
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "--format", "jfif", "--jpeg-baseline", "--", source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any(call["tool"] == "magick" and "-interlace" in call["argv"]
                            for call in result.calls))
        output = source.with_name("jfif-alias.jfif")
        details = subprocess.run([shutil.which("identify"), "-verbose", str(output)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertRegex(details, r"Interlace:\s+None")
        self.assert_clean()

    def test_real_apng_conversion_preserves_all_animation_frames(self):
        self.workspace.use_real_conversion()
        self.workspace.use_real_video_tools()
        first = self.workspace.ppm("input/apng-first.ppm")
        second = self.workspace.ppm("input/apng-second.ppm")
        second.write_bytes(b"P6\n3 2\n255\n" + bytes.fromhex(
            "000000 000000 000000 000000 ffffff 000000"))
        source = self.workspace.path("input/two-frames.gif")
        subprocess.run([shutil.which("magick"), "-delay", "20", str(first),
                        "-delay", "60", str(second), "-loop", "0", str(source)],
                       check=True, capture_output=True, timeout=15)
        before = self.workspace.observe(source)
        result = self.workspace.dispatch("convert", "apng", source)
        output = source.with_suffix(".apng")
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        self.assertTrue(output.is_file(), result.events)
        details = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
                                  "-count_frames", "-show_entries", "stream=codec_name,nb_read_frames",
                                  "-of", "default=noprint_wrappers=1", str(output)], check=True,
                                 capture_output=True, text=True, timeout=15).stdout
        self.assertIn("codec_name=apng", details)
        self.assertIn("nb_read_frames=2", details)
        import struct
        data = output.read_bytes()
        offset = 8
        animation_control = None
        delays = []
        while offset + 12 <= len(data):
            length = struct.unpack_from(">I", data, offset)[0]
            kind = data[offset + 4:offset + 8]
            if kind == b'acTL':
                animation_control = struct.unpack_from(">II", data, offset + 8)
            elif kind == b'fcTL':
                numerator, denominator = struct.unpack_from(">HH", data, offset + 28)
                delays.append((numerator, denominator))
            offset += length + 12
        self.assertEqual(animation_control, (2, 0), '2 frames and infinite playback must survive')
        self.assertEqual(len(delays), 2)
        self.assertAlmostEqual(delays[0][0] / delays[0][1], 0.2, delta=0.01)
        self.assertAlmostEqual(delays[1][0] / delays[1][1], 0.6, delta=0.01)
        producer = next(call["argv"] for call in result.calls
                        if call["tool"] == "ffmpeg" and "-progress" in call["argv"])
        self.assertEqual(producer[producer.index("-plays") + 1], "0")
        self.assertIn(b"acTL", output.read_bytes(), "success requires a real APNG animation")
        self.assertEqual(self.workspace.observe(source), before)

        roundtrip = self.workspace.dispatch("convert", "apng", output)
        self.assertEqual(roundtrip.returncode, 0, (roundtrip.stderr, roundtrip.events))
        second_output = output.with_name("two-frames_1.apng")
        self.assertTrue(second_output.is_file())
        second_probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
                                       "-count_frames", "-show_entries", "stream=codec_name,nb_read_frames",
                                       "-of", "default=noprint_wrappers=1", str(second_output)], check=True,
                                      capture_output=True, text=True, timeout=15).stdout
        self.assertIn("codec_name=apng", second_probe)
        self.assertIn("nb_read_frames=2", second_probe)
        second_data = second_output.read_bytes()
        second_offset = 8
        second_animation_control = None
        second_delays = []
        while second_offset + 12 <= len(second_data):
            length = struct.unpack_from(">I", second_data, second_offset)[0]
            kind = second_data[second_offset + 4:second_offset + 8]
            if kind == b'acTL':
                second_animation_control = struct.unpack_from(">II", second_data, second_offset + 8)
            elif kind == b'fcTL':
                numerator, denominator = struct.unpack_from(">HH", second_data, second_offset + 28)
                second_delays.append((numerator, denominator))
            second_offset += length + 12
        self.assertEqual(second_animation_control, animation_control)
        self.assertEqual(second_delays, delays)

        animated_gif = self.workspace.dispatch("convert", "gif", output)
        self.assertFalse(output.with_name("two-frames_1.gif").exists())
        self.assertFalse(any(call["tool"] == "magick" for call in animated_gif.calls))
        self.assertTrue(any(call["tool"] == "kdialog" and "APNG" in " ".join(call["argv"])
                            for call in animated_gif.calls))

        flattened = self.workspace.dispatch("convert", "jpg", output)
        self.assertFalse(output.with_suffix(".jpg").exists())
        self.assertFalse(any(call["tool"] == "magick" for call in flattened.calls))
        self.assertTrue(any(call["tool"] == "kdialog" and "APNG" in " ".join(call["argv"])
                            for call in flattened.calls))
        self.assert_clean()

    def test_real_gif_conversion_preserves_frame_delays_and_looping(self):
        self.workspace.use_real_conversion()
        magick = shutil.which("magick")
        first = self.workspace.ppm("input/gif-first.ppm")
        second = self.workspace.path("input/gif-second.ppm")
        second.write_bytes(b"P6\n3 2\n255\n" + bytes.fromhex(
            "000000 000000 000000 000000 ffffff 000000"))
        source = self.workspace.path("input/timed.gif")
        subprocess.run([magick, "-delay", "20", str(first), "-delay", "60", str(second),
                        "-loop", "0", str(source)], check=True, capture_output=True, timeout=15)
        result = self.workspace.dispatch("convert", "gif", source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = source.with_name("timed_1.gif")
        source_delays = subprocess.run([shutil.which("identify"), "-format", "%T\n", str(source)],
                                       check=True, capture_output=True, text=True, timeout=10).stdout
        output_delays = subprocess.run([shutil.which("identify"), "-format", "%T\n", str(output)],
                                       check=True, capture_output=True, text=True, timeout=10).stdout
        self.assertEqual(output_delays, source_delays)
        source_loop = subprocess.run([shutil.which("exiftool"), "-s", "-AnimationIterations", str(source)],
                                     check=True, capture_output=True, text=True, timeout=10).stdout
        output_loop = subprocess.run([shutil.which("exiftool"), "-s", "-AnimationIterations", str(output)],
                                     check=True, capture_output=True, text=True, timeout=10).stdout
        self.assertEqual(output_loop, source_loop)
        self.assertEqual(output_delays.splitlines(), ["20", "60"])
        self.assertIn("Infinite", output_loop)
        self.assert_clean()

    def test_real_optional_heic_jp2_and_jxl_decoders_are_used_when_available(self):
        self.workspace.use_real_conversion()
        magick = shutil.which("magick")
        if not magick:
            self.skipTest("ImageMagick is unavailable")
        listing = subprocess.run([magick, "-list", "format"], check=True,
                                 capture_output=True, text=True).stdout
        import re
        attempted = 0
        for extension, coder in (("heic", "HEIC"), ("jp2", "JP2"), ("jxl", "JXL")):
            readable = any(re.search(r"^\s*" + coder + r"\*?\s", line)
                           and len(line.split()) > 2 and "r" in line.split()[2]
                           for line in listing.splitlines())
            if not readable:
                continue
            attempted += 1
            encoded = self.workspace.path("input/source." + extension)
            producer = subprocess.run([magick, str(self.source), coder + ":" + str(encoded)],
                                      capture_output=True, text=True, timeout=20)
            if producer.returncode != 0 or not encoded.is_file() or encoded.stat().st_size == 0:
                self.skipTest(coder + " encoder is advertised but unusable in this ImageMagick build")
            result = self.workspace.dispatch("convert", "png", encoded)
            self.assertEqual(result.returncode, 0, (coder, result.stderr, result.events))
            self.assertEqual(self.workspace.image_info(encoded.with_suffix(".png"))[0], "PNG")
        if not attempted:
            self.skipTest("No HEIC, JPEG 2000 or JPEG XL decoder is installed")
        self.assert_clean()

    def test_hdr_input_fails_closed_for_sdr_output_without_modifying_source(self):
        self.workspace.use_real_conversion()
        magick = shutil.which("magick")
        if not magick:
            self.skipTest("ImageMagick is unavailable")
        hdr = self.workspace.path("input/high-range.exr")
        subprocess.run([magick, str(self.source), "-colorspace", "RGB", "-depth", "16", str(hdr)],
                       check=True, capture_output=True, timeout=15)
        before = self.workspace.observe(hdr)
        result = self.workspace.dispatch("convert", "jpg", hdr)
        self.assertTrue(any(call["tool"] == "kdialog" and "tone mapping" in " ".join(call["argv"])
                            for call in result.calls))
        self.assertEqual(self.workspace.observe(hdr), before)
        self.assertFalse(hdr.with_suffix(".jpg").exists())
        self.assertFalse(any(call["tool"] == "magick" for call in result.calls))
        self.assertTrue(any(call["tool"] == "kdialog" and "Failed: 1" in " ".join(call["argv"])
                            for call in result.calls))
        self.assert_clean()

    def test_format_capability_probe_fails_closed_for_unavailable_jxl_encoder(self):
        source_before = self.workspace.observe(self.source)
        self.workspace.respond("magick", stdout="JPEG* rw- JPEG\nPNG* rw- PNG\n")
        result = self.workspace.dispatch("convert", "jxl", self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.source.with_suffix(".jxl").exists())
        self.assertEqual(self.workspace.observe(self.source), source_before)
        self.assertTrue(any("JPEG XL" in " ".join(call["argv"]) or
                            "JXL" in " ".join(call["argv"]) for call in result.calls
                            if call["tool"] == "kdialog"))
        self.assert_clean()

    def test_multiframe_conversion_to_still_format_is_rejected_before_producer(self):
        first = self.workspace.ppm("input/first.ppm")
        second = self.workspace.ppm("input/second.ppm")
        source = self.workspace.path("input/animated.gif")
        subprocess.run([shutil.which("magick"), "-delay", "10", str(first),
                        "-delay", "20", str(second), str(source)], check=True,
                       capture_output=True, timeout=15)
        before = self.workspace.observe(source)
        result = self.workspace.dispatch("convert", "jpg", source)
        self.assertFalse(source.with_suffix(".jpg").exists())
        self.assertFalse(any(call["tool"] == "magick" for call in result.calls))
        self.assertEqual(self.workspace.observe(source), before)
        self.assertTrue(any(call["tool"] == "kdialog" and "multi-frame" in " ".join(call["argv"])
                            for call in result.calls))
        self.assert_clean()

    def test_jp2_lossless_uses_the_jpeg2000_rate_option_after_runtime_capability_check(self):
        self.workspace.sequence("magick", [
            {"stdout": "JP2* JP2 rw+ JPEG-2000\n"},
            {"output_base64": base64.b64encode(self.source.read_bytes()).decode()},
        ])
        result = self.workspace.dispatch("convert", "--format", "jp2", "--jp2-mode", "lossless",
                                         "--", self.source)
        producer = next(call["argv"] for call in result.calls
                        if call["tool"] == "magick" and "-list" not in call["argv"])
        self.assertIn("jp2:rate=1", producer)
        self.assertTrue(any(value.startswith("JP2:") for value in producer))
        self.assertFalse(self.source.with_suffix(".jp2").exists(),
                         "fake PPM bytes must fail JP2 validation")
        self.assert_clean()

    def test_jp2_lossy_uses_image_magick_quality_not_jpeg_options(self):
        self.workspace.sequence("magick", [
            {"stdout": "JP2* JP2 rw+ JPEG-2000\n"},
            {"output_base64": base64.b64encode(self.source.read_bytes()).decode()},
        ])
        result = self.workspace.dispatch("convert", "--format", "jp2", "--jp2-mode", "lossy",
                                         "--jp2-quality", "62", "--", self.source)
        producer = next(call["argv"] for call in result.calls
                        if call["tool"] == "magick" and "-list" not in call["argv"])
        self.assertEqual(producer[producer.index("-quality") + 1], "62")
        self.assertFalse(any("jp2:rate=1" in value for value in producer))
        self.assertFalse(self.source.with_suffix(".jp2").exists())
        self.assert_clean()

    def test_real_jpeg2000_lossless_mode_is_pixel_exact_when_encoder_exists(self):
        self.workspace.use_real_conversion()
        magick = shutil.which("magick")
        listing = subprocess.run([magick, "-list", "format"], check=True,
                                 capture_output=True, text=True).stdout
        import re
        if not any(re.search(r"^\s*JP2\*?\s", line) and len(line.split()) > 2
                   and "w" in line.split()[2] for line in listing.splitlines()):
            self.skipTest("ImageMagick JPEG 2000 encoder is unavailable")
        original = subprocess.run([magick, str(self.source), "-depth", "8", "-format",
                                   "%[pixel:p{0,0}]", "info:"], capture_output=True)
        self.assertEqual(original.returncode, 0, original.stderr)
        result = self.workspace.dispatch("convert", "--format", "jp2", "--jp2-mode", "lossless",
                                         "--", self.source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = self.source.with_suffix(".jp2")
        self.assertEqual(self.workspace.image_info(output)[0], "JP2")
        decoded = subprocess.run([magick, str(output), "-depth", "8", "-format",
                                 "%[pixel:p{0,0}]", "info:"], capture_output=True)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertEqual(decoded.stdout, original.stdout)
        self.assert_clean()

    def test_real_jpeg2000_lossy_and_16_bit_profiled_lossless_when_encoder_exists(self):
        magick = shutil.which("magick")
        if not magick:
            self.skipTest("ImageMagick is unavailable")
        listing = subprocess.run([magick, "-list", "format"], check=True,
                                 capture_output=True, text=True).stdout
        import re
        writable = any(re.search(r"^\s*JP2\*?\s", line) and len(line.split()) > 2
                       and "w" in line.split()[2] for line in listing.splitlines())
        if not writable:
            self.skipTest("ImageMagick JPEG 2000 encoder is unavailable")

        self.workspace.use_real_conversion()
        lossy = self.workspace.dispatch("convert", "--format", "jp2", "--jp2-mode", "lossy",
                                        "--jp2-quality", "65", "--", self.source)
        self.assertEqual(lossy.returncode, 0, (lossy.stderr, lossy.events))
        self.assertEqual(self.workspace.image_info(self.source.with_suffix(".jp2"))[0], "JP2")

        import struct
        sixteen = self.workspace.path("input/16-bit.ppm")
        sixteen.write_bytes(b"P6\n2 1\n65535\n" + struct.pack(">6H", 1000, 7000, 16000, 30000, 40000, 60000))
        adobe = Path("/usr/share/color/icc/colord/AdobeRGB1998.icc")
        if not adobe.is_file():
            self.skipTest("Adobe RGB ICC profile is unavailable")
        profiled = self.workspace.path("input/16-bit-profiled.tif")
        subprocess.run([magick, str(sixteen), "-profile", str(adobe), str(profiled)],
                       check=True, capture_output=True, timeout=15)
        result = self.workspace.dispatch("convert", "--format", "jp2", "--jp2-mode", "lossless",
                                         "--", profiled)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = profiled.with_suffix(".jp2")
        self.assertEqual(self.workspace.image_info(output)[:3], ("JP2", 2, 1))
        profile = subprocess.run([shutil.which("exiftool"), "-b", "-ICC_Profile", str(output)],
                                 check=True, capture_output=True, timeout=15).stdout
        self.assertTrue(profile, "lossless JPEG 2000 should retain embedded ICC when supported")
        difference = subprocess.run([magick, "compare", "-metric", "AE", str(profiled), str(output), "null:"],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(difference.returncode, 0, difference.stderr + difference.stdout)

    def test_producer_time_destination_creation_is_preserved(self):
        payload = self.workspace.png(".control/reference.png").read_bytes()
        self.workspace.respond("magick", output_base64=base64.b64encode(payload).decode(),
                               writes={"input/photo 雪.png": "concurrent owner"})
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertEqual(self.source.with_suffix(".png").read_bytes(), b"concurrent owner")
        self.assertTrue(any(e["tool"] == "ln" and e["status"] != 0 for e in result.events))
        self.assert_clean()

    def test_cross_device_publication_fails_without_copy(self):
        self.workspace.use_real_conversion()
        self.workspace.respond_to("stat", "%d", [{"stdout": "1\n"}, {"stdout": "2\n"}])
        before = self.workspace.observe(self.source)
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertFalse(self.source.with_suffix(".png").exists())
        self.assertFalse(any(c["tool"] == "cp" for c in result.calls))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_failed_item_does_not_stop_batch(self):
        second = self.workspace.ppm("input/second 雪.ppm")
        payload = self.workspace.png(".control/reference.png").read_bytes()
        self.workspace.sequence("magick", [{"status": 23},
            {"output_base64": base64.b64encode(payload).decode()}])
        result = self.workspace.dispatch("convert", "png", self.source, second)
        self.assertFalse(self.source.with_suffix(".png").exists())
        self.assert_real_image(second.with_suffix(".png"), "PNG")
        self.assertTrue(any("Failed: 1" in " ".join(c["argv"]) and "Succeeded: 1" in " ".join(c["argv"])
                            for c in result.calls))
        self.assert_clean()

    def test_cancellation_during_metadata_preparation_preserves_destination(self):
        target = self.workspace.png("input/photo 雪.png")
        before = self.workspace.observe(target)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.use_real_conversion()
        self.workspace.respond("chmod", cancel=True)
        result = self.workspace.dispatch("convert", "png", self.source)
        self.assertEqual(self.workspace.observe(target), before)
        self.assertFalse(any(c["tool"] == "mv" for c in result.calls))
        self.assert_clean()

    def test_leading_and_trailing_stem_spaces_are_preserved(self):
        source = self.workspace.ppm("input/ space 雪 .ppm")
        self.workspace.use_real_conversion()
        result = self.workspace.dispatch("convert", "png", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(source.with_suffix(".png"), "PNG")
        self.assert_clean()

    def test_newline_mapping_is_rejected_before_processing(self):
        source = self.workspace.ppm("input/ambiguous\nname.ppm")
        before = self.workspace.observe(source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        result = self.workspace.dispatch("convert", "png", source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c["tool"] == "magick" for c in result.calls))
        self.assertEqual(self.workspace.observe(source), before)
        self.assert_clean()


def failure_case(mode, failure):
    def test(self):
        w = self.workspace
        w.env["KIM_POLICY"] = mode
        target = self.source.with_suffix(".png")
        retained = w.png("retained.png")
        if mode == "overwrite":
            w.png("input/photo 雪.png")
        if failure in ("symlink", "dangling"):
            if target.exists():
                target.unlink()
            target.symlink_to("../retained.png" if failure == "symlink" else "../missing.png")
        before = {p: w.observe(p) for p in (self.source, target, retained)}
        payload = w.png(".control/reference.png").read_bytes()
        response = {"output_base64": base64.b64encode(payload).decode()}
        if failure == "before":
            response = {"status": 23}
        elif failure == "partial":
            response = {"status": 23, "output_base64": base64.b64encode(b"partial").decode()}
        elif failure in ("empty", "corrupt", "truncated", "wrong_format"):
            data = {"empty": b"", "corrupt": b"garbage", "truncated": payload[:45],
                    "wrong_format": self.source.read_bytes()}[failure]
            response = {"output_base64": base64.b64encode(data).decode()}
        elif failure == "publication":
            w.respond("ln" if mode == "create" else "mv", status=73)
        elif failure == "metadata":
            w.respond("chmod", status=73)
        elif failure == "encoder":
            response = {"status": 1, "stderr": "no encode delegate\n"}
        elif failure == "decoder":
            w.respond("identify", status=1, stderr="no decode delegate\n")
        elif failure == "staging":
            w.sequence("mktemp", [{"passthrough": True}, {"status": 73}])
        w.respond("magick", **response)
        result = w.dispatch("convert", "png", self.source)
        for p, state in before.items():
            self.assertEqual(w.observe(p), state)
        self.assertTrue(any("Failed: 1" in " ".join(c["argv"]) for c in result.calls), result.calls)
        self.assertFalse(any(c["tool"] == "cp" for c in result.calls))
        self.assert_clean()
    return test


for _mode in ("create", "overwrite"):
    for _failure in ("before", "partial", "empty", "corrupt", "truncated", "wrong_format",
                     "publication", "encoder", "decoder", "staging"):
        setattr(ConversionTests, "test_" + _mode + "_preserves_on_" + _failure,
                failure_case(_mode, _failure))
for _failure in ("symlink", "dangling", "metadata"):
    setattr(ConversionTests, "test_overwrite_preserves_on_" + _failure, failure_case("overwrite", _failure))


def real_format_case(extension, magic):
    def test(self):
        executable = shutil.which("magick")
        if not executable:
            self.skipTest("ImageMagick is unavailable")
        coder = {"avif": "AVIF", "heic": "HEIC", "heif": "HEIC", "webp": "WEBP",
                 "jxl": "JXL", "jp2": "JP2", "j2k": "JP2", "jpc": "JP2"}.get(extension)
        if coder:
            import re
            formats = subprocess.run([executable, "-list", "format"], capture_output=True,
                                     text=True, check=True).stdout
            writable = any(re.search(r"^\s*" + coder + r"\*?\s", line)
                           and len(line.split()) > 2 and "w" in line.split()[2]
                           for line in formats.splitlines())
            if not writable:
                self.skipTest("ImageMagick " + coder + " encoder is unavailable")
        self.workspace.use_real_conversion()
        before = self.workspace.observe(self.source)
        result = self.workspace.dispatch("convert", extension, self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(self.source.with_suffix("." + extension), magic)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()
    return test


for _extension, _magic in (("jpg", "JPEG"), ("jpeg", "JPEG"), ("jpe", "JPEG"), ("jfif", "JPEG"),
        ("png8", "PNG"), ("gif", "GIF"), ("gif87", "GIF"), ("bmp", "BMP"),
        ("dib", "BMP"), ("bmp2", "BMP2"), ("bmp3", "BMP3"), ("tif", "TIFF"), ("tiff", "TIFF"),
        ("tiff64", "TIFF64"), ("webp", "WEBP"), ("avif", "AVIF"), ("heic", "HEIC"),
        ("heif", "HEIC"), ("jxl", "JXL"), ("jp2", "JP2"), ("j2k", "J2K"), ("jpc", "JP2"),
        ("pdf", "PDF"), ("pnm", "PPM"), ("pgm", "PGM"), ("pbm", "PBM"), ("pam", "PAM")):
    setattr(ConversionTests, "test_real_format_" + _extension, real_format_case(_extension, _magic))


if __name__ == "__main__":
    unittest.main()
