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
        self.workspace.use_real_conversion()
        before = self.workspace.observe(self.source)
        result = self.workspace.dispatch("convert", extension, self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_real_image(self.source.with_suffix("." + extension), magic)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()
    return test


for _extension, _magic in (("jpg", "JPEG"), ("jpeg", "JPEG"), ("jpe", "JPEG"),
        ("png8", "PNG"), ("gif", "GIF"), ("gif87", "GIF"), ("bmp", "BMP"),
        ("bmp2", "BMP2"), ("bmp3", "BMP3"), ("tif", "TIFF"), ("tiff", "TIFF"),
        ("tiff64", "TIFF64"), ("webp", "WEBP"), ("avif", "AVIF"), ("heic", "HEIC"),
        ("pdf", "PDF"), ("pnm", "PPM"), ("pgm", "PGM"), ("pbm", "PBM"), ("pam", "PAM")):
    setattr(ConversionTests, "test_real_format_" + _extension, real_format_case(_extension, _magic))


if __name__ == "__main__":
    unittest.main()
