"""Headless tool execution, context-local cancellation/progress and diagnostics.

The shell job adapter owns its group; library/Qt callers own each tool group.
Codec decoding and profile decisions belong to their format-specific modules.
"""
import contextlib
import contextvars
import os
from pathlib import Path
import re
import signal
import subprocess
import time


class ProcessError(ValueError):
    pass


_PROGRESS = contextvars.ContextVar('kim_image_progress', default=None)
_CANCELLED = contextvars.ContextVar('kim_image_cancelled', default=None)
_WARNINGS = contextvars.ContextVar('kim_image_warnings', default=None)
_SHELL_GROUP = contextvars.ContextVar('kim_shell_process_group', default=False)
DIGEST_WARNING = ('Photoshop staging reported a stale IPTC digest; this does not establish conflicting IPTC/XMP values. '
                  'KIM6 has not synchronized or repaired these fields. Metadata is kept unless a removal step is selected.')


@contextlib.contextmanager
def inspection_context(progress=None, cancelled=None):
    tokens = (_PROGRESS.set(progress), _CANCELLED.set(cancelled))
    try:
        yield
    finally:
        _CANCELLED.reset(tokens[1]); _PROGRESS.reset(tokens[0])


def cancelled():
    callback = _CANCELLED.get()
    return bool(callback and callback())


def checkpoint():
    if cancelled(): raise ProcessError('Image processing cancelled')


def stage(message):
    checkpoint()
    callback = _PROGRESS.get()
    if callback: callback(message)
    elif os.environ.get('KIM_JOB_STAGE'): Path(os.environ['KIM_JOB_STAGE']).write_text(message)


def run_process(args, timeout=150, **kwargs):
    """Own delegates too; cancellation reaps the group before workspace cleanup."""
    own_group = not _SHELL_GROUP.get()
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=own_group, **kwargs)
    started = time.monotonic()
    try:
        while True:
            callback = _CANCELLED.get()
            if callback and callback(): raise ProcessError('Image processing cancelled')
            if time.monotonic() - started > timeout: raise subprocess.TimeoutExpired(args, timeout)
            try:
                stdout, stderr = process.communicate(timeout=.1)
                return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        try:
            if own_group: os.killpg(process.pid, signal.SIGTERM)
            else: process.terminate()
        except ProcessLookupError: pass
        try: process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                if own_group: os.killpg(process.pid, signal.SIGKILL)
                else: process.kill()
            except ProcessLookupError: pass
            process.communicate()
        raise


def metadata_diagnostics(args, status, diagnostics):
    """Whitelist one successful ExifTool advisory, never a failed write or ICC warning.

    A stale Photoshop digest is not evidence that either metadata block is wrong.
    In particular, do not use -m or write a new digest to conceal that uncertainty.
    """
    if args[0] != 'exiftool' or status:
        return diagnostics
    remaining = []
    for line in diagnostics.splitlines():
        if re.fullmatch(r'Warning: IPTCDigest is not current\. XMP may be out of sync - .+', line):
            warnings = _WARNINGS.get()
            if warnings is not None:
                if DIGEST_WARNING not in warnings: warnings.append(DIGEST_WARNING)
                exact='IPTCDigest staging diagnostic: '+line
                if exact not in warnings: warnings.append(exact)
        else:
            remaining.append(line)
    return '\n'.join(remaining)


def session_warnings():
    return list(_WARNINGS.get() or [])


@contextlib.contextmanager
def warning_context():
    token = _WARNINGS.set([])
    try:
        yield
    finally:
        _WARNINGS.reset(token)


def add_warning(warning):
    warnings = _WARNINGS.get()
    if warnings is not None and warning not in warnings:
        warnings.append(warning)


def record_warnings(directory, source, identity, warnings):
    """Append source-attributed diagnostics; presentation groups categories later."""
    if not os.environ.get('KIM_PSD_CACHE'): return
    import json
    source=os.path.realpath(source)
    # stdin snapshots resolve back to the selected file on Linux. Never use the
    # derived TIFF/JPEG name as an additional affected source.
    with (Path(directory)/'warnings.jsonl').open('a') as log:
        for warning in warnings:
            log.write(json.dumps({'source':source,'identity':list(identity),'warning':warning})+'\n')
