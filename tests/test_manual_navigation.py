"""Regression coverage for embedded User Guide navigation."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/bin"))

try:
    from PySide6.QtCore import QObject, QUrl, Signal
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
    from PySide6.QtWebEngineCore import QWebEnginePage
    from kim_manual_viewer import add_history_controls, current_guide_url
except ImportError:
    QT_AVAILABLE = False
else:
    QT_AVAILABLE = True


if QT_AVAILABLE:
    class SimulatedPage:
        def __init__(self):
            self.back = QAction("Back")
            self.forward = QAction("Forward")

            self.back.setEnabled(False)
            self.forward.setEnabled(False)

        def action(self, action):
            if action == QWebEnginePage.WebAction.Back:
                return self.back
            if action == QWebEnginePage.WebAction.Forward:
                return self.forward

            raise ValueError(action)


    class SimulatedViewer(QObject):
        urlChanged = Signal(QUrl)
        loadFinished = Signal(bool)

        def __init__(self):
            super().__init__()

            self.history_page = SimulatedPage()

            self.current_url = QUrl()
            self.back_calls = 0
            self.forward_calls = 0

        def page(self):
            return self.history_page

        def url(self):
            return self.current_url

        def back(self):
            self.back_calls += 1

        def forward(self):
            self.forward_calls += 1


@unittest.skipUnless(QT_AVAILABLE, "Qt WebEngine unavailable")
class ManualNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.container = QWidget()
        self.layout = QHBoxLayout(self.container)
        self.viewer = SimulatedViewer()

        self.back, self.forward = add_history_controls(
            self.layout, self.viewer
        )

    def tearDown(self):
        self.container.close()
        self.container.deleteLater()

    def test_empty_history_disables_both_buttons(self):
        self.assertFalse(self.back.isEnabled())
        self.assertFalse(self.forward.isEnabled())

    def test_history_action_changes_update_buttons(self):
        self.viewer.history_page.back.setEnabled(True)

        self.assertTrue(self.back.isEnabled())
        self.assertFalse(self.forward.isEnabled())

        self.viewer.history_page.back.setEnabled(False)
        self.viewer.history_page.forward.setEnabled(True)

        self.assertFalse(self.back.isEnabled())
        self.assertTrue(self.forward.isEnabled())

    def test_buttons_invoke_correct_viewer_actions(self):
        self.viewer.history_page.back.setEnabled(True)
        self.viewer.history_page.forward.setEnabled(True)

        self.back.click()
        self.forward.click()

        self.assertEqual(self.viewer.back_calls, 1)
        self.assertEqual(self.viewer.forward_calls, 1)

    def test_current_page_preserves_reference_and_fragment(self):
        fallback = QUrl.fromLocalFile("/tmp/guide/index.html")

        self.viewer.current_url = QUrl(
            "file:///tmp/guide/reference/ACTIONS.html#resize"
        )

        self.assertEqual(
            current_guide_url(self.viewer, fallback),
            self.viewer.current_url
        )

    def test_current_page_can_be_a_full_size_image(self):
        fallback = QUrl.fromLocalFile("/tmp/guide/index.html")

        self.viewer.current_url = QUrl(
            "file:///tmp/guide/images/example.png"
        )

        self.assertEqual(
            current_guide_url(self.viewer, fallback),
            self.viewer.current_url
        )

    def test_missing_html_view_uses_installed_guide(self):
        fallback = QUrl.fromLocalFile("/tmp/guide/index.html")

        self.assertEqual(
            current_guide_url(None, fallback),
            fallback
        )

    def test_blank_page_uses_installed_guide(self):
        fallback = QUrl.fromLocalFile("/tmp/guide/index.html")

        for url in (QUrl(), QUrl("about:blank")):
            self.viewer.current_url = url

            self.assertEqual(
                current_guide_url(self.viewer, fallback),
                fallback
            )


class ManualHelpTests(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "src/bin/kim_all").read_text()

        self.usage = source.split(
            "\nusage() {\n", 1
        )[1].split(
            "\nmain() {\n", 1
        )[0]

    def section(self, action):
        lines = self.usage.splitlines()

        start = next(
            index for index, line in enumerate(lines)
            if line.startswith("  " + action + " ")
        )

        result = []

        for line in lines[start:]:
            if not line.strip() and result:
                break
            result.append(line)

        return "\n".join(result)

    def test_datesync_does_not_assume_local_time(self):
        help_text = self.section("datesync")

        self.assertIn("Unknown camera", help_text)
        self.assertIn("block synchronization", help_text)
        self.assertNotIn("values use system local time", help_text)

    def test_email_presets_and_review(self):
        help_text = self.section("resizeandsend")

        self.assertNotIn("300", help_text)
        self.assertIn("600 pixel", help_text)
        self.assertIn("Review Changes", help_text)
        self.assertIn("18 MiB", help_text)
        self.assertIn("25 MiB", help_text)

    def test_missing_dispatcher_routes_are_documented(self):
        for route in (
            "location-copy",
            "gallery-choose",
            "photo-story",
        ):
            self.assertIn("  " + route + " --", self.usage)

    def test_flip_and_tiff_are_create_only(self):
        self.assertIn(
            "never overwritten",
            self.section("flipflop")
        )

        self.assertIn(
            "Always creates a new file",
            self.section("tiffjoin")
        )

    def test_webexport_help_is_not_duplicated(self):
        self.assertEqual(
            self.usage.count("  webexport [--"),
            1
        )

        help_text = self.section("webexport")

        self.assertIn("--custom", help_text)
        self.assertIn("Review Changes", help_text)
        self.assertIn("beside each source", help_text)


if __name__ == "__main__":
    unittest.main()
