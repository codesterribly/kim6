"""Image location planning and verification, deliberately independent of Qt.

GPX matching uses ordered segment-local fixes, never extrapolation. Execution
writes the approved numeric result rather than running a second interpolation.
Grid generalization divides the WGS84 meridian into approximately grid-sized
bands, then each band's parallel into approximately grid-sized cells. Cell
centres are deterministic; displacement is a spherical distance estimate, not
an anonymity radius or a measurement of receiver accuracy.
"""
from __future__ import annotations

import bisect
import contextlib
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import selectors
import signal
import time
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kim_preview import (absolute, identity, inspection_path, base_entry, allocate,
                         finish_entry, verify_entry)
from kim_process import checkpoint, inspection_context

TITLES = {'gpx': 'GPX Geotagging', 'copy': 'Copy GPS from Image…',
          'apply': 'Modify GPS on Images…', 'report': 'Inspect Location Metadata',
          'reduce': 'Approximate GPS Location'}
FORMATS = {'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'}, 'WEBP': {'.webp'},
           'TIFF': {'.tif', '.tiff'}, 'HEIC': {'.heic', '.heif', '.hif'},
           'HEIF': {'.heic', '.heif', '.hif'}, 'AVIF': {'.avif'}}
MAX_FILES = 1000
MAX_GPX = 32 * 1024 * 1024
MAX_POINTS = 250000
MAX_METADATA = 4 * 1024 * 1024
MAX_BATCH_METADATA = 64 * 1024 * 1024
UTC = dt.timezone.utc
EPOCH = dt.datetime(1970, 1, 1, tzinfo=UTC)
PLACE_NAMES = {'City', 'State', 'Province-State', 'ProvinceState', 'Country',
               'CountryName', 'CountryCode', 'Country-PrimaryLocationName',
               'Country-PrimaryLocationCode', 'Sub-location', 'Sublocation',
               'Location', 'LocationName', 'LocationID', 'LocationIdentifier',
               'WorldRegion', 'LocationCode', 'LocationName-eng', 'ContentLocationCode',
               'ContentLocationName'}
STRUCTURES = ('LocationCreated', 'LocationShown', 'RatingRegion')
COORDINATE_CATEGORIES = {'camera': 'Photo GPS location',
                         'destination': 'Destination / subject position',
                         'depicted': 'Depicted location',
                         'structured': 'Other structured location',
                         'unknown': 'Unknown / ambiguous coordinate source'}
NARRATIVE = {'Description', 'ImageDescription', 'Caption-Abstract', 'Title', 'Comment'}
# Clear the whole EXIF GPS IFD and XMP GPS family, including stale fix details.
GPS_CLEAR = ['-GPS:all=', '-XMP:GPS*=']
GPS_EXT_CLEAR = ['-XMP-iptcExt:' + p + 'GPS*=' for p in STRUCTURES]
READ_TAGS = ['-EXIF:all', '-IPTC:all', '-XMP:all', '-MakerNotes:all',
             '-Location:all', '-GPS*', '-FileType', '-EncodingProcess', '-Warning', '-Error']


def number(value, label='number', low=None, high=None):
    """Decimal degrees / signed numeric input; no locale or fraction guessing."""
    if isinstance(value, bool) or len(str(value)) > 128 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', str(value).strip()):
        raise ValueError('Invalid ' + label + ': use signed decimal numbers.')
    try: result = float(Decimal(str(value)))
    except (InvalidOperation, OverflowError) as exc: raise ValueError('Invalid ' + label) from exc
    if not math.isfinite(result) or (low is not None and result < low) or (high is not None and result > high):
        raise ValueError(label + ' is outside the supported range.')
    return result


def coordinate(value, ref, latitude):
    limit, positive, negative = (90, 'N', 'S') if latitude else (180, 'E', 'W')
    result = number(value, 'latitude' if latitude else 'longitude', -limit, limit)
    if ref is not None:
        ref = str(ref).upper().strip()
        if ref not in (positive, negative): raise ValueError('Invalid GPS hemisphere reference.')
        if result < 0 and ref == positive: raise ValueError('Coordinate sign contradicts its hemisphere.')
        result = abs(result) * (-1 if ref == negative else 1)
    return result


def descriptor_identity(fd):
    info = os.fstat(fd)
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_uid, info.st_gid]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate metadata keys could not be distinguished.')
        result[key] = value
    return result


def location_process(args, *, pass_fds=(), limit=MAX_METADATA, timeout=120):
    """Cancellable ExifTool pipes with a hard aggregate output bound."""
    checkpoint()
    # During execution the dispatcher adapter owns the entire process group.
    # GUI inspection owns its own group so a cancelled worker can reap it.
    own_group = not os.environ.get('KIM_LOCATION_JOB')
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               pass_fds=pass_fds, start_new_session=own_group)
    outputs = [bytearray(), bytearray()]; started = time.monotonic()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 0)
            selector.register(process.stderr, selectors.EVENT_READ, 1)
            while selector.get_map():
                checkpoint()
                if time.monotonic() - started > timeout: raise ValueError('Location metadata inspection / staging timed out')
                for key, _ in selector.select(.1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk: selector.unregister(key.fileobj); continue
                    outputs[key.data].extend(chunk)
                    if len(outputs[0]) + len(outputs[1]) > limit:
                        raise ValueError('ExifTool location output exceeds the bounded metadata limit')
        while process.poll() is None:
            checkpoint()
            if time.monotonic() - started > timeout: raise ValueError('ExifTool timed out')
            time.sleep(.05)
        return subprocess.CompletedProcess(args, process.returncode,
            outputs[0].decode('utf-8', errors='strict'), outputs[1].decode('utf-8', errors='replace'))
    finally:
        if process.poll() is None:
            try:
                if own_group: os.killpg(process.pid, signal.SIGTERM)
                else: process.terminate()
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    if own_group: os.killpg(process.pid, signal.SIGKILL)
                    else: process.kill()
                except ProcessLookupError: pass
                process.wait()
        process.stdout.close(); process.stderr.close()


def read_many(paths):
    """Bounded groups of descriptor-backed, no-atime ExifTool inspections.

    Family 4 retains duplicate fields; families 3 and 5 identify their actual
    document and metadata path. Copy numbers are per-tag, not record IDs. Structured XMP is kept
    structured so coordinates from different depicted locations never combine.
    No synthetic Composite coordinates are treated as independent stored GPS.
    """
    results = {}; total_bytes = 0
    for start in range(0, len(paths), 12):
        checkpoint(); batch = paths[start:start + 12]
        with contextlib.ExitStack() as stack:
            opened = []; before = {}
            for path in batch:
                try:
                    before[path] = identity(path)
                    name, fd = stack.enter_context(inspection_path(path))
                    if descriptor_identity(fd) != before[path]: raise ValueError('Source changed while opening metadata inspection')
                    opened.append((path, name, fd))
                except (OSError, ValueError) as exc: results[path] = {'error': str(exc)}
            if not opened: continue
            args = ['exiftool', '-q', '-json', '-G1:2:3:4:5', '-a', '-n', '-struct', *READ_TAGS,
                    '--', *[p[1] for p in opened]]
            try:
                response = location_process(args, pass_fds=tuple(p[2] for p in opened), limit=MAX_METADATA * len(opened))
            except (OSError, ValueError) as exc:
                checkpoint()
                for path, _, _ in opened: results[path] = {'error': str(exc)}
                continue
            if len(response.stdout) > MAX_METADATA * len(opened):
                raise ValueError('Location metadata exceeds the inspection limit.')
            # A signal / unexpected exit is a process failure, not a file warning.
            if response.returncode not in (0, 1):
                for path, _, _ in opened: results[path] = inspection_problem(response.stderr.splitlines(), response.returncode, batch_failure=True)
                continue
            try: records = json.loads(response.stdout, object_pairs_hook=unique_object)
            except (ValueError, TypeError):
                for path, _, _ in opened:
                    results[path] = inspection_problem(['ExifTool returned ambiguous or unreadable metadata', *response.stderr.splitlines()], response.returncode, batch_failure=len(opened) > 1)
                continue
            if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
                raise ValueError('Invalid ExifTool metadata response')
            by_name = {r.get('SourceFile'): r for r in records}
            if len(by_name) != len(records) or set(by_name) != {p[1] for p in opened}:
                for path, _, _ in opened: results[path] = {'error': 'ExifTool returned duplicate, unexpected or incomplete source records'}
                continue
            problems = {name: [k.split(':')[-1] + ': ' + str(v) for k, v in record.items() if k.split(':')[-1] in ('Warning', 'Error')]
                        for name, record in by_name.items()}
            unattributed = []
            for line in response.stderr.splitlines():
                if not line.strip() or processing_summary(line): continue
                names = [name for name in by_name if line.endswith(' - ' + name)]
                if len(names) == 1: problems[names[0]].append(line)
                else: unattributed.append(line)
            file_error = any(str(v) for record in records for k, v in record.items() if k.split(':')[-1] == 'Error')
            file_error = file_error or any(line.lstrip().startswith('Error:') for lines in problems.values() for line in lines)
            unexplained_exit = response.returncode and not file_error
            if len(opened) > 1 and (unattributed or unexplained_exit):
                # At most one individual retry per opened source. Reopening uses
                # the same cancellation, pipe limits and O_NOATIME safeguards.
                isolated = {}
                for path, _, _ in opened:
                    checkpoint(); isolated.update(read_many([path]))
                observed = {d for result in isolated.values() for d in result.get('diagnostics', [])}
                unresolved = [line for line in unattributed if diagnostic_text(line) not in observed]
                explained = any(r.get('inspection_exit') == 1 and r.get('diagnostics') for r in isolated.values())
                for path, name, _ in opened:
                    result = isolated[path]
                    if unresolved or (unexplained_exit and not explained):
                        result = inspection_problem(unresolved or ['ExifTool failed without a per-file diagnostic'], response.returncode, batch_failure=True)
                    elif problems[name]:
                        result = inspection_problem(problems[name], response.returncode, names=(name,))
                    if identity(path) != before[path]: result = {'error': 'Source changed during metadata inspection'}
                    total_bytes += len(json.dumps(result))
                    if total_bytes > MAX_BATCH_METADATA: raise ValueError('Batch metadata exceeds 64 MiB; select fewer images')
                    results[path] = result
                continue
            for path, name, fd in opened:
                record = by_name.get(name)
                if record is None or identity(path) != before[path]:
                    results[path] = {'error': 'Source changed or metadata inspection was incomplete.'}; continue
                record_bytes = len(json.dumps(record)); total_bytes += record_bytes
                if total_bytes > MAX_BATCH_METADATA: raise ValueError('Batch metadata exceeds 64 MiB; select fewer images')
                if record_bytes > MAX_METADATA:
                    results[path] = {'error': 'Metadata exceeds the per-image inspection limit.'}; continue
                diagnostics = problems[name] + unattributed
                if diagnostics or unexplained_exit:
                    results[path] = inspection_problem(diagnostics or ['ExifTool failed without a per-file diagnostic'], response.returncode, names=(name,))
                else: results[path] = {'raw': record, 'identity': before[path]}
    return results


def inspection_problem(diagnostics, exit_code, *, names=(), batch_failure=False):
    # Warnings are retained and refuse a safety-sensitive plan, but remain
    # distinguishable from actual file errors and process-wide failures.
    diagnostics = list(dict.fromkeys(line.strip() for line in diagnostics if line.strip()))
    warnings = [diagnostic_text(d, names) for d in diagnostics if d.startswith('Warning:')]
    errors = [diagnostic_text(d, names) for d in diagnostics if d.startswith('Error:')]
    kind = 'batch failure' if batch_failure else 'image error' if errors else 'image warning' if warnings else 'inspection failure'
    return dict(error='GPS information could not be read reliably (' + kind + '): ' +
                '; '.join(diagnostics or ['ExifTool exit code ' + str(exit_code)]),
                diagnostics=[diagnostic_text(d, names) for d in diagnostics],
                inspection_warnings=warnings, inspection_errors=errors,
                inspection_exit=exit_code, inspection_problem=kind)


def processing_summary(line):
    """Only ExifTool's successful read count is informational, never warnings.

    A single -q normally suppresses this. Keep the narrow recognition here for
    wrappers / older installations, without swallowing failures or diagnostics.
    """
    return re.fullmatch(r'\s*\d+ image files? read\s*', line) is not None


def diagnostic_text(message, names=()):
    for name in names:
        if message.endswith(' - ' + name): message = message[:-len(' - ' + name)]
    return re.sub(r'^(?:Warning|Error):\s*', '', message.strip())


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, child in value.items(): yield from leaves(child, prefix + '.' + key if prefix else key)
    elif isinstance(value, list):
        for index, child in enumerate(value): yield from leaves(child, prefix + '[' + str(index) + ']')
    else: yield prefix, value


def tag_parts(key):
    parts = key.split(':'); return parts[0], parts[-1]


def record_context(key):
    """Ignore description / per-tag copy groups, retain document and storage path.

    -G1:2:4 can label native GPSLatitude Copy1 because Composite GPSLatitude
    has the primary name, while GPSLatitudeRef has no Copy group at all.
    The reader also requests families 3/5 so genuine stores remain separate.
    """
    parts = key.split(':')
    context = parts[2:-1] if len(parts) > 2 else []
    return ':'.join([parts[0], *[p for p in context if not re.fullmatch(r'Copy\d+', p)]])


def sibling_values(flattened, key, name):
    context = record_context(key)
    return [value for other, value in flattened.items()
            if record_context(other) == context and tag_parts(other)[1] == name]


def place_base(name):
    # XMP language alternatives are location text too, including non-English
    # place fields. This does not classify narrative captions as location.
    return re.sub(r'-[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$', '', name)


def location_kind(key):
    group, name = tag_parts(key)
    if group in ('Composite', 'File', 'System', 'ExifTool'): return None
    tail = re.split(r'[.\[]', name)[-1].rstrip(']')
    if name in NARRATIVE: return None
    if (group == 'GPS' or 'GPS' in name or 'Geotag' in name or
            name in ('LocationISO6709', 'LocationInformation', 'Geolocation', 'Position', 'Coordinates') or
            name.endswith(('Latitude', 'Longitude', 'LatitudeRef', 'LongitudeRef'))): return 'gps'
    if (tail in PLACE_NAMES or name in PLACE_NAMES or place_base(name) in PLACE_NAMES or
            any(name.startswith(p) for p in STRUCTURES) or
            name in ('LocationInformation', 'LocationISO6709', 'LocationAccuracyHorizontal', 'GPSPosition')):
        return 'place'
    if 'Location' in key.split(':')[1:-1]: return 'place'
    return None


def display_position(position):
    if position is None: return '(camera coordinates unavailable)'
    return f'{position[0]:.12f}, {position[1]:.12f} ({"N" if position[0] >= 0 else "S"}, {"E" if position[1] >= 0 else "W"})'


def coordinate_category(key):
    group, name = tag_parts(key)
    if group == 'XMP-iptcExt' and name.startswith('LocationShown'): return 'depicted'
    if group == 'XMP-iptcExt' and any(name.startswith(p) for p in STRUCTURES): return 'structured'
    if '.' in name or '[' in name: return 'structured'
    if name.startswith('GPSDest'): return 'destination'
    if group in ('GPS', 'XMP-exif') and name.startswith('GPS'): return 'camera'
    return 'unknown'


def coordinate_scope(key, prefix):
    category = coordinate_category(key)
    # Camera / destination duplicates describe one position. A structured array
    # can legitimately describe many places, as can unrelated unknown sources.
    return category, category if category in ('camera', 'destination') else record_context(key) + ':' + prefix


def summarize(raw):
    fields = {k: v for k, v in raw.items() if location_kind(k)}
    gps = {}; places = {}; issues = []; records = {}; details = {}
    categories = {c: dict(records=[], issues=[], optional_issues=[], duplicate_records=0) for c in COORDINATE_CATEGORIES}
    def issue(category, message, optional=False):
        categories[category]['optional_issues' if optional else 'issues'].append(message); issues.append(message)
    for key, value in fields.items():
        group, name = tag_parts(key)
        if name in ('GPSPosition', 'LocationISO6709', 'Geolocation', 'Position', 'Coordinates', 'LocationInformation') and not isinstance(value, (dict, list)):
            issue(coordinate_category(key), key + ': stored coordinate information is not an explicit latitude/longitude record')
        if location_kind(key) == 'place':
            text_leaves = [(sub, item) for sub, item in leaves(value, key) if 'GPS' not in sub and item not in (None, '')]
            if text_leaves: places[key] = value
        for sub, item in leaves(value, key):
            # Structured list members retain their array index in the record key.
            # Match only the logical tag / structured leaf, never group labels.
            logical = tag_parts(sub)[1]
            match = re.fullmatch(r'(.*?)(GPSDestLatitude|GPSDestLongitude|GPSLatitude|GPSLongitude|Latitude|Longitude)(Ref)?(\[\d+\])?', logical)
            if match:
                prefix, axis, ref, index = match.groups()
                family = axis.removesuffix('Latitude').removesuffix('Longitude')
                source = record_context(sub) + ':' + prefix + family + (index or '')
                record = records.setdefault(source, dict(values={}, tags={}, category=coordinate_category(sub),
                                                        scope=coordinate_scope(sub, prefix + (index or ''))))
                component = ('lat' if axis.endswith('Latitude') else 'lon') + ('ref' if ref else '')
                record['values'].setdefault(component, []).append(item)
                record['tags'].setdefault(component, []).append(sub)
                gps[sub] = item
            elif location_kind(key) == 'gps' or location_kind(sub) == 'gps': gps[sub] = item
            if any(t in sub for t in ('Altitude', 'TimeStamp', 'DateStamp', 'DateTime', 'HPositioningError', 'ImgDirection', 'Accuracy')):
                details[sub] = item
    positions = []; cohorts = {}
    for source, stored in records.items():
        values = stored['values']; category = stored['category']
        record = {component: items[0] for component, items in values.items()}
        categories[category]['duplicate_records'] += max(len(items) for items in values.values()) - 1
        result = dict(source=source, category=category, tags=stored['tags'], position=None,
                      stored_digits=[], issues=[], conflict=False)
        categories[category]['records'].append(result)
        cohorts.setdefault(stored['scope'], []).append(result)
        try:
            for component, items in values.items():
                normalized = [str(v).strip().upper() if component.endswith('ref') else number(v, component) for v in items]
                if any(v != normalized[0] for v in normalized[1:]):
                    raise ValueError('Contradictory ' + component + ' fields in the same coordinate record')
            if 'lat' not in record or 'lon' not in record: raise ValueError('Incomplete coordinate pair')
            if source.startswith('GPS:') and ('latref' not in record or 'lonref' not in record):
                raise ValueError('EXIF coordinates lack hemisphere references')
            lat = coordinate(record['lat'], record.get('latref'), True)
            lon = coordinate(record['lon'], record.get('lonref'), False)
            result.update(position=[lat, lon], stored_digits=[decimal_digits(record['lat']), decimal_digits(record['lon'])])
            positions.append(result)
        except ValueError as exc:
            message = source + ': ' + str(exc)
            result['issues'].append(message); issue(category, message)
    # Non-WGS84 positions cannot be safely interpreted as WGS84.
    for key, value in gps.items():
        if key.endswith('GPSMapDatum') and re.sub(r'[^A-Z0-9]', '', str(value).upper()) not in ('WGS84', 'WGS1984'):
            category = coordinate_category(key)
            issue(category, key + ': non-WGS84 datum')
            if category == 'camera': issue('destination', key + ': non-WGS84 datum also applies to GPS destination')
    flattened = dict(leaves(fields))
    for name, low, high in [('GPSAltitude', -12000, 100000), ('GPSImgDirection', 0, 359.999999), ('GPSHPositioningError', 0, 10000000)]:
        values = {}
        for key in flattened:
            match = re.search(r'(?:^|[:.])' + name + r'$', key)
            if not match: continue
            category, scope = coordinate_scope(key, key[:-len(name)])
            try: values.setdefault((category, scope), []).append((key, gps_detail(flattened, key, name, low, high)))
            except ValueError as exc: issue(category, key + ': ' + str(exc), optional=True)
        for (category, _), entries in values.items():
            if any(abs(v[0] - entries[0][1][0]) > 1e-6 or v[1] != entries[0][1][1] for _, v in entries):
                issue(category, 'Conflicting ' + name + ': ' + '; '.join(key for key, _ in entries), optional=True)
    for key, value in flattened.items():
        name = tag_parts(key)[1]
        if name.endswith(('GPSAltitudeRef', 'GPSImgDirectionRef')):
            valid = ('0', '1', '2', '3') if name.endswith('GPSAltitudeRef') else ('T', 'M')
            if str(value) not in valid:
                issue(coordinate_category(key), key + ': unknown reference ' + str(value), optional=True)
            elif not sibling_values(flattened, key, name[:-3]):
                issue(coordinate_category(key), key + ': reference is recorded without its value', optional=True)
    for (category, _), entries in cohorts.items():
        valid = [r for r in entries if r['position'] is not None]
        categories[category]['duplicate_records'] += max(0, len(valid) - 1)
        if valid and any(not same_position(r['position'], valid[0]['position']) for r in valid):
            message = 'Conflicting ' + COORDINATE_CATEGORIES[category].lower() + ' records: ' + '; '.join(r['source'] for r in valid)
            issue(category, message)
            for record in valid: record['conflict'] = True; record['issues'].append(message)
    camera = categories['camera']
    position = camera['records'][0]['position'] if camera['records'] and not camera['issues'] else None
    state = 'conflict' if camera['issues'] else 'coordinates' if positions else 'place-only' if places else 'missing'
    # Low digit counts describe stored numeric resolution only, not accuracy.
    if state == 'coordinates' and all(max(p['stored_digits']) <= 3 for p in positions): state = 'generalized'
    return dict(state=state, format=metadata_value(raw, 'File', 'FileType') or 'Unknown', position=position,
                records=[r for c in categories.values() for r in c['records']], categories=categories, fields=fields,
                gps=gps, places=places, details=details, issues=issues,
                duplicate_records=sum(c['duplicate_records'] for c in categories.values()),
                accuracy='; '.join(k + ': ' + str(v) + ' m (recorded horizontal positioning error)' for k, v in details.items() if 'HPositioningError' in k) or 'Unknown; numeric digits do not establish measurement accuracy')


def decimal_digits(value):
    try: return max(0, -Decimal(str(value)).as_tuple().exponent)
    except (InvalidOperation, TypeError): return 0


def metadata_value(raw, group, name):
    values = [v for k, v in raw.items() if k.split(':')[0] == group and k.split(':')[-1] == name]
    if len({json.dumps(v, sort_keys=True) for v in values}) > 1: raise ValueError('Contradictory ' + name + ' fields')
    return values[0] if values else None


def same_position(first, second):
    return abs(first[0] - second[0]) <= 1e-7 and abs(((first[1] - second[1] + 180) % 360) - 180) <= 1e-7


def gps_detail(flattened, key, name, low, high):
    # Altitude magnitudes are unsigned in EXIF; validate the signed result below.
    result = number(flattened[key], name, None if name == 'GPSAltitude' else low, high); ref = None
    if name == 'GPSAltitude':
        refs = sibling_values(flattened, key, tag_parts(key)[1] + 'Ref')
        if not refs: raise ValueError('Altitude reference is absent; its sign and vertical reference cannot be determined. Latitude/longitude validity is independent of altitude.')
        if any(str(r) != str(refs[0]) for r in refs): raise ValueError('Conflicting altitude references')
        ref = str(refs[0])
        # EXIF 3.0: 0/1 use the ellipsoidal surface, 2/3 sea level.
        if ref not in ('0', '1', '2', '3'): raise ValueError('Unknown altitude reference: ' + ref)
        if result < 0 and ref in ('0', '2'): raise ValueError('Altitude sign contradicts reference')
        result = abs(result) * (-1 if ref in ('1', '3') else 1)
        number(result, 'signed altitude', low, high)
    elif name == 'GPSImgDirection':
        refs = sibling_values(flattened, key, tag_parts(key)[1] + 'Ref')
        if refs and any(r != refs[0] for r in refs): raise ValueError('Conflicting image-direction references')
        ref = refs[0] if refs else None
        if ref not in ('T', 'M'): raise ValueError('Image direction has an invalid / missing bearing reference')
    return result, ref


def optional_gps_record(raw, name, low=None, high=None):
    """Read only camera fix details; structured / subject values are independent."""
    flattened = dict(leaves({k: v for k, v in raw.items() if location_kind(k)}))
    values = []
    for key, value in flattened.items():
        if coordinate_category(key) != 'camera': continue
        if not re.search(r'(?:^|[:.])' + re.escape(name) + r'$', key): continue
        values.append(gps_detail(flattened, key, name, low, high))
    if values and any(abs(v[0] - values[0][0]) > 1e-6 or v[1] != values[0][1] for v in values): raise ValueError('Conflicting camera ' + name)
    return values[0] if values else (None, None)


def optional_gps(raw, name, low=None, high=None):
    return optional_gps_record(raw, name, low, high)[0]


def instant(value, zone='', subsec='', offset=''):
    """Return Decimal UTC seconds, retaining up to nine fractional digits.

    Embedded offsets take priority. IANA local times must round-trip uniquely;
    both folds of an ambiguous clock and all nonexistent clocks are rejected.
    An explicit numeric offset is the supported disambiguation mechanism.
    """
    value = str(value or '')
    value = re.sub(r'^(\d{4}):(\d{2}):(\d{2})', r'\1-\2-\3', value)
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?', value)
    if not match: raise ValueError('Missing or malformed camera / synchronization timestamp')
    date, clock, fraction, embedded = match.groups()
    if subsec:
        if not re.fullmatch(r'\d{1,9}', str(subsec)): raise ValueError('Invalid capture subseconds')
        if fraction and fraction != str(subsec): raise ValueError('Conflicting capture subseconds')
        fraction = str(subsec)
    if offset:
        if embedded and embedded.replace('Z', '+00:00') != str(offset): raise ValueError('Conflicting embedded capture timezone')
        embedded = str(offset)
    selected = embedded or zone
    if not selected: raise ValueError('Camera timezone is required: choose UTC, ±HH:MM or an IANA timezone')
    naive = dt.datetime.fromisoformat(date + 'T' + clock)
    if selected in ('UTC', 'Z'): tz = UTC
    elif re.fullmatch(r'[+-]\d{2}:\d{2}', selected):
        h, m = map(int, selected[1:].split(':'))
        if m > 59 or h > 14 or (h == 14 and m): raise ValueError('Timezone offset must be within ±14:00')
        tz = dt.timezone(dt.timedelta(minutes=(h * 60 + m) * (-1 if selected[0] == '-' else 1)))
    else:
        try: tz = ZoneInfo(selected)
        except (ZoneInfoNotFoundError, ValueError) as exc: raise ValueError('Unknown IANA camera timezone') from exc
        candidates = {naive.replace(tzinfo=tz, fold=fold).astimezone(UTC) for fold in (0, 1)
                      if naive.replace(tzinfo=tz, fold=fold).astimezone(UTC).astimezone(tz).replace(tzinfo=None) == naive}
        if len(candidates) != 1: raise ValueError('Ambiguous or nonexistent DST clock: supply an explicit UTC offset')
    delta = naive.replace(tzinfo=tz).astimezone(UTC) - EPOCH
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal('0.' + (fraction or '0'))


def utc_text(seconds):
    seconds = Decimal(seconds); whole = int(seconds // 1)
    if seconds < whole: whole -= 1
    value = EPOCH + dt.timedelta(seconds=whole)
    fraction = format(seconds - whole, 'f').split('.')[-1].rstrip('0') if seconds != whole else ''
    return value.strftime('%Y-%m-%d %H:%M:%S') + ('.' + fraction if fraction else '') + 'Z'


def capture_instant(raw, zone):
    exif = metadata_value(raw, 'ExifIFD', 'DateTimeOriginal')
    xmp = metadata_value(raw, 'XMP-exif', 'DateTimeOriginal')
    if exif:
        sub = metadata_value(raw, 'ExifIFD', 'SubSecTimeOriginal') or ''
        off = metadata_value(raw, 'ExifIFD', 'OffsetTimeOriginal') or ''
        xmp_offset = re.search(r'(Z|[+-]\d{2}:\d{2})$', str(xmp or ''))
        fallback = off or (xmp_offset.group(1) if xmp_offset else zone)
        result = instant(exif, fallback, sub, off)
        if xmp and instant(xmp, fallback) != result: raise ValueError('EXIF and XMP capture times conflict')
        return str(exif) + ('.' + str(sub) if sub and '.' not in str(exif) else '') + str(off), result
    if xmp: return str(xmp), instant(xmp, zone)
    raise ValueError('No embedded Image Capture Date; file modification time is never a fallback')


def corrected_time(seconds, config):
    value = config.get('seconds', '0')
    number(value, 'camera clock correction', -31557600, 31557600)
    constant = Decimal(str(value))
    if decimal_digits(value) > 9: raise ValueError('Camera correction supports up to nine fractional-second digits')
    drift = Decimal(0)
    pairs = config.get('sync', [])
    if pairs:
        if len(pairs) != 2 or any(len(p) != 2 for p in pairs): raise ValueError('Drift calibration requires two complete camera / GPS UTC pairs')
        c1, c2 = [instant(p[0], config.get('timezone', '')) for p in pairs]
        if any(not re.search(r'(Z|[+]00:00)$', p[1]) for p in pairs):
            raise ValueError('Each GPS synchronization time must explicitly end with Z or +00:00')
        g1, g2 = [instant(p[1], 'UTC') for p in pairs]
        # A GPS synchronization time is explicitly UTC, never an offsetless local clock.
        if c2 - c1 < 60 or g2 <= g1: raise ValueError('Synchronization pairs must be chronological and at least 60 camera seconds apart')
        slope = (g2 - g1) / (c2 - c1)
        if not Decimal('.99') <= slope <= Decimal('1.01'): raise ValueError('Clock drift exceeds the supported 1% bound')
        drift = g1 + (seconds - c1) * slope - seconds
    correction = constant + drift
    if not correction.is_finite() or abs(correction) > 31557600: raise ValueError('Clock correction exceeds one year')
    return seconds + correction, format(correction, '.9f') + ' s (added to camera UTC)'


def parse_gpx(path):
    before = identity(path)
    if before[2] > MAX_GPX: raise ValueError('GPX file exceeds 32 MiB')
    with inspection_path(path) as (_, fd):
        if descriptor_identity(fd) != before: raise ValueError('GPX changed while opening the track')
        with os.fdopen(os.dup(fd), 'rb') as stream: data = stream.read(MAX_GPX + 1)
    if len(data) > MAX_GPX or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper() or b'\x00' in data:
        raise ValueError('GPX DTDs, entities, non-UTF XML and oversized inputs are refused')
    parser = ET.XMLPullParser(events=('start', 'end')); root = None; level = 0; nodes = 0
    try:
        for offset in range(0, len(data), 65536):
            checkpoint(); parser.feed(data[offset:offset+65536])
            for event, element in parser.read_events():
                if event == 'start':
                    level += 1; nodes += 1
                    if root is None: root = element
                    if level > 32 or nodes > 1000000: raise ValueError('GPX exceeds XML depth / element limits')
                else: level -= 1
        parser.close()
    except ET.ParseError as exc: raise ValueError('Malformed GPX XML') from exc
    if root is None: raise ValueError('Empty GPX XML')
    if root.tag not in ('{http://www.topografix.com/GPX/1/0}gpx', '{http://www.topografix.com/GPX/1/1}gpx'):
        raise ValueError('Choose a standard GPX 1.0 or 1.1 file')
    namespace = root.tag.split('}')[0] + '}'
    segments = []; invalid = 0; count = 0
    containers = []
    for child in root:
        if child.tag == namespace + 'trk':
            containers.extend(c for c in child if c.tag == namespace + 'trkseg')
        elif child.tag == namespace + 'rte': containers.append(child)
    for index, container in enumerate(containers):
        fixes = []; previous = None
        expected = namespace + ('rtept' if container.tag == namespace + 'rte' else 'trkpt')
        for point in container:
            if point.tag != expected: continue
            count += 1
            if count > MAX_POINTS: raise ValueError('GPX exceeds 250,000 track points')
            checkpoint()
            try:
                lat = coordinate(point.attrib.get('lat'), None, True)
                lon = coordinate(point.attrib.get('lon'), None, False)
                stamp = point.findtext(namespace + 'time')
                if not stamp or not re.search(r'(Z|[+]00:00)$', stamp): raise ValueError('GPX timestamp must be UTC')
                time = instant(stamp, 'UTC')
                ele = point.findtext(namespace + 'ele')
                altitude = number(ele, 'GPX elevation', -12000, 100000) if ele is not None else None
                if previous is not None and time < previous: raise ValueError('Track segment timestamps run backwards')
                fixes.append((time, lat, lon, altitude)); previous = time
            except ValueError as exc:
                # An invalid fix breaks connectivity; never bridge over it.
                if 'backwards' in str(exc): raise
                invalid += 1
                if fixes: segments.append((f'{index + 1}.{len(segments) + 1}', fixes)); fixes = []
                previous = None
        if fixes: segments.append((str(index + 1) + '.' + str(len(segments) + 1), fixes))
    if not segments: raise ValueError('GPX contains no valid timestamped track / route points')
    if identity(path) != before: raise ValueError('GPX changed while being read')
    return {'segments': segments, 'identity': before, 'path': path, 'invalid': invalid,
            'count': sum(len(f) for _, f in segments),
            'start': utc_text(min(f[0][0] for _, f in segments)),
            'end': utc_text(max(f[-1][0] for _, f in segments))}


def match_gpx(track, seconds, gap):
    gap = number(gap, 'maximum interpolation gap', 0, 86400)
    candidates = []; covered = 0
    for name, fixes in track['segments']:
        checkpoint()
        if not fixes[0][0] <= seconds <= fixes[-1][0]: continue
        covered += 1
        if covered > 1: raise ValueError('Ambiguous: overlapping GPX segments; choose an unambiguous track')
        # bisect's key avoids rebuilding the complete time index for each image.
        left = bisect.bisect_left(fixes, seconds, key=lambda p: p[0])
        right = bisect.bisect_right(fixes, seconds, key=lambda p: p[0])
        if left != right:
            same = fixes[left:right]
            if any(p[1:] != same[0][1:] for p in same): raise ValueError('Ambiguous duplicate GPX timestamps')
            a = b = same[0]
        else:
            a, b = fixes[left - 1], fixes[left]
            # Contradictory duplicate endpoints make the whole interval ambiguous.
            for endpoint in (a, b):
                lo = bisect.bisect_left(fixes, endpoint[0], key=lambda p: p[0])
                hi = bisect.bisect_right(fixes, endpoint[0], key=lambda p: p[0])
                if any(p[1:] != endpoint[1:] for p in fixes[lo:hi]): raise ValueError('Ambiguous duplicate GPX interpolation endpoint')
        interval = b[0] - a[0]
        if interval > gap: continue
        ratio = float((seconds - a[0]) / interval) if interval else 0
        lat = a[1] + ratio * (b[1] - a[1])
        lon = ((a[2] + ratio * (((b[2] - a[2] + 180) % 360) - 180) + 180) % 360) - 180
        alt = a[3] + ratio * (b[3] - a[3]) if a[3] is not None and b[3] is not None else None
        candidates.append({'position': [lat, lon], 'altitude': alt, 'segment': name,
                           'fixes': utc_text(a[0]) + ' → ' + utc_text(b[0]),
                           'gap': str(interval) + ' s; ' + ('exact fix' if not interval else 'interpolated')})
    if not candidates: raise ValueError('Unmatched: outside track segments or interpolation gap exceeds the selected limit')
    if len(candidates) != 1: raise ValueError('Ambiguous: overlapping GPX track segments; choose an unambiguous track')
    return candidates[0]


def meridian(latitude):
    # WGS84 meridional arc series, metre accuracy comfortably below 100 m cells.
    a = 6378137.0; e2 = 6.6943799901413165e-3; p = math.radians(latitude)
    return a * ((1-e2/4-3*e2**2/64-5*e2**3/256)*p
                -(3*e2/8+3*e2**2/32+45*e2**3/1024)*math.sin(2*p)
                +(15*e2**2/256+45*e2**3/1024)*math.sin(4*p)
                -35*e2**3/3072*math.sin(6*p))


def generalize(position, grid):
    if grid not in (100, 1000, 5000, 10000): raise ValueError('Choose a supported location grid size')
    lat, lon = position; pole = meridian(90)
    bands = max(1, round(2*pole/grid)); step = 2*pole/bands
    band = min(bands-1, max(0, int((meridian(lat)+pole)//step)))
    centre = -pole + (band+.5)*step
    lo, hi = -90.0, 90.0
    for _ in range(48):
        mid = (lo+hi)/2
        if meridian(mid) < centre: lo = mid
        else: hi = mid
    newlat = (lo+hi)/2; p = math.radians(newlat)
    radius = 6378137.0/math.sqrt(1-6.6943799901413165e-3*math.sin(p)**2)
    columns = max(1, round(2*math.pi*radius*max(0, math.cos(p))/grid))
    column = min(columns-1, int(((lon+180)%360)/360*columns))
    newlon = ((-180+(column+.5)*360/columns+180)%360)-180
    a1, a2 = map(math.radians, (lat, newlat)); dlon = math.radians(((newlon-lon+180)%360)-180)
    hav = math.sin((a2-a1)/2)**2+math.cos(a1)*math.cos(a2)*math.sin(dlon/2)**2
    distance = 2*6371008.8*math.asin(math.sqrt(min(1, max(0, hav))))
    return [newlat, newlon], distance


def safe_format(path, raw):
    fmt = str(metadata_value(raw, 'File', 'FileType') or '').upper()
    if fmt == 'EXTENDED WEBP': fmt = 'WEBP'
    if fmt not in FORMATS or Path(path).suffix.lower() not in FORMATS[fmt]:
        raise ValueError('GPS writes require verified JPEG, PNG, WebP, TIFF, HEIC/HEIF or AVIF with a matching extension; PSD, RAW and other containers are read-only')
    from kim_date_tools import ensure_still_capture_input
    ensure_still_capture_input(path, preview=True)
    if fmt == 'JPEG' and metadata_value(raw, 'File', 'EncodingProcess') == 2:
        raise ValueError('Progressive JPEG scan preservation is not supported by the current metadata container verifier; use a supported baseline JPEG or another verified format')
    return fmt


def removal_args(info, reduce=False):
    """Only established writable families are cleared; unknown precise stores block."""
    args = list(GPS_CLEAR) + list(GPS_EXT_CLEAR); removed = []
    for key in info['fields']:
        group, name = tag_parts(key)
        kind = location_kind(key)
        if group == 'XMP-iptcExt' and any(name.startswith(p) for p in STRUCTURES):
            # Each semantic structure is independent of camera GPS. Ordinary
            # writes clear GPS leaves; reduction removes the entire structure.
            root = next(p for p in STRUCTURES if name.startswith(p))
            if reduce:
                args.append('-XMP-iptcExt:' + root + '='); removed.append(key)
            else:
                precise = [sub for sub, _ in leaves(info['fields'][key], key) if sub in info['gps']]
                for sub in precise:
                    leaf = tag_parts(sub)[1]
                    if not (leaf.rsplit('.', 1)[-1].startswith('GPS') or leaf.removeprefix(root).startswith('GPS')):
                        raise ValueError('Recognized structured coordinate cannot safely be reconciled: ' + sub)
                if precise: removed.append(key)
            continue
        if kind == 'gps':
            if group == 'GPS' or (group.startswith('XMP-') and name.startswith('GPS')):
                removed.append(key); continue
            raise ValueError('Recognized precise location cannot safely be reconciled: ' + key)
        if reduce:
            if group not in ('IPTC', 'XMP-photoshop', 'XMP-iptcCore', 'XMP-iptcExt') or place_base(name) not in PLACE_NAMES:
                raise ValueError('Recognized place field cannot safely be removed: ' + key)
            args.append('-' + group + ':' + place_base(name) + '='); removed.append(key)
    return list(dict.fromkeys(args)), removed


def assignments(position, altitude=None, direction=None, direction_ref='T', altitude_ref=None):
    lat, lon = position
    result = ['-EXIF:GPSMapDatum=WGS-84', '-EXIF:GPSLatitude=' + format(abs(lat), '.12f'),
              '-EXIF:GPSLatitudeRef=' + ('N' if lat >= 0 else 'S'),
              '-EXIF:GPSLongitude=' + format(abs(lon), '.12f'),
              '-EXIF:GPSLongitudeRef=' + ('E' if lon >= 0 else 'W')]
    if altitude is not None:
        altitude_ref = str(int(altitude < 0)) if altitude_ref is None else str(altitude_ref)
        if altitude_ref not in ('0', '1', '2', '3') or (altitude < 0) != (altitude_ref in ('1', '3')) and altitude != 0:
            raise ValueError('Invalid approved altitude reference')
        result += ['-EXIF:GPSAltitude=' + format(abs(altitude), '.6f'), '-EXIF:GPSAltitudeRef#=' + altitude_ref]
    if direction is not None:
        if direction_ref not in ('T', 'M'): raise ValueError('Invalid image direction reference')
        result += ['-EXIF:GPSImgDirection=' + format(direction, '.6f'), '-EXIF:GPSImgDirectionRef=' + direction_ref]
    return result


def source_info(path, cache):
    try: current = identity(path)
    except (OSError, ValueError): return None
    old = cache.get(path)
    if old and old.get('identity') == current: return old
    return None


def input_instruction(kind, config):
    if kind == 'gpx' and not config.get('gpx', '').strip():
        return 'Choose the GPX track recorded during this image session to preview changes.'
    if kind in ('copy', 'apply'):
        method = config.get('method', 'photo' if kind == 'copy' else 'manual')
        if method == 'photo' and not config.get('reference'):
            return 'Choose a reference image. Its camera coordinates can be copied or applied to the other selected images.'
        if method == 'map' and (config.get('latitude', '') == '' or config.get('longitude', '') == ''):
            return 'Choose a point on the map to preview changes.'
        if method == 'manual' and (not config.get('latitude', '').strip() or not config.get('longitude', '').strip()):
            return 'Enter latitude and longitude in signed decimal degrees to preview changes.'
    return ''


def build_plan(kind, policy, files, config, seeds=None, progress=lambda *_: None, cancelled=lambda: False, cache=None, track_cache=None):
    if kind not in TITLES or policy not in ('create', 'overwrite'): raise ValueError('Invalid location operation or output policy')
    if not files or len(files) > MAX_FILES: raise ValueError('Select between 1 and 1000 images')
    cache = cache if cache is not None else {}; files = [absolute(p) for p in files]
    config = dict(config); dependencies = []; reference = None; reference_error = None; track = None
    requested_kind = kind
    instruction = input_instruction(kind, config)
    if instruction: kind = 'report'
    if kind in ('copy', 'apply'):
        method = config.get('method', 'photo' if kind == 'copy' else 'manual')
        if method not in ('photo', 'map', 'manual'): raise ValueError('Choose a location method')
        kind = 'copy' if method == 'photo' else 'apply'
    plan = dict(operation='location', policy=policy, total=len(files), config=dict(config, kind=requested_kind), entries=[], dependencies=dependencies, pending_input=instruction)
    with inspection_context(cancelled=cancelled):
        if kind == 'gpx':
            path = absolute(config['gpx'])
            prior = track_cache.get('track') if track_cache is not None else None
            track = prior if prior and prior['path'] == path and prior['identity'] == identity(path) else parse_gpx(path)
            if track_cache is not None: track_cache.clear(); track_cache['track'] = track
            dependencies.append({'path': path, 'identity': track['identity']})
            plan['track_summary'] = f'{track["count"]} valid points; {len(track["segments"])} segments; {track["invalid"]} invalid points break connectivity. UTC {track["start"]} → {track["end"]}'
        paths = list(files)
        if kind == 'copy' and config.get('reference'): paths.append(absolute(config['reference']))
        paths = list(dict.fromkeys(paths))
        missing = [p for p in paths if source_info(p, cache) is None]
        if missing:
            progress(0, len(files), 'Reading location metadata in bounded batches…')
            cache.update(read_many(missing))
            if sum(len(json.dumps(r)) for r in cache.values()) > MAX_BATCH_METADATA:
                cache.clear(); raise ValueError('Batch metadata exceeds the 64 MiB cache limit; use a smaller selection')
        # Keep the per-dialog read-only cache bounded.
        for p in list(cache):
            if p not in paths: del cache[p]
        if kind == 'copy' and not config.get('reference'):
            reference_error = 'Choose a reference image with camera coordinates, or choose another location method.'
        if kind == 'copy' and config.get('reference'):
            path = absolute(config['reference'])
            data = cache[path]
            if data.get('error'):
                raise ValueError('GPS information could not be read from reference ' + Path(path).name + ': ' + data['error'])
            reference = summarize(data['raw'])
            camera_issues = reference['categories']['camera']['issues']
            if camera_issues or not reference['position']:
                reference_error = 'This image has no unambiguous camera coordinates: ' + '; '.join(camera_issues or ['no camera coordinate pair'])
            dependencies.append({'path': path, 'identity': data['identity']})
            plan['reference_summary'] = Path(path).name + ': ' + ('GPS unavailable' if reference_error else display_position(reference['position']))
            plan['reference_summary'] += '\nSources: ' + '; '.join(COORDINATE_CATEGORIES[p['category']] + ': ' + p['source'] + ' ' + display_position(p['position']) for p in reference['records'])
            try:
                alt = optional_gps(data['raw'], 'GPSAltitude', -12000, 100000)
                altitude_summary = str(alt) + ' m' if alt is not None else 'not recorded'
            except ValueError as exc: altitude_summary = 'invalid / conflicting: ' + str(exc)
            plan['reference_summary'] += '\nAltitude: ' + altitude_summary + '; conflicts: ' + ('; '.join(reference['issues']) or 'none')
        reserved = set(); seen = set()
        for index, path in enumerate(files):
            checkpoint(); progress(index, len(files), path)
            entry = dict(source=path, status='error', warnings=[], rows=[], args=[])
            try:
                entry = base_entry(path); key = tuple(entry['identity'][:2])
                if key in seen: raise ValueError('Duplicate selected image identity')
                seen.add(key); data = cache[path]
                if data.get('error'): raise ValueError(data['error'])
                if entry['identity'] != data['identity']: raise ValueError('Source changed during inspection')
                raw = data['raw']; info = summarize(raw); entry['location_before'] = info
                if kind != 'report': entry['metadata_digest'] = metadata_digest(raw)
                if kind == 'report' or config.get('inspect_only'):
                    entry['status'] = 'skip'; entry['rows'] = report_rows(path, info)
                    if info['issues']: entry['warnings'] += info['issues']
                    plan['entries'].append(entry); continue
                if reference_error: raise ValueError(reference_error)
                if kind == 'copy' and entry['identity'][:2] == dependencies[0]['identity'][:2]:
                    entry['status'] = 'skip'; entry['rows'] = [[Path(path).name, 'Reference image', display_position(info['position']), 'Preserve reference unchanged', 'Skipped reference']]
                    finish_entry(entry, path, 'overwrite'); plan['entries'].append(entry); continue
                safe_format(path, raw)
                args, removed = removal_args(info, kind == 'reduce')
                altitude = direction = altitude_ref = None; direction_ref = 'T'
                if kind == 'apply':
                    if any(decimal_digits(config.get(k, '')) > 12 for k in ('latitude', 'longitude')):
                        raise ValueError('Enter at most twelve decimal places for each coordinate')
                    position = [coordinate(config.get('latitude', ''), None, True), coordinate(config.get('longitude', ''), None, False)]
                    if config.get('altitude', '') != '': altitude = number(config['altitude'], 'altitude', -12000, 100000)
                    if config.get('direction', '') != '': direction = number(config['direction'], 'image direction', 0, 359.999999)
                elif kind == 'copy':
                    position = reference['position']
                    if config.get('altitude'):
                        try:
                            altitude, altitude_ref = optional_gps_record(cache[dependencies[0]['path']]['raw'], 'GPSAltitude', -12000, 100000)
                            if altitude is None: raise ValueError('No altitude is recorded in the reference image')
                        except ValueError as exc: raise ValueError('Copy Altitude: ' + str(exc)) from exc
                    if config.get('direction'):
                        refraw = cache[dependencies[0]['path']]['raw']
                        direction = optional_gps(refraw, 'GPSImgDirection', 0, 359.999999)
                        refs = [metadata_value(refraw, g, 'GPSImgDirectionRef') for g in ('GPS', 'XMP-exif')]
                        refs = [r for r in refs if r is not None]
                        if direction is not None and (not refs or len(set(refs)) != 1 or refs[0] not in ('T', 'M')): raise ValueError('Reference direction has an invalid / missing bearing reference')
                        direction_ref = refs[0] if refs else 'T'
                elif kind == 'gpx':
                    stored = metadata_value(raw, 'ExifIFD', 'DateTimeOriginal') or metadata_value(raw, 'XMP-exif', 'DateTimeOriginal')
                    entry['rows'].append([Path(path).name, 'Original capture time (unchanged)', str(stored or '(absent)'), '', 'Embedded camera clock; never filesystem modification time'])
                    original, seconds = capture_instant(raw, config.get('timezone', ''))
                    effective, correction = corrected_time(seconds, config)
                    entry['rows'].append([Path(path).name, 'Effective capture time in UTC', original, utc_text(effective), 'Clock correction: ' + correction])
                    match = match_gpx(track, effective, config.get('gap', 300)); position = match['position']
                    if config.get('altitude'): altitude = match['altitude']
                    entry['rows'].append([Path(path).name, 'Track segment ' + match['segment'], match['fixes'], match['gap'], 'Matched'])
                    entry['match_status'] = 'matched'
                    entry['match'] = dict(match, effective=utc_text(effective), correction=correction)
                else:
                    camera_issues = info['categories']['camera']['issues']
                    if camera_issues or not info['position']: raise ValueError('Reduction requires an unambiguous camera position: ' + '; '.join(camera_issues or ['no camera coordinate pair']))
                    position, displacement = generalize(info['position'], int(config.get('grid', 1000)))
                    entry['displacement_m'] = displacement
                    entry['rows'].append([Path(path).name, 'Geographic grid', str(config.get('grid', 1000)) + ' m approximate cells', f'{displacement:.1f} m approximate displacement', 'Cell centre; no anonymity / privacy-radius guarantee'])
                    entry['warnings'].append('Free-text captions, image content and external information may still reveal location. Narrative text is preserved.')
                entry['approved_location'] = {'category': 'camera', 'position': position, 'altitude': altitude, 'direction': direction, 'direction_ref': direction_ref, 'altitude_ref': altitude_ref, 'reduce': kind == 'reduce'}
                entry['args'] = args + assignments(position, altitude, direction, direction_ref, altitude_ref)
                entry['rows'].append([Path(path).name, 'WGS84 camera GPS coordinates', display_position(info['position']), display_position(position), 'Set photo GPS location; remove other recognized precise coordinate records'])
                entry['rows'].append([Path(path).name, 'GPS fix details', 'Existing altitude / time / direction / speed', 'Altitude: ' + (str(altitude) + ' m' if altitude is not None else 'absent') + '; direction: ' + (str(direction) + '° ' + direction_ref if direction is not None else 'absent'), 'Remove stale fix metadata; never invent a GPS timestamp'])
                for key in removed:
                    entry['rows'].append([Path(path).name, key, json.dumps(info['fields'][key], ensure_ascii=False), 'Remove / reconcile', 'Explicit location field'])
                entry['removed_fields'] = removed
                entry['warnings'].extend(info['issues'])
                if matches_approved(info, raw, entry['approved_location']): entry['status'] = 'skip'
                candidate = seeds[index] if seeds else path
                target = allocate(path, candidate, policy, reserved, '-')
                if policy == 'create' and target == path: raise ValueError('Create policy cannot replace an original')
                finish_entry(entry, target, policy)
                entry['rows'].append([Path(path).name, 'Output policy / destination', policy, Path(target).name, str(Path(target).parent)])
                if identity(path) != entry['identity']: raise ValueError('Source changed during planning')
            except Exception as exc:
                entry['status'] = 'error'; entry['error'] = str(exc)
                state = 'Unmatched' if str(exc).startswith('Unmatched:') else 'Ambiguous' if 'ambiguous' in str(exc).lower() else 'Blocked'
                entry['match_status'] = state.lower()
                entry['rows'].append([Path(path).name, 'Image update', '', '', state + ': ' + str(exc)])
            plan['entries'].append(entry)
    protected = {tuple(e['identity'][:2]) for e in plan['entries'] if 'identity' in e}
    protected.update(tuple(d['identity'][:2]) for d in dependencies)
    for entry in plan['entries']:
        dest = entry.get('destination', {}).get('entry')
        if dest and tuple(dest[:2]) in protected and entry.get('target') != entry['source']:
            entry.update(status='error', error='Destination aliases a selected or reference source')
            entry['rows'].append([Path(entry['source']).name, 'Destination', '', '', entry['error']])
    plan['privacy_summary'] = privacy_summary(plan['entries'])
    plan['approval_digest'] = approval_digest(plan)
    return plan


def report_rows(path, info):
    name = Path(path).name
    rows = [[name, 'Location classification', privacy_classification(info), '', '; '.join(info['issues']) or 'No recognized conflicts'],
            [name, 'Photo GPS location', display_position(info['position']), '', 'Only unambiguous camera GPS is eligible for Copy / Reduce'],
            [name, 'Measurement accuracy', info['accuracy'], '', 'Stored decimal resolution is not measurement accuracy']]
    rows.append([name, 'Source format / inspection coverage', str(info['format']), '',
                 'Recognized ExifTool location fields only; editing uses a narrower verified format allowlist'])
    rows.append([name, 'Additional / duplicate coordinate records', str(info['duplicate_records']), '', 'Counted only within the same semantic context; distinct structured locations are independent'])
    for record in info['records']:
        rows.append([name, COORDINATE_CATEGORIES[record['category']] + ': ' + record['source'], display_position(record['position']),
                     'Numeric decimal digits: ' + '/'.join(map(str, record['stored_digits'])),
                     '; '.join(record['issues']) or 'Independent stored record; decimal representation is not receiver accuracy'])
        rows.append([name, 'Coordinate source tags', '; '.join(tag for tags in record['tags'].values() for tag in tags), '', COORDINATE_CATEGORIES[record['category']]])
    for key, value in info['fields'].items():
        label = COORDINATE_CATEGORIES[coordinate_category(key)] if location_kind(key) == 'gps' else 'Recognized location metadata'
        rows.append([name, key, json.dumps(value, ensure_ascii=False), '', label])
    return rows


def privacy_classification(info):
    if info is None: return 'Could not inspect image'
    if info['categories']['camera']['issues']: return 'Conflicting camera coordinates'
    if any(r['position'] is not None for r in info['records']):
        if info['issues']: return 'GPS coordinates found; optional metadata needs review'
        return 'GPS coordinates found'
    if info['issues']: return 'Location information needs review'
    if info['places']: return 'Location names only'
    return 'No recognized location information'


def privacy_summary(entries):
    counts = {}
    for entry in entries:
        label = privacy_classification(entry.get('location_before'))
        counts[label] = counts.get(label, 0) + 1
    return '\n'.join([f'{len(entries)} images checked', *[f'{label}: {count}' for label, count in counts.items()],
        'Other metadata and the picture itself may still reveal a location.'])


def matches_approved(info, raw, approved):
    if approved.get('category') != 'camera': return False
    if info['issues'] or not info['position'] or len(info['records']) != 1 or info['duplicate_records']: return False
    if info['records'][0]['category'] != 'camera': return False
    expected = approved['position']; actual = info['position']
    if not same_position(expected, actual): return False
    # Only the canonical EXIF IFD should contain coordinates after reconciliation.
    if any(not k.startswith('GPS:') for k in info['gps']): return False
    if any(location_kind(k) == 'gps' and not k.startswith('GPS:') for k in info['fields']): return False
    datum = metadata_value(raw, 'GPS', 'GPSMapDatum')
    if re.sub(r'[^A-Z0-9]', '', str(datum).upper()) not in ('WGS84', 'WGS1984'): return False
    allowed = {'GPSVersionID', 'GPSMapDatum', 'GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef'}
    if approved['altitude'] is not None: allowed |= {'GPSAltitude', 'GPSAltitudeRef'}
    if approved['direction'] is not None: allowed |= {'GPSImgDirection', 'GPSImgDirectionRef'}
    if any(k.split(':')[-1] not in allowed for k in info['gps']): return False
    try:
        altitude, altitude_ref = optional_gps_record(raw, 'GPSAltitude', -12000, 100000)
        direction = optional_gps(raw, 'GPSImgDirection', 0, 359.999999)
    except ValueError: return False
    for actual, wanted in ((altitude, approved['altitude']), (direction, approved['direction'])):
        if (actual is None) != (wanted is None) or (actual is not None and abs(actual-wanted) > 1e-5): return False
    if altitude is not None and altitude_ref != (approved.get('altitude_ref') or str(int(altitude < 0))): return False
    if direction is not None and metadata_value(raw, 'GPS', 'GPSImgDirectionRef') != approved['direction_ref']: return False
    if approved['reduce'] and any(location_kind(k) == 'place' for k in info['fields']): return False
    return True


def approval_digest(plan):
    # Freeze execution data without repeatedly hashing the potentially large
    # presentation tables. Source metadata has its own stable digest.
    frozen = {k: plan[k] for k in ('operation', 'policy', 'total', 'config', 'dependencies')}
    keys = ('source', 'identity', 'status', 'target', 'destination', 'publication',
            'args', 'approved_location', 'metadata_digest', 'removed_fields', 'match')
    frozen['entries'] = [{k: entry[k] for k in keys if k in entry} for entry in plan['entries']]
    return hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()


def verify_dependencies(plan, *, integrity=True):
    if plan.get('operation') != 'location': return
    if plan.get('pending_input') or plan.get('config', {}).get('inspect_only'):
        raise ValueError('Select complete location inputs and approve a fresh Preview Changes before publication')
    if integrity and plan.get('approval_digest') != approval_digest(plan):
        raise ValueError('Approved location configuration or plan changed; review a fresh plan')
    for dep in plan['dependencies']:
        if identity(dep['path']) != dep['identity']: raise ValueError('Reference image or GPX file changed; review a fresh plan: ' + dep['path'])
    if plan['policy'] not in ('create', 'overwrite'): raise ValueError('Invalid approved output policy')


def metadata_digest(raw):
    stable = {k: v for k, v in raw.items() if ':' in k and k.split(':')[0] not in ('File', 'System', 'ExifTool', 'Composite')}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def preserved_metadata(raw, reduce=False):
    result = {}
    for key, value in raw.items():
        group, name = tag_parts(key)
        if ':' not in key or group in ('Composite', 'File', 'System', 'ExifTool'): continue
        if group == 'GPS' or (group.startswith('XMP-') and name.startswith('GPS')): continue
        if group == 'XMP-iptcExt' and any(name.startswith(p) for p in STRUCTURES):
            if reduce: continue
            if 'GPS' in name: continue  # Flattened structured GPS fields.
            # Remove only GPS leaves when comparing retained structured place text.
            def strip_gps(v):
                if isinstance(v, dict):
                    return {k: kept for k, c in v.items() if not k.startswith('GPS') and (kept := strip_gps(c)) not in ({}, [])}
                if isinstance(v, list): return [kept for c in v if (kept := strip_gps(c)) not in ({}, [])]
                return v
            value = strip_gps(value)
            if value in ({}, []): continue
        elif reduce and location_kind(key): continue
        # ExifTool regenerates these derived layout / digest bookkeeping fields.
        if name in ('ExifByteOrder', 'ExifImageWidth', 'ExifImageHeight', 'Padding', 'CurrentIPTCDigest', 'IPTCDigest', 'XMPToolkit'):
            if name in ('ExifImageWidth', 'ExifImageHeight'): result[key] = value
            continue
        result[key] = value
    return result


def png_core(path):
    """Hash every non-text / non-EXIF PNG chunk, including ICC and presentation."""
    import zlib
    kept = []; ended = False
    with open(path, 'rb') as stream:
        if stream.read(8) != b'\x89PNG\r\n\x1a\n': raise ValueError('Invalid PNG signature')
        while True:
            checkpoint(); header = stream.read(8)
            if len(header) != 8: raise ValueError('Truncated PNG')
            size, tag = struct.unpack('>I4s', header)
            digest = hashlib.sha256(); checksum = zlib.crc32(tag); remaining = size
            while remaining:
                checkpoint(); chunk = stream.read(min(remaining, 1024*1024))
                if not chunk: raise ValueError('Truncated PNG chunk')
                remaining -= len(chunk); digest.update(chunk); checksum = zlib.crc32(chunk, checksum)
            crc = stream.read(4)
            if len(crc) != 4 or struct.unpack('>I', crc)[0] != checksum & 0xffffffff: raise ValueError('Invalid PNG chunk CRC')
            if tag not in (b'eXIf', b'tEXt', b'zTXt', b'iTXt'): kept.append((tag, size, digest.hexdigest()))
            if tag == b'IEND': ended = True; break
        if not ended or stream.read(1): raise ValueError('Invalid PNG termination')
    return kept


def approved_entry(plan, source):
    verify_dependencies(plan)
    source = absolute(source)
    entry = next(e for e in plan['entries'] if e['source'] == source)
    verify_entry(entry)
    if entry['status'] != 'change': raise ValueError('Image has no approved modification')
    # Recheck the saved numeric configuration against the saved assignments.
    approved = entry['approved_location']
    if approved.get('category') != 'camera': raise ValueError('Approved GPS must describe a camera position')
    wanted = assignments(approved['position'], approved['altitude'], approved['direction'], approved['direction_ref'], approved.get('altitude_ref'))
    if entry['args'][-len(wanted):] != wanted: raise ValueError('Approved configuration / assignments changed')
    return entry


def verify_output(plan, source, output, *, entry=None):
    if entry is None: entry = approved_entry(plan, source)
    else:
        # The same parsed plan was integrity-checked before writing. Only that
        # immutable computation is reused; all live authorizations run again.
        verify_dependencies(plan, integrity=False)
        verify_entry(entry)
    records = read_many([source, output])
    if any(r.get('error') for r in records.values()): raise ValueError('Staged location output cannot be inspected reliably')
    raw = records[output]['raw']; info = summarize(raw)
    if any(key in raw and location_kind(key) == 'place' for key in entry['removed_fields']) and entry['approved_location']['reduce']:
        raise ValueError('An explicitly removed structured location field remains')
    if not matches_approved(info, raw, entry['approved_location']): raise ValueError('Staged GPS / location metadata differs from the approved plan')
    if metadata_digest(records[source]['raw']) != entry['metadata_digest']:
        raise ValueError('Source metadata changed after approval')
    before = preserved_metadata(records[source]['raw'], entry['approved_location']['reduce'])
    after = preserved_metadata(raw, entry['approved_location']['reduce'])
    defaults = {'IFD0:XResolution': 1, 'IFD0:YResolution': 1, 'IFD0:ResolutionUnit': 1,
                'IFD0:YCbCrPositioning': 1, 'ExifIFD:ExifVersion': '0232',
                'ExifIFD:ComponentsConfiguration': '1 2 3 0', 'ExifIFD:FlashpixVersion': '0100',
                'ExifIFD:ColorSpace': 65535}
    for key in list(after):
        canonical = key.split(':')[0] + ':' + key.split(':')[-1]
        if key not in before and canonical in defaults and after[key] == defaults[canonical]: after.pop(key)
    if before != after: raise ValueError('Unrelated descriptive, date, orientation or rights metadata changed during GPS staging')
    if Path(source).suffix.lower() == '.png' and png_core(source) != png_core(output): raise ValueError('PNG encoded pixels, ICC or presentation data changed')


def main():
    command, plan_path, source, *rest = sys.argv[1:]
    plan = json.loads(Path(plan_path).read_text())
    if command in ('write', 'stage'):
        entry = approved_entry(plan, source)
        result = location_process(['exiftool', *entry['args'], '-o', rest[0], '--', source], limit=1024*1024, timeout=150)
        from kim_process import metadata_diagnostics
        diagnostic = metadata_diagnostics(['exiftool'], result.returncode, result.stderr)
        if result.returncode or diagnostic: raise ValueError('ExifTool GPS staging failed: ' + diagnostic.strip())
        if command == 'stage': verify_output(plan, source, rest[0], entry=entry)
    elif command == 'verify': verify_output(plan, source, rest[0])
    else: raise ValueError('Unknown location engine command')
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: print('Image location: ' + str(exc), file=sys.stderr); raise SystemExit(1)
