"""Immutable, inspection-only contract for future metadata publication.

M1 never invokes metadata writers, creates outputs or authorizes publication.
The accepted Editor/Review UI remains authoritative for visible drafts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import stat


@dataclass(frozen=True)
class FileIdentity:
    path: str
    device: int
    inode: int
    mode: int
    links: int
    uid: int
    gid: int
    size: int
    atime_ns: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


@dataclass(frozen=True)
class OutputIdentity:
    path: str
    parent: str
    parent_device: int
    parent_inode: int
    expected_absent: bool


@dataclass(frozen=True)
class Target:
    source: str
    source_path: str
    qualified_tag: str
    language: str | None
    entry_keys: tuple[str, ...]
    is_new: bool


@dataclass(frozen=True)
class Change:
    kind: str
    field: str
    operation: str
    value: str
    target: Target | None
    status: str
    reason: str = ""
    synchronization_requested: bool = False
    warnings: tuple[str, ...] = ()
    gps_removed_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageContract:
    source: str
    identity: FileIdentity | None
    sidecars: tuple[FileIdentity, ...]
    output: OutputIdentity | None
    changes: tuple[Change, ...]


@dataclass(frozen=True)
class ExecutionContract:
    images: tuple[ImageContract, ...]
    seal: str
    schema_version: int = 1

    @property
    def publication_authorized(self) -> bool:
        return False

    @property
    def blocked(self) -> bool:
        return any(
            change.status == "blocked"
            for image in self.images
            for change in image.changes
        )


def _stat_key(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_gid, info.st_size,
        info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns,
    )


def _snapshot(path: str | Path) -> FileIdentity:
    """Hash through O_NOATIME and reject changed or unsafe sources."""
    from kim_preview import absolute

    name = absolute(path)
    before = os.lstat(name)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("Source must be an independent regular file")

    noatime = getattr(os, "O_NOATIME", None)
    if noatime is None:
        raise ValueError("O_NOATIME is unavailable")

    flags = (
        os.O_RDONLY | os.O_NOFOLLOW | noatime |
        getattr(os, "O_CLOEXEC", 0)
    )
    fd = os.open(name, flags)
    try:
        if _stat_key(os.fstat(fd)) != _stat_key(before):
            raise ValueError("Source changed before protected inspection")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if (
            _stat_key(os.fstat(fd)) != _stat_key(before)
            or _stat_key(os.lstat(name)) != _stat_key(before)
        ):
            raise ValueError("Source changed during protected inspection")
    finally:
        os.close(fd)

    return FileIdentity(name, *_stat_key(before), digest.hexdigest())


def _sidecar_names(source: str) -> tuple[str, ...]:
    """Enumerate XMP sidecars through a no-atime directory handle."""
    image = Path(source)
    noatime = getattr(os, "O_NOATIME", None)
    if noatime is None:
        raise ValueError("O_NOATIME is unavailable")

    fd = os.open(
        image.parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
        noatime | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(fd)
        with os.scandir(fd) as entries:
            names = [
                str(image.parent / entry.name)
                for entry in entries
                if (
                    Path(entry.name).stem.casefold()
                    == image.stem.casefold()
                    and Path(entry.name).suffix.casefold() == ".xmp"
                )
            ]
        after = os.fstat(fd)
        def directory_key(info):
            return (
                info.st_dev, info.st_ino, info.st_atime_ns,
                info.st_mtime_ns, info.st_ctime_ns,
            )
        if directory_key(before) != directory_key(after):
            raise ValueError("Source directory changed during sidecar scan")
    finally:
        os.close(fd)

    return tuple(sorted(names, key=lambda name: (name.casefold(), name)))


def _output(source: str, directory: str | None) -> OutputIdentity:
    """Freeze a filename and directory identity, without creating either."""
    from kim_metadata_editor import proposed_output

    candidate = proposed_output(source)
    parent = (
        Path(directory) if directory is not None
        else Path(source).parent
    )
    parent = parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("Destination is not a directory")

    target = parent / candidate.name
    info = os.stat(parent)
    return OutputIdentity(
        str(target), str(parent), info.st_dev, info.st_ino,
        not os.path.lexists(target),
    )


def _typed_target(value) -> Target | None:
    if value is None:
        return None
    return Target(
        value.source, value.source_path, value.qualified_tag,
        value.language, tuple(value.entry_keys), bool(value.is_new),
    )


def _description(path, record, spec, draft, priority, conflict="") -> Change:
    from kim_metadata_editor import _targeted_plan_row, detected_file_type
    from kim_metadata_sources import metadata_representations

    target = _typed_target(draft.target)
    errors = [conflict] if conflict else []
    status = "blocked"
    value = draft.value

    if (
        detected_file_type(record) != "JPEG"
        or Path(path).suffix.lower() not in (".jpg", ".jpeg")
    ):
        errors.append(
            "Descriptive writing requires verified JPEG content and extension"
        )
    if record.error:
        errors.append(record.error)

    if target is None:
        errors.append("No explicitly qualified metadata target")
    else:
        if target.source not in ("Embedded XMP", "IPTC-IIM"):
            errors.append("Only embedded XMP and IPTC-IIM are supported")

        expected = (
            spec.xmp if target.source == "Embedded XMP"
            else spec.iim
        )
        if not expected or target.qualified_tag != expected:
            errors.append("Target tag does not match the field mapping")
        if target.source_path != path:
            errors.append("Metadata target is not the selected image")
        if target.source == "IPTC-IIM" and target.language is not None:
            errors.append("IPTC-IIM cannot have an XMP language target")
        if (
            spec.language_alt and target.source == "Embedded XMP"
            and not target.language
        ):
            errors.append("XMP language alternative must be explicit")

        representations = metadata_representations(record, spec)
        matches = [
            item for item in representations
            if item.target.key == draft.target.key
        ]
        occupied = [
            item for item in representations
            if (
                item.source, item.source_path,
                item.canonical_target, item.language
            ) == (
                target.source, target.source_path,
                target.qualified_tag, target.language
            )
        ]

        if target.is_new:
            if occupied:
                errors.append("New destination now exists; review again")
            if not draft.authorize_new_target:
                errors.append("New target requires explicit authorization")
        elif len(matches) != 1:
            errors.append(
                "Existing metadata representation changed or is ambiguous"
            )

        if draft.sync:
            errors.append(
                "IPTC/XMP synchronization requires a qualified counterpart plan"
            )

        if not errors:
            row = _targeted_plan_row(
                path, record, spec, draft, priority
            )
            status = row["status"]
            value = str(row.get("after", value))
            if row.get("warning"):
                errors.append(str(row["warning"]))
                status = "blocked"

    return Change(
        "descriptive", spec.key, draft.operation, value, target,
        status if not errors else "blocked",
        "; ".join(filter(None, errors)),
        bool(draft.sync),
    )


def _gps_change(path: str, proposal) -> Change:
    from kim_location import manual_location, proposal_problem

    reasons = list(proposal.get("blocked", ()))

    if proposal.get("source") != path:
        reasons.append("GPS proposal belongs to a different image")

    problem = proposal_problem(proposal)
    if problem:
        reasons.append(problem)

    expected = proposal.get("status")
    if expected not in ("valid", "noop"):
        reasons.append("GPS proposal has not passed validation")

    proposed = proposal.get("proposed")
    if (
        not isinstance(proposed, dict)
        or proposed.get("category") != "camera"
    ):
        reasons.append("GPS proposal lacks an explicit camera target")
    else:
        try:
            coordinates, altitude, direction = manual_location(
                proposal["input"]
            )
            if (
                proposed.get("position") != coordinates
                or proposed.get("altitude") != altitude
                or proposed.get("direction") != direction
                or proposed.get("direction_ref") != "T"
            ):
                reasons.append("GPS assignment differs from validated input")
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append("Invalid GPS input: " + str(exc))

    value = (
        json.dumps(proposed, sort_keys=True, ensure_ascii=False)
        if proposed else ""
    )
    return Change(
        "gps", "GPS location", "Reconcile embedded camera GPS",
        value,
        Target("Embedded EXIF GPS", path, "GPS camera", None, (), False),
        "blocked" if reasons else expected,
        "; ".join(reasons),
        False,
        tuple(str(note) for note in proposal.get("warnings", ())),
        tuple(str(key) for key in proposal.get("removed_fields", ())),
    )


def _resolve_batch_target(
    path, record, spec, draft, sessions, priority, locale
):
    from kim_metadata_editor import Draft, new_destination
    from kim_metadata_sources import preferred_representation

    session = next(
        (
            item for item in sessions
            if path in item.get("paths", ())
            and item.get("fields", {}).get(spec.key) is draft
        ),
        None,
    )
    if not session:
        return draft

    pins = session.get("targets", {}).get(spec.key, {})
    if path in pins:
        target = pins[path]
    elif draft.batch_preferred_source:
        preferred, alternatives = preferred_representation(
            record, spec, priority, locale
        )
        target = (
            preferred.target if preferred
            else None if alternatives
            else new_destination(path, spec, priority)
        )
    else:
        target = None

    return Draft(
        draft.operation, draft.value, target, draft.sync,
        draft.create_counterpart, draft.authorize_new_target,
        draft.batch_preferred_source,
    )


def _seal(images):
    payload = json.dumps(
        [asdict(item) for item in images],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_execution_contract(
    paths, records, drafts, batch_sessions=(),
    source_drafts=(), gps_drafts=None, priority=(),
    destination_directory=None, locale=""
) -> ExecutionContract:
    """Build a non-executable snapshot from current in-memory drafts."""
    from kim_metadata_editor import FIELD_SPECS, _plan_draft
    from kim_metadata_reader import MetadataRecord
    from kim_preview import absolute

    gps_drafts = gps_drafts or {}
    images = []

    for item in dict.fromkeys(paths):
        path = absolute(item)
        issues = []
        identity = None
        sidecars = ()
        output = None

        try:
            identity = _snapshot(path)
            sidecars = tuple(
                _snapshot(name) for name in _sidecar_names(path)
            )
        except (OSError, ValueError) as exc:
            issues.append("Source/sidecar blocked: " + str(exc))

        record = records.get(
            path, MetadataRecord(path, error="Metadata scan is incomplete")
        )
        changes = []

        for spec in FIELD_SPECS:
            draft, conflict = _plan_draft(
                path, spec, drafts, "Combined", batch_sessions
            )
            selected = []
            if draft.operation != "Leave unchanged":
                selected.append((
                    _resolve_batch_target(
                        path, record, spec, draft, batch_sessions,
                        priority, locale,
                    ),
                    conflict,
                ))

            selected.extend(
                (other, "")
                for source, field, other in source_drafts
                if source == path and field == spec.key
                and other.operation != "Leave unchanged"
            )
            for proposed, problem in selected:
                changes.append(_description(
                    path, record, spec, proposed, priority, problem
                ))

        if path in gps_drafts:
            changes.append(_gps_change(path, gps_drafts[path]))

        counts = {}
        for change in changes:
            if change.target and change.kind == "descriptive":
                counts[change.target] = counts.get(change.target, 0) + 1

        changes = [
            replace(
                change, status="blocked",
                reason="Duplicate writes to one metadata target",
            )
            if change.target and counts.get(change.target, 0) > 1
            else change
            for change in changes
        ]

        if any(change.status == "valid" for change in changes):
            try:
                output = _output(path, destination_directory)
                if not output.expected_absent:
                    issues.append("Planned output filename is occupied")
            except (OSError, ValueError) as exc:
                issues.append("Destination blocked: " + str(exc))

        if issues:
            changes.append(Change(
                "safety", "Image and destination", "Block publication",
                "", None, "blocked", "; ".join(issues),
            ))

        images.append(ImageContract(
            path, identity, sidecars, output, tuple(changes)
        ))

    destinations = {}
    for image in images:
        if image.output is not None:
            destinations[image.output.path] = (
                destinations.get(image.output.path, 0) + 1
            )

    unique_images = []
    for image in images:
        if image.output and destinations[image.output.path] > 1:
            image = replace(
                image,
                changes=image.changes + (
                    Change(
                        "safety", "Output destination",
                        "Block publication", "", None, "blocked",
                        "Multiple images would share an output filename",
                    ),
                ),
            )
        unique_images.append(image)

    frozen = tuple(unique_images)
    return ExecutionContract(frozen, _seal(frozen))


def verify_execution_contract(plan: ExecutionContract) -> None:
    """Recheck a snapshot without ever invoking a publisher."""
    if plan.schema_version != 1:
        raise ValueError("Unsupported execution contract version")
    if plan.seal != _seal(plan.images):
        raise ValueError("Execution contract changed after review")
    if plan.blocked:
        raise ValueError("Execution contract contains blocked operations")
    if not any(
        change.status == "valid"
        for image in plan.images
        for change in image.changes
    ):
        raise ValueError("Execution contract has no changes to publish")

    for image in plan.images:
        if (
            image.identity is None
            or _snapshot(image.source) != image.identity
        ):
            raise ValueError("Image changed after review")

        current_sidecars = tuple(
            _snapshot(name) for name in _sidecar_names(image.source)
        )
        if current_sidecars != image.sidecars:
            raise ValueError("Sidecar or membership changed after review")

        if image.output is not None:
            info = os.stat(image.output.parent)
            if (
                info.st_dev, info.st_ino
            ) != (
                image.output.parent_device,
                image.output.parent_inode,
            ):
                raise ValueError("Output directory changed after review")
            if os.path.lexists(image.output.path):
                raise ValueError("Approved output filename is now occupied")
