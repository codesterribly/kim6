"""Central Settings metadata controls through native widgets and shared storage."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QDialogButtonBox, QListWidget, QPushButton, QSpinBox, QTabWidget
import kim_settings_dialog as settings
from kim_metadata_sources import MetadataSourcePreferences


class MetadataSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='kimng-central-settings-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'settings.conf'
        self.about = self.root / 'ABOUT'
        self.about.write_text('Test about text')
        self.metadata_path = self.root / 'metadata.ini'
        self.preferences = self.read_preferences()

    def read_preferences(self):
        return MetadataSourcePreferences(QSettings(str(self.metadata_path), QSettings.IniFormat))

    def open_settings(self):
        dialog = settings.create_dialog(self.about, self.path, self.preferences)
        self.addCleanup(dialog.close)
        self.tabs = dialog.findChild(QTabWidget)
        index = next(i for i in range(self.tabs.count()) if self.tabs.tabText(i) == 'Metadata')
        self.tabs.setCurrentIndex(index)
        self.tab = self.tabs.widget(index)
        self.sources = self.tab.findChild(QListWidget)
        self.sync = self.tab.findChild(QCheckBox)
        self.buttons = dialog.findChild(QDialogButtonBox)
        return dialog

    def click(self, parent, text):
        next(button for button in parent.findChildren(QPushButton) if button.text() == text).click()

    def order(self):
        from PySide6.QtCore import Qt
        sources = self.tab.sources
        result = []
        for index in range(sources.count()):
            item = sources.item(index)
            canonical = item.data(Qt.UserRole)
            self.assertEqual(f"{index + 1}. {canonical}", item.text())
            result.append(canonical)
        return tuple(result)

    def test_save_reordered_priority_keeps_general_settings_byte_for_byte(self):
        values = {**settings.DEFAULTS, 'KIM_WEB_QUALITY_JPEG': '83',
                  'KIM_LOCATION_UNITS': settings.system_location_units(),
                  'KIM_COPYRIGHT_CREATOR': 'Photographer'}
        settings.save_settings(self.path, values)
        before = self.path.read_bytes()
        dialog = self.open_settings()
        self.assertEqual(('Embedded XMP', 'XMP sidecar', 'IPTC-IIM', 'EXIF'), self.order())
        self.assertFalse(self.sync.isChecked())
        self.sources.setCurrentRow(0)
        self.click(self.tab, 'Move down')
        self.assertEqual(('XMP sidecar', 'Embedded XMP', 'IPTC-IIM', 'EXIF'), self.order())
        self.assertEqual(('Embedded XMP', 'XMP sidecar', 'IPTC-IIM', 'EXIF'), self.read_preferences().priority)
        self.buttons.button(QDialogButtonBox.Save).click()
        self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(('XMP sidecar', 'Embedded XMP', 'IPTC-IIM', 'EXIF'), self.read_preferences().priority)
        self.assertFalse(self.read_preferences().sync_default)
        self.assertEqual(before, self.path.read_bytes())

    def test_cancel_discards_priority_sync_and_general_changes(self):
        settings.save_settings(self.path, settings.DEFAULTS)
        self.preferences.save(('EXIF', 'IPTC-IIM', 'XMP sidecar', 'Embedded XMP'), True)
        before = self.path.read_bytes(), self.metadata_path.read_bytes()
        dialog = self.open_settings()
        self.sources.setCurrentRow(0)
        self.click(self.tab, 'Move down')
        self.sync.setChecked(False)
        dialog.findChild(QSpinBox).setValue(72)
        self.buttons.button(QDialogButtonBox.Cancel).click()
        self.assertEqual(QDialog.Rejected, dialog.result())
        self.assertEqual(before, (self.path.read_bytes(), self.metadata_path.read_bytes()))

    def test_restore_defaults_only_changes_pending_metadata_then_save_applies_all_tabs(self):
        self.preferences.save(('EXIF', 'IPTC-IIM', 'XMP sidecar', 'Embedded XMP'), True)
        dialog = self.open_settings()
        quality = dialog.findChild(QSpinBox)
        quality.setValue(72)
        self.click(dialog, 'Restore Defaults')
        self.assertEqual(('Embedded XMP', 'XMP sidecar', 'IPTC-IIM', 'EXIF'), self.order())
        self.assertFalse(self.sync.isChecked())
        self.assertEqual(72, quality.value())
        self.assertEqual(('EXIF', 'IPTC-IIM', 'XMP sidecar', 'Embedded XMP'), self.read_preferences().priority)
        self.assertTrue(self.read_preferences().sync_default)
        self.tabs.setCurrentIndex(0)
        self.buttons.button(QDialogButtonBox.Save).click()
        self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(('Embedded XMP', 'XMP sidecar', 'IPTC-IIM', 'EXIF'), self.read_preferences().priority)
        self.assertFalse(self.read_preferences().sync_default)
        self.assertEqual('72', settings.load_settings(self.path)['KIM_WEB_QUALITY_JPEG'])

    def test_deliberate_sync_default_round_trip_preserves_pinned_fields(self):
        from kim_metadata_sources import OverviewField, OverviewPreferences
        pins = [OverviewField('Rating', 'My rating'), OverviewField('Title', 'My title')]
        OverviewPreferences(self.preferences.settings).save(pins)
        dialog = self.open_settings()
        self.sync.setChecked(True)
        self.buttons.button(QDialogButtonBox.Save).click()
        self.assertEqual(QDialog.Accepted, dialog.result())
        restored = self.read_preferences()
        self.assertTrue(restored.sync_default)
        self.assertEqual(pins, OverviewPreferences(restored.settings).fields)
        self.assertFalse(self.path.exists(), 'Metadata-only Save must not create settings.conf')
        reopened = self.open_settings()
        self.assertTrue(self.sync.isChecked())
        self.buttons.button(QDialogButtonBox.Cancel).click()

    def test_metadata_storage_failure_stays_open_and_does_not_save_general_values(self):
        blocked = self.root / 'not-a-directory'
        blocked.write_text('Keep this file')
        self.preferences = MetadataSourcePreferences(QSettings(str(blocked / 'metadata.ini'), QSettings.IniFormat))
        dialog = self.open_settings()
        dialog.show()
        self.sync.setChecked(True)
        dialog.findChild(QSpinBox).setValue(72)
        with patch.object(settings.QMessageBox, 'critical') as error:
            self.buttons.button(QDialogButtonBox.Save).click()
        self.assertTrue(dialog.isVisible())
        self.assertFalse(self.path.exists())
        self.assertIn('write permissions', error.call_args.args[2])
        self.assertIn(str(blocked), error.call_args.args[2])
        self.assertEqual('Keep this file', blocked.read_text())

    def test_general_storage_failure_reports_partial_save_without_accepting(self):
        self.path.mkdir()
        # Reading a directory is correctly refused; replace it after loading.
        self.path.rmdir()
        dialog = self.open_settings()
        dialog.show()
        self.path.mkdir()
        dialog.findChild(QSpinBox).setValue(72)
        self.sync.setChecked(True)
        with patch.object(settings.QMessageBox, 'critical') as error:
            self.buttons.button(QDialogButtonBox.Save).click()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(self.read_preferences().sync_default)
        self.assertIn('General settings were not saved', error.call_args.args[2])
        self.path.rmdir()
        self.buttons.button(QDialogButtonBox.Save).click()
        self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual('72', settings.load_settings(self.path)['KIM_WEB_QUALITY_JPEG'])

    def test_general_restore_defaults_still_resets_legacy_location_units(self):
        settings.save_settings(self.path, {**settings.DEFAULTS, 'KIM_LOCATION_UNITS': settings.system_location_units()})
        dialog = self.open_settings()
        self.tabs.setCurrentIndex(0)
        self.click(dialog, 'Restore Defaults')
        self.buttons.button(QDialogButtonBox.Save).click()
        self.assertEqual('system', settings.load_settings(self.path)['KIM_LOCATION_UNITS'])


class MetadataSettingsActivationTests(unittest.TestCase):
    def test_central_save_reloads_open_windows_without_losing_drafts_targets_or_pins(self):
        import test_metadata_browser as browser_tests
        from kim_metadata_editor import MetadataEditor
        from kim_metadata_sources import OverviewField
        from metadata_integrity import sha256_noatime
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import QLabel

        browser_tests.MetadataBrowserLoadingTests.setUpClass()
        driver = browser_tests.MetadataBrowserLoadingTests()
        driver.setUp()
        self.addCleanup(driver.doCleanups)
        driver.configure(delay=0.01, entries=0, metadata={
            'XMP:XMP-dc:Image:Title': {'id': 'title', 'val': 'Embedded title'},
            'IPTC:IPTC:Image:ObjectName': {'id': 'ObjectName', 'val': 'Legacy title'},
            'XMP:XMP-dc:Image:Description': {'id': 'description', 'val': 'Embedded caption'},
            'IPTC:IPTC:Image:Caption-Abstract': {'id': 'Caption-Abstract', 'val': 'Legacy caption'},
        })
        sidecar = driver.paths[0].with_suffix('.xmp')
        sidecar.write_text('Disposable sidecar fixture')

        def signature(path):
            info = path.stat()
            return sha256_noatime(path), info.st_size, info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns

        before = {path: signature(path) for path in [*driver.paths, sidecar]}
        editor = MetadataEditor(list(map(str, driver.paths)))
        driver.windows.append(editor)
        self.addCleanup(editor.drafts.clear)
        self.addCleanup(editor.source_drafts.clear)
        self.addCleanup(editor.batch_sessions.clear)
        editor.show()
        path = editor.paths[0]
        driver.wait_for(lambda: editor._record(path) is not None and editor.worker is None)

        # Explicitly select a different title source via the existing chooser.
        def select_iptc():
            chooser = driver.app.activeModalWidget()
            chooser.list.setCurrentRow(next(i for i in range(chooser.list.count())
                                            if chooser.list.item(i).data(Qt.UserRole).source == 'IPTC-IIM'))
            next(button for button in chooser.findChildren(QPushButton)
                 if button.text() == 'Edit this source').click()

        QTimer.singleShot(0, select_iptc)
        editor.field_controls['title']['details'].click()
        self.assertEqual('Legacy title', editor.field_controls['title']['edit'].text())
        editor.field_controls['caption']['edit'].setPlainText('Keep this draft')
        draft = editor.drafts[path]['caption']
        explicit_targets = {path: dict(targets) for path, targets in editor.source_targets.items()}
        pins = [OverviewField('Title', 'Title')]
        editor.overview_preferences.save(pins)
        browser = driver.open_browser()
        driver.wait_for(lambda: browser._overview_record(path) is not None and browser.worker is None)
        labels = lambda: [label.text() for label in browser.overview_body.findChildren(QLabel)]
        self.assertIn('Embedded title', labels())

        about = driver.workspace.control / 'ABOUT'
        about.write_text('Test Settings')
        # A separate Settings process exercises QSettings synchronization.
        script = '''import sys
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QTabWidget, QListWidget, QCheckBox, QDialogButtonBox, QPushButton, QDialog
from kim_metadata_sources import MetadataSourcePreferences
from kim_settings_dialog import create_dialog
app = QApplication([])
preferences = MetadataSourcePreferences(QSettings(sys.argv[1], QSettings.IniFormat))
dialog = create_dialog(Path(sys.argv[2]), Path(sys.argv[3]), preferences)
tabs = dialog.findChild(QTabWidget)
tab = tabs.widget(next(i for i in range(tabs.count()) if tabs.tabText(i) == 'Metadata'))
tabs.setCurrentWidget(tab)
sources = tab.findChild(QListWidget)
sources.setCurrentRow(2)
up = next(button for button in tab.findChildren(QPushButton) if button.text() == 'Move up')
up.click(); up.click()
tab.findChild(QCheckBox).setChecked(True)
dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
assert dialog.result() == QDialog.Accepted
'''
        result = subprocess.run([sys.executable, '-B', '-c', script,
                                 editor.preferences.settings.fileName(), str(about),
                                 str(driver.workspace.control / 'settings.conf')],
                                env={**os.environ, 'PYTHONPATH': str(Path(settings.__file__).parent)},
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        driver.app.setActiveWindow(editor)
        driver.wait_for(lambda: editor.preferences.priority[0] == 'IPTC-IIM')
        driver.app.setActiveWindow(browser)
        driver.wait_for(lambda: browser.metadata_preferences.priority[0] == 'IPTC-IIM')
        self.assertIn('Legacy title', labels())
        self.assertTrue(editor.preferences.sync_default)
        self.assertTrue(browser.metadata_preferences.sync_default)
        self.assertIs(draft, editor.drafts[path]['caption'])
        self.assertEqual('Keep this draft', editor.field_controls['caption']['edit'].toPlainText())
        self.assertEqual(explicit_targets, editor.source_targets)
        self.assertEqual('Legacy title', editor.field_controls['title']['edit'].text())
        self.assertEqual(pins, editor.overview_preferences.fields)
        self.assertEqual(pins, browser.overview_preferences.fields)
        self.assertEqual(before, {path: signature(path) for path in before})
