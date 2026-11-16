"""Read-only, structured metadata access for the standalone KIM6 browser.

ExifTool's JSON output is kept as typed Python values. Entries retain the
group-qualified name, tag identifier, source file and duplicate instance so
callers can inspect conflicts without flattening the metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from typing import Any, Iterable

from kim_process import run_process


@dataclass(frozen=True)
class MetadataEntry:
    name: str
    groups: tuple[str, ...]
    tag_id: str | int | None
    value: Any
    source: str
    qualified_name: str
    language: str | None = None

    @property
    def group(self) -> str:
        return ":".join(self.groups) or "Unknown"


@dataclass
class MetadataRecord:
    path: str
    entries: list[MetadataEntry] = field(default_factory=list)
    sidecars: list[str] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def values_for(self, *names: str) -> list[MetadataEntry]:
        wanted = {name.casefold() for name in names}
        return [entry for entry in self.entries if entry.name.casefold() in wanted]


class MetadataReadError(RuntimeError):
    """ExifTool was unavailable or returned an unusable response."""


_LOGICAL_FIELDS = {
    "title": ("Title", "ObjectName"),
    "description": ("Description", "Caption-Abstract", "ImageDescription"),
    "keywords": ("Subject", "Keywords"),
    "creator": ("Creator", "By-line", "Artist"),
    "copyright": ("Rights", "CopyrightNotice", "Copyright"),
    "usageterms": ("UsageTerms", "RightsUsageTerms"),
}


@dataclass(frozen=True)
class _FieldSelection:
    logical_names: frozenset[str]
    qualified: tuple[tuple[str, ...], ...]
    arguments: tuple[str, ...]

    def includes(self, entry: MetadataEntry) -> bool:
        identity = entry.qualified_name.casefold()
        tag = identity.rsplit(":", 1)[-1]
        if entry.name.casefold() in self.logical_names or tag in self.logical_names:
            return True
        groups = tuple(group.casefold() for group in entry.groups)
        for parts in self.qualified:
            if tag != parts[-1]:
                continue
            if len(parts) == 2:
                if parts[0] == "all" or parts[0] in groups:
                    return True
            elif identity == ":".join(parts):
                return True
        return False


def _select_fields(fields: Iterable[str] | None) -> _FieldSelection | None:
    if fields is None:
        return None
    if isinstance(fields, (str, bytes)):
        raise ValueError("fields must be an iterable of field names, not a string")
    try:
        requested = iter(fields)
    except TypeError as exc:
        raise ValueError("fields must be an iterable of field names") from exc
    logical = set()
    qualified = []
    arguments = []
    for index, name in enumerate(requested):
        if index >= 64:
            raise ValueError("At most 64 metadata fields may be requested")
        if (not isinstance(name, str) or len(name) > 256 or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*(?::[A-Za-z0-9][A-Za-z0-9_-]*){0,7}", name)
                or name.rsplit(":", 1)[-1].casefold() == "all"):
            raise ValueError("Invalid metadata field selection: use ASCII tag/group names, "
                             "without options, wildcards or assignments (at most 256 characters)")
        parts = tuple(name.split(":"))
        if len(parts) == 1:
            aliases = _LOGICAL_FIELDS.get(name.casefold(), (name,))
            logical.update(alias.casefold() for alias in aliases)
            tags = [f"all:{alias}" for alias in aliases]
        else:
            qualified.append(tuple(part.casefold() for part in parts))
            tags = [name]
        for tag in tags:
            # Always use qualified tag arguments, so even names such as "r"
            # cannot become ExifTool options. Only this code supplies wildcards.
            arguments.extend((f"-{tag}", f"-{tag}-*"))
    if not arguments:
        raise ValueError("Request at least one metadata field; use None for complete extraction")
    unique_arguments = {}
    for argument in arguments:
        unique_arguments.setdefault(argument.casefold(), argument)
    return _FieldSelection(frozenset(logical), tuple(qualified), tuple(unique_arguments.values()))


def _tag_parts(key: str) -> tuple[tuple[str, ...], str]:
    # -G0:1:2:4 adds available group families before the tag name.
    parts = key.split(":")
    return tuple(parts[:-1]), parts[-1]


def _entry(key: str, value: Any, source: str) -> MetadataEntry:
    groups, name = _tag_parts(key)
    tag_id = None
    language = None
    if isinstance(value, dict) and "val" in value and "id" in value:
        tag_id = value["id"]
        language = value.get("lang")
        value = value["val"]
    if language and name.casefold().endswith("-" + str(language).casefold()):
        name = name[:-(len(str(language)) + 1)]
    return MetadataEntry(name, groups, tag_id, value, source, key, language)


def parse_exiftool_json(payload: str | bytes, requested: Iterable[str] = (),
                        source_aliases: dict[str, str] | None = None) -> dict[str, MetadataRecord]:
    """Parse ExifTool JSON without losing array, structure or duplicate rows."""
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="strict")
        documents = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetadataReadError(f"ExifTool returned invalid JSON: {exc}") from exc
    if not isinstance(documents, list):
        raise MetadataReadError("ExifTool returned an unexpected JSON structure")

    records: dict[str, MetadataRecord] = {}
    aliases: dict[str, str] = {}
    for filename in requested:
        absolute = str(Path(filename).resolve(strict=False))
        records[absolute] = MetadataRecord(path=absolute)
        aliases[filename] = absolute
        aliases[absolute] = absolute

    for document in documents:
        if not isinstance(document, dict):
            continue
        source_value = document.get("SourceFile")
        source = str(source_value) if source_value is not None else ""
        record_key = (aliases.get(source) or (source_aliases or {}).get(source)
                      or (str(Path(source).resolve(strict=False)) if source else ""))
        if not record_key:
            continue
        record = records.setdefault(record_key, MetadataRecord(path=record_key))
        for key, value in document.items():
            if key == "SourceFile":
                continue
            entry = _entry(str(key), value, record_key)
            if entry.name.casefold() == "filename":
                entry = replace(entry, value=Path(record_key).name)
            elif entry.name.casefold() == "directory":
                entry = replace(entry, value=str(Path(record_key).parent))
            if entry.name.casefold() == "error":
                record.error = _readable(entry.value)
            elif entry.name.casefold() == "warning":
                record.warnings.append(_readable(entry.value))
            else:
                record.entries.append(entry)
    # ExifTool emits non-default lang-alt values with a language suffix and a
    # `lang` member. The unsuffixed value is x-default when such siblings exist.
    alternate_keys = {(entry.source, entry.groups, entry.name.casefold())
                      for record in records.values() for entry in record.entries if entry.language}
    for record in records.values():
        record.entries = [replace(entry, language="x-default")
                          if entry.language is None and
                          (entry.source, entry.groups, entry.name.casefold()) in alternate_keys
                          else entry for entry in record.entries]
    return records


def _readable(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def associated_xmp_sidecars(filename: str | Path) -> list[Path]:
    """Return adjacent same-stem XMP sidecars without following directories."""
    image = Path(filename)
    if not image.parent.is_dir():
        return []
    try:
        candidates = [p for p in image.parent.iterdir()
                      if p.resolve(strict=False) != image.resolve(strict=False)
                      and p.is_file() and p.stem.casefold() == image.stem.casefold()
                      and p.suffix.casefold() == ".xmp"]
    except OSError:
        return []
    return sorted(candidates, key=lambda p: p.name.casefold())


def _source_path(path: str | Path) -> str:
    # Canonicalize the parent, but let O_NOFOLLOW reject a final symlink.
    source = Path(os.path.abspath(path))
    return str(source.parent.resolve(strict=False) / source.name)


def _source_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_uid, info.st_gid, info.st_size,
            info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns)


def read_metadata(paths: Iterable[str | Path], *, executable: str = "exiftool",
                  timeout: float = 120.0,
                  fields: Iterable[str] | None = None) -> dict[str, MetadataRecord]:
    """Read images and adjacent XMP sidecars through inherited no-atime stdin.

    No binary extraction option is used. ExifTool therefore reports binary
    blocks as bounded descriptions instead of returning embedded thumbnails,
    previews or full image data. No write option is ever passed.

    fields=None preserves complete extraction. A nonempty iterable of at most
    64 ASCII tag names selects their logical properties, including languages.
    Title, Description, Keywords, Creator, Copyright and UsageTerms also include
    their source-specific aliases. GROUP:Tag selects that exact tag in a group;
    longer qualified names must match MetadataEntry.qualified_name exactly.
    Qualified requests do not expand aliases or return other languages.
    Absent or unsupported names return no entries, without a read error.
    Diagnostics remain in error/warnings. Empty or malformed selections raise
    ValueError before any input is opened. Tag selectors contain no wildcards.
    Names are limited to 256 characters and eight colon-separated components.
    Scoped entry order may follow ExifTool's requested-tag order.
    """
    selection = _select_fields(fields)
    images = [_source_path(path) for path in paths]
    if not images:
        return {}
    tool = shutil.which(executable) if "/" not in executable else executable
    if not tool:
        raise MetadataReadError("ExifTool is required to inspect image metadata. Install ExifTool and try again.")

    sidecars_by_image: dict[str, list[str]] = {}
    inputs: list[str] = []
    seen: set[str] = set()
    for image in images:
        sidecars = [_source_path(path) for path in associated_xmp_sidecars(image)]
        sidecars_by_image[image] = sidecars
        for candidate in (image, *sidecars):
            if candidate not in seen:
                seen.add(candidate)
                inputs.append(candidate)

    noatime = getattr(os, "O_NOATIME", None)
    if noatime is None:
        raise MetadataReadError("This system cannot inspect images without changing their access timestamps.")

    # Opening /proc/self/fd/N creates a new open file description and drops
    # O_NOATIME. ExifTool's supported '-' input duplicates inherited stdin
    # instead. Each input needs its own invocation; share the timeout budget.
    tags = ("-all:all", "-XMP:*") if selection is None else (*selection.arguments, "-Error", "-Warning")
    command = [tool, "-j", "-a", "-u", "-G0:1:2:4", "-D", "-struct",
               "-charset", "filename=UTF8", *tags, "--", "-"]
    deadline = time.monotonic() + timeout
    records: dict[str, MetadataRecord] = {}
    input_errors: dict[str, str] = {}
    for filename in inputs:
        descriptor = None
        try:
            try:
                before = os.stat(filename, follow_symlinks=False)
                if not stat.S_ISREG(before.st_mode):
                    raise OSError("Select a regular file, not a symbolic link or special file.")
                expected = _source_identity(before)
                descriptor = os.open(filename, os.O_RDONLY | noatime | os.O_NOFOLLOW |
                                     os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
                if _source_identity(os.fstat(descriptor)) != expected:
                    raise OSError("Source changed while opening metadata input.")
            except OSError as exc:
                input_errors[filename] = (
                    f"Cannot inspect {Path(filename).name} without risking a filesystem timestamp change: {exc}"
                )
                continue

            # -a/-G4 preserve duplicate identities, -D supplies tag IDs, -struct
            # retains arrays/structures, and -XMP:* retrieves lang-alt values.
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                completed = run_process(command, timeout=remaining, stdin=descriptor)
            except subprocess.TimeoutExpired as exc:
                raise MetadataReadError("ExifTool took too long to inspect the selected images.") from exc
            except (OSError, ValueError) as exc:
                raise MetadataReadError(f"Could not start ExifTool: {exc}") from exc
            try:
                if (_source_identity(os.fstat(descriptor)) != expected or
                        _source_identity(os.stat(filename, follow_symlinks=False)) != expected):
                    raise OSError("Source changed while extracting metadata.")
            except OSError as exc:
                input_errors[filename] = str(exc)
                continue
        finally:
            if descriptor is not None:
                os.close(descriptor)

        if not completed.stdout:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise MetadataReadError(detail or "ExifTool returned no metadata.")
        record = parse_exiftool_json(completed.stdout, [filename], {"-": filename})[filename]
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        if not record.entries and not record.error and (selection is None or completed.returncode):
            record.error = detail or "ExifTool could not read this image."
        if record.entries or (selection is not None and not record.error):
            # Stdin supplies the same stat and embedded metadata, but omits
            # these two pathname tags. Preserve their normal group provenance.
            for name, value in (("FileName", Path(filename).name),
                                ("Directory", str(Path(filename).parent))):
                if not any(entry.name == name and entry.groups == ("File", "System", "Other")
                           for entry in record.entries):
                    record.entries.append(MetadataEntry(name, ("File", "System", "Other"), name,
                                                        value, filename, f"File:System:Other:{name}"))
        if selection is not None:
            record.entries = [entry for entry in record.entries if selection.includes(entry)]
        # Keep partial ExifTool results and attach diagnostics to this input.
        if completed.returncode and detail:
            detail = "\n".join(line for line in detail.splitlines()
                               if not re.fullmatch(r"\s*\d+ image files? read\s*", line)).strip()
            if not record.entries and not record.error:
                record.error = detail or f"ExifTool reported an inspection error (exit {completed.returncode})."
            elif detail and detail not in record.warnings:
                record.warnings.append(f"ExifTool batch warning: {detail}")
        records[filename] = record

    for image in images:
        record = records.setdefault(image, MetadataRecord(path=image))
        record.sidecars = sidecars_by_image[image]
        if image in input_errors:
            record.error = input_errors[image]
        elif not record.entries and not record.error and selection is None:
            record.error = "ExifTool could not read this image."
        for sidecar in record.sidecars:
            if sidecar in input_errors:
                record.warnings.append(input_errors[sidecar])
            sidecar_record = records.get(sidecar)
            if sidecar_record:
                record.entries.extend(sidecar_record.entries)
                record.warnings.extend(sidecar_record.warnings)
                if sidecar_record.error:
                    record.warnings.append(f"{Path(sidecar).name}: {sidecar_record.error}")
    return {image: records[image] for image in images}


def value_text(value: Any) -> str:
    """Return a Unicode-preserving readable value for tables and clipboard."""
    return _readable(value)
