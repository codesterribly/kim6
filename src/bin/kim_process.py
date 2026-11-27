"""Headless tool execution, context-local cancellation/progress and diagnostics.

The shell job adapter owns its group; library/Qt callers own each tool group.
Codec decoding and profile decisions belong to their format-specific modules.
"""
import contextlib
import contextvars
import os
from pathlib import Path
import re
import stat
import signal
import subprocess
import sys
import time


class ProcessError(ValueError):
    pass


_PROGRESS = contextvars.ContextVar('kim_image_progress', default=None)
_CANCELLED = contextvars.ContextVar('kim_image_cancelled', default=None)
_WARNINGS = contextvars.ContextVar('kim_image_warnings', default=None)
_SHELL_GROUP = contextvars.ContextVar('kim_shell_process_group', default=False)
DIGEST_WARNING = ('Photoshop staging reported a stale IPTC digest; this does not establish conflicting IPTC/XMP values. '
                  'KIMng has not synchronized or repaired these fields. Metadata is kept unless a removal step is selected.')


@contextlib.contextmanager
def inspection_context(progress=None, cancelled=None):
    tokens = (_PROGRESS.set(progress), _CANCELLED.set(cancelled))
    try:
        yield
    finally:
        _CANCELLED.reset(tokens[1]); _PROGRESS.reset(tokens[0])


def open_inspection_fd(path):
    """Caller owns a regular-file descriptor that can be passed directly as stdin."""
    noatime = getattr(os, 'O_NOATIME', None)
    if noatime is None:
        raise OSError('Protected source inspection is unavailable on this system')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | noatime)
    except PermissionError as exc:
        raise PermissionError(f'Cannot inspect {path} without changing its access time') from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f'Expected a regular inspection source: {path}')
    except BaseException:
        os.close(fd)
        raise
    return fd


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


def _has_apng_control_chunk_fd(fd):
    """Walk PNG chunk boundaries on an already-opened protected descriptor."""
    with os.fdopen(fd, 'rb') as stream:
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            return False
        filesize = os.fstat(stream.fileno()).st_size
        offset = 8
        while offset + 12 <= filesize:
            header = stream.read(8)
            if len(header) != 8:
                return False
            length = int.from_bytes(header[:4], 'big')
            tag = header[4:8]
            if length > filesize - offset - 12:
                return False
            if tag == b'acTL':
                return length == 8
            if tag in (b'IDAT', b'IEND'):
                return False
            offset += length + 12
            stream.seek(offset, os.SEEK_SET)
    return False


def _cli(argv):
    """Protected-read shell bridge reusing open_inspection_fd (fail closed)."""
    if len(argv) < 2:
        return 2
    mode, source = argv[0], argv[1]
    try:
        fd = open_inspection_fd(source)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 125
    if mode == 'is-psd':
        try:
            sig = os.pread(fd, 4, 0)
        finally:
            os.close(fd)
        return 0 if sig == b'8BPS' else 1
    if mode == 'has-apng':
        return 0 if _has_apng_control_chunk_fd(fd) else 1
    if mode == 'run-stdin':
        if len(argv) < 4 or argv[2] != '--':
            os.close(fd)
            return 2
        cmd = argv[3:]
        try:
            os.dup2(fd, 0)
            os.set_inheritable(0, True)
        finally:
            if fd != 0:
                os.close(fd)
        os.execvp(cmd[0], cmd)
    os.close(fd)
    return 2


if __name__ == '__main__':
    raise SystemExit(_cli(sys.argv[1:]))
