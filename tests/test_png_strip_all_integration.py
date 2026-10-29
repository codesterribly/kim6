"""Exercise real PNG full stripping through the isolated dispatcher."""

import binascii
import os
import shutil
import struct
import unittest

from support import Workspace


def chunk(kind, payload):
    return (struct.pack('>I', len(payload)) + kind + payload +
            struct.pack('>I', binascii.crc32(kind + payload) & 0xffffffff))


def chunks(data, kind):
    found = []
    pos = 8
    while pos + 12 <= len(data):
        size = struct.unpack_from('>I', data, pos)[0]
        end = pos + size + 12
        if end > len(data):
            raise AssertionError('truncated PNG fixture')
        if data[pos + 4:pos + 8] == kind:
            found.append(data[pos:end])
        pos = end
    return found


class PNGStripAllIntegrationTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('exiftool') or not shutil.which('identify'):
            self.skipTest('ExifTool and ImageMagick required')

        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        self.w.approve_overwrite()

        self.source = self.w.png('input/private.png')
        raw = self.source.read_bytes()

        self.source.write_bytes(
            raw[:33] +
            chunk(b'tEXt', b'prompt\x00private generation prompt') +
            chunk(b'tEXt', b'Copyright\x00Private rights') +
            raw[33:]
        )

        self.assertTrue(
            (self.w.control / 'kim_png_metadata.py').is_file()
        )

    def clean(self):
        self.assertFalse(
            list(self.w.root.rglob('.kim6-stage.*'))
        )

    def test_create_preserves_source_and_image(self):
        self.w.env['KIM_POLICY'] = 'create'
        before = self.w.observe(self.source)
        before_idat = chunks(self.source.read_bytes(), b'IDAT')

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all', '--', self.source
        )

        self.assertEqual(
            0, result.returncode, (result.stderr, result.events)
        )

        target = self.source.with_name('private_stripped.png')

        self.assertTrue(target.is_file())
        self.assertEqual(before, self.w.observe(self.source))
        self.assertEqual([], chunks(target.read_bytes(), b'tEXt'))
        self.assertEqual(
            before_idat, chunks(target.read_bytes(), b'IDAT')
        )
        self.clean()

    def test_overwrite_preserves_pixels_permissions_timestamps(self):
        old = chunks(self.source.read_bytes(), b'IDAT')
        before_pixels = self.w.image_info(self.source)

        self.source.chmod(0o640)
        os.utime(
            self.source,
            ns=(
                1_600_000_000_000_000_000,
                1_600_000_001_234_567_891,
            ),
        )

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all', '--', self.source
        )

        self.assertEqual(
            0, result.returncode, (result.stderr, result.events)
        )

        self.assertEqual(
            [], chunks(self.source.read_bytes(), b'tEXt')
        )
        self.assertEqual(
            old, chunks(self.source.read_bytes(), b'IDAT')
        )
        self.assertEqual(
            before_pixels, self.w.image_info(self.source)
        )
        self.assertEqual(
            0o640, self.source.stat().st_mode & 0o777
        )
        self.assertEqual(
            1_600_000_001_234_567_891,
            self.source.stat().st_mtime_ns
        )
        self.clean()

    def test_corruption_preserves_original(self):
        raw = bytearray(self.source.read_bytes())
        raw[-5] ^= 1
        self.source.write_bytes(raw)

        before = self.w.observe(self.source)

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all', '--', self.source
        )

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))
        self.clean()

    def test_missing_companion_preserves_original(self):
        (self.w.control / 'kim_png_metadata.py').unlink()
        before = self.w.observe(self.source)

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all', '--', self.source
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn('unavailable', result.stderr)
        self.assertEqual(before, self.w.observe(self.source))
        self.clean()

    def test_missing_python_preserves_original(self):
        self.w.env['KIM_PNG_PYTHON'] = '/nonexistent/kim6-python'
        before = self.w.observe(self.source)

        result = self.w.dispatch(
            'stripmeta', '--mode', 'all', '--', self.source
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn('unavailable', result.stderr)
        self.assertEqual(before, self.w.observe(self.source))
        self.clean()


if __name__ == '__main__':
    unittest.main()
