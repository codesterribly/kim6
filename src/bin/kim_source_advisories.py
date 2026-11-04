"""Read-only source preflight and job-scoped approval of exact advisories.

Only the PSD compatibility policy is predictable before decoding. All other
source diagnostics remain processing results, even when they mention PSD.
"""
import json
import os
from pathlib import Path
import stat
import tempfile

from kim_psd_source import header, PSDError, WARNING

ACKNOWLEDGMENTS = 'approved-advisories.json'


def source_identity(path):
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Source is not an independent regular file')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def source_advisories(paths, cache=None):
    """Inspect at most 26 bytes per changed source; never decode or run tools.

    Invalid/unreadable inputs get no advisory approval. The existing source
    validators still decide eligibility and report their errors.
    """
    cache = cache if cache is not None else {}
    result = []
    selected = set()
    for path in paths:
        # Canonicalize parent aliases without following a final-entry symlink.
        path = Path(os.path.abspath(path))
        source = str(path.parent.resolve() / path.name)
        selected.add(source)
        try:
            stamp = source_identity(source)
            previous = cache.get(source)
            if previous is not None and previous[0] == stamp:
                record = previous[1]
            else:
                record = None
                if header(source) is not None and source_identity(source) == stamp:
                    record = dict(source=source, identity=stamp, warning=WARNING)
                cache[source] = (stamp, record)
            if record is not None:
                result.append(record)
        except (OSError, ValueError, PSDError):
            cache.pop(source, None)
    for source in list(cache):
        if source not in selected:
            del cache[source]
    return result


def acknowledge_advisories(records):
    """Called only by Create; no configured job means no persistent approval."""
    directory = os.environ.get('KIM_SOURCE_ADVISORY_DIR')
    if not directory:
        return
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.advisories-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(records, stream)
        os.replace(temporary, directory / ACKNOWLEDGMENTS)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def undisclosed_warning_rows(directory, rows):
    """Filter successful presentation only; retain original diagnostic records.

    Require agreement between approval, processing-time identity and the source
    now. Old/partial fingerprints and unreadable approval data fail open to UI.
    """
    from types import SimpleNamespace
    try:
        approved = json.loads((Path(directory) / ACKNOWLEDGMENTS).read_text())
        if not isinstance(approved, list):
            return rows
        keys = {(entry['source'], tuple(entry['identity']), entry['warning'])
                for entry in approved
                if isinstance(entry, dict) and entry.get('warning') == WARNING
                and isinstance(entry.get('source'), str)
                and isinstance(entry.get('identity'), list) and len(entry['identity']) == 5}
    except (OSError, ValueError, KeyError, TypeError):
        return rows
    result = []
    for row in rows:
        stamp = getattr(row, 'identity', None)
        try:
            source = os.path.realpath(row.source)
            current = source_identity(row.source)
            matches = (isinstance(stamp, list) and len(stamp) == 5 and stamp == current
                       and (source, tuple(stamp), WARNING) in keys)
        except (OSError, ValueError):
            matches = False
        warnings = [warning for warning in row.warnings
                    if warning != WARNING or not matches]
        if warnings:
            result.append(SimpleNamespace(source=row.source, identity=stamp, warnings=warnings))
    return result
