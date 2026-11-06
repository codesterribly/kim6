"""Capture clocks are separate from filesystem instants; no implicit local zone."""
import datetime as dt
import re
from kim_recipe_core import RecipeError


def timezone(value):
    if value == 'unknown': return None
    if value == 'UTC': return dt.timezone.utc
    if not isinstance(value, str) or not re.fullmatch(r'[+-]\d{2}:\d{2}', value):
        raise RecipeError('Choose a timezone: unknown camera timezone, UTC, or an explicit ±HH:MM offset.')
    hours, minutes = map(int, value[1:].split(':'))
    if minutes > 59 or hours > 14 or (hours == 14 and minutes):
        raise RecipeError('Timezone offset must be between −14:00 and +14:00.')
    return dt.timezone(dt.timedelta(minutes=(hours * 60 + minutes) * (-1 if value[0] == '-' else 1)))


def specific(value, zone):
    if value == '':
        raise RecipeError('Choose an image capture date and time to continue.')
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?', value):
        raise RecipeError('Enter a complete image capture date and time (YYYY-MM-DD HH:MM:SS); date-only values are ambiguous.')
    tz=timezone(zone)
    try:
        result = dt.datetime.fromisoformat(value).replace(tzinfo=tz)
    except ValueError as exc:
        raise RecipeError('That image capture date or time is impossible. Correct the date and time above.') from exc
    return result, value.split('.', 1)[1] if '.' in value else ''


def explicit(value, zone):
    """Replacing a camera clock assigns whole seconds and clears stale precision.

    Reading/adjusting existing clocks and copying file instants still retain
    their original precision; only an explicitly assigned clock uses this path.
    """
    capture, _ = specific(value, zone)
    return capture.replace(microsecond=0), ''


def assignments(capture, fraction, fields='capture', legacy=True):
    """Write EXIF clocks plus their XMP mirrors; IPTC-IIM only where writable.

    A deliberate unknown zone clears old offsets. EXIF subsecond tags retain up
    to nine supplied digits, XMP retains them too; IPTC-IIM has second precision.
    No filesystem timestamps are changed here.
    """
    wall = f'{capture.year:04d}:' + capture.strftime('%m:%d %H:%M:%S')
    offset = capture.strftime('%z')
    offset = offset[:3] + ':' + offset[3:] if offset else ''
    iso = f'{capture.year:04d}:' + capture.strftime('%m:%d %H:%M:%S') + ('.' + fraction if fraction else '') + offset
    tags = {'EXIF:DateTimeOriginal': wall, 'EXIF:SubSecTimeOriginal': fraction,
            'EXIF:OffsetTimeOriginal': offset, 'XMP-exif:DateTimeOriginal': iso,
            'XMP-photoshop:DateCreated': iso}
    if legacy:
        tags.update({'IPTC:DateCreated': f'{capture.year:04d}:' + capture.strftime('%m:%d'),
                     # ExifTool supplies the computer's zone for a bare IPTC
                     # time. Unknown camera zones must never acquire that guess.
                     'IPTC:TimeCreated': capture.strftime('%H:%M:%S') + offset if offset else ''})
    if fields == 'all':
        tags.update({'EXIF:CreateDate': wall, 'EXIF:ModifyDate': wall,
                     'EXIF:SubSecTimeDigitized': fraction, 'EXIF:SubSecTime': fraction,
                     'EXIF:OffsetTimeDigitized': offset, 'EXIF:OffsetTime': offset,
                     'XMP-xmp:CreateDate': iso, 'XMP-xmp:ModifyDate': iso})
    return ['-' + key + '=' + value for key, value in tags.items()]


def display(capture, fraction=''):
    value = f'{capture.year:04d}-' + capture.strftime('%m-%d %H:%M:%S') + ('.' + fraction if fraction else '')
    return value + (' ' + capture.strftime('%z') if capture.tzinfo else ' (timezone unknown)')


def epoch_ns(capture, fraction):
    """A camera clock is not an instant until its offset is explicitly known."""
    if capture is None:
        raise RecipeError('No image capture date was found. No date was changed. Choose Set Image Capture Date… to enter one.')
    if capture.tzinfo is None:
        raise RecipeError('The camera timezone is unknown. Choose the timezone where this image was captured before setting its File Modification Date.')
    delta = capture.astimezone(dt.timezone.utc) - dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
    return (delta.days*86400 + delta.seconds)*10**9 + int((fraction+'000000000')[:9])
