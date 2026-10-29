"""Byte-identical presentation verification for selective metadata edits."""

import importlib.util
from pathlib import Path
import struct
import unittest

engine = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_jpeg_webp_metadata.py"
)

spec = importlib.util.spec_from_file_location(
    "kim_integrity", engine
)

native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def segment(code, payload):
    return (
        b'\xff' + bytes([code])
        + struct.pack('>H', len(payload) + 2)
        + payload
    )


def jpeg(*segments):
    return (
        b'\xff\xd8'
        + b''.join(segments)
        + b'\xff\xda\x00\x02'
        + b'\x11\x22\xff\xd9'
    )


def chunk(kind, payload):
    return (
        kind
        + struct.pack('<I', len(payload))
        + payload
        + (b'\x00' if len(payload) & 1 else b'')
    )


def webp(*chunks):
    body = b'WEBP' + b''.join(chunks)
    return b'RIFF' + struct.pack('<I', len(body)) + body


class SelectiveIntegrityTests(unittest.TestCase):

    def test_jpeg_metadata_change_accepted(self):
        before = jpeg(
            segment(0xe1, b'old XMP'),
            segment(0xfe, b'comment'),
        )
        after = jpeg(segment(0xe1, b'new XMP'))

        native.verify_selective(before, after, 'jpeg')

    def test_jpeg_scan_change_rejected(self):
        before = jpeg(segment(0xe1, b'XMP'))
        after = before.replace(b'\x11\x22', b'\x11\x23')

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'jpeg')

    def test_jpeg_icc_change_rejected(self):
        before = jpeg(
            segment(0xe2, b'ICC_PROFILE\x00\x01\x01AAAA')
        )
        after = jpeg(
            segment(0xe2, b'ICC_PROFILE\x00\x01\x01BBBB')
        )

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'jpeg')

    def test_jpeg_quantization_change_rejected(self):
        before = jpeg(segment(0xdb, b'quantA'))
        after = jpeg(segment(0xdb, b'quantB'))

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'jpeg')

    def test_webp_xmp_removal_accepted(self):
        frame = chunk(b'VP8 ', b'frames')

        before = webp(
            chunk(b'VP8X', b'\x04' + bytes(9)),
            frame,
            chunk(b'XMP ', b'private'),
        )

        after = webp(
            chunk(b'VP8X', bytes(10)),
            frame,
        )

        native.verify_selective(before, after, 'webp')

    def test_webp_frame_change_rejected(self):
        before = webp(chunk(b'VP8 ', b'frames'))
        after = webp(chunk(b'VP8 ', b'FRAMES'))

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'webp')

    def test_webp_icc_change_rejected(self):
        header = chunk(b'VP8X', b'\x20' + bytes(9))
        frame = chunk(b'VP8 ', b'frames')

        before = webp(
            header, chunk(b'ICCP', b'profile1'), frame
        )
        after = webp(
            header, chunk(b'ICCP', b'profile2'), frame
        )

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'webp')

    def test_webp_animation_change_rejected(self):
        header = chunk(b'VP8X', b'\x02' + bytes(9))
        animation = chunk(b'ANIM', bytes(6))

        before = webp(
            header, animation,
            chunk(b'ANMF', bytes(16)),
        )
        after = webp(
            header, animation,
            chunk(b'ANMF', bytes(15) + b'\x01'),
        )

        with self.assertRaises(native.UnsafeImage):
            native.verify_selective(before, after, 'webp')


if __name__ == '__main__':
    unittest.main()
