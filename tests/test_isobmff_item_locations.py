"""Item-aware HEIF/AVIF integrity regressions."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_isobmff_verify.py"
)

spec = importlib.util.spec_from_file_location(
    "bmff_items", ENGINE
)
bmff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bmff)


def box(kind, body):
    return struct.pack(">I", len(body) + 8) + kind + body


def fullbox(kind, version, payload):
    return box(
        kind,
        bytes([version, 0, 0, 0]) + payload,
    )


def sample(
    *,
    image=b"ENCODED IMAGE",
    metadata=b"EXIF METADATA",
    brand=b"avif",
    external=False,
    method=0,
    corrupt_offset=False,
):
    ftyp = box(
        b"ftyp", brand + bytes(4) + brand
    )

    def infe(item_id, kind):
        body = (
            struct.pack(">HH", item_id, 0)
            + kind
            + b"item\\x00"
        )
        return fullbox(b"infe", 2, body)

    iinf = fullbox(
        b"iinf", 0,
        struct.pack(">H", 2)
        + infe(1, b"av01")
        + infe(2, b"Exif"),
    )

    media = image + metadata

    # Build iloc once to determine the absolute mdat offset.
    def iloc(media_offset):
        entries = bytearray()

        for item_id, start, length in (
            (1, 0, len(image)),
            (2, len(image), len(metadata)),
        ):
            entries += struct.pack(">H", item_id)
            entries += struct.pack(">H", method)
            entries += struct.pack(
                ">H", 1 if external else 0
            )
            entries += struct.pack(">I", 0)
            entries += struct.pack(">H", 1)
            entries += struct.pack(
                ">I",
                (
                    0xFFFFFF00
                    if corrupt_offset
                    else media_offset + start
                ),
            )
            entries += struct.pack(">I", length)

        return fullbox(
            b"iloc", 1,
            bytes([0x44, 0x40])
            + struct.pack(">H", 2)
            + entries,
        )

    provisional = box(
        b"meta",
        bytes(4) + iinf + iloc(0),
    )

    media_offset = len(ftyp) + len(provisional) + 8

    meta = box(
        b"meta",
        bytes(4) + iinf + iloc(media_offset),
    )

    return ftyp + meta + box(b"mdat", media)


class ItemLocationTests(unittest.TestCase):

    def test_same_image_modified_exif_accepted(self):
        bmff.verify(
            sample(metadata=b"old EXIF"),
            sample(metadata=b"new EXIF metadata"),
            "avif",
        )

    def test_encoded_image_change_refused(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.verify(
                sample(image=b"ORIGINAL"),
                sample(image=b"CORRUPTED"),
                "avif",
            )

    def test_external_reference_refused(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(
                sample(external=True), "avif"
            )

    def test_unknown_construction_refused(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(
                sample(method=2), "avif"
            )

    def test_out_of_bounds_extent_refused(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(
                sample(corrupt_offset=True), "avif"
            )

    def test_heic_brand_and_image(self):
        bmff.verify(
            sample(brand=b"heic"),
            sample(
                brand=b"heic",
                metadata=b"edited metadata",
            ),
            "heif",
        )

    def test_wrong_brand_refused(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(sample(), "heif")


if __name__ == "__main__":
    unittest.main()
