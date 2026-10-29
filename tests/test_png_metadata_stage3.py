"""Selective PNG metadata reconstruction regression tests."""

import binascii
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src/bin/kim_png_metadata.py"

spec = importlib.util.spec_from_file_location(
    "kim_png_stage3",
    ENGINE,
)
png = importlib.util.module_from_spec(spec)
spec.loader.exec_module(png)


def chunk(tag, payload):
    return (
        struct.pack(">I", len(payload))
        + tag + payload
        + struct.pack(
            ">I",
            binascii.crc32(tag + payload) & 0xffffffff,
        )
    )


def fixture(*items):
    return (
        png.SIG
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0),
        )
        + b"".join(items)
        + chunk(
            b"IDAT",
            zlib.compress(b"\x00\xff\x00\x00"),
        )
        + chunk(b"IEND", b"")
    )


class PNGSelectiveTests(unittest.TestCase):

    def test_ai_removes_workflow_preserving_rights(self):
        source = fixture(
            chunk(
                b"zTXt",
                b"workflow\x00\x00"
                + zlib.compress(b'{"class_type":"KSampler"}'),
            ),
            chunk(b"tEXt", b"Copyright\x00Photographer"),
        )

        result, changes = png.filter_png(source, "ai")

        self.assertEqual(changes, 1)
        self.assertNotIn(b"workflow", result)
        self.assertIn(b"Photographer", result)

    def test_gps_preserves_ai_workflow(self):
        source = fixture(
            chunk(b"tEXt", b"GPSLatitude\x0042"),
            chunk(b"tEXt", b"workflow\x00Private"),
        )

        result, changes = png.filter_png(source, "gps")

        self.assertEqual(changes, 1)
        self.assertNotIn(b"GPSLatitude", result)
        self.assertIn(b"workflow", result)

    def test_gps_and_ai_combined(self):
        source = fixture(
            chunk(b"tEXt", b"GPSLatitude\x0042"),
            chunk(b"tEXt", b"workflow\x00Private"),
            chunk(b"tEXt", b"Copyright\x00Rights"),
        )

        result, changes = png.filter_png(
            source, "gps", True
        )

        self.assertEqual(changes, 2)
        self.assertNotIn(b"GPSLatitude", result)
        self.assertNotIn(b"workflow", result)
        self.assertIn(b"Rights", result)

    def test_ai_xmp_preserves_non_ai_source(self):
        xml = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            b'xmlns:iptc="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">'
            b'<rdf:RDF><rdf:Description '
            b'iptc:DigitalSourceType="negativeFilm" '
            b'iptc:AIPromptInformation="PrivatePrompt"/>'
            b'</rdf:RDF></x:xmpmeta>'
        )

        source = fixture(
            chunk(
                b"iTXt",
                b"XML:com.adobe.xmp\x00\x00\x00\x00\x00"
                + xml,
            )
        )

        result, changes = png.filter_png(source, "ai")

        self.assertEqual(changes, 1)
        self.assertIn(b"negativeFilm", result)
        self.assertNotIn(b"PrivatePrompt", result)

    def test_ai_xmp_removes_ai_source(self):
        xml = (
            b'<x:xmpmeta xmlns:x="adobe:ns:meta/" '
            b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            b'xmlns:iptc="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">'
            b'<rdf:RDF><rdf:Description '
            b'iptc:DigitalSourceType="trainedAlgorithmicMedia" '
            b'iptc:AIPromptInformation="PrivatePrompt"/>'
            b'</rdf:RDF></x:xmpmeta>'
        )

        source = fixture(
            chunk(
                b"iTXt",
                b"XML:com.adobe.xmp\x00\x00\x00\x00\x00"
                + xml,
            )
        )

        result, changes = png.filter_png(source, "ai")

        self.assertEqual(changes, 1)
        self.assertNotIn(b"trainedAlgorithmicMedia", result)
        self.assertNotIn(b"PrivatePrompt", result)

    def test_selective_exif_refused(self):
        source = fixture(
            chunk(b"eXIf", b"unsupported")
        )

        for mode in ("ai", "gps"):
            with self.subTest(mode=mode):
                with self.assertRaises(png.UnsafePNG):
                    png.filter_png(source, mode)


if __name__ == "__main__":
    unittest.main()
