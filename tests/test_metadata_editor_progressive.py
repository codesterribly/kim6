"""Progressive Editor behavior through native widgets and an external reader."""
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import test_metadata_browser as browser_tests
from kim_metadata_editor import MetadataEditor
from PySide6.QtWidgets import QDialogButtonBox, QDialog
from PySide6.QtCore import Qt


class MetadataEditorProgressiveTests(unittest.TestCase):
    def setUp(self):
        browser_tests.MetadataBrowserLoadingTests.setUpClass()
        self.driver = browser_tests.MetadataBrowserLoadingTests()
        self.driver.setUp()
        self.addCleanup(self.driver.doCleanups)
        self.driver.configure(delay=0.5, entries=25000)
        # GPS inspection has its own real-reader coverage in test_metadata_editor_gps.
        # Keep its independent reads out of this progressive-reader call log.
        gps_section = patch.object(MetadataEditor, '_refresh_gps_section', lambda self: None)
        gps_section.start()
        self.addCleanup(gps_section.stop)
        self.window = MetadataEditor(list(map(str, self.driver.paths)))
        self.driver.windows.append(self.window)
        self.window.show()
        self.addCleanup(self.clear_proposals)

    def clear_proposals(self):
        self.window.drafts.clear()
        self.window.source_drafts.clear()
        self.window.batch_sessions.clear()

    def test_gps_view_preserves_pending_metadata_proposal(self):
        from unittest.mock import patch

        window = self.window
        self.driver.wait_for(
            lambda: window._record(window.paths[0]) is not None
            and window.worker is None
        )

        path = window._active_path()
        window.field_controls["title"]["edit"].setText(
            "Draft retained after GPS inspection"
        )

        original_draft = window.drafts[path]["title"]
        self.assertTrue(window.review_button.isEnabled())

        from kim_metadata_sources import OVERVIEW_DEFAULTS
        from PySide6.QtWidgets import QToolButton

        window.overview_preferences.save([
            field for field in OVERVIEW_DEFAULTS
            if field.section == "Location"
        ])
        window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
        window.overview.show_empty.setChecked(True)

        # Exercise the shared section renderer independently of the
        # asynchronous selective metadata reader. The current image
        # record is sufficient to render empty pinned Location fields.
        window.overview.set_record(window._record(path))
        controls = window.overview.overview_body.findChildren(QToolButton, 'gpsFieldAction')
        maps = [button for button in controls if button.text() == 'View on map…']
        self.assertTrue(maps)
        # This fixture has no coordinates: field-level map controls cannot
        # launch a preferred-source report for a missing coordinate pair.
        self.assertTrue(all(not button.isEnabled() for button in maps))
        self.assertTrue(any(button.text() == 'Add GPS…' for button in controls))
        with patch('kim_location_dialog.LocationDialog') as dialog:
            for button in maps:
                button.click()
            dialog.assert_not_called()

        self.assertIs(
            original_draft, window.drafts[path]["title"]
        )
        self.assertEqual(
            "Draft retained after GPS inspection",
            window.drafts[path]["title"].value
        )
        self.assertTrue(window.review_button.isEnabled())

    def test_review_requires_actual_proposals_and_reverting_restores_noop(self):
        from kim_metadata_editor import ReviewDialog
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        self.assertEqual('Pending changes: 0', window.pending_label.text())
        self.assertFalse(window.review_button.isEnabled())
        with patch('kim_metadata_editor.ReviewDialog', side_effect=AssertionError('Empty review opened')):
            window.review_changes()
        edit = window.field_controls['title']['edit']
        before = edit.text()
        edit.setText('A proposed title')
        self.assertTrue(window.review_button.isEnabled())
        self.assertIn('1 change', window.pending_label.text())
        edit.setText(before)
        self.assertFalse(window.review_button.isEnabled())
        self.assertEqual('Pending changes: 0', window.pending_label.text())
        dialog = ReviewDialog([], window)
        self.assertEqual(QDialog.DialogCode.Rejected, dialog.exec())
        self.assertFalse(dialog.isVisible())
        for plan in ([{'status': 'noop'}], [{'status': 'unchanged'}]):
            empty = ReviewDialog(plan, window)
            empty.show()
            empty.open()
            self.assertEqual(QDialog.DialogCode.Rejected, empty.exec())
            self.assertFalse(empty.isVisible())

    def test_batch_selection_is_independent_of_navigation(self):
        from PySide6.QtCore import Qt
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        self.assertEqual('Edit selected images…', window.batch_button.text())
        self.assertFalse(window.batch_button.isEnabled())
        window.file_list.selectAll()
        selected = [item.data(Qt.UserRole) for item in window.file_list.selectedItems()]
        self.assertTrue(window.batch_button.isEnabled())
        current = window.file_list.currentRow()
        window.file_list.clearSelection()
        self.assertEqual(current, window.file_list.currentRow())
        window.file_list.selectAll()
        window.navigate(1)
        self.assertEqual(selected, [item.data(Qt.UserRole) for item in window.file_list.selectedItems()])
        self.assertEqual(1, window.file_list.currentRow())

    def test_batch_defaults_and_cancel_are_noop(self):
        from kim_metadata_editor import BatchEditDialog
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        dialog = BatchEditDialog(window.paths, window.records, parent=window)
        self.assertEqual({}, dialog.selected_fields())
        self.assertFalse(dialog.add_button.isEnabled())
        for control in dialog.controls.values():
            self.assertEqual('Leave unchanged', control['operation'].currentText())
            self.assertFalse(control['sync'].isChecked())
        title = dialog.controls['title']
        title['operation'].setCurrentText('Replace')
        title['edit'].setText('Batch title')
        self.assertTrue(dialog.add_button.isEnabled())
        title['operation'].setCurrentText('Leave unchanged')
        self.assertFalse(dialog.add_button.isEnabled())
        self.assertEqual({}, dialog.selected_fields())
        dialog.reject()
        self.assertFalse(window.batch_sessions)
        self.assertFalse(window.review_button.isEnabled())

    def test_shared_overview_is_readonly_selective_and_shows_pinned_field(self):
        from kim_metadata_sources import OverviewField
        from PySide6.QtWidgets import QLabel, QLineEdit, QPlainTextEdit
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        window.overview_preferences.save([OverviewField('Title', 'Pinned title'),
                                          OverviewField('Make', 'Camera make')])
        window.tabs.setCurrentIndex(1)
        self.assertEqual('Overview', window.tabs.tabText(1))
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible())
        texts = [label.text() for label in window.overview.findChildren(QLabel)]
        self.assertIn('Pinned title', texts)
        self.assertFalse(window.overview.findChildren(QLineEdit))
        self.assertFalse(window.overview.findChildren(QPlainTextEdit))
        self.assertFalse(any(call['full'] for call in self.driver.calls()))
        calls = len(self.driver.calls())
        window.tabs.setCurrentIndex(0)
        window.tabs.setCurrentIndex(1)
        self.driver.app.processEvents()
        self.assertEqual(calls, len(self.driver.calls()))

    def test_readonly_camera_and_dimensions_match_overview(self):
        from unittest.mock import patch
        from kim_metadata_reader import MetadataEntry, MetadataRecord
        from kim_metadata_sources import OverviewField

        window = self.window
        self.driver.wait_for(
            lambda: window._record(window.paths[0]) is not None
            and window.worker is None
        )

        path = window.paths[0]
        entries = [
            MetadataEntry(
                "Make", ("EXIF", "IFD0"), 1,
                "Google", path, "EXIF:Make"
            ),
            MetadataEntry(
                "Model", ("EXIF", "IFD0"), 2,
                "Pixel 10 Pro", path, "EXIF:Model"
            ),
            MetadataEntry(
                "ImageWidth", ("File", "System"), 3,
                4000, path, "File:ImageWidth"
            ),
            MetadataEntry(
                "ImageHeight", ("File", "System"), 4,
                3000, path, "File:ImageHeight"
            ),
        ]
        record = MetadataRecord(path, entries)

        camera = OverviewField(
            "Make", "Camera", aliases=("Make", "Model")
        )
        dimensions = OverviewField(
            "ImageSize", "Image dimensions",
            aliases=("ImageSize", "ImageWidth", "ImageHeight")
        )

        window.overview_preferences.save([camera, dimensions])

        with patch.object(
            window, "_overview_snapshot",
            return_value=(record, frozenset(
                ("Make", "Model", "ImageWidth", "ImageHeight")
            ))
        ), patch.object(
            window, "_overview_missing", return_value=()
        ):
            window._refresh_editor_pins()

        camera_value = window._readonly_pins[
            camera.key
        ]["value"]
        dimensions_value = window._readonly_pins[
            dimensions.key
        ]["value"]

        self.assertEqual(
            "Google Pixel 10 Pro",
            camera_value.text()
        )
        self.assertEqual(
            "4000 × 3000 pixels",
            dimensions_value.text()
        )
        self.assertTrue(camera_value.textInteractionFlags() & Qt.TextSelectableByMouse)
        self.assertTrue(dimensions_value.textInteractionFlags() & Qt.TextSelectableByMouse)
        self.assertEqual({}, window.drafts)
        self.assertFalse(window.review_button.isEnabled())

    def test_pinned_modify_date_uses_full_cache_without_changing_edit_targets(self):
        from PySide6.QtWidgets import QLabel
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        self.driver.configure(delay=0.01, entries=0, metadata={
            'EXIF:IFD0:Image:ModifyDate': {'id': 'ModifyDate', 'val': '2026:11:15 12:34:56'}})
        window.tabs.setCurrentIndex(window.ALL_TAB)
        self.driver.wait_for(lambda: window._inspection_record is not None)
        row = next(i for i, index in enumerate(window.all_model.rows)
                   if window.all_model.record.entries[index].name == 'ModifyDate')
        window.all_table.setCurrentIndex(window.all_model.index(row, 0))
        window.all_pin.trigger()
        calls = len(self.driver.calls())
        window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible())
        texts = [label.text() for label in window.overview.findChildren(QLabel)]
        self.assertTrue(any('ModifyDate' in value for value in texts))
        self.assertIn('2026:11:15 12:34:56', texts)
        self.assertEqual(calls, len(self.driver.calls()))
        self.assertNotIn('ModifyDate', window.field_controls)
        self.assertFalse(window.source_targets)
        self.assertFalse(window.review_button.isEnabled())

    def test_list_thumbnails_load_without_selection_and_reuse_cache(self):
        window = self.window
        heights = [window.file_list.sizeHintForRow(row) for row in range(len(window.paths))]
        self.driver.wait_for(lambda: all(not window.file_list.item(row).icon().isNull()
                                        for row in range(len(window.paths))))
        self.driver.wait_for(lambda: not window.thumbnail_workers and window.worker is None)
        self.assertEqual(0, window.file_list.currentRow())
        # The permanent fields and default pins can require two selective reads.
        calls = self.driver.calls()
        self.assertLessEqual(len(calls), 2)
        self.assertTrue(calls)
        self.assertFalse(any(call['full'] for call in calls))
        self.assertEqual(1, len({call['inode'] for call in calls}))
        self.assertEqual(heights, [window.file_list.sizeHintForRow(row) for row in range(len(window.paths))])
        with patch('kim_metadata_browser.read_thumbnail', side_effect=AssertionError('Thumbnail decoded twice')):
            window._pump_thumbnails()
            self.driver.app.processEvents()
        self.assertLessEqual(len(window.thumbnails), 128)
        self.assertLessEqual(window.thumbnails.bytes, 4 * 1024 * 1024)

    def test_thumbnail_pool_close_interrupts_every_worker_before_widget_deletion(self):
        from threading import Event
        from PySide6.QtCore import QSize, QThread, Qt
        from PySide6.QtGui import QColor, QImage
        from shiboken6 import isValid
        from metadata_integrity import sha256_noatime

        self.driver.wait_for(lambda: not self.window.preview_workers and
                             not self.window.thumbnail_workers)
        paths = []
        for number in range(9):
            path = self.driver.workspace.path(f'pool/{number}.jpg')
            path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(800, 600, QImage.Format_RGB32)
            image.fill(QColor(number * 25, 0, 0))
            self.assertTrue(image.save(str(path)))
            paths.append(path)

        def signature(path):
            info = path.stat()
            return (sha256_noatime(path), info.st_size, info.st_atime_ns,
                    info.st_mtime_ns, info.st_ctime_ns)

        before = {path: signature(path) for path in paths}
        release = Event()
        decodes = []

        def delayed_decode(path, size, auto_orient=True):
            decodes.append((path, size))
            if size == QSize(96, 72):
                if not release.wait(10):
                    raise RuntimeError('Test did not release thumbnail workers')
            return browser_tests.read_thumbnail(path, size, auto_orient=auto_orient)

        with patch('kim_metadata_browser.read_thumbnail', side_effect=delayed_decode):
            window = MetadataEditor(list(map(str, paths)))
            self.driver.windows.append(window)
            window.setAttribute(Qt.WA_DeleteOnClose)
            window.show()
            try:
                self.driver.wait_for(lambda: len(window.thumbnail_workers) == 4)
                workers = tuple(window.thumbnail_workers)
                self.assertEqual(4, len({worker.path for worker in workers}))
                self.assertTrue(all(worker.priority() == QThread.LowPriority for worker in workers))
                for row in (8, 1, 6, 2, 7):
                    window.file_list.setCurrentRow(row)
                    self.driver.app.processEvents()
                    self.assertLessEqual(len(window.thumbnail_workers), 4)
                    self.assertLessEqual(len(window.preview_workers), 2)
                selected = str(paths[7])
                self.driver.wait_for(lambda: window.current_preview_path == selected and
                                     window._preview_image(selected) is not None)
                preview = window._preview_image(selected)
                self.assertEqual(QSize(640, 480), preview.size())
                self.assertAlmostEqual(175, preview.pixelColor(0, 0).red(), delta=3)
                self.assertFalse(window.close())
                self.assertTrue(window.isVisible())
                self.assertTrue(all(worker.isInterruptionRequested() for worker in workers))
                count = len(decodes)
            finally:
                release.set()
            self.driver.wait_for(lambda: not isValid(window))
            self.driver.windows.remove(window)
            self.assertEqual(count, len(decodes), 'Shutdown restarted preview or thumbnail work')
        self.assertEqual(before, {path: signature(path) for path in paths})
        self.assertEqual(set(paths), set(paths[0].parent.iterdir()), 'Inspection created an output or sidecar')

    def test_single_jpeg_closes_after_all_thumbnail_workers_finish(self):
        path = self.driver.paths[0]
        window = MetadataEditor([str(path)])
        self.driver.windows.append(window)
        window.show()
        self.driver.wait_for(lambda: window._preview_image(str(path)) is not None and
                             not window.thumbnail_workers and not window.preview_workers and
                             window.worker is None)
        self.assertFalse(window.file_list.item(0).icon().isNull())
        self.assertTrue(window.close())
        self.assertFalse(window.isVisible())

    def test_overview_reloads_source_priority_from_another_settings_instance(self):
        from kim_metadata_sources import MetadataSourcePreferences, OverviewField
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QLabel
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        self.driver.configure(delay=0.01, entries=0, metadata={
            'XMP:XMP-dc:Image:Title': {'id': 'title', 'val': 'Embedded title'},
            'IPTC:IPTC:Image:ObjectName': {'id': 'ObjectName', 'val': 'Legacy title'}})
        window.records.clear()
        window._active_record = None
        window._retry_metadata()
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None and window.worker is None)
        window.overview_preferences.save([OverviewField('Title', 'Title')])
        window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible())
        labels = lambda: [label.text() for label in window.overview.overview_body.findChildren(QLabel)]
        self.assertIn('Embedded title', labels())
        other = MetadataSourcePreferences(QSettings(window.preferences.settings.fileName(), QSettings.IniFormat))
        other.save(priority=('IPTC-IIM', 'Embedded XMP', 'XMP sidecar', 'EXIF'))
        calls = len(self.driver.calls())
        window._reload_overview_preferences()
        self.assertIn('Legacy title', labels())
        self.assertEqual(calls, len(self.driver.calls()))

    def test_thumbnail_formats_and_overview_preserve_source_signatures(self):
        import base64
        from PySide6.QtGui import QImage
        from metadata_integrity import sha256_noatime
        png = self.driver.paths[0].with_name('image.png')
        image = QImage(40, 20, QImage.Format_RGB32)
        image.fill(0xff339966)
        self.assertTrue(image.save(str(png)))
        gif = self.driver.paths[0].with_name('image.gif')
        gif.write_bytes(base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'))
        paths = [self.driver.paths[0], png, gif]
        def signature(path):
            info = path.stat()
            return sha256_noatime(path), info.st_size, info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns
        before = {path: signature(path) for path in paths}
        window = MetadataEditor(list(map(str, paths)))
        self.driver.windows.append(window)
        window.show()
        self.driver.wait_for(lambda: all(not window.file_list.item(row).icon().isNull() for row in range(3)))
        window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible())
        self.assertEqual(before, {path: signature(path) for path in paths})

    def test_ctrl_and_shift_selection_do_not_change_current_editing_image(self):
        from PySide6.QtCore import Qt, QEvent
        from PySide6.QtGui import QMouseEvent, QKeyEvent
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None)
        items = window.file_list
        def click(row, modifiers):
            point = items.visualItemRect(items.item(row)).center().toPointF()
            for kind, buttons in ((QEvent.MouseButtonPress, Qt.LeftButton), (QEvent.MouseButtonRelease, Qt.NoButton)):
                event = QMouseEvent(kind, point, point, Qt.LeftButton, buttons, modifiers)
                self.driver.app.sendEvent(items.viewport(), event)
        click(1, Qt.ControlModifier)
        self.assertEqual(window.paths[0], window._active_path())
        self.assertEqual(2, len(items.selectedItems()))
        # Keyboard range selection exercises Qt's native anchor without QtTest.
        click(0, Qt.NoModifier)
        for _ in range(2):
            self.driver.app.sendEvent(items, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.ShiftModifier))
        self.assertEqual(window.paths[0], window._active_path())
        self.assertEqual(3, len(items.selectedItems()))
        self.assertEqual(2, items.currentRow())
        # Clicking the already focused row still starts individual editing.
        click(2, Qt.NoModifier)
        self.assertEqual(window.paths[2], window._active_path())

    def test_pin_changes_during_loading_do_not_mark_dropped_fields_as_loaded(self):
        from kim_metadata_sources import OverviewField
        from PySide6.QtWidgets import QLabel
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None and window.worker is None)
        self.driver.configure(delay=0.1, entries=0, metadata={
            'EXIF:IFD0:Image:Software': {'id': 'Software', 'val': 'Retained software'},
            'EXIF:IFD0:Image:WhiteBalance': {'id': 'WhiteBalance', 'val': 'New white balance'}})
        title, make, model = (OverviewField(name, name) for name in ('Title', 'Software', 'WhiteBalance'))
        window.overview_preferences.save([title, make])
        window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible() and window.worker is None)
        window.overview_preferences.save([title, model])
        window._reload_overview_preferences()
        self.assertIsNotNone(window.worker)
        window.overview_preferences.save([title, make, model])
        window._reload_overview_preferences()
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible() and window.worker is None)
        texts = [label.text() for label in window.overview.overview_body.findChildren(QLabel)]
        self.assertIn('Retained software', texts)
        self.assertIn('New white balance', texts)
        self.assertFalse(any(call['full'] for call in self.driver.calls()))

    def test_source_change_before_worker_start_does_not_merge_old_fields(self):
        from kim_metadata_editor import MetadataWorker
        from kim_metadata_sources import OverviewField
        from PySide6.QtWidgets import QLabel
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None and window.worker is None)
        self.driver.configure(delay=0.01, entries=0, metadata={
            'XMP:XMP-dc:Image:Title': {'id': 'title', 'val': 'Fresh title'},
            'EXIF:IFD0:Image:Software': {'id': 'Software', 'val': 'Fresh maker'}})
        window.overview_preferences.save([OverviewField('Title', 'Title'), OverviewField('Software', 'Software')])
        original_start = MetadataWorker.start
        changed = []
        def start_with_sidecar_change(worker, *args):
            if worker.scope == 'overview' and not changed:
                self.driver.paths[0].with_suffix('.xmp').write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
                changed.append(True)
            return original_start(worker, *args)
        with patch.object(MetadataWorker, 'start', start_with_sidecar_change):
            window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
            self.driver.wait_for(lambda: changed and not window.overview.overview_loading.isVisible() and window.worker is None)
        texts = [label.text() for label in window.overview.overview_body.findChildren(QLabel)]
        self.assertIn('Fresh title', texts)
        self.assertIn('Fresh maker', texts)
        self.assertFalse(any(text.startswith('title:') for text in texts))

    def test_overview_worker_exception_is_visible_and_requires_explicit_retry(self):
        from kim_metadata_sources import OverviewField
        window = self.window
        self.driver.wait_for(lambda: window._record(window.paths[0]) is not None and window.worker is None)
        window.overview_preferences.save([OverviewField('Title', 'Title'), OverviewField('Software', 'Software')])
        with patch('kim_metadata_browser.read_metadata', side_effect=RuntimeError('fixture extraction unavailable')) as reader:
            window.tabs.setCurrentIndex(window.OVERVIEW_TAB)
            self.driver.wait_for(lambda: window.overview.overview_retry.isVisible() and window.worker is None)
            self.assertIn('fixture extraction unavailable', window.overview.overview_loading.text())
            self.assertEqual(1, reader.call_count)
            self.assertFalse(window.preview.pixmap().isNull())
        window.overview.overview_retry.click()
        self.driver.wait_for(lambda: not window.overview.overview_loading.isVisible())

    def test_preview_precedes_selective_current_image_fields_and_cancel_is_native(self):
        window = self.window
        self.driver.wait_for(lambda: window.preview.pixmap() and not window.preview.pixmap().isNull())
        self.assertEqual('Loading metadata…', window.loading_label.text())
        self.assertTrue(window.loading_label.isVisible())
        self.assertFalse(window.records)
        self.driver.wait_for(lambda: window.records.get(str(self.driver.paths[0])) is not None)
        self.assertFalse(window.loading_label.isVisible())
        self.assertEqual(1, len(self.driver.calls()))
        self.assertFalse(self.driver.calls()[0]['full'])
        self.assertEqual(['Edit metadata', 'Overview', 'All fields', 'Sources && targets'], [window.tabs.tabText(i) for i in range(4)])
        self.assertEqual(QDialogButtonBox.AcceptRole, window.buttons.buttonRole(window.review_button))
        window.buttons.button(QDialogButtonBox.Cancel).click()
        self.driver.wait_for(lambda: not window.isVisible())

    def test_cached_navigation_retains_drafts_without_decoding_or_extraction(self):
        window = self.window
        first, second = map(str, self.driver.paths[:2])
        self.driver.wait_for(lambda: window._record(first) is not None)
        title = window.field_controls['title']['edit']
        title.setText('Draft retained')
        target = window.drafts[first]['title'].target
        window.navigate(1)
        self.driver.wait_for(lambda: window._record(second) is not None and window._preview_image(second) is not None)
        self.driver.wait_for(lambda: not window.preview_workers and window.worker is None)
        calls = len(self.driver.calls())
        with patch('kim_metadata_browser.read_thumbnail', side_effect=AssertionError('Cached preview reread')):
            window.navigate(-1)
            self.driver.app.processEvents()
        self.assertEqual('Draft retained', title.text())
        self.assertEqual(target, window.drafts[first]['title'].target)
        self.assertEqual(calls, len(self.driver.calls()))

    def test_all_fields_is_lazy_shared_search_and_pinning_preserve_editable_record(self):
        window = self.window
        first = str(self.driver.paths[0])
        self.driver.wait_for(lambda: window._record(first) is not None)
        record = window._record(first)
        self.assertFalse(any(call['full'] for call in self.driver.calls()))
        self.driver.configure(delay=0.02, entries=1000, structured=True)
        window.tabs.setCurrentIndex(2)
        self.driver.wait_for(lambda: window._inspection_record is not None and window._inspection_filter is None)
        self.assertEqual(1005, len(window._inspection_record.entries))
        self.assertIs(record, window._record(first))
        window.all_search.setText('needle-at-the-end')
        self.driver.wait_for(lambda: window._inspection_filter is None and window.all_model.rowCount() == 1)
        window.all_table.setCurrentIndex(window.all_model.index(0, 0))
        self.assertIn('Structured value (2 elements)', window.all_details.toPlainText())
        self.assertEqual('needle-at-the-end', window._inspected_entry.value['tail'])
        window.all_pin.trigger()
        self.assertEqual('Added to Browser overview', window.statusBar().currentMessage())
        self.assertEqual('Remove from Browser overview', window.all_pin.text())
        self.assertEqual('MakerNotes:Google:Image:Structure', window.overview_preferences.fields[-1].selector)

    def test_explicit_all_fields_supersedes_pending_editing_scope(self):
        import json
        window = self.window
        self.driver.wait_for(lambda: bool(self.driver.calls()))
        window.tabs.setCurrentIndex(2)
        self.driver.wait_for(lambda: any(call['full'] for call in self.driver.calls()))
        finished = self.driver.log.with_suffix('.finished')
        completed = [json.loads(line) for line in finished.read_text().splitlines()] if finished.exists() else []
        self.assertFalse(any(not call['full'] for call in completed))
        self.driver.wait_for(lambda: window._inspection_record is not None)
        window.tabs.setCurrentIndex(0)
        self.driver.wait_for(lambda: not window.loading_label.isVisible())
        self.assertEqual(1, sum(call['full'] for call in self.driver.calls()))

    def test_pinning_distinguishes_embedded_and_sidecar_representations(self):
        window = self.window
        first = self.driver.paths[0]
        self.driver.wait_for(lambda: window._record(str(first)) is not None)
        first.with_suffix('.xmp').write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
        self.driver.configure(delay=0.01, entries=0)
        window.tabs.setCurrentIndex(2)
        self.driver.wait_for(lambda: window._inspection_record is not None)
        model = window.all_model
        def select_title(source):
            row = next(row for row, index in enumerate(model.rows)
                       if model.record.entries[index].name == 'Title' and
                       model.record.entries[index].source == str(source))
            window.all_table.setCurrentIndex(model.index(row, 0))
        select_title(first)
        window.all_pin.trigger()
        self.assertEqual('Remove from Browser overview', window.all_pin.text())
        select_title(first.with_suffix('.xmp'))
        self.assertEqual('Show in Browser overview', window.all_pin.text())
        window.all_pin.trigger()
        self.assertEqual('Remove from Browser overview', window.all_pin.text())
        fields = [field for field in window.overview_preferences.fields
                  if field.selector == 'XMP:XMP-dc:Image:Title']
        self.assertEqual({'Embedded XMP', 'XMP sidecar'}, {field.source for field in fields})

    def test_pins_refresh_across_open_applications_and_persist(self):
        from kim_metadata_sources import OverviewPreferences
        from PySide6.QtCore import QSettings
        window = self.window
        first = str(self.driver.paths[0])
        self.driver.wait_for(lambda: window._record(first) is not None)
        self.driver.configure(delay=0.01, entries=10)
        window.tabs.setCurrentIndex(2)
        self.driver.wait_for(lambda: window._inspection_record is not None)
        window.all_table.setCurrentIndex(window.all_model.index(0, 0))
        entry = window._inspected_entry
        window.all_pin.trigger()
        self.assertEqual('Added to Browser overview', window.statusBar().currentMessage())
        browser = self.driver.open_browser()
        self.driver.wait_for(lambda: browser._overview_record(first) is not None)
        self.assertTrue(browser.overview_preferences.is_pinned(entry, window._inspection_record))
        browser.tabs.setCurrentIndex(1)
        self.driver.wait_for(lambda: browser.grouped_model.record is not None)
        browser.tag_view_mode.setCurrentText('Flat')
        browser.table.setCurrentIndex(browser.model.index(0, 0))
        browser.pin_button.trigger()
        window.tabs.setCurrentIndex(0)
        window.tabs.setCurrentIndex(2)
        self.assertFalse(window.overview_preferences.is_pinned(entry, window._inspection_record))
        window.all_pin.trigger()
        calls = len(self.driver.calls())
        browser.tabs.setCurrentIndex(0)
        self.driver.wait_for(lambda: not browser.overview_loading.isVisible())
        self.assertTrue(browser.overview_preferences.is_pinned(entry, window._inspection_record))
        self.assertEqual(calls, len(self.driver.calls()))
        restored = OverviewPreferences(QSettings(window.overview_preferences.settings.fileName(), QSettings.IniFormat))
        self.assertTrue(restored.is_pinned(entry, window._inspection_record))
        window.close()
        browser.close()
        self.driver.wait_for(lambda: not window.isVisible() and not browser.isVisible())
        reopened = MetadataEditor(list(map(str, self.driver.paths)))
        self.driver.windows.append(reopened)
        reopened.show()
        browser = self.driver.open_browser()
        self.driver.wait_for(lambda: reopened._record(first) is not None and browser._overview_record(first) is not None)
        self.assertTrue(reopened.overview_preferences.is_pinned(entry, reopened._record(first)))
        self.assertTrue(browser.overview_preferences.is_pinned(entry, browser._overview_record(first)))

    def test_cancel_with_drafts_requires_discard_and_review_does_not_write(self):
        from PySide6.QtWidgets import QMessageBox
        window = self.window
        first = str(self.driver.paths[0])
        self.driver.wait_for(lambda: window._record(first) is not None)
        window.field_controls['title']['edit'].setText('Not written')
        with patch('kim_metadata_editor.QMessageBox.question', return_value=QMessageBox.Cancel):
            window.buttons.button(QDialogButtonBox.Cancel).click()
            self.assertTrue(window.isVisible())
            self.assertIn(first, window.drafts)
        with patch('kim_metadata_editor.QMessageBox.question', return_value=QMessageBox.Discard):
            window.buttons.button(QDialogButtonBox.Cancel).click()
            self.driver.wait_for(lambda: not window.isVisible())
        self.assertFalse(window.drafts)

    def test_loading_error_is_local_and_explicit_retry_keeps_the_preview(self):
        window = self.window
        first = str(self.driver.paths[0])
        self.driver.wait_for(lambda: window._record(first) is not None)
        self.driver.configure(delay=0.01, entries=0, fail=True)
        window.navigate(1)
        self.driver.wait_for(lambda: window.retry_metadata.isVisible())
        self.assertIn('fixture metadata failure', window.loading_label.text())
        self.driver.wait_for(lambda: window.preview.pixmap() and not window.preview.pixmap().isNull())
        self.driver.configure(delay=0.01, entries=0)
        window.retry_metadata.click()
        self.driver.wait_for(lambda: not window.loading_label.isVisible())
        self.assertFalse(window.preview.pixmap().isNull())


if __name__ == '__main__':
    unittest.main()
