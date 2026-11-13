"""Focused identity and Qt checks for the two-image metadata comparison."""
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/bin"))

from kim_metadata_reader import MetadataEntry, MetadataRecord, parse_exiftool_json
from kim_metadata_compare import compare_records, visible_rows


def record(path, entries=(), error=None):
    return MetadataRecord(str(Path(path)), list(entries), error=error)


def entry(name, value, group="XMP-dc:Copy0", tag_id=None, language=None, source=None):
    path = source or "/photos/reference.jpg"
    groups = tuple(group.split(":"))
    qualified = f"{group}:{name}"
    return MetadataEntry(name, groups, tag_id, value, path, qualified, language)


class MetadataCompareTests(unittest.TestCase):
    def rows(self, left, right):
        return compare_records(record("/photos/reference.jpg", left),
                               record("/other/comparison.jpg", right))

    def test_matching_and_differing_captions_and_keywords(self):
        ref = [entry("Description", "Morning over Montréal", tag_id="dc:Description"),
               entry("Subject", ["dawn", "harbor", "harbor"], tag_id="dc:Subject")]
        same = [entry("Description", "Morning over Montréal", tag_id="dc:Description",
                      source="/other/comparison.jpg"),
                entry("Subject", ["dawn", "harbor", "harbor"], tag_id="dc:Subject",
                      source="/other/comparison.jpg")]
        self.assertEqual(["identical", "identical"], [r.state for r in self.rows(ref, same)])
        changed = [entry("Description", "Evening over Montréal", tag_id="dc:Description",
                         source="/other/comparison.jpg"),
                   entry("Subject", ["dawn", "harbor"], tag_id="dc:Subject",
                         source="/other/comparison.jpg")]
        self.assertEqual(["different", "different"], [r.state for r in self.rows(ref, changed)])

    def test_unrelated_same_label_tags_do_not_match(self):
        rows = self.rows([entry("Description", "XMP caption", group="XMP-dc:Copy0")],
                         [entry("Description", "EXIF image description", group="EXIF:IFD0")])
        self.assertEqual(2, len(rows))
        self.assertEqual(["missing", "missing"], [r.state for r in rows])
        self.assertEqual(2, len({r.label for r in rows}))

    def test_structured_values_are_compared_without_flattening(self):
        left = entry("LocationCreated", {"City": "Montréal", "Country": "Canada"},
                     group="XMP-iptcExt:Copy0", tag_id="LocationCreated")
        right = entry("LocationCreated", {"Country": "Canada", "City": "Montréal"},
                      group="XMP-iptcExt:Copy0", tag_id="LocationCreated",
                      source="/other/comparison.jpg")
        rows = self.rows([left], [right])
        self.assertEqual("identical", rows[0].state)

    def test_missing_and_explicitly_empty_values_are_distinct(self):
        rows = self.rows([entry("Title", ""), entry("Creator", "Ada")], [])
        self.assertEqual({"Title": "empty", "Creator": "missing"},
                         {r.reference.name: r.state for r in rows})

    def test_language_variants_are_independent_rows(self):
        ref = [entry("Description", "Morning", language="x-default"),
               entry("Description", "Matin", language="fr")]
        cmp = [entry("Description", "Morning", language="x-default", source="/other/comparison.jpg"),
               entry("Description", "Soir", language="fr", source="/other/comparison.jpg")]
        rows = self.rows(ref, cmp)
        self.assertEqual({"x-default": "identical", "fr": "different"},
                         {r.reference.language: r.state for r in rows})

    def test_repeated_entries_keep_occurrences(self):
        ref = [entry("Keywords", "orchid"), entry("Keywords", "orchid"), entry("Keywords", "purple")]
        cmp = [entry("Keywords", "orchid", source="/other/comparison.jpg"),
               entry("Keywords", "purple", source="/other/comparison.jpg"),
               entry("Keywords", "purple", source="/other/comparison.jpg")]
        rows = self.rows(ref, cmp)
        self.assertEqual(3, len(rows))
        self.assertEqual(["identical", "identical", "different"], [r.state for r in rows])
        self.assertEqual(2, sum(row.reference.value == row.comparison.value for row in rows))

    def test_repeated_identical_set_is_order_independent_and_keeps_multiplicity(self):
        left = [entry("Keywords", "orchid"), entry("Keywords", "orchid"), entry("Keywords", "blue")]
        right = [entry("Keywords", "blue", source="/other/comparison.jpg"),
                 entry("Keywords", "orchid", source="/other/comparison.jpg"),
                 entry("Keywords", "orchid", source="/other/comparison.jpg")]
        rows = self.rows(left, right)
        self.assertEqual(3, len(rows))
        self.assertEqual(["identical"] * 3, [row.state for row in rows])

    def test_technical_families_are_available_separately(self):
        left = [entry("FileModifyDate", "2024:01:01", group="File:System"),
                entry("Warning", "diagnostic", group="ExifTool:ExifTool")]
        right = [entry("FileModifyDate", "2026:11:13", group="File:System",
                       source="/other/comparison.jpg"),
                 entry("Warning", "other", group="ExifTool:ExifTool",
                       source="/other/comparison.jpg")]
        primary = self.rows(left, right)
        technical_left = record("/photos/reference.jpg", left, error="Unreadable block")
        technical_right = record("/other/comparison.jpg", right)
        technical_left.warnings = ["Incomplete metadata"]
        technical = compare_records(technical_left, technical_right, include_technical=True)
        self.assertEqual([], primary)
        self.assertEqual(4, len(visible_rows(technical, "Technical metadata")))
        self.assertTrue(all(row.technical for row in technical))

    def test_sidecar_provenance_stays_separate_from_embedded(self):
        ref = [entry("Description", "same", source="/photos/reference.jpg")]
        cmp = [entry("Description", "same", source="/other/comparison.xmp")]
        rows = self.rows(ref, cmp)
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row.state == "missing" for row in rows))
        self.assertTrue(any("XMP sidecar" in row.label for row in rows))

    def test_file_paths_and_filesystem_timestamps_are_not_image_metadata(self):
        ref = [entry("FileName", "one.jpg", group="File:Other"),
               entry("FileModifyDate", "2024:01:01 00:00:00", group="File:System")]
        cmp = [entry("FileName", "two.jpg", group="File:Other", source="/other/comparison.jpg"),
               entry("FileModifyDate", "2026:11:13 00:00:00", group="File:System",
                     source="/other/comparison.jpg")]
        self.assertEqual([], self.rows(ref, cmp))

    def test_conflicting_representations_remain_separate(self):
        ref = [entry("Description", "XMP caption", group="XMP-dc:Copy0"),
               entry("Caption-Abstract", "IPTC caption", group="IPTC:Application2")]
        cmp = [entry("Description", "Other XMP caption", group="XMP-dc:Copy0",
                     source="/other/comparison.jpg"),
               entry("Caption-Abstract", "Other IPTC caption", group="IPTC:Application2",
                     source="/other/comparison.jpg")]
        rows = self.rows(ref, cmp)
        self.assertEqual(2, len(rows))
        self.assertEqual(["different", "different"], [r.state for r in rows])

    def test_malformed_record_errors_do_not_become_metadata_values(self):
        bad_path = "/a/bad.jpg"
        malformed = parse_exiftool_json(
            '[{"SourceFile":"/a/bad.jpg","System:Error":"File format error"}]', [bad_path])[
                str(Path(bad_path).resolve())]
        rows = compare_records(malformed,
                               record("/b/good.jpg", [entry("Title", "Good", source="/b/good.jpg")]))
        self.assertEqual(1, len(rows))
        self.assertEqual("missing", rows[0].state)
        self.assertEqual("File format error", malformed.error)

    def test_comparison_is_symmetric(self):
        left = [entry("Title", "One"), entry("Subject", ["a", "b"])]
        right = [entry("Title", "Two", source="/other/comparison.jpg"),
                 entry("Subject", ["a", "b"], source="/other/comparison.jpg")]
        ab = compare_records(record("/photos/reference.jpg", left), record("/other/comparison.jpg", right))
        ba = compare_records(record("/other/comparison.jpg", right), record("/photos/reference.jpg", left))
        self.assertEqual([(r.identity, r.state) for r in ab], [(r.identity, r.state) for r in ba])
        self.assertEqual([(r.reference.value, r.comparison.value) for r in ab],
                         [(r.comparison.value, r.reference.value) for r in ba])

    def test_filter_shows_only_nonidentical_rows(self):
        rows = self.rows([entry("Title", "Same"), entry("Description", "Old")],
                         [entry("Title", "Same", source="/other/comparison.jpg"),
                          entry("Description", "New", source="/other/comparison.jpg")])
        self.assertEqual(["different"], [r.state for r in visible_rows(rows, "Differences only")])
        self.assertEqual(2, len(visible_rows(rows, "All fields")))


class MetadataCompareQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def make_browser(self, names=("a.jpg", "b.jpg", "c.jpg"), *, loaded=True):
        from unittest.mock import patch
        from PySide6.QtWidgets import QListWidgetItem
        from kim_metadata_browser import MetadataBrowser

        paths = tuple(f"/images/{name}" for name in names)
        with patch.object(MetadataBrowser, "set_images"):
            browser = MetadataBrowser(paths)
        browser.paths = list(paths)
        for name in names:
            browser.image_list.addItem(QListWidgetItem(name))
        browser.selection_count.setText(f"{len(paths)} images")
        if loaded:
            browser.records = {
                path: record(path, [entry("Title", f"Title for {Path(path).stem}", source=path),
                                    entry("Description", f"Description for {Path(path).stem}", source=path)])
                for path in paths
            }
        browser.resize(1000, 700)
        browser.show()
        self.app.processEvents()
        self.addCleanup(self.close_browser, browser)
        return browser

    def close_browser(self, browser):
        from unittest.mock import Mock
        if browser.worker and browser.worker.isRunning():
            browser.worker.requestInterruption()
            browser.worker.wait(1000)
            browser.worker = None
        browser.settings = Mock()
        browser.close()
        self.app.processEvents()

    def click_row(self, browser, row, modifier=None):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        item = browser.image_list.item(row)
        point = browser.image_list.visualItemRect(item).center()
        viewport = browser.image_list.viewport()
        local = QPointF(point)
        global_point = QPointF(viewport.mapToGlobal(point))
        modifiers = modifier if modifier is not None else Qt.NoModifier
        press = QMouseEvent(QEvent.MouseButtonPress, local, global_point, Qt.LeftButton,
                            Qt.LeftButton, modifiers)
        release = QMouseEvent(QEvent.MouseButtonRelease, local, global_point, Qt.LeftButton,
                              Qt.NoButton, modifiers)
        QApplication.sendEvent(viewport, press)
        QApplication.sendEvent(viewport, release)
        self.app.processEvents()

    def selected_names(self, browser):
        return [item.text() for item in browser.image_list.selectedItems()]

    def test_exact_selection_cardinality_and_required_workflow(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser()
        self.assertEqual(0, len(self.selected_names(browser)))
        self.assertFalse(browser.compare_images_button.isEnabled())
        self.assertIn("exactly two", browser.compare_images_button.toolTip())
        self.click_row(browser, 0)
        self.assertEqual(["a.jpg"], self.selected_names(browser))
        self.assertFalse(browser.compare_images_button.isEnabled())
        self.click_row(browser, 1, Qt.ControlModifier)
        self.assertEqual(["a.jpg", "b.jpg"], self.selected_names(browser))
        self.assertTrue(browser.compare_images_button.isEnabled())
        browser.compare_images_button.click()
        self.assertEqual(("/images/a.jpg", "/images/b.jpg"), browser.compared_paths)
        self.assertEqual(2, browser.tabs.currentIndex())
        self.assertEqual("a.jpg", browser.comparison_image_1_header.filename.text())
        self.assertEqual("b.jpg", browser.comparison_image_2_header.filename.text())
        self.assertEqual(["a.jpg", "b.jpg"], self.selected_names(browser))

    def test_selection_and_comparison_persist_across_tabs_and_replace_explicitly(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser()
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        browser.tabs.setCurrentIndex(2)
        self.app.processEvents()
        original = browser.compared_paths
        self.assertEqual(("/images/a.jpg", "/images/b.jpg"), original)
        self.assertEqual(2, len(browser.image_list.selectedItems()))
        browser.tabs.setCurrentIndex(0)
        self.app.processEvents()
        self.assertEqual(2, len(browser.image_list.selectedItems()))
        browser.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertEqual(2, len(browser.image_list.selectedItems()))
        browser.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertEqual(original, browser.compared_paths)
        self.assertEqual("a.jpg", browser.comparison_image_1_header.filename.text())

        self.click_row(browser, 1, Qt.ControlModifier)
        self.assertEqual(["a.jpg"], self.selected_names(browser))
        self.assertEqual(original, browser.compared_paths)
        self.assertTrue(browser.comparison_content.isVisible())
        self.assertFalse(browser.compare_images_button.isEnabled())
        self.click_row(browser, 2, Qt.ControlModifier)
        self.assertEqual(["a.jpg", "c.jpg"], self.selected_names(browser))
        self.assertTrue(browser.compare_images_button.isEnabled())
        browser.compare_images_button.click()
        self.assertEqual(("/images/a.jpg", "/images/c.jpg"), browser.compared_paths)
        self.assertEqual("c.jpg", browser.comparison_image_2_header.filename.text())

    def test_three_selection_and_shift_range_show_instruction(self):
        from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt
        browser = self.make_browser()
        self.click_row(browser, 0)
        first = browser.image_list.model().index(0, 0)
        last = browser.image_list.model().index(2, 0)
        range_selection = QItemSelection(first, last)
        browser.image_list.selectionModel().select(
            range_selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.app.processEvents()
        self.assertEqual(["a.jpg", "b.jpg", "c.jpg"], self.selected_names(browser))
        self.assertFalse(browser.compare_images_button.isEnabled())
        browser.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertIn("Select two images", browser.comparison_empty.text())
        self.assertIn("Ctrl+click", browser.comparison_empty.text())
        self.assertTrue(browser.comparison_tree.topLevelItemCount() <= 1)
        self.assertFalse(browser.comparison_content.isVisible())

    def test_list_navigation_preserves_multiselection_and_single_image_browsing(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser()
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        browser.next_button.click()
        self.app.processEvents()
        self.assertEqual(["a.jpg", "b.jpg"], self.selected_names(browser))
        self.assertEqual("c.jpg", browser.filename.text())
        self.click_row(browser, 0)
        self.assertEqual(["a.jpg"], self.selected_names(browser))
        browser.next_button.click()
        self.app.processEvents()
        self.assertEqual(["b.jpg"], self.selected_names(browser))
        self.assertEqual("b.jpg", browser.filename.text())
        browser.tabs.setCurrentIndex(0)
        browser.tabs.setCurrentIndex(1)
        browser.tabs.setCurrentIndex(0)
        self.assertEqual(["b.jpg"], self.selected_names(browser))

    def test_compare_tab_auto_compares_two_selected_images(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser()
        self.click_row(browser, 1)
        self.click_row(browser, 2, Qt.ControlModifier)
        browser.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertEqual(("/images/b.jpg", "/images/c.jpg"), browser.compared_paths)
        self.assertEqual("b.jpg", browser.comparison_image_1_header.filename.text())
        self.assertEqual("c.jpg", browser.comparison_image_2_header.filename.text())

    def test_selection_change_during_extraction_cannot_label_stale_results_as_new_pair(self):
        from unittest.mock import Mock, patch
        from PySide6.QtCore import Qt
        browser = self.make_browser(loaded=False)
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        worker = Mock()
        worker.isRunning.return_value = True
        browser.worker = worker
        with patch("kim_metadata_browser.MetadataWorker") as worker_type:
            browser.compare_images_button.click()
            self.assertEqual(("/images/a.jpg", "/images/b.jpg"), browser.pending_comparison_paths)
            worker_type.assert_not_called()
        self.click_row(browser, 1, Qt.ControlModifier)
        self.click_row(browser, 2, Qt.ControlModifier)
        self.assertIsNone(browser.pending_comparison_paths)
        browser.worker_generation = 3
        browser.receive_results(
            {"/images/a.jpg": record("/images/a.jpg", [entry("Title", "Stale")])}, {}, None, 2)
        self.assertNotIn("/images/a.jpg", browser.records)
        browser.receive_results(
            {"/images/a.jpg": record("/images/a.jpg", [entry("Title", "A")]),
             "/images/b.jpg": record("/images/b.jpg", [entry("Title", "B")])}, {}, None, 3)
        self.assertIsNone(browser.compared_paths)
        self.assertFalse(browser.comparison_content.isVisible())
        self.assertIn("Selection changed", browser.comparison_empty.text())
        browser.worker = None

    def test_loading_queues_missing_selected_image_after_existing_worker(self):
        from unittest.mock import Mock, patch
        from PySide6.QtCore import Qt
        browser = self.make_browser(loaded=False)
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        worker = Mock()
        worker.isRunning.return_value = True
        browser.worker = worker
        browser.compare_images_button.click()
        self.click_row(browser, 1, Qt.ControlModifier)
        self.click_row(browser, 2, Qt.ControlModifier)
        browser.compare_images_button.click()
        self.assertEqual(("/images/a.jpg", "/images/c.jpg"), browser.pending_comparison_paths)
        browser.receive_results({"/images/a.jpg": record("/images/a.jpg", [entry("Title", "A")]),
                                 "/images/b.jpg": record("/images/b.jpg", [entry("Title", "B")])}, {}, None)
        self.assertIsNone(browser.compared_paths)
        worker.isRunning.return_value = False
        worker.wait.return_value = True
        queued = Mock()
        queued.completed = Mock()
        queued.finished = Mock()
        with patch("kim_metadata_browser.MetadataWorker", return_value=queued) as worker_type:
            browser.worker_finished()
        worker_type.assert_called_once_with(["/images/c.jpg"], browser)
        queued.start.assert_called_once_with()
        self.assertEqual(("/images/a.jpg", "/images/c.jpg"), browser.pending_comparison_paths)
        browser.worker = None

    def test_modes_show_match_state_and_sidecar_conflict_summary(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser(("reference.jpg", "comparison.jpg"))
        browser.records = {
            browser.paths[0]: record(browser.paths[0], [
                entry("Description", "Same caption", tag_id="dc:Description", source=browser.paths[0]),
                entry("Caption-Abstract", "Old IPTC caption", group="IPTC:Application2",
                      tag_id="Caption-Abstract", source=browser.paths[0]),
            ]),
            browser.paths[1]: record(browser.paths[1], [
                entry("Description", "Same caption", tag_id="dc:Description", source=browser.paths[1]),
                entry("Description", "External caption", tag_id="dc:Description",
                      source="/photos/comparison.xmp"),
            ]),
        }
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        browser.compare_images_button.click()
        self.assertIn("1 matching", browser.comparison_summary.text())
        self.assertIn("1 IPTC/XMP source conflict", browser.comparison_summary.text())
        self.assertTrue(browser.comparison_empty.isHidden())
        browser.compare_mode.setCurrentText("All fields")
        self.assertGreater(browser.comparison_tree.topLevelItemCount(), 0)

    def test_identical_metadata_reports_match_and_all_fields_can_be_shown(self):
        from PySide6.QtCore import Qt
        browser = self.make_browser(("reference.jpg", "comparison.jpg"))
        same = [entry("Title", "Same title", source=browser.paths[0]),
                entry("Description", "Same description", source=browser.paths[0])]
        other = [entry("Title", "Same title", source=browser.paths[1]),
                 entry("Description", "Same description", source=browser.paths[1])]
        browser.records = {browser.paths[0]: record(browser.paths[0], same),
                           browser.paths[1]: record(browser.paths[1], other)}
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        browser.compare_images_button.click()
        self.assertEqual("Differences only", browser.compare_mode.currentText())
        self.assertTrue(browser.comparison_tree.topLevelItem(0).text(0).startswith("The metadata matches"))
        browser.compare_mode.setCurrentText("All fields")
        self.assertEqual("Description (2)", browser.comparison_tree.topLevelItem(0).text(0))

    def test_running_worker_still_allows_pair_request_and_shutdown_waits(self):
        from unittest.mock import Mock
        from PySide6.QtCore import Qt
        browser = self.make_browser(loaded=False)
        self.click_row(browser, 0)
        self.click_row(browser, 1, Qt.ControlModifier)
        browser.worker = Mock()
        browser.worker.isRunning.return_value = True
        self.assertTrue(browser.compare_images_button.isEnabled())
        browser.compare_images_button.click()
        self.assertEqual(("/images/a.jpg", "/images/b.jpg"), browser.pending_comparison_paths)
        event = Mock()
        browser.closeEvent(event)
        browser.worker.requestInterruption.assert_called_once_with()
        event.ignore.assert_called_once_with()
        self.assertTrue(browser.close_after_worker)
        browser.worker = None
        browser.settings = Mock()
        browser.close()


if __name__ == "__main__":
    unittest.main()
