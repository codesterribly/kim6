"""PNG/APNG metadata reconstruction regression tests."""

import binascii
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / 'src' / 'bin')
)

from kim_png_metadata import SIG, UnsafePNG, filter_png


def chunk(kind, data=b''):
    crc = binascii.crc32(kind + data) & 0xffffffff
    return (
        struct.pack('>I', len(data))
        + kind
        + data
        + struct.pack('>I', crc)
    )


def fixture(*extra):
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    image = zlib.compress(b'\x00\xff\x00\x00')

    return (
        SIG
        + chunk(b'IHDR', ihdr)
        + b''.join(extra)
        + chunk(b'IDAT', image)
        + chunk(b'IEND')
    )


class PNGMetadataTests(unittest.TestCase):

    def test_all_removes_unknown_and_ai_without_touching_image(self):
        idat = chunk(
            b'IDAT', zlib.compress(b'\x00\xff\x00\x00')
        )

        source = fixture(
            chunk(b'tEXt', b'prompt\x00secret'),
            chunk(b'vpAg', b'private'),
            chunk(b'tEXt', b'Copyright\x00rights'),
        )

        output, removed = filter_png(source, 'all')

        self.assertEqual(removed, 3)
        self.assertIn(idat, output)
        self.assertEqual(
            filter_png(output, 'all'), (output, 0)
        )

    def test_ai_keeps_copyright_and_removes_comfy_prompt(self):
        source = fixture(
            chunk(b'tEXt', b'Copyright\x00rights'),
            chunk(
                b'zTXt',
                b'workflow\x00\x00'
                + zlib.compress(b'{"class_type":"KSampler"}'),
            ),
        )

        output, removed = filter_png(source, 'ai')

        self.assertEqual(removed, 1)
        self.assertIn(b'Copyright\x00rights', output)
        self.assertNotIn(b'workflow', output)

    def test_gps_does_not_remove_ai(self):
        source = fixture(
            chunk(b'tEXt', b'GPSLatitude\x0042'),
            chunk(b'tEXt', b'workflow\x00secret'),
        )

        output, removed = filter_png(source, 'gps')

        self.assertEqual(removed, 1)
        self.assertIn(b'workflow', output)

    def test_apng_chunks_are_preserved(self):
        animation = (
            chunk(
                b'acTL',
                b'\x00\x00\x00\x01\x00\x00\x00\x00'
            ),
            chunk(b'fcTL', b'\x00' * 26),
        )

        source = fixture(
            *animation,
            chunk(b'tEXt', b'prompt\x00secret'),
        )

        output, _ = filter_png(source, 'all')

        for item in animation:
            self.assertIn(item, output)

    def test_corrupt_crc_is_rejected(self):
        source = bytearray(fixture())
        source[-5] ^= 1

        with self.assertRaises(UnsafePNG):
            filter_png(bytes(source), 'all')

    def test_exif_requires_structured_handling(self):
        source = fixture(
            chunk(b'eXIf', b'not parsed')
        )

        for mode in ('all', 'ai', 'gps'):
            with self.subTest(mode=mode):
                with self.assertRaises(UnsafePNG):
                    filter_png(source, mode)

    def test_xmp_requires_structured_handling(self):
        source = fixture(
            chunk(
                b'iTXt',
                b'XML:com.adobe.xmp\x00\x00\x00'
                b'\x00\x00<x:xmpmeta/>',
            )
        )

        for mode in ('ai', 'gps'):
            with self.subTest(mode=mode):
                with self.assertRaises(UnsafePNG):
                    filter_png(source, mode)

    def test_trailing_bytes_are_rejected(self):
        with self.assertRaises(UnsafePNG):
            filter_png(fixture() + b'secret', 'all')


if __name__ == '__main__':
    unittest.main()
