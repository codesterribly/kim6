"""Presentation helpers for Image Location Tools; no publication operations."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys

from PySide6.QtCore import QUrl, Qt, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QMessageBox, QWidget, QVBoxLayout,
    QFormLayout, QLabel, QScrollArea, QSizePolicy, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget,
    QPushButton, QApplication)
from kim_location import (COORDINATE_CATEGORIES, coordinate_category, leaves,
                          optional_gps, optional_gps_record, summarize, number, coordinate,
                          privacy_classification, same_position, FORMATS, metadata_value)
from kim_settings_dialog import (config_path, load_settings, save_settings,
                                system_location_units as system_units, location_unit_choices,
                                location_unit_selection)

FEET_PER_METRE = Decimal('1') / Decimal('0.3048')


def unit_preference():
    stored = load_settings(config_path())['KIM_LOCATION_UNITS']
    selected = location_unit_selection(stored)
    if selected != stored:
        try: persist_units(selected)
        except (OSError, ValueError) as exc:
            print('KIM6: measurement preference follows the system for this session; could not save migration: ' + str(exc), file=sys.stderr)
    return selected


def preferred_units(preference=None):
    value = unit_preference() if preference is None else preference
    return value if value in ('imperial', 'metric') else system_units()


def persist_units(value):
    if value not in ('system', 'imperial', 'metric'):
        raise ValueError('Choose System or the alternative measurement system.')
    path = config_path()
    settings = load_settings(path)
    settings['KIM_LOCATION_UNITS'] = value
    save_settings(path, settings)


def altitude_to_metres(value, units):
    # Decimal arithmetic keeps conversions out of the metadata engine.
    number(value, 'altitude')
    parsed = Decimal(value)
    if not parsed.is_finite(): raise ValueError('Enter a finite altitude.')
    metres = parsed * Decimal('0.3048') if units == 'imperial' else parsed
    if not Decimal('-12000') <= metres <= Decimal('100000'):
        raise ValueError('Altitude is outside the supported range.')
    return format(metres, 'f')


def altitude_from_metres(value, units):
    parsed = Decimal(str(value))
    return format(parsed * FEET_PER_METRE if units == 'imperial' else parsed, '.3f').rstrip('0').rstrip('.') or '0'


def height(value, units):
    converted = Decimal(str(value)) * FEET_PER_METRE if units == 'imperial' else Decimal(str(value))
    return format(converted, '.1f') + (' ft' if units == 'imperial' else ' m')


def distance(value, units):
    value = float(value)
    if units == 'imperial':
        feet = value / .3048
        return f'{feet / 5280:,.2f} miles' if abs(feet) >= 5280 else f'{feet:,.0f} ft'
    return f'{value / 1000:,.2f} km' if abs(value) >= 1000 else f'{value:,.0f} m'


def position_text(position):
    if position is None: return 'No camera coordinates recorded'
    lat, lon = position
    return f'{abs(lat):.7f}° {"N" if lat >= 0 else "S"}, {abs(lon):.7f}° {"E" if lon >= 0 else "W"}'


def open_camera_map(parent, info):
    """Only call from an explicit action, with the parser's camera summary."""
    try:
        if not info or info['position'] is None or info['categories']['camera']['issues']:
            raise ValueError('Select an image with valid, unambiguous camera coordinates. Refresh if the image has changed.')
        lat = repr(coordinate(info['position'][0], None, True))
        lon = repr(coordinate(info['position'][1], None, False))
        url = QUrl(f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}')
        if not QDesktopServices.openUrl(url):
            raise ValueError('The default browser could not be opened. Check your desktop’s default browser setting, or use Copy Coordinates to open the location yourself.')
    except (ValueError, RuntimeError) as exc:
        QMessageBox.warning(parent, 'View on Map', str(exc))


def is_reference(entry, config):
    return config.get('method') == 'photo' and entry['source'] == config.get('reference')


def output_description(entry, config):
    if is_reference(entry, config): return 'GPS source, unchanged. No output created.'
    if entry['status'] == 'skip': return 'Already matches GPS, no changes needed. No output created.'
    if entry['status'] == 'error': return 'Cannot update this image. No output will be created.'
    target = entry.get('target')
    if not target: return ''
    return ('Update original: ' if target == entry['source'] else 'Create new image: ') + target


def location_result_message(plan, ok, failed, cancelled, skipped, stopped, unchanged_paths):
    """Counts come from publication results, never from planned changes."""
    config = plan['config']
    skipped_references = sum(is_reference({'source': path}, config) for path in unchanged_paths)
    external_reference = (config.get('method') == 'photo' and config.get('reference') and
                          all(e['source'] != config['reference'] for e in plan['entries']))
    references = skipped_references + bool(external_reference)
    unchanged = len(unchanged_paths) - skipped_references
    unprocessed = max(0, skipped - len(unchanged_paths))
    incomplete = bool(failed or cancelled or stopped or unprocessed)
    action = 'GPS precision reduction' if config['kind'] == 'reduce' else 'GPS coordinate changes'
    heading = action + (' stopped before completion.' if incomplete else ' completed successfully.' if ok else ': no changes needed.')
    lines = [heading, '']
    images = lambda n: 'image' if n == 1 else 'images'
    if ok:
        if plan['policy'] == 'create':
            description = 'with reduced GPS precision' if config['kind'] == 'reduce' else 'with GPS coordinates'
            lines.append(f'Created {ok} new {images(ok)} {description}.')
        else:
            lines.append(f'Updated GPS {"precision" if config["kind"] == "reduce" else "coordinates"} in {ok} original {images(ok)}.')
    else: lines.append('No images were saved.')
    if references: lines.append(f'{references} GPS source {images(references)} remained unchanged.')
    if unchanged: lines.append(f'{unchanged} destination {images(unchanged)} already matched; no output created.')
    if failed: lines.append(f'{failed} {images(failed)} could not be saved. See Details for the affected image and cause.')
    if cancelled: lines.append(f'Processing was cancelled for {cancelled} {images(cancelled)}.')
    if unprocessed: lines.append(f'{unprocessed} {images(unprocessed)} were not processed.' if unprocessed != 1 else '1 image was not processed.')
    if incomplete and ok: lines.append('Successfully saved results were kept.')
    if plan['policy'] == 'create': lines += ['', 'Original images were not modified.']
    return '\n'.join(lines), incomplete


def value_text(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def privacy_status(info):
    return privacy_classification(info)


def camera_status(info):
    if not info: return 'Could not inspect image'
    issues = info['categories']['camera']['issues']
    if issues:
        return 'Conflicting camera GPS' if any('conflict' in issue.lower() or 'contradict' in issue.lower() for issue in issues) else 'Invalid or incomplete camera GPS'
    return 'Camera GPS recorded' if info['position'] is not None else 'No camera GPS recorded'


def blocked_destination(entry, inspecting=False):
    """Short display reason only; the protected planner decides execution."""
    if not entry.get('error') and not inspecting: return ''
    info = entry.get('location_before')
    if not info: return entry.get('error') or 'Blocked: inspection unavailable'
    fmt = str(info['format']).upper()
    if fmt == 'EXTENDED WEBP': fmt = 'WEBP'
    if fmt == 'GIF': return 'Unsupported: KIM6 cannot add GPS coordinates to GIF images.'
    if fmt not in FORMATS: return f'Unsupported: {fmt} GPS write'
    if Path(entry['source']).suffix.lower() not in FORMATS[fmt]:
        return 'Unsupported: format / extension mismatch'
    if entry.get('error', '').startswith('Progressive JPEG scan preservation'):
        return 'Unsupported: progressive JPEG GPS write'
    if entry.get('error', '').startswith('Animated images are not supported'):
        return f'Unsupported: animated {fmt} GPS write'
    if entry.get('error'): return entry['error']
    return ''


def gps_metadata_changes(entry, raw):
    """Explain existing planned actions. Never decides whether an image is a no-op."""
    approved = entry.get('approved_location'); info = entry.get('location_before')
    if entry['status'] != 'change' or not approved or not info: return []
    removed = {key.split(':')[-1] for key in entry.get('removed_fields', [])}
    changes = []
    if info['position'] is None: changes.append('Set camera GPS coordinates')
    elif not same_position(info['position'], approved['position']): changes.append('Replace camera coordinates')
    for name, label, ref in (
        ('GPSAltitude', 'altitude', approved.get('altitude_ref')),
        ('GPSImgDirection', 'image direction', approved.get('direction_ref')),
    ):
        wanted = approved['altitude' if name == 'GPSAltitude' else 'direction']
        present = any(key.endswith(':' + name) for key in info['gps'])
        if wanted is None:
            if name in removed: changes.append('Remove ' + label)
            continue
        if not raw: continue
        try:
            actual, actual_ref = optional_gps_record(raw, name, -12000 if name == 'GPSAltitude' else 0,
                                                   100000 if name == 'GPSAltitude' else 359.999999)
            wanted_ref = (ref or str(int(wanted < 0))) if name == 'GPSAltitude' else ref
            # Same canonical values/tolerance as matches_approved; explanation only.
            if actual is None or abs(actual - wanted) > 1e-5 or actual_ref != wanted_ref:
                changes.append(('Update ' if present else 'Add ') + label)
        except ValueError: changes.append('Correct ' + label + ' metadata')
    if removed & {'GPSDateStamp', 'GPSTimeStamp'}: changes.append('Remove GPS fix time')
    if any(name.startswith(('GPSSpeed', 'GPSTrack')) for name in removed): changes.append('Remove GPS movement details')
    retained = {'GPSVersionID', 'GPSMapDatum', 'GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef',
                'GPSAltitude', 'GPSAltitudeRef', 'GPSImgDirection', 'GPSImgDirectionRef', 'GPSDateStamp', 'GPSTimeStamp'}
    if any(name not in retained and not name.startswith(('GPSSpeed', 'GPSTrack')) for name in removed):
        changes.append('Reconcile other location metadata')
    if info['duplicate_records'] or any(not key.startswith('GPS:') for key in info['gps']):
        changes.append('Reconcile GPS records')
    if raw and metadata_value(raw, 'GPS', 'GPSMapDatum') is None: changes.append('Record WGS84 datum')
    return list(dict.fromkeys(changes)) or ['Reconcile GPS metadata']


def destination_status(entry, proposed=None, inspecting=False):
    info = entry.get('location_before')
    blocked = blocked_destination(entry, inspecting)
    if blocked: return blocked
    if not inspecting and entry['status'] == 'skip': return 'Already matches, no change'
    if not info: return 'Blocked: inspection unavailable'
    if proposed is None: return 'Choose a location source'
    if info['position'] is None:
        return 'GPS conflict, review required' if info['categories']['camera']['issues'] else 'Add GPS'
    if same_position(info['position'], proposed):
        if inspecting: return 'GPS matches; preview required'
        changes = gps_summary_changes(entry)
        return changes[0] + '; GPS matches' if len(changes) == 1 and changes[0] != 'Reconcile GPS metadata' else 'Update GPS information'
    return 'Replace existing GPS'


def gps_summary_changes(entry):
    """Keep datum bookkeeping in the technical report, not the ordinary summary."""
    return [label for label in entry.get('gps_change_labels', []) if label != 'Record WGS84 datum']


def places_text(info):
    values = []
    for key, value in info.get('places', {}).items():
        for sub, item in leaves(value, key):
            if 'GPS' not in sub and item not in (None, ''):
                values.append(str(item))
    return '; '.join(dict.fromkeys(values)) or 'No place names recorded in the file'


def gps_overview(info):
    if not info: return 'Inspection unavailable'
    text = position_text(info['position']) if info['position'] is not None else ('Camera coordinates need review' if info['categories']['camera']['issues'] else 'No camera coordinates recorded')
    other = [COORDINATE_CATEGORIES[r['category']] for r in info['records']
             if r['category'] != 'camera' and r['position'] is not None]
    if other: text += '; ' + ', '.join(dict.fromkeys(other)) + ' also recorded'
    return text


def reference_caption(path, data, units):
    name = Path(path).name
    if not data: return name + '\nReading GPS information…'
    if data.get('error'): return name + '\nGPS information could not be read'
    try:
        raw = data['raw']; info = summarize(raw)
        lines = [name, 'Camera GPS present — ' + position_text(info['position']) if info['position'] else ('Camera coordinates need review' if info['categories']['camera']['issues'] else 'No camera coordinates recorded')]
        try:
            altitude = optional_gps(raw, 'GPSAltitude', -12000, 100000)
            lines.append('Altitude: ' + (height(altitude, units) if altitude is not None else 'not recorded'))
        except ValueError as exc: lines.append('Altitude needs review: ' + str(exc))
        stamps = list(dict.fromkeys(str(v) for k, v in raw.items() if k.split(':')[-1] == 'DateTimeOriginal'))
        lines.append('Capture date: ' + (' / '.join(stamps) if stamps else 'not recorded'))
        others = [COORDINATE_CATEGORIES[r['category']] for r in info['records'] if r['category'] != 'camera' and r['position'] is not None]
        if others: lines.append('Other location records: ' + ', '.join(dict.fromkeys(others)) + ' (not copied)')
        if info['issues']: lines.append('Location information needs review; see Technical Metadata.')
        return '\n'.join(lines)
    except ValueError as exc:
        return name + '\nGPS information needs review: ' + str(exc)


def friendly_field(key):
    name = key.split(':')[-1]
    labels = {'GPSSpeed': 'Speed', 'GPSSpeedRef': 'Speed units', 'GPSTrack': 'Direction of travel',
              'GPSTrackRef': 'Travel direction reference', 'GPSImgDirection': 'Recorded image direction',
              'GPSImgDirectionRef': 'Image direction reference', 'GPSDOP': 'Position dilution (DOP)',
              'GPSHPositioningError': 'Recorded horizontal error', 'GPSMeasureMode': 'Position measurement mode',
              'GPSAltitudeRef': 'Altitude reference', 'GPSDestDistanceRef': 'Subject distance units'}
    if name in labels: return labels[name]
    name = re.sub(r'GPS|LocationShown|LocationCreated', '', name)
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).replace('_', ' ').strip() or 'Location value'


def location_sections(entry, units, technical=False):
    """Complete inspection evidence, grouped for the optional metadata view."""
    sections = [('Image', [entry['source']])]
    info = entry.get('location_before')
    if not info:
        sections.append(('Inspection failure', [entry.get('error') or 'GPS information could not be read']))
        if entry.get('warnings'): sections.append(('Warnings', entry['warnings']))
        if technical and entry.get('rows'):
            sections.append(('Inspection and change details', [' | '.join(row[1:]) for row in entry['rows']]))
        return sections
    groups = {title: [] for title in ('Camera position', 'Other locations depicted or described', 'Place names recorded in the file',
        'Altitude, direction and movement', 'Location timestamps', 'Precision and measurement accuracy', 'Conflicts or warnings')}
    for r in info['records']:
        group = 'Camera position' if r['category'] == 'camera' else 'Other locations depicted or described'
        rendered = position_text(r['position'])
        if r['issues']: rendered += ' — ' + '; '.join(r['issues'])
        if r['category'] != 'camera': rendered = COORDINATE_CATEGORIES[r['category']] + ': ' + rendered
        if rendered not in groups[group]: groups[group].append(rendered)
        if r['stored_digits']:
            groups['Precision and measurement accuracy'].append(COORDINATE_CATEGORIES[r['category']] +
                ': stored decimal places ' + ' / '.join(map(str, r['stored_digits'])))
    groups['Place names recorded in the file'].append(places_text(info))
    # Flatten all recognized fields, including structured arrays, keeping their
    # semantic context. The complete unchanged source fields are available below.
    flat = dict(leaves(info['fields']))
    for key, value in flat.items():
        label = COORDINATE_CATEGORIES[coordinate_category(key)] + ' — ' + friendly_field(key)
        if 'Altitude' in key or 'Direction' in key or any(t in key for t in ('GPSSpeed', 'GPSDestDistance', 'GPSTrack')):
            rendered = value_text(value)
            if key.endswith('Altitude'):
                try:
                    from kim_location import gps_detail
                    metres, _ = gps_detail(flat, key, 'GPSAltitude', -12000, 100000)
                    rendered = height(metres, units)
                except ValueError: rendered += ' (altitude could not be interpreted reliably)'
            elif key.endswith('AltitudeRef'):
                rendered = {'0': 'above the ellipsoidal surface (EXIF 3.0)', '1': 'below the ellipsoidal surface (EXIF 3.0)',
                            '2': 'positive height relative to sea level', '3': 'negative height relative to sea level'}.get(str(value), rendered)
            elif key.endswith(('DirectionRef', 'GPSTrackRef')):
                rendered = {'T': 'true north', 'M': 'magnetic north'}.get(str(value), rendered)
            elif key.endswith('GPSSpeedRef'):
                rendered = {'K': 'kilometres per hour', 'M': 'miles per hour', 'N': 'knots'}.get(str(value), rendered)
            elif key.endswith('GPSDestDistanceRef'):
                rendered = {'K': 'kilometres', 'M': 'miles', 'N': 'nautical miles'}.get(str(value), rendered)
            elif key.endswith('GPSDestDistance'):
                try:
                    ref = flat.get(key + 'Ref')
                    factor = {'K': 1000, 'M': 1609.344, 'N': 1852}.get(str(ref))
                    if factor: rendered = distance(float(value) * factor, units)
                except (ValueError, TypeError): pass
            groups['Altitude, direction and movement'].append(label + ': ' + rendered)
        elif any(t in key for t in ('TimeStamp', 'DateStamp', 'DateTime')):
            groups['Location timestamps'].append(label + ': ' + value_text(value))
        elif any(t in key for t in ('Accuracy', 'HPositioningError', 'GPSDOP', 'GPSMeasureMode')):
            rendered = value_text(value)
            if any(t in key for t in ('HPositioningError', 'LocationAccuracyHorizontal')):
                try: rendered = distance(float(value), units)
                except (ValueError, TypeError): pass
            if key.endswith('GPSMeasureMode'): rendered = {'2': 'two-dimensional fix', '3': 'three-dimensional fix'}.get(str(value), rendered)
            groups['Precision and measurement accuracy'].append(label + ': ' + rendered)
    groups['Precision and measurement accuracy'].append('Stored decimal places do not establish measurement accuracy. Accuracy is unknown unless recorded separately.')
    groups['Conflicts or warnings'].extend(dict.fromkeys([*info['issues'], *entry.get('warnings', []), entry.get('error', '')]))
    if entry.get('approved_location') and entry.get('status') == 'change':
        approved = entry['approved_location']
        groups['Camera position'].append('New location: ' + position_text(approved['position']))
        groups['Altitude, direction and movement'].append('New altitude: ' + (height(approved['altitude'], units) if approved['altitude'] is not None else 'not retained'))
    if 'displacement_m' in entry:
        groups['Camera position'].append('Approximate displacement: ' + distance(entry['displacement_m'], units))
    if entry.get('removed_fields') and entry.get('status') == 'change':
        groups['Conflicts or warnings'].append('Location metadata being removed or replaced: ' + ', '.join(friendly_field(k) for k in entry['removed_fields']))
    if entry.get('output_description'):
        sections.append(('Output', [entry['output_description']]))
    if entry.get('gps_change_labels'):
        sections.append(('Planned GPS changes', entry['gps_change_labels']))
    for title, contents in groups.items():
        sections.append((title, list(dict.fromkeys(s for s in contents if s)) or ['None recorded']))
    if technical:
        sections.append(('Technical metadata fields (original stored values and units)',
                         [key + ': ' + value_text(value) for key, value in info['fields'].items()] or ['None recorded']))
        if entry.get('rows'):
            sections.append(('Inspection and change details', [' | '.join(row[1:]) for row in entry['rows']
                if not (row[1] == 'Output policy / destination' and entry.get('status') != 'change')]))
    return sections


def location_details(entry, units, technical=False):
    return '\n\n'.join(title + '\n' + '\n'.join(values)
                        for title, values in location_sections(entry, units, technical))


def recorded_location_rows(info, units):
    """Concise existing information; interpretation stays with the GPS parser."""
    if not info: return []
    rows = []
    for name, low, high, label in (('GPSAltitude', -12000, 100000, 'Altitude'),
                                  ('GPSImgDirection', 0, 359.999999, 'Image direction')):
        try:
            value, ref = optional_gps_record(info['fields'], name, low, high)
            if value is None: continue
            if name == 'GPSAltitude':
                reference = 'ellipsoidal surface' if ref in ('0', '1') else 'sea level'
                text = height(abs(value), units) + (' below ' if ref in ('1', '3') else ' above ') + reference
            else:
                text = f'{value:g}° from ' + ('true north' if ref == 'T' else 'magnetic north')
            rows.append((label, text))
        except ValueError:
            rows.append((label, 'Recorded, but needs review — see Technical Metadata'))
    if info['places']: rows.append(('Place names in file', places_text(info)))
    others = [COORDINATE_CATEGORIES[r['category']] + ': ' + position_text(r['position'])
              for r in info['records'] if r['category'] != 'camera' and r['position'] is not None and not r['issues']]
    if others: rows.append(('Other recorded locations', '\n'.join(dict.fromkeys(others))))
    # Full timestamps, movement, accuracy and their provenance remain in metadata.
    flat = dict(leaves(info['fields']))
    additional = []
    if any(any(part in key for part in ('TimeStamp', 'DateStamp', 'DateTime')) for key in flat):
        additional.append('Location timestamps recorded')
    if any(any(part in key for part in ('GPSSpeed', 'GPSTrack', 'GPSDestDistance')) for key in flat):
        additional.append('Movement or subject-distance information recorded')
    if any(any(part in key for part in ('Accuracy', 'HPositioningError', 'GPSDOP', 'GPSMeasureMode')) for key in flat):
        additional.append('Position measurement information recorded')
    coordinate_fields = {'GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef', 'GPSVersionID', 'GPSMapDatum'}
    if not rows and not additional and any(key.split(':')[-1] not in coordinate_fields for key in flat):
        additional.append('Other location information recorded — see Technical Metadata')
    if additional: rows.append(('Additional information', '\n'.join(additional)))
    return rows


def inspection_warning(entry):
    """Expose every affected category without putting raw tag names in the summary."""
    info = entry.get('location_before')
    warnings = []
    if info:
        for category, data in info['categories'].items():
            if data['issues']:
                warnings.append((camera_status(info) if category == 'camera' else
                                 COORDINATE_CATEGORIES[category] + ' needs review') + ' — see Technical Metadata')
            if data['optional_issues']:
                warnings.append(COORDINATE_CATEGORIES[category] + ': additional location information needs review')
        if info['duplicate_records']: warnings.append('Duplicate location records — see Technical Metadata')
    warnings.extend(w for w in entry.get('warnings', []) if not info or w not in info['issues'])
    return '\n'.join(dict.fromkeys(warnings))


def operation_inspector_rows(entry, *, planned, inspecting, refreshing=False):
    """Present an existing plan entry; never infer new changes or output paths."""
    if not entry: return [('Selected image', 'Select a destination image')]
    rows = [('Selected image', Path(entry['source']).name)]
    if refreshing:
        return rows + [('Action', 'Refreshing proposal…'), ('Output', 'Not yet available')]
    info = entry.get('location_before')
    blocked = blocked_destination(entry, inspecting)
    if blocked:
        rows += [('Action', 'Skipped'), ('Reason', blocked), ('Output', 'No output created')]
        warning = inspection_warning(entry)
        if warning: rows.append(('Review', warning))
        return rows
    if not planned:
        rows += [('Action', 'Preview required'), ('Existing location', position_text(info['position'])
                 if info and info['position'] is not None else camera_status(info)),
                 ('Output', 'Determined in final preview')]
    elif entry['status'] == 'skip':
        rows += [('Action', 'Already matches, no change'), ('Location', 'Existing GPS already matches the requested result.'),
                 ('Output', 'No output created')]
    elif entry['status'] == 'change' and entry.get('approved_location'):
        approved = entry['approved_location']
        # Classification and optional-field changes are supplied by the planner.
        rows += [('Action', destination_status(entry, approved['position'])),
                 ('Existing location', position_text(info['position']) if info and info['position'] is not None else camera_status(info)),
                 ('New location', position_text(approved['position']))]
        changes = [label for label in gps_summary_changes(entry)
                   if label not in ('Set camera GPS coordinates', 'Replace camera coordinates')]
        if changes: rows.append(('Additional changes', '\n'.join(changes)))
        target = entry.get('target')
        rows.append(('Output', Path(target).name if target else 'No output created'))
        if target == entry['source']: rows.append(('Output policy', 'Update original, subject to final approval'))
    else:
        rows += [('Action', 'Preview required'), ('Output', 'Not yet available')]
    warning = inspection_warning(entry)
    if warning: rows.append(('Review', warning))
    return rows


def privacy_inspector_rows(entry, units):
    if not entry: return [('Camera location', 'Select an image')]
    info = entry.get('location_before')
    rows = [('Camera location', position_text(info['position']) if info and info['position'] is not None else camera_status(info))]
    if info:
        additional = recorded_location_rows(info, units)
        rows += additional or [('Other location information', 'No additional location metadata recorded.')]
        privacy = []
        if info['position'] is not None: privacy.append('Camera GPS coordinates are recorded in this image.')
        elif info['categories']['camera']['issues']: privacy.append('Camera location metadata is present but cannot be interpreted reliably.')
        if any(r['category'] != 'camera' for r in info['records']) or info['places']:
            privacy.append('Other recorded location information may reveal a location.')
        if info['fields'] and not privacy: privacy.append('Recorded location information is available in Technical Metadata.')
        if privacy: rows.append(('Privacy', '\n'.join(privacy)))
    else:
        rows.append(('Inspection', 'Could not read location metadata. See Technical Metadata for the cause.'))
    warning = inspection_warning(entry)
    if warning: rows.append(('Review', warning))
    rows.append(('Privacy reminder', 'Visible photograph content and other metadata may reveal a location even when GPS is absent.'))
    return rows


class ElidedImageLabel(QLabel):
    """A selectable filename with its full path available without widening a pane."""
    def __init__(self):
        super().__init__()
        self.full_text = ''
        self.setTextFormat(Qt.PlainText)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def set_value(self, text, full_path):
        self.full_text = text
        self.setToolTip(full_path or text); self.setAccessibleName(text)
        self.elide()

    def elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideMiddle, max(1, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event); self.elide()


def metadata_display_rows(values):
    """Lay out existing formatted evidence without interpreting stored values."""
    if values == ['None recorded']: return []
    rows = []
    for value in values:
        label, separator, text = value.partition(': ')
        if not separator: label, text = 'Information', value
        label = label.removeprefix(COORDINATE_CATEGORIES['camera'] + ' — ')
        label = {'Date Stamp': 'GPS date', 'Time Stamp': 'GPS time',
                 'Recorded image direction': 'Image direction (degrees)'}.get(label, label)
        rows.append((label, text))
    return rows


def metadata_summary_sections(entry, sections):
    """Photographer-facing rows over the existing parsed summary and formatters."""
    if not entry: return []
    info = entry.get('location_before'); evidence = dict(sections)
    image = [('Filename', Path(entry['source']).name), ('Full file path', entry['source'])]
    if info: image.append(('File format', str(info['format'])))
    result = [('Image', image)]
    if not info:
        result.append(('Inspection', [('Error', entry.get('error') or 'GPS information could not be read')]))
        if entry.get('warnings'):
            result.append(('Warnings', [('Warning', warning) for warning in entry['warnings']]))
        return result
    camera = []
    if info['position'] is not None:
        latitude, longitude = position_text(info['position']).split(', ', 1)
        camera += [('Latitude', latitude), ('Longitude', longitude)]
    else:
        camera.append(('Camera GPS', camera_status(info)))
    other = []
    if info['places']: other.append(('Place names', places_text(info)))
    other += metadata_display_rows(evidence.get('Other locations depicted or described', []))
    other += metadata_display_rows(evidence.get('Location timestamps', []))
    changes = []
    for label, value in metadata_display_rows(evidence.get('Altitude, direction and movement', [])):
        if label == 'New altitude': changes.append((label, value))
        elif ' — ' in label: other.append((label, value))
        else: camera.append((label, value))
    result.append(('Camera location', camera))
    if other: result.append(('Other location information', other))
    quality = [('Coordinate interpretation', camera_status(info))] if info['position'] is not None else []
    warning = inspection_warning(entry).replace(' — see Technical Metadata', '')
    if info['duplicate_records']:
        warning = '\n'.join(line for line in warning.splitlines() if line != 'Duplicate location records')
    if warning: quality.append(('Review', warning))
    elif info['issues']: quality.append(('Review', 'Recorded location information needs review. See Technical Details.'))
    elif not entry.get('error'): quality.append(('Conflicts', 'No metadata conflicts detected.'))
    if entry.get('error'): quality.append(('Error', entry['error']))
    if info['duplicate_records']: quality.append(('Duplicate records', str(info['duplicate_records'])))
    for label, value in metadata_display_rows(evidence.get('Precision and measurement accuracy', [])):
        quality.append(('Precision limitation' if label == 'Information' else label, value))
    result.append(('Quality and conflicts', quality))
    for label, value in metadata_display_rows(evidence.get('Camera position', [])):
        if label in ('New location', 'Approximate displacement'): changes.append((label, value))
    if entry.get('approved_location') and entry.get('status') == 'change':
        changes.insert(0, ('Action', destination_status(entry, entry['approved_location']['position'])))
    changes += [('Additional change', label) for label in gps_summary_changes(entry)
                if label not in ('Set camera GPS coordinates', 'Replace camera coordinates')]
    if entry.get('output_description'): changes.append(('Output', entry['output_description']))
    if changes: result.append(('Planned changes', changes))
    return result


class TechnicalMetadataDialog(QDialog):
    """Shared native viewer; interpretation stays in the existing GPS helpers."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Technical Metadata')
        self.setSizeGripEnabled(True)
        available = self.screen().availableGeometry()
        self.resize(min(900, available.width() * 9 // 10), min(650, available.height() * 9 // 10))
        self.setMinimumSize(min(480, available.width() * 4 // 5), min(320, available.height() * 4 // 5))
        layout = QVBoxLayout(self)
        self.controls = QVBoxLayout(); layout.addLayout(self.controls)
        self.tabs = QTabWidget()
        self.summary = self.make_table(2, 'Location summary')
        self.technical = self.make_table(3, 'Original metadata and inspection evidence')
        self.tabs.addTab(self.summary, 'Location Summary')
        self.tabs.addTab(self.technical, 'Technical Details')
        layout.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.copy_metadata = buttons.addButton('Copy Metadata', QDialogButtonBox.ActionRole)
        self.copy_metadata.clicked.connect(self.copy_full_metadata)
        buttons.rejected.connect(self.reject)
        for button in buttons.buttons(): button.setAutoDefault(False)
        layout.addWidget(buttons)
        self.full_metadata = ''

    def make_table(self, columns, accessible_name):
        table = QTableWidget(0, columns)
        table.setAccessibleName(accessible_name)
        table.setFont(self.font())
        table.setFrameShape(QTableWidget.NoFrame); table.setShowGrid(False)
        table.setAlternatingRowColors(True); table.setWordWrap(True)
        table.setTextElideMode(Qt.ElideNone)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.verticalHeader().hide(); table.horizontalHeader().hide()
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, min(self.width() // 3,
                                   self.fontMetrics().horizontalAdvance('Coordinate interpretation') + 24))
        for column in range(1, columns): header.setSectionResizeMode(column, QHeaderView.Stretch)
        # Width changes must also recompute wrapped row heights, including on first show.
        header.sectionResized.connect(table.resizeRowsToContents)
        return table

    @staticmethod
    def add_row(table, values, tooltip=None, heading=False):
        row = table.rowCount(); table.insertRow(row)
        if heading: table.setSpan(row, 0, 1, table.columnCount())
        elif len(values) == 2 and table.columnCount() == 3: table.setSpan(row, 1, 1, 2)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            item.setToolTip((tooltip + '\n' + value if column else tooltip) if tooltip else value)
            if column == 0 or heading:
                font = table.font(); font.setBold(True)
                if heading and font.pointSizeF() > 0: font.setPointSizeF(font.pointSizeF() * 1.1)
                item.setFont(font)
            table.setItem(row, column, item)

    def set_metadata(self, sections, full_metadata, entry):
        self.full_metadata = full_metadata  # The existing complete troubleshooting export.
        for table in (self.summary, self.technical):
            table.setUpdatesEnabled(False); table.clearSpans(); table.setRowCount(0)
        for title, rows in metadata_summary_sections(entry, sections):
            self.add_row(self.summary, [title], heading=True)
            for row in rows: self.add_row(self.summary, row)
        info = entry.get('location_before') if entry else None
        if info and info['fields']:
            self.add_row(self.technical, ['Original metadata fields'], heading=True)
            self.add_row(self.technical, ['Field', 'Original value', 'Source'])
            for key, value in info['fields'].items():
                source, _, field = key.rpartition(':')
                self.add_row(self.technical, [field, value_text(value), source], tooltip=key)
        # Keep every existing formatted category available as detailed evidence.
        # Original fields and diagnostic columns have their own structured rows.
        for title, values in sections:
            if title in ('Image', 'Technical metadata fields (original stored values and units)',
                         'Inspection and change details'): continue
            if title == 'Place names recorded in the file' and not (info and info['places']): continue
            rows = metadata_display_rows(values)
            if not rows: continue
            self.add_row(self.technical, [title], heading=True)
            for row in rows: self.add_row(self.technical, row)
        diagnostics = [row for row in entry.get('rows', [])
                       if not (info and row[1] == 'Output policy / destination' and entry.get('status') != 'change')] if entry else []
        if diagnostics:
            self.add_row(self.technical, ['Inspection details'], heading=True)
            self.add_row(self.technical, ['Inspection', 'Recorded / proposed', 'Evidence'])
            for row in diagnostics:
                values = '\n'.join(label + ': ' + value for label, value in
                                   (('Recorded', row[2]), ('Proposed', row[3])) if value)
                self.add_row(self.technical, [row[1], values, row[4]])
        for table in (self.summary, self.technical):
            table.resizeRowsToContents(); table.scrollToTop(); table.setUpdatesEnabled(True)
        self.tabs.setCurrentIndex(0)
        self.copy_metadata.setEnabled(bool(sections))

    def copy_full_metadata(self):
        QApplication.clipboard().setText(self.full_metadata)


class LocationInspector(QWidget):
    """Small shared presentation surface; callers supply workflow-specific rows."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title); font = heading.font(); font.setBold(True); heading.setFont(font)
        layout.addWidget(heading)
        self.summary = QScrollArea(); self.summary.setWidgetResizable(True); self.summary.setFrameShape(QScrollArea.NoFrame)
        self.summary.setMinimumSize(0, 0); self.summary.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_content = QWidget()
        self.form = QFormLayout(self.summary_content); self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self.form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.form.setVerticalSpacing(layout.spacing())
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.summary.setWidget(self.summary_content); layout.addWidget(self.summary, 1)
        self.metadata_dialog = TechnicalMetadataDialog(self)
        self.metadata_controls = self.metadata_dialog.controls
        self.metadata_button = QPushButton('Technical Metadata…')
        self.metadata_button.setAutoDefault(False); self.metadata_button.setEnabled(False)
        layout.addWidget(self.metadata_button)
        self.sections = None

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance('M') * 36, self.fontMetrics().lineSpacing() * 12)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def set_summary(self, rows, entry=None):
        if getattr(self, 'summary_rows', None) == (rows, entry.get('source') if entry else None, entry.get('target') if entry else None): return
        self.summary_rows = (rows, entry.get('source') if entry else None, entry.get('target') if entry else None)
        while self.form.rowCount(): self.form.removeRow(0)
        for title, text in rows:
            if title in ('Selected image', 'Output'):
                value = ElidedImageLabel()
                path = entry.get('source' if title == 'Selected image' else 'target') if entry else None
                value.set_value(text, path if path and text == Path(path).name else text)
            else:
                value = QLabel(text); value.setTextFormat(Qt.PlainText); value.setWordWrap(True)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                value.setFocusPolicy(Qt.ClickFocus); value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            value.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.form.addRow(title + ':', value)

    def set_metadata(self, entry, units):
        sections = location_sections(entry, units, True) if entry else []
        if sections == self.sections: return
        self.sections = sections
        self.metadata_dialog.set_metadata(sections, location_details(entry, units, True) if entry else '', entry)
        self.metadata_button.setEnabled(bool(sections))

    def show_metadata(self):
        if not self.sections: return
        if self.metadata_dialog.isVisible():
            self.metadata_dialog.raise_(); self.metadata_dialog.activateWindow()
        else:
            # Window-modal open keeps destination selection intact without a nested event loop.
            self.metadata_dialog.open()
