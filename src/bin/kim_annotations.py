"""Read-only publication annotations and bounded literal raster labels.

Precedence (first nonempty field): capture = EXIF DateTimeOriginal,
XMP-exif DateTimeOriginal, XMP-photoshop DateCreated, EXIF CreateDate,
XMP-xmp CreateDate. No filesystem clock or timezone conversion is used.
Camera = EXIF Model, XMP-tiff Model; lens = EXIF LensModel, XMP-exifEX
LensModel, XMP-aux Lens, EXIF LensInfo. Description = XMP-dc Description
(x-default), IPTC Caption-Abstract, EXIF ImageDescription.

ExifTool reads selected tags once per source. Qt paints untrusted text literally
into PNG: no caption ever enters ImageMagick's label/annotate/property parser.
"""
import json
import datetime as dt
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from kim_psd_source import run_process

CAPTURE = ('ExifIFD:DateTimeOriginal', 'XMP-exif:DateTimeOriginal',
           'XMP-photoshop:DateCreated', 'ExifIFD:CreateDate', 'XMP-xmp:CreateDate')
CAMERA = ('IFD0:Model', 'XMP-tiff:Model')
LENS = ('ExifIFD:LensModel', 'XMP-exifEX:LensModel', 'XMP-aux:Lens', 'ExifIFD:LensInfo')
DESCRIPTION = ('XMP-dc:Description', 'IPTC:Caption-Abstract', 'IFD0:ImageDescription')
TAGS = ('EXIF:DateTimeOriginal', 'XMP-exif:DateTimeOriginal', 'XMP-photoshop:DateCreated',
        'EXIF:CreateDate', 'XMP-xmp:CreateDate', 'EXIF:Model', 'XMP-tiff:Model',
        'EXIF:LensModel', 'XMP-exifEX:LensModel', 'XMP-aux:Lens', 'EXIF:LensInfo',
        'XMP-dc:Description', 'IPTC:Caption-Abstract', 'EXIF:ImageDescription')

# Overlay-only fields: do not change the existing Album/Contact Sheet captions.
# Prefer explicit EXIF values, then their embedded XMP equivalents. In
# particular, do not derive a lens name from LensInfo or exposure from APEX.
CAMERA_FIELDS = [('Camera make', 'make'), ('Camera model', 'model'), ('Lens', 'lens'),
                 ('Focal length', 'focal_length'), ('Aperture', 'aperture'),
                 ('Shutter speed', 'shutter_speed'), ('ISO', 'iso'), ('Capture date', 'capture_date')]
CAMERA_DEFAULTS = {key: key in ('model', 'lens', 'aperture', 'shutter_speed', 'iso')
                   for _, key in CAMERA_FIELDS}
CAMERA_TAGS = {
    'make': ('IFD0:Make', 'XMP-tiff:Make'), 'model': CAMERA,
    'lens': ('ExifIFD:LensModel', 'XMP-exifEX:LensModel', 'XMP-aux:Lens'),
    'focal_length': ('ExifIFD:FocalLength', 'XMP-exif:FocalLength'),
    'aperture': ('ExifIFD:FNumber', 'XMP-exif:FNumber'),
    'shutter_speed': ('ExifIFD:ExposureTime', 'XMP-exif:ExposureTime'),
    'iso': ('ExifIFD:ISO', 'XMP-exif:ISO'), 'capture_date': CAPTURE,
}
CAMERA_READ_TAGS = ('EXIF:Make', 'XMP-tiff:Make', 'EXIF:Model', 'XMP-tiff:Model',
                    'EXIF:LensModel', 'XMP-exifEX:LensModel', 'XMP-aux:Lens',
                    'EXIF:FocalLength', 'XMP-exif:FocalLength',
                    'EXIF:FNumber', 'XMP-exif:FNumber',
                    'EXIF:ExposureTime', 'XMP-exif:ExposureTime', 'EXIF:ISO', 'XMP-exif:ISO',
                    'EXIF:DateTimeOriginal', 'XMP-exif:DateTimeOriginal',
                    'XMP-photoshop:DateCreated', 'EXIF:CreateDate', 'XMP-xmp:CreateDate')
NO_CAMERA_INFORMATION = 'No selected camera or EXIF information is embedded in this image.'


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def read_tags(path, tags, numeric=False):
    """Read the opened regular file, then verify both the descriptor and name."""
    path = os.path.abspath(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode): raise ValueError('Source is not a regular file')
        before = identity(info)
        result = run_process(['exiftool', '-json', '-G1', '-a'] +
                             (['-n'] if numeric else []) + ['-' + tag for tag in tags] + [f'/proc/{os.getpid()}/fd/{fd}'])
        # A recognized FileType is useful even when ExifTool flags incomplete
        # metadata. Callers decide whether an Error prevents their operation.
        rows = json.loads(result.stdout)
        if len(rows) != 1 or not isinstance(rows[0], dict): raise ValueError('Invalid metadata response')
        if before != identity(os.fstat(fd)) or before != identity(os.lstat(path)):
            raise ValueError('Source changed during inspection')
        return rows[0], before, result.returncode
    finally:
        os.close(fd)


def clean_text(value, limit=16384):
    if isinstance(value, dict): value = value.get('x-default', '')
    if not isinstance(value, (str, int, float)): return ''
    value = str(value).replace('\r\n', '\n').replace('\r', '\n')
    value = ''.join(c for c in value if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127)).strip()
    return value if len(value) <= limit else value[:limit-1] + '…'


def camera_details(row, selected):
    """Format only explicit, usable source values, in the checkbox order."""
    def positive(value):
        if type(value) not in (str, int, float): return None
        text = str(value).strip()
        if len(text) > 100 or not re.fullmatch(r'\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?:/\d+(?:\.\d+)?)?', text):
            return None
        try:
            parts = text.split('/')
            number = float(parts[0])
            if len(parts) == 2: number /= float(parts[1])
            return number if math.isfinite(number) and number > 0 else None
        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    def formatted(key, value):
        if key in ('make', 'model', 'lens'):
            return clean_text(value, 4096) if isinstance(value, str) else ''
        if key == 'capture_date':
            if not isinstance(value, str) or len(value) > 128: return ''
            # Retain the embedded wall clock, fractions and offset; no timezone
            # guessing, filesystem fallback, or partial/zero dates.
            text = re.sub(r'^(\d{4}):(\d{2}):(\d{2})', r'\1-\2-\3', value.strip())
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?', text):
                return ''
            try: dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
            except ValueError: return ''
            return text.replace('T', ' ')
        number = positive(value)
        if number is None: return ''
        if key == 'focal_length': return f'{number:g}mm'
        if key == 'aperture': return f'f/{number:g}'
        if key == 'iso': return str(round(number)) if number.is_integer() else ''
        reciprocal = 1 / number
        if not math.isfinite(reciprocal): return ''
        denominator = round(reciprocal)
        if number < 1 and denominator >= 2 and abs(reciprocal - denominator) <= denominator * .0001:
            return f'1/{denominator} sec'
        return f'{number:g} sec'

    values = {}
    for _, key in CAMERA_FIELDS:
        if selected[key]:
            values[key] = next((text for tag in CAMERA_TAGS[key]
                                if (text := formatted(key, row.get(tag)))), '')
    make, model = values.get('make', ''), values.get('model', '')
    if make and model and re.search(r'(?<!\w)' + re.escape(make) + r'(?!\w)', model, re.IGNORECASE):
        values['make'] = ''
    return '\n'.join(f'{label}: {values[key]}' for label, key in CAMERA_FIELDS if values.get(key))


def metadata(path):
    try:
        row, _, _ = read_tags(path, TAGS)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return dict(capture='', camera='', caption='')
    def first(keys):
        return next((text for key in keys if (text := clean_text(row.get(key)))), '')
    return dict(capture=first(CAPTURE), camera=' — '.join(filter(None, (first(CAMERA), first(LENS)))),
                caption=first(DESCRIPTION))


def caption_text(path, mode, index=1, date=False, camera=False, custom=''):
    fields = metadata(path) if mode in ('capture', 'camera', 'embedded') or date or camera else {}
    filename = clean_text(Path(path).name)
    primary = {'none': '', 'number': str(index), 'filename': filename,
               'both': f'{index}. {filename}', 'capture': fields.get('capture', ''),
               'camera': fields.get('camera', ''), 'embedded': fields.get('caption', ''),
               'custom': clean_text(custom)}[mode]
    return '\n'.join(filter(None, (primary, fields.get('capture', '') if date else '',
                                  fields.get('camera', '') if camera else '')))


def paint_label(text, output, width, height, pixels, background):
    """Wrap within a fixed pixel rectangle, eliding the last visible line."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter, QTextLayout, QTextOption
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(Qt.black if background == 'black' else Qt.white)
    painter = QPainter(image)
    try:
        painter.setPen(Qt.white if background == 'black' else Qt.black)
        font = QFont('DejaVu Sans'); font.setPixelSize(pixels)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        pad = max(2, pixels // 5); usable = width - pad * 2
        y = float(pad); paragraphs = clean_text(text).split('\n')
        option = QTextOption(); option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layouts = []; visible = []; truncated = False
        # Keep each layout alive until its QTextLines have been painted.
        for paragraph in paragraphs:
            encoded = (paragraph or ' ').encode('utf-16-le')
            layout = QTextLayout(paragraph or ' ', font); layout.setTextOption(option)
            layouts.append(layout); layout.beginLayout()
            try:
                while True:
                    line = layout.createLine()
                    if not line.isValid(): break
                    line.setLineWidth(usable)
                    if y + line.height() > height - pad:
                        truncated = True; break
                    start, length = line.textStart(), line.textLength()
                    literal = encoded[start*2:(start+length)*2].decode('utf-16-le')
                    visible.append((line, y, literal)); y += line.height()
            finally:
                layout.endLayout()
            if truncated: break
        tail = visible.pop() if truncated and visible else None
        painter.setClipRect(0, 0, width, height)
        for line, top, _ in visible: line.draw(painter, QPointF(pad, top))
        if tail:
            shortened = metrics.elidedText(tail[2].rstrip() + '…', Qt.ElideRight, usable)
            painter.drawText(QPointF(pad, tail[1] + metrics.ascent()), shortened)
    finally:
        painter.end()
    save_image(image, output)


def save_image(image, output):
    if not image.save(output, 'PNG'): raise ValueError('Could not write annotation image')


def automatic_contactsheet_plan(dimensions, width, height, dpi, labels, font_size, fit):
    """Plan integer pixel rectangles independently of decoding and page rendering.

    At most twelve photographs share a page. Candidate grids are scored by
    visible image area, size balance, empty slots and (for Fill) retained source
    area. A physical minimum image size can reduce page capacity. Page counts
    are balanced, then every page is planned against its own ordered sources.
    """
    import math
    margin = round(dpi * 0.35)
    gap = max(1, round(dpi * 0.10))
    heading_height = round(dpi * 0.50)
    top = margin + heading_height + gap
    usable_width = width - 2 * margin
    usable_height = height - top - margin
    line_count = {'none': 0, 'number': 1, 'capture': 2, 'filename': 3,
                  'both': 3, 'camera': 3, 'embedded': 4}[labels]

    def page_layout(sources):
        count = len(sources)
        candidates = []
        for cols in range(1, count + 1):
            rows = (count + cols - 1) // cols
            cell_width = (usable_width - (cols - 1) * gap) // cols
            max_height = (usable_height - (rows - 1) * gap) // rows
            points = {'small': 8, 'medium': 10, 'large': 12}.get(font_size)
            if points is None:
                points = max(9, min(12, min(cell_width, max_height) * 72 / dpi * 0.075))
            pixels = max(4, round(points * dpi / 72))
            caption_height = (math.ceil(line_count * pixels * 1.35) + 2 * max(2, pixels // 5)
                              if line_count else 0)
            max_photo_height = max_height - caption_height
            if cell_width < 16 or max_photo_height < 16: continue
            ratios = [w / h for w, h in sources]
            # Try the available height and source-shaped boxes. Fit boxes are
            # trimmed below when no source would use their extra blank height.
            photo_heights = {max_photo_height}
            photo_heights.update(min(max_photo_height, max(16, round(cell_width / ratio)))
                                 for ratio in ratios)
            for photo_height in sorted(photo_heights):
                if fit == 'fit':
                    photo_height = min(photo_height, math.ceil(max(cell_width / r for r in ratios)))
                cell_height = photo_height + caption_height
                areas, short_edges, retained = [], [], []
                for ratio in ratios:
                    fitted_width = min(cell_width, photo_height * ratio)
                    fitted_height = min(photo_height, cell_width / ratio)
                    keep = min(ratio / (cell_width / photo_height), (cell_width / photo_height) / ratio)
                    areas.append(fitted_width * fitted_height if fit == 'fit' else cell_width * photo_height)
                    short_edges.append(min(fitted_width, fitted_height) if fit == 'fit' else min(cell_width, photo_height))
                    retained.append(keep)
                total = sum(areas)
                balance = (min(areas) / (total / count)) ** 0.15
                slots = (count / (cols * rows)) ** 0.15
                density = (total / (count * cell_width * photo_height)) ** 0.10
                crop = (sum(retained) / count) ** 0.65 if fit == 'fill' else 1
                score = total * balance * slots * density * crop
                candidates.append((min(short_edges) >= dpi * 1.05, score,
                                   (cols, rows, cell_width, cell_height, caption_height, pixels)))
        if not candidates: raise ValueError('No usable contact-sheet geometry')
        readable, _, geometry = max(candidates, key=lambda item: (item[0], item[1]))
        return readable, geometry

    previous_pages = 0
    for capacity in range(12, 0, -1):
        pages = (len(dimensions) + capacity - 1) // capacity
        if pages == previous_pages: continue
        previous_pages = pages
        first, plans, readable = 0, [], True
        for page in range(pages):
            count = len(dimensions) // pages + (page < len(dimensions) % pages)
            last = first + count
            fits, geometry = page_layout(dimensions[first:last])
            readable = readable and (fits or count == 1)
            cols, rows, cell_width, cell_height, caption_height, pixels = geometry
            if (cols * cell_width + (cols - 1) * gap > usable_width or
                    rows * cell_height + (rows - 1) * gap > usable_height or
                    cell_height <= caption_height):
                raise ValueError('Contact-sheet cells exceed the printable region')
            plans.append((first, last, *geometry, margin, gap, top, heading_height))
            first = last
        if readable: return plans
    raise ValueError('Unable to plan contact-sheet pages')


def write_contactsheet_plan(arguments):
    source, output, width, height, dpi, labels, font_size, fit, expected = arguments
    dimensions = []
    for record in Path(source).read_text().splitlines():
        w, h, orientation = record.split('|')
        w, h = int(w), int(h)
        if w <= 0 or h <= 0: raise ValueError('Invalid source dimensions')
        if orientation in ('LeftTop', 'RightTop', 'RightBottom', 'LeftBottom'):
            w, h = h, w
        dimensions.append((w, h))
    if not dimensions or len(dimensions) != int(expected):
        raise ValueError('Source count changed during geometry inspection')
    plans = automatic_contactsheet_plan(dimensions, int(width), int(height), int(dpi), labels, font_size, fit)
    Path(output).write_text(''.join('\t'.join(map(str, page)) + '\n' for page in plans))
    return 0


def main():
    # All text travels as data arguments; output and dimensions are job-owned.
    # The shell publication monitor owns this process group and all delegates.
    from kim_psd_source import _SHELL_GROUP
    _SHELL_GROUP.set(True)
    source, output, width, height, pixels, background, mode, index, date, camera, custom = sys.argv[1:]
    width, height, pixels = int(width), int(height), int(pixels)
    if not (16 <= width <= 10000 and 8 <= height <= 10000 and 4 <= pixels <= 512):
        raise ValueError('Invalid annotation dimensions')
    if background not in ('white', 'black'): raise ValueError('Invalid annotation background')
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv[:1])
    paint_label(caption_text(source, mode, int(index), date == 'true', camera == 'true', custom),
                output, width, height, pixels, background)
    return 0


if __name__ == '__main__':
    raise SystemExit(write_contactsheet_plan(sys.argv[2:]) if sys.argv[1:2] == ['--plan-contactsheet'] else main())
