#!/usr/bin/env python3
"""KIM6 conservative PNG/APNG metadata container filtering.

Preserves encoded image and animation data without re-encoding.
Unknown or unsupported metadata structures fail closed when their
safe removal or preservation cannot be established.
"""

from __future__ import annotations

import argparse
import binascii
from pathlib import Path
import struct
import sys
import zlib
import xml.etree.ElementTree as ET


SIG = b'\x89PNG\r\n\x1a\n'

# Chunks required for decoding, color interpretation, presentation,
# transparency, and animation.
PRESENTATION = {
    b'PLTE', b'tRNS', b'cHRM', b'gAMA', b'iCCP',
    b'sRGB', b'sBIT', b'bKGD', b'hIST', b'pHYs',
    b'sPLT', b'acTL', b'fcTL', b'fdAT',
}

IMAGE = {b'IHDR', b'IDAT', b'IEND'}
TEXT = {b'tEXt', b'zTXt', b'iTXt'}

# Ordinary photographic text that AI mode may preserve.
PHOTOGRAPHIC_TEXT = {
    'title', 'description', 'comment', 'author',
    'artist', 'copyright', 'disclaimer', 'warning',
    'source', 'creation time', 'date:create', 'date:modify',
}

# Recognized generation-specific text keys.
AI_KEYWORDS = {
    'prompt', 'workflow', 'parameters', 'negative prompt',
    'generation data', 'model', 'sampler', 'seed',
    'steps', 'cfg scale', 'denoise', 'loras',
    'comfyui', 'invokeai', 'automatic1111', 'fooocus',
}

# Recognizable content signatures in generic metadata fields.
AI_SIGNATURES = (
    b'"class_type"',
    b'"sampler_name"',
    b'"positive"',
    b'"negative"',
    b'negative prompt:',
    b'cfg scale:',
    b'steps:',
    b'comfyui',
    b'stable diffusion',
    b'invokeai',
    b'fooocus',
    b'automatic1111',
)

MAX_TEXT = 16 * 1024 * 1024


class UnsafePNG(ValueError):
    """The input cannot be reconstructed safely."""


def decompress_limited(data: bytes) -> bytes:
    """Decompress PNG text without permitting unbounded expansion."""
    dec = zlib.decompressobj()

    try:
        output = dec.decompress(data, MAX_TEXT + 1)

        if (
            len(output) > MAX_TEXT
            or not dec.eof
            or dec.unused_data
            or dec.unconsumed_tail
        ):
            raise UnsafePNG(
                'compressed text exceeds limit or is malformed'
            )

        output += dec.flush()

    except zlib.error as exc:
        raise UnsafePNG('malformed compressed text') from exc

    if len(output) > MAX_TEXT:
        raise UnsafePNG('decompressed text exceeds limit')

    return output


def unpack_text(tag: bytes, payload: bytes) -> tuple[str, bytes]:
    """Decode tEXt, zTXt, or iTXt for privacy classification."""
    key, separator, remainder = payload.partition(b'\x00')

    if not separator or not (1 <= len(key) <= 79):
        raise UnsafePNG('invalid PNG text keyword')

    keyword = key.decode('latin-1').casefold().strip()

    if tag == b'tEXt':
        value = remainder

    elif tag == b'zTXt':
        if len(remainder) < 1 or remainder[0] != 0:
            raise UnsafePNG('unsupported zTXt compression')

        value = decompress_limited(remainder[1:])

    else:
        if (
            len(remainder) < 2
            or remainder[0] not in (0, 1)
            or remainder[1] != 0
        ):
            raise UnsafePNG('unsupported iTXt compression')

        language, separator, rest = (
            remainder[2:].partition(b'\x00')
        )

        if not separator:
            raise UnsafePNG('invalid iTXt language field')

        translated, separator, value = rest.partition(b'\x00')

        if not separator:
            raise UnsafePNG('invalid iTXt translated keyword')

        if remainder[0]:
            value = decompress_limited(value)

    if len(value) > MAX_TEXT:
        raise UnsafePNG('text chunk exceeds safety limit')

    return keyword, value



XMP_SAFE = {
    'adobe:ns:meta/',
    'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'http://purl.org/dc/elements/1.1/',
    'http://ns.adobe.com/xap/1.0/',
    'http://ns.adobe.com/xap/1.0/rights/',
    'http://ns.adobe.com/exif/1.0/',
    'http://ns.adobe.com/exif/1.0/aux/',
    'http://ns.adobe.com/tiff/1.0/',
    'http://ns.adobe.com/photoshop/1.0/',
    'http://iptc.org/std/Iptc4xmpExt/2008-02-29/',
    'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
}


def local(name):
    return (
        name.rsplit('}', 1)[-1]
        .casefold()
        .replace('_', '')
        .replace('-', '')
        .replace(' ', '')
    )


def known(name):
    return (
        isinstance(name, str)
        and name.startswith('{')
        and name[1:].split('}', 1)[0] in XMP_SAFE
    )


def is_gps(name):
    return any(
        x in local(name)
        for x in ('gps', 'latitude', 'longitude', 'geocoordinate')
    )


def is_ai(name):
    key = local(name)
    return (
        key in {
            'parameters', 'model', 'seed', 'sampler',
            'cfgscale', 'steps', 'denoise',
            'aipromptinformation', 'aipromptwritername',
            'aisystemused', 'aisystemversionused',
        }
        or any(
            x in key
            for x in ('workflow', 'prompt', 'comfyui', 'diffusion')
        )
    )


def filter_xmp(data, mode, remove_ai):
    if (
        b'<!DOCTYPE' in data.upper()
        or b'<!ENTITY' in data.upper()
    ):
        raise UnsafePNG('unsupported XML constructs')

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise UnsafePNG('malformed XMP') from exc

    if not known(root.tag):
        raise UnsafePNG('unrecognized XMP root')

    changed = False
    ai_sources = {
        'trainedalgorithmicmedia',
        'compositewithtrainedalgorithmicmedia',
        'algorithmicmedia',
    }

    def drop(name, value):
        if mode == 'gps' and is_gps(name):
            return True

        if mode == 'ai' or remove_ai:
            if is_ai(name):
                return True

            if (
                local(name) == 'digitalsourcetype'
                and value.strip().casefold() in ai_sources
            ):
                return True

            if mode == 'ai' and not known(name):
                return True

        return False

    def walk(node):
        nonlocal changed

        for name, value in list(node.attrib.items()):
            if drop(name, value):
                del node.attrib[name]
                changed = True

        for child in list(node):
            if not isinstance(child.tag, str):
                continue

            if drop(child.tag, ''.join(child.itertext())):
                node.remove(child)
                changed = True
            else:
                walk(child)

    walk(root)

    return (
        ET.tostring(root, encoding='utf-8')
        if changed else data
    )


def text_payload(tag, payload, mode, remove_ai):
    if mode == 'all':
        return None

    key, value = unpack_text(tag, payload)

    if key == 'xml:com.adobe.xmp':
        updated = filter_xmp(value, mode, remove_ai)

        if updated == value:
            return payload

        name, _, tail = payload.partition(b'\x00')

        if tag == b'tEXt':
            return name + b'\x00' + updated

        if tag == b'zTXt':
            return name + b'\x00\x00' + zlib.compress(updated)

        language, sep, rest = tail[2:].partition(b'\x00')

        if not sep:
            raise UnsafePNG('bad iTXt language')

        translated, sep, _ = rest.partition(b'\x00')

        if not sep:
            raise UnsafePNG('bad iTXt translated keyword')

        return (
            name + b'\x00'
            + tail[:2]
            + language + b'\x00'
            + translated + b'\x00'
            + (
                zlib.compress(updated)
                if tail[0] else updated
            )
        )

    if 'xml' in key or 'xmp' in key:
        raise UnsafePNG('unknown XML payload')

    if mode == 'gps' and is_gps(key):
        return None

    if mode == 'ai' or remove_ai:
        if is_ai(key):
            return None

        if any(x in value.lower() for x in AI_SIGNATURES):
            if key in PHOTOGRAPHIC_TEXT:
                raise UnsafePNG(
                    'AI metadata mixed into ordinary text'
                )
            return None

    if mode == 'ai' and key not in PHOTOGRAPHIC_TEXT:
        return None

    return payload


def make_chunk(tag, payload):
    return (
        struct.pack('>I', len(payload))
        + tag + payload
        + struct.pack(
            '>I',
            binascii.crc32(tag + payload) & 0xffffffff,
        )
    )


def orientation_only(payload):
    if len(payload) < 8 or payload[:2] not in (b'II', b'MM'):
        raise UnsafePNG('invalid EXIF header')

    endian = '<' if payload[:2] == b'II' else '>'

    if struct.unpack_from(endian + 'H', payload, 2)[0] != 42:
        raise UnsafePNG('unsupported EXIF TIFF header')

    offset = struct.unpack_from(endian + 'I', payload, 4)[0]

    if offset < 8 or offset + 2 > len(payload):
        raise UnsafePNG('invalid EXIF offset')

    count = struct.unpack_from(endian + 'H', payload, offset)[0]

    if offset + 2 + count * 12 + 4 > len(payload):
        raise UnsafePNG('truncated EXIF directory')

    orientation = None

    for index in range(count):
        at = offset + 2 + 12 * index

        code, kind, items = struct.unpack_from(
            endian + 'HHI', payload, at
        )

        if code == 274:
            if (
                orientation is not None
                or kind != 3
                or items != 1
            ):
                raise UnsafePNG('ambiguous orientation')

            orientation = struct.unpack_from(
                endian + 'H',
                payload,
                at + 8,
            )[0]

            if not 1 <= orientation <= 8:
                raise UnsafePNG('invalid orientation')

    if orientation is None:
        return None

    return (
        b'II*\x00\x08\x00\x00\x00\x01\x00'
        + struct.pack('<HHIH', 274, 3, 1, orientation)
        + b'\x00\x00\x00\x00\x00\x00'
    )


def filter_png(data: bytes, mode: str, remove_ai=False) -> tuple[bytes, int]:
    """Reconstruct recognized PNG structures without re-encoding."""
    if mode not in ('all', 'ai', 'gps'):
        raise ValueError('invalid metadata mode')

    if not data.startswith(SIG):
        raise UnsafePNG('not a PNG')

    position = len(SIG)
    result = bytearray(SIG)

    seen_ihdr = False
    seen_iend = False
    seen_idat = False
    discarded = 0

    while position < len(data):
        if len(data) - position < 12:
            raise UnsafePNG('truncated PNG chunk')

        size = struct.unpack_from('>I', data, position)[0]
        tag = data[position + 4:position + 8]
        end = position + 12 + size

        if (
            end > len(data)
            or len(tag) != 4
            or any(
                not (65 <= c <= 90 or 97 <= c <= 122)
                for c in tag
            )
        ):
            raise UnsafePNG('invalid chunk header')

        chunk = data[position:end]
        payload = data[position + 8:end - 4]

        crc = struct.unpack_from('>I', data, end - 4)[0]

        if binascii.crc32(tag + payload) & 0xffffffff != crc:
            raise UnsafePNG('PNG CRC mismatch')

        if not seen_ihdr:
            if tag != b'IHDR' or size != 13:
                raise UnsafePNG('invalid IHDR')
            seen_ihdr = True

        elif tag == b'IHDR':
            raise UnsafePNG('duplicate IHDR')

        if tag == b'IDAT':
            seen_idat = True

        if tag == b'IEND':
            if size or not seen_idat:
                raise UnsafePNG('invalid IEND')
            seen_iend = True

        selected = chunk

        if tag == b'eXIf':
            if mode != 'all':
                raise UnsafePNG(
                    'selective EXIF edit needs TIFF IFD filtering'
                )

            orientation = orientation_only(payload)

            selected = (
                make_chunk(tag, orientation)
                if orientation else None
            )

        elif tag in TEXT:
            updated = text_payload(
                tag, payload, mode, remove_ai
            )

            if updated is None:
                selected = None
            elif updated != payload:
                selected = make_chunk(tag, updated)

        elif tag in IMAGE or tag in PRESENTATION:
            pass

        elif not tag[0] & 0x20:
            raise UnsafePNG('unknown critical PNG chunk')

        elif mode in ('all', 'ai'):
            selected = None

        if selected is not None:
            result.extend(selected)

        if selected != chunk:
            discarded += 1

        position = end

        if seen_iend:
            if position != len(data):
                raise UnsafePNG('trailing bytes after IEND')
            break

    if not seen_iend:
        raise UnsafePNG('IEND missing')

    return bytes(result), discarded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--mode', choices=('all', 'ai', 'gps'), required=True
    )
    parser.add_argument('--remove-ai', action='store_true')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)

    args = parser.parse_args()

    try:
        source = args.input.read_bytes()
        result, removed = filter_png(source, args.mode, args.remove_ai)

        with args.output.open('xb') as stream:
            stream.write(result)

        # Reinspect the exact output before declaring success.
        checked, second = filter_png(result, args.mode, args.remove_ai)

        if checked != result or second != 0:
            args.output.unlink(missing_ok=True)
            raise UnsafePNG('post-write validation failed')

        print(
            f'removed={removed} '
            f'bytes={len(source)}->{len(result)}'
        )

        return 0

    except (OSError, UnsafePNG) as exc:
        print(
            f'PNG metadata processing refused: {exc}',
            file=sys.stderr,
        )
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
