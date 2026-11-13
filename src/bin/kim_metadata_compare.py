"""Identity-aware, read-only comparison of two metadata records."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from kim_metadata_reader import MetadataEntry, MetadataRecord, value_text


@dataclass(frozen=True)
class ComparisonRow:
    section: str
    label: str
    identity: str
    reference: MetadataEntry | None
    comparison: MetadataEntry | None
    state: str
    technical: bool = False


_FIELD_SECTIONS = {
    "title": "Description", "objectname": "Description",
    "description": "Description", "caption-abstract": "Description",
    "imagedescription": "Description", "subject": "Description",
    "keywords": "Description",
    "creator": "Creator & rights", "by-line": "Creator & rights",
    "artist": "Creator & rights", "rights": "Creator & rights",
    "copyrightnotice": "Creator & rights", "copyright": "Creator & rights",
    "usageterms": "Creator & rights", "rightsusageterms": "Creator & rights",
    "make": "Camera & capture", "model": "Camera & capture",
    "lensmodel": "Camera & capture", "lensid": "Camera & capture",
    "datetimeoriginal": "Camera & capture", "createdate": "Camera & capture",
    "imagesize": "Camera & capture", "imagewidth": "Camera & capture",
    "imageheight": "Camera & capture", "iso": "Camera & capture",
    "photographicsensitivity": "Camera & capture", "exposuretime": "Camera & capture",
    "fnumber": "Camera & capture", "aperture": "Camera & capture",
    "focallength": "Camera & capture",
}
SECTION_ORDER = ("Description", "Creator & rights", "Camera & capture", "Other metadata", "Technical metadata")


def _source_kind(entry: MetadataEntry, record: MetadataRecord) -> str:
    """Treat source paths as provenance only, never as metadata values."""
    try:
        return "sidecar" if Path(entry.source).resolve(strict=False) != Path(record.path).resolve(strict=False) else "embedded"
    except (OSError, ValueError):
        return "embedded"


def _identity(entry: MetadataEntry, record: MetadataRecord) -> tuple[Any, ...]:
    # The qualified name captures ExifTool group and namespace identity. Keep
    # the explicit fields too, as ExifTool IDs/language are meaningful parts
    # of an identity and repeated identical entries need stable occurrence
    # slots. Only the source's embedded/sidecar role crosses image paths.
    return (entry.qualified_name.casefold(), tuple(str(g).casefold() for g in entry.groups),
            str(entry.tag_id).casefold() if entry.tag_id is not None else None,
            (entry.language or "").casefold(), _source_kind(entry, record))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _state(reference: MetadataEntry | None, comparison: MetadataEntry | None) -> str:
    if reference is None or comparison is None:
        present = reference or comparison
        if present is not None and present.value in ("", None, [], {}):
            return "empty"
        return "missing"
    if _canonical(reference.value) == _canonical(comparison.value):
        return "empty" if reference.value in ("", None, [], {}) else "identical"
    return "different"


def _is_technical(entry: MetadataEntry) -> bool:
    groups = {str(group).casefold() for group in entry.groups}
    return "exiftool" in groups or "file" in groups


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _entry_label(entry: MetadataEntry, record: MetadataRecord) -> str:
    readable = {
        "title": "Title", "objectname": "Object name", "description": "Description",
        "caption-abstract": "Caption", "imagedescription": "Image description",
        "subject": "Subject", "keywords": "Keywords", "creator": "Creator",
        "by-line": "Byline", "artist": "Artist", "rights": "Rights",
        "copyrightnotice": "Copyright notice", "copyright": "Copyright",
        "usageterms": "Usage terms", "rightsusageterms": "Rights usage terms",
        "make": "Camera make", "model": "Camera model", "lensmodel": "Lens model",
        "lensid": "Lens identifier", "datetimeoriginal": "Capture date",
        "createdate": "Creation date", "imagesize": "Image dimensions",
        "imagewidth": "Image width", "imageheight": "Image height", "iso": "ISO",
        "photographicsensitivity": "Photographic sensitivity", "exposuretime": "Exposure time",
        "fnumber": "Aperture", "aperture": "Aperture", "focallength": "Focal length",
    }
    label = readable.get(entry.name.casefold(), entry.name)
    if entry.language:
        label += f" ({entry.language})"
    if _source_kind(entry, record) == "sidecar":
        label += " (XMP sidecar)"
    return label


def _entry_display(entry: MetadataEntry | None) -> str:
    if entry is None:
        return "Not present"
    if entry.value in ("", None, [], {}):
        return "Explicitly empty"
    if isinstance(entry.value, list) and all(not isinstance(item, (dict, list)) for item in entry.value):
        return " · ".join(value_text(item) for item in entry.value)
    return value_text(entry.value)


def entry_provenance(entry: MetadataEntry | None, record: MetadataRecord) -> str:
    if entry is None:
        return "Not present"
    return "XMP sidecar" if _source_kind(entry, record) == "sidecar" else "Embedded image metadata"


def compare_records(reference: MetadataRecord, comparison: MetadataRecord, *,
                   include_technical: bool = False) -> list[ComparisonRow]:
    """Return aligned rows without flattening namespaces or provenance.

    Filesystem details and reader diagnostics are excluded unless technical
    metadata is requested. Entries match on qualified identity, group, ID,
    language and source role. Arrays and structures remain typed values.
    """
    def collect(record):
        buckets = {}
        entries = list(record.entries)
        if include_technical:
            if record.error:
                entries.append(MetadataEntry("Read error", ("ExifTool", "Diagnostics"),
                    "Error", record.error, record.path, "ExifTool:Diagnostics:Error"))
            if record.warnings:
                entries.append(MetadataEntry("Warnings", ("ExifTool", "Diagnostics"),
                    "Warning", list(record.warnings), record.path, "ExifTool:Diagnostics:Warning"))
        for entry in entries:
            if _is_technical(entry) and not include_technical:
                continue
            identity = _identity(entry, record)
            buckets.setdefault(identity, []).append(entry)
        return buckets

    left, right = collect(reference), collect(comparison)
    rows = []
    identity_groups = {}
    for owner, buckets in ((reference, left), (comparison, right)):
        for entries in buckets.values():
            for entry in entries:
                key = (entry.name.casefold(), (entry.language or "").casefold(), _source_kind(entry, owner))
                identity_groups.setdefault(key, set()).add((entry.qualified_name.casefold(),
                                                             tuple(g.casefold() for g in entry.groups),
                                                             str(entry.tag_id).casefold() if entry.tag_id is not None else None))
    identities = list(dict.fromkeys([*left.keys(), *right.keys()]))
    for identity in identities:
        left_entries = list(left.get(identity, ()))
        right_entries = list(right.get(identity, ()))
        # Repeated ExifTool entries are a multiset for comparison. Match equal
        # values first so an unstable return order cannot manufacture changes.
        right_by_value = {}
        for item in right_entries:
            right_by_value.setdefault(_canonical(item.value), []).append(item)
        pairs = []
        unmatched_left = []
        for item in left_entries:
            matches = right_by_value.get(_canonical(item.value))
            if matches:
                pairs.append((item, matches.pop(0)))
            else:
                unmatched_left.append(item)
        unmatched_right = [item for values in right_by_value.values() for item in values]
        unmatched_left.sort(key=lambda item: _canonical(item.value))
        unmatched_right.sort(key=lambda item: _canonical(item.value))
        while unmatched_left and unmatched_right:
            pairs.append((unmatched_left.pop(0), unmatched_right.pop(0)))
        pairs.extend((item, None) for item in unmatched_left)
        pairs.extend((None, item) for item in unmatched_right)
        for occurrence, (a, b) in enumerate(pairs):
            exemplar = a or b
            if exemplar is None:
                continue
            section = ("Technical metadata" if _is_technical(exemplar) else
                       _FIELD_SECTIONS.get(exemplar.name.casefold(), "Other metadata"))
            exemplar_record = reference if a else comparison
            label = _entry_label(exemplar, exemplar_record)
            disambiguator = (exemplar.name.casefold(), (exemplar.language or "").casefold(),
                             _source_kind(exemplar, exemplar_record))
            name_identities = identity_groups.get(disambiguator, set())
            if len(name_identities) > 1:
                groups = {item[1] for item in name_identities}
                ids = {item[2] for item in name_identities}
                qualified_names = {item[0] for item in name_identities}
                if len(groups) > 1:
                    label += f" · {exemplar.group}"
                if len(ids) > 1 and exemplar.tag_id is not None:
                    label += f" · ID {exemplar.tag_id}"
                if len(qualified_names) > 1 and len(groups) == 1 and len(ids) == 1:
                    label += f" · {exemplar.qualified_name}"
            if occurrence:
                label += f" (entry {occurrence + 1})"
            identity_text = exemplar.qualified_name
            if exemplar.tag_id is not None:
                identity_text += f" · ID {exemplar.tag_id}"
            if exemplar.language:
                identity_text += f" · language {exemplar.language}"
            if _source_kind(exemplar, reference if a else comparison) == "sidecar":
                identity_text += " · XMP sidecar"
            rows.append(ComparisonRow(section, label, identity_text, a, b, _state(a, b),
                                      _is_technical(exemplar)))
    return sorted(rows, key=lambda row: (SECTION_ORDER.index(row.section), row.label.casefold(), row.identity.casefold()))


def visible_rows(rows: list[ComparisonRow], mode: str) -> list[ComparisonRow]:
    """Apply the compare view's All fields or Differences only mode."""
    if mode == "Differences only":
        return [row for row in rows if row.state != "identical"]
    if mode == "Technical metadata":
        return [row for row in rows if row.technical]
    return list(rows)
