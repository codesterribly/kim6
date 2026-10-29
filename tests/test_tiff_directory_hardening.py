"""Classic TIFF directory and compressed-payload verification tests."""

import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_tiff_verify.py"
)

spec = importlib.util.spec_from_file_location(
    "kim_tiff_directory", ENGINE
)
tiff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiff)


def fixture(
    *,
    endian="<",
    tiled=False,
    frames=(b"compressed-frame-0",),
    circular=False,
    subifd=False,
):
    """Build a structurally valid Classic TIFF directory chain.

    Payloads are controlled bytes because the verifier compares
    encoded data; decoding is not needed for these structural tests.
    """
    order = b"II" if endian == "<" else b"MM"

    count = len(frames)
    if not 1 <= count <= 3:
        raise ValueError("fixture supports 1–3 directories")

    first_ifd = 8
    entry_count = 3 if subifd else 2
    directory_size = 2 + 12 * entry_count + 4
    offsets = [
        first_ifd + index * directory_size
        for index in range(count)
    ]

    payload_start = (
        first_ifd + directory_size * count + 32
    )

    payload_offsets = []
    cursor = payload_start

    for frame in frames:
        payload_offsets.append(cursor)
        cursor += len(frame) + 16

    output = bytearray(cursor + 16)
    output[:2] = order

    def word(pos, value):
        struct.pack_into(endian + "H", output, pos, value)

    def dword(pos, value):
        struct.pack_into(endian + "I", output, pos, value)

    word(2, 42)
    dword(4, first_ifd)

    offset_tag = 324 if tiled else 273
    length_tag = 325 if tiled else 279

    for index, frame in enumerate(frames):
        pos = offsets[index]

        word(pos, entry_count)
        entry = pos + 2

        for tag, value in (
            (offset_tag, payload_offsets[index]),
            (length_tag, len(frame)),
        ):
            word(entry, tag)
            word(entry + 2, 4)
            dword(entry + 4, 1)
            dword(entry + 8, value)
            entry += 12

        if subifd:
            word(entry, 330)
            word(entry + 2, 4)
            dword(entry + 4, 1)
            dword(entry + 8, 0)
            entry += 12

        next_offset = (
            offsets[index + 1]
            if index + 1 < count
            else 0
        )

        if circular and index == count - 1:
            next_offset = offsets[0]

        dword(entry, next_offset)

        start = payload_offsets[index]
        output[start:start + len(frame)] = frame

    return bytes(output)


class TIFFDirectoryTests(unittest.TestCase):

    def extract(self, data):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "image.tif"
            path.write_bytes(data)
            return tiff.encoded_payloads(path)

    def verify(self, before, after):
        with tempfile.TemporaryDirectory() as root:
            original = Path(root) / "original.tif"
            candidate = Path(root) / "candidate.tif"

            original.write_bytes(before)
            candidate.write_bytes(after)

            return subprocess.run(
                [
                    sys.executable,
                    "-B", str(ENGINE),
                    "--before", str(original),
                    "--after", str(candidate),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

    def test_little_endian_strip(self):
        data = fixture(frames=(b"LZW DATA",))
        self.assertEqual(
            self.extract(data),
            ((b"LZW DATA",),),
        )

    def test_big_endian_strip(self):
        data = fixture(
            endian=">",
            frames=(b"BIG ENDIAN DATA",),
        )
        self.assertEqual(
            self.extract(data),
            ((b"BIG ENDIAN DATA",),),
        )

    def test_tiled_image_payload(self):
        data = fixture(
            tiled=True,
            frames=(b"TILE DATA",),
        )
        self.assertEqual(
            self.extract(data),
            ((b"TILE DATA",),),
        )

    def test_multiple_top_level_directories(self):
        data = fixture(
            frames=(
                b"FIRST FRAME",
                b"SECOND FRAME",
                b"THIRD FRAME",
            )
        )

        self.assertEqual(
            self.extract(data),
            (
                (b"FIRST FRAME",),
                (b"SECOND FRAME",),
                (b"THIRD FRAME",),
            ),
        )

        result = self.verify(data, data)
        self.assertEqual(
            result.returncode, 0,
            result.stderr,
        )

    def test_second_directory_corruption_refused(self):
        original = fixture(
            frames=(b"frame-one", b"frame-two"),
        )
        modified = fixture(
            frames=(b"frame-one", b"frame-TWO"),
        )

        result = self.verify(original, modified)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "compressed TIFF image data changed",
            result.stderr,
        )

    def test_tile_corruption_refused(self):
        original = fixture(
            tiled=True,
            frames=(b"tile-original",),
        )
        modified = fixture(
            tiled=True,
            frames=(b"tile-ORIGINAL",),
        )

        result = self.verify(original, modified)
        self.assertNotEqual(result.returncode, 0)

    def test_circular_directory_chain_refused(self):
        data = fixture(
            frames=(b"one", b"two"),
            circular=True,
        )

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.extract(data)

    def test_nested_subifd_refused(self):
        data = fixture(
            frames=(b"nested-data",),
            subifd=True,
        )

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.extract(data)

    def test_truncated_encoded_payload_refused(self):
        data = fixture(
            frames=(b"protected-payload",),
        )

        # Change the strip length in the first directory to
        # something extending beyond the end of the file.
        changed = bytearray(data)
        struct.pack_into("<I", changed, 8 + 2 + 12 + 8, 0xFFFFFFFF)

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.extract(changed)

    def test_duplicate_strip_offset_tag_refused(self):
        data = fixture(frames=(b"duplicated",))

        changed = bytearray(data)

        # The second entry's tag becomes a duplicate of the first.
        struct.pack_into("<H", changed, 8 + 2 + 12, 273)

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.extract(changed)

    def test_rejects_directory_added_or_removed(self):
        before = fixture(frames=(b"one", b"two"))
        after = fixture(frames=(b"one",))

        result = self.verify(before, after)
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_invalid_tiff_even_when_files_identical(self):
        invalid = b"not a TIFF file"

        result = self.verify(invalid, invalid)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
