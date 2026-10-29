#!/usr/bin/env python3
"""Lossless JPEG/WebP full-metadata reconstruction.

Compressed image data is never decoded or re-encoded.
Unsupported or ambiguous structures are rejected.
"""

import argparse
import struct
import sys
from pathlib import Path


class UnsafeImage(ValueError):
    pass


def orientation_from_exif(data):
    if not data.startswith(b'Exif\x00\x00'):
        raise UnsafeImage('unrecognized EXIF')

    data = data[6:]

    if len(data) < 8 or data[:2] not in (b'II', b'MM'):
        raise UnsafeImage('invalid TIFF header')

    endian = '<' if data[:2] == b'II' else '>'

    if struct.unpack_from(endian + 'H', data, 2)[0] != 42:
        raise UnsafeImage('invalid TIFF marker')

    offset = struct.unpack_from(endian + 'I', data, 4)[0]

    if offset < 8 or offset + 2 > len(data):
        raise UnsafeImage('invalid EXIF IFD offset')

    count = struct.unpack_from(endian + 'H', data, offset)[0]

    if offset + 2 + count * 12 + 4 > len(data):
        raise UnsafeImage('truncated EXIF directory')

    orientation = None

    for index in range(count):
        pos = offset + 2 + index * 12
        tag, kind, number = struct.unpack_from(
            endian + 'HHI', data, pos
        )

        if tag != 274:
            continue

        if orientation is not None or kind != 3 or number != 1:
            raise UnsafeImage('ambiguous orientation')

        orientation = struct.unpack_from(
            endian + 'H', data, pos + 8
        )[0]

        if not 1 <= orientation <= 8:
            raise UnsafeImage('invalid orientation')

    return orientation


def orientation_only_exif(value):
    return (
        b'Exif\x00\x00'
        b'II*\x00\x08\x00\x00\x00\x01\x00'
        + struct.pack('<HHIH', 274, 3, 1, value)
        + b'\x00\x00\x00\x00\x00\x00'
    )


def validate_jpeg_scan(data, start):
    """Validate baseline entropy-coded scan boundaries.

    JPEG byte stuffing and restart markers are permitted. Files
    containing multiple scans or ambiguous trailing structures are
    refused rather than incompletely filtered.
    """
    pos = start

    while pos < len(data):
        if data[pos] != 0xff:
            pos += 1
            continue

        marker_start = pos

        while pos < len(data) and data[pos] == 0xff:
            pos += 1

        if pos >= len(data):
            raise UnsafeImage('truncated JPEG scan marker')

        marker = data[pos]
        pos += 1

        if marker == 0x00:
            continue

        if 0xd0 <= marker <= 0xd7:
            continue

        if marker == 0xd9:
            if pos != len(data):
                raise UnsafeImage('trailing bytes after JPEG EOI')
            return

        # A further SOS, DHT, APP, COM or other marker could be
        # valid in a multi-scan JPEG, but that structure needs a
        # complete segment-aware parser before metadata removal.
        raise UnsafeImage(
            'unsupported marker in JPEG scan at byte '
            + str(marker_start)
        )

    raise UnsafeImage('JPEG EOI missing')


def jpeg(data):
    if not data.startswith(b'\xff\xd8'):
        raise UnsafeImage('not JPEG')

    position = 2
    output = bytearray(data[:2])
    removed = 0
    found_scan = False
    seen_exif = False
    icc_segments = []

    while position < len(data):
        start = position

        if data[position] != 0xff:
            raise UnsafeImage('invalid JPEG marker')

        while (
            position < len(data)
            and data[position] == 0xff
        ):
            position += 1

        if position >= len(data):
            raise UnsafeImage('truncated JPEG marker')

        marker = data[position]
        position += 1

        if (
            marker in (0, 1, 0xd8, 0xd9)
            or 0xd0 <= marker <= 0xd7
        ):
            raise UnsafeImage('unsupported marker ordering')

        if position + 2 > len(data):
            raise UnsafeImage('truncated JPEG segment')

        length = struct.unpack_from(
            '>H', data, position
        )[0]

        end = position + length

        if length < 2 or end > len(data):
            raise UnsafeImage('invalid JPEG segment length')

        payload = data[position + 2:end]

        if marker == 0xda:
            # Preserve entropy-coded image data verbatim.
            # Require an EOI marker at the end of the stream.
            validate_jpeg_scan(data, end)

            output.extend(data[start:])
            found_scan = True
            break

        keep = True
        replacement = None

        if (
            marker == 0xe1
            and payload.startswith(b'Exif\x00\x00')
        ):
            if seen_exif:
                raise UnsafeImage('duplicate EXIF')

            seen_exif = True
            orientation = orientation_from_exif(payload)

            if orientation is None:
                keep = False
            else:
                replacement = orientation_only_exif(
                    orientation
                )

        elif (
            marker == 0xe2
            and payload.startswith(b'ICC_PROFILE\x00')
        ):
            if len(payload) < 14:
                raise UnsafeImage('invalid JPEG ICC segment')

            icc_segments.append(
                (payload[12], payload[13])
            )

        elif (
            marker == 0xe0
            and payload.startswith(
                (b'JFIF\x00', b'JFXX\x00')
            )
        ):
            pass

        elif (
            marker == 0xee
            and payload.startswith(b'Adobe')
        ):
            pass

        elif 0xe0 <= marker <= 0xef or marker == 0xfe:
            keep = False

        if keep:
            if replacement is None:
                output.extend(data[start:end])
            else:
                output.extend(data[start:position])
                output.extend(
                    struct.pack(
                        '>H', len(replacement) + 2
                    )
                )
                output.extend(replacement)

                if replacement != payload:
                    removed += 1
        else:
            removed += 1

        position = end

    if not found_scan:
        raise UnsafeImage('JPEG scan missing')

    if icc_segments:
        count = icc_segments[0][1]

        if (
            count == 0
            or len(icc_segments) != count
            or sorted(icc_segments) != [
                (i, count)
                for i in range(1, count + 1)
            ]
        ):
            raise UnsafeImage(
                'incomplete or duplicate JPEG ICC profile'
            )

    return bytes(output), removed


def validate_webp_features(chunks, flags):
    """Reject inconsistent VP8X metadata, ICC and animation flags."""

    kinds = [kind for kind, _, _ in chunks]

    if flags is None:
        if any(
            kind in kinds
            for kind in (b'ICCP', b'EXIF', b'XMP ', b'ANIM', b'ANMF')
        ):
            raise UnsafeImage('extended WebP features need VP8X')
        return

    features = (
        (b'ICCP', 0x20),
        (b'EXIF', 0x08),
        (b'XMP ', 0x04),
    )

    for kind, bit in features:
        present = kind in kinds
        advertised = bool(flags & bit)

        if present != advertised:
            raise UnsafeImage(
                'WebP VP8X feature flag disagrees with '
                + kind.decode('ascii')
            )

    animated = b'ANIM' in kinds or b'ANMF' in kinds

    if bool(flags & 0x02) != animated:
        raise UnsafeImage('WebP animation flag mismatch')

    if animated:
        if b'ANIM' not in kinds or b'ANMF' not in kinds:
            raise UnsafeImage('incomplete WebP animation')

        if kinds.index(b'ANIM') > kinds.index(b'ANMF'):
            raise UnsafeImage('WebP frame precedes animation header')


def webp(data):
    if (
        len(data) < 20
        or data[:4] != b'RIFF'
        or data[8:12] != b'WEBP'
    ):
        raise UnsafeImage('not WebP')

    declared = struct.unpack_from('<I', data, 4)[0]

    if declared + 8 != len(data) or declared % 2:
        raise UnsafeImage('invalid RIFF length')

    position = 12
    chunks = []
    seen = set()
    flags = None
    removed = 0

    while position < len(data):
        if position + 8 > len(data):
            raise UnsafeImage('truncated WebP chunk')

        kind = data[position:position + 4]
        length = struct.unpack_from(
            '<I', data, position + 4
        )[0]

        end = (
            position + 8 + length
            + (length & 1)
        )

        if end > len(data):
            raise UnsafeImage('invalid WebP chunk size')

        payload = data[
            position + 8:position + 8 + length
        ]

        if (
            kind in (
                b'VP8X', b'ICCP', b'EXIF',
                b'XMP ', b'ANIM',
            )
            and kind in seen
        ):
            raise UnsafeImage('duplicate WebP chunk')

        seen.add(kind)

        if kind == b'VP8X':
            if (
                position != 12
                or length != 10
                or flags is not None
            ):
                raise UnsafeImage('invalid VP8X')

            flags = payload[0]

        chunks.append(
            (kind, payload, data[position:end])
        )

        position = end

    if not (
        b'VP8 ' in seen
        or b'VP8L' in seen
        or b'ANMF' in seen
    ):
        raise UnsafeImage('WebP image payload missing')

    if (
        seen & {
            b'EXIF', b'XMP ',
            b'ICCP', b'ANMF',
        }
        and flags is None
    ):
        raise UnsafeImage('VP8X header required')

    validate_webp_features(chunks, flags)

    for kind, payload, _ in chunks:
        if kind == b'EXIF':
            orientation = orientation_from_exif(
                payload
            )

            if orientation not in (None, 1):
                raise UnsafeImage(
                    'WebP EXIF orientation cannot '
                    'be removed safely'
                )

    output = []

    for kind, payload, original in chunks:
        if kind in (b'EXIF', b'XMP '):
            removed += 1
            continue

        if kind == b'VP8X':
            # Clear only XMP and EXIF feature bits.
            updated = (
                bytes([payload[0] & ~0x0c])
                + payload[1:]
            )

            original = (
                kind
                + struct.pack('<I', len(updated))
                + updated
            )

            if updated != payload:
                removed += 1

        if kind in (
            b'VP8 ', b'VP8L', b'VP8X',
            b'ALPH', b'ICCP', b'ANIM',
            b'ANMF',
        ):
            output.append(original)
        else:
            removed += 1

    body = b'WEBP' + b''.join(output)

    return (
        b'RIFF'
        + struct.pack('<I', len(body))
        + body,
        removed,
    )



def selective_jpeg_core(data):
    """Extract byte-identical JPEG picture and color structures."""
    if not data.startswith(b'\xff\xd8'):
        raise UnsafeImage('not JPEG')

    pos = 2
    kept = []

    while pos < len(data):
        start = pos

        if data[pos] != 255:
            raise UnsafeImage('bad JPEG segment boundary')

        while pos < len(data) and data[pos] == 255:
            pos += 1

        if pos >= len(data):
            raise UnsafeImage('truncated JPEG marker')

        marker = data[pos]
        pos += 1

        if (
            marker in (0, 1, 0xd8, 0xd9)
            or 0xd0 <= marker <= 0xd7
        ):
            raise UnsafeImage('unsupported JPEG marker ordering')

        if pos + 2 > len(data):
            raise UnsafeImage('truncated JPEG length')

        length = struct.unpack_from('>H', data, pos)[0]
        end = pos + length

        if length < 2 or end > len(data):
            raise UnsafeImage('invalid JPEG length')

        if marker == 0xda:
            validate_jpeg_scan(data, end)
            kept.append(data[start:])
            return tuple(kept)

        payload = data[pos + 2:end]

        if (
            marker == 0xe2
            and payload.startswith(b'ICC_PROFILE\x00')
        ):
            kept.append(data[start:end])

        elif (
            marker == 0xe0
            and payload.startswith((b'JFIF\x00', b'JFXX\x00'))
        ):
            kept.append(data[start:end])

        elif marker == 0xee and payload.startswith(b'Adobe'):
            kept.append(data[start:end])

        elif not (0xe0 <= marker <= 0xef or marker == 0xfe):
            kept.append(data[start:end])

        pos = end

    raise UnsafeImage('JPEG scan missing')


def selective_webp_core(data):
    """Extract image, color and animation chunks without metadata."""
    if (
        len(data) < 20
        or data[:4] != b'RIFF'
        or data[8:12] != b'WEBP'
    ):
        raise UnsafeImage('not WebP')

    if struct.unpack_from('<I', data, 4)[0] + 8 != len(data):
        raise UnsafeImage('invalid RIFF length')

    pos = 12
    result = []
    chunks = []
    flags = None

    while pos < len(data):
        if pos + 8 > len(data):
            raise UnsafeImage('truncated WebP chunk')

        kind = data[pos:pos + 4]
        length = struct.unpack_from('<I', data, pos + 4)[0]
        end = pos + 8 + length + (length & 1)

        if end > len(data):
            raise UnsafeImage('invalid WebP chunk boundary')

        payload = data[pos + 8:pos + 8 + length]
        chunks.append((kind, payload, data[pos:end]))

        if kind == b'VP8X':
            if pos != 12 or length != 10 or flags is not None:
                raise UnsafeImage('invalid VP8X')

            flags = payload[0]
            result.append((
                kind,
                bytes([payload[0] & ~0x0c]) + payload[1:],
            ))

        elif kind not in (b'EXIF', b'XMP '):
            result.append((kind, data[pos:end]))

        pos = end

    validate_webp_features(chunks, flags)

    if not any(
        kind in (b'VP8 ', b'VP8L', b'ANMF')
        for kind, _, _ in chunks
    ):
        raise UnsafeImage('missing image payload')

    return tuple(result)


def verify_selective(before, after, format_name):
    """Refuse metadata edits that modify encoded presentation data."""
    if format_name == 'jpeg':
        original = selective_jpeg_core(before)
        updated = selective_jpeg_core(after)

    elif format_name == 'webp':
        original = selective_webp_core(before)
        updated = selective_webp_core(after)

    else:
        raise UnsafeImage('unsupported selective integrity format')

    if original != updated:
        raise UnsafeImage(
            'encoded image, color or animation data changed'
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--format',
        choices=('jpeg', 'webp'),
        required=True,
    )
    parser.add_argument(
        '--input', type=Path, required=True
    )
    parser.add_argument(
        '--output', type=Path
    )
    parser.add_argument('--verify-before', type=Path)

    args = parser.parse_args()
    created = False

    try:
        source = args.input.read_bytes()

        if args.verify_before is not None:
            verify_selective(
                args.verify_before.read_bytes(),
                source,
                args.format,
            )
            return 0

        if args.output is None:
            raise UnsafeImage('output path required')

        operation = (
            jpeg if args.format == 'jpeg'
            else webp
        )

        output, count = operation(source)

        verified, remaining = operation(output)

        if verified != output or remaining:
            raise UnsafeImage(
                'reconstructed output failed validation'
            )

        with args.output.open('xb') as stream:
            created = True
            stream.write(output)

        print(
            f'removed={count} '
            f'bytes={len(source)}->{len(output)}'
        )

        return 0

    except (OSError, UnsafeImage) as exc:
        if created:
            args.output.unlink(missing_ok=True)

        print(
            f'KIM6 reconstruction refused: {exc}',
            file=sys.stderr,
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
