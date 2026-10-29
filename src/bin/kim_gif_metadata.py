#!/usr/bin/env python3
"""Lossless, fail-closed GIF full-metadata reconstruction."""

import argparse
from pathlib import Path
import sys


class UnsafeGIF(ValueError):
    pass


def subblocks(data, pos):
    while True:
        if pos >= len(data):
            raise UnsafeGIF("truncated data subblocks")
        count = data[pos]
        pos += 1
        if pos + count > len(data):
            raise UnsafeGIF("invalid data subblock")
        pos += count
        if count == 0:
            return pos


def reconstruct(data):
    if len(data) < 14 or data[:6] not in (b"GIF87a", b"GIF89a"):
        raise UnsafeGIF("invalid GIF header")

    pos = 13
    packed = data[10]
    if packed & 0x80:
        pos += 3 * (1 << ((packed & 7) + 1))
    if pos >= len(data):
        raise UnsafeGIF("truncated global color table")

    out = bytearray(data[:pos])
    frames = 0
    removed = 0
    ended = False

    while pos < len(data):
        start = pos
        kind = data[pos]
        pos += 1

        if kind == 0x3B:
            if pos != len(data):
                raise UnsafeGIF("trailing GIF data")
            out.append(kind)
            ended = True
            break

        if kind == 0x2C:
            if pos + 9 > len(data):
                raise UnsafeGIF("truncated image descriptor")
            descriptor = data[pos:pos + 9]
            pos += 9
            if descriptor[8] & 0x80:
                pos += 3 * (1 << ((descriptor[8] & 7) + 1))
            if pos >= len(data):
                raise UnsafeGIF("missing LZW code size")
            if not 2 <= data[pos] <= 8:
                raise UnsafeGIF("invalid LZW code size")
            pos = subblocks(data, pos + 1)
            out.extend(data[start:pos])
            frames += 1
            continue

        if kind != 0x21 or pos >= len(data):
            raise UnsafeGIF("unrecognized GIF block")

        label = data[pos]
        pos += 1

        if label == 0xF9:
            if (
                pos + 6 > len(data)
                or data[pos] != 4
                or data[pos + 5] != 0
            ):
                raise UnsafeGIF("invalid graphics control extension")
            pos += 6
            out.extend(data[start:pos])
            continue

        if label == 0xFE:
            pos = subblocks(data, pos)
            removed += 1
            continue

        if label == 0x01:
            if pos + 13 > len(data) or data[pos] != 12:
                raise UnsafeGIF("invalid plain text extension")
            pos = subblocks(data, pos + 13)
            out.extend(data[start:pos])
            continue

        if label == 0xFF:
            if pos + 12 > len(data) or data[pos] != 11:
                raise UnsafeGIF("invalid application extension")

            identifier = data[pos + 1:pos + 12]
            pos = subblocks(data, pos + 12)

            if identifier in (b"NETSCAPE2.0", b"ANIMEXTS1.0"):
                out.extend(data[start:pos])
            elif identifier == b"XMP DataXMP":
                removed += 1
            else:
                raise UnsafeGIF("unrecognized application extension")
            continue

        raise UnsafeGIF("unsupported GIF extension")

    if not ended or not frames:
        raise UnsafeGIF("GIF trailer or frames missing")

    return bytes(out), removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("gif",), required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    created = False
    try:
        source = args.input.read_bytes()
        output, removed = reconstruct(source)
        if reconstruct(output) != (output, 0):
            raise UnsafeGIF("output failed revalidation")

        with args.output.open("xb") as stream:
            created = True
            stream.write(output)

        print(f"removed={removed} bytes={len(source)}->{len(output)}")
        return 0
    except (OSError, UnsafeGIF) as exc:
        if created:
            args.output.unlink(missing_ok=True)
        print(f"KIM6 GIF refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
