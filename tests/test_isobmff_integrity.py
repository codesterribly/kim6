"""Conservative HEIF/AVIF ISO-BMFF integrity verification."""

import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ENGINE = (
    Path(__file__).resolve().parents[1]
    / "src/bin/kim_isobmff_verify.py"
)

spec = importlib.util.spec_from_file_location(
    "kim_bmff_runtime", ENGINE
)
bmff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bmff)


def box(name, data):
    return (
        struct.pack(">I", len(data) + 8)
        + name + data
    )


def sample(
    *,
    brand=b"avif",
    encoded=b"encoded pixels",
    description=b"caption",
    embedded=False,
):
    ftyp = box(
        b"ftyp",
        brand + b"\x00\x00\x00\x00" + brand,
    )

    children = box(b"hdlr", b"image metadata")

    if embedded:
        children += box(b"idat", encoded)

    children += box(b"uuid", description)

    meta = box(
        b"meta",
        bytes(4) + children,
    )

    if embedded:
        return ftyp + meta

    return ftyp + meta + box(b"mdat", encoded)


class BMFFIntegrityTests(unittest.TestCase):

    def verify_cli(self, before, after, fmt="avif"):
        with tempfile.TemporaryDirectory() as root:
            original = Path(root) / "before.avif"
            candidate = Path(root) / "after.avif"
            original.write_bytes(before)
            candidate.write_bytes(after)

            return subprocess.run(
                [
                    sys.executable, "-B", str(ENGINE),
                    "--format", fmt,
                    "--before", str(original),
                    "--after", str(candidate),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

    def test_metadata_change_accepted(self):
        before = sample(description=b"old")
        after = sample(description=b"new")
        bmff.verify(before, after, "avif")

    def test_mdat_change_rejected(self):
        before = sample()
        after = sample(encoded=b"changed pixels")
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.verify(before, after, "avif")

    def test_idat_change_rejected(self):
        before = sample(embedded=True)
        after = sample(
            embedded=True, encoded=b"changed"
        )
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.verify(before, after, "avif")

    def test_idat_metadata_change_accepted(self):
        bmff.verify(
            sample(embedded=True, description=b"A"),
            sample(embedded=True, description=b"B"),
            "avif",
        )

    def test_heif_brand(self):
        bmff.verify(
            sample(brand=b"heic"),
            sample(brand=b"heic"),
            "heif",
        )

    def test_brand_change_rejected(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.verify(
                sample(brand=b"avif"),
                sample(brand=b"avis"),
                "avif",
            )

    def test_wrong_format_rejected(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(sample(brand=b"avif"), "heif")

    def test_truncated_box_rejected(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(sample()[:-3], "avif")

    def test_missing_media_rejected(self):
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(
                sample()[:-len(box(b"mdat", b"encoded pixels"))],
                "avif",
            )

    def test_fragmented_container_rejected(self):
        data = sample() + box(b"moof", bytes(8))
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(data, "avif")

    def test_unsupported_item_locations_rejected(self):
        data = (
            box(
                b"ftyp",
                b"avif" + bytes(4) + b"avif",
            )
            + box(
                b"meta",
                bytes(4)
                + box(b"iloc", bytes(8))
                + box(b"idat", b"pixels"),
            )
        )
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(data, "avif")

    def test_duplicate_ftyp_rejected(self):
        data = sample()
        data += box(
            b"ftyp",
            b"avif" + bytes(4) + b"avif",
        )
        with self.assertRaises(bmff.UnsafeBMFF):
            bmff.inspect(data, "avif")

    def test_cli_success(self):
        result = self.verify_cli(
            sample(description=b"old"),
            sample(description=b"new"),
        )
        self.assertEqual(
            result.returncode, 0,
            result.stderr,
        )

    def test_cli_corruption_failure(self):
        result = self.verify_cli(
            sample(),
            sample(encoded=b"corrupted"),
        )
        self.assertNotEqual(result.returncode, 0)

    def test_identical_invalid_files_rejected(self):
        result = self.verify_cli(b"invalid", b"invalid")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
