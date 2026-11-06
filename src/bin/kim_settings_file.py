"""Bounded, literal Settings text reads without Qt or shell evaluation."""
import os
import stat

MAX_SETTINGS_BYTES = 1024 * 1024


def read_settings(path):
    """Return ordered literal key/value pairs; only a missing path means empty Settings.

    Open without following the final symlink and without waiting for a FIFO.
    Validate the opened descriptor, not a prior pathname observation. Atomic
    replacement leaves this read on one complete inode; the next read sees the
    replacement. Concurrent in-place mutation is rejected where observable.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return []
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('KIM6 Settings must be a regular file')
        if before.st_size > MAX_SETTINGS_BYTES:
            raise ValueError('KIM6 Settings file exceeds size limit')
        chunks = []
        remaining = MAX_SETTINGS_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b''.join(chunks)
        if len(payload) > MAX_SETTINGS_BYTES:
            raise ValueError('KIM6 Settings file exceeds size limit')
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('KIM6 Settings changed while reading; retry')
    finally:
        os.close(fd)
    try:
        content = payload.decode('utf-8')
    except UnicodeError as exc:
        raise ValueError('KIM6 Settings must be UTF-8 text') from exc
    if '\0' in content:
        raise ValueError('KIM6 Settings must not contain NUL bytes')
    return [tuple(line.split('=', 1)) for line in content.splitlines()
            if line and not line.startswith('#') and '=' in line]
