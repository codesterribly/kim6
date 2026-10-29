"""Verify TIFF compressed strip/tile bytes survive metadata edits.

Classic TIFF, both byte orders, multiple top-level IFDs.
Unsupported image layouts fail closed rather than passing unchecked.
"""

import os
from pathlib import Path
import shutil
import struct
import subprocess
import unittest

from support import Workspace


class UnsupportedTIFF(ValueError):
    pass


def encoded_payloads(path):
    """Return the compressed image payloads in IFD order."""
    data = Path(path).read_bytes()

    if len(data) < 8:
        raise UnsupportedTIFF("truncated TIFF")

    byte_order = data[:2]

    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        raise UnsupportedTIFF("invalid TIFF byte order")

    def u16(pos):
        if pos < 0 or pos + 2 > len(data):
            raise UnsupportedTIFF("truncated TIFF word")
        return struct.unpack_from(endian + "H", data, pos)[0]

    def u32(pos):
        if pos < 0 or pos + 4 > len(data):
            raise UnsupportedTIFF("truncated TIFF dword")
        return struct.unpack_from(endian + "I", data, pos)[0]

    if u16(2) != 42:
        raise UnsupportedTIFF(
            "unsupported TIFF format or BigTIFF"
        )

    offset = u32(4)
    visited = set()
    images = []

    while offset:
        if offset in visited:
            raise UnsupportedTIFF("circular IFD chain")
        visited.add(offset)

        count = u16(offset)
        entries = offset + 2

        if entries + count * 12 + 4 > len(data):
            raise UnsupportedTIFF("truncated IFD")

        tags = {}

        for index in range(count):
            pos = entries + index * 12
            tag = u16(pos)
            typ = u16(pos + 2)
            elements = u32(pos + 4)
            value = u32(pos + 8)

            if tag in tags:
                raise UnsupportedTIFF("duplicate TIFF tag")

            tags[tag] = (
                typ, elements, value, pos + 8
            )

        # SubIFDs may contain other image planes or reduced images.
        # They need full traversal, so reject them for now.
        if 330 in tags:
            raise UnsupportedTIFF(
                "SubIFDs require additional validation"
            )

        def values(tag):
            if tag not in tags:
                raise UnsupportedTIFF(
                    f"missing TIFF tag {tag}"
                )

            typ, elements, value, inline = tags[tag]

            if typ == 3:
                width = 2
                fmt = "H"
            elif typ == 4:
                width = 4
                fmt = "I"
            else:
                raise UnsupportedTIFF(
                    f"unsupported TIFF tag type {typ}"
                )

            if not elements or elements > 100000:
                raise UnsupportedTIFF("invalid element count")

            size = elements * width
            pos = inline if size <= 4 else value

            if pos < 0 or pos + size > len(data):
                raise UnsupportedTIFF(
                    "TIFF value extends beyond file"
                )

            return struct.unpack_from(
                endian + str(elements) + fmt,
                data,
                pos,
            )

        tiled = 324 in tags or 325 in tags
        stripped = 273 in tags or 279 in tags

        if tiled and stripped:
            raise UnsupportedTIFF(
                "mixed strips and tiles"
            )

        if tiled:
            offsets = values(324)
            lengths = values(325)
        elif stripped:
            offsets = values(273)
            lengths = values(279)
        else:
            raise UnsupportedTIFF(
                "IFD has no strip/tile data"
            )

        if len(offsets) != len(lengths):
            raise UnsupportedTIFF(
                "strip/tile count mismatch"
            )

        blocks = []

        for start, length in zip(offsets, lengths):
            if not length or start + length > len(data):
                raise UnsupportedTIFF(
                    "invalid compressed payload bounds"
                )

            blocks.append(data[start:start + length])

        images.append(tuple(blocks))

        offset = u32(entries + count * 12)

    if not images:
        raise UnsupportedTIFF("no TIFF image directories")

    return tuple(images)


class TIFFEncodedPreservationTests(unittest.TestCase):

    def setUp(self):
        self.magick = shutil.which("magick")
        self.exiftool = shutil.which("exiftool")

        if not self.magick or not self.exiftool:
            self.skipTest("ImageMagick and ExifTool required")

        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.w.env["KIM_TIFF_VERIFY"] = "native"
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()

        pixels = self.w.ppm("input/encoded-source.ppm")
        self.source = self.w.path("input/encoded.tiff")

        subprocess.run(
            [
                self.magick, str(pixels),
                "-compress", "LZW",
                str(self.source),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        subprocess.run(
            [
                self.exiftool,
                "-overwrite_original",
                "-GPSLatitude=42.5",
                "-GPSLatitudeRef=N",
                "-GPSLongitude=71.25",
                "-GPSLongitudeRef=W",
                "-Artist=Photographer",
                "-Copyright=All rights reserved",
                str(self.source),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        self.original_blocks = encoded_payloads(
            self.source
        )

    def strip(self, mode):
        self.w.env["KIM_POLICY"] = "create"

        return self.w.dispatch(
            "stripmeta", "--mode", mode,
            "--", self.source,
        )

    def derived(self):
        paths = [
            path
            for path in self.source.parent.glob("*.tiff")
            if path != self.source
        ]
        self.assertEqual(len(paths), 1)
        return paths[0]

    def test_full_strip_preserves_compressed_blocks(self):
        original = self.w.observe(self.source)

        result = self.strip("all")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        self.assertEqual(
            encoded_payloads(self.derived()),
            self.original_blocks,
        )
        self.assertEqual(
            self.w.observe(self.source),
            original,
        )

    def test_gps_strip_preserves_compressed_blocks(self):
        original = self.w.observe(self.source)

        result = self.strip("gps")

        self.assertEqual(
            result.returncode, 0,
            (result.stderr, result.events),
        )

        self.assertEqual(
            encoded_payloads(self.derived()),
            self.original_blocks,
        )
        self.assertEqual(
            self.w.observe(self.source),
            original,
        )

    def test_detects_compressed_payload_corruption(self):
        original = self.original_blocks

        raw = bytearray(self.source.read_bytes())
        first = original[0][0]

        self.assertTrue(first)

        # Locate the actual compressed payload, not the IFD.
        position = raw.find(first)
        self.assertGreaterEqual(position, 0)

        raw[position] ^= 0x01

        altered = self.w.path(
            "input/altered.tiff"
        )
        altered.write_bytes(raw)

        self.assertNotEqual(
            encoded_payloads(altered),
            original,
        )

    def test_rejects_truncated_directory(self):
        altered = self.w.path(
            "input/truncated.tiff"
        )

        altered.write_bytes(
            self.source.read_bytes()[:9]
        )

        with self.assertRaises(UnsupportedTIFF):
            encoded_payloads(altered)

    def test_rejects_circular_ifd(self):
        # Minimal little-endian classic TIFF with zero
        # directory entries and a self-referential next IFD.
        altered = self.w.path(
            "input/circular.tiff"
        )

        altered.write_bytes(
            b"II*\x00"
            + struct.pack("<I", 8)
            + struct.pack("<H", 0)
            + struct.pack("<I", 8)
        )

        with self.assertRaises(UnsupportedTIFF):
            encoded_payloads(altered)


if __name__ == "__main__":
    unittest.main()
