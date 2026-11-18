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

    def test_equal_explicitly_empty_values_are_not_differences(self):
        rows = self.rows([entry('Title', '')], [entry('Title', '', source='/other/comparison.jpg')])
        self.assertEqual('empty', rows[0].state)
        self.assertEqual([], visible_rows(rows, 'Differences only'))


class MetadataCompareQtTests(unittest.TestCase):
    """Native interaction tests for independently assigned comparison slots."""
    def setUp(self):
        from test_metadata_browser import MetadataBrowserLoadingTests
        MetadataBrowserLoadingTests.setUpClass()
        self.driver = MetadataBrowserLoadingTests()
        self.driver.setUp()
        self.addCleanup(self.driver.doCleanups)
        self.driver.configure(delay=0.1, entries=1000)
        self.window = self.driver.open_browser()
        self.app = self.driver.app
        self.paths = list(map(str, self.driver.paths))

    def test_keyboard_accessible_selectors_assign_without_multiselection(self):
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.comparison_image_1_header.selector.setCurrentIndex(1)
        window.comparison_image_2_header.selector.setCurrentIndex(2)
        self.assertEqual(tuple(self.paths[:2]), window.compared_paths)
        self.assertFalse(window.preview.isVisible())
        self.driver.wait_for(lambda: not window.comparison_image_1_header.preview.image.isNull() and
                             not window.comparison_image_2_header.preview.image.isNull())
        self.assertEqual(self.driver.paths[0].name, window.comparison_image_1_header.filename.text())
        self.assertEqual(self.driver.paths[1].name, window.comparison_image_2_header.filename.text())

    def test_failed_slot_previews_show_errors_without_repeated_decoding(self):
        from unittest.mock import patch
        from kim_metadata_browser import read_thumbnail
        for path in self.driver.paths[1:]:
            path.write_bytes(b'Owned undecodable image fixture')
        window = self.window
        with patch('kim_metadata_browser.read_thumbnail', wraps=read_thumbnail) as decode:
            window.tabs.setCurrentIndex(2)
            window.assign_comparison(0, self.paths[1])
            window.assign_comparison(1, self.paths[2])
            panels = (window.comparison_image_1_header, window.comparison_image_2_header)
            self.driver.wait_for(lambda: all('Preview dimensions unavailable' in panel.preview.text()
                                             for panel in panels))
            self.driver.wait_for(lambda: not window.preview_workers)
            attempts = [call for call in decode.call_args_list if call.args[0] in self.paths[1:]]
            window._update_slot_headers()
            window._ensure_preview()
            self.app.processEvents()
            self.assertEqual(attempts, [call for call in decode.call_args_list if call.args[0] in self.paths[1:]])
            for path in self.paths[1:]:
                self.assertEqual(1, sum(call.args[0] == path for call in attempts))

    def test_pair_and_swap_survive_navigation_and_tab_changes(self):
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        window.swap_button.click()
        for index in (0, 1, 2):
            window.tabs.setCurrentIndex(index)
            window.image_list.setCurrentRow(2)
        self.assertEqual((self.paths[1], self.paths[0]), window.compared_paths)

    def test_choose_image_placeholder_clears_only_its_slot(self):
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        self.driver.wait_for(lambda: not window.comparison_image_1_header.preview.image.isNull() and
                             not window.comparison_image_2_header.preview.image.isNull())
        window.comparison_image_1_header.selector.setCurrentIndex(0)
        self.assertEqual([None, self.paths[1]], window.comparison_slots)
        self.assertIsNone(window.compared_paths)
        self.assertTrue(window.comparison_image_1_header.preview.image.isNull())
        self.assertFalse(window.comparison_image_2_header.preview.image.isNull())
        self.assertEqual('', window.comparison_image_1_header.filename.text())
        self.assertEqual(0, window.comparison_model.rowCount())

    def test_duplicate_selector_assignment_swaps_or_reports_conflict(self):
        from PySide6.QtWidgets import QPushButton
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        window.comparison_image_1_header.selector.setCurrentIndex(2)
        self.assertEqual((self.paths[1], self.paths[0]), window.compared_paths)
        window.assign_comparison(1, None)
        window.assign_comparison(1, self.paths[1])
        self.assertEqual([self.paths[1], None], window.comparison_slots)
        self.assertIn('different', window.comparison_summary.text())
        self.assertFalse(any(button.text() == 'Use selected image' for button in window.findChildren(QPushButton)))

    def test_three_selected_images_do_not_initialize_an_ambiguous_pair(self):
        window = self.window
        window.image_list.selectAll()
        self.assertFalse(window.compare_images_button.isEnabled())
        window.tabs.setCurrentIndex(2)
        self.app.processEvents()
        self.assertEqual([None, None], window.comparison_slots)
        self.assertIn('Assign a left image', window.comparison_summary.text())
        self.assertTrue(window.comparison_image_1_header.selector.isVisible())

    def test_exactly_two_images_can_initialize_the_slots(self):
        window = self.window
        window.image_list.clearSelection()
        for row in (0, 2):
            window.image_list.item(row).setSelected(True)
        window.compare_images_button.click()
        self.assertEqual((self.paths[0], self.paths[2]), window.compared_paths)

    def test_dragging_loaded_images_assigns_and_slot_drags_swap(self):
        from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        window = self.window
        window.tabs.setCurrentIndex(2)
        def drop(widget, data):
            enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(widget, enter)
            event = QDropEvent(QPointF(10, 10), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(widget, event)
        for side, path in enumerate(self.paths[:2]):
            data = QMimeData()
            data.setUrls([QUrl.fromLocalFile(path)])
            panel = (window.comparison_image_1_header, window.comparison_image_2_header)[side]
            drop(panel.preview, data)
        self.assertEqual(tuple(self.paths[:2]), window.compared_paths)
        data = QMimeData()
        data.setData('application/x-kimng-slot', b'0')
        drop(window.comparison_image_2_header.preview, data)
        self.assertEqual((self.paths[1], self.paths[0]), window.compared_paths)
        window.assign_comparison(0, '/not/a/loaded/image.jpg')
        self.assertEqual((self.paths[1], self.paths[0]), window.compared_paths)

    def test_compare_scope_and_filter_reuse_without_full_extraction(self):
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        self.driver.wait_for(lambda: window.comparison_model.rowCount() > 0)
        self.assertEqual('Overview fields', window.compare_scope.currentText())
        self.assertFalse(any(call['full'] for call in self.driver.calls()))
        count = len(self.driver.calls())
        data = window.comparison_data
        window.compare_mode.setCurrentText('All values')
        window.compare_mode.setCurrentText('Differences only')
        self.assertIs(data, window.comparison_data)
        self.assertEqual(count, len(self.driver.calls()))

        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: window.comparison_data is not data and len(window.comparison_data.rows) >= 1000)
        full = window.comparison_data
        count = len(self.driver.calls())
        window.compare_mode.setCurrentText('All values')
        window.compare_mode.setCurrentText('Differences only')
        self.assertIs(full, window.comparison_data)
        self.assertEqual(count, len(self.driver.calls()))

    def test_overview_compares_preferred_logical_fields_once_and_full_scope_keeps_alternates(self):
        self.driver.configure(delay=0.01, entries=10, metadata={
            'IPTC:IPTC:Image:ObjectName': {'id': 'ObjectName', 'val': 'Alternate title'},
            'EXIF:ExifIFD:Time:DateTimeOriginal': {'id': 'DateTimeOriginal', 'val': '2026:01:02 03:04:05'},
            'XMP:XMP-xmp:Time:CreateDate': {'id': 'CreateDate', 'val': '2025:01:02 03:04:05'}})
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        self.driver.wait_for(lambda: window.comparison_data is not None)
        rows = window.comparison_data.rows
        self.assertEqual(1, sum(row.label == 'Title' for row in rows))
        self.assertFalse(any(row.label in ('Object name', 'Creation date') for row in rows))
        self.assertEqual(1, sum(row.label == 'Capture date' for row in rows))
        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: window._comparison_data_key[1] == 'All fields')
        self.assertTrue(any(row.reference and row.reference.name == 'ObjectName' for row in window.comparison_data.rows))

    def test_reading_priority_refreshes_an_open_comparison_without_extraction(self):
        from kim_metadata_sources import MetadataSourcePreferences
        self.driver.configure(delay=0.01, entries=0, metadata={
            'IPTC:IPTC:Image:ObjectName': {'id': 'ObjectName', 'val': 'IPTC title'}})
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        self.driver.wait_for(lambda: window.comparison_data is not None)
        calls = len(self.driver.calls())
        prefs = MetadataSourcePreferences(window.metadata_preferences.settings)
        prefs.save(('IPTC-IIM', 'Embedded XMP', 'XMP sidecar', 'EXIF'))
        from PySide6.QtCore import QEvent
        window.activateWindow()
        self.app.processEvents()
        self.app.sendEvent(window, QEvent(QEvent.ActivationChange))
        self.driver.wait_for(lambda: window.comparison_data is not None and any(
            row.label == 'Title' and row.reference.value == 'IPTC title' for row in window.comparison_data.rows))
        self.assertEqual(calls, len(self.driver.calls()))


    def test_structured_values_have_bounded_cells_and_complete_details(self):
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QPlainTextEdit
        self.driver.configure(delay=0.01, entries=1000, structured=True)
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: window.comparison_data is not None and len(window.comparison_data.rows) > 1000)
        window.compare_mode.setCurrentText('All values')
        model = window.comparison_model
        row = next(i for i, number in enumerate(model.rows) if window.comparison_data.rows[number].reference and
                   window.comparison_data.rows[number].reference.name == 'Structure')
        self.assertEqual('Structured value (2 elements)', model.index(row, 1).data())
        self.assertIsNone(model.index(row, 1).data(Qt.BackgroundRole))
        self.assertEqual(28, window.comparison_tree.rowHeight(row))
        window.comparison_tree.setCurrentIndex(model.index(row, 1))
        captured = []
        def inspect():
            dialog = self.app.activeModalWidget()
            self.assertFalse(dialog.structure.isExpanded(dialog.structure.model().index(0, 0)))
            self.assertEqual(list(range(3000)), dialog.structure.model().root.value['values'])
            dialog.raw_copy.click()
            captured.append(self.app.clipboard().text())
            dialog.reject()
        QTimer.singleShot(0, inspect)
        window.show_comparison_details()
        self.assertIn('needle-at-the-end', captured[0])
        self.assertIn('2999', captured[0])
        different = next(i for i, number in enumerate(model.rows) if window.comparison_data.rows[number].state == 'different')
        self.assertIsNotNone(model.index(different, 1).data(Qt.BackgroundRole))
        self.assertFalse(model.index(different, 1).data().startswith('Different'))

    def test_complete_compare_cancellation_and_retry(self):
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        self.driver.wait_for(lambda: window.comparison_data is not None)
        previous = window.comparison_data
        self.driver.configure(delay=0.3, entries=1000)
        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: any(call['full'] for call in self.driver.calls()))
        window.compare_cancel.click()
        self.driver.wait_for(lambda: window.worker is None and window._comparison_worker is None)
        self.assertIn('canceled', window.comparison_summary.text())
        window.compare_retry.click()
        self.driver.wait_for(lambda: window.comparison_data is not previous)
        self.assertGreaterEqual(sum(call['full'] for call in self.driver.calls()), 3)

    def test_comparison_cache_accounts_for_retained_metadata_values(self):
        window = self.window
        window.comparison_cache_budget = 256 * 1024
        self.driver.configure(delay=0.01, entries=10, metadata={
            'XMP:XMP-test:Image:Blob': {'id': 'Blob', 'val': 'x' * (512 * 1024)}})
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: window.comparison_data is not None and any(
            row.reference and row.reference.name == 'Blob' for row in window.comparison_data.rows))
        self.assertGreater(window.comparison_data.bytes, window.comparison_cache_budget)
        self.assertNotIn(window._comparison_data_key, window._comparison_cache)

    def test_overview_derived_from_full_records_reuses_the_pair_working_set(self):
        self.driver.configure(delay=0.01, entries=1000)
        window = self.window
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, self.paths[0])
        window.assign_comparison(1, self.paths[1])
        window.compare_scope.setCurrentText('All fields')
        self.driver.wait_for(lambda: window.comparison_data is not None and len(window.comparison_data.rows) > 1000)
        window.overview_records.clear()
        window.overview_records.budget = 1
        window._active_overview = None
        window._comparison_overviews.clear()
        window._comparison_overview_stamps.clear()
        calls = len(self.driver.calls())
        record = window._overview_record(self.paths[1])
        self.assertIs(record, window._overview_record(self.paths[1]))
        window._update_slot_headers()
        self.assertEqual(calls, len(self.driver.calls()))


if __name__ == '__main__':
    unittest.main()
