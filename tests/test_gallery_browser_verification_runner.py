"""Classification tests for the repeatable gallery verification runner."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from run_gallery_verification import (  # noqa: E402
    REQUIRED_SCREENSHOTS,
    classify_browser_result,
    validate_screenshot,
)


class BrowserResultClassificationTests(unittest.TestCase):
    def test_browser_pass_requires_a_run_test_and_no_skip(self):
        self.assertEqual(classify_browser_result(
            0, "Ran 1 test in 2.0s\n\nOK\n"), "PASSED")
        self.assertEqual(classify_browser_result(
            0, "Ran 1 test in 0.5s\n\nOK (skipped=1)\n"),
            "INCOMPLETE_DEPENDENCY")

    def test_startup_and_automation_failures_are_distinct_from_product_failures(self):
        self.assertEqual(classify_browser_result(
            1, "BROWSER_STARTUP_BLOCKED: Operation not permitted"),
            "ENVIRONMENT_BLOCKED")
        self.assertEqual(classify_browser_result(
            1, "BROWSER_AUTOMATION_FAILED: DevTools websocket refused"),
            "AUTOMATION_FAILED")
        self.assertEqual(classify_browser_result(
            1, "FAIL: test_mobile_overflow\nAssertionError: overflow"),
            "PRODUCT_FAILED")

    def test_unknown_or_empty_browser_results_are_incomplete(self):
        self.assertEqual(classify_browser_result(0, ""), "INCOMPLETE")
        self.assertEqual(classify_browser_result(2, "runner invocation failed"),
                         "INCOMPLETE")

    def test_required_screenshots_reject_missing_empty_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in REQUIRED_SCREENSHOTS:
                screenshot = root / name
                self.assertEqual(validate_screenshot(screenshot), "missing")
                screenshot.write_bytes(b"")
                self.assertEqual(validate_screenshot(screenshot), "empty or truncated")
                screenshot.write_bytes(b"not a PNG image with enough bytes")
                self.assertEqual(validate_screenshot(screenshot), "invalid PNG header")

    def test_required_screenshot_accepts_nonempty_png_with_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            screenshot = Path(directory) / "gallery-desktop.png"
            screenshot.write_bytes(
                b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                + b"\x00\x00\x05\xa0\x00\x00\x03\x84"
            )
            self.assertIsNone(validate_screenshot(screenshot))


if __name__ == "__main__":
    unittest.main()
