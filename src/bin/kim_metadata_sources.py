"""Shared, read-only metadata source preference and selection helpers."""
from __future__ import annotations

from dataclasses import dataclass
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
        sidecar = Path(entry.source).resolve(strict=False) != Path(record.path).resolve(strict=False)
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
    buckets = {}
    editability = {}
    for entry in record.entries:
        source = source_name(entry, record)
        if not source:
            continue
        mapping = _source_mapping(spec, entry, source)
        editable = bool(mapping)
        if not mapping and source == "EXIF" and entry.name.casefold() in {name.casefold() for name in spec.aliases}:
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
    if not isinstance(best.value, list) and len({repr(entry.value) for entry in same_target}) > 1:
        return None
    return best


def preferred_representation(record, spec, priority=SOURCE_PRIORITY_DEFAULT, locale=""):
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
