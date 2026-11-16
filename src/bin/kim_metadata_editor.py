#!/usr/bin/env python3
"""Standalone KIM6 metadata editor and read-only change planner.

Phase 1 deliberately has no metadata writer. It reads selected files through
the browser's read-only metadata service, keeps edits in memory, and produces
an inspectable plan only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import signal
import sys

try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QLocale, QSignalBlocker, QEvent, QItemSelectionModel
    from PySide6.QtGui import QImage, QPixmap, QIcon, QAction
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
        QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
        QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
        QScrollArea, QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem,
        QGroupBox, QToolButton, QFrame, QCheckBox, QAbstractItemView,
        QSizePolicy, QTabWidget, QTableView, QHeaderView, QProgressBar, QStyle,
    )
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        print("KIM6 Metadata Editor requires PySide6. Install the KIM6 Qt runtime and try again.", file=sys.stderr)
        raise SystemExit(2) from exc
    raise

from kim_metadata_reader import MetadataEntry, MetadataRecord, read_metadata, value_text, _source_path, _select_fields
from kim_photo_selection import read_thumbnail
from kim_process import inspection_context
from kim_metadata_sources import (
    MetadataSourcePreferences, MetadataRepresentation, TargetIdentity,
    SOURCE_PRIORITY_DEFAULT, metadata_representations, index_metadata_representations,
    ordered_representations, preferred_entry, preferred_representation, OverviewPreferences, overview_source,
)

from kim_metadata_browser import (MetadataWorker as InspectionWorker, PreviewWorker, InspectionCache,
    _file_stamp, _record_stamp, _record_bytes, TagModel, TagFilterWorker, OverviewFieldsDialog,
    MetadataBrowser, PinDelegate, MetadataDetailsDialog, metadata_alternatives, MetadataOverview, ListThumbnails)


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    aliases: tuple[str, ...]
    xmp: str
    iim: str | None
    iim_limit: int | None
    exif: str | None = None
    multiline: bool = False
    multiple: bool = False
    language_alt: bool = False


# Canonical six-field contract from §3.1. These names are intended targets;
# displaying them is not a claim that any write command has been qualified.
FIELD_SPECS = (
    FieldSpec("title", "Title", ("Title", "ObjectName"), "XMP-dc:Title", "IPTC:ObjectName", 64,
              language_alt=True),
    FieldSpec("caption", "Description", ("Description", "Caption-Abstract"),
              "XMP-dc:Description", "IPTC:Caption-Abstract", 2000, multiline=True, language_alt=True),
    FieldSpec("keywords", "Keywords", ("Subject", "Keywords"), "XMP-dc:Subject", "IPTC:Keywords", 64,
              multiline=True, multiple=True),
    FieldSpec("creator", "Creator", ("Creator", "By-line", "Artist"), "XMP-dc:Creator", "IPTC:By-line", 32,
              multiline=True, multiple=True),
    FieldSpec("copyright", "Copyright notice", ("Rights", "CopyrightNotice"),
              "XMP-dc:Rights", "IPTC:CopyrightNotice", 128, language_alt=True),
    FieldSpec("usage", "Usage terms", ("UsageTerms",),
              "XMP-xmpRights:UsageTerms", None, None, multiline=True, language_alt=True),
)


@dataclass
class Draft:
    operation: str = "Leave unchanged"
    value: str = ""
    target: TargetIdentity | None = None
    sync: bool = False
    create_counterpart: bool = False
    authorize_new_target: bool = False
    batch_preferred_source: bool = False


def _entry_value(entry: MetadataEntry) -> str:
    value = entry.value
    if isinstance(value, dict):
        if "x-default" in value:
            value = value["x-default"]
        elif len(value) == 1:
            value = next(iter(value.values()))
    if isinstance(value, list):
        return "\n".join(value_text(item) for item in value)
    return value_text(value)


def field_entries(record: MetadataRecord, spec: FieldSpec) -> list[MetadataEntry]:
    aliases = {name.casefold() for name in spec.aliases}
    return [entry for entry in record.entries if entry.name.casefold() in aliases]


def entry_source(record: MetadataRecord, entry: MetadataEntry) -> str:
    if Path(entry.source).resolve(strict=False) != Path(record.path).resolve(strict=False):
        return "XMP sidecar"
    if any(str(group).casefold().startswith("xmp") for group in entry.groups):
        return "XMP"
    if any(str(group).casefold().startswith("iptc") for group in entry.groups):
        return "IPTC-IIM"
    if any(str(group).casefold().startswith("exif") for group in entry.groups):
        return "EXIF"
    return entry.group


def comparable_entries(entries: list[MetadataEntry], spec: FieldSpec) -> list[MetadataEntry]:
    canonical = [entry for entry in entries if any(
        str(group).casefold().startswith(("xmp", "iptc")) for group in entry.groups)]
    if not spec.language_alt:
        return canonical
    defaults = [entry for entry in canonical if entry.language in (None, "x-default")]
    legacy = [entry for entry in canonical if any(
        str(group).casefold().startswith("iptc") for group in entry.groups)]
    return defaults + legacy


def field_state(record: MetadataRecord, spec: FieldSpec) -> tuple[str, str, str]:
    """Return status, readable values, and provenance without choosing a winner."""
    entries = field_entries(record, spec)
    if not entries:
        if record.error:
            return "Unreadable", record.error, ""
        return "Not present", "", ""
    comparison_entries = comparable_entries(entries, spec)
    values = [_entry_value(entry) for entry in comparison_entries]
    distinct = list(dict.fromkeys(values))
    if len(distinct) > 1:
        state = "Conflicting"
    elif not any(_entry_value(entry) for entry in entries):
        state = "Present but empty"
    else:
        state = "Present populated"
    lines = []
    sources = []
    for entry in entries:
        value = _entry_value(entry)
        source = entry_source(record, entry)
        sources.append(source)
        language = f" ({entry.language})" if entry.language and entry.language != "x-default" else ""
        lines.append(f"{source}{language}: {value if value else '(empty)'}")
    return state, "\n".join(lines), ", ".join(dict.fromkeys(sources))


def aggregate_field_state(paths: list[str], records: dict[str, MetadataRecord],
                          spec: FieldSpec) -> str:
    """Summarize a batch without collapsing absence, emptiness, or conflicts."""
    per_image = []
    value_keys = []
    for path in paths:
        record = records.get(str(Path(path).resolve(strict=False)))
        if record is None:
            per_image.append("Scanning")
            continue
        state, _shown, _sources = field_state(record, spec)
        if not record.error and detected_file_type(record) != "JPEG":
            state = "Unsupported"
        per_image.append(state)
        if state == "Present populated":
            entries = comparable_entries(field_entries(record, spec), spec) or field_entries(record, spec)
            value_keys.append(tuple(_entry_value(entry) for entry in entries))
    if not per_image or "Scanning" in per_image:
        return f"Scanning · {len(records)} of {len(paths)} images"
    counts = {}
    for state in per_image:
        counts[state] = counts.get(state, 0) + 1
    if len(counts) > 1:
        labels = {
            "Not present": "not present", "Present but empty": "empty",
            "Present populated": "populated", "Unreadable": "unreadable",
            "Conflicting": "conflicting", "Read-only · JPEG format not confirmed": "unsupported",
            "Unsupported": "unsupported",
        }
        detail = ", ".join(f"{count} {labels.get(state, state.casefold())}"
                            for state, count in counts.items())
        return f"Mixed ({detail})"
    state = per_image[0]
    if state == "Present populated" and len(set(value_keys)) > 1:
        return f"Mixed ({len(per_image)} populated with different values)"
    return state


def intended_targets(spec: FieldSpec) -> tuple[str, ...]:
    xmp = f"embedded {spec.xmp}"
    if spec.language_alt:
        xmp += " (x-default)"
    if spec.iim:
        return (xmp, f"embedded {spec.iim}")
    return (xmp,)


def new_destination(path, spec, priority=SOURCE_PRIORITY_DEFAULT):
    """Choose a qualified embedded destination without creating it."""
    candidates = [source for source in priority
                  if source in ("Embedded XMP", "IPTC-IIM") and
                  (source == "Embedded XMP" or spec.iim)]
    source = candidates[0] if candidates else "Embedded XMP"
    qualified = spec.xmp if source == "Embedded XMP" else spec.iim
    language = "x-default" if source == "Embedded XMP" and spec.language_alt else None
    return TargetIdentity(source, str(Path(path).resolve(strict=False)), qualified,
                          language, (), True)


def detected_file_type(record: MetadataRecord) -> str | None:
    source_path = Path(record.path).resolve(strict=False)
    entries = [entry for entry in record.entries
               if entry.name.casefold() == "filetype" and "File" in entry.groups and
               Path(entry.source).resolve(strict=False) == source_path]
    values = {value_text(entry.value).strip().upper() for entry in entries}
    return next(iter(values)) if len(values) == 1 else None


def proposed_output(source: str | Path) -> Path:
    source = Path(source)
    base = source.with_name(f"{source.stem}-metadata{source.suffix}")
    candidate = base
    version = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}-metadata-{version}{source.suffix}")
        version += 1
    return candidate


def _plan_draft(path, spec, drafts, mode, batch_sessions):
    resolved = str(Path(path).resolve(strict=False))
    if mode == "Individual":
        return drafts.get(resolved, {}).get(spec.key, Draft()), ""
    if mode == "Batch":
        return drafts.get("__batch__", {}).get(spec.key, Draft()), ""
    individual = drafts.get(resolved, {}).get(spec.key, Draft())
    batch_values = [session.get("fields", {}).get(spec.key) for session in batch_sessions
                    if resolved in session.get("paths", ()) and
                    session.get("fields", {}).get(spec.key, Draft()).operation != "Leave unchanged"]
    individual_active = individual.operation != "Leave unchanged"
    if individual_active and batch_values:
        return Draft(), "This field has both an Individual change and a Batch change"
    if len(batch_values) > 1:
        return Draft(), "This field is included in more than one Batch change"
    if batch_values:
        return batch_values[0], ""
    return individual, ""


def _targeted_plan_row(path, record, spec, draft, priority):
    """Plan one explicitly pinned representation, optionally with a qualified pair."""
    target = draft.target
    source_entries = field_entries(record, spec)
    representations = metadata_representations(record, spec)
    exact = next((item for item in representations if item.target.key == target.key), None)
    before = exact.value if exact else "Not present"
    if isinstance(before, list):
        before = "\n".join(value_text(item) for item in before)
    elif isinstance(before, dict):
        before = "\n".join(f"{language}: {value_text(value)}" for language, value in before.items())
    if before in (None, ""):
        before = "Present but empty" if exact else "Not present"
    target_names = [f"{target.source}: {target.qualified_tag}" +
                    (f" ({target.language})" if target.language else "")]
    untouched = [f"{item.source}: {item.qualified_tag}" +
                 (f" ({item.language})" if item.language else "")
                 for item in representations if item.target.key != target.key]
    issue = ""
    destinations = [target]
    if target.is_new and not draft.authorize_new_target:
        issue = f"New destination {target.source}: {target.qualified_tag} requires explicit authorization"
    if not target.is_new and exact is None and draft.operation not in ('Clear', 'Remove keywords'):
        issue = 'The selected source representation is no longer present. Choose and authorize a new target in Sources & targets.'
    if target.source == "EXIF":
        issue = "EXIF is available for inspection but has no approved editable mapping for this field"
    if draft.sync:
        if target.source not in ("Embedded XMP", "IPTC-IIM"):
            issue = "Sync IPTC and XMP applies only to embedded XMP and IPTC-IIM"
        elif spec.iim is None:
            issue = "This field has no supported IPTC-IIM counterpart"
        elif spec.language_alt and target.language not in (None, "x-default"):
            issue = "A language alternative cannot be synchronized to a language-neutral IPTC value"
        else:
            counterpart_source = "IPTC-IIM" if target.source == "Embedded XMP" else "Embedded XMP"
            counterpart_tag = spec.iim if counterpart_source == "IPTC-IIM" else spec.xmp
            counterpart = next((item for item in representations
                                if item.source == counterpart_source and
                                item.canonical_target == counterpart_tag and
                                (not spec.language_alt or item.language in (target.language, None, "x-default"))), None)
            if counterpart is None:
                if draft.operation in ("Clear", "Remove keywords"):
                    # Removing from an absent counterpart does not create it.
                    pass
                elif not draft.create_counterpart:
                    issue = f"Creating the missing {counterpart_source} counterpart requires separate authorization"
                else:
                    destinations.append(TargetIdentity(
                        counterpart_source, str(Path(record.path).resolve(strict=False)),
                        counterpart_tag, target.language if counterpart_source == "Embedded XMP" else None,
                        (), True))
                    target_names.append(f"New {counterpart_source}: {counterpart_tag}")
            else:
                destinations.append(counterpart.target)
                target_names.append(f"{counterpart_source}: {counterpart.qualified_tag}" +
                                     (f" ({counterpart.language})" if counterpart.language else ""))
    if target.source == "XMP sidecar":
        issue = "A sidecar-capable save mode is unavailable in Phase 1"
    if exact and exact.ambiguous and draft.operation in ("Fill empty", "Add keywords", "Remove keywords"):
        issue = "This source contains multiple values; choose Replace or Clear deliberately"
    if record.error:
        issue = f"Read blocked: {record.error}"
    if draft.operation in ("Replace", "Replace keywords") and draft.value == "":
        issue = "A blank value does not clear metadata; choose Clear explicitly"
    planned_value = draft.value
    current_values = list(exact.value) if exact and isinstance(exact.value, list) else (
        [exact.value] if exact and exact.value not in (None, "") else [])
    requested_values = [value for value in draft.value.splitlines() if value]
    if draft.operation == "Add keywords":
        planned_value = "\n".join(current_values + [value for value in requested_values if value not in current_values])
    elif draft.operation == "Remove keywords":
        planned_value = "\n".join(value for value in current_values if value not in requested_values)
    elif draft.operation == "Replace keywords":
        planned_value = "\n".join(requested_values)
    if draft.operation == "Fill empty" and exact and not exact.is_empty:
        return {"image": Path(path).name, "path": path, "field": spec.label,
                "operation": "No change required", "status": "noop", "before": str(before),
                "after": "Unchanged", "warning": "", "sources": target.display,
                "targets": "; ".join(target_names), "sync": str(bool(draft.sync)),
                "untouched": "; ".join(untouched), "result": "No output planned"}
    if draft.operation == "Fill empty" and not draft.value:
        return {"image": Path(path).name, "path": path, "field": spec.label,
                "operation": "No change required", "status": "noop", "before": str(before),
                "after": "Unchanged", "warning": "", "sources": target.display,
                "targets": "; ".join(target_names), "sync": str(bool(draft.sync)),
                "untouched": "; ".join(untouched), "result": "No output planned"}
    if draft.operation == "Clear" and not exact:
        return {"image": Path(path).name, "path": path, "field": spec.label,
                "operation": "No change required", "status": "noop", "before": str(before),
                "after": "Unchanged", "warning": "", "sources": target.display,
                "targets": "; ".join(target_names), "sync": str(bool(draft.sync)),
                "untouched": "; ".join(untouched), "result": "No output planned"}
    if draft.operation in ("Add keywords", "Remove keywords") and spec.key != "keywords":
        issue = "Keyword operations are available only for Keywords"
    expected = planned_value.splitlines() if spec.multiple else draft.value
    all_destinations_same = bool(destinations) and all(
        next((item.value for item in representations
              if item.source == destination.source and
              item.canonical_target == destination.qualified_tag and
              item.language == destination.language), None) == expected
        for destination in destinations if not destination.is_new)
    if draft.operation in ("Replace", "Replace keywords", "Add keywords", "Remove keywords") and exact and all_destinations_same and not any(item.is_new for item in destinations):
        return {"image": Path(path).name, "path": path, "field": spec.label,
                "operation": "No change required", "status": "noop", "before": str(before),
                "after": "Unchanged", "warning": "", "sources": target.display,
                "targets": "; ".join(target_names), "sync": str(bool(draft.sync)),
                "untouched": "; ".join(untouched), "result": "No output planned"}
    for destination in destinations:
        if destination.source == "IPTC-IIM" and spec.iim_limit and draft.operation != "Clear":
            values = [v for v in planned_value.splitlines() if v] if spec.multiple else [draft.value]
            if any(len(value.encode("utf-8")) > spec.iim_limit for value in values):
                issue = f"Legacy IPTC limit is {spec.iim_limit} UTF-8 bytes"
    operation = f"Blocked · {draft.operation}" if issue else draft.operation
    return {"image": Path(path).name, "path": path, "field": spec.label,
            "operation": operation, "status": "blocked" if issue else "valid",
            "before": str(before), "after": "(cleared)" if draft.operation == "Clear" else planned_value,
            "warning": issue, "sources": target.display, "targets": "; ".join(target_names),
            "sync": str(bool(draft.sync)), "untouched": "; ".join(untouched),
            "result": "No output planned" if issue else str(proposed_output(path))}


def build_plan(paths: list[str], records: dict[str, MetadataRecord],
               drafts: dict[str, dict[str, Draft]], mode: str,
               batch_sessions=(), source_drafts=(), priority=SOURCE_PRIORITY_DEFAULT) -> list[dict[str, str]]:
    """Build a view-only plan. No filesystem destination is opened or created."""
    plan = []
    for path in paths:
        resolved = str(Path(path).resolve(strict=False))
        record = records.get(resolved, MetadataRecord(resolved, error="Metadata scan is incomplete."))
        if detected_file_type(record) != "JPEG":
            reason = (f"Could not read image: {record.error}" if record.error else
                      "JPEG format could not be confirmed from file contents")
            plan.append({"image": Path(path).name, "path": path, "field": "Image eligibility",
                         "operation": "Blocked", "status": "blocked", "before": "Not checked",
                         "after": reason, "warning": reason, "sources": "", "value": f"Current: Not checked\nPlanned: {reason}",
                         "targets": "Not applicable", "result": "No output planned"})
            continue
        out = str(proposed_output(path))
        for spec in FIELD_SPECS:
            draft, draft_conflict = _plan_draft(path, spec, drafts, mode, batch_sessions)
            if draft.operation != "Leave unchanged" and mode == "Combined" and draft.target is None:
                batch_session = next((session for session in batch_sessions
                                      if resolved in session.get("paths", ()) and
                                      session.get("fields", {}).get(spec.key) is draft), None)
                pinned_targets = batch_session.get("targets", {}).get(spec.key, {}) if batch_session else {}
                source_policy = draft.batch_preferred_source
                if not source_policy:
                    plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                                 "operation": f"Blocked · {draft.operation}", "status": "blocked",
                                 "before": _field_summary(record, spec)[1],
                                 "after": "Select the preferred-source target policy in Batch edit",
                                 "warning": "Batch target is ambiguous until a source policy is selected",
                                 "sources": "", "targets": "No target selected", "result": "No output planned"})
                    continue
                if resolved in pinned_targets and pinned_targets[resolved] is None:
                    plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                                 "operation": f"Blocked · {draft.operation}", "status": "blocked",
                                 "before": _field_summary(record, spec)[1],
                                 "after": "Choose a specific source for this image",
                                 "warning": "Preferred source is ambiguous for this image",
                                 "sources": "", "targets": "Ambiguous source", "result": "No output planned"})
                    continue
                pinned = pinned_targets.get(resolved)
                if pinned:
                    draft = Draft(draft.operation, draft.value, pinned, draft.sync,
                                  draft.create_counterpart, draft.authorize_new_target,
                                  draft.batch_preferred_source)
                else:
                    preferred, available = preferred_representation(record, spec, priority, QLocale().name())
                    if preferred:
                        draft = Draft(draft.operation, draft.value, preferred.target, draft.sync,
                                      draft.create_counterpart, draft.authorize_new_target,
                                      draft.batch_preferred_source)
                    elif available:
                        plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                                     "operation": f"Blocked · {draft.operation}", "status": "blocked",
                                     "before": _field_summary(record, spec)[1],
                                     "after": "Choose a specific source for this image",
                                     "warning": "Preferred source is ambiguous for this image",
                                     "sources": "", "targets": "Ambiguous source", "result": "No output planned"})
                        continue
                    else:
                        draft = Draft(draft.operation, draft.value, new_destination(resolved, spec, priority), draft.sync,
                                      draft.create_counterpart, draft.authorize_new_target,
                                      draft.batch_preferred_source)
            targeted = []
            if draft.target is not None and draft.operation != "Leave unchanged":
                targeted.append(draft)
            targeted.extend(item for item_path, field_key, item in source_drafts
                            if str(Path(item_path).resolve(strict=False)) == resolved and
                            field_key == spec.key and item.operation != "Leave unchanged")
            if targeted:
                target_keys = [item.target.key for item in targeted]
                if len(set(target_keys)) != len(target_keys):
                    for item in targeted:
                        row = _targeted_plan_row(path, record, spec, item, priority)
                        row.update(status="blocked", operation=f"Blocked · {item.operation}",
                                   warning="More than one pending draft targets this representation",
                                   result="No output planned")
                        plan.append(row)
                else:
                    plan.extend(_targeted_plan_row(path, record, spec, item, priority) for item in targeted)
                continue
            state, existing, _sources = field_state(record, spec)
            display_before = existing if state == "Conflicting" else _field_summary(record, spec)[1]
            entries = field_entries(record, spec)
            targets = comparable_entries(entries, spec)
            issue = ""
            no_change = False
            if draft_conflict:
                plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                             "operation": "Blocked · Resolve overlapping drafts", "status": "blocked",
                             "before": display_before or "Not present", "after": draft_conflict,
                             "warning": draft_conflict, "sources": _sources,
                             "value": f"Current: {display_before or '(not present)'}\nPlanned: {draft_conflict}",
                             "targets": ", ".join(intended_targets(spec)), "result": "No output planned"})
                continue
            if draft.operation == "Leave unchanged":
                plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                             "operation": "Leave unchanged", "status": "unchanged",
                             "before": display_before or "Not present", "after": "Unchanged", "warning": "",
                             "sources": _sources,
                             "value": f"Current: {display_before or '(not present)'}\nNo change proposed",
                             "targets": ", ".join(intended_targets(spec)), "result": "No output planned"})
                continue
            if record.error:
                issue = f"Read blocked: {record.error}"
            elif state == "Conflicting":
                resolves_conflict = (draft.operation == "Clear" or
                                     (draft.operation in ("Replace", "Replace keywords") and bool(draft.value)))
                if not resolves_conflict:
                    issue = "Existing values conflict; choose Replace with a value or Clear to resolve explicitly"
            elif draft.operation in ("Replace", "Replace keywords") and draft.value == "":
                issue = "A blank value does not clear metadata; enter a value or choose Clear"
            elif draft.operation == "Fill empty" and state == "Present populated":
                no_change = True
            elif draft.operation == "Fill empty" and not (
                    [value for value in draft.value.splitlines() if value] if spec.multiple else draft.value):
                no_change = True
            elif draft.operation == "Fill empty" and state not in ("Not present", "Present but empty"):
                issue = f"Fill empty does not apply to {state.casefold()} values"
            elif draft.operation in ("Add keywords", "Remove keywords", "Replace keywords") and spec.key != "keywords":
                issue = "Keyword operations are available only for Keywords"
            elif draft.operation == "Replace" and targets and all(_entry_value(entry) == draft.value for entry in targets):
                no_change = True
            elif draft.operation == "Replace keywords" and targets:
                requested = [value for value in draft.value.splitlines() if value]
                if all(_entry_value(entry).splitlines() == requested for entry in targets):
                    no_change = True
            elif draft.operation == "Clear" and not targets:
                no_change = True
            elif draft.operation in ("Add keywords", "Remove keywords") and spec.key == "keywords":
                before = _entry_value(entries[0]).splitlines() if entries else []
                requested = [value for value in draft.value.splitlines() if value]
                if draft.operation == "Add keywords" and all(value in before for value in requested):
                    no_change = True
                elif draft.operation == "Remove keywords" and not any(value in before for value in requested):
                    no_change = True
            if spec.iim_limit is not None and draft.operation != "Clear" and not no_change:
                values = [v for v in draft.value.splitlines() if v] if spec.multiple else [draft.value]
                oversized = [len(v.encode("utf-8")) for v in values if len(v.encode("utf-8")) > spec.iim_limit]
                if oversized:
                    issue = f"Legacy IPTC limit is {spec.iim_limit} UTF-8 bytes"
            if no_change and not issue:
                plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                             "operation": "No change required", "status": "noop",
                             "before": display_before or "Not present", "after": "Unchanged", "warning": "",
                             "sources": _sources,
                             "value": f"Current: {display_before or '(not present)'}\nThe selected operation does not change this image",
                             "targets": ", ".join(intended_targets(spec)), "result": "No output planned"})
                continue
            operation = f"Blocked · {draft.operation}" if issue else draft.operation
            planned = issue or ("(cleared)" if draft.operation == "Clear" else draft.value)
            value = f"Current: {display_before or '(not present)'}\nPlanned: {planned}"
            plan.append({"image": Path(path).name, "path": path, "field": spec.label,
                         "operation": operation, "status": "blocked" if issue else "valid",
                         "before": display_before or "Not present", "after": planned, "warning": issue,
                         "sources": _sources,
                         "value": value, "targets": ", ".join(intended_targets(spec)),
                         "result": "No output planned" if issue else out})
    return plan


EDITOR_FIELDS = tuple(dict.fromkeys(['FileType', 'ImageWidth', 'ImageHeight'] +
                                       [alias for spec in FIELD_SPECS for alias in spec.aliases]))


class MetadataWorker(InspectionWorker):
    prepared = Signal(object, object, object)

    def __init__(self, paths, parent=None, fields=EDITOR_FIELDS):
        super().__init__(paths, parent, fields=fields)
        self.cached_record = None
        self.scope = "edit"
        self.previous_overview = None
        self.previous_stamp = None
        self.previous_coverage = frozenset()
        self.overview_coverage = frozenset()
        self.overview_selectors = ()
        self.completed.connect(self._prepare_records, Qt.DirectConnection)

    def _prepare_records(self, records, previews, error):
        # Run on the extraction thread; even one pinned structure can be large.
        if self.scope == "overview" and self.previous_overview is not None:
            previous = self.previous_overview
            selection = _select_fields(self.fields)
            editing = _select_fields(EDITOR_FIELDS)
            overview = _select_fields(self.overview_selectors)
            for path, record in tuple(records.items()):
                if record.error or previous.error:
                    self.overview_coverage = frozenset(self.fields)
                    continue
                if self.previous_stamp != self.stamps.get(path):
                    # The extraction is newer than its base. Retry from a fresh
                    # snapshot instead of labeling mixed versions as current.
                    return
                entries = []
                for index, entry in enumerate(previous.entries):
                    if index % 256 == 0 and self.isInterruptionRequested():
                        return
                    if not selection.includes(entry) and (editing.includes(entry) or overview.includes(entry)):
                        entries.append(entry)
                merged = MetadataRecord(path, entries + record.entries, record.sidecars, None,
                                        list(dict.fromkeys(previous.warnings + record.warnings)))
                records[path] = merged
                self.weights[path] = _record_bytes(merged)
                retained = frozenset(EDITOR_FIELDS) | frozenset(self.overview_selectors)
                self.overview_coverage = (self.previous_coverage & retained) | frozenset(self.fields)
        if not self.isInterruptionRequested():
            self.prepared.emit(records, previews, error)

    def run(self):
        if self.cached_record is None:
            return super().run()
        full = self.cached_record
        selection = _select_fields(self.fields)
        entries = []
        for index, entry in enumerate(full.entries):
            if index % 256 == 0 and self.isInterruptionRequested():
                return
            if selection.includes(entry):
                entries.append(entry)
        record = MetadataRecord(full.path, entries, full.sidecars, full.error, full.warnings)
        self.stamps[full.path] = self.cached_stamp
        self.weights[full.path] = _record_bytes(record)
        if not self.isInterruptionRequested():
            self.completed.emit({full.path: record}, {}, None)


class PreviewImages(InspectionCache):
    """Preserve Editor's image mapping while sharing validated preview caching."""
    def __init__(self):
        super().__init__(16, 16 * 1024 * 1024, preview=True)

    def __getitem__(self, key):
        return super().__getitem__(key)[0]

    def __setitem__(self, key, image):
        self.store(key, (image, ''), _file_stamp(key), image.sizeInBytes())


class FieldDetailsDialog(QDialog):
    def __init__(self, title, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} details")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        label = QLabel("Values by source. Different representations are shown separately.")
        label.setWordWrap(True)
        layout.addWidget(label)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(details or "No metadata values are present.")
        layout.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MetadataSettingsDialog(QDialog):
    """Isolated Settings → Metadata surface for future main-settings integration."""
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences = preferences
        self.setWindowTitle("Metadata settings")
        self.resize(500, 430)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Metadata reading priority"))
        layout.addWidget(QLabel("The first available supported source is shown when editing an image."))
        self.sources = QListWidget()
        self.sources.setAccessibleName("Metadata reading priority")
        self.sources.addItems(preferences.priority)
        layout.addWidget(self.sources, 1)
        controls = QHBoxLayout()
        self.up = QPushButton("Move up")
        self.down = QPushButton("Move down")
        self.reset = QPushButton("Restore defaults")
        controls.addWidget(self.up)
        controls.addWidget(self.down)
        controls.addWidget(self.reset)
        layout.addLayout(controls)
        self.sync_default = QCheckBox("Sync IPTC and XMP by default")
        self.sync_default.setChecked(preferences.sync_default)
        layout.addWidget(self.sync_default)
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.reset.clicked.connect(self._reset)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _move(self, delta):
        row = self.sources.currentRow()
        target = row + delta
        if not 0 <= row < self.sources.count() or not 0 <= target < self.sources.count():
            return
        item = self.sources.takeItem(row)
        self.sources.insertItem(target, item)
        self.sources.setCurrentRow(target)

    def _reset(self):
        self.sources.clear()
        self.sources.addItems(SOURCE_PRIORITY_DEFAULT)
        self.sync_default.setChecked(False)

    def _save(self):
        priority = [self.sources.item(index).text() for index in range(self.sources.count())]
        self.preferences.save(priority, self.sync_default.isChecked())
        self.accept()


class SourceChooserDialog(QDialog):
    def __init__(self, spec, representations, active_target, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Other metadata sources for {spec.label}")
        self.resize(720, 430)
        self.selected = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the representation to edit. Other values remain unchanged."))
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        for representation in representations:
            value = representation.value
            if isinstance(value, list):
                value = "\n".join(value_text(item) for item in value)
            elif isinstance(value, dict):
                value = "\n".join(f"{language}: {item}" for language, item in value.items())
            text = "(present but empty)" if value in (None, "", [], {}) else value_text(value)
            provenance = "Embedded image" if representation.source_path == str(Path(parent._active_path()).resolve(strict=False)) else Path(representation.source_path).name
            language = f" · {representation.language}" if representation.language else ""
            read_only = " · read only" if not representation.editable else ""
            item = QListWidgetItem(f"{representation.source}{language}{read_only} · {provenance}\n{text}")
            item.setData(Qt.UserRole, representation)
            item.setToolTip(f"{representation.qualified_tag}\n{representation.source_path}")
            self.list.addItem(item)
            if representation.target.key == getattr(active_target, "key", None):
                self.list.setCurrentItem(item)
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        choose = buttons.addButton("Edit this source", QDialogButtonBox.AcceptRole)
        self.choose_button = choose
        self.list.currentItemChanged.connect(self._update_choice)
        self._update_choice(self.list.currentItem(), None)
        choose.clicked.connect(self._choose)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose(self):
        item = self.list.currentItem()
        if item:
            self.selected = item.data(Qt.UserRole)
            self.accept()

    def _update_choice(self, item, _previous):
        self.choose_button.setEnabled(bool(item and item.data(Qt.UserRole).editable))


def _metadata_value(record, names):
    wanted = {name.casefold() for name in names}
    values = []
    for entry in record.entries:
        if entry.name.casefold() in wanted:
            text = value_text(entry.value)
            if text and text not in values:
                values.append(text)
    return " · ".join(values)


def _user_state(state):
    return {
        "Present populated": "Present",
        "Present but empty": "Present but empty",
        "Not present": "Not present",
        "Unreadable": "Could not read",
        "Conflicting": "Conflicting metadata values",
    }.get(state, state)


def _field_summary(record, spec):
    state, _details, _sources = field_state(record, spec)
    if state == "Conflicting":
        return state, "Conflicting metadata values"
    if state == "Unreadable":
        return state, "Could not read this image"
    if state != "Present populated":
        return state, _user_state(state)
    entries = field_entries(record, spec)
    primary = comparable_entries(entries, spec) or entries
    values = list(dict.fromkeys(_entry_value(entry) for entry in primary if _entry_value(entry)))
    if not values:
        return "Present but empty", "Present but empty"
    language_entries = [entry for entry in entries if entry.language and entry.language != "x-default"]
    suffix = f" (+{len(language_entries)} translations)" if language_entries else ""
    return state, values[0] + suffix


def field_input_value(record, spec):
    """Choose the canonical editable value only when the logical field is not conflicted."""
    state, _details, _sources = field_state(record, spec)
    if state == "Conflicting":
        return ""
    entries = comparable_entries(field_entries(record, spec), spec)
    if not entries:
        entries = field_entries(record, spec)
    if not entries:
        return ""
    entries = sorted(entries, key=lambda entry: (
        0 if "xmp" in " ".join(str(g).casefold() for g in entry.groups) else
        1 if "iptc" in " ".join(str(g).casefold() for g in entry.groups) else 2,
        0 if entry.language in (None, "x-default") else 1))
    return _entry_value(entries[0])


def candidate_conflict_entries(record, spec):
    entries = comparable_entries(field_entries(record, spec), spec)
    if not entries:
        entries = field_entries(record, spec)
    return entries


def has_clear_target(record, spec):
    return bool(comparable_entries(field_entries(record, spec), spec))


def _state_values(paths, records, spec):
    result = []
    for path in paths:
        record = records.get(str(Path(path).resolve(strict=False)))
        name = Path(path).name
        if record is None:
            result.append((name, "Scanning", "", "Scanning"))
            continue
        state, details, _sources = field_state(record, spec)
        if record.error:
            state = "Unreadable"
        elif detected_file_type(record) != "JPEG":
            state = "Unsupported"
        summary_state, summary_value = _field_summary(record, spec)
        logical = (summary_state, summary_value if summary_state == "Present populated" else state)
        result.append((name, _user_state(state), details or "(not present)", logical))
    return result


class ReviewDialog(QDialog):
    """Read-only, image-grouped review with a vertical value detail pane."""
    def __init__(self, plan, parent=None, selected_count=None):
        super().__init__(parent)
        self.plan = list(plan)
        self.has_proposals = any(row.get("status") in ("valid", "blocked") for row in self.plan)
        if not self.has_proposals:
            return
        self.setWindowTitle("Review changes")
        self.resize(1080, 700)
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)

        selected = selected_count if selected_count is not None else len({row.get("path", row["image"]) for row in plan})
        valid_rows = [row for row in plan if row.get("status") == "valid"]
        valid_images = {row.get("path", row["image"]) for row in valid_rows}
        blocked_rows = [row for row in plan if row.get("status") == "blocked"]
        blocked_images = {row.get("path", row["image"]) for row in blocked_rows}
        noop_count = sum(row.get("status") == "noop" for row in plan)
        selected_label = "image" if selected == 1 else "images"
        valid_label = "image will" if len(valid_images) == 1 else "images will"
        field_label = "field" if len(valid_rows) == 1 else "fields"
        blocked_label = "image" if len(blocked_images) == 1 else "images"
        blocked_operation_label = "operation" if len(blocked_rows) == 1 else "operations"
        noop_label = "operation" if noop_count == 1 else "operations"
        self.summary = QLabel(
            "Planning only. Metadata will not be written.\n"
            f"{selected} selected {selected_label} | {len(valid_images)} {valid_label} change | "
            f"{len(valid_rows)} {field_label} changing | {len(blocked_images)} blocked {blocked_label} "
            f"({len(blocked_rows)} blocked {blocked_operation_label}) | {noop_count} no-op {noop_label}")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("padding: 8px; border: 1px solid palette(mid); border-radius: 4px;")
        layout.addWidget(self.summary)
        self.copy_notice = QLabel("Read-only plan. No images, copies, or sidecars will be created.")
        layout.addWidget(self.copy_notice)

        self.splitter = QSplitter(Qt.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setMinimumHeight(150)
        self.detail = QWidget()
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        self.detail_heading = QLabel("Select an image or field to inspect its plan.")
        self.detail_heading.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.detail_heading.setMaximumHeight(30)
        detail_layout.addWidget(self.detail_heading)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: palette(link); padding: 3px;")
        self.warning_label.setMaximumHeight(44)
        detail_layout.addWidget(self.warning_label)
        value_columns = QHBoxLayout()
        self.before_view = self._value_view()
        self.after_view = self._value_view()
        before_panel = self._value_panel("Before", self.before_view)
        after_panel = self._value_panel("After", self.after_view)
        before_panel.setMaximumHeight(160)
        after_panel.setMaximumHeight(160)
        value_columns.addWidget(before_panel, 1)
        value_columns.addWidget(after_panel, 1)
        detail_layout.addLayout(value_columns)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        detail_layout.addWidget(self.result_label)
        self.source_label = QLabel()
        self.source_label.setWordWrap(True)
        detail_layout.addWidget(self.source_label)
        self.technical_button = QToolButton()
        self.technical_button.setText("Show file path and metadata targets")
        self.technical_button.setCheckable(True)
        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setMaximumHeight(150)
        self.technical.hide()
        self.technical_button.toggled.connect(self.technical.setVisible)
        detail_layout.addWidget(self.technical_button)
        detail_layout.addWidget(self.technical)
        detail_layout.addStretch(1)
        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)

        self.items = []
        rows_by_image = {}
        for row in plan:
            key = row.get("path", row["image"])
            rows_by_image.setdefault(key, []).append(row)
        for key, rows in rows_by_image.items():
            statuses = {row.get("status") for row in rows}
            if "blocked" in statuses:
                image_status = "Blocked"
            elif "valid" in statuses:
                image_status = "Valid changes"
            elif "noop" in statuses:
                image_status = "No change required"
            else:
                image_status = "Unchanged"
            first = rows[0]
            root_text = f"{first['image']} · {image_status}"
            parent_item = QTreeWidgetItem([root_text])
            parent_item.setData(0, Qt.UserRole, {"image": first["image"], "path": first.get("path", ""),
                                                 "status": image_status})
            self.tree.addTopLevelItem(parent_item)
            for row in rows:
                child = QTreeWidgetItem([f"{row['field']} · {row['operation']}"])
                child.setData(0, Qt.UserRole, row)
                parent_item.addChild(child)
                self.items.append(child)
        if len(rows_by_image) == 1:
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
        self.tree.currentItemChanged.connect(self._show_item)
        if self.items:
            first_image = self.tree.topLevelItem(0)
            first_image.setExpanded(True)
            first_change = next((self.items[index] for index, row in enumerate(plan)
                                 if row.get("status") in ("valid", "blocked", "noop")),
                                first_image.child(0))
            self.tree.setCurrentItem(first_change)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).setDefault(True)
        layout.addWidget(buttons)

    def exec(self):
        if not self.has_proposals:
            return QDialog.DialogCode.Rejected
        return super().exec()

    def open(self):
        if self.has_proposals:
            super().open()

    def show(self):
        if self.has_proposals:
            super().show()

    @staticmethod
    def _value_view():
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setMinimumHeight(70)
        view.setMaximumHeight(110)
        return view

    @staticmethod
    def _value_panel(title, view):
        panel = QGroupBox(title)
        box = QVBoxLayout(panel)
        box.addWidget(view)
        return panel

    def _show_item(self, item, _previous=None):
        if item is None:
            return
        row = item.data(0, Qt.UserRole)
        if not isinstance(row, dict) or "field" not in row:
            image_name = row.get("image", "Image") if isinstance(row, dict) else "Image"
            image_status = row.get("status", "") if isinstance(row, dict) else ""
            self.detail_heading.setText(f"{image_name} · {image_status}".strip(" ·"))
            siblings = [item.child(i).data(0, Qt.UserRole) for i in range(item.childCount())]
            blocked = [value for value in siblings if value.get("status") == "blocked"]
            valid = sum(value.get("status") == "valid" for value in siblings)
            noops = sum(value.get("status") == "noop" for value in siblings)
            unchanged = sum(value.get("status") == "unchanged" for value in siblings)
            self.warning_label.setText("This image has blocked operations. No output is planned."
                                       if blocked else "Expand the image to inspect its field details.")
            self.before_view.setPlainText("Current values are available under each field.")
            self.after_view.setPlainText(
                f"{valid} valid changes\n{noops} no-op operations\n{len(blocked)} blocked operations\n"
                f"{unchanged} unchanged fields")
            planned_results = [value.get("result", "") for value in siblings
                               if value.get("status") == "valid" and value.get("result")]
            self.result_label.setText(f"Planned result: {Path(planned_results[0]).name}" if planned_results
                                      else "No output planned")
            self.source_label.clear()
            self.technical.setPlainText(f"Full path: {row.get('path', '')}" if isinstance(row, dict) else "")
            return
        self.detail_heading.setText(f"{row['field']} · {row['operation']}")
        status = row.get("status", "unchanged")
        self.warning_label.setText(row.get("warning", "") or {
            "valid": "Valid proposed change. No file has been created.",
            "noop": "No change required. This operation will not create a copy.",
            "unchanged": "This field is unchanged.",
            "blocked": "This operation is blocked. No output is planned.",
        }.get(status, ""))
        self.before_view.setPlainText(row.get("before", ""))
        self.after_view.setPlainText(row.get("after", ""))
        self.source_label.setText(
            (f"Editing: {row.get('sources', 'Unselected source')}" if row.get("sources") else "") +
            (f" · Sync IPTC and XMP: {'On' if row.get('sync') == 'True' else 'Off'}"
             if "sync" in row else ""))
        result = row.get("result", "No output planned")
        self.result_label.setText(f"Planned result: {Path(result).name}" if row.get("status") == "valid"
                                  else "No output planned")
        technical = [f"Image: {row.get('image', '')}"]
        if row.get("path"):
            technical.append(f"Full path: {row['path']}")
        if row.get("targets"):
            technical.append(f"Metadata targets: {row['targets']}")
        if row.get("sources"):
            technical.append(f"Provenance: {row['sources']}")
        if row.get("untouched"):
            technical.append(f"Existing representations left unchanged: {row['untouched']}")
        if row.get("result"):
            technical.append(f"Planned result: {row['result']}")
        self.technical.setPlainText("\n".join(technical))



def _input_widget(spec, name):
    if spec.multiple or spec.multiline:
        widget = QPlainTextEdit()
        widget.setObjectName(name)
        widget.setPlaceholderText("One value per line" if spec.multiple else "Enter a value")
        widget.setMinimumHeight(50 if spec.multiple else 60)
        widget.setMaximumHeight(86 if spec.multiple else 100)
        return widget
    widget = QLineEdit()
    widget.setObjectName(name)
    return widget


def _editor_text(widget):
    return widget.toPlainText() if isinstance(widget, QPlainTextEdit) else widget.text()


def _set_editor_text(widget, value):
    widget.blockSignals(True)
    if isinstance(widget, QPlainTextEdit):
        widget.setPlainText(value)
    else:
        widget.setText(value)
    widget.blockSignals(False)


def _resized_splitter_sizes(saved, total, minimum_first, minimum_second):
    """Validate stored pane proportions and keep both panes visible."""
    if not isinstance(saved, (list, tuple)) or len(saved) != 2:
        return None
    try:
        first, second = (int(value) for value in saved)
    except (TypeError, ValueError, OverflowError):
        return None
    if first <= 0 or second <= 0 or total <= minimum_first + minimum_second:
        return None
    first_size = round(total * first / (first + second))
    first_size = max(minimum_first, min(first_size, total - minimum_second))
    second_size = total - first_size
    return [first_size, second_size]


def _batch_value_summary(paths, records, spec, priority=SOURCE_PRIORITY_DEFAULT):
    labels, signatures = [], []
    for path in paths:
        record = records.get(str(Path(path).resolve(strict=False)))
        if record is None:
            state, value = "Scanning", ""
        elif record.error:
            state, value = "Unreadable", record.error
        elif detected_file_type(record) != "JPEG":
            state, value = "Unsupported", "Not editable in Phase 1"
        else:
            preferred, _all = preferred_representation(record, spec, priority, QLocale().name())
            if preferred:
                value = preferred.value
                if isinstance(value, list):
                    value = "\n".join(value_text(item) for item in value)
                state, value = ("Present populated", value_text(value)) if value not in (None, "", [], {}) else ("Present but empty", "Present but empty")
            else:
                state, value = _field_summary(record, spec)
        signatures.append((state, value))
        labels.append((Path(path).name, state, value))
    if len(set(signatures)) > 1:
        return "Mixed values", labels
    return (signatures[0][1] if signatures else "No images selected"), labels


class BatchEditDialog(QDialog):
    """Separate batch drafting action. It never writes files."""
    def __init__(self, paths, records, existing=None, parent=None, priority=SOURCE_PRIORITY_DEFAULT,
                 sync_default=False):
        super().__init__(parent)
        self.paths = list(paths)
        self.records = records
        self.existing = existing or {}
        self.priority = priority
        self.sync_default = sync_default
        self.controls = {}
        self.setWindowTitle("Batch edit images")
        self.resize(820, 560)
        self.setMinimumSize(680, 480)
        layout = QVBoxLayout(self)

        heading = QLabel(f"Batch edit {len(self.paths)} images")
        heading.setStyleSheet("font-weight: bold; font-size: 15px;")
        layout.addWidget(heading)
        self.image_list = QListWidget()
        self.image_list.setMaximumHeight(72)
        for path in self.paths:
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(path)
            self.image_list.addItem(item)
        layout.addWidget(self.image_list)

        blocked = [path for path in self.paths
                   if (self.records.get(str(Path(path).resolve(strict=False))) is None
                       or self.records[str(Path(path).resolve(strict=False))].error
                       or detected_file_type(self.records[str(Path(path).resolve(strict=False))]) != "JPEG")]
        self.blocked_notice = QLabel()
        self.blocked_notice.setWordWrap(True)
        self.blocked_notice.setText(
            ((f"{len(blocked)} selected image will remain blocked in Review changes." if len(blocked) == 1 else
              f"{len(blocked)} selected images will remain blocked in Review changes.") if blocked else ""))
        self.blocked_notice.setVisible(bool(blocked))
        layout.addWidget(self.blocked_notice)
        self.target_policy = QCheckBox("Use each image’s preferred source and show every target in Review changes")
        self.target_policy.setObjectName("batch_preferred_source_policy")
        if self.existing:
            self.target_policy.setChecked(any(draft.batch_preferred_source
                                              for draft in self.existing.values()))
        layout.addWidget(self.target_policy)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        fields = QVBoxLayout(content)
        fields.setContentsMargins(2, 2, 2, 4)
        fields.setSpacing(5)
        for spec in FIELD_SPECS:
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            box = QVBoxLayout(card)
            box.setContentsMargins(8, 5, 8, 5)
            header = QHBoxLayout()
            label = QLabel(spec.label)
            label.setStyleSheet("font-weight: bold;")
            header.addWidget(label)
            summary, _values = _batch_value_summary(self.paths, records, spec, self.priority)
            state = QLabel(summary)
            state.setWordWrap(True)
            header.addWidget(state, 1)
            details = QPushButton("Details…")
            details.clicked.connect(lambda _checked=False, s=spec: self.show_values(s))
            header.addWidget(details)
            box.addLayout(header)

            controls = QWidget()
            control_layout = QVBoxLayout(controls)
            control_layout.setContentsMargins(0, 2, 0, 0)
            operation = QComboBox()
            operation.setObjectName(f"batch_operation_{spec.key}")
            operation.addItems(["Leave unchanged", "Fill empty", "Replace", "Clear"])
            edit = _input_widget(spec, f"batch_value_{spec.key}")
            sync = QCheckBox("Sync IPTC and XMP")
            sync.setChecked(False)
            sync.setEnabled(bool(spec.iim))
            counterpart = QCheckBox("Create missing counterparts")
            counterpart.hide()
            sync.toggled.connect(counterpart.setVisible)
            new_target = QCheckBox("Allow a new destination for images where this field is missing")
            byte_status = QLabel()
            byte_status.hide()
            clear_note = QLabel("Clear removes applicable values from every eligible image in this batch.")
            clear_note.setWordWrap(True)
            clear_note.hide()
            control_layout.addWidget(operation)
            control_layout.addWidget(edit)
            control_layout.addWidget(sync)
            control_layout.addWidget(counterpart)
            control_layout.addWidget(new_target)
            control_layout.addWidget(clear_note)
            control_layout.addWidget(byte_status)
            box.addWidget(controls)
            fields.addWidget(card)

            previous = self.existing.get(spec.key)
            if previous:
                if previous.operation not in [operation.itemText(i) for i in range(operation.count())]:
                    operation.addItem(previous.operation)
                operation.setCurrentText(previous.operation)
                _set_editor_text(edit, previous.value)
                sync.setChecked(previous.sync)
                counterpart.setChecked(previous.create_counterpart)
                new_target.setChecked(previous.authorize_new_target)
            def update_operation(value, edit=edit, clear_note=clear_note, sync=sync,
                                 counterpart=counterpart, new_target=new_target):
                active = value != "Leave unchanged"
                edit.setEnabled(active and value != "Clear")
                clear_note.setVisible(value == "Clear")
                for control in (sync, counterpart, new_target):
                    control.setVisible(active and (control is not counterpart or sync.isChecked()))
                self._update_batch_action()
            operation.currentTextChanged.connect(update_operation)
            edit.textChanged.connect(lambda *_args, s=spec, w=edit, label=byte_status:
                                     self.update_bytes(s, _editor_text(w), label))
            edit.textChanged.connect(self._update_batch_action)
            update_operation(operation.currentText())
            self.controls[spec.key] = {
                "spec": spec, "controls": controls,
                "operation": operation, "edit": edit, "byte_status": byte_status,
                "sync": sync, "counterpart": counterpart,
                "new_target": new_target,
            }
        fields.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        add = buttons.addButton("Add batch changes", QDialogButtonBox.AcceptRole)
        self.add_button = add
        add.setDefault(True)
        add.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        add.setIcon(QIcon.fromTheme("list-add", self.style().standardIcon(QStyle.SP_ArrowForward)))
        buttons.button(QDialogButtonBox.Cancel).setIcon(QIcon.fromTheme("dialog-cancel", self.style().standardIcon(QStyle.SP_DialogCancelButton)))
        layout.addWidget(buttons)
        self.scope_summary = QLabel()
        layout.addWidget(self.scope_summary)
        self.discard_requested = False
        if self.existing:
            discard = buttons.addButton("Discard batch changes", QDialogButtonBox.DestructiveRole)
            discard.setIcon(QIcon.fromTheme("edit-delete"))
            discard.clicked.connect(self.discard_changes)
        self._update_batch_action()

    def discard_changes(self):
        self.discard_requested = True
        QDialog.accept(self)

    def _update_batch_action(self):
        if not hasattr(self, "add_button"):
            return
        fields = self.selected_fields()
        self.add_button.setEnabled(bool(fields) and len(set(self.paths)) >= 2)
        self.scope_summary.setText(f"Selected images: {len(set(self.paths))} · Proposed fields: {len(fields)}")

    def accept(self):
        if not self.selected_fields() or len(set(self.paths)) < 2:
            return
        super().accept()

    def update_bytes(self, spec, value, label):
        if spec.iim_limit is None:
            label.hide()
            return
        values = [item for item in value.splitlines() if item] if spec.multiple else [value]
        count = max((len(item.encode("utf-8")) for item in values), default=0)
        if count >= int(spec.iim_limit * 0.8) or count > spec.iim_limit:
            label.setText(f"{count} of {spec.iim_limit} UTF-8 bytes"
                          f"{' per entry' if spec.multiple else ''}")
            label.show()
        else:
            label.hide()

    def show_values(self, spec):
        blocks = []
        for path in self.paths:
            record = self.records.get(str(Path(path).resolve(strict=False)))
            state, details, sources = field_state(record, spec) if record else ("Scanning", "", "")
            blocks.append(f"{Path(path).name} · {state}\n{details or '(not present)'}"
                          + (f"\nSources: {sources}" if sources else ""))
        FieldDetailsDialog(spec.label, "\n\n".join(blocks), self).exec()

    def selected_fields(self):
        result = {}
        for spec in FIELD_SPECS:
            control = self.controls[spec.key]
            operation = control["operation"].currentText()
            if operation == "Leave unchanged":
                continue
            value = "" if operation == "Clear" else _editor_text(control["edit"])
            result[spec.key] = Draft(operation, value, sync=control["sync"].isChecked(),
                                      create_counterpart=control["counterpart"].isChecked(),
                                      authorize_new_target=control["new_target"].isChecked(),
                                      batch_preferred_source=self.target_policy.isChecked())
        return result


class EditorImageList(QListWidget):
    """Native selection keeps its focus/anchor, independently of the edited image."""
    editingRowChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editing_row = -1
        self._selecting = False
        self.currentRowChanged.connect(self._current_changed)

    def set_editing_row(self, row):
        if row != self.editing_row:
            self.editing_row = row
            self.editingRowChanged.emit(row)

    def _current_changed(self, row):
        if not self._selecting:
            self.set_editing_row(row)

    def mousePressEvent(self, event):
        self._selecting = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        try:
            super().mousePressEvent(event)
            if not self._selecting and self.indexAt(event.position().toPoint()).isValid():
                self.set_editing_row(self.currentRow())
        finally:
            self._selecting = False

    def keyPressEvent(self, event):
        self._selecting = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        try:
            super().keyPressEvent(event)
            if not self._selecting:
                self.set_editing_row(self.currentRow())
        finally:
            self._selecting = False


class MetadataEditor(QMainWindow, ListThumbnails):
    HORIZONTAL_SPLITTER_KEY = "metadata/editorHorizontalSplitterSizes"
    IMAGE_SPLITTER_KEY = "metadata/editorImagePanelSplitterSizes"
    EDIT_TAB, OVERVIEW_TAB, ALL_TAB, ADVANCED_TAB = range(4)

    def __init__(self, paths, preferences=None):
        super().__init__()
        self.paths = list(dict.fromkeys(_source_path(Path(path).expanduser()) for path in paths))
        self.records = InspectionCache(32, 32 * 1024 * 1024)
        self._representation_indexes = {}
        self.previews = PreviewImages()
        self.thumbnails = InspectionCache(128, 4 * 1024 * 1024, preview=True)
        self.thumbnail_worker = None
        self._thumbnail_seen = {}
        self._thumbnail_cursor = 0
        self._icon_paths = set()
        self._path_rows = {path: row for row, path in enumerate(self.paths)}
        self.preferences = preferences or MetadataSourcePreferences()
        self.overview_preferences = OverviewPreferences(self.preferences.settings)
        self.full_records = InspectionCache(4, 64 * 1024 * 1024)
        self.overview_cache = InspectionCache(32, 16 * 1024 * 1024)
        self._overview_scopes = {}
        self._active_overview = None
        self._displayed_overview = None
        self.preview_workers = set()
        self._preview_failures = {}
        self._active_preview = None
        self._active_record = None
        self._active_full = None
        self._load_generation = 0
        self._closing = False
        self._all_requested = None
        self._inspection_record = None
        self._inspection_filter = None
        self._inspection_filter_pending = False
        self._planning_records = {}
        self._pending_action = None
        self._load_paths = []
        self.source_targets = {}
        self.source_drafts = []
        self.sync_overrides = {}
        self.creation_authorizations = {}
        self.counterpart_authorizations = {}
        self.drafts: dict[str, dict[str, Draft]] = {}
        self.batch_sessions = []
        self.worker = None
        self.close_after_worker = False
        self._refreshing = False
        self.setWindowTitle("KIM6 Metadata Editor")
        self.resize(1120, 780)
        self.setMinimumSize(760, 560)
        settings_menu = self.menuBar().addMenu("Settings")
        metadata_settings = settings_menu.addAction("Metadata…")
        metadata_settings.triggered.connect(self.open_metadata_settings)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 7, 10, 5)

        top = QHBoxLayout()
        self.image_heading = QLabel("Loading images…")
        self.image_heading.setStyleSheet("font-weight: bold; font-size: 15px;")
        top.addWidget(self.image_heading, 1)
        self.batch_button = QPushButton("Edit selected images…")
        self.batch_button.setEnabled(False)
        self.batch_button.clicked.connect(self.batch_edit_selected)
        top.addWidget(self.batch_button)
        layout.addLayout(top)

        self.splitter = QSplitter(Qt.Horizontal)
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(220)
        left = QVBoxLayout(self.left_panel)
        left.setContentsMargins(0, 0, 5, 0)
        self.image_splitter = QSplitter(Qt.Vertical)
        self.image_splitter.setObjectName("imagePreviewSplitter")
        self.image_splitter.setHandleWidth(7)
        self.image_splitter.setChildrenCollapsible(False)
        self.image_list_panel = QWidget()
        image_list_layout = QVBoxLayout(self.image_list_panel)
        image_list_layout.setContentsMargins(0, 0, 0, 0)
        image_list_layout.addWidget(QLabel("Images"))
        self.file_list = EditorImageList()
        self.image_list = self.file_list
        self.file_list.setIconSize(QSize(48, 36))
        self.file_list.setUniformItemSizes(True)
        self.file_list.verticalScrollBar().valueChanged.connect(lambda: self._pump_thumbnails())
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.editingRowChanged.connect(self._image_changed)
        self.file_list.itemSelectionChanged.connect(self._selection_changed)
        image_list_layout.addWidget(self.file_list, 1)
        selection_actions = QHBoxLayout()
        for text, callback in (("Select all", self.file_list.selectAll),
                               ("Clear selection", self.file_list.clearSelection)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            selection_actions.addWidget(button)
        image_list_layout.addLayout(selection_actions)
        self.selection_summary = QLabel()
        image_list_layout.addWidget(self.selection_summary)
        self.image_list_panel.setMinimumHeight(120)

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel("Image preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(40, 40)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("border: 1px solid palette(mid); border-radius: 4px;")
        preview_layout.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.previous_button.clicked.connect(lambda: self.navigate(-1))
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(lambda: self.navigate(1))
        nav.addWidget(self.previous_button)
        nav.addWidget(self.next_button)
        preview_layout.addLayout(nav)
        self.image_info = QLabel("Reading image information…")
        self.image_info.setWordWrap(True)
        preview_layout.addWidget(self.image_info)
        self.preview_panel.setMinimumHeight(155)
        self.image_splitter.addWidget(self.preview_panel)
        self.image_splitter.addWidget(self.image_list_panel)
        self.image_splitter.setStretchFactor(0, 3)
        self.image_splitter.setStretchFactor(1, 2)
        self.image_splitter.setSizes([360, 220])
        left.addWidget(self.image_splitter, 1)
        self.splitter.addWidget(self.left_panel)

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.NoFrame)
        self.form_scroll.setMinimumWidth(640)
        self.form_content = QWidget()
        self.fields_layout = QVBoxLayout(self.form_content)
        self.fields_layout.setContentsMargins(4, 1, 4, 4)
        self.fields_layout.setSpacing(5)
        self.field_controls = {}
        self.advanced_scroll = QScrollArea()
        self.advanced_scroll.setWidgetResizable(True)
        advanced = QWidget()
        self.advanced_layout = QVBoxLayout(advanced)
        self.sources_targets_help = QLabel("")
        self.sources_targets_help.setTextFormat(Qt.PlainText)
        self.sources_targets_help.setWordWrap(True)
        self.sources_targets_help.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.advanced_layout.addWidget(self.sources_targets_help)
        self.advanced_scroll.setWidget(advanced)
        self.loading_label = QLabel('Loading metadata…')
        self.loading_label.setTextFormat(Qt.PlainText)
        self.fields_layout.addWidget(self.loading_label)
        self.retry_metadata = QPushButton('Retry metadata')
        self.retry_metadata.setIcon(QIcon.fromTheme('view-refresh'))
        self.retry_metadata.clicked.connect(self._retry_metadata)
        self.retry_metadata.hide()
        self.fields_layout.addWidget(self.retry_metadata)
        self.target_notice = QLabel('Planning only. Your image files will not be changed.')
        self.target_notice.setWordWrap(True)
        self.fields_layout.addWidget(self.target_notice)
        pin_row = QHBoxLayout()
        pin_help = QLabel(
            "Pins control which fields appear in Browser and Editor."
        )
        pin_help.setTextFormat(Qt.PlainText)
        pin_help.setWordWrap(True)
        pin_row.addWidget(pin_help, 1)
        configure = QPushButton("Configure fields…")
        configure.setIcon(QIcon.fromTheme("configure"))
        configure.clicked.connect(self._configure_editor_pins)
        pin_row.addWidget(configure)

        self.view_gps_button = QPushButton('View on map…')
        self.view_gps_button.setIcon(QIcon.fromTheme('globe'))
        self.view_gps_button.setToolTip(
            'Inspect this image in the existing read-only GPS viewer. '
            'Pending metadata proposals are preserved.'
        )
        self.view_gps_button.clicked.connect(self.view_gps_on_map)
        pin_row.addWidget(self.view_gps_button)
        self.fields_layout.addLayout(pin_row)
        self._pin_signature = None
        self._readonly_pins = {}
        self._pin_order = []
        self._build_fields()
        self.advanced_layout.addStretch(1)
        self.fields_layout.addStretch(1)
        self._refresh_editor_pins()
        self.form_scroll.setWidget(self.form_content)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.form_scroll, 'Edit metadata')
        self.overview = MetadataOverview(self.preferences, self.overview_preferences, self)
        self.overview.view_gps_on_map = self.view_gps_on_map
        self.overview.configuration_changed.connect(self._reload_overview_preferences)
        self.overview.retry.connect(self._retry_overview)
        self.tabs.addTab(self.overview, 'Overview')
        self._build_all_fields()
        self.tabs.addTab(self.advanced_scroll, 'Sources && targets')
        self.tabs.currentChanged.connect(self._editor_tab_changed)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setHandleWidth(7)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([340, 760])
        layout.addWidget(self.splitter, 1)

        self.current_preview_path = None
        self.splitter.splitterMoved.connect(self._splitter_moved)
        self.image_splitter.splitterMoved.connect(self._splitter_moved)
        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(250)
        self._splitter_save_timer.timeout.connect(self._persist_splitter_sizes)

        footer = QHBoxLayout()
        self.pending_label = QLabel("Pending changes: 0")
        footer.addWidget(self.pending_label, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Cancel).setIcon(QIcon.fromTheme('dialog-cancel', self.style().standardIcon(QStyle.SP_DialogCancelButton)))
        self.review_button = self.buttons.addButton('Review changes', QDialogButtonBox.AcceptRole)
        self.review_button.setIcon(QIcon.fromTheme('go-next', self.style().standardIcon(QStyle.SP_ArrowForward)))
        self.review_button.setDefault(True)
        self.review_button.clicked.connect(self.review_changes)
        self.buttons.rejected.connect(self.close)
        footer.addWidget(self.buttons)
        layout.addLayout(footer)
        self.statusBar().showMessage("Read-only change planner. No metadata will be written.")

        if self.paths:
            for path in self.paths:
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.UserRole, path)
                item.setSizeHint(QSize(0, 40))
                item.setToolTip(path)
                self.file_list.addItem(item)
            self.file_list.setCurrentRow(0)
        else:
            self.image_heading.setText("No images selected")
            self.review_button.setEnabled(False)
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
        self._selection_changed()
        self._refresh_pending()
        QTimer.singleShot(0, self._restore_splitter_sizes)

    def _build_all_fields(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.all_status = QLabel('Open All fields to inspect complete metadata.')
        self.all_status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.all_status)
        controls = QHBoxLayout()
        self.all_search = QLineEdit()
        self.all_search.setPlaceholderText('Search all tag names, values, groups or identifiers')
        self.all_search.textChanged.connect(self._search_all_fields)
        controls.addWidget(self.all_search, 1)
        self.all_progress = QProgressBar()
        self.all_progress.setRange(0, 0)
        self.all_progress.setMaximumWidth(100)
        self.all_progress.hide()
        controls.addWidget(self.all_progress)
        self.all_cancel = QPushButton('Cancel loading')
        self.all_cancel.clicked.connect(self._cancel_all_fields)
        controls.addWidget(self.all_cancel)
        self.all_retry = QPushButton('Load all fields')
        self.all_retry.clicked.connect(lambda: self._editor_tab_changed(self.ALL_TAB))
        self.all_retry.hide()
        controls.addWidget(self.all_retry)
        layout.addLayout(controls)
        self.all_model = TagModel(False, self)
        self.all_table = QTableView()
        self.all_table.setModel(self.all_model)
        self.all_table.setWordWrap(False)
        self.all_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.all_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.all_table.verticalHeader().setDefaultSectionSize(26)
        self.all_table.verticalHeader().hide()
        self.all_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.all_table.selectionModel().currentChanged.connect(self._inspect_entry)
        layout.addWidget(self.all_table, 1)
        self.all_details = QPlainTextEdit()
        self.all_details.setReadOnly(True)
        self.all_details.setMaximumHeight(160)
        layout.addWidget(self.all_details)
        self.all_pin = QAction('Show in Browser overview', self)
        self.all_pin.setIcon(QIcon.fromTheme('list-add'))
        self.all_pin.setEnabled(False)
        self.all_pin.triggered.connect(self._pin_entry)
        self.all_model.pin_preferences = self.overview_preferences
        self.all_model.pin_destination = 'Browser overview'
        delegate = PinDelegate(self.all_table, self.overview_preferences, 'Browser overview')
        delegate.toggled.connect(lambda index: self._pin_entry(index.data(Qt.UserRole)))
        details = QPushButton('Details')
        details.setIcon(QIcon.fromTheme('dialog-information'))
        details.clicked.connect(lambda: MetadataDetailsDialog(metadata_alternatives(self._inspected_entry, self._inspection_record), self).exec()
                                if getattr(self, '_inspected_entry', None) else None)
        layout.addWidget(details, 0, Qt.AlignRight)
        configure = QPushButton('Configure overview fields…')
        configure.clicked.connect(lambda: OverviewFieldsDialog(self.overview_preferences, self).exec())
        layout.addWidget(configure, 0, Qt.AlignLeft)
        self.tabs.addTab(panel, 'All fields')

    def _inspect_entry(self, current, _previous=None):
        entry = current.data(Qt.UserRole) if current.isValid() else None
        self._inspected_entry = entry
        self.all_pin.setEnabled(entry is not None)
        text = (f'Structured value ({len(entry.value)} elements)' if isinstance(entry.value, (dict, list)) else value_text(entry.value)) if entry else ''
        if len(text) > 1000:
            text = text[:999] + '…'
        self.all_details.setPlainText((f'{entry.name}\nSource: {entry.source}\n{entry.group} · {entry.language or "No language qualification"}\n' + text) if entry else '')
        pinned = entry is not None and self.overview_preferences.is_pinned(entry, self._inspection_record)
        self.all_pin.setText('Remove from Browser overview' if pinned else 'Show in Browser overview')

    def _pin_entry(self, entry=None):
        entry = entry if isinstance(entry, MetadataEntry) else getattr(self, '_inspected_entry', None)
        if entry is not None and self._inspection_record is not None:
            try:
                self.overview_preferences.reload()
                pinned = self.overview_preferences.is_pinned(entry, self._inspection_record)
                self.overview_preferences.toggle_entry(entry, self._inspection_record)
                self._inspect_entry(self.all_table.currentIndex())
                self.all_table.viewport().update()
                self._update_overview()
                self._refresh_editor_pins()
                self._pump_load()
                self.statusBar().showMessage('Removed from Browser overview' if pinned else 'Added to Browser overview', 3500)
            except ValueError as exc:
                QMessageBox.warning(self, 'Cannot change overview fields', str(exc))

    def _editor_tab_changed(self, index):
        self._reload_overview_preferences()
        if index == self.ALL_TAB:
            current = self._full_record(self._active_path())
            if current is not None and current.error:
                self.full_records.pop(self._active_path(), None)
                self._active_full = None
            self._all_requested = self._active_path()
            if self.worker is not None and (self.worker.fields is not None or self.worker.paths != [self._active_path()]):
                self.worker.requestInterruption()
                self._load_generation += 1
            self._update_all_fields()
            if self._inspection_record is not None and self._inspection_filter is None:
                self._search_all_fields()
        else:
            self._all_requested = None
            if self._inspection_filter is not None:
                self._inspection_filter.requestInterruption()
                self._inspection_filter_pending = False
            if self.worker is not None and self.worker.fields is None:
                self.worker.requestInterruption()
                self._load_generation += 1
        self._pump_load()

    def _reload_overview_preferences(self):
        if self._closing:
            return
        self.overview_preferences.reload()
        previous_priority = tuple(self.preferences.priority)
        self.preferences.reload()
        if tuple(self.preferences.priority) != previous_priority:
            self._refresh_individual(self._active_path())
            self._refresh_pending()
        self._inspect_entry(self.all_table.currentIndex())
        self.all_table.viewport().update()
        self._update_overview()
        self._refresh_editor_pins()
        self._pump_load()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, 'all_table'):
            QTimer.singleShot(0, self._reload_overview_preferences)

    def _cancel_all_fields(self):
        self._all_requested = None
        if self.worker is not None and self.worker.fields is None:
            self.worker.requestInterruption()
            self._load_generation += 1
        self.all_status.setText('Complete metadata loading canceled.')
        self.all_progress.hide()
        self.all_cancel.hide()
        self.all_retry.show()

    def _overview_snapshot(self, path):
        record = self.overview_cache.get(path)
        if record is None and self._active_overview and self._active_overview[1].path == path:
            stamp, active = self._active_overview
            if stamp == _record_stamp(path, active.sidecars):
                record = active
        scope = self._overview_scopes.get(path)
        if record is not None and scope and scope[0] is record:
            return record, scope[1]
        record = self._record(path)
        return record, frozenset(EDITOR_FIELDS) if record is not None else frozenset()

    def _overview_missing(self, path):
        record, covered = self._overview_snapshot(path)
        if record is not None and record.error:
            return ()
        logical = set()
        qualified = set()
        for selector in covered:
            selection = _select_fields((selector,))
            logical.update(selection.logical_names)
            qualified.update(selection.qualified)
        missing = []
        for selector in self.overview_preferences.selectors:
            selection = _select_fields((selector,))
            if selection.logical_names:
                present = selection.logical_names <= logical
            else:
                languages = [field.language.casefold() for field in self.overview_preferences.fields
                             if field.selector.casefold() == selector.casefold() and field.language]
                present = all(parts in qualified or parts[-1] in logical or any(
                    parts[-1].endswith("-" + language) and
                    parts[-1][:-(len(language) + 1)] in logical for language in languages)
                    for parts in selection.qualified)
            if not present:
                missing.append(selector)
        return tuple(missing)

    def _store_overview(self, path, record, coverage, stamp, weight):
        self.overview_cache.store(path, record, stamp, weight)
        self._active_overview = (stamp, record)
        wanted = frozenset(EDITOR_FIELDS) | frozenset(self.overview_preferences.selectors)
        self._overview_scopes[path] = (record, frozenset(coverage) & wanted)
        keep = set(self.overview_cache) | {path}
        self._overview_scopes = {key: value for key, value in self._overview_scopes.items() if key in keep}

    def _update_overview(self):
        if self.tabs.currentIndex() != self.OVERVIEW_TAB:
            return
        path = self._active_path()
        record, _covered = self._overview_snapshot(path)
        if self._overview_missing(path):
            record = None
        key = (path, id(record), tuple(self.overview_preferences.fields), tuple(self.preferences.priority))
        if key != self._displayed_overview:
            self._displayed_overview = key
            self.overview.set_record(record)

    def _retry_overview(self):
        path = self._active_path()
        self.overview_cache.pop(path, None)
        self._overview_scopes.pop(path, None)
        self._active_overview = None
        if self._record(path) is not None and self._record(path).error:
            self._retry_metadata()
        self._displayed_overview = None
        self._update_overview()
        self._pump_load()

    def _full_record(self, path):
        record = self.full_records.get(path)
        if record is not None:
            return record
        if self._active_full and self._active_full[1].path == path:
            stamp, record = self._active_full
            if stamp == _record_stamp(path, record.sidecars):
                return record
        return None

    def _update_all_fields(self):
        if self.tabs.currentIndex() != self.ALL_TAB:
            return
        record = self._full_record(self._active_path())
        if record is None:
            if self._inspection_record is not None:
                self.all_model.set_record(None)
                self._inspection_record = None
            if self._all_requested:
                self.all_status.setText('Loading all metadata…')
                self.all_progress.show()
                self.all_cancel.show()
                self.all_retry.hide()
            return
        self.all_progress.hide()
        self.all_cancel.hide()
        self.all_retry.setVisible(bool(record.error))
        self.all_status.setText(record.error or f'{len(record.entries)} complete metadata entries')
        if record is not self._inspection_record:
            self._inspection_record = record
            self.all_model.set_record(record)
            self._search_all_fields()

    def _search_all_fields(self, *_args):
        if self._inspection_record is None:
            return
        if self._inspection_filter is not None:
            self._inspection_filter.requestInterruption()
            self._inspection_filter_pending = True
            return
        self._inspection_filter_pending = False
        if not self.all_search.text().strip():
            self.all_model.set_record(self._inspection_record)
            return
        worker = TagFilterWorker(self._inspection_record, self.all_search.text(), None, False, self)
        self._inspection_filter = worker
        worker.completed.connect(lambda record, rows: self._inspection_matches(worker, record, rows), Qt.QueuedConnection)
        worker.finished.connect(lambda: self._inspection_finished(worker), Qt.QueuedConnection)
        worker.start()

    def _inspection_matches(self, worker, record, rows):
        if not self._closing and self.tabs.currentIndex() == self.ALL_TAB and not worker.isInterruptionRequested() and record is self._inspection_record:
            self.all_model.set_record(record, rows)
            self.all_status.setText(f'{len(rows)} of {len(record.entries)} metadata entries')

    def _inspection_finished(self, worker):
        self._inspection_filter = None
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        elif self._inspection_filter_pending:
            self._search_all_fields()

    def _record(self, path):
        if path is None:
            return None
        record = self.records.get(path)
        if record is not None:
            return record
        if self._active_record and self._active_record[1].path == path:
            stamp, record = self._active_record
            if stamp == _record_stamp(path, record.sidecars):
                return record
        if path in self._planning_records:
            stamp, record = self._planning_records[path]
            if stamp == _record_stamp(path, record.sidecars):
                return record
            del self._planning_records[path]
        full = self._full_record(path)
        if full is not None:
            if full.error:
                return full
            selection = _select_fields(EDITOR_FIELDS)
            record = MetadataRecord(path, [entry for entry in full.entries if selection.includes(entry)],
                                    full.sidecars, full.error, full.warnings)
            stamp = _record_stamp(path, record.sidecars)
            weight = self.full_records._items[path][2] if path in self.full_records._items else self.records.budget + 1
            self.records.store(path, record, stamp, weight)
            self._active_record = (stamp, record)
            return record
        return None

    def _retry_metadata(self):
        path = self._active_path()
        self.records.pop(path, None)
        self._planning_records.pop(path, None)
        self._representation_indexes.pop(path, None)
        self._active_record = None
        full = self._full_record(path)
        if full is not None and full.error:
            self.full_records.pop(path, None)
            self._active_full = None
        self._load_generation += 1
        if self.worker is not None:
            self.worker.requestInterruption()
        self._image_changed(self.file_list.editing_row)

    def _preview_image(self, path):
        image = self.previews.get(path)
        if image is not None:
            return image
        if self._active_preview and self._active_preview[0] == path:
            _path, stamp, image = self._active_preview
            if stamp == _file_stamp(path):
                return image
        return None

    def _wanted_previews(self):
        return (self._active_path(),) if self._active_path() else ()

    def _preview_for(self, path):
        image = self._preview_image(path)
        return (image, "") if image is not None else None

    def _preview_failure(self, path):
        return self._preview_failures.get(path)

    def _ensure_preview(self):
        path = self._active_path()
        if self._closing or not path or self._preview_image(path) is not None or path in self._preview_failures:
            return
        if len(self.preview_workers) >= 2 or any(job.path == path and not job.isInterruptionRequested() for job in self.preview_workers):
            return
        worker = PreviewWorker(path, self)
        self.preview_workers.add(worker)
        worker.completed.connect(self._preview_ready, Qt.QueuedConnection)
        worker.finished.connect(lambda: self._preview_finished(worker), Qt.QueuedConnection)
        worker.start()

    def _preview_ready(self, path, value, stamp):
        if self._closing or path != self._active_path() or stamp != _file_stamp(path):
            return
        image, error = value
        if error:
            self._preview_failures[path] = error
            self.preview.setText(error)
            return
        self.previews.store(path, value, stamp, image.sizeInBytes())
        self._active_preview = (path, stamp, image)
        self._store_thumbnail(path, image, stamp)
        self._refresh_preview()
        self._pump_thumbnails()

    def _preview_finished(self, worker):
        self.preview_workers.discard(worker)
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        else:
            self._ensure_preview()
            self._pump_thumbnails()

    def _next_load(self):
        path = self._active_path()
        if self.tabs.currentIndex() == self.ALL_TAB and self._all_requested == path and self._full_record(path) is None:
            return path, None
        if path and self._record(path) is None:
            return path, EDITOR_FIELDS
        if path and self.tabs.currentIndex() == self.OVERVIEW_TAB:
            missing = self._overview_missing(path)
            if missing:
                return path, missing
        if (path and self.tabs.currentIndex() == self.EDIT_TAB
                and self._record(path) is not None
                and self._full_record(path) is None):
            extra = {
                name for field in self.overview_preferences.fields
                if self._pin_spec(field) is None
                for name in field.selectors
            }
            missing = tuple(
                name for name in self._overview_missing(path)
                if name in extra
            )
            if missing:
                return path, missing
        for candidate in self._load_paths:
            if self._record(candidate) is None:
                return candidate, EDITOR_FIELDS
        return None

    def _pump_load(self):
        if self._closing or self.worker is not None:
            return
        desired = self._next_load()
        if desired is None:
            if self._pending_action:
                action = self._pending_action
                self._pending_action = None
                self._load_paths = []
                QTimer.singleShot(0, self.batch_edit_selected if action == 'batch' else self.review_changes)
            return
        path, fields = desired
        generation = self._load_generation
        worker = MetadataWorker([path], self, fields=fields)
        if fields is not None and fields != EDITOR_FIELDS:
            worker.scope = "overview"
            previous, coverage = self._overview_snapshot(path)
            stamp = _record_stamp(path, previous.sidecars) if previous is not None else None
            if previous is None or self._overview_snapshot(path)[0] is not previous:
                worker.deleteLater()
                QTimer.singleShot(0, lambda: self._image_changed(self.file_list.editing_row))
                return
            worker.previous_overview = previous
            worker.previous_stamp = stamp
            worker.previous_coverage = coverage
            worker.overview_selectors = self.overview_preferences.selectors
            full = self._full_record(path)
            if full is not None and not full.error:
                worker.cached_record = full
                worker.cached_stamp = _record_stamp(path, full.sidecars)
        if fields is None:
            worker.derived_fields = EDITOR_FIELDS
        self.worker = worker
        worker.prepared.connect(lambda records, _previews, _error: self._receive_load(worker, generation, records), Qt.QueuedConnection)
        worker.finished.connect(lambda: self._worker_finished(worker), Qt.QueuedConnection)
        worker.start()

    def _receive_load(self, worker, generation, records):
        if self._closing or generation != self._load_generation:
            return
        for path, record in records.items():
            stamp = worker.stamps.get(path)
            if not record.error and stamp != _record_stamp(path, record.sidecars):
                continue
            if record.error:
                stamp = _record_stamp(path, record.sidecars)
            if worker.scope == "overview":
                self._store_overview(path, record, worker.overview_coverage, stamp, worker.weights[path])
                continue
            if worker.fields is None:
                existing = self._record(path)
                self.full_records.store(path, record, stamp, worker.weights[path])
                self._active_full = (stamp, record)
                if path in worker.derived_records and (existing is None or existing.error):
                    subset = worker.derived_records[path]
                    self.records.store(path, subset, stamp, worker.derived_weights[path])
                    self._active_record = (stamp, subset)
                    self._representation_indexes.pop(path, None)
            else:
                self.records.store(path, record, stamp, worker.weights[path])
                self._representation_indexes.pop(path, None)
                if path == self._active_path():
                    self._active_record = (stamp, record)
                if path in self._load_paths or path in self._proposal_paths():
                    self._planning_records[path] = (stamp, record)
        self._image_changed(self.file_list.editing_row)
        self._selection_changed()
        self._update_all_fields()

    def _proposal_paths(self):
        paths = {path for path, fields in self.drafts.items() if any(draft.operation != 'Leave unchanged' for draft in fields.values())}
        paths.update(path for path, _key, draft in self.source_drafts if draft.operation != 'Leave unchanged')
        paths.update(path for session in self.batch_sessions if session['fields'] for path in session['paths'])
        return [path for path in self.paths if path in paths]

    def _plan_records(self, paths):
        return {path: record for path in paths if (record := self._record(path)) is not None}

    def _prune_record_working_set(self):
        keep = set(self._load_paths) | set(self._proposal_paths())
        for path in tuple(self._planning_records):
            if path not in keep:
                del self._planning_records[path]
        indexed = set(self.records) | {self._active_path()}
        for path in tuple(self._representation_indexes):
            if path not in indexed:
                del self._representation_indexes[path]

    def _request_paths(self, paths, action):
        missing = [path for path in paths if self._record(path) is None]
        if not missing:
            return False
        self._pending_action = action
        self._load_paths = list(paths)
        for path in paths:
            record = self._record(path)
            if record is not None:
                self._planning_records[path] = (_record_stamp(path, record.sidecars), record)
        self.statusBar().showMessage('Loading metadata for the selected operation…')
        self._pump_load()
        return True

    @staticmethod
    def _pin_spec(field):
        if field.source or field.language or ":" in field.selector:
            return None
        return {
            "title": "title",
            "description": "caption",
            "keywords": "keywords",
            "creator": "creator",
            "copyright": "copyright",
            "usageterms": "usage",
        }.get(field.selector.casefold())

    def view_gps_on_map(self):
        """Inspect GPS without changing the Editor's pending drafts."""
        path = self._active_path()
        if not path:
            QMessageBox.information(
                self, "View on map", "Select an image first."
            )
            return

        try:
            from kim_location_dialog import LocationDialog
            dialog = LocationDialog("report", [path], "create", None)
            dialog.exec()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(
                self, "View on map",
                "Could not open the GPS viewer: " + str(exc)
            )

    def _configure_editor_pins(self):
        if OverviewFieldsDialog(
                self.overview_preferences, self
        ).exec() == QDialog.Accepted:
            self._reload_overview_preferences()

    def _unpin_supported_field(self, key):
        for field in self.overview_preferences.fields:
            if self._pin_spec(field) == key:
                self._unpin_editor_field(field)
                return

    def _unpin_editor_field(self, field):
        self.overview_preferences.reload()
        remaining = [
            current for current in self.overview_preferences.fields
            if current.key != field.key
        ]
        if len(remaining) == len(self.overview_preferences.fields):
            return
        self.overview_preferences.save(remaining)
        self._refresh_editor_pins()
        self._refresh_pending()
        self._update_overview()
        self._pump_load()

    def _new_readonly_pin(self, field):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 4, 8, 5)

        heading = QHBoxLayout()
        title = QLabel(field.label)
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        heading.addWidget(title, 1)

        pin = QToolButton()
        pin.setIcon(QIcon.fromTheme(
            "pin", QIcon.fromTheme("emblem-favorite")
        ))
        pin.setAutoRaise(True)
        pin.setToolTip("Unpin from Browser and Editor")
        pin.clicked.connect(
            lambda _checked=False, selected=field:
            self._unpin_editor_field(selected)
        )
        heading.addWidget(pin)
        layout.addLayout(heading)

        value = QPlainTextEdit()
        value.setReadOnly(True)
        value.setEnabled(False)
        value.setMaximumHeight(80)
        layout.addWidget(value)

        provenance = QLabel()
        provenance.setTextFormat(Qt.PlainText)
        provenance.setWordWrap(True)
        layout.addWidget(provenance)

        note = QLabel("Editing not supported in this version.")
        note.setEnabled(False)
        layout.addWidget(note)

        details = QPushButton("Details…")
        details.setEnabled(False)
        details.clicked.connect(
            lambda _checked=False, selected=field:
            self._readonly_pin_details(selected)
        )
        layout.addWidget(details, 0, Qt.AlignLeft)

        self._readonly_pins[field.key] = {
            "card": card, "value": value,
            "source": provenance, "details": details,
        }
        return card

    def _readonly_pin_details(self, field):
        path = self._active_path()
        if not path:
            return
        record = self._full_record(path)
        if record is None:
            record, _coverage = self._overview_snapshot(path)
        if record and not record.error:
            entries = field.entries(record)
            if entries:
                MetadataDetailsDialog(
                    entries, self, field.label
                ).exec()

    def _refresh_editor_pins(self):
        if not hasattr(self, "_pin_signature"):
            return
        fields = tuple(self.overview_preferences.fields)
        if fields != self._pin_signature:
            for control in self.field_controls.values():
                card = control["card"]
                self.fields_layout.removeWidget(card)
                card.hide()

            for widgets in self._readonly_pins.values():
                card = widgets["card"]
                self.fields_layout.removeWidget(card)
                card.hide()
                card.deleteLater()

            self._readonly_pins.clear()
            self._pin_order.clear()

            for field in fields:
                key = self._pin_spec(field)
                card = (
                    self.field_controls[key]["card"]
                    if key else self._new_readonly_pin(field)
                )
                self.fields_layout.insertWidget(
                    self.fields_layout.count() - 1, card
                )
                self._pin_order.append((field, card, key))

            self._pin_signature = fields

        path = self._active_path()
        base = self._record(path) if path else None
        record = self._full_record(path) if path else None
        if record is None and path:
            record, _coverage = self._overview_snapshot(path)

        missing = (
            set(self._overview_missing(path))
            if path and self._full_record(path) is None
            else set()
        )

        for field, card, key in self._pin_order:
            card.setVisible(bool(base and not base.error))
            if key:
                continue

            widgets = self._readonly_pins[field.key]
            value = widgets["value"]
            source = widgets["source"]
            details = widgets["details"]

            details.setEnabled(False)
            source.clear()
            value.setToolTip("")

            if not base or not record:
                value.setPlainText("Loading…")
                continue
            if record.error:
                value.setPlainText("Metadata unavailable")
                continue
            if any(name in missing for name in field.selectors):
                value.setPlainText("Loading pinned value…")
                continue

            entries = field.entries(record)
            if not entries:
                value.setPlainText("Not present")
                continue

            chosen = preferred_entry(
                entries, record, self.preferences.priority,
                language_alt=True, locale=QLocale().name()
            )
            if chosen is None and len(entries) == 1:
                chosen = entries[0]

            # Match Browser Overview for composite camera fields.
            # Never combine a source- or language-qualified pin with
            # values from another metadata representation.
            if (
                not field.source
                and not field.language
                and field.label in (
                    "Camera",
                    "Image dimensions",
                    "GPS position",
                    "GPS altitude",
                )
            ):
                formatted = self.overview._camera_values(
                    field.label, field.selectors, record
                )
                text = (
                    " | ".join(formatted)
                    if formatted
                    else _entry_value(chosen)
                    if chosen is not None
                    else "Multiple representations. See Details."
                )
            else:
                text = (
                    _entry_value(chosen)
                    if chosen is not None
                    else "Multiple representations. See Details."
                )
            text = str(text)
            value.setPlainText(
                text[:500] + "…" if len(text) > 500 else text
            )
            value.setToolTip(text[:1000])

            sources = list(dict.fromkeys(
                overview_source(entry, record)
                + (f" ({entry.language})" if entry.language else "")
                for entry in entries
            ))
            source.setText("Source: " + ", ".join(sources))
            details.setEnabled(True)

    def _build_fields(self):
        for spec in FIELD_SPECS:
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)
            box = QVBoxLayout(card)
            box.setContentsMargins(8, 4, 8, 5)
            box.setSpacing(3)
            heading = QHBoxLayout()
            title = QLabel(spec.label)
            title.setStyleSheet("font-weight: bold;")
            heading.addWidget(title)
            pin = QToolButton()
            pin.setIcon(QIcon.fromTheme(
                "pin", QIcon.fromTheme("emblem-favorite")
            ))
            pin.setAutoRaise(True)
            pin.setToolTip("Unpin from Browser and Editor")
            pin.clicked.connect(
                lambda _checked=False, key=spec.key:
                self._unpin_supported_field(key)
            )
            heading.addWidget(pin)
            state = QLabel()
            state.setWordWrap(True)
            heading.addStretch(1)
            sync = QCheckBox("Sync IPTC and XMP")
            sync.setChecked(self.preferences.sync_default and bool(spec.iim))
            sync.setEnabled(bool(spec.iim))

            clear = QPushButton("Clear…")
            clear.setMaximumWidth(82)
            clear.hide()
            heading.addWidget(clear)
            details = QPushButton("Other metadata sources (0)")
            details.setMaximumWidth(230)

            heading.addWidget(details)
            box.addLayout(heading)
            advanced = QGroupBox(spec.label)
            advanced_box = QVBoxLayout(advanced)
            advanced_box.addWidget(state)
            advanced_box.addWidget(sync)
            self.advanced_layout.addWidget(advanced)
            advanced.hide()

            conflict = QWidget()
            conflict_layout = QVBoxLayout(conflict)
            conflict_layout.setContentsMargins(0, 0, 0, 0)
            conflict_layout.setSpacing(2)
            conflict.hide()
            advanced_box.addWidget(conflict)

            edit = _input_widget(spec, f"individual_{spec.key}")
            if isinstance(edit, QPlainTextEdit):
                edit.setMinimumHeight(52 if spec.multiple else 62)
                edit.setMaximumHeight(86 if spec.multiple else 100)
            edit.setEnabled(False)
            box.addWidget(edit)
            note = QLabel()
            note.setWordWrap(True)
            note.hide()
            advanced_box.addWidget(note)
            byte_status = QLabel()
            byte_status.setWordWrap(True)
            byte_status.hide()
            advanced_box.addWidget(byte_status)
            create_target = QCheckBox("Create a new Embedded XMP value")
            create_target.hide()
            advanced_box.addWidget(create_target)
            create_counterpart = QCheckBox("Create the missing IPTC or XMP counterpart")
            create_counterpart.hide()
            advanced_box.addWidget(create_counterpart)
            self.fields_layout.addWidget(card)

            control = {"spec": spec, "card": card, "state": state, "clear": clear,
                       "pin": pin,
                       "details": details, "conflict": conflict, "conflict_layout": conflict_layout,
                       "edit": edit, "note": note, "byte_status": byte_status,
                       "advanced": advanced, "sync": sync, "create_target": create_target,
                       "create_counterpart": create_counterpart}
            self.field_controls[spec.key] = control
            clear.clicked.connect(lambda _checked=False, s=spec: self.clear_individual(s))
            details.clicked.connect(lambda _checked=False, s=spec: self.choose_source(s))
            sync.toggled.connect(lambda checked, s=spec: self.individual_sync_changed(s, checked))
            create_target.toggled.connect(lambda checked, s=spec: self.new_target_changed(s, checked))
            create_counterpart.toggled.connect(lambda checked, s=spec: self.counterpart_changed(s, checked))
            if isinstance(edit, QPlainTextEdit):
                edit.textChanged.connect(lambda s=spec, w=edit: self.individual_changed(s, _editor_text(w)))
            else:
                edit.textChanged.connect(lambda value, s=spec: self.individual_changed(s, value))

    def _active_path(self):
        row = self.file_list.editing_row
        return self.paths[row] if 0 <= row < len(self.paths) else None

    def _splitter_moved(self, *_args):
        self._refresh_preview()
        self._splitter_save_timer.start()

    def _restore_splitter_sizes(self):
        settings = self.preferences.settings
        for splitter, key, minimums, first_fraction in (
                (self.splitter, self.HORIZONTAL_SPLITTER_KEY, (220, 640), 0.31),
                (self.image_splitter, f'{self.IMAGE_SPLITTER_KEY}/preview-first', (155, 120), 0.62)):
            total = sum(splitter.sizes())
            if total <= sum(minimums):
                total = (splitter.width() if splitter.orientation() == Qt.Horizontal
                         else splitter.height()) - splitter.handleWidth()
            if total <= sum(minimums):
                continue
            saved = settings.value(key, None)
            if splitter is self.image_splitter and saved is None:
                previous = settings.value(self.IMAGE_SPLITTER_KEY, None)
                if isinstance(previous, (list, tuple)) and len(previous) == 2:
                    saved = [previous[1], previous[0]]
            sizes = _resized_splitter_sizes(saved, total, *minimums)
            if sizes is None:
                first = max(minimums[0], min(round(total * first_fraction), total - minimums[1]))
                sizes = [first, total - first]
            splitter.setSizes(sizes)
        self._refresh_preview()

    def _persist_splitter_sizes(self):
        settings = self.preferences.settings
        for splitter, key in ((self.splitter, self.HORIZONTAL_SPLITTER_KEY),
                              (self.image_splitter, f'{self.IMAGE_SPLITTER_KEY}/preview-first')):
            sizes = splitter.sizes()
            if len(sizes) == 2 and all(size > 0 for size in sizes):
                settings.setValue(key, list(sizes))
        settings.sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_preview()
        QTimer.singleShot(0, self._refresh_preview)

    def _refresh_preview(self):
        path = self.current_preview_path
        image = self._preview_image(path)
        thumbnail = self.thumbnails.get(path) if path else None
        if image is None and thumbnail is not None:
            image = thumbnail[0]
        if image is None:
            return
        if image.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Preview unavailable")
            return
        size = self.preview.contentsRect().size()
        if size.width() <= 0 or size.height() <= 0:
            return
        key = (path, image.cacheKey(), size.width(), size.height())
        if getattr(self, '_painted_preview', None) == key and self.preview.pixmap() and not self.preview.pixmap().isNull():
            return
        self._painted_preview = key
        scaled = image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setText("")
        self.preview.setPixmap(QPixmap.fromImage(scaled))

    def navigate(self, direction):
        row = self.file_list.editing_row
        target = row + direction
        if 0 <= target < len(self.paths):
            self.file_list.setCurrentRow(target, QItemSelectionModel.NoUpdate)
            self.file_list.set_editing_row(target)
            self.file_list.scrollToItem(self.file_list.item(target))

    def _selection_changed(self, *_args):
        if not hasattr(self, "batch_button"):
            return
        count = len(self.file_list.selectedItems())
        if self._pending_action == 'batch':
            selected = {item.data(Qt.UserRole) for item in self.file_list.selectedItems()}
            if selected != set(self._load_paths):
                self._pending_action = None
                self._load_paths = []
        self.selection_summary.setText(f"{count} images selected" if count != 1 else "1 image selected")
        self.batch_button.setToolTip(f"Edit {count} selected images" if count >= 2 else
                                     "Select two or more images with Ctrl+click or Shift+click")
        self.batch_button.setEnabled(count >= 2)

    def _field_draft(self, path, spec):
        return self.drafts.get(path, {}).get(spec.key)

    def _representations(self, path, spec):
        record = self._record(path)
        if record is None:
            return []
        cached = self._representation_indexes.get(path)
        if cached is None or cached[0] is not record:
            cached = (record, index_metadata_representations(record, FIELD_SPECS))
            self._representation_indexes[path] = cached
        return cached[1][spec.key]

    def _active_representation(self, path, spec):
        representations = self._representations(path, spec)
        selected = self.source_targets.get(path, {}).get(spec.key)
        if selected:
            found = next((item for item in representations if item.target.key == selected.key), None)
            if found:
                return found
        draft = self._field_draft(path, spec)
        if draft and draft.target:
            found = next((item for item in representations if item.target.key == draft.target.key), None)
            if found:
                return found
            if draft.operation != 'Leave unchanged':
                return None
        # Keep the index independent of priority and locale changes.
        preferred, _all = preferred_representation(
            self._record(path), spec, self.preferences.priority, QLocale().name(),
            representations=representations)
        if preferred:
            return preferred
        return None

    def _proposed_target(self, path, spec):
        return new_destination(path, spec, self.preferences.priority)

    def _field_value(self, path, spec):
        draft = self._field_draft(path, spec)
        if draft is not None:
            return draft.value
        representation = self._active_representation(path, spec)
        if not representation:
            return ""
        value = representation.value
        if isinstance(value, list):
            return "\n".join(value_text(item) for item in value)
        if isinstance(value, dict):
            language = representation.language or "x-default"
            value = value.get(language, value.get("x-default", next(iter(value.values()), "")))
        return value_text(value)

    @staticmethod
    def _representation_value(representation):
        if not representation:
            return ""
        value = representation.value
        if isinstance(value, list):
            return "\n".join(value_text(item) for item in value)
        if isinstance(value, dict):
            language = representation.language or "x-default"
            value = value.get(language, value.get("x-default", next(iter(value.values()), "")))
        return value_text(value)

    def open_metadata_settings(self):
        dialog = MetadataSettingsDialog(self.preferences, self)
        if dialog.exec() == QDialog.Accepted:
            # Settings affect future default selection; explicitly selected
            # targets and pending drafts remain pinned to their original source.
            self._refresh_individual(self._active_path())
            self._refresh_pending()

    def choose_source(self, spec):
        path = self._active_path()
        record = self._record(path) if path else None
        if not record:
            return
        representations = ordered_representations(
            self._representations(path, spec), self.preferences.priority, QLocale().name())
        if not representations:
            return
        current = self._active_representation(path, spec)
        dialog = SourceChooserDialog(spec, representations,
                                     current.target if current else None, self)
        if dialog.exec() != QDialog.Accepted or not dialog.selected:
            return
        if current and dialog.selected.target.key == current.target.key:
            return
        draft = self._field_draft(path, spec)
        if draft and draft.operation != "Leave unchanged":
            box = QMessageBox(self)
            box.setWindowTitle("Pending edit for this source")
            box.setText(f"Keep the pending {spec.label} edit for {draft.target.display if draft.target else 'the current source'}?")
            keep = box.addButton("Keep original draft", QMessageBox.AcceptRole)
            discard = box.addButton("Discard and switch", QMessageBox.DestructiveRole)
            cancel = box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked == cancel:
                return
            if clicked == keep:
                self.source_drafts.append((path, spec.key, draft))
            elif clicked != discard:
                return
            self.drafts.get(path, {}).pop(spec.key, None)
        self.source_targets.setdefault(path, {})[spec.key] = dialog.selected.target
        self._refresh_individual(path)
        self._refresh_pending()


    def individual_sync_changed(self, spec, checked):
        path = self._active_path()
        if not path:
            return
        self.sync_overrides.setdefault(path, {})[spec.key] = bool(checked)
        draft = self._field_draft(path, spec)
        if draft and draft.operation != "Leave unchanged":
            draft.sync = bool(checked)
        self._refresh_individual(path)
        self._refresh_pending()

    def new_target_changed(self, spec, checked):
        path = self._active_path()
        draft = self._field_draft(path, spec) if path else None
        if checked and draft and draft.target and not draft.target.is_new and not self._representations(path, spec):
            draft.target = self._proposed_target(path, spec)
        target = (draft.target if draft and draft.target else
                  self._active_representation(path, spec).target if path and self._active_representation(path, spec)
                  else self._proposed_target(path, spec) if path else None)
        if path and target:
            self.creation_authorizations.setdefault(path, {}).setdefault(spec.key, {})[target.key] = bool(checked)
        if draft:
            draft.authorize_new_target = bool(checked)
            self._refresh_individual(path)
            self._refresh_pending()

    def counterpart_changed(self, spec, checked):
        path = self._active_path()
        draft = self._field_draft(path, spec) if path else None
        target = (draft.target if draft and draft.target else
                  self._active_representation(path, spec).target if path and self._active_representation(path, spec)
                  else self._proposed_target(path, spec) if path else None)
        if path and target:
            self.counterpart_authorizations.setdefault(path, {}).setdefault(spec.key, {})[target.key] = bool(checked)
        if draft:
            draft.create_counterpart = bool(checked)
            self._refresh_pending()

    def _field_is_editable(self, path):
        record = self._record(path)
        return bool(record and not record.error and detected_file_type(record) == "JPEG")

    def _image_changed(self, row):
        path = self.paths[row] if 0 <= row < len(self.paths) else None
        token = (path, _file_stamp(path) if path else None)
        if token != getattr(self, '_selection_token', None):
            self._selection_token = token
            self._load_generation += 1
            self._preview_failures.clear()
            self._active_preview = None
            self._active_record = None
            self._active_full = None
            for worker in self.preview_workers:
                if worker.path != path:
                    worker.requestInterruption()
            if self.worker is not None:
                self.worker.requestInterruption()
            if self._inspection_filter is not None:
                self._inspection_filter.requestInterruption()
            self._inspection_record = None
            self.all_model.set_record(None)
            self._all_requested = path if self.tabs.currentIndex() == self.ALL_TAB else None
        self.current_preview_path = path
        if path:
            if self._preview_image(path) is None and self.thumbnails.get(path) is None:
                self.preview.setPixmap(QPixmap())
                self.preview.setText("Loading preview…")
            else:
                self._refresh_preview()
            record = self._record(path)
            if record is None:
                self.image_info.setText(f"{Path(path).name}\nReading image information…")
                fmt, dims = "Reading…", ""
            else:
                fmt = detected_file_type(record) or "Unknown format"
                width = _metadata_value(record, ("ImageWidth", "ExifImageWidth", "SourceImageWidth"))
                height = _metadata_value(record, ("ImageHeight", "ExifImageHeight", "SourceImageHeight"))
                dims = f"{width} × {height}" if width and height else "Dimensions unavailable"
                if record.error:
                    dims += " · Could not read metadata"
                elif fmt != "JPEG":
                    dims += " · Read-only inspection"
                self.image_info.setText(f"{Path(path).name}\n{fmt} · {dims}")
            self.image_heading.setText(f"Editing image {row + 1} of {len(self.paths)}")
            self.previous_button.setEnabled(row > 0)
            self.next_button.setEnabled(row < len(self.paths) - 1)
        else:
            self.image_heading.setText("No images selected")
            self.image_info.setText("")
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Image preview")
        self._refresh_individual(path)
        self._refresh_pending()
        record = self._record(path)
        self.loading_label.setText(record.error if record and record.error else 'Loading metadata…')
        self.loading_label.setVisible(record is None or bool(record.error))
        self.retry_metadata.setVisible(bool(record and record.error))
        self._refresh_editor_pins()
        self.target_notice.setVisible(bool(record and not record.error))
        self._refresh_pending()
        self._update_all_fields()
        self._update_overview()
        self._ensure_preview()
        self._pump_thumbnails()
        self._pump_load()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def _refresh_conflicts(self, path, spec, record, control, state):
        layout = control["conflict_layout"]
        self._clear_layout(layout)
        if not record or state != "Conflicting":
            control["conflict"].hide()
            return
        label = QLabel("Choose a stored value or type an intended replacement.")
        label.setWordWrap(True)
        layout.addWidget(label)
        entries = candidate_conflict_entries(record, spec)
        representations = {}
        for entry in entries:
            source = entry_source(record, entry)
            text = _entry_value(entry)
            key = (source, text)
            representations[key] = representations.get(key, 0) + 1
        for (source, text), occurrences in representations.items():
            row = QHBoxLayout()
            repeated = f" ({occurrences} entries)" if occurrences > 1 else ""
            value = QLabel(f"{source}{repeated}: {text}")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(value, 1)
            use = QPushButton("Use this value")
            use.clicked.connect(lambda _checked=False, s=spec, v=text:
                                self.choose_conflict_value(s, v))
            row.addWidget(use)
            layout.addLayout(row)
        layout.activate()
        control["conflict"].setMinimumHeight(layout.sizeHint().height())
        control["conflict"].show()

    def _refresh_individual(self, path):
        self._refreshing = True
        record = self._record(path) if path else None
        editable = bool(path and self._field_is_editable(path))
        for spec in FIELD_SPECS:
            control = self.field_controls[spec.key]
            representation = self._active_representation(path, spec) if record else None
            representations = self._representations(path, spec) if record else []
            target = representation.target if representation else (
                self._proposed_target(path, spec) if path and not representations else None)
            if record:
                value = self._field_value(path, spec)
                if record.error:
                    label = "Could not read"
                elif not editable:
                    label = "Read only"
                elif representation and representation.editable:
                    label = f"Editing: {representation.source}" + (
                        f" · {representation.language}" if representation.language else "")
                elif representation:
                    label = f"From: {representation.source} · read only"
                elif representations:
                    label = "Choose a metadata source with a single value"
                else:
                    label = f"Target: {target.source}" if target else "Not present"
            else:
                value, label = "", "Loading…"
            control["state"].setText(label)
            control["details"].setText("Sources…")
            control["details"].setToolTip(
                f"Inspect or choose among {len(representations)} metadata representations"
            )
            control["details"].setEnabled(bool(representations))
            control["details"].setVisible(bool(representations))
            _set_editor_text(control["edit"], value)
            control["edit"].setEnabled(editable and
                                       ((bool(representation) and representation.editable) or not representations))
            control["conflict"].hide()
            has_target = bool(representation and representation.editable)
            control["clear"].setVisible(editable and has_target)
            draft = self._field_draft(path, spec) if path else None
            if draft and draft.operation == "Clear":
                note = "Marked to clear. The change remains pending until Review changes."
            elif not representation and representations:
                note = "The preferred source has multiple values. Inspect the alternatives before editing."
            elif not representation and record and not record.error:
                note = "Choose where to store this field in Sources & targets before reviewing."
            elif value == "" and representation and representation.value not in ("", None, [], {}):
                note = "A blank input will not clear metadata. Use Clear to remove it."
            elif record and not editable:
                note = "Editing is available for eligible JPEG images."
            else:
                note = ""
            control["note"].setText(note)
            control["note"].setVisible(bool(note))
            sync_allowed = (not representation or (representation.editable and
                           representation.source in ("Embedded XMP", "IPTC-IIM")))
            control["sync"].setEnabled(bool(spec.iim) and editable and sync_allowed)
            if not sync_allowed:
                control["sync"].setToolTip("Sync applies to embedded XMP and IPTC-IIM only.")
            else:
                control["sync"].setToolTip("")
            if draft and draft.operation != "Leave unchanged":
                desired_sync = draft.sync
            elif path and spec.key in self.sync_overrides.get(path, {}):
                desired_sync = self.sync_overrides[path][spec.key]
            else:
                desired_sync = self.preferences.sync_default and bool(spec.iim)
            blocker = QSignalBlocker(control["sync"])
            control["sync"].setChecked(desired_sync)
            del blocker
            is_new = bool(draft and draft.target and draft.target.is_new) or (not representation and not representations)
            proposed_target = draft.target if draft and draft.target and draft.target.is_new else target
            control["create_target"].setText(
                f"Allow new {proposed_target.source} target" if proposed_target else "Allow new target")
            control["create_target"].setVisible(editable and is_new)
            create_authorized = (draft.authorize_new_target if draft and draft.target and draft.target.key == proposed_target.key
                                 else self.creation_authorizations.get(path, {}).get(spec.key, {}).get(proposed_target.key, False)
                                 if path and proposed_target else False)
            blocker = QSignalBlocker(control["create_target"])
            control["create_target"].setChecked(bool(create_authorized))
            del blocker
            counterpart_missing = False
            if spec.iim and control["sync"].isChecked():
                active_source = representation.source if representation else proposed_target.source
                counterpart_source = "IPTC-IIM" if active_source == "Embedded XMP" else "Embedded XMP"
                counterpart_tag = spec.iim if counterpart_source == "IPTC-IIM" else spec.xmp
                counterpart_missing = not any(item.source == counterpart_source and
                                               item.canonical_target == counterpart_tag
                                               for item in representations)
            control["create_counterpart"].setVisible(
                editable and bool(spec.iim) and control["sync"].isChecked() and counterpart_missing)
            counterpart_authorized = (draft.create_counterpart if draft and draft.target and draft.target.key == target.key
                                      else self.counterpart_authorizations.get(path, {}).get(spec.key, {}).get(target.key, False)
                                      if path and target else False)
            blocker = QSignalBlocker(control["create_counterpart"])
            control["create_counterpart"].setChecked(bool(counterpart_authorized))
            del blocker
            counts_for_iptc = bool(target and target.source == "IPTC-IIM") or control["sync"].isChecked()
            if counts_for_iptc:
                self._update_bytes(spec, value, control["byte_status"])
            else:
                control["byte_status"].hide()
        self._refreshing = False

    def _update_bytes(self, spec, value, label):
        if spec.iim_limit is None:
            label.hide()
            return
        values = [item for item in value.splitlines() if item] if spec.multiple else [value]
        count = max((len(item.encode("utf-8")) for item in values), default=0)
        if count >= int(spec.iim_limit * 0.8) or count > spec.iim_limit:
            label.setText(f"{count} of {spec.iim_limit} UTF-8 bytes"
                          f"{' per entry' if spec.multiple else ''}")
            label.show()
        else:
            label.hide()

    def individual_changed(self, spec, value):
        if self._refreshing:
            return
        path = self._active_path()
        record = self._record(path) if path else None
        if not record or not self._field_is_editable(path):
            return
        representation = self._active_representation(path, spec)
        target = representation.target if representation else self._proposed_target(path, spec)
        baseline = self._representation_value(representation)
        if not value:
            operation = "Leave unchanged"
        elif value == baseline:
            operation = "Leave unchanged"
        elif not representation or representation.is_empty:
            operation = "Fill empty"
        else:
            operation = "Replace"
        self.drafts.setdefault(path, {})[spec.key] = Draft(
            operation, value, target, self.field_controls[spec.key]["sync"].isChecked(),
            self.field_controls[spec.key]["create_counterpart"].isChecked(),
            self.field_controls[spec.key]["create_target"].isChecked())
        note = self.field_controls[spec.key]["note"]
        if not value and baseline:
            note.setText("A blank input will not clear metadata. Use Clear to remove it.")
            note.show()
        else:
            note.clear()
            note.hide()
        self._update_bytes(spec, value, self.field_controls[spec.key]["byte_status"])
        self._refresh_pending()

    def choose_conflict_value(self, spec, value):
        widget = self.field_controls[spec.key]["edit"]
        if isinstance(widget, QPlainTextEdit):
            widget.setPlainText(value)
        else:
            widget.setText(value)

    def clear_individual(self, spec):
        path = self._active_path()
        if not path or path not in self.records:
            return
        answer = QMessageBox.question(
            self, "Clear metadata",
            f"Clear {spec.label} for {Path(path).name}? This creates a pending proposal for review.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return
        representation = self._active_representation(path, spec)
        if representation is None:
            return
        control = self.field_controls[spec.key]
        self.drafts.setdefault(path, {})[spec.key] = Draft(
            "Clear", "", representation.target, control["sync"].isChecked(),
            control["create_counterpart"].isChecked())
        self._refresh_individual(path)
        self._refresh_pending()

    def show_individual_details(self, spec):
        path = self._active_path()
        record = self._record(path) if path else None
        if not record:
            return
        state, details, sources = field_state(record, spec)
        text = details or f"{state}: no stored value"
        text += f"\n\nSources: {sources or 'None'}"
        text += f"\nCanonical targets: {', '.join(intended_targets(spec))}"
        FieldDetailsDialog(spec.label, text, self).exec()

    def batch_edit_selected(self):
        if self._closing:
            return
        selected = {item.data(Qt.UserRole) for item in self.file_list.selectedItems()}
        paths = [path for path in self.paths if path in selected]
        if len(paths) < 2:
            return
        if self._request_paths(paths, 'batch'):
            return
        key = tuple(paths)
        existing = next((session for session in self.batch_sessions
                         if tuple(session["paths"]) == key), None)
        dialog = BatchEditDialog(paths, self._plan_records(paths), existing["fields"] if existing else {}, self,
                                 self.preferences.priority, self.preferences.sync_default)
        if dialog.exec() != QDialog.Accepted:
            self._prune_record_working_set()
            return
        fields = {} if getattr(dialog, "discard_requested", False) else dialog.selected_fields()
        if existing:
            self.batch_sessions.remove(existing)
        if fields:
            pinned_targets = {}
            for spec in FIELD_SPECS:
                draft = fields.get(spec.key)
                if not draft or not draft.batch_preferred_source:
                    continue
                previous = existing.get("fields", {}).get(spec.key) if existing else None
                same_draft = bool(previous and
                                  (draft.operation, draft.value, draft.sync,
                                   draft.create_counterpart, draft.authorize_new_target,
                                   draft.batch_preferred_source) ==
                                  (previous.operation, previous.value, previous.sync,
                                   previous.create_counterpart, previous.authorize_new_target,
                                   previous.batch_preferred_source))
                if same_draft and spec.key in existing.get("targets", {}):
                    pinned_targets[spec.key] = dict(existing["targets"][spec.key])
                    continue
                per_image = {}
                for path in paths:
                    record = self._record(str(Path(path).resolve(strict=False)))
                    if not record or record.error or detected_file_type(record) != "JPEG":
                        continue
                    preferred, available = preferred_representation(
                        record, spec, self.preferences.priority, QLocale().name())
                    if preferred:
                        per_image[str(Path(path).resolve(strict=False))] = preferred.target
                    elif available:
                        per_image[str(Path(path).resolve(strict=False))] = None
                    else:
                        per_image[str(Path(path).resolve(strict=False))] = new_destination(
                            path, spec, self.preferences.priority)
                pinned_targets[spec.key] = per_image
            self.batch_sessions.append({"paths": tuple(paths), "fields": fields,
                                       "priority": tuple(self.preferences.priority),
                                       "targets": pinned_targets})
        self._refresh_pending()

    def _refresh_sources_targets(self):
        """Present current sources and controls for proposed changes."""
        if not hasattr(self, "sources_targets_help"):
            return

        path = self._active_path()
        record = self._record(path) if path else None
        changed = []
        descriptions = []

        for spec in FIELD_SPECS:
            control = self.field_controls[spec.key]
            draft = self._field_draft(path, spec) if path else None
            pending = bool(
                draft is not None
                and draft.operation != "Leave unchanged"
            )

            control["advanced"].setVisible(pending)

            if pending:
                changed.append(spec.label)

            if record is None or record.error:
                continue

            active = self._active_representation(path, spec)
            available = self._representations(path, spec)

            if active is not None:
                description = active.source
                if active.language:
                    description += f" ({active.language})"
                if not active.editable:
                    description += " (read-only)"
                if len(available) > 1:
                    other = len(available) - 1
                    description += (
                        f", {other} other representation"
                        + ("s" if other != 1 else "")
                    )
            elif available:
                sources = ", ".join(sorted({
                    item.source for item in available
                }))
                description = (
                    f"Multiple values ({sources}), "
                    "choose a source on Edit metadata"
                )
            else:
                description = "Not present"

            if pending:
                if draft.target is not None:
                    description += f" | Proposed target: {draft.target.source}"
                    if draft.target.language:
                        description += f" ({draft.target.language})"
                    if draft.target.is_new and not draft.authorize_new_target:
                        description += " (authorization required)"
                else:
                    description += " | Change proposed"

            descriptions.append(f"{spec.label}: {description}")

        lines = [
            "Planning only. Your image files will not be changed.",
            "",
        ]

        if path is None:
            lines.append("Select an image to inspect its metadata sources.")
        elif record is None:
            lines.append("Loading metadata for this image…")
        elif record.error:
            lines.append("Metadata could not be read for this image.")
        else:
            priority = " > ".join(
                str(item) for item in self.preferences.priority
            )
            lines.extend([
                "Metadata reading priority",
                priority or "Not configured",
                "",
                "Common metadata fields",
                *descriptions,
                "",
                "Camera, GPS, and other technical metadata are "
                "available in Overview and All fields.",
            ])

            if changed:
                lines.extend([
                    "",
                    "Proposed changes: " + ", ".join(changed),
                    "Review the storage targets and any required "
                    "permissions below before opening Review changes.",
                ])
            elif path in self._proposal_paths():
                lines.extend([
                    "",
                    "Additional changes are pending for this image.",
                    "Their exact targets appear in Review changes.",
                ])
            else:
                lines.extend([
                    "",
                    "No changes proposed for this image.",
                    "Edit a field on Edit metadata to review its "
                    "storage target here.",
                ])

        self.sources_targets_help.setText("\n".join(lines))

    def _refresh_pending(self):
        if not hasattr(self, "pending_label"):
            return
        self._refresh_sources_targets()
        self._prune_record_working_set()
        paths = self._proposal_paths()
        if not paths:
            self.pending_label.setText('Pending changes: 0')
            self.review_button.setEnabled(False)
            return
        plan = build_plan(paths, self._plan_records(paths), self.drafts, 'Combined', self.batch_sessions,
                          self.source_drafts, self.preferences.priority)
        valid = sum(row.get("status") == "valid" for row in plan)
        blocked = sum(row.get("status") == "blocked" for row in plan)
        count = valid + blocked
        self.review_button.setEnabled(count > 0)
        if not count:
            self.pending_label.setText("Pending changes: 0")
            return
        change_label = "change" if count == 1 else "changes"
        self.pending_label.setText(
            f"Pending changes: {count} {change_label}"
            + (f" · {blocked} blocked" if blocked else ""))

    def _scan_complete(self, records, previews):
        # Records are extraction snapshots. A refresh can reuse an object, so
        # invalidate its derived values even when its identity is unchanged.
        for path in records:
            self._representation_indexes.pop(path, None)
        self.records.update(records)
        self.previews.update(previews)
        self._image_changed(self.file_list.editing_row)
        self._selection_changed()
        self.statusBar().showMessage("Read-only change planner. No metadata will be written.")

    def _worker_finished(self, worker=None):
        worker = worker or self.worker
        if worker is not self.worker:
            return
        self.worker = None
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        else:
            self._image_changed(self.file_list.editing_row)
            self._pump_load()

    def _finish_close(self):
        if self.worker is None and not self.preview_workers and self._inspection_filter is None and self.thumbnail_worker is None:
            self.close()

    def review_changes(self):
        if self._closing:
            return
        paths = self._proposal_paths()
        if self._request_paths(paths, 'review'):
            return
        plan = build_plan(paths, self._plan_records(paths), self.drafts, 'Combined', self.batch_sessions,
                          self.source_drafts, self.preferences.priority)
        if not any(row.get("status") in ("valid", "blocked") for row in plan):
            self._refresh_pending()
            return
        ReviewDialog(plan, self, len(paths)).exec()

    def closeEvent(self, event):
        paths = self._proposal_paths()
        plan = build_plan(paths, self._plan_records(paths), self.drafts, 'Combined', self.batch_sessions,
                          self.source_drafts, self.preferences.priority) if paths else []
        if any(row.get("status") in ("valid", "blocked") for row in plan):
            answer = QMessageBox.question(
                self, "Pending changes",
                "Your proposed changes have not been written. Keep editing or discard them?",
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Discard:
                event.ignore()
                return
            self.drafts.clear()
            self.source_drafts.clear()
            self.batch_sessions.clear()
        self._closing = True
        self._pending_action = None
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.requestInterruption()
        for worker in self.preview_workers:
            worker.requestInterruption()
        if self._inspection_filter:
            self._inspection_filter.requestInterruption()
        if self.worker:
            self.worker.requestInterruption()
            if not self.worker.isRunning():
                self.worker.deleteLater()
                self.worker = None
        if self.worker is not None or self.preview_workers or self._inspection_filter is not None or self.thumbnail_worker is not None:
            event.ignore()
            return
        self._persist_splitter_sizes()
        super().closeEvent(event)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    shutdown_requested = False

    def request_shutdown(_signum, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    signal.signal(signal.SIGINT, request_shutdown)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KIM6 Metadata Editor")
    app.setOrganizationName("KIM6")
    window = MetadataEditor(argv)
    window.show()
    shutdown_timer = QTimer()
    shutdown_timer.setInterval(100)
    def process_shutdown_request():
        if shutdown_requested:
            shutdown_timer.stop()
            window.close()
    shutdown_timer.timeout.connect(process_shutdown_request)
    shutdown_timer.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
