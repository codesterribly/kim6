"""GIF native reconstruction and dispatcher checks."""

import importlib.util
from pathlib import Path
import shutil
import unittest

from support import Workspace

engine = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_gif_metadata.py"
)
spec = importlib.util.spec_from_file_location("kim_gif_native", engine)
gif = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gif)

HEADER = b"GIF89a\x01\x00\x01\x00\x00\x00\x00"
IMAGE = (
    b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00"
    b"\x02\x02\x44\x01\x00"
)
GCE = b"\x21\xf9\x04\x09\x0a\x00\x00\x00"
LOOP = b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"


class GIFParserTests(unittest.TestCase):

    def test_remove_comment(self):
        source = HEADER + b"\x21\xfe\x06secret\x00" + IMAGE + b"\x3b"
        result, removed = gif.reconstruct(source)
        self.assertEqual(removed, 1)
        self.assertNotIn(b"secret", result)
        self.assertIn(IMAGE, result)

    def test_preserve_animation(self):
        source = HEADER + LOOP + GCE + IMAGE + GCE + IMAGE + b"\x3b"
        self.assertEqual(gif.reconstruct(source), (source, 0))

    def test_remove_xmp(self):
        xmp = b"\x21\xff\x0bXMP DataXMP\x06secret\x00"
        result, removed = gif.reconstruct(
            HEADER + xmp + IMAGE + b"\x3b"
        )
        self.assertEqual(removed, 1)
        self.assertNotIn(b"secret", result)

    def test_unknown_application_refused(self):
        item = b"\x21\xff\x0bCUSTOMAPP01\x01\x01\x00"
        with self.assertRaises(gif.UnsafeGIF):
            gif.reconstruct(HEADER + item + IMAGE + b"\x3b")

    def test_trailing_data_refused(self):
        with self.assertRaises(gif.UnsafeGIF):
            gif.reconstruct(HEADER + IMAGE + b"\x3bextra")

    def test_truncated_frame_refused(self):
        with self.assertRaises(gif.UnsafeGIF):
            gif.reconstruct(HEADER + IMAGE[:-2])


class GIFDispatcherTests(unittest.TestCase):

    def setUp(self):
        if not shutil.which("exiftool"):
            self.skipTest("ExifTool required")
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_GIF_ENGINE"] = "native"
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        self.w.env["KIM_POLICY"] = "create"

    def create_gif(self, filename, data):
        source = self.w.path("input/" + filename)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
        return source

    def test_create_preserves_original(self):
        source = self.create_gif(
            "animation.gif",
            HEADER + LOOP + GCE + IMAGE + b"\x3b",
        )
        before = self.w.observe(source)
        result = self.w.dispatch(
            "stripmeta", "--mode", "all", "--", source
        )
        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )
        target = source.with_name("animation_stripped.gif")
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), source.read_bytes())
        self.assertEqual(self.w.observe(source), before)

    def test_missing_engine_preserves_original(self):
        source = self.create_gif(
            "missing.gif", HEADER + IMAGE + b"\x3b"
        )
        before = self.w.observe(source)
        (self.w.control / "kim_gif_metadata.py").unlink()
        result = self.w.dispatch(
            "stripmeta", "--mode", "all", "--", source
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(source), before)
        self.assertFalse(
            source.with_name("missing_stripped.gif").exists()
        )


if __name__ == "__main__":
    unittest.main()
