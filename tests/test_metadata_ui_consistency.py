"""Metadata UI consistency checks, without metadata publication."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0, os.environ.get("KIMNG_TEST_RUNTIME", str(ROOT / "src/bin"))
)

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel,
    QToolButton, QWidget,
)

from kim_metadata_browser import MetadataOverview
from kim_metadata_editor import ReviewDialog
from kim_metadata_gps_actions import gps_field, field_actions
from kim_metadata_reader import MetadataEntry, MetadataRecord
from kim_metadata_sources import (
    MetadataSourcePreferences, OverviewPreferences,
)


class MetadataUIConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="kimng-ui-")
        self.addCleanup(self.folder.cleanup)
        self.settings = QSettings(
            str(Path(self.folder.name) / "metadata.ini"),
            QSettings.IniFormat,
        )

    def overview(self, record):
        preferences = MetadataSourcePreferences(self.settings)
        fields = OverviewPreferences(self.settings)
        widget = MetadataOverview(preferences, fields)
        self.addCleanup(widget.deleteLater)
        widget.set_record(record)
        return widget

    def heading(self, overview, label):
        for card in overview.findChildren(QWidget, "overviewField"):
            layout = card.layout()
            if layout is None or not layout.count():
                continue
            heading = layout.itemAt(0).layout()
            if heading is None or not heading.count():
                continue
            title = heading.itemAt(0).widget()
            if isinstance(title, QLabel) and title.text() == label:
                return heading
        self.fail(f"No Overview heading for {label}")

    def test_details_are_immediately_after_field_name(self):
        source = "/example.jpg"
        record = MetadataRecord(source, [
            MetadataEntry(
                "Make", ("EXIF", "IFD0"), None, "Canon",
                source, "EXIF:IFD0:Make",
            ),
        ])
        overview = self.overview(record)
        heading = self.heading(overview, "Camera")

        self.assertIsInstance(heading.itemAt(0).widget(), QLabel)
        details = heading.itemAt(1).widget()
        self.assertIsInstance(details, QToolButton)
        self.assertEqual(
            "View Camera details", details.accessibleName()
        )
        self.assertIsNotNone(
            heading.itemAt(heading.count() - 1).spacerItem()
        )

    def test_gps_controls_follow_details_before_spacer(self):
        overview = self.overview(MetadataRecord("/empty.jpg"))
        heading = self.heading(overview, "GPS position")

        self.assertIsInstance(heading.itemAt(1).widget(), QToolButton)
        self.assertEqual(
            ["View on map…", "Add GPS"],
            [
                heading.itemAt(index).widget().text()
                for index in (2, 3)
            ],
        )
        self.assertIsNotNone(
            heading.itemAt(heading.count() - 1).spacerItem()
        )

    def test_gif_without_gps_is_not_mislabeled(self):
        record = MetadataRecord("/my_animation_1.gif")
        overview = self.overview(record)
        self.assertFalse(overview.show_empty.isChecked())

        labels = [
            label.text()
            for label in overview.findChildren(QLabel)
        ]
        self.assertIn(
            "No embedded camera GPS coordinates", labels
        )

        context = gps_field(record)
        self.assertIsNone(context.position)
        self.assertEqual(
            "No embedded camera GPS coordinates",
            context.provenance,
        )

        actions = field_actions(object(), context)
        self.assertFalse(actions[0][2])
        self.assertEqual("Add GPS", actions[1][0])
        self.assertFalse(actions[1][2])
        self.assertIn("unavailable", actions[1][3])

    def test_jpeg_without_gps_still_offers_add(self):
        record = MetadataRecord("/empty.jpg")
        context = gps_field(record)
        actions = field_actions(object(), context)

        self.assertFalse(actions[0][2])
        self.assertTrue(actions[1][2])
        self.assertEqual("Add GPS", actions[1][0])

    def review(self):
        plan = [{
            "image": "example.jpg",
            "path": "/example.jpg",
            "field": "Title",
            "operation": "Replace",
            "status": "valid",
            "before": "Old title",
            "after": "New title",
        }]
        dialog = ReviewDialog(plan)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_review_button_layout_and_icons(self):
        dialog = self.review()
        self.assertEqual("Back", dialog.back_button.text())
        self.assertEqual("Apply changes", dialog.apply_button.text())
        self.assertEqual("Cancel", dialog.cancel_button.text())

        self.assertFalse(dialog.back_button.icon().isNull())
        self.assertFalse(dialog.apply_button.icon().isNull())
        self.assertFalse(dialog.cancel_button.icon().isNull())
        self.assertFalse(dialog.apply_button.isEnabled())

        row = dialog.layout().itemAt(
            dialog.layout().count() - 1
        ).layout()
        self.assertIs(row.itemAt(0).widget(), dialog.back_button)
        self.assertIsNotNone(row.itemAt(1).spacerItem())

        buttons = row.itemAt(2).widget()
        self.assertIsInstance(buttons, QDialogButtonBox)
        self.assertIn(dialog.apply_button, buttons.buttons())
        self.assertIs(
            buttons.button(QDialogButtonBox.Cancel),
            dialog.cancel_button,
        )

    def test_review_cannot_apply(self):
        dialog = self.review()

        dialog.apply_button.click()
        dialog.accept()
        dialog.done(QDialog.Accepted)
        self.assertNotEqual(QDialog.Accepted, dialog.result())

        dialog.cancel_button.click()
        self.assertEqual(QDialog.Rejected, dialog.result())


if __name__ == "__main__":
    unittest.main()
