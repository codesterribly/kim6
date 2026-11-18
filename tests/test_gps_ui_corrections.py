"""Acceptance regressions for readable GPS actions, map opt-in and PNG previews."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import struct
import zlib
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from PySide6.QtCore import Qt, QSize, QRect, QSettings
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout, QToolButton, QTableView
import kim_metadata_gps_actions as actions
import kim_location_map as maps
from kim_location_dialog import LocationDialog
from kim_photo_selection import read_thumbnail, ThumbnailWorker, PhotoPreview
from kim_metadata_browser import MetadataOverview, TagModel
from kim_metadata_sources import OverviewPreferences, MetadataSourcePreferences, OVERVIEW_DEFAULTS
from kim_settings_dialog import config_path, load_settings, save_settings
from test_metadata_gps_field_actions import entry
from kim_metadata_reader import MetadataRecord
from metadata_integrity import sha256_noatime


def signature(path):
    s=path.stat()
    return sha256_noatime(path), s.st_size, s.st_atime_ns, s.st_mtime_ns, s.st_ctime_ns


class GPSUICorrections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name, 'XDG_CACHE_HOME': self.temp.name + '/cache'})
        env.start(); self.addCleanup(env.stop)
        limit = QImageReader.allocationLimit()
        self.addCleanup(QImageReader.setAllocationLimit, limit)

    def record(self):
        return MetadataRecord('/image.jpg', [entry('GPSLatitude', 12), entry('GPSLongitude', 34),
            entry('GPSLatitudeRef', 'North'), entry('GPSLongitudeRef', 'East'), entry('GPSAltitude', 80)])

    def test_altitude_controls_show_action_text_and_own_coordinates(self):
        record = self.record()
        widget = QWidget(); layout = QHBoxLayout(widget)
        self.addCleanup(widget.deleteLater)
        field = actions.gps_field(record, record.entries[-1])
        actions.add_field_controls(layout, object(), field)
        buttons = widget.findChildren(QToolButton)
        self.assertEqual(['View on map…', 'Edit GPS'], [b.text() for b in buttons])
        self.assertEqual(Qt.ToolButtonIconOnly, buttons[0].toolButtonStyle())
        self.assertFalse(buttons[0].icon().isNull())
        self.assertEqual("View on map", buttons[0].accessibleName())
        self.assertEqual(Qt.ToolButtonTextOnly, buttons[1].toolButtonStyle())
        with patch.object(actions, 'show_field_map') as show:
            buttons[0].click()
        self.assertEqual([12, 34], show.call_args.args[2])

    def test_delegate_reserves_readable_text_without_row_widgets(self):
        view = QTableView(); model = TagModel(False, None); model.set_record(self.record()); view.setModel(model)
        self.addCleanup(view.deleteLater)
        delegate = actions.GPSActionDelegate(view, view, lambda i: actions.gps_field(model.record, i.data(Qt.UserRole)))
        index = model.index(0, 1)
        _, buttons = delegate.buttons(index, QRect(0, 0, 500, 32))
        for action, rect in buttons:
            self.assertGreaterEqual(rect.width(), view.fontMetrics().horizontalAdvance(action[0]) + 12)
        self.assertEqual([], view.findChildren(QToolButton))

    def test_overview_groups_same_representation_with_one_action_cluster(self):
        settings = QSettings(str(self.folder / 'overview.ini'), QSettings.IniFormat)
        prefs = OverviewPreferences(settings); prefs.fields = [f for f in OVERVIEW_DEFAULTS if f.label in ('GPS position', 'GPS altitude')]
        overview = MetadataOverview(MetadataSourcePreferences(settings), prefs)
        self.addCleanup(overview.deleteLater)
        overview.set_record(self.record())
        buttons = overview.findChildren(QToolButton, 'gpsFieldAction')
        self.assertEqual(['View on map…', 'Edit GPS'], [b.text() for b in buttons])

    def test_saved_map_preference_is_independent_of_cache_persistence(self):
        path = self.folder / 'map-test.jpg'
        image = QImage(8, 8, QImage.Format_RGB32); image.fill(Qt.red)
        self.assertTrue(image.save(str(path)))
        for saved in ('yes', 'no'):
            with self.subTest(saved=saved):
                settings = load_settings(config_path()); settings['KIM_LOCATION_ONLINE_MAPS'] = saved
                save_settings(config_path(), settings)
                before = config_path().read_bytes()
                dialog = LocationDialog('apply', [str(path)], 'proposal', None)
                try:
                    self.assertFalse(dialog.location_map.store.persistent)
                    self.assertEqual(saved == 'yes', dialog.location_map.store.enabled)
                    self.assertEqual(saved == 'yes', dialog.location_map.online.isHidden())
                finally:
                    dialog.reject(); dialog.deleteLater()
                for persistent in (False, True):
                    store = maps.TileStore(None, persistent=persistent)
                    store.preference_timer.stop()
                    try:
                        self.assertEqual(saved == 'yes', store.enabled)
                        store.views[self] = {(1, 0, 0)}
                        with patch.object(store, 'initialize') as initialize:
                            store.request_visible()
                        self.assertEqual(saved == 'yes', initialize.called)
                        if not persistent:
                            store.initialize()
                            self.assertIsNone(store.network.cache())
                            store.set_enabled(True)
                            self.assertEqual(before, config_path().read_bytes())
                            self.assertFalse((self.folder / 'cache').exists())
                    finally:
                        store.timer.stop(); store.deleteLater()

    def dialog(self):
        dialog = LocationDialog('report', [], 'create', {})
        dialog.timer.stop()
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_supported_png_and_jpeg_preview_with_gps_allocation_limit(self):
        self.dialog()
        for extension in ('png', 'jpg'):
            path = self.folder / ('ordinary.' + extension)
            image = QImage(3840, 2560, QImage.Format_RGB32); image.fill(Qt.red)
            self.assertTrue(image.save(str(path)))
            before = signature(path)
            preview, _ = read_thumbnail(str(path), QSize(800, 600))
            self.assertFalse(preview.isNull())
            self.assertLessEqual(preview.width(), 800)
            self.assertLessEqual(preview.height(), 600)
            self.assertEqual(before, signature(path))
        self.assertGreater(QImageReader.allocationLimit(), 0)
        self.assertLessEqual(QImageReader.allocationLimit(), 64)

    def test_large_png_fails_with_allocation_reason_and_preserves_source(self):
        self.dialog()
        # A valid 20 MP PNG: stream compressed rows without a large test bitmap.
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        compressor = zlib.compressobj()
        data = b''.join(compressor.compress(b'\0' + b'\xff' * 15000) for _ in range(4000)) + compressor.flush()
        path = self.folder / 'large.png'
        path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 5000, 4000, 8, 2, 0, 0, 0)) + chunk(b'IDAT', data) + chunk(b'IEND', b''))
        before = signature(path)
        with self.assertRaisesRegex(ValueError, '64 MiB preview allocation limit'):
            read_thumbnail(str(path), QSize(800, 600))
        self.assertEqual(before, signature(path))

    def test_failure_reason_survives_worker_and_reaches_preview(self):
        path = self.folder / 'broken.png'; path.write_bytes(b'not a PNG')
        before = signature(path)
        preview = PhotoPreview(); self.addCleanup(preview.deleteLater)
        preview.requested = str(path)
        worker = ThumbnailWorker([str(path)], QSize(80, 60), preview)
        worker.request_id = preview.request_id
        preview.worker = worker
        worker.thumbnail_ready.connect(preview.receive_preview)
        worker.run()
        self.assertIn('Unsupported image format', preview.canvas.message)
        self.assertNotIn('may lack', preview.canvas.message)
        self.assertIn('independently', preview.canvas.message)
        self.assertEqual(before, signature(path))
        preview.worker = None


if __name__ == '__main__': unittest.main()
