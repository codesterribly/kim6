"""BigTIFF 64-bit directory, tile and SubIFD safety tests."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_tiff_verify.py"
)

spec = importlib.util.spec_from_file_location(
    "bigtiff_runtime", ENGINE
)
tiff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiff)


def sample(
    endian="<",
    tiles=False,
    child=False,
    payload=b"primary",
    subpayload=b"preview",
    invalid_header=False,
):
    out = bytearray(600)
    out[:2] = b"II" if endian == "<" else b"MM"

    def u16(pos, value):
        struct.pack_into(endian + "H", out, pos, value)

    def u64(pos, value):
        struct.pack_into(endian + "Q", out, pos, value)

    u16(2, 43)
    u16(4, 4 if invalid_header else 8)
    u16(6, 0)
    u64(8, 16)

    def directory(pos, encoded, where, sub=None):
        count = 3 if sub else 2
        u64(pos, count)

        entries = [
            (324 if tiles else 273, 16, 1, where),
            (325 if tiles else 279, 16, 1, len(encoded)),
        ]

        if sub:
            entries.append((330, 18, 1, sub))

        for index, (tag, typ, amount, value) in enumerate(entries):
            entry = pos + 8 + index * 20
            u16(entry, tag)
            u16(entry + 2, typ)
            u64(entry + 4, amount)
            u64(entry + 12, value)

        u64(pos + 8 + count * 20, 0)
        out[where:where + len(encoded)] = encoded

    directory(16, payload, 300, 128 if child else None)

    if child:
        directory(128, subpayload, 400)

    return bytes(out)


class BigTIFFTests(unittest.TestCase):

    def inspect(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tif"
            path.write_bytes(data)
            return tiff.encoded_payloads(path)

    def test_little_endian(self):
        self.assertEqual(
            self.inspect(sample()),
            ((b"primary",),),
        )

    def test_big_endian(self):
        self.assertEqual(
            self.inspect(sample(">")),
            ((b"primary",),),
        )

    def test_tiles(self):
        self.assertEqual(
            self.inspect(sample(tiles=True)),
            ((b"primary",),),
        )

    def test_nested_preview(self):
        result = self.inspect(sample(child=True))
        self.assertIn(b"preview", repr(result).encode())

    def test_nested_corruption(self):
        self.assertNotEqual(
            self.inspect(sample(child=True)),
            self.inspect(sample(
                child=True,
                subpayload=b"changed",
            )),
        )

    def test_primary_corruption(self):
        self.assertNotEqual(
            self.inspect(sample()),
            self.inspect(sample(payload=b"changed")),
        )

    def test_invalid_header(self):
        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(sample(invalid_header=True))

    def test_cycle(self):
        data = bytearray(sample(child=True))

        struct.pack_into(
            "<Q", data,
            16 + 8 + 2 * 20 + 12,
            16,
        )

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(bytes(data))

    def test_truncated(self):
        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(sample()[:50])

    def test_malformed_offset(self):
        data = bytearray(sample())

        struct.pack_into(
            "<Q", data,
            16 + 8 + 12,
            10**10,
        )

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(bytes(data))


if __name__ == "__main__":
    unittest.main()
