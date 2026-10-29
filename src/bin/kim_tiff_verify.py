#!/usr/bin/env python3
"""Fail-closed TIFF compressed-strip/tile preservation verifier."""

import argparse
from pathlib import Path
import struct
import sys

class UnsupportedTIFF(ValueError):
    pass

def encoded_payloads(path):
    """Compare Classic TIFF/BigTIFF strips, tiles and SubIFD tree contents.

    Metadata offsets may change during edits. Encoded image payloads
    and their directory hierarchy must remain identical.
    """
    data = Path(path).read_bytes()
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise UnsupportedTIFF("invalid TIFF byte order or header")

    endian = "<" if data[:2] == b"II" else ">"

    def number(pos, width):
        if pos < 0 or pos + width > len(data):
            raise UnsupportedTIFF("out-of-bounds TIFF field")
        return struct.unpack_from(
            endian + {2: "H", 4: "I", 8: "Q"}[width],
            data, pos
        )[0]

    magic = number(2, 2)

    if magic == 42:
        offset_width = 4
        count_width = 2
        entry_width = 12
        first_offset_pos = 4
    elif magic == 43:
        if (
            len(data) < 16
            or number(4, 2) != 8
            or number(6, 2) != 0
        ):
            raise UnsupportedTIFF(
                "invalid BigTIFF offset-size header"
            )
        offset_width = 8
        count_width = 8
        entry_width = 20
        first_offset_pos = 8
    else:
        raise UnsupportedTIFF("unsupported TIFF magic")

    visited = set()
    MAX_DIRECTORIES = 1024
    MAX_DEPTH = 16
    MAX_ENTRIES = 100000

    def chain(offset, depth):
        if depth > MAX_DEPTH:
            raise UnsupportedTIFF(
                "SubIFD nesting limit exceeded"
            )

        results = []

        while offset:
            if offset in visited:
                raise UnsupportedTIFF(
                    "circular or shared TIFF IFD reference"
                )

            if len(visited) >= MAX_DIRECTORIES:
                raise UnsupportedTIFF(
                    "too many TIFF directories"
                )

            visited.add(offset)

            count = number(offset, count_width)

            if count > MAX_ENTRIES:
                raise UnsupportedTIFF(
                    "excessive TIFF entry count"
                )

            entries = offset + count_width
            next_pos = entries + count * entry_width

            if next_pos + offset_width > len(data):
                raise UnsupportedTIFF(
                    "truncated TIFF directory"
                )

            tags = {}

            for index in range(count):
                pos = entries + index * entry_width
                tag = number(pos, 2)

                if tag in tags:
                    raise UnsupportedTIFF(
                        "duplicate TIFF tag"
                    )

                typ = number(pos + 2, 2)
                elements = number(
                    pos + 4, offset_width
                )
                inline = pos + 4 + offset_width

                tags[tag] = (
                    typ,
                    elements,
                    number(inline, offset_width),
                    inline,
                )

            def values(tag):
                if tag not in tags:
                    raise UnsupportedTIFF(
                        "missing TIFF tag " + str(tag)
                    )

                typ, elements, address, inline = tags[tag]

                types = {
                    3: (2, "H"),
                    4: (4, "I"),
                    13: (4, "I"),
                    16: (8, "Q"),
                    18: (8, "Q"),
                }

                if typ not in types:
                    raise UnsupportedTIFF(
                        "unsupported TIFF pointer type"
                    )

                if typ in (13, 18) and tag != 330:
                    raise UnsupportedTIFF(
                        "unexpected IFD pointer type"
                    )

                if not elements or elements > MAX_ENTRIES:
                    raise UnsupportedTIFF(
                        "invalid TIFF element count"
                    )

                width, fmt = types[typ]
                size = elements * width
                position = (
                    inline if size <= offset_width
                    else address
                )

                if (
                    position < 0
                    or position + size > len(data)
                ):
                    raise UnsupportedTIFF(
                        "TIFF value outside file"
                    )

                return struct.unpack_from(
                    endian + str(elements) + fmt,
                    data,
                    position,
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
                    "IFD lacks encoded strips or tiles"
                )

            if len(offsets) != len(lengths):
                raise UnsupportedTIFF(
                    "image block counts disagree"
                )

            blocks = []

            for begin, length in zip(offsets, lengths):
                if (
                    not begin
                    or not length
                    or begin + length > len(data)
                ):
                    raise UnsupportedTIFF(
                        "invalid compressed image extent"
                    )

                blocks.append(
                    data[begin:begin + length]
                )

            if 330 in tags:
                if tags[330][0] not in (4, 13, 16, 18):
                    raise UnsupportedTIFF(
                        "invalid SubIFD pointer type"
                    )

                pointers = values(330)

                if not all(pointers):
                    raise UnsupportedTIFF(
                        "null TIFF SubIFD pointer"
                    )

                children = []

                for pointer in pointers:
                    nested = chain(pointer, depth + 1)

                    if len(nested) != 1:
                        raise UnsupportedTIFF(
                            "chained SubIFD siblings"
                        )

                    children.append(nested[0])

                results.append((
                    tuple(blocks),
                    ("SubIFDs", tuple(children)),
                ))
            else:
                results.append(tuple(blocks))

            offset = number(
                next_pos, offset_width
            )

        return tuple(results)

    images = chain(number(first_offset_pos, offset_width), 0)

    if not images:
        raise UnsupportedTIFF(
            "no TIFF image directories"
        )

    return images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    args = parser.parse_args()

    try:
        original = encoded_payloads(args.before)
        candidate = encoded_payloads(args.after)

        if original != candidate:
            raise UnsupportedTIFF(
                "compressed TIFF image data changed"
            )

        return 0

    except (OSError, ValueError, struct.error) as exc:
        print(
            f"KIM6 TIFF verification refused: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
