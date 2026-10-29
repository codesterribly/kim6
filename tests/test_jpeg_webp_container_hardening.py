"""JPEG/WebP malformed-container rejection regressions."""

import importlib.util
from pathlib import Path
import struct
import unittest


ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_jpeg_webp_metadata.py"
)

spec = importlib.util.spec_from_file_location(
    "kim_container_hardening", ENGINE
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def jpeg(scan):
    return (
        b'\xff\xd8'
        + b'\xff\xda\x00\x02'
        + scan
    )


def chunk(tag, data):
    return (
        tag
        + struct.pack('<I', len(data))
        + data
        + (b'\x00' if len(data) % 2 else b'')
    )


def webp(*items):
    body = b'WEBP' + b''.join(items)
    return b'RIFF' + struct.pack('<I', len(body)) + body


class ContainerHardeningTests(unittest.TestCase):

    def test_valid_baseline_jpeg(self):
        source = jpeg(b'\x12\x34\xff\xd9')
        output, changes = native.jpeg(source)

        self.assertEqual(output, source)
        self.assertEqual(changes, 0)

    def test_valid_jpeg_byte_stuffing(self):
        source = jpeg(
            b'\x12\xff\x00\x34\xff\xd9'
        )

        self.assertEqual(native.jpeg(source), (source, 0))

    def test_valid_jpeg_restart_marker(self):
        source = jpeg(
            b'\x12\xff\xd0\x34\xff\xd9'
        )

        self.assertEqual(native.jpeg(source), (source, 0))

    def test_jpeg_rejects_trailing_bytes(self):
        source = jpeg(
            b'\x12\xff\xd9private'
        )

        with self.assertRaises(native.UnsafeImage):
            native.jpeg(source)

    def test_jpeg_rejects_unescaped_marker(self):
        source = jpeg(
            b'\x12\xff\xfe\x34\xff\xd9'
        )

        with self.assertRaises(native.UnsafeImage):
            native.jpeg(source)

    def test_jpeg_rejects_truncated_marker(self):
        source = jpeg(b'\x12\xff')

        with self.assertRaises(native.UnsafeImage):
            native.jpeg(source)

    def test_webp_ordinary_image(self):
        source = webp(chunk(b'VP8 ', b'abcd'))

        self.assertEqual(native.webp(source), (source, 0))

    def test_webp_xmp_without_feature_flag(self):
        source = webp(
            chunk(b'VP8X', bytes(10)),
            chunk(b'VP8 ', b'abcd'),
            chunk(b'XMP ', b'private'),
        )

        with self.assertRaises(native.UnsafeImage):
            native.webp(source)

    def test_webp_missing_advertised_icc(self):
        source = webp(
            chunk(b'VP8X', b'\x20' + bytes(9)),
            chunk(b'VP8 ', b'abcd'),
        )

        with self.assertRaises(native.UnsafeImage):
            native.webp(source)

    def test_webp_animation_without_flag(self):
        source = webp(
            chunk(b'VP8X', bytes(10)),
            chunk(b'ANIM', bytes(6)),
            chunk(b'ANMF', bytes(16)),
        )

        with self.assertRaises(native.UnsafeImage):
            native.webp(source)

    def test_webp_animation_without_frames(self):
        source = webp(
            chunk(b'VP8X', b'\x02' + bytes(9)),
            chunk(b'ANIM', bytes(6)),
        )

        with self.assertRaises(native.UnsafeImage):
            native.webp(source)


if __name__ == "__main__":
    unittest.main()
