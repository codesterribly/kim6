"""Latest-selection previews with a real Qt worker and controlled decoding."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
import kim_photo_selection as photos


class PhotoPreviewRequests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.002)
        self.assertTrue(predicate(), 'preview did not settle')

    def exercise(self, sequence, *, fail_first=False, fail_latest=False, stop=False,
                 stale=False, close_dialog=False, expire_timer=True):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: str(Path(tmp) / (name + '.png')) for name in 'ABC'}
            for name, path in paths.items():
                image = QImage(8, 8, QImage.Format_RGB32)
                image.fill(QColor({'A': 'red', 'B': 'green', 'C': 'blue'}[name]))
                self.assertTrue(image.save(path))
            entered, release = threading.Event(), threading.Event()
            calls = []
            read = photos.read_thumbnail

            def controlled_read(path, size):
                calls.append(path)
                if len(calls) == 1:
                    entered.set()
                    if not release.wait(3): raise RuntimeError('test gate timed out')
                    if fail_first: raise ValueError('first decoder failed')
                elif fail_latest:
                    raise ValueError('latest decoder failed')
                return read(path, size)

            dialog = None
            if close_dialog:
                from kim_location_dialog import LocationDialog
                with patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}):
                    dialog = LocationDialog('report', [], 'create', {})
                dialog.timer.stop()
                preview = dialog.photo_preview
                dialog.show()
            else:
                preview = photos.PhotoPreview()
            with patch.object(photos, 'read_thumbnail', side_effect=controlled_read):
                try:
                    preview.set_path(paths['A'])
                    preview.timer.stop(); preview.start_preview()
                    self.assertTrue(entered.wait(3))
                    original = preview.worker
                    for name in sequence:
                        preview.set_path(paths[name] if name else '')
                    # Let the debounce expire while the interrupted worker is busy.
                    if expire_timer:
                        preview.timer.stop(); preview.start_preview()
                    if stale:
                        image, stamp = read(paths['A'], photos.QSize(8, 8))
                        original.thumbnail_ready.emit(paths['A'], image, stamp)
                        self.app.processEvents()
                        self.assertTrue(preview.canvas.image.isNull(), 'accepted superseded A')
                    if close_dialog:
                        dialog.close()
                        self.assertTrue(dialog.isVisible(), 'dialog destroyed its active worker')
                    elif stop:
                        preview.stop()
                    release.set()
                    self.wait_for(lambda: preview.worker is None and not preview.timer.isActive())
                    if stop or close_dialog or not sequence[-1]:
                        self.assertEqual(calls, [paths['A']])
                        self.assertTrue(preview.canvas.image.isNull())
                    elif fail_latest:
                        self.assertIn('unavailable', preview.canvas.message)
                    else:
                        self.assertFalse(preview.canvas.image.isNull(), preview.canvas.message)
                        expected, _ = read(paths[sequence[-1]], photos.QSize(8, 8))
                        self.assertEqual(preview.canvas.image.pixelColor(0, 0), expected.pixelColor(0, 0))
                        self.assertEqual(calls[-1], paths[sequence[-1]])
                        self.assertEqual(len(calls), 1 if set(sequence) == {'A'} else 2)
                    if close_dialog: self.assertFalse(dialog.isVisible())
                finally:
                    preview.stop(); release.set()
                    self.wait_for(lambda: preview.worker is None)
                    (dialog or preview).deleteLater(); self.app.processEvents()

    def test_interrupted_selection_sequences(self):
        for sequence in [('B', 'A'), ('B', 'C'), ('B', 'A', 'B'), ('A', 'A'),
                         ('B', 'A', 'A'), ('B', '', 'C'), ('',)]:
            with self.subTest(sequence=sequence): self.exercise(sequence)

    def test_superseded_result_with_same_path_is_ignored(self):
        self.exercise(('B', 'A'), stale=True)

    def test_decoder_failure_during_selection_change(self):
        self.exercise(('B', 'A'), fail_first=True)
        self.exercise(('B', 'A'), fail_latest=True)

    def test_stop_retires_active_worker_without_restarting(self):
        self.exercise(('B', 'A'), stop=True)

    def test_closing_location_dialog_waits_for_preview_worker(self):
        self.exercise(('B', 'A'), close_dialog=True)

    def test_completion_without_result_shows_error(self):
        preview = photos.PhotoPreview()
        try:
            with patch.object(photos.ThumbnailWorker, 'run', lambda worker: None):
                preview.set_path('/unused.png')
                preview.timer.stop(); preview.start_preview()
                self.wait_for(lambda: preview.worker is None)
            self.assertIn('unavailable', preview.canvas.message)
        finally:
            preview.stop(); preview.deleteLater(); self.app.processEvents()

    def test_replacement_worker_consumes_pending_debounce(self):
        self.exercise(('B', 'A'), expire_timer=False)


if __name__ == '__main__':
    unittest.main()
