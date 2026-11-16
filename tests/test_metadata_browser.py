"""Progressive Browser loading through real Qt and an external ExifTool fixture."""
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src/bin')]
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from kim_metadata_browser import MetadataBrowser, read_thumbnail
from support import Workspace
from metadata_integrity import sha256_noatime


class MetadataBrowserLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.paths = [self.workspace.jpeg(f'photos/{name}') for name in ('雪 first.jpg', '-second.jpg', 'third.jpg')]
        self.log = self.workspace.control / 'exiftool.jsonl'
        self.config = self.workspace.control / 'metadata-config.json'
        self.configure(delay=0.5, entries=25000)
        tool = self.workspace.bin / 'exiftool'
        tool.unlink()
        tool.write_text('#!' + sys.executable + '\n' + '''import os,sys,json,time,fcntl
from pathlib import Path
config=json.loads(Path(os.environ['BROWSER_TEST_CONFIG']).read_text())
full='-all:all' in sys.argv
inode=os.fstat(0).st_ino
assert fcntl.fcntl(0,fcntl.F_GETFL)&os.O_NOATIME
with Path(os.environ['BROWSER_TEST_LOG']).open('a') as stream:
    stream.write(json.dumps({'full':full,'inode':inode,'args':sys.argv[1:]})+'\\n')
time.sleep(config['delay'])
with Path(os.environ['BROWSER_TEST_LOG']).with_suffix('.finished').open('a') as stream:
    stream.write(json.dumps({'full':full,'inode':inode})+'\\n')
if config.get('fail'):
    print(json.dumps([{'SourceFile':'-','ExifTool:Other:Error':'fixture metadata failure'}]))
    sys.exit(1)
if config.get('broken_json'):
    print('{}')
    sys.exit(0)
doc={'SourceFile':'-','XMP:XMP-dc:Image:Title':{'id':'title','val':'title:'+str(inode)},
     'File:System:Other:FileType':{'id':'FileType','val':'JPEG'}}
doc.update(config.get('metadata',{}))
if full:
    for i in range(config['entries']): doc['MakerNotes:Google:Image:Field'+str(i)]={'id':str(i),'val':i}
    if config.get('structured'):
        doc['MakerNotes:Google:Image:Structure']={'id':'structure','val':{'values':list(range(3000)),'tail':'needle-at-the-end'}}
print(json.dumps([doc]))
''')
        tool.chmod(0o755)
        env = {'PATH': str(self.workspace.bin) + os.pathsep + os.environ.get('PATH', ''),
               'BROWSER_TEST_CONFIG': str(self.config), 'BROWSER_TEST_LOG': str(self.log)}
        environment = patch.dict(os.environ, env)
        environment.start()
        self.addCleanup(environment.stop)
        settings = QSettings(str(self.workspace.control / 'browser.ini'), QSettings.IniFormat)
        preferences = patch('kim_metadata_browser.QSettings', return_value=settings)
        preferences.start()
        self.addCleanup(preferences.stop)
        shared_preferences = patch('kim_metadata_sources.QSettings', return_value=settings)
        shared_preferences.start()
        self.addCleanup(shared_preferences.stop)
        self.windows = []
        self.addCleanup(self.close_windows)

    def configure(self, **values):
        self.config.write_text(json.dumps(values))

    def wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition():
            self.app.processEvents()
            if time.monotonic() >= deadline:
                self.fail('Browser condition timed out')
            time.sleep(0.002)
        self.app.processEvents()

    def open_browser(self):
        window = MetadataBrowser([str(path) for path in self.paths])
        self.windows.append(window)
        window.show()
        return window

    def close_windows(self):
        for window in self.windows:
            window.close()
        self.wait_for(lambda: all(not window.isVisible() for window in self.windows))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_preview_is_visible_while_metadata_is_still_loading(self):
        window = self.open_browser()
        self.wait_for(lambda: not window.preview.image.isNull())
        self.assertFalse(window.records)
        self.assertIn('Loading metadata', window.status_summary.text())
        self.assertLessEqual(len(self.calls()), 1)

    def test_list_thumbnails_arrive_without_selection_and_do_not_repeat(self):
        self.configure(delay=0.01, entries=0)
        window = self.open_browser()
        heights = [window.image_list.sizeHintForRow(row) for row in range(len(self.paths))]
        self.wait_for(lambda: all(not window.image_list.item(row).icon().isNull() for row in range(len(self.paths))))
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        self.assertEqual(0, window.image_list.currentRow())
        self.assertEqual(1, len(self.calls()))
        self.assertEqual(heights, [window.image_list.sizeHintForRow(row) for row in range(len(self.paths))])
        self.wait_for(lambda: window.thumbnail_worker is None)
        with patch('kim_metadata_browser.read_thumbnail', side_effect=AssertionError('Cached thumbnail reread')):
            window._pump_thumbnails()
            self.app.processEvents()
        for path in self.paths:
            self.assertIsNotNone(window.thumbnails.get(str(path)))

    def test_thumbnail_queue_preserves_jpeg_png_and_gif_sources(self):
        import base64
        from PySide6.QtGui import QImage
        png = self.paths[0].with_name('image.png')
        image = QImage(40, 20, QImage.Format_RGB32)
        image.fill(0xff339966)
        self.assertTrue(image.save(str(png)))
        gif = self.paths[0].with_name('image.gif')
        gif.write_bytes(base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'))
        paths = [self.paths[0], png, gif]
        def signature(path):
            info = path.stat()
            return sha256_noatime(path), info.st_size, info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns
        before = {path: signature(path) for path in paths}
        window = MetadataBrowser(list(map(str, paths)))
        self.windows.append(window)
        window.show()
        self.wait_for(lambda: all(not window.image_list.item(row).icon().isNull() for row in range(3)))
        self.assertEqual(before, {path: signature(path) for path in paths})

    def test_adding_images_starts_thumbnails_when_the_current_preview_is_cached(self):
        self.configure(delay=0.01, entries=0)
        window = MetadataBrowser([str(self.paths[0])])
        self.windows.append(window)
        window.show()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None and
                      not window.preview_workers and window.thumbnail_worker is None)
        calls = len(self.calls())
        window.set_images(list(map(str, self.paths)))
        self.wait_for(lambda: all(not window.image_list.item(row).icon().isNull() for row in range(3)))
        self.assertEqual(0, window.image_list.currentRow())
        self.assertEqual(calls, len(self.calls()))

    def test_overview_loading_and_show_empty_fields(self):
        from PySide6.QtWidgets import QLabel
        window = self.open_browser()
        self.assertTrue(window.overview_loading.isVisible())
        self.assertEqual('Loading metadata…', window.overview_loading.text())
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        self.wait_for(lambda: not window.overview_loading.isVisible())
        labels = lambda: [label.text() for label in window.overview_body.findChildren(QLabel) if label.isVisible()]
        self.assertNotIn('Creator', labels())
        calls = len(self.calls())
        window.show_empty.setChecked(True)
        self.app.processEvents()
        self.assertIn('Creator', labels())
        self.assertIn('Not present', labels())
        self.assertEqual(calls, len(self.calls()))

    def test_overview_fields_reflow_and_sections_expand_without_overlap(self):
        from PySide6.QtWidgets import QToolButton
        self.configure(delay=0.01, entries=0, metadata={
            'EXIF:IFD0:Image:Make': {'id': 'Make', 'val': 'Camera maker'},
            'EXIF:IFD0:Image:Model': {'id': 'Model', 'val': 'Camera model'},
            'EXIF:ExifIFD:Image:ISO': {'id': 'ISO', 'val': 100},
            'EXIF:ExifIFD:Image:FNumber': {'id': 'FNumber', 'val': 2.8}})
        window = self.open_browser()
        window.resize(1400, 900)
        self.wait_for(lambda: not window.overview_loading.isVisible())
        window.show_empty.setChecked(True)
        self.app.processEvents()
        cards = window.overview_body.findChildren(type(window.overview_body), 'overviewField')
        self.assertTrue(cards, 'Overview must expose field containers for native layout')
        self.assertGreater(len({card.mapTo(window.overview_body, card.rect().topLeft()).x()
                               for card in cards if card.isVisible()}), 1)
        calls = len(self.calls())
        for width in (1000, 1400, 900):
            window.resize(width, 800)
            for heading in window.overview_body.findChildren(QToolButton):
                if heading.isCheckable() and heading.isVisible():
                    for _ in range(3):
                        heading.click()
                        self.app.processEvents()
                    heading.setChecked(True)
            self.app.processEvents()
            cards = [card for card in cards if card.isVisible()]
            rects = [(card, card.geometry().translated(card.parentWidget().mapTo(window.overview_body, card.parentWidget().rect().topLeft())))
                     for card in cards]
            for index, (card, rect) in enumerate(rects):
                self.assertLessEqual(rect.bottom(), window.overview_body.height())
                self.assertFalse(any(rect.intersects(other) for _widget, other in rects[index + 1:]))
        self.assertEqual(calls, len(self.calls()))

    def test_overview_details_control_is_native_and_inspector_is_readable(self):
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QToolButton, QLabel
        self.configure(delay=0.01, entries=0)
        window = self.open_browser()
        self.wait_for(lambda: not window.overview_loading.isVisible())
        buttons = [button for button in window.overview_body.findChildren(QToolButton)
                   if button.toolTip() == 'View field details']
        self.assertTrue(buttons)
        self.assertFalse(buttons[0].autoRaise())
        self.assertEqual(Qt.StrongFocus, buttons[0].focusPolicy())
        captured = []
        def inspect():
            dialog = self.app.activeModalWidget()
            captured.extend(label.text() for label in dialog.findChildren(QLabel))
            dialog.reject()
        QTimer.singleShot(0, inspect)
        buttons[0].click()
        self.assertIn('Qualified identifier', captured)
        self.assertIn('Title', captured)

    def test_location_section_visibility_is_restored_in_a_new_window(self):
        from PySide6.QtWidgets import QToolButton
        self.configure(delay=0.01, entries=0)
        window = self.open_browser()
        self.wait_for(lambda: not window.overview_loading.isVisible())
        window.show_empty.setChecked(True)
        heading = next(button for button in window.overview_body.findChildren(QToolButton) if button.text() == 'Location')
        heading.setChecked(False)
        second = self.open_browser()
        self.wait_for(lambda: not second.overview_loading.isVisible())
        second.show_empty.setChecked(True)
        heading = next(button for button in second.overview_body.findChildren(QToolButton) if button.text() == 'Location')
        self.assertFalse(heading.isChecked())

    def test_structured_inspector_fetches_every_value_without_expanding_by_default(self):
        from kim_metadata_browser import MetadataDetailsDialog
        from kim_metadata_reader import MetadataEntry
        values = list(range(3000))
        original = {'values': values, 'tail': 'Preserved'}
        entry = MetadataEntry('Values', ('XMP', 'XMP-test'), 'Values', original, str(self.paths[0]), 'XMP:XMP-test:Values')
        dialog = MetadataDetailsDialog([entry])
        self.windows.append(dialog)
        dialog.show()
        model = dialog.structure.model()
        root = model.index(0, 0)
        self.assertFalse(dialog.structure.isExpanded(root))
        self.assertEqual(0, model.rowCount(root))
        dialog.structure.expand(root)
        nested = model.index(0, 0, root)
        dialog.structure.expand(nested)
        def scroll():
            dialog.structure.scrollToBottom()
            return model.rowCount(nested) == len(values)
        self.wait_for(scroll)
        dialog.raw_copy.click()
        self.assertEqual(original, json.loads(self.app.clipboard().text()))

    def test_inspector_raw_copy_preserves_empty_boolean_and_numeric_types(self):
        from kim_metadata_browser import MetadataDetailsDialog
        from kim_metadata_reader import MetadataEntry
        for value in (None, False, 123, {'fr': 'Français'}):
            entry = MetadataEntry('Value', ('XMP',), 'Value', value, str(self.paths[0]), 'XMP:Value')
            dialog = MetadataDetailsDialog([entry])
            dialog.copy_raw()
            copied = json.loads(self.app.clipboard().text())
            self.assertEqual(value, copied)
            self.assertIs(type(value), type(copied))
            dialog.close()

    def test_overview_pinning_persists_exact_identity_and_controls_selective_requests(self):
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        first = str(self.paths[0])
        self.wait_for(lambda: window._overview_record(first) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        window.tag_view_mode.setCurrentText('Flat')
        window.table.setCurrentIndex(window.model.index(4, 0))
        selected = window.selected_entry
        window.pin_button.trigger()
        field = window.overview_preferences.fields[-1]
        self.assertEqual(selected.qualified_name, field.selector)
        self.assertIn(selected.qualified_name, window.overview_preferences.selectors)
        self.assertEqual('Remove from overview', window.pin_button.text())
        from kim_metadata_sources import OverviewPreferences
        self.assertEqual(window.overview_preferences.fields, OverviewPreferences(window.overview_preferences.settings).fields)
        window.tabs.setCurrentIndex(0)
        window.image_list.setCurrentRow(1)
        second = str(self.paths[1])
        self.wait_for(lambda: window._overview_record(second) is not None)
        self.assertIn('-' + selected.qualified_name, self.calls()[-1]['args'])

    def test_row_pin_mouse_and_keyboard_preserve_selection_without_extraction(self):
        from PySide6.QtCore import QPoint, QPointF, Qt, QEvent
        from PySide6.QtGui import QMouseEvent, QKeyEvent
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        window.tag_view_mode.setCurrentText('Flat')
        original = window.model.index(0, 0)
        target = window.model.index(4, 0)
        window.table.setCurrentIndex(original)
        entry = target.data(Qt.UserRole)
        calls = len(self.calls())
        rect = window.table.visualRect(target)
        point = QPointF(rect.topLeft() + QPoint(10, rect.height() // 2))
        for event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            self.app.sendEvent(window.table.viewport(), QMouseEvent(event_type, point, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertTrue(window.overview_preferences.is_pinned(entry, window.model.record))
        self.assertEqual(original, window.table.currentIndex())
        window.table.setCurrentIndex(target)
        self.app.sendEvent(window.table, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
        self.assertFalse(window.overview_preferences.is_pinned(entry, window.model.record))
        self.assertEqual(calls, len(self.calls()))

    def test_pin_context_menu_rejects_a_model_reset_while_open(self):
        from PySide6.QtCore import QTimer
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        window.tag_view_mode.setCurrentText('Flat')
        before = list(window.overview_preferences.fields)
        index = window.model.index(4, 0)
        def reset_model():
            menu = self.app.activePopupWidget()
            window.model.set_record(window.model.record, list(range(10, 30)))
            menu.actions()[0].trigger()
            menu.close()
        QTimer.singleShot(0, reset_model)
        window.table.itemDelegateForColumn(0).context_menu(window.table.visualRect(index).center())
        self.assertEqual(before, window.overview_preferences.fields)

    def test_overview_configuration_search_reorder_remove_defaults_and_validation(self):
        from kim_metadata_browser import OverviewFieldsDialog
        from kim_metadata_sources import OverviewPreferences, PINNED_DEFAULTS, OverviewField
        window = self.open_browser()
        dialog = OverviewFieldsDialog(window.overview_preferences, window)
        dialog.search.setText('white balance')
        self.assertEqual(1, dialog.catalog.count())
        dialog.catalog.setCurrentRow(0)
        dialog.add()
        self.assertEqual('WhiteBalance', dialog.fields[-1].selector)
        dialog.selected.setCurrentRow(len(dialog.fields) - 1)
        dialog.move(-1)
        self.assertEqual('WhiteBalance', dialog.fields[-2].selector)
        dialog.save()
        restored = OverviewPreferences(window.overview_preferences.settings)
        self.assertEqual(dialog.fields, restored.fields)
        self.assertIn('WhiteBalance', restored.selectors)
        with self.assertRaises(ValueError):
            restored.save([OverviewField('-overwrite_original', 'Unsafe')])
        dialog.remove()
        self.assertFalse(any(field.selector == 'WhiteBalance' for field in dialog.fields))
        dialog.defaults()
        self.assertEqual(list(PINNED_DEFAULTS), dialog.fields)

    def test_malformed_saved_overview_fields_fall_back_to_defaults(self):
        from kim_metadata_sources import OverviewPreferences, PINNED_DEFAULTS
        window = self.open_browser()
        for value in ('[1]', '{"unexpected":true}', '[{"selector":1}]'):
            window.overview_preferences.settings.setValue(OverviewPreferences.KEY, value)
            self.assertEqual(list(PINNED_DEFAULTS), OverviewPreferences(window.overview_preferences.settings).fields)

    def test_pinned_technical_field_keeps_embedded_and_sidecar_roles_distinct(self):
        from kim_metadata_reader import MetadataRecord, MetadataEntry
        from kim_metadata_sources import OverviewPreferences
        window = self.open_browser()
        prefs = OverviewPreferences(window.overview_preferences.settings)
        path = str(self.paths[0])
        embedded = MetadataEntry('Size', ('File', 'System'), 'Size', 123, path, 'File:System:Size')
        sidecar = MetadataEntry('Size', ('File', 'System'), 'Size', 456, path + '.xmp', 'File:System:Size')
        record = MetadataRecord(path, [embedded, sidecar])
        prefs.toggle_entry(embedded, record)
        self.assertTrue(prefs.is_pinned(embedded, record))
        self.assertFalse(prefs.is_pinned(sidecar, record))
        self.assertEqual([embedded], prefs.fields[-1].entries(record))
        prefs.toggle_entry(sidecar, record)
        self.assertEqual([sidecar], prefs.fields[-1].entries(record))

    def test_qualified_overview_comparison_retains_only_configured_source_and_language(self):
        from kim_metadata_reader import MetadataRecord, MetadataEntry
        from kim_metadata_sources import OverviewField
        window = self.open_browser()
        path = str(self.paths[0])
        window.overview_preferences.save([OverviewField('XMP:Title', 'French title', source='Embedded XMP', language='fr')])
        entries = [MetadataEntry('Title', ('XMP', 'XMP-dc'), 'Title', text, source,
                                'XMP:XMP-dc:Title', language)
                   for text, source, language in (('English', path, 'en'), ('Français', path, 'fr'),
                                                  ('Sidecar', path + '.xmp', 'fr'))]
        selected = window.overview_preferences.select_record(MetadataRecord(path, entries))
        self.assertEqual(['Français'], [entry.value for entry in selected.entries])

    def test_explicit_empty_is_distinct_from_absent_when_empty_fields_are_shown(self):
        from PySide6.QtWidgets import QLabel
        self.configure(delay=0.01, entries=0, metadata={
            'XMP:XMP-dc:Image:Title': {'id': 'title', 'val': ''}})
        window = self.open_browser()
        self.wait_for(lambda: not window.overview_loading.isVisible())
        labels = lambda: [label.text() for label in window.overview_body.findChildren(QLabel) if label.isVisible()]
        self.assertNotIn('Title', labels())
        window.show_empty.setChecked(True)
        self.app.processEvents()
        self.assertIn('Explicitly empty', labels())
        self.assertIn('Not present', labels())

    def test_compare_slots_are_independent_of_navigation_and_swap(self):
        self.configure(delay=0.1, entries=1000)
        window = self.open_browser()
        window.tabs.setCurrentIndex(2)
        window.assign_comparison(0, str(self.paths[0]))
        window.assign_comparison(1, str(self.paths[1]))
        self.assertEqual(tuple(map(str, self.paths[:2])), window.compared_paths)
        self.assertFalse(window.preview.isVisible())
        self.wait_for(lambda: not window.comparison_image_1_header.preview.image.isNull() and
                      not window.comparison_image_2_header.preview.image.isNull())
        window.image_list.setCurrentRow(2)
        self.assertEqual(tuple(map(str, self.paths[:2])), window.compared_paths)
        window.swap_button.click()
        self.assertEqual((str(self.paths[1]), str(self.paths[0])), window.compared_paths)
        window.tabs.setCurrentIndex(0)
        self.assertTrue(window.preview.isVisible())
        window.tabs.setCurrentIndex(2)
        self.assertEqual((str(self.paths[1]), str(self.paths[0])), window.compared_paths)

    def test_overview_uses_one_preferred_date_position_and_configured_altitude_units(self):
        from PySide6.QtWidgets import QLabel
        metadata = {
            'EXIF:ExifIFD:Time:DateTimeOriginal': {'val': '2026:09:15 10:02:01'},
            'EXIF:ExifIFD:Time:CreateDate': {'val': '2025:01:01 00:00:00'},
            'EXIF:GPS:Location:GPSLatitude': {'val': '45 deg 30\' 0.00" N'},
            'EXIF:GPS:Location:GPSLongitude': {'val': '73 deg 30\' 0.00" W'},
            'EXIF:GPS:Location:GPSAltitude': {'val': '100 m'},
            'Composite:Composite:Location:GPSAltitude': {'val': '100 m Above Sea Level'},
        }
        self.configure(delay=0.01, entries=0, metadata={key: dict(value, id=key.rsplit(':', 1)[-1])
                                                     for key, value in metadata.items()})
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.workspace.control / 'config')}), \
                patch('kim_location_ui.system_units', return_value='imperial'):
            window = self.open_browser()
            self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
            self.wait_for(lambda: not window.overview_loading.isVisible())
            labels = [label.text() for label in window.overview_body.findChildren(QLabel) if label.isVisible()]
            self.assertIn('328.1 ft', labels)
            self.assertIn('45.5000000° N, 73.5000000° W', labels)
            self.assertEqual(1, sum('2026' in text for text in labels))
            self.assertFalse(any('2025' in text for text in labels))
            self.assertEqual(1, labels.count('328.1 ft'))

    def test_overview_is_selective_and_all_tags_is_lazy_and_virtual(self):
        self.configure(delay=0.02, entries=25000)
        window = self.open_browser()
        first = str(self.paths[0])
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        self.assertEqual(1, len(self.calls()))
        self.assertFalse(self.calls()[0]['full'])
        self.assertEqual(self.paths[0].stat().st_ino, self.calls()[0]['inode'])
        self.assertFalse(window.records)
        self.assertEqual(0, window.model.rowCount())
        self.assertEqual(0, window.grouped_model.rowCount())
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.records.get(first) is not None)
        self.assertEqual(1, sum(call['full'] for call in self.calls()))
        self.assertEqual(25004, len(window.records[first].entries))
        self.assertEqual(25004, sum(len(rows) for _family, rows in window.grouped_model.families))
        self.assertEqual(0, window.model.rowCount())
        window.tag_view_mode.setCurrentText('Flat')
        self.assertLess(window.model.rowCount(), 25004)
        while window.model.canFetchMore():
            window.model.fetchMore()
        self.assertEqual(25004, window.model.rowCount())
        self.assertEqual(0, window.grouped_model.rowCount())
        window.table.setCurrentIndex(window.model.index(4, 0))
        self.assertIsNotNone(window.selected_entry)
        self.assertTrue(window.copy_button.isEnabled())
        calls = len(self.calls())
        window.tabs.setCurrentIndex(0)
        window.tabs.setCurrentIndex(1)
        self.assertEqual(calls, len(self.calls()))

    def test_show_empty_fields_remains_usable_after_selective_loading(self):
        self.configure(delay=0.01, entries=0)
        window = self.open_browser()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        window.show_empty.setChecked(True)
        self.app.processEvents()
        self.assertTrue(window.show_empty.isChecked())
        self.assertGreater(window.overview_layout.count(), 0)

    def test_structured_values_are_bounded_inline_and_searchable_in_full(self):
        self.configure(delay=0.01, entries=1000, structured=True)
        window = self.open_browser()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        window.tag_view_mode.setCurrentText('Flat')
        window.search.setText('needle-at-the-end')
        self.wait_for(lambda: window._tag_filter_worker is None and window.model.rowCount() == 1)
        self.assertLessEqual(len(window.model.index(0, 1).data()), 241)
        self.assertEqual('Structured value (2 elements)', window.model.index(0, 1).data())
        window.table.setCurrentIndex(window.model.index(0, 0))
        self.assertEqual('Structured value (2 elements)', window.value_detail.toPlainText())
        window.copy_value()
        self.assertIn('needle-at-the-end', self.app.clipboard().text())
        self.assertEqual(list(range(3000)), window.selected_entry.value['values'])
        self.assertEqual(26, window.table.rowHeight(0))

    def test_cancel_all_tags_and_retry(self):
        self.configure(delay=0.3, entries=1000)
        window = self.open_browser()
        first = str(self.paths[0])
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: any(call['full'] for call in self.calls()))
        self.assertTrue(window.all_tags_progress.isVisible())
        window.all_tags_cancel.click()
        self.wait_for(lambda: window.worker is None)
        self.assertFalse(window.records)
        self.assertIn('canceled', window.all_tags_status.text())
        window.all_tags_retry.click()
        self.wait_for(lambda: window.records.get(first) is not None)
        self.assertEqual(2, sum(call['full'] for call in self.calls()))

    def test_explicit_all_tags_supersedes_pending_overview(self):
        self.configure(delay=1.5, entries=100)
        window = self.open_browser()
        self.wait_for(lambda: bool(self.calls()))
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: any(call['full'] for call in self.calls()))
        finished = self.log.with_suffix('.finished')
        completed = [json.loads(line) for line in finished.read_text().splitlines()] if finished.exists() else []
        self.assertFalse(any(not call['full'] for call in completed))
        self.wait_for(lambda: window._full_record(str(self.paths[0])) is not None)

    def test_rapid_navigation_rejects_obsolete_results_and_bounds_workers(self):
        self.configure(delay=0.3, entries=1000)
        window = self.open_browser()
        self.wait_for(lambda: bool(self.calls()))
        for row in (1, 0, 2, 1, 2):
            window.image_list.setCurrentRow(row)
            self.app.processEvents()
            self.assertLessEqual(len(window.preview_workers), 2)
        current = str(self.paths[2])
        self.wait_for(lambda: window.overview_records.get(current) is not None)
        self.assertEqual(self.paths[2].name, window.filename.text())
        self.assertIn('title:' + str(self.paths[2].stat().st_ino),
                      [entry.value for entry in window.overview_records[current].entries])
        self.assertNotIn(str(self.paths[0]), window.overview_records)
        self.assertFalse(window.preview.image.isNull())

    def test_cached_navigation_and_sidecar_change_invalidation(self):
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        first, second = map(str, self.paths[:2])
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        window.image_list.setCurrentRow(1)
        self.wait_for(lambda: window.overview_records.get(second) is not None)
        calls = len(self.calls())
        window.image_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(calls, len(self.calls()))
        self.paths[0].with_suffix('.xmp').write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
        window.image_list.setCurrentRow(1)
        window.image_list.setCurrentRow(0)
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        self.assertGreater(len(self.calls()), calls)
        self.assertEqual([str(self.paths[0].with_suffix('.xmp'))], window.overview_records[first].sidecars)
        calls = len(self.calls())
        self.paths[0].with_suffix('.xmp').write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/">changed</x:xmpmeta>')
        window.image_list.setCurrentRow(1)
        window.image_list.setCurrentRow(0)
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        self.assertGreater(len(self.calls()), calls)

    def test_source_change_invalidates_preview_and_metadata(self):
        self.configure(delay=0.02, entries=1000)
        window = self.open_browser()
        first = str(self.paths[0])
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        self.wait_for(lambda: window._preview_for(first) is not None)
        calls = len(self.calls())
        old_stamp = window.previews._items[first][0]
        with self.paths[0].open('ab') as stream:
            stream.write(b'changed fixture')
        window.update_current()
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        self.wait_for(lambda: window._preview_for(first) is not None)
        self.assertGreater(len(self.calls()), calls)
        self.assertNotEqual(old_stamp, window.previews._items[first][0])

    def test_abandoned_full_request_cannot_populate_next_image(self):
        self.configure(delay=0.2, entries=1000)
        window = self.open_browser()
        first, second = map(str, self.paths[:2])
        self.wait_for(lambda: window.overview_records.get(first) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: any(call['full'] for call in self.calls()))
        window.image_list.setCurrentRow(1)
        self.wait_for(lambda: window._full_record(second) is not None)
        self.assertNotIn(first, window.records)
        self.assertEqual(second, window.grouped_model.record.path)
        self.assertEqual(self.paths[1].name, window.filename.text())

    def test_cached_metadata_waits_for_an_evicted_preview(self):
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        first, second = map(str, self.paths[:2])
        self.wait_for(lambda: window._overview_record(first) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        window.image_list.setCurrentRow(1)
        self.wait_for(lambda: window._full_record(second) is not None)
        self.wait_for(lambda: window.worker is None and not window.preview_workers)
        del window.previews[first]
        def slow_decode(*args, **kwargs):
            time.sleep(0.2)
            return read_thumbnail(*args, **kwargs)
        calls = len(self.calls())
        with patch('kim_metadata_browser.read_thumbnail', side_effect=slow_decode):
            window.image_list.setCurrentRow(0)
            self.app.processEvents()
            self.assertFalse(window.preview.image.isNull())
            self.assertLessEqual(window.preview.image.width(), 96)
            self.assertIsNone(window.grouped_model.record)
            self.assertEqual((first, id(None)), window._displayed_overview)
            self.wait_for(lambda: not window.preview.image.isNull())
            self.wait_for(lambda: window.grouped_model.record is not None)
        self.assertEqual(first, window.grouped_model.record.path)
        self.assertEqual(calls, len(self.calls()))

    def test_scrolling_reveals_every_incrementally_exposed_row_in_both_views(self):
        self.configure(delay=0.01, entries=1000)
        window = self.open_browser()
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        group = next(row for row, (family, _rows) in enumerate(window.grouped_model.families)
                     if family == 'MakerNotes')
        parent = window.grouped_model.index(group, 0)
        def scroll_to_last_grouped_row():
            window.grouped_tree.scrollToBottom()
            return window.grouped_model.rowCount(parent) == 1000
        self.wait_for(scroll_to_last_grouped_row)
        window.tag_view_mode.setCurrentText('Flat')
        def scroll_to_last_row():
            window.table.scrollToBottom()
            return window.model.rowCount() == len(window.model.record.entries)
        self.wait_for(scroll_to_last_row)
        self.assertEqual(1004, window.model.rowCount())

    def test_cache_limits_and_source_integrity(self):
        self.configure(delay=0.01, entries=1000)
        def signature(path):
            info = path.stat()
            return (sha256_noatime(path), info.st_size, info.st_atime_ns,
                    info.st_mtime_ns, info.st_ctime_ns)
        before = {path: signature(path) for path in self.paths}
        window = self.open_browser()
        window.previews.limit = window.overview_records.limit = window.records.limit = 1
        for row, path in enumerate(self.paths):
            window.image_list.setCurrentRow(row)
            self.wait_for(lambda: window.overview_records.get(str(path)) is not None)
            window.tabs.setCurrentIndex(1)
            self.wait_for(lambda: window.records.get(str(path)) is not None)
            window.tabs.setCurrentIndex(0)
            for cache in (window.records, window.overview_records, window.previews):
                self.assertLessEqual(len(cache), 1)
                self.assertLessEqual(cache.bytes, cache.budget)
        self.assertEqual(before, {path: signature(path) for path in before})

    def test_metadata_failure_does_not_remove_the_preview(self):
        self.configure(delay=0.1, entries=0, fail=True)
        window = self.open_browser()
        self.wait_for(lambda: 'fixture metadata failure' in window.notice.text())
        self.assertFalse(window.preview.image.isNull())

    def test_extraction_exception_is_local_and_does_not_retry_forever(self):
        self.configure(delay=0.05, entries=0, broken_json=True)
        window = self.open_browser()
        self.wait_for(lambda: 'unexpected JSON structure' in window.notice.text())
        self.wait_for(lambda: window.worker is None)
        self.assertEqual(1, len(self.calls()))
        self.assertFalse(window.preview.image.isNull())

    def test_explicit_retry_recovers_metadata_without_losing_preview(self):
        self.configure(delay=0.01, entries=0, fail=True)
        window = self.open_browser()
        self.wait_for(lambda: window.overview_retry.isVisible())
        self.configure(delay=0.01, entries=0)
        window.overview_retry.click()
        self.wait_for(lambda: not window.overview_loading.isVisible())
        self.assertFalse(window.preview.image.isNull())
        self.assertEqual(2, len(self.calls()))

    def test_records_larger_than_cache_budgets_remain_accessible_without_reload_loops(self):
        self.configure(delay=0.02, entries=1000)
        window = self.open_browser()
        for cache in (window.previews, window.overview_records, window.records):
            cache.budget = 1
        self.wait_for(lambda: window._overview_record(str(self.paths[0])) is not None)
        self.wait_for(lambda: not window.preview.image.isNull())
        window.tabs.setCurrentIndex(1)
        self.wait_for(lambda: window.grouped_model.record is not None)
        self.wait_for(lambda: window.worker is None and not window.preview_workers)
        self.assertEqual(1004, len(window.grouped_model.record.entries))
        self.assertEqual(2, len(self.calls()))
        for cache in (window.previews, window.overview_records, window.records):
            self.assertLessEqual(cache.bytes, cache.budget)

    def test_symlink_selection_is_not_resolved_before_protected_readers(self):
        link = self.paths[0].with_name('linked.jpg')
        link.symlink_to(self.paths[0])
        before = link.lstat()
        window = MetadataBrowser([str(link)])
        self.windows.append(window)
        window.show()
        self.wait_for(lambda: 'symbolic link' in window.notice.text())
        self.assertEqual([], self.calls())
        self.assertEqual(str(link), window.paths[0])
        self.assertEqual(before, link.lstat())


if __name__ == '__main__':
    unittest.main()
