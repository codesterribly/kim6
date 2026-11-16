"""Shared, read-only metadata source preference and selection helpers."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

try:
    from PySide6.QtCore import QSettings
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        QSettings = None
    else:
        raise


SOURCE_PRIORITY_DEFAULT = (
    "Embedded XMP",
    "XMP sidecar",
    "IPTC-IIM",
    "EXIF",
)
SOURCE_SETTING_KEY = "metadata/readingPriority"
SYNC_SETTING_KEY = "metadata/syncIptcXmpDefault"


def overview_source(entry, record):
    """Keep file provenance even for tags outside the editable source families."""
    known = source_name(entry, record)
    if known:
        return known
    return 'Embedded image' if os.path.abspath(entry.source) == os.path.abspath(record.path) else 'Associated sidecar'


@dataclass(frozen=True)
class OverviewField:
    selector: str
    label: str
    section: str = 'Additional fields'
    aliases: tuple[str, ...] = ()
    source: str = ''
    language: str = ''

    @property
    def selectors(self):
        return self.aliases or (self.selector,)

    @property
    def key(self):
        return self.selector.casefold(), self.source, self.language.casefold()

    def entries(self, record):
        from kim_metadata_reader import _select_fields
        selection = _select_fields(self.selectors)
        return [entry for entry in record.entries if selection.includes(entry) and
                (not self.source or overview_source(entry, record) == self.source) and
                (not self.language or (entry.language or '').casefold() == self.language.casefold())]


OVERVIEW_DEFAULTS = (
    OverviewField('Title', 'Title', 'Description', ('Title', 'ObjectName')),
    OverviewField('Description', 'Description', 'Description', ('Description', 'Caption-Abstract', 'ImageDescription')),
    OverviewField('Keywords', 'Keywords', 'Description', ('Subject', 'Keywords')),
    OverviewField('Creator', 'Creator', 'Creator & rights', ('Creator', 'By-line', 'Artist')),
    OverviewField('Copyright', 'Copyright notice', 'Creator & rights', ('Rights', 'CopyrightNotice', 'Copyright')),
    OverviewField('UsageTerms', 'Usage terms', 'Creator & rights', ('UsageTerms', 'RightsUsageTerms')),
    OverviewField('Make', 'Camera', 'Camera & capture', ('Make', 'Model')),
    OverviewField('LensModel', 'Lens', 'Camera & capture', ('LensModel', 'LensID')),
    OverviewField('DateTimeOriginal', 'Capture date', 'Camera & capture', ('DateTimeOriginal', 'CreateDate')),
    OverviewField('ImageSize', 'Image dimensions', 'Camera & capture', ('ImageSize', 'ImageWidth', 'ImageHeight')),
    OverviewField('ExposureTime', 'Exposure', 'Camera & capture'),
    OverviewField('FNumber', 'Aperture', 'Camera & capture', ('FNumber', 'Aperture')),
    OverviewField('ISO', 'ISO', 'Camera & capture', ('ISO', 'PhotographicSensitivity')),
    OverviewField('FocalLength', 'Focal length', 'Camera & capture'),
    OverviewField('GPSPosition', 'GPS position', 'Location', ('GPSPosition', 'GPSCoordinates', 'GPSLatitude', 'GPSLongitude', 'GPSLatitudeRef', 'GPSLongitudeRef')),
    OverviewField('GPSAltitude', 'GPS altitude', 'Location', ('GPSAltitude', 'GPSAltitudeRef')),
    OverviewField('Location', 'Location', 'Location', ('Location', 'City', 'State', 'Country', 'CountryName')),
)
OVERVIEW_CATALOG = OVERVIEW_DEFAULTS + tuple(OverviewField(tag, label) for tag, label in (
    ('Rating', 'Rating'), ('Software', 'Software'), ('WhiteBalance', 'White balance'),
    ('Flash', 'Flash'), ('ExposureProgram', 'Exposure program'), ('ColorSpace', 'Color space'),
    ('Orientation', 'Orientation'), ('SerialNumber', 'Camera serial number'),
    ('ImageUniqueID', 'Image identifier'), ('PersonInImage', 'People in image')))


class OverviewPreferences:
    """One ordered field selection shared by metadata inspection applications."""
    KEY = 'metadata/overviewFieldsV1'

    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings('KIM6', 'MetadataTools')
        self.reload()

    def reload(self):
        try:
            self.settings.sync()
            raw = self.settings.value(self.KEY, '')
            decoded = json.loads(raw) if raw else None
            if decoded is not None and (not isinstance(decoded, list) or any(not isinstance(value, dict) for value in decoded)):
                raise ValueError('Invalid overview configuration.')
            fields = [OverviewField(**dict(value, aliases=tuple(value.get('aliases', ())))) for value in decoded] if decoded is not None else list(OVERVIEW_DEFAULTS)
            self.validate(fields)
            self.fields = fields
        except (ValueError, TypeError, KeyError):
            self.fields = list(OVERVIEW_DEFAULTS)
        return self

    @staticmethod
    def validate(fields):
        from kim_metadata_reader import _select_fields
        if any(not isinstance(field, OverviewField) or
               any(not isinstance(getattr(field, name), str) for name in ('selector', 'label', 'section', 'source', 'language'))
               for field in fields):
            raise ValueError('Invalid overview field.')
        if len(fields) > 64 or len({field.key for field in fields}) != len(fields):
            raise ValueError('Choose at most 64 distinct overview fields.')
        for field in fields:
            if not field.label or len(field.label) > 256 or field.source not in ('', *SOURCE_PRIORITY_DEFAULT, 'Embedded image', 'Associated sidecar'):
                raise ValueError('Invalid overview field.')
            _select_fields((field.selector,))
        selectors = tuple(dict.fromkeys(['FileType', 'ImageWidth', 'ImageHeight'] + [name for field in fields for name in field.selectors]))
        _select_fields(selectors)
        return selectors

    @property
    def selectors(self):
        return self.validate(self.fields)

    def save(self, fields):
        from dataclasses import asdict
        fields = list(fields)
        self.validate(fields)
        self.settings.setValue(self.KEY, json.dumps([asdict(field) for field in fields], ensure_ascii=False))
        self.settings.sync()
        self.fields = fields

    @staticmethod
    def _entry_field(entry, record):
        return OverviewField(entry.qualified_name, entry.name + (f' ({entry.language})' if entry.language else '') + f' · {entry.group}',
                             source=overview_source(entry, record), language=entry.language or '')

    def is_pinned(self, entry, record):
        key = self._entry_field(entry, record).key
        return any(field.key == key for field in self.fields)

    def toggle_entry(self, entry, record):
        self.reload()
        field = self._entry_field(entry, record)
        existing = next((item for item in self.fields if item.key == field.key), None)
        self.save([item for item in self.fields if item.key != field.key] if existing else [*self.fields, field])

    def select_record(self, record):
        from kim_metadata_reader import MetadataRecord, _select_fields
        selection = _select_fields(self.selectors)
        fields = [(field, _select_fields(field.selectors)) for field in self.fields]
        entries = [entry for entry in record.entries if selection.includes(entry) and (
            entry.name.casefold() == 'filetype' or any(chosen.includes(entry) and
            (not field.source or overview_source(entry, record) == field.source) and
            (not field.language or (entry.language or '').casefold() == field.language.casefold())
            for field, chosen in fields))]
        return MetadataRecord(record.path, entries,
                              record.sidecars, record.error, record.warnings)


def _valid_priority(value: Any) -> tuple[str, ...]:
    try:
        values = list(value)
    except TypeError:
        values = []
    ordered = [source for source in values if source in SOURCE_PRIORITY_DEFAULT]
    ordered = list(dict.fromkeys(ordered))
    ordered.extend(source for source in SOURCE_PRIORITY_DEFAULT if source not in ordered)
    return tuple(ordered)


class MetadataSourcePreferences:
    """Qt settings wrapper shared by the standalone Editor and Browser."""

    def __init__(self, settings=None):
        if settings is None:
            if QSettings is None:
                raise RuntimeError("PySide6 QSettings is required for metadata preferences")
            settings = QSettings("KIM6", "MetadataTools")
        self.settings = settings
        self.reload()

    def reload(self):
        self.priority = _valid_priority(
            self.settings.value(SOURCE_SETTING_KEY, SOURCE_PRIORITY_DEFAULT))
        self.sync_default = bool(self.settings.value(SYNC_SETTING_KEY, False, type=bool))
        return self

    def save(self, priority=None, sync_default=None):
        if priority is not None:
            self.priority = _valid_priority(priority)
            self.settings.setValue(SOURCE_SETTING_KEY, list(self.priority))
        if sync_default is not None:
            self.sync_default = bool(sync_default)
            self.settings.setValue(SYNC_SETTING_KEY, self.sync_default)
        self.settings.sync()
        return self

    def snapshot(self) -> tuple[tuple[str, ...], bool]:
        return self.priority, self.sync_default


@dataclass(frozen=True)
class TargetIdentity:
    """Stable, explicit identity for a planned source representation."""

    source: str
    source_path: str
    qualified_tag: str
    language: str | None = None
    entry_keys: tuple[str, ...] = ()
    is_new: bool = False

    @property
    def key(self) -> str:
        parts = (self.source, self.source_path, self.qualified_tag,
                 self.language or "", "\x1e".join(self.entry_keys), str(self.is_new))
        return "\x1f".join(parts)

    @property
    def display(self) -> str:
        language = f" · {self.language}" if self.language else ""
        return f"{self.source}{language}"


@dataclass(frozen=True)
class MetadataRepresentation:
    source: str
    source_path: str
    qualified_tag: str
    language: str | None
    entries: tuple[Any, ...]
    value: Any
    ambiguous: bool = False
    canonical_target: str = ""
    editable: bool = True

    @property
    def target(self) -> TargetIdentity:
        keys = tuple(_entry_key(entry) for entry in self.entries)
        return TargetIdentity(self.source, self.source_path, self.canonical_target or self.qualified_tag,
                              self.language, keys)

    @property
    def is_empty(self) -> bool:
        return self.value in (None, "", [], {})


def _entry_key(entry) -> str:
    return "\x1f".join((entry.qualified_name, str(entry.tag_id or ""),
                        entry.language or "", str(entry.source)))


def source_name(entry, record) -> str | None:
    """Return only a known, qualified metadata source category."""
    try:
        # Extraction already canonicalizes paths and rejects final symlinks.
        # Source classification must not repeat filesystem resolution per value.
        sidecar = entry.source != record.path and os.path.abspath(entry.source) != os.path.abspath(record.path)
    except (OSError, ValueError):
        return None
    groups = tuple(str(group).casefold() for group in (entry.groups or ()))
    if sidecar:
        return "XMP sidecar" if any(group.startswith("xmp") for group in groups) else None
    if any(group.startswith("xmp") for group in groups):
        return "Embedded XMP"
    if any(group.startswith("iptc") for group in groups):
        return "IPTC-IIM"
    if any(group.startswith("exif") for group in groups):
        return "EXIF"
    return None


def _source_mapping(spec, entry, source):
    groups = tuple(str(group).casefold() for group in (entry.groups or ()))
    name = entry.name.casefold()
    aliases = {str(value).casefold() for value in spec.aliases}
    if name not in aliases:
        return None
    if source in ("Embedded XMP", "XMP sidecar") and any(g.startswith("xmp") for g in groups):
        return spec.xmp
    if source == "IPTC-IIM" and spec.iim and any(g.startswith("iptc") for g in groups):
        return spec.iim
    exif_target = getattr(spec, "exif", None)
    if source == "EXIF" and exif_target and any(g.startswith("exif") for g in groups):
        return exif_target
    return None


def _typed_value(entries, multiple):
    if multiple:
        result = []
        for entry in entries:
            value = entry.value
            result.extend(value if isinstance(value, list) else [value])
        return result
    values = [entry.value for entry in entries]
    if len(values) > 1 and len({repr(value) for value in values}) > 1:
        return values
    return values[0] if values else ""


def metadata_representations(record, spec) -> list[MetadataRepresentation]:
    """Group actual entries by source, qualified field and language."""
    return _representations_from_entries(record, spec, record.entries)


def index_metadata_representations(record, specs) -> dict[str, list[MetadataRepresentation]]:
    """Select all requested fields in one pass, preserving entry order."""
    specs = tuple(specs)
    fields_by_name = {}
    candidates = {spec.key: [] for spec in specs}
    for spec in specs:
        for name in {alias.casefold() for alias in spec.aliases}:
            fields_by_name.setdefault(name, []).append(spec.key)
    for entry in record.entries:
        for key in fields_by_name.get(entry.name.casefold(), ()):
            candidates[key].append(entry)
    return {spec.key: _representations_from_entries(record, spec, candidates[spec.key])
            for spec in specs}


def _representations_from_entries(record, spec, entries):
    buckets = {}
    editability = {}
    aliases = {name.casefold() for name in spec.aliases}
    for entry in entries:
        if entry.name.casefold() not in aliases:
            continue
        source = source_name(entry, record)
        if not source:
            continue
        mapping = _source_mapping(spec, entry, source)
        editable = bool(mapping)
        if not mapping and source == "EXIF":
            # Keep a qualified, inspectable provenance representation without
            # inventing a writable EXIF mapping for a registry field.
            mapping = entry.qualified_name
            editable = False
        if not mapping:
            continue
        language = entry.language if spec.language_alt else None
        # A list property is one representation. Repeated IPTC list entries
        # share a qualified property and retain their input order/multiplicity.
        key = (source, str(Path(entry.source).resolve(strict=False)),
               mapping, language, entry.qualified_name, str(entry.tag_id or ""))
        buckets.setdefault(key, []).append(entry)
        editability[key] = editable
    representations = []
    for key, entries in buckets.items():
        source, source_path, mapping, language, qualified, _tag_id = key
        value = _typed_value(entries, spec.multiple)
        ambiguous = isinstance(value, list) and not spec.multiple
        representations.append(MetadataRepresentation(
            source, source_path, qualified, language, tuple(entries), value, ambiguous, mapping,
            editability[key]))
    return representations


def _normalized_language(value: str | None) -> str:
    return (value or "").replace("_", "-").casefold()


def ordered_representations(representations, priority=SOURCE_PRIORITY_DEFAULT,
                            locale=""):
    ranks = {source: index for index, source in enumerate(_valid_priority(priority))}
    locale_key = _normalized_language(locale)

    def language_rank(representation):
        language = _normalized_language(representation.language)
        if locale_key and language == locale_key:
            return 0
        if language == "x-default":
            return 1 if locale_key else 0
        if not language:
            return 2 if locale_key else 1
        return 2

    return sorted(representations, key=lambda item: (
        ranks.get(item.source, len(ranks)), language_rank(item),
        item.source_path.casefold(), item.qualified_tag.casefold(),
        (item.language or "").casefold()))


def preferred_entry(entries, record, priority=SOURCE_PRIORITY_DEFAULT,
                    language_alt=False, locale=""):
    """Choose one existing metadata entry without merging source values."""
    candidates = []
    for order, entry in enumerate(entries):
        source = source_name(entry, record)
        if source not in priority:
            continue
        candidates.append((source, entry, order))
    if not candidates:
        return None
    ranks = {source: index for index, source in enumerate(_valid_priority(priority))}
    locale_key = _normalized_language(locale)

    def language_rank(entry):
        if not language_alt:
            return 0
        language = _normalized_language(entry.language)
        if locale_key and language == locale_key:
            return 0
        if language == "x-default":
            return 1 if locale_key else 0
        if not language:
            return 2 if locale_key else 1
        return 2

    candidates.sort(key=lambda row: (ranks.get(row[0], len(ranks)),
                                     language_rank(row[1]), row[2]))
    best_source, best, _order = candidates[0]
    same_target = [entry for source, entry, _ in candidates
                   if source == best_source and language_rank(entry) == language_rank(best)]
    if len(same_target) > 1 and not isinstance(best.value, list) and len({repr(entry.value) for entry in same_target}) > 1:
        return None
    return best


def preferred_representation(record, spec, priority=SOURCE_PRIORITY_DEFAULT, locale="", *,
                             representations=None):
    """Rank stored representations using current source and language preferences."""
    if representations is None:
        representations = metadata_representations(record, spec)
    ordered = ordered_representations(representations, priority, locale)
    if not ordered:
        return None, representations
    first = ordered[0]
    if first.ambiguous:
        return None, representations
    equal_rank = [item for item in ordered
                  if item.source == first.source and item.language == first.language]
    # A scalar field with multiple different qualified values in the same
    # source/language is ambiguous. Never pick an arbitrary alias as a winner.
    if not spec.multiple and len(equal_rank) > 1:
        values = {repr(item.value) for item in equal_rank}
        if len(values) > 1:
            return None, representations
    return first, representations
