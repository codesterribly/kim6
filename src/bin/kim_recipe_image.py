"""Image operation handler. External tools receive fixed argument arrays only."""
import copy
import contextlib
import contextvars
import datetime as dt
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import struct
import string
import tempfile
from kim_settings_file import read_settings
from kim_image_ops import CROP_DEFAULTS, OVERLAY_DEFAULTS
from kim_psd_source import prepared, prepared_read, PSDError, WARNING as PSD_WARNING, protected_header as psd_header
from kim_process import open_inspection_fd, run_process, metadata_diagnostics, session_warnings, stage
from kim_recipe_core import RecipeError, OutputFormatRequired, keys, text, enabled_steps, config_path, format_output_pattern, display_output_pattern

_OMIT_STANDALONE_OVERLAY_METADATA = contextvars.ContextVar(
    "kimng_omit_standalone_overlay_metadata",
    default=False,
)


@contextlib.contextmanager
def standalone_overlay_metadata_policy(enabled=False):
    """Explicit transient output policy, scoped to one worker."""
    token = _OMIT_STANDALONE_OVERLAY_METADATA.set(
        bool(enabled)
    )
    try:
        yield
    finally:
        _OMIT_STANDALONE_OVERLAY_METADATA.reset(token)


_AUTO_WATERMARK_METADATA_FALLBACK = contextvars.ContextVar(
    "kimng_auto_watermark_metadata_fallback",
    default=False,
)


@contextlib.contextmanager
def automatic_watermark_metadata_fallback(enabled=False):
    token = _AUTO_WATERMARK_METADATA_FALLBACK.set(
        bool(enabled)
    )
    try:
        yield
    finally:
        _AUTO_WATERMARK_METADATA_FALLBACK.reset(token)


FORMATS = {'jpeg': 'jpg', 'png': 'png', 'webp': 'webp', 'avif': 'avif',
           'bmp': 'bmp', 'gif': 'gif', 'heic': 'heic', 'heif': 'heif',
           'jp2': 'jp2', 'jxl': 'jxl', 'pdf': 'pdf', 'tiff': 'tiff'}
CODERS = {fmt: fmt.upper() for fmt in FORMATS}
CODERS.update(jpeg='JPEG', heif='HEIC')
# These containers cannot safely carry the engine's full EXIF/IPTC/XMP contract.
# Export pixels, optionally stripping metadata in the encoder, rather than
# pretending an ExifTool write succeeded or retaining hidden PDF revisions.
PIXEL_EXPORTS = {'bmp', 'gif', 'pdf'}
# ExifTool can write EXIF/XMP here, but not legacy IPTC-IIM.
NO_LEGACY_IPTC = {'webp', 'heic', 'heif', 'avif', 'jxl'}
CONVERT_OPTIONS = {'jp2_mode': 'lossless', 'tiff_compression': 'zip',
                   'depth': 'preserve', 'jpeg_progressive': False, 'jpeg_optimize': False}
CATEGORIES = ('Geometry & Orientation', 'Format & Color', 'Metadata & Copyright', 'Filenames & Dates')
AI_TAGS = ('XMP-iptcExt:AIPromptInformation', 'XMP-iptcExt:AIPromptWriterName',
           'XMP-iptcExt:AISystemUsed', 'XMP-iptcExt:AISystemVersionUsed')
GPS_TAGS = ('GPS:all', 'XMP-exif:GPS*', 'XMP:GPS*') + tuple(
    'XMP-iptcExt:' + location + field
    for location in ('LocationShown', 'LocationCreated', 'RatingRegion')
    for field in ('GPSLatitude', 'GPSLongitude', 'GPSAltitude', 'GPSAltitudeRef'))

DEFAULTS = {
    'image.crop': CROP_DEFAULTS, 'image.overlay': OVERLAY_DEFAULTS,
    'image.auto_orient': {}, 'image.rotate': {'degrees': 90},
    'image.flip': {'axis': 'horizontal'},
    'image.resize': {'max_width': 2048, 'max_height': 2048, 'upscale': False},
    'image.resize_percent': {'percent': 50},
    'image.resize_exact': {'width': 1600, 'height': 1200},
    'image.resize_long_edge': {'pixels': 1600, 'upscale': False},
    'image.resize_geometry': {'geometry': '1600x1600>'},
    'image.convert': {'format': 'jpeg', 'quality': 90},
    'image.compress': {'preset': 'recommended', 'quality': 85, 'png_level': 6,
                       'jpeg_progressive': True, 'jpeg_optimize': False},
    'image.color': {'mode': 'preserve'},
    'metadata.strip_all': {}, 'metadata.strip_descriptive': {}, 'metadata.strip_gps': {}, 'metadata.reduce_gps': {'grid': '1000'}, 'metadata.strip_ai': {},
    'metadata.set_description': {'value': ''},
    'metadata.set_keywords': {'mode': 'unchanged', 'keywords': ''},
    'metadata.copyright': {'creator': None, 'notice': None, 'rights': None},
    'metadata.creator': {}, 'metadata.copyright_notice': {}, 'metadata.usage_rights': {},
    'metadata.shift_capture': {'seconds': 3600},
    'metadata.set_capture': {'mode': 'specific', 'datetime': '', 'timezone': 'unknown', 'fields': 'capture'},
    'file.name_transform': {'method': 'lowercase', 'value': '', 'replacement': '', 'start': 1, 'padding': 3},
    'file.rename_output': {'pattern': '{filename}_recipe'}, 'file.sync_date': {}, 'file.preserve_date': {},
}


SETTING_FIELDS = {'metadata.creator': 'creator', 'metadata.copyright_notice': 'notice',
                  'metadata.usage_rights': 'rights'}
SETTING_KEYS = {'creator': 'KIM_COPYRIGHT_CREATOR', 'notice': 'KIM_COPYRIGHT_NOTICE',
                'rights': 'KIM_COPYRIGHT_USAGE_RIGHTS'}
LABELS = {
    'image.crop': 'Crop Image', 'image.overlay': 'Add Watermark / Overlay',
    'image.auto_orient': 'Auto-Orient', 'image.resize': 'Resize to Fit',
    'image.resize_percent': 'Resize by Percentage', 'image.resize_exact': 'Resize to Exact Dimensions', 'image.rotate': 'Rotate',
    'image.flip': 'Flip Image', 'image.color': 'Color Profile', 'image.convert': 'Convert Format',
    'image.compress': 'Compress Image', 'image.resize_long_edge': 'Resize Long Edge',
    'image.resize_geometry': 'Resize with Custom Geometry',
    'metadata.set_capture': 'Set Image Capture Date', 'metadata.strip_descriptive': 'Remove Descriptive Metadata',
    'file.name_transform': 'Change Output Filename',
    'metadata.strip_all': 'Remove All Metadata', 'metadata.strip_gps': 'Remove GPS Location',
    'metadata.reduce_gps': 'Reduce GPS Precision',
    'metadata.set_description': 'Set Caption / Description',
    'metadata.set_keywords': 'Set Keywords',
    'metadata.strip_ai': 'Remove AI Metadata', 'metadata.copyright': 'Set Copyright',
    'metadata.shift_capture': 'Adjust Image Capture Date', 'file.rename_output': 'Rename Output File',
    'file.sync_date': 'Synchronize File Date', 'file.preserve_date': 'Keep Source File Date', 'metadata.creator': 'Set Creator / Artist',
    'metadata.copyright_notice': 'Set Copyright Notice', 'metadata.usage_rights': 'Set Usage Rights',
}


def literal_settings(defaults):
    """Read literal Settings values; never interpret shell syntax."""
    values = dict(defaults)
    path = config_path().with_name('settings.conf')
    try:
        stored = read_settings(path)
    except ValueError as exc:
        raise RecipeError(str(exc)) from exc
    for key, value in stored:
        if key in values:
            values[key] = text(value)
    for key in values:
        if key in os.environ:
            values[key] = text(os.environ[key])
    return values


def copyright_settings():
    values = literal_settings(dict.fromkeys(SETTING_KEYS.values(), ''))
    return {field: values[key] for field,key in SETTING_KEYS.items()}


def quality_setting(fmt):
    return {'jpeg':'KIM_WEB_QUALITY_JPEG','webp':'KIM_WEB_QUALITY_WEBP','avif':'KIM_WEB_QUALITY_AVIF'}.get(fmt)


def inherited_quality(fmt):
    key = quality_setting(fmt)
    if key is None: return 90  # Unused lossless controls, or an explicit-quality codec.
    value = literal_settings({key:'95'})[key]
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 100:
        raise RecipeError(key + ' in KIMng Settings must be 1–100. Correct Settings or enter a quality override.')
    return int(value)


COPYRIGHT_TAGS = {
    'creator': ('EXIF:Artist', 'IPTC:By-line', 'XMP-dc:Creator'),
    'notice': ('EXIF:Copyright', 'IPTC:CopyrightNotice', 'XMP-dc:Rights'),
    'rights': ('XMP-xmpRights:UsageTerms',),
}
DESCRIPTION_TAGS = ('XMP-dc:Description', 'IPTC:Caption-Abstract')
KEYWORD_TAGS = ('XMP-dc:Subject', 'IPTC:Keywords')
IPTC_CAPTION_BYTE_LIMIT = 2000
IPTC_KEYWORD_BYTE_LIMIT = 64


def parse_keywords(raw):
    """Parse comma-, semicolon-, or newline-separated keywords into a deduplicated list."""
    import re
    if not isinstance(raw, str):
        return []
    items, seen = [], set()
    for part in re.split(r'[,;\r\n]+', raw):
        cleaned = part.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            items.append(cleaned)
    return items


def _normalize_tag_list(value):
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    result, seen = [], set()
    for item in raw_items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def read_descriptive_metadata(path):
    """Read current XMP/IPTC description, language alternatives, and keywords."""
    data = json.loads(run([
        'exiftool', '-json', '-G1', '-a',
        '-XMP-dc:Description*', '-IPTC:Caption-Abstract',
        '-XMP-dc:Subject', '-IPTC:Keywords', '-',
    ], source=path))[0]
    xmp_desc = data.get('XMP-dc:Description')
    iptc_desc = data.get('IPTC:Caption-Abstract')
    lang_alts = {
        key: str(val)
        for key, val in data.items()
        if key.startswith('XMP-dc:Description-') and key != 'XMP-dc:Description-x-default' and val is not None
    }
    xmp_kw = _normalize_tag_list(data.get('XMP-dc:Subject'))
    iptc_kw = _normalize_tag_list(data.get('IPTC:Keywords'))
    merged_kw, seen = [], set()
    for kw in xmp_kw + iptc_kw:
        if kw not in seen:
            seen.add(kw)
            merged_kw.append(kw)
    return {
        'xmp_description': None if xmp_desc is None else str(xmp_desc),
        'iptc_description': None if iptc_desc is None else str(iptc_desc),
        'lang_alts': lang_alts,
        'xmp_keywords': xmp_kw,
        'iptc_keywords': iptc_kw,
        'keywords': merged_kw,
    }


_CROP_OPTIONAL_METADATA = contextvars.ContextVar(
    "kimng_crop_optional_metadata", default=False
)
_CROP_CLEAN_RETRY = contextvars.ContextVar(
    "kimng_crop_clean_retry", default=False
)


@contextlib.contextmanager
def standalone_crop_metadata_fallback():
    token = _CROP_OPTIONAL_METADATA.set(True)
    try:
        yield
    finally:
        _CROP_OPTIONAL_METADATA.reset(token)


@contextlib.contextmanager
def standalone_crop_clean_retry():
    token = _CROP_CLEAN_RETRY.set(True)
    try:
        yield
    finally:
        _CROP_CLEAN_RETRY.reset(token)


def selected_metadata(path, tags):
    data = json.loads(run(['exiftool', '-json', '-G1'] + ['-' + tag for tag in tags] + ['-'], source=path))[0]
    # These selected tags have distinct names; ExifTool reports EXIF's IFD group.
    return {tag: next((value for key, value in data.items()
                      if key.split(':')[-1] == tag.split(':')[-1]), None) for tag in tags}


def planning_metadata(path, *, psd=False):
    """One text-valued observation for the selected planning fields.

    Header/date numbers are deliberately read separately by inspect(). Family
    zero and one retain EXIF/IPTC/XMP and ICC subgroup distinctions here.
    """
    import fnmatch
    copyright_tags = [tag for tags in COPYRIGHT_TAGS.values() for tag in tags]
    ai_tags = AI_TAGS + ('XMP-iptcExt:DigitalSourceType',)
    tags = copyright_tags + list(GPS_TAGS) + list(ai_tags)
    # PSD ICC reads deliberately use the normalized composite, while rights,
    # GPS and provenance must describe the original Photoshop document.
    if not psd: tags.append('ICC_Profile:all')
    data = json.loads(run(['exiftool', '-json', '-G0:1'] + ['-' + tag for tag in tags] + ['-'], source=path))[0]
    if psd:
        profile_data = json.loads(run(['exiftool', '-json', '-G0:1', '-ICC_Profile:all', '-'], source=path))[0]
        data.update({key: value for key, value in profile_data.items() if key != 'SourceFile'})

    def matches(key, tag):
        parts = key.split(':')
        group, name = tag.split(':')
        return group in parts[:-1] and (name == 'all' or fnmatch.fnmatchcase(parts[-1], name))

    def selected(tags):
        return {tag: next((value for key, value in data.items() if matches(key, tag)), None) for tag in tags}

    gps = any(any(matches(key, tag) for tag in GPS_TAGS) for key in data)
    profile = {key.split(':')[-1]: value for key, value in data.items() if key.startswith('ICC_Profile:')}
    return selected(copyright_tags), gps, selected(ai_tags), profile


TOOL_TIMEOUT = 180

def run(args, allow_icc_removal=False, allow_png_iptc=False, *, source=None, fd=None):
    if not shutil.which(args[0]):
        raise RecipeError('Missing dependency: ' + args[0])
    try:
        if source is None:
            with prepared(args) as resolved:
                result = run_process(resolved, timeout=TOOL_TIMEOUT, text=True)
        else:
            with prepared_read(args, source, fd) as (resolved, stdin):
                result = run_process(resolved, timeout=TOOL_TIMEOUT, text=True, stdin=stdin)
    except (OSError, subprocess.TimeoutExpired, PSDError) as exc:
        raise RecipeError(str(exc)) from exc
    diagnostics = metadata_diagnostics(args, result.returncode, result.stderr)
    if allow_icc_removal:
        diagnostics = '\n'.join(line for line in diagnostics.splitlines() if not line.startswith('Warning: ICC_Profile deleted. Image colors may be affected - '))
    if allow_png_iptc:
        diagnostics = '\n'.join(line for line in diagnostics.splitlines() if not line.startswith('Warning: [minor] Creating non-standard IPTC in PNG - '))
    if result.returncode or 'Warning:' in diagnostics or 'Error:' in diagnostics:
        raise RecipeError(args[0] + ': ' + (result.stderr or result.stdout)[-1500:])
    return result.stdout


def magick_input(file_type):
    """Use seekable inherited stdin for stream-capable coders.

    ImageMagick sniffs bare '-' via a temporary file. Its HEIC delegate
    requires that named scratch input; native stream readers can use fd:0.
    The caller supplies the observed content type, never a filename suffix.
    """
    coder = file_type.upper()
    if coder in ('JPEG', 'PNG', 'WEBP', 'TIFF', 'GIF', 'BMP', 'PPM', 'JP2'):
        return coder + ':fd:0'
    return '-'


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise RecipeError(f'Expected integer {low}–{high}')


_CHECKED_INPUTS = contextvars.ContextVar('kim_checked_input_headers',default=None)


@contextlib.contextmanager
def checked_input_headers(cache):
    token=_CHECKED_INPUTS.set(cache)
    try: yield
    finally: _CHECKED_INPUTS.reset(token)


def inspection_identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def inspect(path, output=False, pdf_scale=1):
    from kim_process import checkpoint
    checkpoint()
    fd = open_inspection_fd(path)
    try:
        before=inspection_identity(os.fstat(fd)); key=os.path.abspath(path)
        cache=None if output else _CHECKED_INPUTS.get()
        previous=cache.get(key) if cache is not None else None
        if previous is not None and previous[0] == before:
            result = copy.deepcopy(previous[1])
        else:
            result = inspect_open_path(path, fd, output=output, pdf_scale=pdf_scale)
        if (inspection_identity(os.fstat(fd)) != before or
                inspection_identity(os.stat(path, follow_symlinks=False)) != before):
            raise RecipeError('Source changed during inspection; try again')
        # A hit already owns a detached result. Keep PSD and output checks fresh.
        if cache is not None and result[1] != 'psd' and (previous is None or previous[0] != before):
            cache[key] = (before, copy.deepcopy(result))
        return result
    finally:
        os.close(fd)


def inspect_open_path(path, fd, output=False, pdf_scale=1):
    stage('Reading image metadata')
    grouped = json.loads(run(['exiftool', '-json', '-G1', '-a', '-n', '-FileType', '-ImageWidth', '-ImageHeight',
                           '-Orientation', '-DateTimeOriginal', '-OffsetTimeOriginal', '-SubSecTimeOriginal',
                           '-CreateDate', '-ModifyDate', '-DateCreated', '-MajorBrand', '-AnimationIterations', '-'], source=path, fd=fd))[0]
    info = {key.split(':')[-1]:value for key,value in grouped.items()}
    # Keep date groups distinct: flattening XMP onto EXIF loses independent
    # clocks and passes XMP fractions/offsets to an EXIF-only parser.
    date_groups = {'ExifIFD:DateTimeOriginal': 'EXIF:DateTimeOriginal',
                   'ExifIFD:CreateDate': 'EXIF:CreateDate',
                   'IFD0:ModifyDate': 'EXIF:ModifyDate',
                   'XMP-exif:DateTimeOriginal': 'XMP-exif:DateTimeOriginal',
                   'XMP-photoshop:DateCreated': 'XMP-photoshop:DateCreated',
                   'XMP-xmp:CreateDate': 'XMP-xmp:CreateDate',
                   'XMP-xmp:ModifyDate': 'XMP-xmp:ModifyDate'}
    info['_date_fields'] = {tag: grouped[key] for key,tag in date_groups.items() if key in grouped}
    if 'IFD0:Orientation' in grouped: info['Orientation'] = grouped['IFD0:Orientation']
    info['_xmp_capture'] = grouped.get('XMP-exif:DateTimeOriginal')
    exif_capture = grouped.get('ExifIFD:DateTimeOriginal')
    if exif_capture is not None:
        info['DateTimeOriginal'] = exif_capture
        info['_capture_source'] = 'EXIF DateTimeOriginal'
    elif info.get('_xmp_capture'):
        info['DateTimeOriginal'] = info['_xmp_capture']
        info.pop('SubSecTimeOriginal',None);info.pop('OffsetTimeOriginal',None)
        info['_capture_source'] = 'XMP-exif DateTimeOriginal'
    if info.get('FileType') == 'HEIF': info['FileType'] = 'HEIC'
    if info.get('FileType') == 'Extended WEBP':
        info['FileType'] = 'WEBP'
    if info.get('FileType') == 'APNG':
        raise RecipeError('Animated PNG is unavailable in Recipes; use the existing animation menus.')
    allowed = ('JPEG', 'PNG', 'WEBP', 'AVIF', 'TIFF', 'BMP', 'PPM', 'HEIC', 'PSD', 'GIF', 'JP2', 'JXL') + (('PDF',) if output else ())
    if info.get('FileType') not in allowed:
        raise RecipeError('Unsupported input image format: ' + str(info.get('FileType')))
    if not output and info.get('AnimationIterations') is not None:
        raise RecipeError('Animated images are unavailable in Recipes; use the existing animation menus.')
    if not output and info.get('MajorBrand') in ('avis','msf1','hevs','hevm','heis'):
        raise RecipeError('Image sequences are unavailable in Recipes; select a single still image.')
    if not output and info.get('FileType') == 'WEBP':
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), 'rb') as stream:
            stream.read(12)
            while block := stream.read(8):
                if len(block) != 8: raise RecipeError('Truncated WebP')
                tag,length = struct.unpack('<4sI',block)
                if tag in (b'ANIM',b'ANMF'): raise RecipeError('Animated WebP is unavailable in Recipes; use the existing animation menus.')
                stream.seek(length + length % 2,1)
    if info.get('FileType') == 'PNG':
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(fd), 'rb') as stream:
            stream.read(8)
            while True:
                header = stream.read(8)
                if len(header) != 8:
                    raise RecipeError('Truncated PNG')
                length, tag = struct.unpack('>I4s', header)
                if tag in (b'acTL', b'fcTL', b'fdAT'):
                    raise RecipeError('Animated PNG is unavailable in Recipes v1')
                if tag == b'IEND':
                    break
                stream.seek(length + 4, 1)
    stage('Inspecting image dimensions')
    # Reject multiple frames/pages before any image execution.
    if output and info.get('FileType') == 'PDF':
        # identify ignores PDF density on some IM builds; the normal reader
        # honors it and supplies a complete decode for verification as well.
        frames = run(['magick','-density',str(72*pdf_scale),'-','-format','%m %w %h\n','info:'], source=path, fd=fd).splitlines()
    else:
        frames = run(['magick','identify','-ping','-format','%m %w %h\n',magick_input(info['FileType'])], source=path, fd=fd).splitlines()
    if len(frames) != 1:
        raise RecipeError('Only single-frame images are supported')
    fmt, width, height = frames[0].split()
    fmt = canonical_file_type(fmt)
    if fmt.upper() not in allowed:
        raise RecipeError('Unsupported input image format: ' + fmt)
    if output and info.get('FileType') == 'PDF':
        if int(width) % pdf_scale or int(height) % pdf_scale: raise RecipeError('PDF page dimensions disagree with its pixel canvas')
        width, height = int(width)//pdf_scale, int(height)//pdf_scale
    return info, ('psd' if info.get('FileType') == 'PSD' else fmt.lower()), int(width), int(height)


def cached_input_name_filters():
    return input_name_filters() if _input_name_filters.cache_info().currsize else None


def input_name_filters():
    """Browsing filters intersect the reader's whitelist with readable coders.

    No image is decoded here. PSB, raw JPEG 2000 codestreams and PGM/PBM are
    deliberately absent: the current content validator does not accept them.
    A missing capability listing safely leaves All Files and content inspection.
    """
    return list(_input_name_filters())


@lru_cache(maxsize=1)
def _input_name_filters():
    try:
        listing = run(['magick','-list','format'])
    except (OSError,RecipeError):
        from kim_process import checkpoint
        checkpoint()  # A cancelled probe must not cache an empty capability list.
        listing = ''
    readable = {p[0].rstrip('*') for line in listing.splitlines()
                if len(p := line.split()) >= 3 and 'r' in p[2]}
    groups = [
        ('JPEG Images',('JPEG',),('jpg','jpeg','jpe','jfif')),
        ('PNG Images',('PNG',),('png',)),
        ('WebP Images',('WEBP',),('webp',)),
        ('AVIF Images',('AVIF',),('avif',)),
        ('TIFF Images',('TIFF',),('tif','tiff')),
        ('HEIC / HEIF Images',('HEIC','HEIF'),('heic','heif')),
        ('BMP Images',('BMP',),('bmp',)),
        ('GIF Images',('GIF',),('gif',)),
        ('JPEG 2000 Images',('JP2',),('jp2',)),
        ('JPEG XL Images',('JXL',),('jxl',)),
        ('Photoshop Documents',('PSD',),('psd',)),
        ('Portable Pixmap Images',('PPM',),('ppm','pnm')),
    ]
    enabled = [(label,' '.join('*.'+ext for ext in extensions))
               for label,coders,extensions in groups if all(coder in readable for coder in coders)]
    return ['All Supported Images ('+' '.join(patterns for _,patterns in enabled)+')'] + [
        label+' ('+patterns+')' for label,patterns in enabled] + ['All Files (*)']


def canonical_file_type(value):
    return {'Extended WEBP':'WEBP','HEIF':'HEIC'}.get(value,value)


def capture_date(info):
    raw = info.get('DateTimeOriginal')
    if not raw:
        return None
    try:
        if len(raw) < 19 or raw[10] not in (' ','T'):
            raise ValueError('incomplete embedded date')
        # XMP-only capture dates may include fractions and an offset in the
        # value; EXIF keeps these in separate companion tags.
        value = dt.datetime.fromisoformat(raw[:10].replace(':','-') + raw[10:])
        offset = info.get('OffsetTimeOriginal')
        if offset:
            from kim_recipe_dates import timezone
            value = value.replace(tzinfo=timezone(offset))
        # Fractional precision is carried separately, including >6 digits.
        value = value.replace(microsecond=0)
        return value
    except ValueError as exc:
        raise RecipeError('The embedded image capture date is invalid or incomplete') from exc


def srgb_profile():
    for name in ('/usr/share/color/icc/sRGB.icc', '/usr/share/color/icc/ghostscript/srgb.icc',
                 '/usr/share/color/icc/colord/sRGB.icc'):
        if Path(name).is_file():
            return name
    raise RecipeError('sRGB ICC profile unavailable')


def planned_geometry(width, height, geometry):
    """Use the same bounded ImageMagick rounding in previews and execution."""
    if geometry.endswith('%'):
        ratio=int(geometry[:-1])/100
        return max(1,math.floor(width*ratio+.5)),max(1,math.floor(height*ratio+.5))
    import re
    if '@' in geometry:
        bound = int(geometry.split('@')[0])
    else:
        match = re.fullmatch(r'(\d*)x(\d*)([!^]?)([<>]?)',geometry)
        w,h,method,condition = match.groups()
        ratios = ([int(w)/width] if w else []) + ([int(h)/height] if h else [])
        ratio = max(ratios) if method == '^' else min(ratios)
        if condition == '>': ratio = min(1,ratio)
        if condition == '<': ratio = max(1,ratio)
        bound = int(w or width)*int(h or height) if method == '!' else math.ceil(width*ratio)*math.ceil(height*ratio)
    if bound > 100000000:
        raise RecipeError('Custom geometry exceeds the 100 megapixel safety limit. Choose smaller dimensions.')
    size = run(['magick','-limit','memory','256MiB','-limit','map','512MiB','-limit','disk','1GiB','-limit','thread','2','-size',f'{width}x{height}','xc:none','-resize',geometry,'-format','%w %h','info:'])
    width,height = map(int,size.split())
    return width,height


class ImageHandler:
    def operation_definitions(self):
        """Small UI contract owned by the media handler, including shared file steps."""
        choices = {'axis': ('horizontal', 'vertical'), 'preset': ('recommended', 'maximum', 'custom'),
                   'format': tuple(FORMATS), 'mode': ('preserve', 'srgb'), 'jp2_mode': ('lossless', 'lossy'),
                   'tiff_compression': ('zip', 'lzw', 'none'), 'depth': ('preserve', '8', '16'),
                   'grid': ('100', '1000', '5000', '10000')}
        limits = {'max_width': (1, 100000), 'max_height': (1, 100000),
                  'width': (1, 100000), 'height': (1, 100000), 'percent': (1, 1000), 'quality': (1, 100),
                  'seconds': (-315576000, 315576000), 'degrees': (-360, 360), 'png_level': (0, 9),
                  'start': (0, 1000000000), 'padding': (1, 18)}
        definitions = {}
        for op, original_defaults in DEFAULTS.items():
            defaults = dict(original_defaults)
            if op == 'image.convert': defaults.update(CONVERT_OPTIONS)
            parameters = {}
            for key, default in defaults.items():
                spec = {'default': default, 'type': 'text', 'label': {
                    'jp2_mode':'JPEG 2000 mode', 'tiff_compression':'TIFF compression', 'depth':'Output bit depth', 'jpeg_progressive':'Progressive JPEG',
                    'max_width': 'Maximum width', 'max_height': 'Maximum height',
                    'pattern':'Output filename pattern', 'upscale': 'Allow upscaling', 'creator': 'Creator / Artist',
                    'notice': 'Copyright notice', 'rights': 'Usage rights',
                    'datetime': 'Image capture date and time', 'timezone': 'Camera timezone', 'fields':'Date fields',
                    'grid': 'Approximate location grid (metres)',
                    'png_level':'PNG lossless compression level', 'jpeg_optimize':'Optimize JPEG Huffman coding',
                }.get(key, key.replace('_', ' ').capitalize())}
                if type(default) is bool:
                    spec['type'] = 'boolean'
                elif type(default) is int:
                    spec.update(type='integer', minimum=limits.get(key, (1, 100000))[0],
                                maximum=limits.get(key, (1, 100000))[1])
                if key in choices:
                    spec['choices'] = choices[key]
                parameters[key] = spec
            if op == 'metadata.shift_capture':
                parameters['fields'] = {'type': 'text', 'default': 'capture', 'choices': ('capture', 'all'), 'label': 'Date fields'}
            if op == 'image.rotate':
                parameters['degrees'].update(type='number', minimum=-360, maximum=360)
                parameters['condition'] = {'type': 'text', 'default': 'always', 'choices': ('always','landscape','portrait'), 'label': 'Apply to'}
            if op == 'metadata.set_capture':
                parameters['mode']['label'] = 'Date source'
                parameters['mode']['choices'] = ('specific', 'embedded', 'file_mtime')
                parameters['timezone']['choices'] = ('', 'unknown', 'embedded', 'UTC', 'custom')
                parameters['datetime']['type'] = 'capture_datetime'
                parameters['fields']['choices'] = ('capture', 'all')
            if op == 'image.overlay':
                parameters['opacity'].update(type='integer', minimum=0, maximum=100)
                parameters['size'].update(type='number', minimum=0.1, maximum=100.0)
                parameters['margin'].update(type='number', minimum=0.0, maximum=40.0)
                parameters['anchor']['choices'] = (
                    'top_left', 'top', 'top_right', 'left', 'center', 'right',
                    'bottom_left', 'bottom', 'bottom_right',
                )
                parameters['assistance']['choices'] = ('none', 'shadow', 'outline')
            if op == 'metadata.set_description':
                parameters['value']['label'] = 'Caption / Description'
            if op == 'metadata.set_keywords':
                parameters['mode']['label'] = 'Keyword handling'
                parameters['mode']['choices'] = ('unchanged', 'append', 'replace')
                parameters['keywords']['label'] = 'Keywords (comma or semicolon separated)'
            if op == 'file.name_transform':
                parameters['method']['choices'] = ('lowercase', 'uppercase', 'spaces_to_dashes', 'spaces_to_underscores', 'underscores_to_spaces', 'dashes_to_spaces', 'prefix', 'suffix', 'replace', 'sequential', 'capture_date')
            category = (CATEGORIES[3] if op.startswith('file.') or op in ('metadata.set_capture','metadata.shift_capture') else CATEGORIES[2] if op.startswith('metadata.')
                        else CATEGORIES[1] if op in ('image.convert', 'image.color', 'image.compress') else CATEGORIES[0])
            definitions[op] = {'label': LABELS[op], 'parameters': parameters, 'category': category,
                               'keywords': op.replace('.', ' ') + ' ' + ' '.join(parameters) + ' ' + {
                                   'image.flip':'mirror reflect horizontal vertical', 'image.color':'ICC colorspace sRGB',
                                   'file.preserve_date':'mtime modification timestamp', 'file.sync_date':'timestamp EXIF',
                                   'metadata.strip_all':'privacy EXIF IPTC XMP', 'metadata.reduce_gps':'gps location privacy approximate generalize grid coordinates', 'image.compress':'compression quality smaller recommended maximum custom JPEG PNG WebP AVIF',
                                   'metadata.set_description':'caption description text editorial iptc xmp alt language',
                                   'metadata.set_keywords':'keywords tags subject iptc xmp append replace editorial',
                                   'image.resize_long_edge':'resize longest edge aspect fit scale',
                                   'metadata.set_capture':'date timestamp EXIF capture camera clock mtime',
                                   'image.convert':'encode codec JPEG BMP GIF HEIC HEIF JP2 JPEG2000 JXL PDF TIFF WebP AVIF PNG'}.get(op,'')}
            if op in ('image.crop', 'image.overlay'):
                definitions[op]['editor'] = 'image_ops'
                definitions[op]['keywords'] += (' crop aspect ratio rectangle pixels selection' if op == 'image.crop' else ' watermark overlay text logo camera caption artist copyright')
                definitions[op]['category'] = CATEGORIES[0] if op == 'image.crop' else CATEGORIES[2]
                definitions[op]['description'] = ('Crop the oriented image, then optionally resize proportionally. Manual areas use relative coordinates on every image.' if op == 'image.crop' else 'Visible pixels, independent of embedded rights metadata. Place after all geometry and color steps; missing embedded fields are omitted.')
            if op == 'image.convert':
                definitions[op]['description'] = 'Changes the output file format (such as JPEG, PNG, WebP or AVIF) with one output per input. JPEG/BMP/PDF/HEIC use white backgrounds; GIF uses palette transparency. JPEG/WebP/AVIF quality can inherit KIMng Web Export Settings or use an override. Use Compress Image to adjust compression without changing format.'
                definitions[op]['parameters']['quality'].update(settings_key='Web Export quality',settings_field='quality')
            if op == 'image.resize_exact': definitions[op]['description'] = 'Sets both dimensions exactly; the image may stretch.'
            descriptions = {
                'image.auto_orient': 'Rotates pixels to match the camera orientation tag and clears the orientation flag.',
                'image.flip': 'Mirrors the image horizontally (left to right) or vertically (top to bottom).',
                'image.resize': 'Fits the image within maximum width and height limits while keeping its aspect ratio. Use Resize Long Edge when you only want one pixel limit.',
                'image.resize_percent': 'Scales both width and height by a percentage of the current dimensions.',
                'image.resize_long_edge': 'Scales the longest side to a single pixel target while keeping the aspect ratio. Use Resize to Fit when width and height need separate limits.',
                'image.color': 'Converts to sRGB for web viewing, preserves the embedded ICC profile, or strips color profiles.',
                'image.compress': 'Adjusts final output compression without changing format. Recommended: quality 85 / PNG level 6; Maximum: quality 70 / PNG level 9; Custom exposes quality, PNG level and JPEG options. Use Convert Format to change file format.',
                'metadata.strip_all': 'Removes all EXIF, IPTC, XMP and camera metadata for privacy while keeping image pixels.',
                'metadata.strip_gps': 'Removes GPS coordinates and location tags while keeping other camera and descriptive metadata.',
                'metadata.reduce_gps': 'Replaces exact GPS coordinates with the center of an approximate WGS84 grid cell (100 m, 1 km, 5 km or 10 km) and clears altitude, direction, destination coordinates, structured location blocks and place-name tags. Does not remove location clues in captions or image pixels.',
                'metadata.set_description': 'Sets the embedded caption or description (XMP-dc:Description and IPTC:Caption-Abstract) while preserving unrelated metadata and non-default XMP language alternatives. Leaving the value blank keeps existing descriptions unchanged.',
                'metadata.set_keywords': 'Updates embedded IPTC and XMP keywords (XMP-dc:Subject and IPTC:Keywords). Choose Leave unchanged, Append (adds unique entries to existing keywords) or Replace. Separate multiple keywords with commas or semicolons.',
                'metadata.strip_ai': 'Removes IPTC AI generation prompt and system tags while keeping other metadata.',
                'metadata.set_capture': 'Enter when the image was captured, use its embedded date, or use its file modification time (which may reflect copying). Choose Unknown if you do not know the camera timezone. All dates also sets embedded creation and modification dates. File timestamps change only with Synchronize File Date.',
                'metadata.shift_capture': 'Advanced: adjust an existing capture clock by days, hours, minutes and seconds. Use Set Image Capture Date for a missing date. All also shifts existing EXIF creation/modification dates. Camera timezone and fractional seconds are retained.',
                'metadata.strip_descriptive': 'Remove descriptive EXIF/IPTC/XMP while keeping the ICC profile and orientation. Image capture dates and copyright are removed. Add new date or rights steps afterwards if needed.',
                'file.name_transform': 'Transforms the current planned output filename (without extension) using case change, prefix, suffix, find/replace or numbering. Use Rename Output File for {filename}, {date}, {index} or Recipe question templates.',
                'file.rename_output': 'Replaces the output filename using a template with {filename}, {date}, {index} or Recipe questions. Use Change Output Filename to transform the existing name (case, prefix, suffix or find/replace).',
                'file.sync_date': 'Sets the output file modification time to match the image capture date (EXIF DateTimeOriginal). Use Keep Source File Date to copy the original file modification time instead.',
                'file.preserve_date': 'Copies the original file modification time onto the output file. Use Synchronize File Date to match the embedded capture date instead.',
                'image.rotate': 'Rotate the displayed image; orientation is baked into pixels. Custom angles use a transparent background (white in opaque output formats).',
                'image.resize_geometry': 'ImageMagick geometry: WIDTHxHEIGHT fits, ! stretches, ^ fills without cropping, > only shrinks, < only enlarges. Width-only (1600x), height-only (x1200), and maximum pixel area (1000000@) are allowed. Use Resize by Percentage for percentages.',
            }
            if op in descriptions: definitions[op]['description'] = descriptions[op]
            if op in SETTING_FIELDS:
                definitions[op]['parameters'] = {'value': {
                    'type': 'text', 'default': None, 'settings_key': SETTING_KEYS[SETTING_FIELDS[op]], 'settings_field': SETTING_FIELDS[op],
                    'label': LABELS[op].removeprefix('Set ')}}
                field_desc = {
                    'metadata.creator': 'Sets only the creator / artist tag. Defaults to KIMng Settings; typing creates a recipe-specific override. Use Set Copyright to manage all rights fields together.',
                    'metadata.copyright_notice': 'Sets only the copyright notice tag. Defaults to KIMng Settings; typing creates a recipe-specific override. Use Set Copyright to manage creator, notice, rights and year together.',
                    'metadata.usage_rights': 'Sets only the usage rights tag. Defaults to KIMng Settings; typing creates a recipe-specific override. Use Set Copyright to manage all rights fields together.',
                }
                definitions[op]['description'] = field_desc.get(op, 'Defaults to KIMng Settings. Typing creates a recipe-specific override.')
            if op == 'metadata.copyright':
                for key, spec in definitions[op]['parameters'].items():
                    spec.update(settings_key=SETTING_KEYS[key], settings_field=key)
                definitions[op]['parameters']['year'] = {'type':'text','default':'','label':'Copyright year (blank = capture year)'}
                definitions[op]['description'] = 'Sets creator, copyright notice, usage rights and year together in one step. Each field can inherit KIMng Settings or use an override; a blank override leaves that field unchanged.'
        return copy.deepcopy(definitions)

    def step_label(self, step):
        op = step['op']
        label = LABELS.get(op, op)
        if op == 'image.crop':
            return label + ': ' + step['aspect'] + ', ' + step['area'] + ('; target ' + str(step['target_width']) + ' × ' + str(step['target_height']) if step['resize'] else '')
        if op == 'image.overlay':
            from kim_image_ops import KINDS
            return label + ': ' + dict((value, title) for title, value in KINDS)[step['kind']] + ', ' + step['anchor'].replace('_', ' ') + ', ' + str(step['opacity']) + '%'
        if op == 'image.resize':
            return f"{label}: {step['max_width']} × {step['max_height']}"
        if op == 'image.convert':
            fmt = step['format']
            try: quality_label = str(self.parameter_value(step,'quality')) + ' (Settings)' if step['quality'] is None else str(step['quality'])
            except (OSError,RecipeError): quality_label = 'Settings unavailable'
            detail = ('lossless' if fmt == 'jp2' and step.get('jp2_mode','lossless') == 'lossless' else
                      step.get('tiff_compression','zip').upper() if fmt == 'tiff' else
                      'single page, 8-bit' if fmt == 'pdf' else '8-bit' if fmt == 'bmp' else
                      'single frame, palette' if fmt == 'gif' else 'lossless' if fmt == 'png' else
                      'quality ' + quality_label)
            return label + ': ' + fmt.upper() + ', ' + detail
        if op == 'image.compress': return label + ': ' + step['preset'].capitalize()
        if op == 'metadata.set_capture': return label + ': ' + {'specific':step.get('datetime') or 'choose date and time', 'embedded':'embedded date', 'file_mtime':'source file modification time'}.get(step['mode'],'choose source')
        if op == 'metadata.shift_capture': return label + ': ' + str(dt.timedelta(seconds=step['seconds']))
        if op == 'metadata.reduce_gps':
            grid_labels = {'100': '~100 m grid', '1000': '~1 km grid', '5000': '~5 km grid', '10000': '~10 km grid'}
            return label + ': ' + grid_labels.get(str(step.get('grid', '1000')), str(step.get('grid', '1000')) + ' m grid')
        if op == 'metadata.set_description':
            val = (step.get('value') or '').strip()
            if not val:
                return label + ': leave unchanged'
            snippet = val if len(val) <= 36 else val[:35] + '…'
            return label + ': ' + snippet
        if op == 'metadata.set_keywords':
            mode = step.get('mode', 'unchanged')
            mode_label = {'unchanged': 'leave unchanged', 'append': 'append', 'replace': 'replace'}.get(mode, mode)
            kws = parse_keywords(step.get('keywords', ''))
            if mode == 'unchanged' or not kws:
                return label + ': ' + mode_label
            return f"{label}: {mode_label} ({len(kws)})"
        if op == 'image.color':
            return label + ': ' + ('sRGB' if step['mode'] == 'srgb' else 'Preserve')
        if op == 'image.resize_percent':
            return f"{label}: {step['percent']}%"
        return label

    def parameter_value(self, step, key, settings=None):
        spec = self.operation_definitions()[step['op']]['parameters'][key]
        if step['op'] == 'image.convert' and key == 'quality' and step.get(key) is None:
            return inherited_quality(step['format'])
        if spec.get('settings_key') and step.get(key) is None:
            settings = copyright_settings() if settings is None else settings
            return settings[spec['settings_field']]
        return copy.deepcopy(step.get(key, spec['default']))

    def validate_context(self, steps):
        for step in enabled_steps(steps):
            if step['op'] == 'metadata.set_capture' and step['mode'] == 'specific' and not step['datetime']:
                raise RecipeError('Choose an image capture date and time to continue.')
            if step['op'] == 'image.overlay' and step['kind'] == 'text':
                from kim_image_ops import watermark_text
                watermark_text(step)
            if step['op'] == 'image.overlay' and step['kind'] == 'camera':
                from kim_image_ops import validate_camera_selection
                validate_camera_selection(step)
        active = [s for s in enabled_steps(steps) if s['op'] in SETTING_FIELDS or s['op'] == 'metadata.copyright']
        settings = copyright_settings() if any(any(s.get(k) is None for k in self.operation_definitions()[s['op']]['parameters']) for s in active) else {}
        for step in active:
            if step['op'] in SETTING_FIELDS and step.get('value') is None and not self.parameter_value(step, 'value', settings).strip():
                raise RecipeError(LABELS[step['op']] + ' has no inherited Settings value. Enter an override or set KIMng Settings.')
            if step['op'] == 'metadata.copyright' and any(step.get(k) is None for k in COPYRIGHT_TAGS) and not any(self.parameter_value(step,k,settings).strip() for k in COPYRIGHT_TAGS):
                raise RecipeError('Set Copyright requires at least one nonempty value from Settings or an override.')
        return settings

    def source_properties(self, source):
        info, fmt, width, height = inspect(source)
        if info.get('Orientation', 1) in (5, 6, 7, 8):
            width, height = height, width
        return {'original_display_width': width, 'original_display_height': height,
                'source_format': fmt, 'original_orientation': info.get('Orientation')}

    def operation_details(self, step):
        definition = self.operation_definitions()[step['op']]
        if step['op'] in ('image.crop', 'image.overlay'):
            from kim_image_ops import step_details
            return definition['label'], step_details(step)
        details = []
        for key, spec in definition['parameters'].items():
            try:
                value = self.parameter_value(step, key)
                if step['op']=='file.rename_output' and key=='pattern': value=display_output_pattern(value)
                if spec['type'] == 'boolean':
                    value = 'Yes' if value else 'No'
                elif value is None or value == '':
                    value = 'Not included: enter a value in Recipe Editor'
                if spec.get('settings_key'):
                    value = str(value) + (' (inherited from Settings)' if step.get(key) is None else ' (recipe override)')
            except (OSError, RecipeError) as exc:
                value = 'Unavailable: ' + str(exc)
            details.append((spec.get('label', key), str(value)))
        return definition['label'], details

    def preview_fields(self, row):
        p = row.properties
        original = f"{p.get('original_display_width', p.get('original_width', '?'))} × {p.get('original_display_height', p.get('original_height', '?'))} pixels"
        fields = [('Original dimensions', original)]
        if row.problems:
            if p.get('source_format'):
                fields.append(('Source format', p['source_format'].upper()))
            return fields
        fields += [('Final format', row.format.upper()),
                   ('Quality', str(p['quality']) if p.get('quality') is not None else 'Not set by enabled steps'),
                   ('Output dimensions', f"{p.get('display_width', p.get('width', '?'))} × {p.get('display_height', p.get('height', '?'))} pixels (planned)")]
        if p.get('compression'): fields.append(('Compression',p['compression']))
        fields += [('Crop geometry', value) for value in p.get('crops', [])]
        fields += [('Visible overlay', value) for value in p.get('overlays', [])]
        names = {tag: LABELS['metadata.' + {'creator': 'creator', 'notice': 'copyright_notice', 'rights': 'usage_rights'}[field]].removeprefix('Set ') + ' (' + tag.split(':')[0] + ')'
                 for field, tags in COPYRIGHT_TAGS.items() for tag in tags}
        for line in row.metadata:
            key, _, value = line.partition(': ')
            if key == 'Output timestamp':
                key = 'File modified'
                if value == 'execution time (not predetermined)':
                    value = 'When exported'
            elif key == 'GPS':
                value = ('Removed (recognized fields)' if p.get('strip_gps') else 'None detected (recognized fields)') if value.startswith('absent') else 'Preserved (recognized fields present)'
            elif key == 'AI fields' and value.startswith('absent'):
                value = ('Removed (recognized fields)' if p.get('strip_ai') or p.get('strip_all') else 'None detected (recognized fields)') + '; other provenance may remain'
            elif key == 'ICC':
                if value == 'absent in input':
                    value = 'Not included: no input profile detected'
                elif value == 'absent (ICC stripped)':
                    value = 'Removed'
                else:
                    value = value.replace('stripped', 'removed')
            elif key == 'Orientation' and value.startswith('absent'):
                value = 'Normal display (no orientation tag)'
            elif key == 'Orientation' and value == '1':
                value = 'Normal display (orientation 1)'
            elif value == 'absent':
                value = 'Removed' if p.get('strip_all') else 'Not included'
            fields.append((names.get(key, key), value))
        return fields

    def validate_step(self, step):
        op = step.get('op')
        if op not in DEFAULTS or not op.startswith(('image.', 'metadata.','file.')):
            raise RecipeError('Unknown image operation: ' + str(op))
        if op in ('image.crop', 'image.overlay'):
            from kim_image_ops import validate_crop, validate_overlay
            (validate_crop if op == 'image.crop' else validate_overlay)(step)
            return
        required = tuple(DEFAULTS[op])
        optional = ('enabled',)
        if op in SETTING_FIELDS:
            optional += ('value',)
        if op == 'image.convert': optional += tuple(CONVERT_OPTIONS)
        if op == 'image.rotate': optional += ('condition',)
        if op == 'metadata.shift_capture': optional += ('fields',)
        if op == 'metadata.copyright':
            required, optional = (), ('creator', 'notice', 'rights', 'year', 'enabled')
        keys(step, ('op',) + required, optional)
        if op in SETTING_FIELDS and step.get('value') is not None:
            text(step['value'])
        if op == 'image.rotate':
            if type(step['degrees']) not in (int, float) or not math.isfinite(step['degrees']) or not -360 <= step['degrees'] <= 360:
                raise RecipeError('Rotation must be between −360 and 360 degrees')
            if step.get('condition', 'always') not in ('always','landscape','portrait'): raise RecipeError('Invalid rotation condition')
        if op == 'image.flip' and step['axis'] not in ('horizontal', 'vertical'):
            raise RecipeError('Invalid flip axis')
        if op == 'image.resize':
            integer(step['max_width'], 1, 100000); integer(step['max_height'], 1, 100000)
            if type(step['upscale']) is not bool:
                raise RecipeError('upscale must be boolean')
        if op == 'image.resize_exact':
            integer(step['width'], 1, 100000); integer(step['height'], 1, 100000)
        if op == 'image.resize_percent':
            integer(step['percent'], 1, 1000)
        if op == 'image.resize_long_edge':
            integer(step['pixels'], 1, 100000)
            if type(step['upscale']) is not bool: raise RecipeError('upscale must be boolean')
        if op == 'image.resize_geometry':
            import re
            value = step['geometry']
            if not isinstance(value,str) or not re.fullmatch(r'(?:(?:[1-9]\d{0,4}x[1-9]\d{0,4}|[1-9]\d{0,4}x|x[1-9]\d{0,4})(?:[!^])?|[1-9]\d{0,8}@)[<>]?',value):
                raise RecipeError('Enter bounded resize geometry such as 1600x1200>, 1600x, x1200 or 1600x1200!.')
        if op == 'image.compress':
            if step['preset'] not in ('recommended','maximum','custom'): raise RecipeError('Choose a compression preset')
            integer(step['quality'], 1, 100); integer(step['png_level'], 0, 9)
            for key in ('jpeg_progressive','jpeg_optimize'):
                if type(step[key]) is not bool: raise RecipeError(key + ' must be boolean')
        if op == 'image.convert':
            if not isinstance(step['format'], str) or step['format'] not in FORMATS:
                raise RecipeError('Unsupported output format')
            if step['quality'] is not None: integer(step['quality'], 1, 100)
            elif step['format'] in ('heic','heif','jxl') or (step['format'] == 'jp2' and step.get('jp2_mode') == 'lossy'):
                raise RecipeError('KIMng Settings has no quality default for ' + step['format'].upper() + '. Enter a quality override.')
            for key, choices in (('jp2_mode', ('lossless','lossy')), ('tiff_compression', ('zip','lzw','none')), ('depth', ('preserve','8','16'))):
                if step.get(key, CONVERT_OPTIONS[key]) not in choices: raise RecipeError('Invalid conversion ' + key)
            if type(step.get('jpeg_progressive', False)) is not bool: raise RecipeError('jpeg_progressive must be boolean')
            if type(step.get('jpeg_optimize', False)) is not bool: raise RecipeError('jpeg_optimize must be boolean')
            if step.get('depth') == '16' and step['format'] not in ('png','tiff','jp2'):
                raise RecipeError('16-bit output is available for PNG, TIFF and JPEG 2000')
        if op == 'image.color' and step['mode'] not in ('preserve', 'srgb'):
            raise RecipeError('Unsupported color mode')
        if op == 'metadata.reduce_gps' and str(step['grid']) not in ('100', '1000', '5000', '10000'):
            raise RecipeError('Choose a supported GPS precision grid (100, 1000, 5000 or 10000 metres).')
        if op == 'metadata.set_description':
            text(step['value'])
        if op == 'metadata.set_keywords':
            if step['mode'] not in ('unchanged', 'append', 'replace'):
                raise RecipeError('Choose a supported keyword handling mode (unchanged, append or replace).')
            text(step['keywords'])
        if op == 'metadata.copyright':
            for key, value in step.items():
                if key != 'enabled' and value is not None:
                    text(value)
            year = step.get('year','')
            if year and (not year.isascii() or not year.isdigit() or len(year) != 4 or year == '0000'):
                raise RecipeError('Copyright year must be four digits, or blank to use the capture year.')
        if op == 'metadata.shift_capture':
            integer(step['seconds'], -315576000, 315576000)
            if step.get('fields','capture') not in ('capture','all'): raise RecipeError('Invalid date fields')
        if op == 'metadata.set_capture':
            from kim_recipe_dates import specific, timezone
            text(step['datetime']); text(step['timezone'])
            if step['mode'] not in ('specific','embedded','file_mtime'): raise RecipeError('Choose the image capture date source')
            if step['fields'] not in ('capture','all'): raise RecipeError('Choose capture or all date fields')
            if step['mode'] == 'specific':
                # Empty is a serializable draft, never a processing default.
                if step['datetime']: specific(step['datetime'], step['timezone'])
            elif step['timezone'] != 'embedded' or step['mode'] == 'file_mtime': timezone(step['timezone'])
            if step['mode'] == 'file_mtime' and step['timezone'] == 'unknown': raise RecipeError('Choose UTC or an explicit offset to interpret the source file modification time.')
        if op == 'file.name_transform':
            if step['method'] not in self.operation_definitions()[op]['parameters']['method']['choices']: raise RecipeError('Invalid filename method')
            text(step['value'], 180); text(step['replacement'], 180)
            integer(step['start'], 0, 1000000000); integer(step['padding'], 1, 18)
            if step['method'] == 'replace' and not step['value']: raise RecipeError('Enter the filename text to replace')

    def validate_order(self, steps):
        metadata_step = None
        overlay_seen = False
        declarations = set()
        for step in enabled_steps(steps):
            op = step['op']
            if overlay_seen and (op in ('image.crop', 'image.rotate', 'image.flip', 'image.auto_orient', 'image.color') or op.startswith('image.resize')):
                raise RecipeError('Move ' + LABELS[op] + ' before Add Watermark / Overlay; overlays must use final image geometry and color.')
            if op == 'image.overlay': overlay_seen = True
            if op in ('image.convert', 'image.compress'):
                if op in declarations:
                    raise RecipeError('Multiple Convert Format steps conflict. Keep one final output format.' if op == 'image.convert' else
                                      'Keep only one compression step; Compress Image selects the final encoder settings.')
                declarations.add(op)
                # Container and encoder options are declarations, not pixel work.
                # Retain the established metadata boundary: a later Convert may
                # change which earlier metadata assignments can be represented.
                if op == 'image.convert' and metadata_step:
                    raise RecipeError('Move Convert Format above ' + LABELS[metadata_step] + '.')
                continue
            if op.startswith('metadata.') and op != 'metadata.shift_capture':
                metadata_step = metadata_step or op
            if op.startswith('image.') and metadata_step:
                raise RecipeError('Move ' + LABELS[op] + ' above ' + LABELS[metadata_step] +
                                  '; pixel processing must precede ordered metadata edits.')

    def plan(self, source, steps, index, stem=None):
        from kim_recipe_dates import specific, explicit, timezone, assignments, display
        stage('Validating recipe')
        # Error locations refer to the editor's numbered list, including
        # disabled entries; only enabled steps affect working state.
        numbered_steps = [(number,step) for number,step in enumerate(steps,1) if step.get('enabled',True)]
        steps = [step for _,step in numbered_steps]
        settings = self.validate_context(steps)

        omit_source_metadata = (
            _OMIT_STANDALONE_OVERLAY_METADATA.get()
        )
        # Only the private retry may omit inherited metadata.
        # The initial Crop attempt preserves metadata normally.
        omit_source_metadata = (
            omit_source_metadata or _CROP_CLEAN_RETRY.get()
        )
        if _OMIT_STANDALONE_OVERLAY_METADATA.get():
            active = [s["op"] for s in steps]
            if (
                active.count("image.overlay") != 1
                or any(
                    op.startswith("metadata.")
                    for op in active
                )
            ):
                raise RecipeError(
                    "Metadata-free watermark mode requires "
                    "one overlay and no metadata-editing steps."
                )

        if _CROP_CLEAN_RETRY.get():
            active = [s["op"] for s in steps]
            if (
                active.count("image.crop") != 1
                or "image.overlay" in active
                or any(op.startswith("metadata.") for op in active)
            ):
                raise RecipeError(
                    "Metadata-free Crop retry requires one crop "
                    "and no explicit metadata-editing steps."
                )

        info, fmt, width, height = inspect(source)
        stage('Checking recipe operations')
        orientation_tag = info.get('Orientation')
        orientation = orientation_tag or 1
        date_warnings = []; capture_problem = None
        try: capture = capture_date(info)
        except RecipeError as exc:
            capture = None
            capture_problem = str(exc)
            date_warnings.append(str(exc) + '. Choose Set Image Capture Date to replace this invalid embedded date.')
        logical_capture = capture
        fraction = str(info.get('SubSecTimeOriginal', '')) if capture else ''
        if capture and not fraction and '.' in str(info.get('DateTimeOriginal','')):
            import re
            found = re.search(r'\.(\d+)',info['DateTimeOriginal'])
            fraction = found.group(1) if found else ''
        date_source = info.get('_capture_source','embedded image capture date') if capture else 'no usable embedded image capture date'
        if capture and info.get('_xmp_capture') and info.get('_capture_source') == 'EXIF DateTimeOriginal' and any(s['op'] == 'metadata.shift_capture' or (s['op'] == 'metadata.set_capture' and s['mode'] == 'embedded') for s in steps):
            try: xmp_capture = capture_date({'DateTimeOriginal':info['_xmp_capture']})
            except RecipeError: xmp_capture = None
            if xmp_capture != capture:
                date_warnings.append('EXIF DateTimeOriginal and XMP-exif DateTimeOriginal disagree (possibly in timezone). Embedded mode uses EXIF. Enter a specific image capture date/time to replace both.')
        removed_at = None
        working_dates = dict(info.get('_date_fields', {}))
        original_width, original_height = width, height
        srgb_pixels = False
        name = (stem if stem is not None else source.stem) + '_recipe'
        pixel_args, edits = [], []
        crop_descriptions, overlays = [], []
        conversion = next((s for s in steps if s['op'] == 'image.convert'), None)
        compression = next((s for s in steps if s['op'] == 'image.compress'), None)
        if conversion: fmt = conversion['format']
        if compression and fmt not in ('jpeg','png','webp','avif'):
            raise RecipeError('Compress Image supports JPEG, PNG, WebP and AVIF. Choose one of these in Convert Format or disable Compress Image.')
        copyright_values, gps_present, ai_values, source_profile = planning_metadata(source, psd=info.get('FileType') == 'PSD')
        gps_state = 'present (recognized fields)' if gps_present else 'absent (recognized fields)'
        ai_present = {tag: value for tag, value in ai_values.items() if value is not None}
        ai_state = ('preserved ' + json.dumps(ai_present, ensure_ascii=False) if ai_present else 'absent (recognized fields)') + '; unrecognized provenance unknown'
        icc = source_profile.get('ProfileDescription')
        color_state = 'preserved ' + str(icc) if icc is not None else 'absent in input'
        if info.get('FileType') == 'PSD':
            color_state = 'PSD decoded profile: ' + (str(icc) if icc else 'unavailable')
            document = psd_header(source)
            if document is None: raise RecipeError('Source changed during inspection; try again')
            if document[3] in (1, 4):
                color_state += '; normalized to sRGB before image operations'
        color_record = run(['magick','identify','-ping','-format','%[colorspace]|%z',magick_input(info['FileType'])], source=source).strip().lower()
        colorspace, source_depth = color_record.split('|')
        source_depth = int(source_depth)
        timestamp_state = 'execution time (not predetermined)'
        quality, timestamp, timestamp_ns = None, None, None
        auto_oriented = False
        gps_reduce_args = None
        approved_gps_reduction = None
        gps_reduce_warnings = []
        has_desc_ops = any(s['op'] in ('metadata.set_description', 'metadata.set_keywords') for s in steps)
        desc_info = read_descriptive_metadata(source) if has_desc_ops else None
        expected_description = None
        expected_keywords = None
        desc_state = None
        kw_state = None
        for step_number, step in numbered_steps:
            op = step['op']
            if op in ('image.rotate', 'image.flip', 'image.crop', 'image.overlay'):
                # Explicit transforms act on the displayed image and bake orientation into pixels.
                pixel_args += ['-auto-orient']
                if orientation in (5, 6, 7, 8):
                    width, height = height, width
                orientation = 1
                orientation_tag = 1
                auto_oriented = True
            if op == 'image.auto_orient':
                pixel_args += ['-auto-orient']
                if orientation in (5, 6, 7, 8):
                    width, height = height, width
                orientation = 1
                orientation_tag = 1
                auto_oriented = True
            elif op == 'image.rotate':
                apply = (step.get('condition','always') == 'always' or
                         step.get('condition') == ('landscape' if width > height else 'portrait' if height > width else 'square'))
                if apply:
                    rotation = ['-background','none','-rotate',str(step['degrees']),'+repage']
                    # Let the installed IM engine compute arbitrary-angle canvas
                    # rounding without decoding the source a second time.
                    if step['degrees'] % 90 == 0:
                        if step['degrees'] % 180: width,height = height,width
                    else:
                        size = run(['magick','-size',f'{width}x{height}','xc:none',*rotation,'-format','%w %h','info:'])
                        width, height = map(int,size.split())
                    pixel_args += rotation
            elif op == 'image.flip':
                pixel_args += ['-flop' if step['axis'] == 'horizontal' else '-flip']
            elif op == 'image.crop':
                from kim_image_ops import crop_plan
                crop = crop_plan(width, height, step)
                pixel_args += crop['args']
                crop_descriptions.append(f"{crop['width']} × {crop['height']} at ({crop['x']}, {crop['y']}) → {crop['output_width']} × {crop['output_height']} pixels")
                width, height = crop['output_width'], crop['output_height']
            elif op == 'image.overlay':
                from kim_image_ops import overlay_plan
                overlays.append(overlay_plan(source, width, height, step))
            elif op in ('image.resize','image.resize_long_edge'):
                max_width = step['pixels'] if op == 'image.resize_long_edge' else step['max_width']
                max_height = step['pixels'] if op == 'image.resize_long_edge' else step['max_height']
                ratio = min(max_width / width, max_height / height)
                if not step['upscale']:
                    ratio = min(ratio, 1)
                width, height = max(1, math.floor(width * ratio + .5)), max(1, math.floor(height * ratio + .5))
                pixel_args += ['-resize', f'{max_width}x{max_height}' + ('' if step['upscale'] else '>')]
            elif op == 'image.resize_exact':
                width, height = step['width'], step['height']
                pixel_args += ['-resize', f'{width}x{height}!']
            elif op == 'image.resize_percent':
                ratio = step['percent'] / 100
                width, height = max(1, math.floor(width * ratio + .5)), max(1, math.floor(height * ratio + .5))
                pixel_args += ['-resize', str(step['percent']) + '%']
            elif op == 'image.resize_geometry':
                width,height=planned_geometry(width,height,step['geometry'])
                pixel_args += ['-resize',step['geometry']]
            elif op == 'image.color' and step['mode'] == 'srgb':
                if 'cmyk' in colorspace and not source_profile:
                    raise RecipeError('Unprofiled CMYK has unknown source colors; supply a valid source ICC profile')
                if not source_profile and colorspace in ('gray','lineargray'):
                    pixel_args += ['-colorspace','sRGB']
                pixel_args += ['-profile', srgb_profile()]
                color_state = 'sRGB ICC'
                srgb_pixels = True
            elif op in ('image.convert','image.compress'):
                pass  # Resolved once below; visible order never adds an intermediate encode.
            elif op == 'metadata.set_capture':
                if step['mode'] == 'specific':
                    capture, fraction = explicit(step['datetime'],step['timezone'])
                    date_source = 'entered date and time'
                elif step['mode'] == 'file_mtime':
                    ns = source.stat().st_mtime_ns
                    capture = dt.datetime.fromtimestamp(ns // 1000000000, timezone(step['timezone']))
                    fraction = f'{ns % 1000000000:09d}'.rstrip('0')
                    date_source = 'source file modification time (may reflect copying rather than capture)'
                else:
                    if capture is None:
                        if capture_problem and not removed_at:
                            raise RecipeError(capture_problem + '. Enter a specific date/time above or use the source file modification time.')
                        reason = (f'Step {removed_at} removes capture metadata before Step {step_number}. Enter a specific date here, use source file modification time, or move this step before Step {removed_at}.' if removed_at else
                                  f'This {info["FileType"]} has no embedded image capture date. Choose a specific date above or use its file modification time.')
                        raise RecipeError(reason)
                    if step['timezone'] != 'embedded': capture = capture.replace(tzinfo=timezone(step['timezone']))
                    date_source = 'working embedded image capture date'
                logical_capture = capture
                date_edits = assignments(capture, fraction, step['fields'], fmt not in NO_LEGACY_IPTC)
                working_dates.update(edit[1:].split('=',1) for edit in date_edits
                                     if edit[1:].split('=',1)[0] in (
                                         'EXIF:DateTimeOriginal','EXIF:CreateDate','EXIF:ModifyDate',
                                         'XMP-exif:DateTimeOriginal','XMP-photoshop:DateCreated',
                                         'XMP-xmp:CreateDate','XMP-xmp:ModifyDate'))
                edits.append(date_edits)
            elif op == 'metadata.shift_capture':
                if capture is None:
                    if removed_at:
                        raise RecipeError(f'Step {removed_at} removes capture metadata before Step {step_number} tries to adjust it. Set a specific date at Step {step_number}, or move the adjustment before Step {removed_at}.')
                    if capture_problem:
                        raise RecipeError(capture_problem + '. Add Set Image Capture Date to replace it before Adjust Image Capture Date.')
                    raise RecipeError(f'This {info["FileType"]} has no embedded image capture date. Add Set Image Capture Date to enter a date or use its file modification time before Adjust Image Capture Date.')
                try:
                    capture += dt.timedelta(seconds=step['seconds'])
                except OverflowError as exc:
                    raise RecipeError('Image Capture Date out of range') from exc
                logical_capture = capture
                date_source += '; adjusted by ' + str(dt.timedelta(seconds=step['seconds']))
                date_edits = assignments(capture, fraction, 'capture', fmt not in NO_LEGACY_IPTC)
                shifted_dates = {}
                for tag,raw in working_dates.items():
                    if step.get('fields','capture') != 'all' and tag.split(':')[-1] not in ('DateTimeOriginal','DateCreated'):
                        continue
                    try:
                        # Shift the whole-second wall clock only. Retaining the
                        # suffix verbatim preserves XMP precision and its zone;
                        # EXIF's companion subsecond/offset tags stay untouched.
                        value = dt.datetime.strptime(raw[:19].replace('T',' '),'%Y:%m:%d %H:%M:%S') + dt.timedelta(seconds=step['seconds'])
                    except (ValueError, OverflowError) as exc:
                        raise RecipeError('Cannot adjust invalid ' + tag) from exc
                    shifted_dates[tag] = f'{value.year:04d}:' + value.strftime('%m:%d %H:%M:%S') + raw[19:]
                working_dates.update(edit[1:].split('=',1) for edit in date_edits
                                     if edit.startswith(('-EXIF:DateTimeOriginal=', '-XMP-exif:DateTimeOriginal=', '-XMP-photoshop:DateCreated=')))
                working_dates.update(shifted_dates)
                edits.append(date_edits + ['-' + tag + '=' + value for tag,value in shifted_dates.items()])
            elif op in ('metadata.strip_all','metadata.strip_descriptive'):
                if op == 'metadata.strip_all' and orientation != 1:
                    raise RecipeError('metadata.strip_all requires normalized orientation: add an earlier image.auto_orient, image.rotate, or image.flip step. Removing the orientation tag alone would change the displayed image; Recipes will not silently re-encode it.')
                capture = None
                fraction = ''; removed_at = step_number
                date_source = 'removed at Step ' + str(step_number)
                working_dates.clear()
                edits.append(['-all='] if op == 'metadata.strip_all' else ['-EXIF:all=','-IPTC:all=','-XMP:all=', '-EXIF:Orientation#=' + str(orientation)])
                copyright_values = dict.fromkeys(copyright_values)
                gps_state = 'absent (recognized fields)'
                ai_state = 'absent (recognized writable fields); unrecognized provenance unknown'
                if desc_info is not None:
                    desc_info = {'xmp_description': None, 'iptc_description': None, 'lang_alts': {},
                                 'xmp_keywords': [], 'iptc_keywords': [], 'keywords': []}
                expected_description = None
                expected_keywords = None
                desc_state = None
                kw_state = None
                if op == 'metadata.strip_all':
                    color_state = 'sRGB pixels; ICC profile stripped' if srgb_pixels else 'absent (ICC stripped)'
                    orientation_tag = None
                    orientation = 1
                else: orientation_tag = orientation
            elif op == 'metadata.strip_gps':
                edits.append(['-' + tag + '=' for tag in GPS_TAGS])
                gps_reduce_args = None
                approved_gps_reduction = None
                gps_state = 'absent (recognized fields)'
            elif op == 'metadata.reduce_gps':
                from kim_location import (
                    read_many, summarize, removal_args, generalize,
                    assignments as gps_assignments, display_position,
                )
                grid_m = int(step['grid'])
                src_key = str(source)
                loc_data = read_many([src_key], complete=True)[src_key]
                if loc_data.get('error'):
                    raise RecipeError('GPS inspection failed: ' + str(loc_data['error']))
                loc_info = summarize(loc_data['raw'])
                camera_issues = loc_info['categories']['camera']['issues']
                if camera_issues:
                    raise RecipeError('GPS precision reduction blocked: ' + '; '.join(camera_issues))
                if not loc_info['position']:
                    raise RecipeError(
                        'No camera GPS coordinates found to reduce. '
                        'Use Remove GPS coordinates or deselect images without GPS.'
                    )
                try:
                    rem_args, _removed = removal_args(loc_info, reduce=True)
                    new_pos, displacement = generalize(loc_info['position'], grid_m)
                    write_args = gps_assignments(new_pos)
                except ValueError as exc:
                    raise RecipeError(str(exc)) from exc
                gps_reduce_args = rem_args + write_args
                approved_gps_reduction = {
                    'category': 'camera',
                    'position': new_pos,
                    'altitude': None,
                    'direction': None,
                    'direction_ref': 'T',
                    'altitude_ref': None,
                    'reduce': True,
                }
                grid_caption = {100: '100 m', 1000: '1 km', 5000: '5 km', 10000: '10 km'}.get(grid_m, f'{grid_m} m')
                gps_state = (
                    f'reduced to ~{grid_caption} grid ({display_position(new_pos)}; '
                    f'~{displacement:.0f} m displacement); altitude, direction, destination and place-name tags cleared'
                )
                gps_reduce_warnings.append(
                    'Free-text captions, image content and external information may still reveal location. Narrative text is preserved.'
                )
            elif op == 'metadata.set_description':
                val = step['value'].strip()
                if not val:
                    if desc_state is None:
                        desc_state = 'unchanged (existing preserved)'
                else:
                    write_iptc = fmt not in NO_LEGACY_IPTC
                    if write_iptc and len(val.encode('utf-8')) > IPTC_CAPTION_BYTE_LIMIT:
                        raise RecipeError(f'Caption / Description exceeds the {IPTC_CAPTION_BYTE_LIMIT}-byte legacy IPTC limit.')
                    args = ['-XMP-dc:Description-x-default=' + val]
                    if write_iptc:
                        args = ['-IPTC:CodedCharacterSet=UTF8', '-IPTC:Caption-Abstract=' + val] + args
                    edits.append(args)
                    expected_description = {
                        'value': val,
                        'iptc': write_iptc,
                        'lang_alts': dict(desc_info['lang_alts']) if desc_info else {},
                    }
                    if desc_info is not None:
                        desc_info['xmp_description'] = val
                        if write_iptc:
                            desc_info['iptc_description'] = val
                    has_alts = bool(desc_info and desc_info['lang_alts'])
                    desc_state = val + (
                        ' (XMP + IPTC; other XMP languages preserved)' if write_iptc and has_alts
                        else ' (XMP + IPTC)' if write_iptc
                        else ' (XMP only; other XMP languages preserved)' if has_alts
                        else ' (XMP only)'
                    )
            elif op == 'metadata.set_keywords':
                mode = step['mode']
                requested = parse_keywords(step['keywords'])
                if mode == 'unchanged':
                    if kw_state is None:
                        kw_state = 'unchanged (existing preserved)'
                elif mode == 'append':
                    if not requested:
                        if kw_state is None:
                            kw_state = 'unchanged (no keywords provided)'
                    else:
                        merged = list(desc_info['keywords']) if desc_info else []
                        seen_kw = set(merged)
                        for kw in requested:
                            if kw not in seen_kw:
                                seen_kw.add(kw)
                                merged.append(kw)
                        write_iptc = fmt not in NO_LEGACY_IPTC
                        if write_iptc:
                            for kw in merged:
                                if len(kw.encode('utf-8')) > IPTC_KEYWORD_BYTE_LIMIT:
                                    raise RecipeError(f'Keyword "{kw}" exceeds the {IPTC_KEYWORD_BYTE_LIMIT}-byte legacy IPTC limit.')
                        args = ['-XMP-dc:Subject='] + ['-XMP-dc:Subject=' + kw for kw in merged]
                        if write_iptc:
                            args = ['-IPTC:CodedCharacterSet=UTF8', '-IPTC:Keywords='] + ['-IPTC:Keywords=' + kw for kw in merged] + args
                        edits.append(args)
                        expected_keywords = {'values': merged, 'iptc': write_iptc}
                        if desc_info is not None:
                            desc_info['keywords'] = merged
                        kw_state = ', '.join(merged) + (' (append; XMP + IPTC)' if write_iptc else ' (append; XMP only)')
                elif mode == 'replace':
                    if not requested:
                        raise RecipeError('Enter at least one keyword when Keyword handling is set to Replace, or choose Leave unchanged.')
                    write_iptc = fmt not in NO_LEGACY_IPTC
                    if write_iptc:
                        for kw in requested:
                            if len(kw.encode('utf-8')) > IPTC_KEYWORD_BYTE_LIMIT:
                                raise RecipeError(f'Keyword "{kw}" exceeds the {IPTC_KEYWORD_BYTE_LIMIT}-byte legacy IPTC limit.')
                    args = ['-XMP-dc:Subject='] + ['-XMP-dc:Subject=' + kw for kw in requested]
                    if write_iptc:
                        args = ['-IPTC:CodedCharacterSet=UTF8', '-IPTC:Keywords='] + ['-IPTC:Keywords=' + kw for kw in requested] + args
                    edits.append(args)
                    expected_keywords = {'values': requested, 'iptc': write_iptc}
                    if desc_info is not None:
                        desc_info['keywords'] = requested
                    kw_state = ', '.join(requested) + (' (replace; XMP + IPTC)' if write_iptc else ' (replace; XMP only)')
            elif op == 'metadata.strip_ai':
                args = ['-' + tag + '=' for tag in AI_TAGS]
                # Only remove DigitalSourceType when it identifies AI generation.
                current = ai_values.get('XMP-iptcExt:DigitalSourceType') or ''
                if any(value in current for value in ('trainedAlgorithmicMedia', 'compositeWithTrainedAlgorithmicMedia', 'algorithmicMedia')):
                    args.append('-XMP-iptcExt:DigitalSourceType=')
                edits.append(args)
                ai_state = 'absent (recognized AI-generation fields); other provenance may remain'
            elif op == 'metadata.copyright' or op in SETTING_FIELDS:
                values = {k:self.parameter_value(step,k,settings) for k in COPYRIGHT_TAGS} if op == 'metadata.copyright' else {SETTING_FIELDS[op]: self.parameter_value(step, 'value', settings)}
                args = []
                for key, tags in COPYRIGHT_TAGS.items():
                    if fmt in NO_LEGACY_IPTC: tags = tuple(tag for tag in tags if not tag.startswith('IPTC:'))
                    value = values.get(key, '').strip()
                    if not value:
                        continue
                    if key == 'notice' and '{YEAR}' in value:
                        year = step.get('year','')
                        if year and (not year.isascii() or not year.isdigit() or len(year) != 4 or year == '0000'):
                            raise RecipeError('Copyright year must be four digits, or blank to use the capture year.')
                        if not year and logical_capture is None:
                            raise RecipeError('Copyright {YEAR} needs an image capture date. Enter a copyright year or add Set Image Capture Date before this step.')
                        value = value.replace('{YEAR}', year or str(logical_capture.year))
                    for tag in tags:
                        args.append('-' + tag + '=' + value)
                        copyright_values[tag] = value
                if args: edits.append(args)
            elif op == 'file.rename_output':
                if capture is None and any(field == 'date' for _,field,_,_ in string.Formatter().parse(step['pattern'])):
                    raise RecipeError('The output name needs an image capture date. Add Set Image Capture Date before Rename Output File.')
                name = format_output_pattern(step['pattern'],stem if stem is not None else source.stem,
                                             date=capture.strftime('%Y%m%d_%H%M%S') if capture else '',index=index)
            elif op == 'file.name_transform':
                from kim_filename import transform
                try: name=transform(name,step,index,capture)
                except ValueError as exc: raise RecipeError(str(exc)) from exc
            elif op == 'file.preserve_date':
                timestamp_ns = source.stat().st_mtime_ns
                timestamp = timestamp_ns / 1_000_000_000
                timestamp_state = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()
            elif op == 'file.sync_date':
                if capture is None:
                    raise RecipeError('The output file timestamp needs an image capture date. Add Set Image Capture Date before Synchronize File Date.')
                if capture.tzinfo is None:
                    raise RecipeError('File date synchronization needs an explicit image capture timezone (OffsetTimeOriginal). Choose UTC or a camera offset in Set Image Capture Date before this step.')
                from kim_recipe_dates import epoch_ns
                timestamp_ns = epoch_ns(capture,fraction)
                timestamp = timestamp_ns / 1000000000
                timestamp_state = capture.isoformat()
            if width * height > 100000000 or max(width,height) > 100000:
                raise RecipeError('Planned dimensions exceed the 100 megapixel safety limit. Choose a smaller size.')
        if fmt in PIXEL_EXPORTS and orientation != 1:
            raise RecipeError('Add Auto-Orient before Convert Format for ' + fmt.upper() + ' output')
        if fmt in PIXEL_EXPORTS: orientation_tag = None
        if conversion and not compression: quality = self.parameter_value(conversion,'quality')
        if compression:
            quality = compression['quality'] if compression['preset'] == 'custom' else 70 if compression['preset'] == 'maximum' else 85
        encode = bool(pixel_args or overlays or quality is not None)
        if fmt == 'psd' and conversion is None:
            raise OutputFormatRequired(
                'This recipe needs an output format for Photoshop files. '
                'KIMng can read PSD files but cannot save new PSD files. '
                'Add “Convert Format” and choose JPEG, PNG, TIFF or another supported output format. '
                'Your original PSD will remain unchanged.')
        if not encode and fmt not in FORMATS:
            raise RecipeError('Add Convert Format and choose a supported output format for this image.')
        if fmt not in FORMATS:
            raise RecipeError('Choose an available output format in Convert Format')
        if overlays and 'cmyk' in colorspace and not source_profile:
            raise RecipeError('Unprofiled CMYK has unknown source colors; supply a valid source ICC profile before overlaying')
        if encode:
            formats = run(['magick', '-list', 'format'])
            if not any(len(parts := line.split()) >= 3 and parts[0].rstrip('*') == CODERS[fmt] and 'w' in parts[2] for line in formats.splitlines()):
                raise RecipeError('ImageMagick ' + CODERS[fmt] + ' writer unavailable')
        stage('Checking metadata')
        pixel_export = fmt in PIXEL_EXPORTS
        strip_requested = (
            omit_source_metadata
            or any(
                s['op'] == 'metadata.strip_all'
                for s in steps
            )
        )
        descriptive_removed = any(s['op'] == 'metadata.strip_descriptive' for s in steps)
        # Photoshop's nonstandard Manifest list can be retained as a raw XMP
        # packet. Editing that packet would make ExifTool repair unrelated
        # provenance. Require explicit removal instead of hiding that warning.
        if not (strip_requested or descriptive_removed) and (auto_oriented or any(any(a.startswith('-XMP') for a in edit) for edit in edits)):
            import xml.etree.ElementTree as ET
            packet = run(['exiftool','-b','-XMP','-'], source=source)
            if packet:
                try:
                    root = ET.fromstring(packet)
                    manifests = root.iter('{http://ns.adobe.com/xap/1.0/mm/}Manifest')
                    if any(list(node) and list(node)[0].tag != '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag' for node in manifests):
                        raise RecipeError('The embedded Photoshop XMP Manifest uses a nonstandard list. Editing XMP would repair unrelated provenance. Add Remove Descriptive Metadata before the date/copyright step, or keep the metadata without editing it.')
                except ET.ParseError as exc:
                    raise RecipeError('Embedded XMP is malformed. Remove Descriptive Metadata before editing dates or copyright, or keep it unchanged.') from exc
        if pixel_export and (any(edit != ['-all='] for edit in edits) or gps_reduce_args):
            raise RecipeError(fmt.upper() + ' output cannot retain the selected capture-date/copyright/descriptive/GPS metadata fields. Choose PNG, TIFF, JPEG, WebP or HEIC, or disable those metadata steps.')
        if pixel_export and not strip_requested:
            descriptive = json.loads(run(['exiftool','-json','-EXIF:all','-XMP:all','-IPTC:all','-'], source=source))[0]
            if len(descriptive) > 1:
                raise RecipeError(fmt.upper() + ' cannot guarantee descriptive metadata preservation; add Remove All Metadata after Convert Format')
        if fmt in NO_LEGACY_IPTC and not (strip_requested or descriptive_removed) and run(['exiftool','-s3','-IPTC:all','-'], source=source).strip():
            raise RecipeError(fmt.upper() + ' cannot retain legacy IPTC; add Remove Descriptive Metadata / Remove All Metadata or choose TIFF/PNG/JPEG')
        # Opaque / non-profile containers require sRGB pixels before metadata
        # removal. Never assign an RGB profile to unknown CMYK samples.
        force_srgb = fmt in ('bmp','pdf') or (encode and strip_requested)
        rgb_only = fmt in ('png','webp','avif','heic','heif','gif','bmp','pdf','jp2','jxl')
        transform = force_srgb or (rgb_only and 'cmyk' in colorspace)
        if ('cmyk' in colorspace) and not source_profile and (transform or srgb_pixels):
            raise RecipeError('Unprofiled CMYK has unknown source colors; supply a valid source ICC profile')
        if transform:
            if not source_profile and colorspace in ('gray','lineargray'): pixel_args += ['-colorspace','sRGB']
            pixel_args += ['-profile',srgb_profile()]
            srgb_pixels = True
            color_state = 'sRGB pixels' + ('; profile removed' if strip_requested or fmt in ('bmp','pdf') else '; sRGB ICC')
        if fmt in ('png','bmp','gif','pdf','tiff') or (fmt == 'jp2' and (conversion or {}).get('jp2_mode','lossless') == 'lossless'): quality = None
        expected = {}
        strip_all = strip_gps = omit_source_metadata
        for edit in edits:
            if edit[:3] == ['-EXIF:all=','-IPTC:all=','-XMP:all=']:
                expected.clear(); strip_gps = True
                expected['EXIF:Orientation#'] = str(orientation_tag or 1)
                continue
            for assignment in edit:
                tag, value = assignment[1:].split('=', 1)
                if tag == 'all':
                    expected.clear(); strip_all = True; strip_gps = True
                elif tag == 'GPS:all':
                    strip_gps = True
                elif tag in ('IPTC:CodedCharacterSet', 'XMP-dc:Description-x-default',
                             'IPTC:Caption-Abstract', 'XMP-dc:Subject', 'IPTC:Keywords'):
                    continue
                else:
                    expected[tag] = value
        profile = None
        if encode and not strip_all:
            profile = source_profile
            if srgb_pixels:
                profile = json.loads(run(['exiftool', '-json', '-ICC_Profile:all', srgb_profile()]))[0]
                profile.pop('SourceFile', None)
        if fmt in ('bmp','pdf'): profile = None
        compression_label = None
        if compression:
            level = compression['png_level'] if compression['preset'] == 'custom' else 9 if compression['preset'] == 'maximum' else 6
            compression_label = (f'PNG lossless level {level}; pixels and bit depth preserved' if fmt == 'png' else
                                 f'{fmt.upper()} lossy quality {quality}')
            if fmt == 'jpeg': compression_label += '; ' + ('progressive' if compression['jpeg_progressive'] else 'baseline') + ('; optimized Huffman coding' if compression['jpeg_optimize'] else '')
            compression_label += '; one final encode; smaller size is not guaranteed'
        final_metadata = ['Image capture time: ' + (display(capture,fraction) if capture else 'absent'),
                          'Image capture date: ' + date_source,
                          'Orientation: ' + (str(orientation_tag) if orientation_tag is not None else 'absent (normal display)'),
                          'GPS: ' + gps_state, 'AI fields: ' + ai_state,
                          'ICC: ' + color_state, 'Output timestamp: ' + timestamp_state]
        if desc_state is not None:
            final_metadata.append('Caption / Description: ' + desc_state)
        if kw_state is not None:
            final_metadata.append('Keywords: ' + kw_state)
        if conversion and conversion['quality'] is None and quality_setting(fmt) and not compression:
            final_metadata.append('Quality source: KIMng Settings - ' + quality_setting(fmt))
        if capture and capture.tzinfo is None and any(s['op'] in ('metadata.set_capture','metadata.shift_capture') for s in steps):
            final_metadata.append('Image capture timezone: Unknown; EXIF/XMP have no offset. IPTC time is omitted to avoid an invented timezone.')
        output_depth = (conversion or {}).get('depth','preserve')
        if fmt in ('jpeg','webp','bmp','gif','pdf','heic','heif'): output_depth = '8'
        precision = str(source_depth) + '-bit source; '
        precision += ('AVIF encoder selects supported precision (up to 12-bit)' if fmt == 'avif' else
                      str(source_depth) + '-bit samples retained' if output_depth == 'preserve' else output_depth + '-bit output')
        if fmt == 'gif': precision += '; palette colors and limited transparency'
        final_metadata.append('Sample precision: ' + precision)
        if omit_source_metadata:
            final_metadata = [
                "Source metadata: omitted from this derivative",
                "EXIF, IPTC, XMP, GPS: omitted",
                "Color: converted to sRGB; embedded profile omitted",
                "Original image: unchanged",
            ]

        # Describe every final rights field, including fields removed before restoration.
        final_metadata.extend(tag + ': ' + (json.dumps(value, ensure_ascii=False) if value is not None else 'absent')
                              for tag, value in copyright_values.items())
        if fmt == 'png' and any(value is not None for tag, value in copyright_values.items() if tag.startswith('IPTC:')):
            final_metadata.append('IPTC storage: PNG raw profile (nonstandard, supported by ExifTool)')
        return {'orientation': orientation_tag, 'profile': profile, 'expected': expected, 'strip_all': strip_all, 'strip_gps': strip_gps, 'name': name, 'extension': FORMATS[fmt], 'format': fmt,
                'properties': {'original_width': original_width, 'original_height': original_height,
                               'original_display_width': original_height if info.get('Orientation', 1) in (5, 6, 7, 8) else original_width,
                               'original_display_height': original_width if info.get('Orientation', 1) in (5, 6, 7, 8) else original_height,
                               'display_width': height if orientation in (5, 6, 7, 8) else width,
                               'display_height': width if orientation in (5, 6, 7, 8) else height,
                               'source_format': info.get('FileType', '').lower(),
                               'crops': crop_descriptions,
                               'overlays': [('Camera & EXIF details' if r['step']['kind'] == 'camera' else r['step']['kind']) + ' at ' + r['step']['anchor'].replace('_', ' ') + (': ' + r['text'] if r['text'] else ': ' + r['step']['logo'] if r['step']['kind'] == 'image' else ': no embedded fields; skipped') for r in overlays],
                               'strip_all': strip_all, 'strip_gps': strip_gps,
                               'strip_ai': any(s['op'] == 'metadata.strip_ai' for s in steps),
                               'width': width, 'height': height, 'dimensions': 'exact planned pixels', 'compressed_size': 'unknown', 'quality': quality, 'orientation': orientation_tag, 'compression': compression_label},
                'metadata': final_metadata, 'pixel_args': pixel_args, 'edits': edits, 'overlays': overlays,
                'gps_reduce_args': gps_reduce_args, 'approved_gps_reduction': approved_gps_reduction,
                'expected_description': expected_description, 'expected_keywords': expected_keywords,
                'warnings': ([PSD_WARNING] if info.get('FileType') == 'PSD' else []) + session_warnings() + date_warnings + gps_reduce_warnings + [w for r in overlays for w in r['warnings']],
                'compression': compression, 'compression_label': compression_label,
                'conversion': conversion, 'pixel_export': pixel_export, 'force_srgb': force_srgb, 'profile_srgb': srgb_pixels,
                'encode': encode, 'quality': quality, 'timestamp': timestamp, 'timestamp_ns': timestamp_ns, 'auto_oriented': auto_oriented,
                'capture_year': capture.strftime('%Y') if capture is not None else None,
                'capture_date_iso': capture.strftime('%Y-%m-%d') if capture is not None else None,
                'capture_problem': capture_problem,
                'omit_source_metadata': omit_source_metadata,
                '_recipe_index': index,
                '_source_stem': stem}

    def execute(self, source, output, steps, state):
        stage('Encoding image' if state['encode'] else 'Copying source')
        if state['encode']:
            args = []  # Final encoder options; shared overlays precede these.
            if state['quality'] is not None:
                args += ['-quality', str(state['quality'])]
            # JPEG cannot represent transparency: flatten explicitly onto white.
            if state['format'] in ('jpeg','bmp','pdf','heic','heif'):
                args += ['-background', 'white', '-alpha', 'remove', '-alpha', 'off']
            fmt = state['format']; options = state.get('conversion') or {}
            compression = state.get('compression')
            if compression:
                options = dict(options, jpeg_progressive=compression['jpeg_progressive'],jpeg_optimize=compression['jpeg_optimize'])
                if fmt == 'png':
                    level = compression['png_level'] if compression['preset'] == 'custom' else 9 if compression['preset'] == 'maximum' else 6
                    args += ['-define',f'png:compression-level={level}']
            if fmt == 'jpeg': args += ['-depth','8','-interlace', 'Plane' if options.get('jpeg_progressive',False) else 'None']
            if fmt == 'jpeg' and options.get('jpeg_optimize',False): args += ['-define','jpeg:optimize-coding=true']
            if fmt == 'bmp': args += ['-define','bmp:format=bmp5','-depth','8']
            if fmt == 'gif': args += ['-depth','8']
            if fmt == 'jp2':
                args += ['-define','jp2:rate=1'] if options.get('jp2_mode','lossless') == 'lossless' else ['-quality',str(state['quality'] or 90)]
            if fmt == 'tiff': args += ['-compress', {'zip':'Zip','lzw':'LZW','none':'None'}[options.get('tiff_compression','zip')]]
            if options.get('depth','preserve') != 'preserve': args += ['-depth',options['depth']]
            if fmt == 'pdf': args += ['-depth','8','-compress','Zip','-units','PixelsPerInch','-density','72']
            if fmt in ('heic','heif'): args += ['-depth','8']
            # Strip before encoding too: otherwise IM can carry a legacy IPTC
            # chunk into WebP/HEIC that ExifTool cannot subsequently remove.
            # Its ICC has already been used for the required sRGB transform.
            if state['strip_all'] or fmt in ('bmp','pdf'): args += ['-strip']
            from kim_image_ops import overlay_arguments
            with tempfile.TemporaryDirectory(prefix='.kimng-overlay.', dir=output.parent) as workspace:
                composites = overlay_arguments(source, state, workspace)
                run(['magick', str(source)] + state['pixel_args'] + composites + args + [CODERS[fmt] + ':' + str(output)])
            if fmt == 'jp2' and state['profile']:
                # Match Convert's explicit JP2 ICC restoration, from the profile
                # actually used to encode the pixels (including a color step).
                profile_source = srgb_profile() if state['profile_srgb'] else source
                with prepared(['exiftool','-b','-ICC_Profile',str(profile_source)]) as resolved:
                    try: result = run_process(resolved,timeout=180)
                    except (OSError,subprocess.TimeoutExpired,PSDError) as exc:
                        raise RecipeError('Could not read JPEG 2000 color profile: ' + str(exc)) from exc
                    diagnostics = metadata_diagnostics(resolved,result.returncode,result.stderr.decode(errors='replace'))
                    if result.returncode or diagnostics or not result.stdout: raise RecipeError('Could not recover the encoded JPEG 2000 color profile')
                    blob = result.stdout
                profile_file = output.with_suffix('.icc')
                try:
                    profile_file.write_bytes(blob)
                    run(['exiftool','-overwrite_original','-ICC_Profile<='+str(profile_file),str(output)])
                finally: profile_file.unlink(missing_ok=True)
            try:
                if (
                    not state['pixel_export']
                    and not state['omit_source_metadata']
                ):

                    # Copy descriptive metadata without replacing the encoded color profile.
                    tags = json.loads(run(['exiftool', '-json', '-EXIF:all', '-XMP:all', '-IPTC:all', str(source)]))[0]
                    if len(tags) > 1 and not state['strip_all'] and not any(s['op'] == 'metadata.strip_descriptive' for s in steps):
                        # Block-copy XMP verbatim. Rebuilding every XMP tag may
                        # "repair" unrelated Photoshop structures (e.g. Manifest)
                        # and change digest/provenance data the user did not edit.
                        groups = ['-EXIF:all','-XMP'] + (['-IPTC'] if fmt not in NO_LEGACY_IPTC else [])
                        run(['exiftool', '-overwrite_original', '-TagsFromFile', str(source)] + groups + [str(output)], allow_png_iptc=fmt == 'png')
                    run(['exiftool', '-overwrite_original',
                         '-EXIF:ExifImageWidth=' + str(state['properties']['width']),
                         '-EXIF:ExifImageHeight=' + str(state['properties']['height']), str(output)])
                    if state['auto_oriented']:
                        run(['exiftool', '-overwrite_original', '-EXIF:Orientation#=1', '-XMP-tiff:Orientation#=1', str(output)])

            except RecipeError as metadata_error:
                # A standalone watermark can still produce a
                # valid image when optional source metadata
                # cannot be copied. Never apply this policy to
                # ordinary Recipes or other image operations.
                active = [
                    step['op']
                    for step in steps
                    if step.get('enabled', True)
                ]

                eligible = (
                    _AUTO_WATERMARK_METADATA_FALLBACK.get()
                    and not state['omit_source_metadata']
                    and active.count('image.overlay') == 1
                    and not any(
                        op.startswith('metadata.')
                        for op in active
                    )
                )

                crop_eligible = (
                    _CROP_OPTIONAL_METADATA.get()
                    and not state['omit_source_metadata']
                    and state['format'] == 'jpeg'
                    and active.count('image.crop') == 1
                    and 'image.overlay' not in active
                    and not any(
                        op.startswith('metadata.')
                        for op in active
                    )
                    and 'Incomplete extended XMP'
                        in str(metadata_error)
                )

                eligible = eligible or crop_eligible

                if not eligible:
                    raise

                from kim_process import checkpoint
                checkpoint()
                stage(
                    'Rebuilding cropped image without source metadata'
                    if crop_eligible else
                    'Rebuilding watermark without source metadata'
                )

                # Re-plan from the same private source snapshot.
                # Metadata removal and sRGB handling use the
                # existing verified image-planning code.
                retry_policy = (
                    standalone_crop_clean_retry()
                    if crop_eligible
                    else standalone_overlay_metadata_policy(True)
                )
                with retry_policy:
                    clean_state = self.plan(
                        source,
                        steps,
                        state['_recipe_index'],
                        stem=state['_source_stem'],
                    )

                    if (
                        clean_state['name'] != state['name']
                        or clean_state['extension']
                            != state['extension']
                        or clean_state['format'] != state['format']
                        or (
                            clean_state['properties']['width'],
                            clean_state['properties']['height'],
                        ) != (
                            state['properties']['width'],
                            state['properties']['height'],
                        )
                    ):
                        raise RecipeError(
                            'Automatic watermark fallback changed '
                            'the reviewed filename, format, or dimensions'
                        )

                    # Discard the partially modified staging output.
                    # The original source is never touched.
                    output.unlink(missing_ok=True)
                    checkpoint()

                    self.execute(
                        source, output, steps, clean_state
                    )

                # The caller verifies the actual clean output
                # against this new metadata-free state before
                # publication.
                state.clear()
                state.update(clean_state)
                if crop_eligible:
                    state['optional_metadata_warning'] = (
                        'Image saved with reduced metadata. '
                        'Incomplete extended XMP prevented safe '
                        'metadata preservation. The original is unchanged.'
                    )
                else:
                    state['optional_metadata_warning'] = (
                        'Image created. Some metadata could not be '
                        'preserved. Check the final image.'
                    )
                return
        else:
            shutil.copyfile(source, output)
        if state['edits'] or state.get('gps_reduce_args'): stage('Updating metadata')
        for args in state['edits']:
            if state['pixel_export'] and args == ['-all=']: continue
            run(['exiftool', '-overwrite_original'] + args + [str(output)],
                allow_icc_removal=args == ['-all='],
                allow_png_iptc=state['format'] == 'png' and any(arg.startswith('-IPTC:') for arg in args))
            if args == ['-all=']:
                remaining = json.loads(run(['exiftool', '-json', '-EXIF:all', '-XMP:all', '-IPTC:all', '-ICC_Profile:all', str(output)]))[0]
                if len(remaining) > 1:
                    raise RecipeError('Metadata stripping verification failed')
        if state.get('gps_reduce_args'):
            run(['exiftool', '-overwrite_original'] + state['gps_reduce_args'] + [str(output)],
                allow_png_iptc=state['format'] == 'png' and any(arg.startswith('-IPTC:') for arg in state['gps_reduce_args']))

    def verify(self, output, state):
        stage('Verifying output')
        # Ghostscript rejects some very small page raster sizes at 72 DPI.
        # Verify those pages at an integer scale and compare logical dimensions;
        # this changes neither the PDF canvas nor the published image.
        pdf_scale = max(1, math.ceil(32/min(state['properties']['width'],state['properties']['height']))) if state['format'] == 'pdf' else 1
        info, fmt, width, height = inspect(output, output=True, pdf_scale=pdf_scale)
        if (info.get('Orientation') or 1) != (state['orientation'] or 1):
            raise RecipeError('Output orientation failed verification')
        if state['auto_oriented'] and not state['strip_all'] and not state['pixel_export']:
            orientations = run(['exiftool', '-s3', '-n', '-EXIF:Orientation', '-XMP-tiff:Orientation', str(output)]).splitlines()
            if not orientations or any(value != '1' for value in orientations):
                raise RecipeError('Output orientation tags disagree')
        if CODERS.get(fmt, fmt.upper()) != CODERS[state['format']] or (width, height) != (state['properties']['width'], state['properties']['height']):
            raise RecipeError('Output format or dimensions failed verification')
        # Decode the result, rather than trusting headers alone.
        if fmt != 'pdf': run(['magick',str(output),'null:'])
        if state['profile']:
            actual_profile = json.loads(run(['exiftool', '-json', '-ICC_Profile:all', str(output)]))[0]
            actual_profile.pop('SourceFile', None)
            if actual_profile != state['profile']:
                raise RecipeError('Output ICC profile failed verification')
        for tag, value in state['expected'].items():
            actual = run(['exiftool', '-s3', '-' + tag, str(output)]).strip()
            if actual != value:
                raise RecipeError('Metadata verification failed: ' + tag)
        if state.get('expected_description') or state.get('expected_keywords'):
            actual_desc = json.loads(run([
                'exiftool', '-json', '-G1', '-a',
                '-XMP-dc:Description*', '-IPTC:Caption-Abstract',
                '-XMP-dc:Subject', '-IPTC:Keywords', str(output),
            ]))[0]
            exp_desc = state.get('expected_description')
            if exp_desc:
                if str(actual_desc.get('XMP-dc:Description', '')) != exp_desc['value']:
                    raise RecipeError('Metadata verification failed: XMP-dc:Description')
                if exp_desc['iptc'] and str(actual_desc.get('IPTC:Caption-Abstract', '')) != exp_desc['value']:
                    raise RecipeError('Metadata verification failed: IPTC:Caption-Abstract')
                for lang_tag, lang_val in exp_desc.get('lang_alts', {}).items():
                    if str(actual_desc.get(lang_tag, '')) != lang_val:
                        raise RecipeError('Metadata verification failed: preserved language alternative ' + lang_tag)
            exp_kw = state.get('expected_keywords')
            if exp_kw:
                if _normalize_tag_list(actual_desc.get('XMP-dc:Subject')) != exp_kw['values']:
                    raise RecipeError('Metadata verification failed: XMP-dc:Subject')
                if exp_kw['iptc'] and _normalize_tag_list(actual_desc.get('IPTC:Keywords')) != exp_kw['values']:
                    raise RecipeError('Metadata verification failed: IPTC:Keywords')
        if state['strip_gps']:
            remaining = run(['exiftool', '-s3'] + ['-' + tag for tag in GPS_TAGS] + [str(output)]).strip()
            if remaining:
                raise RecipeError('GPS removal verification failed')
        if state.get('approved_gps_reduction'):
            from kim_location import read_many, summarize, matches_approved
            out_key = str(output)
            out_data = read_many([out_key], complete=True)[out_key]
            if out_data.get('error'):
                raise RecipeError('Reduced GPS verification failed: ' + str(out_data['error']))
            out_raw = out_data['raw']
            if not matches_approved(summarize(out_raw), out_raw, state['approved_gps_reduction']):
                raise RecipeError('Reduced GPS verification failed')
        if state['strip_all'] and not any(state['expected'].values()):
            remaining = json.loads(run(['exiftool', '-json', '-EXIF:all', '-XMP:all',
                                        '-IPTC:all', '-ICC_Profile:all', str(output)]))[0]
            if len(remaining) > 1:
                raise RecipeError('Metadata stripping verification failed')
        if state.get('timestamp_ns') is not None:
            os.utime(output, ns=(state['timestamp_ns'],state['timestamp_ns']))
            if output.stat().st_mtime_ns != state['timestamp_ns']:
                raise RecipeError('The destination filesystem cannot store this File Modification Date at the requested precision. Disable file-date synchronization or choose a compatible destination; the Image Capture Date can remain embedded.')
        elif state['timestamp'] is not None:
            os.utime(output, (state['timestamp'], state['timestamp']))
