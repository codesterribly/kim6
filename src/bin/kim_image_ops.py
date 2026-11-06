"""Shared, versioned crop geometry and literal raster overlays for KIM6.

Standalone dialogs and Recipes use these same planners and renderers. Geometry
is always measured after orientation normalization. No source is opened writable.
"""
import copy
import contextlib
import contextvars
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import subprocess
import sys

from kim_recipe_core import RecipeError, keys
from kim_annotations import CAMERA_FIELDS, CAMERA_DEFAULTS, NO_CAMERA_INFORMATION

CROP_DEFAULTS = dict(version=1, aspect='original', ratio_width=1, ratio_height=1,
                     area='aspect', crop_width=1000, crop_height=1000, placement='center',
                     x=0.0, y=0.0, w=1.0, h=1.0, resize=False,
                     target_width=1000, target_height=1000, upscale=False)
OVERLAY_DEFAULTS = dict(version=1, kind='text', source='custom', value='', logo='',
                        anchor='bottom_right', margin=3.0, size=3.0, opacity=65,
                        font='DejaVu Sans', color='#ffffff', bold=False, italic=False,
                        assistance='outline', text_fields=None, camera_fields=None)
ASPECTS = [('Original aspect ratio', 'original'), ('1:1', '1:1'), ('4:3', '4:3'),
           ('3:2', '3:2'), ('16:9', '16:9'), ('9:16', '9:16'),
           ('Custom ratio', 'custom'), ('Free crop', 'free')]
PLACEMENTS = [('Centered crop', 'center'), ('Top-left', 'top_left'), ('Top-right', 'top_right'),
              ('Bottom-left', 'bottom_left'), ('Bottom-right', 'bottom_right'), ('Manual selection', 'manual')]
ANCHORS = [(v.replace('_', ' ').capitalize(), v) for v in
           ('top_left', 'top', 'top_right', 'left', 'center', 'right', 'bottom_left', 'bottom', 'bottom_right')]
TEXT_SOURCES = [('Custom text', 'custom'), ('Creator / Artist from KIM6 Settings', 'creator'),
                ('Copyright Notice from KIM6 Settings', 'notice'), ('Usage Rights from KIM6 Settings', 'rights')]
TEXT_FIELDS = [('Creator / Artist', 'creator'), ('Copyright Notice', 'notice'),
               ('Usage Rights', 'rights'), ('Custom text', 'custom')]
KINDS = [('Text watermark', 'text'), ('Image watermark / logo', 'image'),
         ('Camera & EXIF details', 'camera'), ('Caption overlay', 'caption')]


def number(value, low, high, integer=False):
    if (type(value) not in ((int,) if integer else (int, float)) or
            not math.isfinite(value) or not low <= value <= high):
        raise RecipeError(f'Expected {"integer" if integer else "number"} between {low} and {high}')


def literal(value, limit=4096):
    if (not isinstance(value, str) or len(value) > limit or
            any(ord(c) < 32 and c not in '\n\t' for c in value) or '\x7f' in value):
        raise RecipeError('Invalid overlay text')
    return value


def validate_crop(step):
    keys(step, ('op',) + tuple(CROP_DEFAULTS), ('enabled',))
    if type(step['version']) is not int or step['version'] != 1: raise RecipeError('Unsupported crop version')
    if not isinstance(step['aspect'], str) or step['aspect'] not in tuple(v for _, v in ASPECTS): raise RecipeError('Choose a crop aspect ratio')
    if step['area'] not in ('aspect', 'pixels', 'manual'): raise RecipeError('Choose a crop area')
    if not isinstance(step['placement'], str) or step['placement'] not in tuple(v for _, v in PLACEMENTS): raise RecipeError('Choose a crop position')
    for key in ('ratio_width', 'ratio_height', 'crop_width', 'crop_height', 'target_width', 'target_height'):
        number(step[key], 1, 100000, True)
    for key in ('x', 'y', 'w', 'h'): number(step[key], 0, 1)
    if not step['w'] or not step['h'] or step['x'] + step['w'] > 1.0000001 or step['y'] + step['h'] > 1.0000001:
        raise RecipeError('The manual crop rectangle must stay inside the image')
    for key in ('resize', 'upscale'):
        if type(step[key]) is not bool: raise RecipeError(key + ' must be boolean')


def crop_ratio(step, width, height):
    aspect = step['aspect']
    if aspect == 'free': return None
    if aspect == 'original': return width / height
    if aspect == 'custom': return step['ratio_width'] / step['ratio_height']
    w, h = map(int, aspect.split(':'))
    return w / h


def fit_ratio(width, height, ratio):
    if ratio is None: return width, height
    cw, ch = min(width, math.floor(height * ratio)), min(height, math.floor(width / ratio))
    if min(cw, ch) < 1: raise RecipeError('The selected ratio cannot fit a one-pixel crop on this image')
    return cw, ch


def crop_plan(width, height, step):
    """Return bounded integer crop coordinates and a separate proportional resize.

    Manual rectangles are normalized bounding areas, then fitted to the chosen
    aspect on each image. Their pixel coordinates are deliberately per-image.
    Exact crop pixels never silently shrink to fit a smaller input.
    """
    validate_crop(step)
    ratio = crop_ratio(step, width, height)
    manual = step['area'] == 'manual'
    if manual:
        left = min(width - 1, round(step['x'] * width))
        top = min(height - 1, round(step['y'] * height))
        right = min(width, round((step['x'] + step['w']) * width))
        bottom = min(height, round((step['y'] + step['h']) * height))
        if right <= left or bottom <= top: raise RecipeError('Manual crop is smaller than one pixel on this image')
        cw, ch = fit_ratio(right - left, bottom - top, ratio)
        x, y = left + (right - left - cw) // 2, top + (bottom - top - ch) // 2
    else:
        if step['area'] == 'pixels':
            cw, ch = step['crop_width'], step['crop_height']
            if ratio and abs(ch - cw / ratio) > 1:
                raise RecipeError('Exact crop pixels do not match the selected ratio. Choose Free crop or matching dimensions.')
        else: cw, ch = fit_ratio(width, height, ratio)
        if cw > width or ch > height:
            raise RecipeError(f'Crop area {cw} × {ch} exceeds this image’s {width} × {height} pixels')
        placement = step['placement']
        if placement == 'manual':
            x, y = round(step['x'] * width), round(step['y'] * height)
            if x + cw > width or y + ch > height:
                raise RecipeError('Manual position and exact crop dimensions exceed this image')
        else:
            x = 0 if placement.endswith('left') else width - cw if placement.endswith('right') else (width - cw) // 2
            y = 0 if placement.startswith('top') else height - ch if placement.startswith('bottom') else (height - ch) // 2
    if min(cw, ch) < 1 or x < 0 or y < 0 or x + cw > width or y + ch > height:
        raise RecipeError('Crop rectangle exceeds this image')
    ow, oh = cw, ch
    args = ['-crop', f'{cw}x{ch}+{x}+{y}', '+repage']
    if step['resize']:
        tw, th = step['target_width'], step['target_height']
        scale = min(tw / cw, th / ch)
        ow, oh = max(1, math.floor(cw * scale + .5)), max(1, math.floor(ch * scale + .5))
        if (ow, oh) != (tw, th):
            raise RecipeError('Target pixels would change proportions. Match the target to the crop ratio; KIM6 will not stretch it.')
        if scale > 1 and not step['upscale']:
            raise RecipeError('Target pixels require enlargement. Enable Allow enlargement or choose smaller target dimensions.')
        args += ['-resize', f'{tw}x{th}']
    if ow * oh > 100000000: raise RecipeError('Crop output exceeds the 100 megapixel safety limit')
    return dict(x=x, y=y, width=cw, height=ch, output_width=ow, output_height=oh, args=args)


def validate_overlay(step):
    keys(step, ('op',) + tuple(k for k in OVERLAY_DEFAULTS if k not in ('text_fields', 'camera_fields')),
         ('enabled', 'text_fields', 'camera_fields'))
    if type(step['version']) is not int or step['version'] != 1: raise RecipeError('Unsupported overlay version')
    if not isinstance(step['kind'], str) or step['kind'] not in tuple(v for _, v in KINDS): raise RecipeError('Choose an overlay type')
    if step['source'] not in ('custom', 'creator', 'notice', 'rights', 'embedded'): raise RecipeError('Choose an overlay text source')
    if step['kind'] == 'text' and step['source'] == 'embedded': raise RecipeError('Choose a text watermark source')
    if step['kind'] == 'caption' and step['source'] not in ('custom', 'embedded'): raise RecipeError('Choose a caption source')
    if step['value'] is not None: literal(step['value'])
    elif step['kind'] != 'text' or step['source'] not in ('creator', 'notice', 'rights'):
        raise RecipeError('Only Settings text can use an inherited value')
    if step.get('text_fields') is not None:
        keys(step['text_fields'], tuple(k for _, k in TEXT_FIELDS))
        for _, key in TEXT_FIELDS:
            field = step['text_fields'][key]
            keys(field, ('selected', 'value'))
            if type(field['selected']) is not bool: raise RecipeError('Text field selection must be boolean')
            if field['value'] is None:
                if key == 'custom': raise RecipeError('Custom text cannot inherit Settings')
            else: literal(field['value'])
    if step.get('camera_fields') is not None:
        keys(step['camera_fields'], tuple(key for _, key in CAMERA_FIELDS))
        if any(type(value) is not bool for value in step['camera_fields'].values()):
            raise RecipeError('Camera & EXIF field selections must be boolean')
    literal(step['font'], 200); literal(step['logo'])
    if not step['font'].strip(): raise RecipeError('Choose an overlay font')
    if not isinstance(step['anchor'], str) or step['anchor'] not in tuple(v for _, v in ANCHORS): raise RecipeError('Choose an overlay anchor')
    number(step['margin'], 0, 40); number(step['size'], .1, 100); number(step['opacity'], 0, 100, True)
    for key in ('bold', 'italic'):
        if type(step[key]) is not bool: raise RecipeError(key + ' must be boolean')
    if not isinstance(step['color'], str) or not re.fullmatch('#[0-9a-fA-F]{6}', step['color']):
        raise RecipeError('Choose a text color in #RRGGBB form')
    if step['assistance'] not in ('none', 'shadow', 'outline'): raise RecipeError('Choose readability assistance')
    if step['kind'] == 'image' and (not step['logo'] or not Path(step['logo']).is_absolute()):
        raise RecipeError('Choose an absolute local watermark image filename')


def reference_identity(path):
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode): raise RecipeError('Watermark must be a regular local image, not a symlink: ' + str(path))
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except OSError as exc:
        raise RecipeError('Missing or unreadable watermark image: ' + str(path)) from exc


_LOGO_INSPECTIONS = contextvars.ContextVar('kim_logo_inspections', default=None)


@contextlib.contextmanager
def logo_inspections():
    """Bound logo observations to one batch/generation, including nested previews."""
    if _LOGO_INSPECTIONS.get() is not None:
        yield
        return
    token = _LOGO_INSPECTIONS.set({})
    try: yield
    finally: _LOGO_INSPECTIONS.reset(token)


def inspect_logo(path):
    from kim_recipe_image import inspect, run, srgb_profile, inspection_identity
    before = reference_identity(path)
    cache = _LOGO_INSPECTIONS.get()
    key = os.path.abspath(path)
    # Conversion policy is part of the observation, even when the logo is stable.
    profile_path = srgb_profile()
    policy = os.stat(profile_path)
    signature = (before, profile_path, policy.st_dev, policy.st_ino, policy.st_size,
                 policy.st_mtime_ns, policy.st_ctime_ns)
    if cache is not None and key in cache and cache[key][0] == signature:
        from kim_process import checkpoint
        checkpoint()
        return cache[key][1]
    try:
        info, _, width, height = inspect(Path(path))
        if info.get('Orientation') in (5, 6, 7, 8): width, height = height, width
        if min(width, height) < 1 or width * height > 100000000:
            raise RecipeError('Watermark image exceeds safe dimensions')
        profile = run(['exiftool', '-s3', '-ICC_Profile:ProfileDescription', str(path)]).strip()
        space = run(['magick', 'identify', '-format', '%[colorspace]', str(path)]).strip().lower()
        if 'cmyk' in space and not profile:
            raise RecipeError('Unprofiled CMYK watermark has unknown colors')
        # Full decode and ICC conversion are checked before batch publication.
        opaque = run(['magick', str(path), '-auto-orient', '-profile', srgb_profile(),
                      '-format', '%[opaque]', 'info:']).strip().lower() == 'true'
    except (OSError, RecipeError) as exc:
        raise RecipeError('Cannot decode watermark image ' + str(path) + ': ' + str(exc)) from exc
    if before != reference_identity(path): raise RecipeError('Watermark image changed during inspection: ' + str(path))
    if min(width, height) < 1 or width * height > 100000000: raise RecipeError('Watermark image exceeds safe dimensions: ' + str(path))
    result = before, opaque, width, height
    policy_after = os.stat(profile_path)
    if inspection_identity(policy) != inspection_identity(policy_after): raise RecipeError('Watermark color policy changed during inspection')
    if cache is not None:
        if len(cache) >= 64: cache.clear()
        cache[key] = signature, result
    return result


def watermark_fields(step):
    """Expand old single-source steps without changing their saved definition."""
    if step.get('text_fields') is not None:
        return copy.deepcopy(step['text_fields'])
    return {key: dict(selected=step['source'] == key,
                      value=step['value'] if step['source'] == key else '' if key == 'custom' else None)
            for _, key in TEXT_FIELDS}


def camera_fields(step):
    """Older overlay Recipes use the new defaults without rewriting their JSON."""
    return copy.deepcopy(step.get('camera_fields') if step.get('camera_fields') is not None else CAMERA_DEFAULTS)


def validate_camera_selection(step):
    if not any(camera_fields(step).values()):
        raise RecipeError('Select at least one Camera & EXIF details field.')


def resolved_watermark_fields(step, settings=None):
    fields = watermark_fields(step)
    inherited = [key for key, field in fields.items() if field['selected'] and field['value'] is None]
    if inherited:
        if settings is None:
            from kim_recipe_image import copyright_settings
            settings = copyright_settings()
        for key in inherited: fields[key]['value'] = literal(settings[key])
    return fields


def watermark_text(step, settings=None):
    fields = resolved_watermark_fields(step, settings)
    value = '\n'.join(fields[key]['value'].strip() for _, key in TEXT_FIELDS
                      if fields[key]['selected'] and fields[key]['value'].strip())
    if not value:
        raise RecipeError('Select at least one text watermark field with nonempty text. Enter a value or reset a field from KIM6 Settings.')
    return value


def overlay_text(source, step):
    from kim_annotations import read_tags, clean_text, DESCRIPTION, CAMERA_READ_TAGS, camera_details
    if step['kind'] == 'text':
        return watermark_text(step)
    if step['kind'] == 'caption' and step['source'] == 'custom':
        if not step['value'].strip(): raise RecipeError('Enter a caption or choose Embedded image caption')
        return step['value']
    if step['kind'] == 'camera': validate_camera_selection(step)
    tags = CAMERA_READ_TAGS if step['kind'] == 'camera' else (
                'XMP-dc:Description', 'IPTC:Caption-Abstract', 'EXIF:ImageDescription')
    try:
        row, _, rc = read_tags(source, tags, numeric=step['kind'] == 'camera')
        if rc or any(k.split(':')[-1] == 'Error' for k in row): raise ValueError('Metadata reader reported an error')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise RecipeError('Cannot read embedded overlay fields: ' + str(exc)) from exc
    def first(names):
        return next((v for k in names if (v := clean_text(row.get(k), 4096))), '')
    if step['kind'] == 'caption': return first(DESCRIPTION)
    return camera_details(row, camera_fields(step))


def overlay_plan(source, width, height, step):
    validate_overlay(step)
    result = dict(step=step.copy(), text='', identity=None, warnings=[])
    if step['kind'] == 'image':
        result['identity'], opaque, lw, lh = inspect_logo(step['logo'])
        edge = max(1, round(min(width, height) * step['size'] / 100))
        scale = min(edge / lw, edge / lh)
        lw, lh = max(1, math.floor(lw * scale + .5)), max(1, math.floor(lh * scale + .5))
        anchor_position(width, height, lw, lh, step)
        if opaque: result['warnings'].append('Watermark image is completely opaque; its background will cover image pixels: ' + step['logo'])
    else:
        result['text'] = overlay_text(source, step)
        if step['kind'] == 'camera' and not result['text']:
            raise RecipeError(NO_CAMERA_INFORMATION + ' Choose other fields or remove this image from the batch before continuing.')
        if result['text']:
            with tempfile.TemporaryDirectory(prefix='kim6-overlay-plan-') as workspace:
                lw, lh = text_layer(result['text'], width, height, step, Path(workspace) / 'text.png')
                anchor_position(width, height, lw, lh, step)
        if not result['text']:
            result['warnings'].append('No embedded caption; overlay is skipped for this image.')
    result['width'], result['height'] = width, height
    return result


_GUI_APP = None


def ensure_gui():
    from PySide6.QtGui import QGuiApplication
    global _GUI_APP
    if QGuiApplication.instance() is None:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        _GUI_APP = QGuiApplication(['kim6-overlay'])


def text_layer(text, width, height, step, output):
    """Rasterize literal Unicode with Qt, including wrapping, never IM text syntax."""
    ensure_gui()
    from kim_process import checkpoint
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextLayout, QTextOption
    short = min(width, height); margin = round(short * step['margin'] / 100)
    available_w, available_h = max(1, width - 2 * margin), max(1, height - 2 * margin)
    pixels = max(1, round(short * step['size'] / 100)); pad = max(2, round(pixels * .16))
    if available_w <= pad * 2 or available_h <= pad * 2: raise RecipeError('Overlay margins leave no room for text')
    font = QFont(step['font']); font.setPixelSize(pixels); font.setBold(step['bold']); font.setItalic(step['italic'])
    option = QTextOption(); option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layouts, lines = [], []; y = float(pad); content_w = 1
    for paragraph in text.split('\n'):
        checkpoint()
        layout = QTextLayout(paragraph or ' ', font); layouts.append(layout); layout.setTextOption(option); layout.beginLayout()
        try:
            while True:
                line = layout.createLine()
                if not line.isValid(): break
                line.setLineWidth(available_w - 2 * pad)
                if y + line.height() + pad > available_h:
                    raise RecipeError('Overlay text does not fit. Reduce size or margins, or shorten the text.')
                line.setPosition(QPointF(pad, y)); lines.append((layout, line))
                content_w = max(content_w, math.ceil(line.naturalTextWidth())); y += line.height()
        finally: layout.endLayout()
    layer_w, layer_h = min(available_w, content_w + 2 * pad), min(available_h, math.ceil(y + pad))
    if layer_w * layer_h > 100000000: raise RecipeError('Text overlay exceeds the raster safety limit')
    image = QImage(layer_w, layer_h, QImage.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(step['color']); dark = QColor('black') if color.lightness() > 128 else QColor('white')
        # Draw QTextLayout directly so shaping and fallback fonts match both
        # preview and output. The outline uses bounded offset copies.
        offset = max(1, round(pixels * .055))
        if step['assistance'] != 'none':
            painter.setPen(dark)
            offsets = [(offset, offset)] if step['assistance'] == 'shadow' else [
                (-offset, 0), (offset, 0), (0, -offset), (0, offset),
                (-offset, -offset), (-offset, offset), (offset, -offset), (offset, offset)]
            for dx, dy in offsets:
                checkpoint()
                for layout in layouts: layout.draw(painter, QPointF(dx, dy))
        painter.setPen(color)
        for layout in layouts: layout.draw(painter, QPointF(0, 0))
    finally: painter.end()
    if step['opacity'] != 100:
        painter = QPainter(image)
        try:
            painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            painter.fillRect(image.rect(), QColor(0, 0, 0, round(step['opacity'] * 255 / 100)))
        finally: painter.end()
    if not image.save(str(output), 'PNG'): raise RecipeError('Cannot write text overlay raster')
    return layer_w, layer_h


def anchor_position(width, height, lw, lh, step):
    margin = round(min(width, height) * step['margin'] / 100)
    if lw + 2 * margin > width or lh + 2 * margin > height: raise RecipeError('Overlay and margins do not fit this image')
    a = step['anchor']
    x = margin if a.endswith('left') or a == 'left' else width - lw - margin if a.endswith('right') or a == 'right' else (width - lw) // 2
    y = margin if a.startswith('top') else height - lh - margin if a.startswith('bottom') else (height - lh) // 2
    return x, y


def overlay_arguments(source, state, workspace):
    """Build fixed composite arguments with private, color-managed raster layers."""
    from kim_recipe_image import run, srgb_profile
    from kim_psd_source import prepared
    from kim_process import run_process, checkpoint
    args = []
    overlays = state.get('overlays', [])
    if not overlays: return args
    # Map sRGB overlay samples into the same profile as the final base pixels.
    target_profile = srgb_profile() if state['profile_srgb'] else None
    if not target_profile:
        with prepared(['exiftool', '-b', '-ICC_Profile', str(source)]) as resolved:
            response = run_process(resolved, timeout=180)
            if response.returncode: raise RecipeError('Cannot read base image ICC profile')
            profile = response.stdout
        if profile:
            target_profile = str(Path(workspace) / 'overlay-target.icc'); Path(target_profile).write_bytes(profile)
    for index, record in enumerate(overlays):
        checkpoint(); step = record['step']; width, height = record['width'], record['height']
        if step['kind'] != 'image' and not record['text']: continue
        output = Path(workspace) / f'overlay-{index}.png'
        if step['kind'] == 'image':
            # Copy a stable reference into the private job directory. Decode the
            # snapshot, never a later replacement of the chosen filename.
            logo = Path(step['logo']); before = reference_identity(logo)
            if before != record['identity']: raise RecipeError('Watermark image changed since planning: ' + str(logo))
            snapshot = Path(workspace) / f'logo-{index}.input'
            fd = os.open(logo, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as inp, snapshot.open('xb') as out:
                opened = os.fstat(inp.fileno())
                if (not stat.S_ISREG(opened.st_mode) or
                        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != before):
                    raise RecipeError('Watermark image changed before copying')
                while block := inp.read(1024 * 1024): checkpoint(); out.write(block)
            if reference_identity(logo) != before: raise RecipeError('Watermark changed while copying: ' + str(logo))
            edge = max(1, round(min(width, height) * step['size'] / 100))
            # Assign sRGB only for unprofiled RGB/gray. Reject unknown CMYK via
            # the same source color safety used by the Recipe planner.
            profile_present = run(['exiftool', '-s3', '-ICC_Profile:ProfileDescription', str(snapshot)]).strip()
            space = run(['magick', 'identify', '-format', '%[colorspace]', str(snapshot)]).strip().lower()
            if 'cmyk' in space and not profile_present: raise RecipeError('Unprofiled CMYK watermark has unknown colors: ' + str(logo))
            color_args = ['-profile', srgb_profile()] if profile_present else ['-colorspace', 'sRGB', '-profile', srgb_profile()]
            run(['magick', str(snapshot), '-auto-orient', *color_args, '-resize', f'{edge}x{edge}',
                 '-alpha', 'on', '-channel', 'A', '-evaluate', 'multiply', str(step['opacity'] / 100), '+channel', 'PNG:' + str(output)])
            lw, lh = map(int, run(['magick', 'identify', '-format', '%w %h', str(output)]).split())
        else:
            lw, lh = text_layer(record['text'], width, height, step, output)
        x, y = anchor_position(width, height, lw, lh, step)
        color_args = ['-profile', srgb_profile()]
        if target_profile: color_args += ['-profile', target_profile]
        args += ['(', str(output), *color_args, ')', '-gravity', 'NorthWest', '-geometry', f'+{x}+{y}', '-compose', 'Over', '-composite']
    return args


def step_details(step):
    """Human-readable Recipe settings without importing any GUI module."""
    if step['op'] == 'image.crop':
        details = [('Aspect ratio', step['aspect'] if step['aspect'] != 'custom' else f"{step['ratio_width']}:{step['ratio_height']}"),
                   ('Crop area', step['area']), ('Position', step['placement'].replace('_', ' '))]
        if step['area'] == 'pixels': details.append(('Crop pixels', f"{step['crop_width']} × {step['crop_height']}"))
        if step['area'] == 'manual':
            details.append(('Relative area (x, y, width, height)', ', '.join(f"{step[k] * 100:.2f}%" for k in ('x', 'y', 'w', 'h'))))
        details.append(('Output resize', f"{step['target_width']} × {step['target_height']} pixels; enlargement {'allowed' if step['upscale'] else 'off'}" if step['resize'] else 'None; keep cropped pixels'))
        return details
    source = dict((v, k) for k, v in TEXT_SOURCES).get(step['source'], step['source'])
    if step['kind'] == 'text':
        fields = watermark_fields(step)
        text_details = [(label, 'Inherited from Settings' if fields[key]['value'] is None else fields[key]['value'])
                        for label, key in TEXT_FIELDS if fields[key]['selected']]
        if not text_details: text_details = [('Selected text fields', 'None — select a field and enter text')]
    elif step['kind'] == 'camera':
        selected = camera_fields(step)
        text_details = [('Camera & EXIF fields', ', '.join(label for label, key in CAMERA_FIELDS if selected[key]) or 'None selected')]
    else:
        text_details = [('Text source', source), ('Text', 'Inherited from Settings' if step['value'] is None else step['value'])]
    return [('Overlay type', dict((v, k) for k, v in KINDS)[step['kind']]), *text_details,
            ('Watermark image', step['logo'] if step['kind'] == 'image' else 'Not used'),
            ('Position', step['anchor'].replace('_', ' ')),
            ('Size', f"{step['size']:g}% of shorter image edge ({'logo bounding box' if step['kind'] == 'image' else 'font height'})"),
            ('Margin', f"{step['margin']:g}% of shorter image edge"), ('Opacity', str(step['opacity']) + '%'),
            ('Text style', step['font'] + (' bold' if step['bold'] else '') + (' italic' if step['italic'] else '') + ', ' + step['color'] + ', ' + step['assistance'])]


def has_image_operations(recipe):
    return any(s['op'] in ('image.crop', 'image.overlay') and s.get('enabled', True) for s in recipe['steps'])


def preflight_batch(recipe, sources, chosen=None, start_index=1):
    """Fail before the first publication if any selected image has no safe plan."""
    from kim_recipe_core import preview
    from kim_process import checkpoint
    problems = []
    for row in preview(recipe, sources, chosen, start_index):
        checkpoint()
        problems.extend(row.source + ': ' + issue for issue in row.problems)
    if problems: raise RecipeError('Batch preflight blocked publication:\n' + '\n'.join(problems))


def picker_preview(path, edge, workspace):
    """Inspect using overlay readers, then shrink in a private picker process.

    The caller owns a timed, cancellable process group and its temporary tree.
    Keep decoder/delegate children in that group, including PSD staging tools.
    This preview never decides whether the file may be selected.
    """
    from kim_psd_source import source_session
    from kim_process import _SHELL_GROUP
    from kim_recipe_image import inspect, run, srgb_profile
    _SHELL_GROUP.set(True)
    before = reference_identity(path)
    with source_session():
        info, fmt, width, height = inspect(Path(path))
        if min(width, height) < 1 or width * height > 100000000:
            raise RecipeError('Watermark image exceeds safe preview dimensions')
        if info.get('Orientation') in (5, 6, 7, 8): width, height = height, width
        Path(workspace, 'info.json').write_text(json.dumps(dict(width=width, height=height,
                                                              format=info.get('FileType', fmt.upper()))))
        profile = run(['exiftool', '-s3', '-ICC_Profile:ProfileDescription', str(path)]).strip()
        space = run(['magick', 'identify', '-ping', '-format', '%[colorspace]', str(path)]).strip().lower()
        if 'cmyk' in space and not profile: raise RecipeError('Unprofiled CMYK has unknown colors')
        color = ['-profile', srgb_profile()] if profile else ['-colorspace', 'sRGB', '-profile', srgb_profile()]
        # JPEG can shrink during decoding. Other readers may need a full decode,
        # but only for requested visible files, under the caller's limits.
        run(['magick', '-define', f'jpeg:size={edge * 2}x{edge * 2}', str(path), '-auto-orient',
             *color, '-thumbnail', f'{edge}x{edge}>', '-depth', '8', '-strip',
             'PNG:' + str(Path(workspace, 'preview.png'))])
    if reference_identity(path) != before: raise RecipeError('Image changed while loading its preview')


if __name__ == '__main__':
    # Reuse this installed module rather than installing a separate helper.
    try:
        if len(sys.argv) != 5 or sys.argv[1] != '--watermark-preview':
            raise RecipeError('Expected a private watermark preview request')
        edge = int(sys.argv[3]); number(edge, 1, 720, True)
        picker_preview(sys.argv[2], edge, sys.argv[4])
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
