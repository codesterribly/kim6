"""APNG control must be a PNG chunk type, not incidental metadata bytes."""

import struct
import unittest
import zlib

from support import Workspace


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    )


def insert_after_ihdr(path, *chunks):
    image = path.read_bytes()
    if (
        not image.startswith(b"\x89PNG\r\n\x1a\n")
        or image[12:16] != b"IHDR"
    ):
        raise ValueError("not a PNG fixture with IHDR first")

    end = 8 + 12 + int.from_bytes(image[8:12], "big")
    path.write_bytes(image[:end] + b"".join(chunks) + image[end:])


class ApngChunkDetectionTests(unittest.TestCase):

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.png("input/still.png")

    def probe(self, command):
        return self.w.shared_progress(command, self.source)

    def test_png_text_value_containing_acTL_is_not_animation(self):
        insert_after_ihdr(
            self.source,
            png_chunk(
                b"tEXt",
                b"Description\x00not an animation; acTL is in metadata",
            ),
        )

        result = self.probe(
            'if image_has_apng_control_chunk "$1"; '
            'then echo animated; else echo still; fi'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "still")

    def test_real_chunk_type_is_found_after_text_with_same_marker(self):
        insert_after_ihdr(
            self.source,
            png_chunk(
                b"tEXt",
                b"Comment\x00acTL appears before the true chunk",
            ),
            png_chunk(b"acTL", struct.pack(">II", 2, 3)),
        )

        result = self.probe('image_apng_play_count "$1"')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3")

    def test_control_chunk_after_image_data_is_not_apng(self):
        image = self.source.read_bytes()
        iend = image.rfind(b"\x00\x00\x00\x00IEND")

        self.assertGreater(iend, 0)

        self.source.write_bytes(
            image[:iend]
            + png_chunk(b"acTL", struct.pack(">II", 2, 3))
            + image[iend:]
        )

        result = self.probe(
            'if image_has_apng_control_chunk "$1"; '
            'then echo animated; else echo still; fi'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "still")


    def test_actl_after_large_metadata_chunk_is_detected(self):
        # A valid ancillary PNG chunk may exceed one megabyte.
        insert_after_ihdr(
            self.source,
            png_chunk(b"tEXt", b"Comment\\x00" + b"x" * 1_100_000),
            png_chunk(b"acTL", struct.pack(">II", 2, 3)),
        )

        result = self.probe('image_apng_control_offset "$1"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(int(result.stdout.strip()), 1_048_576)

        result = self.probe('image_apng_play_count "$1"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "3")

    def test_large_metadata_text_containing_actl_stays_still(self):
        insert_after_ihdr(
            self.source,
            png_chunk(
                b"tEXt",
                b"Comment\\x00" + b"x" * 1_100_000 + b"acTL",
            ),
        )

        result = self.probe(
            'if image_has_apng_control_chunk "$1"; '
            'then echo animated; else echo still; fi'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "still")


if __name__ == "__main__":
    unittest.main()
