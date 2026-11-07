"""Read-only date planning used by standalone dialogs and their executor."""
import argparse
import datetime as dt
import json
import os
import copy
from functools import lru_cache
from pathlib import Path
import sys
from kim_recipe_core import RecipeError
from kim_recipe_dates import specific, explicit, timezone, assignments, display, epoch_ns
from kim_recipe_image import capture_date, NO_LEGACY_IPTC, canonical_file_type
from kim_process import run_process


def ensure_still_capture_input(path, preview=False):
    """Do not let a still-photo metadata workflow weaken animation refusals.

    Header/chunk inspection is read-only and never decodes a large PSD merely
    to display the date dialog. Unsupported/truncated files still reach the
    existing metadata/tool validation; animation control always fails closed.
    """
    import struct
    import os
    with os.fdopen(os.open(path,os.O_RDONLY | (os.O_NOFOLLOW|os.O_NOATIME if preview else 0)),'rb') as stream:
        signature=stream.read(12)
        png=signature.startswith(b'\x89PNG\r\n\x1a\n')
        webp=signature[:4]==b'RIFF' and signature[8:12]==b'WEBP'
        if not (png or webp): return
        stream.seek(8 if png else 12)
        while chunk:=stream.read(8):
            if len(chunk)!=8: return
            if png: length,tag=struct.unpack('>I4s',chunk)
            else: tag,length=struct.unpack('<4sI',chunk)
            if tag in (b'acTL',b'fcTL',b'fdAT',b'ANIM',b'ANMF'):
                raise RecipeError('Animated images are not supported by Image Capture Date actions. Select a still PNG/JPEG or use the existing animation menus; no date was changed.')
            if png and tag==b'IEND': return
            stream.seek(length+(4 if png else length%2),1)


def _source_date_uncached(path, ignore_invalid=False, preview=False, allow_animation=False):
    if not allow_animation:
        ensure_still_capture_input(path,preview)
    tags=['-EXIF:all','-XMP:all','-IPTC:DateCreated','-IPTC:TimeCreated','-FileType']
    if preview:
        from kim_preview import read_metadata
        raw=read_metadata(path,tags)
    else:
        result=run_process(['exiftool','-json','-G1',*tags,'--',str(path)],text=True)
        if result.returncode: raise RecipeError('Cannot read image capture dates: '+result.stderr.strip())
        raw=json.loads(result.stdout)[0]
    exif = raw.get('ExifIFD:DateTimeOriginal'); xmp = raw.get('XMP-exif:DateTimeOriginal')
    info = {'DateTimeOriginal':exif or xmp, 'FileType':raw.get('File:FileType','')}
    if exif:
        info.update(OffsetTimeOriginal=raw.get('ExifIFD:OffsetTimeOriginal'),
                    SubSecTimeOriginal=raw.get('ExifIFD:SubSecTimeOriginal',''))
    try: capture = capture_date(info)
    except RecipeError:
        if not ignore_invalid: raise
        capture=None
    import re
    match = re.search(r'\.(\d+)',str(info['DateTimeOriginal']))
    fraction = str(info.get('SubSecTimeOriginal') or (match.group(1) if match else ''))
    return capture, fraction, canonical_file_type(info['FileType']).lower(),raw


@lru_cache(maxsize=128)
def _cache_source_date(path, ignore_invalid, preview, stamp, allow_animation):
    return _source_date_uncached(path, ignore_invalid, preview, allow_animation)


def source_date(path, ignore_invalid=False, preview=False, allow_animation=False):
    path = os.path.abspath(os.fspath(path))

    def fingerprint():
        info = os.stat(path, follow_symlinks=False)
        return (info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    before = fingerprint()
    result = _cache_source_date(
        path, bool(ignore_invalid), bool(preview), before, bool(allow_animation)
    )

    if fingerprint() != before:
        _cache_source_date.cache_clear()
        raise RecipeError(
            'Source changed during date inspection. Review a fresh plan.'
        )

    return copy.deepcopy(result)


def resolve(path, config):
    kind = config['kind']; fields = config.get('fields','capture'); zone = config.get('timezone','embedded')
    if fields not in ('capture','all'): raise RecipeError('Choose the date fields to change.')
    if kind == 'set-file':
        capture, fraction = explicit(
            config.get('datetime', ''), zone
        )
        return {
            'epoch_ns': epoch_ns(capture, fraction),
            'preview': display(capture, fraction),
            'args': [],
        }

    if (
        kind == 'reference-to-file'
        and config.get('reference_type') == 'file'
    ):
        from kim_preview import identity

        reference = config['reference_path']
        expected = config['reference_identity']

        if identity(reference) != expected:
            raise RecipeError(
                'Reference image changed. Select it again.'
            )

        ns = Path(reference).stat().st_mtime_ns

        if identity(reference) != expected:
            raise RecipeError(
                'Reference image changed during inspection.'
            )

        seconds, subsec = divmod(ns, 10**9)
        value = dt.datetime.fromtimestamp(
            seconds, dt.timezone.utc
        )
        return {
            'epoch_ns': ns,
            'preview': display(
                value, f'{subsec:09d}'.rstrip('0')
            ),
            'args': [],
        }

    file_date_only = kind in (
        'set-file', 'reference-to-file', 'exif-to-file'
    )

    capture, fraction, fmt, raw = source_date(
        path,
        ignore_invalid=kind in (
            'set', 'file-to-exif', 'set-file',
            'reference-to-exif', 'reference-to-file'
        ),
        preview=config.get('_preview', False),
        allow_animation=file_date_only,
    )

    if kind == 'set':
        capture, fraction = explicit(config.get('datetime',''),zone)
    elif kind == 'set-file':
        capture, fraction = explicit(
            config.get('datetime', ''), zone
        )
    elif kind in ('reference-to-exif', 'reference-to-file'):
        from kim_preview import identity

        reference = config['reference_path']

        if identity(reference) != config['reference_identity']:
            raise RecipeError(
                'Reference image changed. Select it again.'
            )

        ref_type = config['reference_type']

        if ref_type not in ('capture', 'file'):
            raise RecipeError('Invalid reference date source.')

        if ref_type == 'capture':
            capture, fraction, _, _ = source_date(
                reference,
                ignore_invalid=False,
                preview=config.get('_preview', False),
            )

            if capture is None:
                raise RecipeError(
                    'The reference image has no usable capture date.'
                )

            if zone != 'embedded':
                capture = capture.replace(
                    tzinfo=timezone(zone)
                )

        else:
            ns = Path(reference).stat().st_mtime_ns
            seconds, subsec = divmod(ns, 10**9)

            if kind == 'reference-to-file':
                display_date = dt.datetime.fromtimestamp(
                    seconds, dt.timezone.utc
                )

                return {
                    'epoch_ns': ns,
                    'preview': display(
                        display_date,
                        f'{subsec:09d}'.rstrip('0'),
                    ),
                    'args': [],
                }

            tz = timezone(zone)

            if tz is None:
                raise RecipeError(
                    'Choose UTC or an explicit offset '
                    'for the reference file date.'
                )

            capture = dt.datetime.fromtimestamp(
                seconds, tz
            )

            fraction = f'{subsec:09d}'.rstrip('0')

        if identity(reference) != config['reference_identity']:
            raise RecipeError(
                'Reference image changed during preview.'
            )

    elif kind == 'file-to-exif':
        tz = timezone(zone)
        if tz is None: raise RecipeError('Choose a known timezone to express the File Modification Date as an Image Capture Date.')
        ns = Path(path).stat().st_mtime_ns
        capture = dt.datetime.fromtimestamp(ns//10**9,tz)
        fraction = f'{ns % 10**9:09d}'.rstrip('0')
    elif kind in ('shift','exif-to-file'):
        if capture is None: epoch_ns(None,'')
        if zone != 'embedded': capture = capture.replace(tzinfo=timezone(zone))
        if kind == 'shift':
            seconds = config.get('seconds',0)
            if type(seconds) is not int or abs(seconds) > 315576000: raise RecipeError('Choose an adjustment within ten years.')
            try: capture += dt.timedelta(seconds=seconds)
            except OverflowError as exc: raise RecipeError('The adjusted date is outside the supported years.') from exc
    else: raise RecipeError('Unknown date action')
    if kind in ('exif-to-file', 'set-file', 'reference-to-file'):
        return {
            'epoch_ns': epoch_ns(capture, fraction),
            'preview': display(capture, fraction),
            'args': [],
        }

    if fmt not in ('jpeg','png','tiff','webp','avif','heic','heif','jp2','jxl','psd'):
        raise RecipeError(
            fmt.upper()
            + ' cannot safely store the selected image capture '
            'date fields. Convert to JPEG, PNG or TIFF first.'
        )
    args = assignments(capture,fraction,fields,fmt not in NO_LEGACY_IPTC)
    if kind == 'shift' and fields == 'all':
        # Change only dates that exist, each by the same wall-clock delta.
        for key,subsec,offset,mirror in [('CreateDate','SubSecTimeDigitized','OffsetTimeDigitized','XMP-xmp:CreateDate'),
                                         ('ModifyDate','SubSecTime','OffsetTime','XMP-xmp:ModifyDate')]:
            value=raw.get('ExifIFD:'+key) if key=='CreateDate' else raw.get('IFD0:'+key)
            args=[a for a in args if not a.startswith(('-EXIF:'+key+'=','-EXIF:'+subsec+'=','-EXIF:'+offset+'=','-'+mirror+'='))]
            if value:
                other=capture_date({'DateTimeOriginal':value,'OffsetTimeOriginal':raw.get('ExifIFD:'+offset)})
                try: other+=dt.timedelta(seconds=config.get('seconds',0))
                except OverflowError as exc: raise RecipeError('An adjusted embedded date is outside the supported years.') from exc
                frac=str(raw.get('ExifIFD:'+subsec,''))
                wall=f'{other.year:04d}:'+other.strftime('%m:%d %H:%M:%S')
                off=other.strftime('%z'); off=off[:3]+':'+off[3:] if off else ''
                args += ['-EXIF:'+key+'='+wall, '-'+mirror+'='+wall+('.'+frac if frac else '')+off]
    return {'preview':display(capture,fraction),'args':args,'current':raw}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('config'); parser.add_argument('source'); parser.add_argument('result')
    args=parser.parse_args()
    try:
        result=resolve(args.source,json.loads(Path(args.config).read_text()))
        values = ([str(result['epoch_ns'])] if 'epoch_ns' in result else result['args'])
        Path(args.result).write_bytes(b''.join(v.encode()+b'\0' for v in values)); return 0
    except (OSError, ValueError, RecipeError) as exc:
        print(str(exc),file=sys.stderr); return 1


if __name__ == '__main__': raise SystemExit(main())
