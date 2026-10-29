"""JPEG/WebP lossless container and dispatcher tests."""

import importlib.util
from pathlib import Path
import shutil
import struct
import unittest

from support import Workspace


ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_jpeg_webp_metadata.py"
)

spec = importlib.util.spec_from_file_location(
    "kim_native_container", ENGINE
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def jpeg_segment(marker, payload):
    return (
        b'\xff'
        + bytes([marker])
        + struct.pack('>H', len(payload) + 2)
        + payload
    )


def jpeg_fixture(*segments):
    return (
        b'\xff\xd8'
        + b''.join(segments)
        + b'\xff\xda\x00\x02'
        + b'\x11\x22\x33\xff\xd9'
    )


def webp_chunk(kind, payload):
    return (
        kind
        + struct.pack('<I', len(payload))
        + payload
        + (b'\x00' if len(payload) & 1 else b'')
    )


def webp_fixture(*chunks):
    body = b'WEBP' + b''.join(chunks)
    return (
        b'RIFF'
        + struct.pack('<I', len(body))
        + body
    )


class NativeContainerTests(unittest.TestCase):

    def test_jpeg_scan_is_byte_identical(self):
        source = jpeg_fixture(
            jpeg_segment(0xe1, b'private XMP'),
            jpeg_segment(0xe0, b'JFIF\x00\x01\x02'),
        )

        output, removed = native.jpeg(source)

        self.assertEqual(removed, 1)
        self.assertNotIn(b'private XMP', output)
        self.assertIn(b'JFIF\x00', output)
        self.assertEqual(
            source[source.index(b'\xff\xda'):],
            output[output.index(b'\xff\xda'):],
        )
        self.assertEqual(
            native.jpeg(output),
            (output, 0),
        )

    def test_jpeg_orientation_retained(self):
        source = jpeg_fixture(
            jpeg_segment(
                0xe1,
                native.orientation_only_exif(6),
            )
        )

        output, _ = native.jpeg(source)

        self.assertIn(
            native.orientation_only_exif(6),
            output,
        )

    def test_jpeg_incomplete_icc_refused(self):
        source = jpeg_fixture(
            jpeg_segment(
                0xe2,
                b'ICC_PROFILE\x00\x01\x02payload',
            )
        )

        with self.assertRaises(native.UnsafeImage):
            native.jpeg(source)

    def test_webp_encoded_image_preserved(self):
        image = webp_chunk(b'VP8 ', b'abcd')
        xmp = webp_chunk(b'XMP ', b'private')
        vp8x = webp_chunk(
            b'VP8X',
            b'\x04' + bytes(9),
        )

        source = webp_fixture(vp8x, image, xmp)
        output, count = native.webp(source)

        self.assertEqual(count, 2)
        self.assertIn(image, output)
        self.assertNotIn(xmp, output)
        self.assertEqual(
            native.webp(output),
            (output, 0),
        )

    def test_webp_animation_chunks_preserved(self):
        vp8x = webp_chunk(
            b'VP8X',
            b'\x22' + bytes(9),
        )
        icc = webp_chunk(b'ICCP', b'ICCdata')
        anim = webp_chunk(b'ANIM', bytes(6))
        frame = webp_chunk(b'ANMF', bytes(16))

        output, _ = native.webp(
            webp_fixture(vp8x, icc, anim, frame)
        )

        for item in (icc, anim, frame):
            self.assertIn(item, output)

    def test_invalid_riff_rejected(self):
        source = webp_fixture(
            webp_chunk(b'VP8 ', b'abcd')
        )

        with self.assertRaises(native.UnsafeImage):
            native.webp(source + b'extra')


class NativeDispatcherTests(unittest.TestCase):

    def setUp(self):
        if not shutil.which('exiftool'):
            self.skipTest('ExifTool required')

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.env['KIM_JPEG_WEBP_ENGINE'] = 'native'
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()

    def test_native_jpeg_create_preserves_original(self):
        source = self.w.jpeg('input/native.jpg')
        original = self.w.observe(source)

        self.w.env['KIM_POLICY'] = 'create'

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all',
            '--', source,
        )

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        target = source.with_name(
            'native_stripped.jpg'
        )

        self.assertTrue(target.is_file())
        self.assertEqual(
            original, self.w.observe(source)
        )

        self.assertFalse(
            list(self.w.root.rglob('.kim6-stage.*'))
        )

    def test_missing_native_engine_fails_closed(self):
        source = self.w.jpeg('input/native.jpg')
        original = self.w.observe(source)

        self.w.env['KIM_POLICY'] = 'create'

        (self.w.control /
         'kim_jpeg_webp_metadata.py').unlink()

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all',
            '--', source,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            original, self.w.observe(source)
        )
        self.assertFalse(
            source.with_name(
                'native_stripped.jpg'
            ).exists()
        )


if __name__ == '__main__':
    unittest.main()
