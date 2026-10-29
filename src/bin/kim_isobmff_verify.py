#!/usr/bin/env python3
"""Conservative ISO-BMFF image payload preservation verifier.

For HEIC, HEIF and AVIF metadata edits, require identical encoded
media payloads and compatible file brands. Refuse unsupported or
ambiguous layouts. This is not an ISO-BMFF metadata sanitizer.
"""

import argparse
from pathlib import Path
import struct
import sys


class UnsafeBMFF(ValueError):
    pass


IMAGE_BRANDS = {
    b"mif1", b"msf1",
    b"heic", b"heix", b"hevc", b"hevx",
    b"heim", b"heis", b"hevm", b"hevs",
    b"avif", b"avis",
}

HEIF_BRANDS = {
    b"mif1", b"msf1",
    b"heic", b"heix", b"hevc", b"hevx",
    b"heim", b"heis", b"hevm", b"hevs",
}

AVIF_BRANDS = {b"avif", b"avis"}

# Structural boxes that would require additional parsing to
# establish preservation of fragmented or externally sourced data.
UNSUPPORTED = {
    b"moof", b"traf", b"mfra",
    b"sidx", b"ssix", b"iloc",
    b"dref", b"ipro",
}

# Do not recurse into arbitrary boxes: a byte pattern that resembles
# a box header inside a metadata value is not a child box.
CONTAINERS = {b"meta", b"iprp", b"ipco"}

MAX_BOXES = 100000
MAX_DEPTH = 12
MAX_FILE_SIZE = 8 * 1024 * 1024 * 1024


def read_box_header(data, position, limit):
    if position + 8 > limit:
        raise UnsafeBMFF("truncated box header")

    size = struct.unpack_from(">I", data, position)[0]
    kind = data[position + 4:position + 8]
    header = 8

    if size == 1:
        if position + 16 > limit:
            raise UnsafeBMFF("truncated 64-bit box header")
        size = struct.unpack_from(">Q", data, position + 8)[0]
        header = 16

    elif size == 0:
        size = limit - position

    if size < header or position + size > limit:
        raise UnsafeBMFF("invalid box boundary")

    return kind, position + header, position + size



# Item types whose data contributes to image appearance or decoding.
# Unrecognized item types with data are refused, not presumed metadata.
IMAGE_ITEM_TYPES = {
    b"av01", b"hvc1", b"hev1",
    b"grid", b"iovl", b"iden",
    b"jpeg", b"unci",
}

METADATA_ITEM_TYPES = {
    b"Exif", b"mime", b"uri ",
}


def inspect(data, requested_format):
    """Return a conservative image-integrity signature.

    For ordinary files without item locations, retain the earlier
    whole-media comparison. For item-addressed HEIF, resolve every
    item extent and compare encoded image items independently of
    editable Exif/XMP metadata items.
    """
    if len(data) < 24:
        raise UnsafeBMFF("truncated image container")

    if len(data) > MAX_FILE_SIZE:
        raise UnsafeBMFF("container exceeds safety limit")

    brands = None
    media = []
    idat_ranges = []
    iloc_range = None
    iinf_range = None
    image_properties = []
    structural_refs = []
    box_count = 0
    seen_meta = False
    seen_ftyp = False

    def walk(start, limit, depth, path=()):
        nonlocal brands, box_count, seen_meta, seen_ftyp
        nonlocal iloc_range, iinf_range

        if depth > MAX_DEPTH:
            raise UnsafeBMFF("box nesting limit exceeded")

        position = start

        while position < limit:
            kind, body, end = read_box_header(
                data, position, limit
            )

            box_count += 1
            if box_count > MAX_BOXES:
                raise UnsafeBMFF("too many container boxes")

            if kind in UNSUPPORTED - {b"iloc"}:
                raise UnsafeBMFF(
                    "unsupported image box "
                    + kind.decode("ascii", "replace")
                )

            if kind == b"ftyp":
                if depth or seen_ftyp or position != 0:
                    raise UnsafeBMFF(
                        "duplicate, misplaced or nested ftyp"
                    )

                if end - body < 8 or (end - body) % 4:
                    raise UnsafeBMFF("invalid ftyp payload")

                major = data[body:body + 4]
                compatible = {
                    data[i:i + 4]
                    for i in range(body + 8, end, 4)
                }
                compatible.add(major)

                if not compatible & IMAGE_BRANDS:
                    raise UnsafeBMFF(
                        "not a supported HEIF/AVIF image"
                    )

                brands = frozenset(compatible)
                seen_ftyp = True

            elif kind == b"mdat":
                media.append(
                    (kind, body, end, path)
                )

            elif kind == b"idat":
                if b"meta" not in path:
                    raise UnsafeBMFF(
                        "idat outside metadata container"
                    )
                if idat_ranges:
                    raise UnsafeBMFF(
                        "multiple idat boxes unsupported"
                    )
                idat_ranges.append((body, end))
                media.append(
                    (kind, body, end, path)
                )

            elif kind == b"meta":
                if depth or seen_meta:
                    raise UnsafeBMFF(
                        "duplicate or nested metadata box"
                    )
                seen_meta = True

                if body + 4 > end or data[body] != 0:
                    raise UnsafeBMFF(
                        "unsupported meta FullBox"
                    )

                walk(body + 4, end, depth + 1,
                     path + (kind,))

            elif kind == b"iloc":
                if b"meta" not in path or iloc_range:
                    raise UnsafeBMFF(
                        "misplaced or duplicate iloc"
                    )
                iloc_range = (body, end)

            elif kind == b"iinf":
                if b"meta" not in path or iinf_range:
                    raise UnsafeBMFF(
                        "misplaced or duplicate iinf"
                    )
                iinf_range = (body, end)

            elif kind == b"iprp":
                image_properties.append(
                    data[position:end]
                )
                walk(body, end, depth + 1,
                     path + (kind,))

            elif kind in (b"iref", b"pitm"):
                structural_refs.append(
                    (kind, data[position:end])
                )

            elif kind in CONTAINERS:
                walk(body, end, depth + 1,
                     path + (kind,))

            elif kind in (b"moov", b"trak", b"mdia"):
                raise UnsafeBMFF(
                    "unsupported movie/track structure"
                )

            position = end

        if position != limit:
            raise UnsafeBMFF("incomplete box traversal")

    walk(0, len(data), 0)

    if not seen_ftyp or brands is None:
        raise UnsafeBMFF("missing file type box")

    if not seen_meta:
        raise UnsafeBMFF("missing metadata box")

    if requested_format == "avif":
        if not brands & AVIF_BRANDS:
            raise UnsafeBMFF("AVIF brand missing")
    else:
        if not brands & HEIF_BRANDS:
            raise UnsafeBMFF("HEIF brand missing")

    if not media:
        raise UnsafeBMFF("no encoded media payload found")

    # Preserve backwards compatibility for non-item-addressed
    # layouts already supported and tested.
    if iloc_range is None:
        if iinf_range is not None:
            raise UnsafeBMFF(
                "item descriptions without item locations"
            )
        return (
            brands,
            tuple(
                (kind, path, data[body:end])
                for kind, body, end, path in media
            ),
        )

    if iinf_range is None:
        raise UnsafeBMFF(
            "item locations without item descriptions"
        )

    def unsigned(position, width, limit):
        if width == 0:
            return 0, position
        if width > 8 or position + width > limit:
            raise UnsafeBMFF("truncated item location field")
        return int.from_bytes(
            data[position:position + width], "big"
        ), position + width

    def item_descriptions():
        start, end = iinf_range
        if start + 6 > end:
            raise UnsafeBMFF("truncated iinf")

        version = data[start]
        if version not in (0, 1):
            raise UnsafeBMFF("unsupported iinf version")

        pos = start + 4
        count_width = 2 if version == 0 else 4
        count, pos = unsigned(pos, count_width, end)

        if count > MAX_BOXES:
            raise UnsafeBMFF("excessive item definitions")

        definitions = {}

        for _ in range(count):
            kind, body, box_end = read_box_header(
                data, pos, end
            )

            if kind != b"infe" or body + 8 > box_end:
                raise UnsafeBMFF(
                    "unsupported item definition"
                )

            v = data[body]
            if v not in (2, 3):
                raise UnsafeBMFF(
                    "unsupported infe version"
                )

            id_width = 2 if v == 2 else 4
            item_id, cursor = unsigned(
                body + 4, id_width, box_end
            )

            _, cursor = unsigned(
                cursor, 2, box_end
            )

            if cursor + 4 > box_end or item_id in definitions:
                raise UnsafeBMFF(
                    "invalid or duplicate item definition"
                )

            item_type = data[cursor:cursor + 4]

            if item_type not in (
                IMAGE_ITEM_TYPES | METADATA_ITEM_TYPES
            ):
                raise UnsafeBMFF(
                    "unknown item type requires review"
                )

            definitions[item_id] = item_type
            pos = box_end

        if pos != end:
            raise UnsafeBMFF(
                "unexpected trailing iinf data"
            )

        return definitions

    def locations():
        start, end = iloc_range
        if start + 8 > end:
            raise UnsafeBMFF("truncated iloc")

        version = data[start]
        if version not in (0, 1, 2):
            raise UnsafeBMFF("unsupported iloc version")

        sizes = data[start + 4]
        sizes2 = data[start + 5]

        offset_size = sizes >> 4
        length_size = sizes & 15
        base_size = sizes2 >> 4
        index_size = sizes2 & 15 if version else 0

        if any(
            width not in (0, 1, 2, 4, 8)
            for width in (
                offset_size, length_size,
                base_size, index_size,
            )
        ):
            raise UnsafeBMFF(
                "unsupported iloc integer width"
            )

        pos = start + 6
        count_width = 4 if version == 2 else 2
        count, pos = unsigned(pos, count_width, end)

        if count > MAX_BOXES:
            raise UnsafeBMFF("excessive item locations")

        result = {}

        for _ in range(count):
            id_width = 4 if version == 2 else 2
            item_id, pos = unsigned(
                pos, id_width, end
            )

            method = 0

            if version in (1, 2):
                method_flags, pos = unsigned(
                    pos, 2, end
                )
                if method_flags & 0xFFF0:
                    raise UnsafeBMFF(
                        "invalid construction flags"
                    )
                method = method_flags & 15

            data_reference, pos = unsigned(
                pos, 2, end
            )

            if data_reference != 0:
                raise UnsafeBMFF(
                    "external item data reference"
                )

            if method not in (0, 1):
                raise UnsafeBMFF(
                    "unsupported construction method"
                )

            base, pos = unsigned(
                pos, base_size, end
            )
            number, pos = unsigned(pos, 2, end)

            if item_id in result or number == 0:
                raise UnsafeBMFF(
                    "duplicate or empty item location"
                )

            if number > MAX_BOXES:
                raise UnsafeBMFF(
                    "excessive item extents"
                )

            extents = []

            for _ in range(number):
                if index_size:
                    extent_index, pos = unsigned(
                        pos, index_size, end
                    )
                    if extent_index:
                        raise UnsafeBMFF(
                            "indexed item extents unsupported"
                        )

                offset, pos = unsigned(
                    pos, offset_size, end
                )
                length, pos = unsigned(
                    pos, length_size, end
                )

                if length == 0:
                    raise UnsafeBMFF(
                        "zero-length item extent"
                    )

                extent_start = base + offset

                if method == 1:
                    if len(idat_ranges) != 1:
                        raise UnsafeBMFF(
                            "idat construction without idat"
                        )
                    extent_start += idat_ranges[0][0]

                extent_end = extent_start + length

                valid_ranges = (
                    [(a, b) for kind, a, b, _ in media
                     if kind == b"mdat"]
                    if method == 0
                    else idat_ranges
                )

                if not any(
                    extent_start >= a and extent_end <= b
                    for a, b in valid_ranges
                ):
                    raise UnsafeBMFF(
                        "item extent outside protected media"
                    )

                extents.append(
                    data[extent_start:extent_end]
                )

            result[item_id] = tuple(extents)

        if pos != end:
            raise UnsafeBMFF(
                "unexpected trailing iloc data"
            )

        return result

    definitions = item_descriptions()
    extents = locations()

    if set(extents) != set(definitions):
        raise UnsafeBMFF(
            "item definitions and locations disagree"
        )

    image_items = tuple(sorted(
        (
            item_id,
            definitions[item_id],
            extents[item_id],
        )
        for item_id in definitions
        if definitions[item_id] in IMAGE_ITEM_TYPES
    ))

    if not image_items:
        raise UnsafeBMFF(
            "no verifiable encoded image items"
        )

    return (
        brands,
        image_items,
        tuple(image_properties),
        tuple(structural_refs),
    )


def verify(before, after, format_name):
    original = inspect(before, format_name)
    candidate = inspect(after, format_name)

    if original != candidate:
        raise UnsafeBMFF(
            "brands, encoded media, or payload topology changed"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format", choices=("heif", "avif"),
        required=True,
    )
    parser.add_argument(
        "--before", type=Path, required=True
    )
    parser.add_argument(
        "--after", type=Path, required=True
    )
    args = parser.parse_args()

    try:
        verify(
            args.before.read_bytes(),
            args.after.read_bytes(),
            args.format,
        )
        return 0

    except (OSError, UnsafeBMFF) as exc:
        print(
            f"KIM6 ISO-BMFF verification refused: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
