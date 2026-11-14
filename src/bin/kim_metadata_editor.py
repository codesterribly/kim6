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
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QLocale, QSignalBlocker
    from PySide6.QtGui import QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
        QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
        QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
        QScrollArea, QVBoxLayout, QWidget, QTreeWidget, QTreeWidgetItem,
        QGroupBox, QToolButton, QFrame, QCheckBox, QAbstractItemView,
        QSizePolicy,
    )
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        print("KIM6 Metadata Editor requires PySide6. Install the KIM6 Qt runtime and try again.", file=sys.stderr)
        raise SystemExit(2) from exc
    raise

from kim_metadata_reader import MetadataEntry, MetadataRecord, read_metadata, value_text
from kim_photo_selection import read_thumbnail
from kim_process import inspection_context
from kim_metadata_sources import (
    MetadataSourcePreferences, MetadataRepresentation, TargetIdentity,
    SOURCE_PRIORITY_DEFAULT, metadata_representations, ordered_representations,
    preferred_entry, preferred_representation,
)


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


class MetadataWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self):
        try:
            with inspection_context(cancelled=self.isInterruptionRequested):
                records = read_metadata(self.paths)
        except Exception as exc:
            records = {str(Path(path).resolve(strict=False)): MetadataRecord(
                path=str(Path(path).resolve(strict=False)), error=str(exc)) for path in self.paths}
        previews = {}
        for path in self.paths:
            if self.isInterruptionRequested():
                break
            key = str(Path(path).resolve(strict=False))
            try:
                image, _stamp = read_thumbnail(path, QSize(480, 360))
                previews[key] = image
            except Exception:
                previews[key] = QImage()
        self.completed.emit(records, previews)


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
        self.copy_notice = QLabel("Planned save: Create copies · Beside each source")
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
        self.setWindowTitle("Batch edit selected images")
        self.resize(820, 560)
        self.setMinimumSize(680, 480)
        layout = QVBoxLayout(self)

        heading = QLabel(f"Batch edit {len(self.paths)} selected images")
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
            apply_check = QCheckBox("Apply")
            apply_check.setObjectName(f"batch_apply_{spec.key}")
            header.addWidget(apply_check)
            box.addLayout(header)

            controls = QWidget()
            control_layout = QVBoxLayout(controls)
            control_layout.setContentsMargins(0, 2, 0, 0)
            operation = QComboBox()
            operation.setObjectName(f"batch_operation_{spec.key}")
            operation.addItems(
                ["Replace keywords", "Fill empty", "Add keywords", "Remove keywords", "Clear"]
                if spec.key == "keywords" else ["Replace", "Fill empty", "Clear"])
            edit = _input_widget(spec, f"batch_value_{spec.key}")
            sync = QCheckBox("Sync IPTC and XMP")
            sync.setChecked(self.sync_default and bool(spec.iim))
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
            controls.hide()
            box.addWidget(controls)
            fields.addWidget(card)

            previous = self.existing.get(spec.key)
            if previous:
                apply_check.setChecked(True)
                operation.setCurrentText(previous.operation)
                _set_editor_text(edit, previous.value)
                sync.setChecked(previous.sync)
                counterpart.setChecked(previous.create_counterpart)
                new_target.setChecked(previous.authorize_new_target)
            def update_operation(value, edit=edit, clear_note=clear_note, check=apply_check):
                clear = value == "Clear"
                edit.setEnabled(check.isChecked() and not clear)
                clear_note.setVisible(check.isChecked() and clear)
            def update_apply(checked, controls=controls, operation=operation, edit=edit,
                             clear_note=clear_note, check=apply_check, update=update_operation):
                controls.setVisible(checked)
                update(operation.currentText(), edit, clear_note, check)
            apply_check.toggled.connect(update_apply)
            operation.currentTextChanged.connect(update_operation)
            edit.textChanged.connect(lambda *_args, s=spec, w=edit, label=byte_status:
                                     self.update_bytes(s, _editor_text(w), label))
            update_operation(operation.currentText())
            if previous:
                controls.show()
            self.controls[spec.key] = {
                "spec": spec, "apply": apply_check, "controls": controls,
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
        layout.addWidget(buttons)

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
            if not control["apply"].isChecked():
                continue
            operation = control["operation"].currentText()
            value = "" if operation == "Clear" else _editor_text(control["edit"])
            result[spec.key] = Draft(operation, value, sync=control["sync"].isChecked(),
                                      create_counterpart=control["counterpart"].isChecked(),
                                      authorize_new_target=control["new_target"].isChecked(),
                                      batch_preferred_source=self.target_policy.isChecked())
        return result


class MetadataEditor(QMainWindow):
    HORIZONTAL_SPLITTER_KEY = "metadata/editorHorizontalSplitterSizes"
    IMAGE_SPLITTER_KEY = "metadata/editorImagePanelSplitterSizes"

    def __init__(self, paths, preferences=None):
        super().__init__()
        self.paths = [str(Path(path).expanduser().resolve(strict=False)) for path in paths]
        self.records = {}
        self.previews = {}
        self.preferences = preferences or MetadataSourcePreferences()
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
        self.batch_button = QPushButton("Batch edit selected (0)…")
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
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._image_changed)
        self.file_list.itemSelectionChanged.connect(self._selection_changed)
        image_list_layout.addWidget(self.file_list, 1)
        self.image_list_panel.setMinimumHeight(120)
        self.image_splitter.addWidget(self.image_list_panel)

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
        self.image_splitter.setStretchFactor(0, 1)
        self.image_splitter.setStretchFactor(1, 1)
        self.image_splitter.setSizes([250, 220])
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
        self._build_fields()
        self.fields_layout.addStretch(1)
        self.form_scroll.setWidget(self.form_content)
        self.splitter.addWidget(self.form_scroll)
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
        self.review_button = QPushButton("Review changes")
        self.review_button.setDefault(True)
        self.review_button.clicked.connect(self.review_changes)
        footer.addWidget(self.review_button)
        layout.addLayout(footer)
        self.statusBar().showMessage("Metadata writing is unavailable in this development phase.")

        if self.paths:
            for path in self.paths:
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self.file_list.addItem(item)
            self.file_list.setCurrentRow(0)
            self.worker = MetadataWorker(self.paths, self)
            self.worker.completed.connect(self._scan_complete)
            self.worker.finished.connect(self._worker_finished)
            self.worker.start()
        else:
            self.image_heading.setText("No images selected")
            self.review_button.setEnabled(False)
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
        self._selection_changed()
        self._refresh_pending()
        QTimer.singleShot(0, self._restore_splitter_sizes)

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
            state = QLabel()
            state.setWordWrap(True)
            heading.addWidget(state, 1)
            sync = QCheckBox("Sync IPTC and XMP")
            sync.setChecked(self.preferences.sync_default and bool(spec.iim))
            sync.setEnabled(bool(spec.iim))
            heading.addWidget(sync)
            clear = QPushButton("Clear…")
            clear.setMaximumWidth(82)
            clear.hide()
            heading.addWidget(clear)
            details = QPushButton("Other metadata sources (0)")
            details.setMaximumWidth(230)
            heading.addWidget(details)
            box.addLayout(heading)

            conflict = QWidget()
            conflict_layout = QVBoxLayout(conflict)
            conflict_layout.setContentsMargins(0, 0, 0, 0)
            conflict_layout.setSpacing(2)
            conflict.hide()
            box.addWidget(conflict)

            edit = _input_widget(spec, f"individual_{spec.key}")
            if isinstance(edit, QPlainTextEdit):
                edit.setMinimumHeight(52 if spec.multiple else 62)
                edit.setMaximumHeight(86 if spec.multiple else 100)
            edit.setEnabled(False)
            box.addWidget(edit)
            note = QLabel()
            note.setWordWrap(True)
            note.hide()
            box.addWidget(note)
            byte_status = QLabel()
            byte_status.setWordWrap(True)
            byte_status.hide()
            box.addWidget(byte_status)
            create_target = QCheckBox("Create a new Embedded XMP value")
            create_target.hide()
            box.addWidget(create_target)
            create_counterpart = QCheckBox("Create the missing IPTC or XMP counterpart")
            create_counterpart.hide()
            box.addWidget(create_counterpart)
            self.fields_layout.addWidget(card)

            control = {"spec": spec, "card": card, "state": state, "clear": clear,
                       "details": details, "conflict": conflict, "conflict_layout": conflict_layout,
                       "edit": edit, "note": note, "byte_status": byte_status,
                       "sync": sync, "create_target": create_target,
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
        row = self.file_list.currentRow()
        return self.paths[row] if 0 <= row < len(self.paths) else None

    def _splitter_moved(self, *_args):
        self._refresh_preview()
        self._splitter_save_timer.start()

    def _restore_splitter_sizes(self):
        settings = self.preferences.settings
        for splitter, key, minimums, first_fraction in (
                (self.splitter, self.HORIZONTAL_SPLITTER_KEY, (220, 640), 0.31),
                (self.image_splitter, self.IMAGE_SPLITTER_KEY, (120, 155), 0.53)):
            total = sum(splitter.sizes())
            if total <= sum(minimums):
                total = (splitter.width() if splitter.orientation() == Qt.Horizontal
                         else splitter.height()) - splitter.handleWidth()
            if total <= sum(minimums):
                continue
            saved = settings.value(key, None)
            sizes = _resized_splitter_sizes(saved, total, *minimums)
            if sizes is None:
                first = max(minimums[0], min(round(total * first_fraction), total - minimums[1]))
                sizes = [first, total - first]
            splitter.setSizes(sizes)
        self._refresh_preview()

    def _persist_splitter_sizes(self):
        settings = self.preferences.settings
        for splitter, key in ((self.splitter, self.HORIZONTAL_SPLITTER_KEY),
                              (self.image_splitter, self.IMAGE_SPLITTER_KEY)):
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
        image = self.previews.get(path) if path else None
        if image is None:
            return
        if image.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Preview unavailable")
            return
        size = self.preview.contentsRect().size()
        if size.width() <= 0 or size.height() <= 0:
            return
        scaled = image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setText("")
        self.preview.setPixmap(QPixmap.fromImage(scaled))

    def navigate(self, direction):
        row = self.file_list.currentRow()
        target = row + direction
        if 0 <= target < len(self.paths):
            self.file_list.setCurrentRow(target)
            self.file_list.scrollToItem(self.file_list.item(target))

    def _selection_changed(self, *_args):
        if not hasattr(self, "batch_button"):
            return
        count = len(self.file_list.selectedItems())
        self.batch_button.setText(f"Batch edit selected ({count})…")
        self.batch_button.setEnabled(count >= 2 and len(self.records) == len(self.paths))

    def _field_draft(self, path, spec):
        return self.drafts.get(path, {}).get(spec.key)

    def _representations(self, path, spec):
        record = self.records.get(path)
        return metadata_representations(record, spec) if record else []

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
        preferred, _all = preferred_representation(
            self.records[path], spec, self.preferences.priority, QLocale().name())
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
        record = self.records.get(path) if path else None
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
        target = (draft.target if draft and draft.target else
                  self._active_representation(path, spec).target if path and self._active_representation(path, spec)
                  else self._proposed_target(path, spec) if path else None)
        if path and target:
            self.creation_authorizations.setdefault(path, {}).setdefault(spec.key, {})[target.key] = bool(checked)
        if draft:
            draft.authorize_new_target = bool(checked)
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
        record = self.records.get(path)
        return bool(record and not record.error and detected_file_type(record) == "JPEG")

    def _image_changed(self, row):
        path = self.paths[row] if 0 <= row < len(self.paths) else None
        self.current_preview_path = path
        if path:
            if path not in self.previews:
                self.preview.setPixmap(QPixmap())
                self.preview.setText("Loading preview…")
            else:
                self._refresh_preview()
            record = self.records.get(path)
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
                    dims += " · Read only in Phase 1"
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
        record = self.records.get(path) if path else None
        editable = bool(path and self._field_is_editable(path))
        for spec in FIELD_SPECS:
            control = self.field_controls[spec.key]
            representation = self._active_representation(path, spec) if record else None
            representations = self._representations(path, spec) if record else []
            target = representation.target if representation else (
                self._proposed_target(path, spec) if path and not representations else None)
            if record:
                state, _details, _sources = field_state(record, spec)
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
                    label = f"New destination: {target.source}" if target else "Not present"
            else:
                state, value, label = "Scanning", "", "Loading…"
            control["state"].setText(label)
            control["details"].setText(f"Other metadata sources ({max(0, len(representations) - (1 if representation else 0))})")
            control["details"].setEnabled(bool(representations))
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
                note = f"Choose Create a new {target.source} value to authorize this destination."
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
                f"Create a new {proposed_target.source} value" if proposed_target else "Create a new value")
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
        record = self.records.get(path) if path else None
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
        record = self.records.get(path) if path else None
        if not record:
            return
        state, details, sources = field_state(record, spec)
        text = details or f"{state}: no stored value"
        text += f"\n\nSources: {sources or 'None'}"
        text += f"\nCanonical targets: {', '.join(intended_targets(spec))}"
        FieldDetailsDialog(spec.label, text, self).exec()

    def batch_edit_selected(self):
        selected = {item.data(Qt.UserRole) for item in self.file_list.selectedItems()}
        paths = [path for path in self.paths if path in selected]
        if len(paths) < 2:
            return
        key = tuple(paths)
        existing = next((session for session in self.batch_sessions
                         if tuple(session["paths"]) == key), None)
        dialog = BatchEditDialog(paths, self.records, existing["fields"] if existing else {}, self,
                                 self.preferences.priority, self.preferences.sync_default)
        if dialog.exec() != QDialog.Accepted:
            return
        fields = dialog.selected_fields()
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
                    record = self.records.get(str(Path(path).resolve(strict=False)))
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

    def _refresh_pending(self):
        if not hasattr(self, "pending_label"):
            return
        if len(self.records) != len(self.paths):
            self.pending_label.setText("Pending changes: reading images…")
            return
        plan = build_plan(self.paths, self.records, self.drafts, "Combined", self.batch_sessions,
                          self.source_drafts, self.preferences.priority)
        valid = sum(row.get("status") == "valid" for row in plan)
        blocked = sum(row.get("status") == "blocked" for row in plan)
        noops = sum(row.get("status") == "noop" for row in plan)
        change_label = "change" if valid == 1 else "changes"
        self.pending_label.setText(
            f"Pending changes: {valid} {change_label}"
            + (f" · {blocked} blocked" if blocked else "")
            + (f" · {noops} no-op" if noops else ""))

    def _scan_complete(self, records, previews):
        self.records.update(records)
        self.previews.update(previews)
        self._image_changed(self.file_list.currentRow())
        self._selection_changed()
        self.statusBar().showMessage("Metadata writing is unavailable in this development phase.")

    def _worker_finished(self):
        if self.close_after_worker:
            self.close_after_worker = False
            self.close()
        elif self.worker:
            self.worker.deleteLater()
            self.worker = None

    def review_changes(self):
        plan = build_plan(self.paths, self.records, self.drafts, "Combined", self.batch_sessions,
                          self.source_drafts, self.preferences.priority)
        ReviewDialog(plan, self, len(self.paths)).exec()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.close_after_worker = True
            self.worker.requestInterruption()
            event.ignore()
            return
        individual_pending = (any(d.operation != "Leave unchanged"
                                  for fields in self.drafts.values() for d in fields.values()) or
                             any(d.operation != "Leave unchanged" for _path, _key, d in self.source_drafts))
        batch_pending = any(session["fields"] for session in self.batch_sessions)
        if individual_pending or batch_pending:
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
