#!/usr/bin/env python3
"""Run K01 infrastructure checks: python3 -B tests/run.py [--pattern GLOB]."""
import argparse
from pathlib import Path
import sys
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
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
