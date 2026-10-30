#!/usr/bin/env python3
"""Run K01 infrastructure checks: python3 -B tests/run.py [--pattern GLOB]."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py")
    options = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parent), pattern=options.pattern
    )
    if suite.countTestCases() == 0:
        print("No tests matched " + options.pattern, file=sys.stderr)
        return 2
    # KIM6_NONINTERACTIVE_TEST_RUNNER
    # Never permit a test to open an actual desktop dialog.
    # Tests with their own isolated tool adapters retain those adapters.
    with tempfile.TemporaryDirectory(
        prefix="kim6-test-no-gui-"
    ) as temporary:
        shims = Path(temporary)

        for tool in (
            "kdialog",
            "zenity",
            "yad",
            "qarma",
        ):
            executable = shims / tool
            executable.write_text(
                "#!/bin/sh\n"
                "printf '%s\n' "
                "'KIM6 TEST: unexpected GUI request refused' >&2\n"
                "exit 1\n"
            )
            executable.chmod(0o700)

        previous = {
            name: os.environ.get(name)
            for name in (
                "PATH",
                "DISPLAY",
                "WAYLAND_DISPLAY",
                "QT_QPA_PLATFORM",
            )
        }

        try:
            os.environ["PATH"] = (
                str(shims) + os.pathsep
                + os.environ.get("PATH", "")
            )
            os.environ.pop("DISPLAY", None)
            os.environ.pop("WAYLAND_DISPLAY", None)
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

            print(
                "KIM6 TEST MODE: desktop dialogs disabled",
                file=sys.stderr,
                flush=True,
            )

            result = unittest.TextTestRunner(
                verbosity=2
            ).run(suite)

        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
