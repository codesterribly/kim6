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
import subprocess
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


def read_metadata(paths: Iterable[str | Path], *, executable: str = "exiftool",
                  timeout: float = 120.0) -> dict[str, MetadataRecord]:
    """Read selected images and adjacent XMP sidecars using one ExifTool run.

    No binary extraction option is used. ExifTool therefore reports binary
    blocks as bounded descriptions instead of returning embedded thumbnails,
    previews or full image data. No write option is ever passed.
    """
    images = [str(Path(path).resolve(strict=False)) for path in paths]
    if not images:
        return {}
    tool = shutil.which(executable) if "/" not in executable else executable
    if not tool:
        raise MetadataReadError("ExifTool is required to inspect image metadata. Install ExifTool and try again.")

    sidecars_by_image: dict[str, list[str]] = {}
    inputs: list[str] = []
    seen: set[str] = set()
    for image in images:
        sidecars = [str(path.resolve(strict=False)) for path in associated_xmp_sidecars(image)]
        sidecars_by_image[image] = sidecars
        for candidate in (image, *sidecars):
            if candidate not in seen:
                seen.add(candidate)
                inputs.append(candidate)

    noatime = getattr(os, "O_NOATIME", None)
    if noatime is None:
        raise MetadataReadError("This system cannot inspect images without changing their access timestamps.")

    descriptors: list[int] = []
    fd_inputs: list[str] = []
    fd_aliases: dict[str, str] = {}
    input_errors: dict[str, str] = {}
    try:
        for filename in inputs:
            try:
                descriptor = os.open(filename, os.O_RDONLY | noatime | getattr(os, "O_CLOEXEC", 0))
            except OSError as exc:
                input_errors[filename] = (
                    f"Cannot inspect {Path(filename).name} without risking a filesystem timestamp change: {exc}"
                )
                continue
            descriptors.append(descriptor)
            descriptor_path = f"/proc/self/fd/{descriptor}"
            fd_inputs.append(descriptor_path)
            fd_aliases[descriptor_path] = filename

        if not descriptors:
            records = {image: MetadataRecord(path=image) for image in images}
            for image in images:
                record = records[image]
                record.error = input_errors.get(image, "No image or sidecar could be opened safely.")
                record.sidecars = sidecars_by_image[image]
                for sidecar in record.sidecars:
                    if sidecar in input_errors:
                        record.warnings.append(input_errors[sidecar])
            return records

        # -a/-G4 preserve duplicate identities, -D supplies tag IDs, -struct
        # retains arrays/structures, and -XMP:* retrieves every lang-alt value.
        # O_NOATIME descriptors keep the read itself from changing source times.
        command = [tool, "-j", "-a", "-u", "-G0:1:2:4", "-D", "-struct",
                   "-charset", "filename=UTF8", "-all:all", "-XMP:*", "--", *fd_inputs]
        try:
            completed = run_process(command, timeout=timeout, pass_fds=tuple(descriptors))
        except subprocess.TimeoutExpired as exc:
            raise MetadataReadError("ExifTool took too long to inspect the selected images.") from exc
        except (OSError, ValueError) as exc:
            raise MetadataReadError(f"Could not start ExifTool: {exc}") from exc
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
    if not completed.stdout:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise MetadataReadError(detail or "ExifTool returned no metadata.")
    records = parse_exiftool_json(completed.stdout, inputs, fd_aliases)
    for image in images:
        record = records.setdefault(image, MetadataRecord(path=image))
        record.sidecars = sidecars_by_image[image]
        if image in input_errors:
            record.error = input_errors[image]
        elif not record.entries and not record.error:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            record.error = detail or "ExifTool could not read this image."
        for sidecar in record.sidecars:
            if sidecar in input_errors:
                record.warnings.append(input_errors[sidecar])
            sidecar_record = records.get(sidecar)
            if sidecar_record:
                record.entries.extend(sidecar_record.entries)
                record.warnings.extend(sidecar_record.warnings)
                if sidecar_record.error:
                    record.warnings.append(f"{Path(sidecar).name}: {sidecar_record.error}")
    # ExifTool may return valid records alongside a non-zero status. Keep those
    # records and expose a concise per-image failure wherever no data arrived.
    if completed.returncode and completed.stderr:
        diagnostics = completed.stderr.decode("utf-8", errors="replace").splitlines()
        diagnostics = [line for line in diagnostics
                       if not re.fullmatch(r"\s*\d+ image files? read\s*", line, re.IGNORECASE)]
        detail = "\n".join(diagnostics).strip()
        for image in images:
            record = records[image]
            if not record.entries and not record.error:
                record.error = detail or f"ExifTool reported an inspection error (exit {completed.returncode})."
            elif detail and detail not in record.warnings:
                record.warnings.append(f"ExifTool batch warning: {detail}")
    return {image: records[image] for image in images}


def value_text(value: Any) -> str:
    """Return a Unicode-preserving readable value for tables and clipboard."""
    return _readable(value)
