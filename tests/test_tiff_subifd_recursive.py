"""Nested TIFF SubIFD compressed-data verification tests."""

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
    "tiff_subifd", ENGINE
)
tiff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiff)


def nested(
    *,
    endian="<",
    child=b"preview",
    parent=b"original",
    grandchild=None,
    cycle=False,
    duplicate=False,
    null=False,
    pointer_type=4,
):
    data = bytearray(1024)
    data[0:2] = b"II" if endian == "<" else b"MM"

    def u16(pos, value):
        struct.pack_into(endian + "H", data, pos, value)

    def u32(pos, value):
        struct.pack_into(endian + "I", data, pos, value)

    u16(2, 42)
    u32(4, 8)

    def directory(pos, payload_pos, payload, pointers=None):
        tags = [
            (273, 4, 1, payload_pos),
            (279, 4, 1, len(payload)),
        ]

        if pointers is not None:
            if len(pointers) == 1:
                tags.append((
                    330, pointer_type, 1, pointers[0]
                ))
            else:
                pos_array = 700

                for index, target in enumerate(pointers):
                    u32(pos_array + 4 * index, target)

                tags.append((
                    330, pointer_type,
                    len(pointers), pos_array
                ))

        u16(pos, len(tags))

        for index, (tag, typ, count, value) in enumerate(tags):
            entry = pos + 2 + 12 * index
            u16(entry, tag)
            u16(entry + 2, typ)
            u32(entry + 4, count)
            u32(entry + 8, value)

        u32(pos + 2 + 12 * len(tags), 0)
        data[payload_pos:payload_pos + len(payload)] = payload

    targets = [80, 160] if duplicate else [80]

    if null:
        targets = [0]

    if cycle:
        targets = [8]

    directory(8, 400, parent, targets)

    if not cycle and not null:
        directory(
            80, 500, child,
            [160] if grandchild is not None else None,
        )

        if grandchild is not None:
            directory(160, 600, grandchild)

        if duplicate:
            directory(160, 500, child)

    return bytes(data)


class SubIFDTests(unittest.TestCase):

    def inspect(self, payload):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "image.tif"
            path.write_bytes(payload)
            return tiff.encoded_payloads(path)

    def test_one_child(self):
        self.assertEqual(
            self.inspect(nested()),
            (
                (
                    (b"original",),
                    ("SubIFDs", ((b"preview",),)),
                ),
            ),
        )

    def test_nested_grandchild(self):
        result = self.inspect(
            nested(grandchild=b"thumbnail")
        )
        self.assertIn(
            b"thumbnail",
            repr(result).encode(),
        )

    def test_big_endian(self):
        self.assertEqual(
            self.inspect(nested(endian=">")),
            self.inspect(nested()),
        )

    def test_child_payload_change_detected(self):
        self.assertNotEqual(
            self.inspect(nested()),
            self.inspect(nested(child=b"changed")),
        )

    def test_grandchild_payload_change_detected(self):
        self.assertNotEqual(
            self.inspect(nested(grandchild=b"A")),
            self.inspect(nested(grandchild=b"B")),
        )

    def test_cycle_refused(self):
        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(nested(cycle=True))

    def test_null_pointer_refused(self):
        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(nested(null=True))

    def test_duplicate_reference_refused(self):
        data = bytearray(nested(duplicate=True))
        struct.pack_into("<I", data, 704, 80)

        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(bytes(data))

    def test_wrong_pointer_type_refused(self):
        with self.assertRaises(tiff.UnsupportedTIFF):
            self.inspect(nested(pointer_type=3))

    def test_topology_difference_detected(self):
        self.assertNotEqual(
            self.inspect(nested()),
            self.inspect(nested(grandchild=b"thumbnail")),
        )


if __name__ == "__main__":
    unittest.main()
