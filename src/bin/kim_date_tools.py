"""Read-only date planning used by standalone dialogs and their executor."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from kim_recipe_core import RecipeError
from kim_recipe_dates import specific, explicit, timezone, assignments, display, epoch_ns
from kim_recipe_image import capture_date, NO_LEGACY_IPTC, canonical_file_type
from kim_psd_source import run_process


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
                raise RecipeError('Animated images are not supported by Photo Capture Date actions. Select a still PNG/JPEG or use the existing animation menus; no date was changed.')
            if png and tag==b'IEND': return
            stream.seek(length+(4 if png else length%2),1)


def source_date(path, ignore_invalid=False, preview=False):
    ensure_still_capture_input(path,preview)
    tags=['-EXIF:all','-XMP:all','-IPTC:DateCreated','-IPTC:TimeCreated','-FileType']
    if preview:
        from kim_preview import read_metadata
        raw=read_metadata(path,tags)
    else:
        result=run_process(['exiftool','-json','-G1',*tags,'--',str(path)],text=True)
        if result.returncode: raise RecipeError('Cannot read photo dates: '+result.stderr.strip())
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


def resolve(path, config):
    kind = config['kind']; fields = config.get('fields','capture'); zone = config.get('timezone','embedded')
    if fields not in ('capture','all'): raise RecipeError('Choose the date fields to change.')
    capture, fraction, fmt, raw = source_date(path, ignore_invalid=kind in ('set','file-to-exif'),preview=config.get('_preview',False))
    if kind == 'set':
        capture, fraction = explicit(config.get('datetime',''),zone)
    elif kind == 'file-to-exif':
        tz = timezone(zone)
        if tz is None: raise RecipeError('Choose a known timezone to express the File Modification Date as a Photo Capture Date.')
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
    if fmt not in ('jpeg','png','tiff','webp','avif','heic','heif','jp2','jxl','psd'):
        raise RecipeError(fmt.upper() + ' cannot safely store the selected photo date fields. Convert to JPEG, PNG or TIFF first.')
    if kind == 'exif-to-file':
        return {'epoch_ns':epoch_ns(capture,fraction),'preview':display(capture,fraction),'args':[]}
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
