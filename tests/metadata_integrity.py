"""Non-mutating checksum reads for metadata timestamp integrity tests."""
import hashlib
import os


def sha256_noatime(path):
    """Hash owned test fixtures without changing the timestamps under test.

    Fail if O_NOATIME cannot be used; an ordinary-read fallback would interfere
    with the integrity assertions.
    """
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOATIME), "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()
