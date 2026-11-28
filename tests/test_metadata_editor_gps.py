"""GPS-1 proposals only: protected real reads and native Qt draft lifecycle."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from metadata_integrity import sha256_noatime
import kim_location as gps
from kim_location_dialog import LocationDialog, ProposalWorker
from kim_metadata_editor import MetadataEditor, ReviewDialog, Draft, gps_review_rows
from kim_metadata_reader import read_metadata
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox


def signature(path):
    st = path.stat()
    return (sha256_noatime(path), st.st_size, st.st_atime_ns, st.st_mtime_ns, st.st_ctime_ns)


class GPSProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not all(shutil.which(x) for x in ('magick', 'exiftool')):
            raise unittest.SkipTest('ImageMagick and ExifTool required')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kimng-gps1-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.image = self.folder / 'image.jpg'
        subprocess.run(['magick', '-size', '16x12', 'xc:red', str(self.image)], check=True, capture_output=True)
        subprocess.run(['exiftool', '-overwrite_original', '-GPSLatitude=48.5', '-GPSLongitude=2.25',
                        '-GPSLatitudeRef=N', '-GPSLongitudeRef=E', '-GPSMapDatum=WGS-84',
                        '-GPSDateStamp=2020:01:01', '-GPSTimeStamp=12:00:00', '-GPSSpeed=20',
                        '-XMP-dc:Title=Original', str(self.image)], check=True, capture_output=True)
        self.sidecar = self.image.with_suffix('.xmp')
        self.sidecar.write_text('''<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="10,0N" exif:GPSLongitude="20,0E"/>
</rdf:RDF></x:xmpmeta>''')
        self.config = dict(method='manual', latitude='-40.25', longitude='71.5', altitude='-50', direction='123')

    def proposal(self, **updates):
        return gps.build_manual_proposal(str(self.image), dict(self.config, **updates))

    def wait_for(self, predicate):
        deadline = time.monotonic() + 8
        while not predicate():
            self.app.processEvents()
            if time.monotonic() > deadline: self.fail('Focused worker timed out')
            time.sleep(.01)

    def editor(self, *, wait=True, paths=None):
        # Exercise the actual widgets, keeping unrelated progressive loading out.
        for name in ('_pump_load', '_pump_thumbnails', '_ensure_preview', '_persist_splitter_sizes', '_restore_splitter_sizes'):
            # PySide6 6.10 inspects class methods while connecting Qt signals.
            # Use real callable stubs, since MagicMock attributes can crash that inspection.
            patcher = patch.object(MetadataEditor, name, lambda self, *args, **kwargs: None)
            patcher.start(); self.addCleanup(patcher.stop)
        paths = paths or [str(self.image)]
        editor = MetadataEditor(paths)
        editor._scan_complete(read_metadata(paths), {})
        def close():
            editor.drafts.clear(); editor.source_drafts.clear(); editor.batch_sessions.clear(); editor.gps_drafts.clear()
            editor.close()
            self.wait_for(lambda: editor._gps_inspection is None and editor._gps_dialog is None)
            editor.deleteLater(); self.app.processEvents()
        self.addCleanup(close)
        if wait: self.wait_for(lambda: str(self.image) in editor._gps_snapshots)
        return editor

    def dialog(self, config=None):
        dialog = LocationDialog('apply', [str(self.image)], 'proposal', None, initial=self.config if config is None else config)
        def close():
            dialog.reject()
            self.wait_for(lambda: dialog.worker is None and dialog.inspection_worker is None and dialog.photo_preview.worker is None)
            dialog.deleteLater(); self.app.processEvents()
        self.addCleanup(close)
        return dialog

    def test_review_groups_one_gps_operation_and_cannot_accept(self):
        proposal = self.proposal()
        dialog = ReviewDialog(gps_review_rows(proposal), selected_count=1)
        self.assertIn('1 image has proposed changes', dialog.summary.text())
        self.assertIn('1 proposed operation', dialog.summary.text())
        self.assertEqual(1, dialog.tree.topLevelItem(0).childCount())
        self.assertEqual('Change GPS location', dialog.tree.topLevelItem(0).child(0).text(0))
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.apply_button.click()
        dialog.accept()
        dialog.done(QDialog.Accepted)
        self.assertNotEqual(QDialog.Accepted, dialog.result())
        dialog.technical_button.setChecked(True)
        self.assertIn('GPS fix details', dialog.technical.toPlainText())
        self.assertIn(str(self.sidecar), dialog.technical.toPlainText())
        self.assertNotIn('Planned result:', dialog.result_label.text())
        dialog.back_button.click()

    def test_permanent_fields_and_gps_pin_share_one_editor_section(self):
        from kim_metadata_sources import OVERVIEW_DEFAULTS
        editor = self.editor()
        editor.overview_preferences.fields = list(OVERVIEW_DEFAULTS)
        editor._refresh_editor_pins()
        self.assertEqual(3, len(editor.capture_values))
        self.assertFalse(any(field.label == 'GPS position' for field, card, key in editor._pin_order))
        self.assertIn('1 change', self._pending_gps(editor))
        editor.overview_preferences.fields = []
        editor._refresh_editor_pins()
        self.assertFalse(editor.capture_section.isHidden())
        self.assertFalse(editor.gps_section.isHidden())

    def _pending_gps(self, editor):
        editor.gps_drafts[str(self.image)] = self.proposal()
        editor._refresh_pending()
        return editor.pending_label.text()

    def test_coordinate_form_is_compact_and_keyboard_review_cannot_accept(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import Qt
        before = [signature(p) for p in (self.image, self.sidecar)]
        dialog = self.dialog()
        dialog.show()
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        self.assertEqual('Edit GPS location', dialog.windowTitle())
        self.assertEqual('Use this location', dialog.apply_button.text())
        latitude = dialog.inputs['latitude']; longitude = dialog.inputs['longitude']
        self.assertEqual(latitude.y(), longitude.y())
        self.assertGreater(dialog.inputs['altitude'].y(), latitude.y())
        self.assertLess(dialog.controls.height(), 300)
        review = ReviewDialog(gps_review_rows(dialog.proposal))
        review.show()
        self.app.processEvents()
        self.assertTrue(review.apply_button.isVisible())
        self.app.sendEvent(review, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
        self.app.sendEvent(review, QKeyEvent(QEvent.KeyRelease, Qt.Key_Return, Qt.NoModifier))
        review.accept()
        self.assertNotEqual(QDialog.Accepted, review.result())
        review.reject()
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_add_blocked_and_noop_review_keep_details_and_operation_counts(self):
        subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)], check=True, capture_output=True)
        proposal = self.proposal()
        review = ReviewDialog(gps_review_rows(proposal))
        self.assertEqual('Add GPS location', review.items[0].text(0))
        self.assertIn('1 proposed operation', review.summary.text())
        self.assertIn('No camera GPS', review.before_view.toPlainText())
        review.reject()
        self.sidecar.write_text(self.sidecar.read_text() + ' ')
        review = ReviewDialog(gps_review_rows(proposal))
        self.assertIn('1 blocked operation', review.summary.text())
        self.assertIn('changed', review.warning_label.text())
        self.assertFalse(review.apply_button.isEnabled())
        review.reject()
        noop = dict(image='image.jpg', path=str(self.image), field='Title', operation='No change required',
                    status='noop', before='Title', after='Unchanged')
        review = ReviewDialog([noop])
        self.assertTrue(review.has_proposals)
        self.assertIn('1 no-op operation', review.summary.text())
        review.reject()

    def test_editor_gps_section_is_independent_of_pins_and_loading(self):
        editor = self.editor(wait=False)
        self.assertTrue(hasattr(editor, 'gps_section'))
        self.assertIs(editor.gps_section.parentWidget(), editor.capture_section)
        self.assertGreater(editor.fields_layout.indexOf(editor.capture_section), 0)
        self.assertEqual('Checking GPS location…', editor.gps_status.text())
        self.assertFalse(editor.add_gps_button.isEnabled())

    def test_proposal_reuses_preview_and_interactive_map(self):
        dialog = self.dialog()
        self.assertTrue(hasattr(dialog, 'photo_preview'))
        self.assertTrue(hasattr(dialog, 'location_map'))
        self.assertTrue(dialog.location_map.canvas.interactive)
        self.assertTrue(dialog.sidebar.isHidden())
        self.assertEqual('Use this location', dialog.apply_button.text())

    def test_embedded_and_sidecar_conflict_is_visible_without_merging(self):
        before = [signature(p) for p in (self.image, self.sidecar)]
        editor = self.editor()
        self.assertTrue(editor.gps_status.text().startswith('GPS:'))
        self.assertIn('48.500000', editor.gps_status.text())
        self.assertIn('Sidecar image.xmp (unchanged)', editor.gps_status.text())
        self.assertIn('conflict', editor.gps_status.text())
        self.assertEqual('Edit GPS location…', editor.add_gps_button.text())
        self.assertTrue(editor.add_gps_button.isEnabled())
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_sidecar_only_state_does_not_seed_embedded_coordinates(self):
        subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)], check=True, capture_output=True)
        editor = self.editor()
        self.assertIn('Sidecar-only GPS', editor.gps_status.text())
        self.assertEqual('Add GPS location…', editor.add_gps_button.text())
        self.assertTrue(editor.add_gps_button.isEnabled())
        dialog = self.dialog({})
        self.wait_for(lambda: dialog.inspection_worker is None and dialog.gps_snapshot is not None)
        self.assertEqual('', dialog.inputs['latitude'].text())
        self.assertIsNone(dialog.proposal)
        self.assertNotIn('Invalid', dialog.coordinate_readout.text())

    def test_absent_gps_navigation_and_pin_changes(self):
        other = self.folder / 'absent.jpg'
        subprocess.run(['magick', '-size', '16x12', 'xc:blue', str(other)], check=True, capture_output=True)
        editor = self.editor(paths=[str(self.image), str(other)])
        editor.overview_preferences.fields = []
        editor._refresh_editor_pins()
        self.assertFalse(editor.gps_section.isHidden())
        self.assertIs(editor.gps_section.parentWidget(), editor.capture_section)
        self.assertGreater(editor.fields_layout.indexOf(editor.capture_section), 0)
        editor.navigate(1)
        self.assertEqual('Checking GPS location…', editor.gps_status.text())
        self.assertFalse(editor.add_gps_button.isEnabled())
        self.wait_for(lambda: str(other) in editor._gps_snapshots)
        self.assertEqual('No camera GPS coordinates recorded.', editor.gps_status.text())
        self.assertEqual('Add GPS location…', editor.add_gps_button.text())
        editor.navigate(-1)
        self.assertTrue(editor.gps_status.text().startswith('GPS:'))

    def test_conflicting_embedded_coordinates_disable_editing(self):
        subprocess.run(['exiftool', '-overwrite_original', '-XMP-exif:GPSLatitude=12',
                        '-XMP-exif:GPSLongitude=34', str(self.image)], check=True, capture_output=True)
        editor = self.editor()
        self.assertIn('Conflicting', editor.gps_status.text())
        self.assertIn('XMP-exif', editor.gps_status.text())
        self.assertFalse(editor.add_gps_button.isEnabled())
        self.assertFalse(editor.view_gps_button.isHidden())

    def test_unreadable_and_unsupported_sources_are_not_absent_gps(self):
        for name, contents in [('broken.jpg', b'not an image'), ('unknown.raw', b'unsupported')]:
            with self.subTest(name=name):
                path = self.folder / name; path.write_bytes(contents)
                snapshot = gps.inspect_editor_gps(str(path))
                self.assertTrue(snapshot['blocked'])
                self.assertNotIn('No camera GPS coordinates recorded.', gps.editor_gps_description(snapshot))
        png = self.folder / 'supported.png'
        subprocess.run(['magick', '-size', '16x12', 'xc:blue', str(png)], check=True, capture_output=True)
        snapshot = gps.inspect_editor_gps(str(png))
        self.assertIn('No camera GPS coordinates recorded.', gps.editor_gps_description(snapshot))
        self.assertFalse(snapshot['blocked'])

    def test_manual_and_map_entry_and_preview_preserve_source_signatures(self):
        before = [signature(p) for p in (self.image, self.sidecar)]
        dialog = self.dialog({})
        dialog.show()
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None and dialog.photo_preview.worker is None)
        self.assertEqual('48.5', dialog.inputs['latitude'].text())
        self.assertFalse(dialog.photo_preview.canvas.image.isNull())
        canvas = dialog.location_map.canvas
        canvas.select_at(QPointF(canvas.width() / 2 + 20, canvas.height() / 2))
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        self.assertAlmostEqual(canvas.selected[1], dialog.proposal['proposed']['position'][1], places=10)
        self.assertNotEqual(2.25, dialog.proposal['proposed']['position'][1])
        # The established map emits this signal for a click or Space selection.
        dialog.location_map.canvas.position_changed.emit([-23.5, 0])
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        self.assertEqual([-23.5, 0], dialog.proposal['proposed']['position'])
        self.assertEqual([-23.5, 0], dialog.location_map.canvas.selected)
        dialog.inputs['latitude'].setText('91')
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertTrue(dialog.proposal['blocked'])
        dialog.inputs['latitude'].setText('-12.25')
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        self.assertEqual([-12.25, 0], dialog.proposal['proposed']['position'])
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_pending_section_and_explicit_discard_preserve_metadata_draft(self):
        editor = self.editor(); path = str(self.image)
        editor.field_controls['title']['edit'].setText('Retained')
        draft = editor.drafts[path]['title']
        proposal = self.proposal(); editor.gps_drafts[path] = proposal
        editor._refresh_pending()
        self.assertIn('Current:', editor.gps_status.text())
        self.assertIn('Proposed:', editor.gps_status.text())
        self.assertEqual('Edit GPS location…', editor.add_gps_button.text())
        self.assertFalse(editor.discard_gps_button.isHidden())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel): editor.discard_gps_proposal()
        self.assertIs(proposal, editor.gps_drafts[path])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard): editor.discard_gps_proposal()
        self.assertNotIn(path, editor.gps_drafts)
        self.assertIs(draft, editor.drafts[path]['title'])

    def test_standalone_location_methods_and_buttons_remain_available(self):
        dialog = LocationDialog('apply', [str(self.image)], 'select', None)
        try:
            self.assertEqual(['photo', 'map', 'manual', 'gpx'], [dialog.method.itemData(i) for i in range(dialog.method.count())])
            self.assertEqual('Review changes…', dialog.apply_button.text())
            self.assertTrue(hasattr(dialog, 'output_create'))
            self.assertTrue(dialog.location_map.store.persistent)
            self.assertFalse(dialog.location_map.canvas.interactive)
            self.assertFalse(dialog.sidebar.isHidden())
        finally:
            dialog.reject()
            self.wait_for(lambda: dialog.worker is None and dialog.thumbnail_worker is None and dialog.photo_preview.worker is None)
            dialog.deleteLater(); self.app.processEvents()

    def test_valid_proposal_provenance_and_exact_signatures(self):
        before = [signature(p) for p in (self.image, self.sidecar)]
        p = self.proposal()
        self.assertEqual('valid', p['status'], p)
        self.assertEqual([48.5, 2.25], p['existing']['position'])
        self.assertEqual([-40.25, 71.5], p['proposed']['position'])
        self.assertEqual('1', p['proposed']['altitude_ref'])
        self.assertEqual('T', p['proposed']['direction_ref'])
        self.assertEqual([10, 20], p['sidecars'][0]['existing']['position'])
        self.assertTrue(p['embedded_provenance'])
        self.assertTrue(p['removed_fields'])
        self.assertFalse(p['noop'])
        self.assertEqual(before, [signature(x) for x in (self.image, self.sidecar)])
        forbidden = {'args', 'target', 'destination', 'publication', 'policy', 'approved_location', 'approval_digest'}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse((forbidden - {'destination'}).intersection(value))
                if 'destination' in value:
                    self.assertIn('camera', value)  # semantic coordinate categories, not an output
                for child in value.values(): check(child)
            elif isinstance(value, list):
                for child in value: check(child)
        check(p)
        rows = gps_review_rows(p)
        self.assertTrue(any(row['status'] == 'unchanged' and 'sidecar' in row['sources'].lower() for row in rows))
        self.assertIn('timestamps', rows[0]['warning'])

    def test_sidecar_coordinates_do_not_supply_an_embedded_target(self):
        subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)],
                       check=True, capture_output=True)
        p = self.proposal()
        self.assertEqual('valid', p['status'], p)
        self.assertIsNone(p['existing']['position'])
        self.assertEqual([10, 20], p['sidecars'][0]['existing']['position'])
        self.assertEqual([-40.25, 71.5], p['proposed']['position'])

    def test_changed_source_blocks_dialog_acceptance(self):
        dialog = self.dialog()
        self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
        with self.image.open('ab') as stream: stream.write(b' ')
        dialog.accept()
        self.assertNotEqual(QDialog.Accepted, dialog.result())
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertIn('regenerate', dialog.summary.text())

    def test_first_input_cancel_keeps_descriptive_draft_and_adds_no_gps(self):
        editor = self.editor(); path = str(self.image)
        editor.field_controls['title']['edit'].setText('Retained')
        original = editor.drafts[path]['title']
        def cancel(dialog):
            dialog.reject(); return QDialog.Rejected
        with patch.object(LocationDialog, 'exec', cancel): editor.add_gps_location()
        self.assertFalse(editor.gps_drafts)
        self.assertIs(original, editor.drafts[path]['title'])

    def test_invalid_numeric_input_and_optional_fields(self):
        for updates in (dict(latitude='91'), dict(longitude='-181'), dict(latitude='NaN'),
                        dict(latitude='1.1234567890123'), dict(altitude='-12001'),
                        dict(altitude='bad'), dict(direction='360'), dict(direction='-1'), dict(method='photo')):
            with self.subTest(updates=updates):
                p = self.proposal(**updates)
                self.assertEqual('blocked', p['status']); self.assertTrue(p['blocked'])
        p = self.proposal(altitude='', direction='')
        self.assertEqual('valid', p['status'])
        self.assertIsNone(p['proposed']['altitude']); self.assertIsNone(p['proposed']['direction'])

    def test_stale_fix_is_not_noop_and_canonical_coordinates_can_be_noop(self):
        p = self.proposal(latitude='48.5', longitude='2.25', altitude='', direction='')
        self.assertFalse(p['noop']); self.assertEqual('valid', p['status'])
        subprocess.run(['exiftool', '-overwrite_original', '-GPSDateStamp=', '-GPSTimeStamp=',
                        '-GPSSpeed=', str(self.image)], check=True, capture_output=True)
        p = self.proposal(latitude='48.5', longitude='2.25', altitude='', direction='')
        self.assertEqual('noop', p['status'], p)
        self.assertTrue(ReviewDialog(gps_review_rows(p)).has_proposals)

    def test_duplicate_coordinates_require_reconciliation(self):
        subprocess.run(['exiftool', '-overwrite_original', '-XMP-exif:GPSLatitude=48.5',
                        '-XMP-exif:GPSLongitude=2.25', str(self.image)], check=True, capture_output=True)
        p = self.proposal(latitude='48.5', longitude='2.25', altitude='', direction='')
        self.assertEqual('valid', p['status']); self.assertFalse(p['noop'])
        self.assertTrue(any('XMP-exif' in field for field in p['removed_fields']))

    def test_stale_source_sidecar_and_membership_block_without_rebase(self):
        for target in (self.image, self.sidecar):
            p = self.proposal(); old = p['freshness']
            with target.open('ab') as stream: stream.write(b' ')
            self.assertIn('changed', gps.proposal_problem(p))
            self.assertTrue(any(r['status'] == 'blocked' for r in gps_review_rows(p)))
            self.assertIs(old, p['freshness'])
        p = self.proposal()
        other = self.folder / 'IMAGE.XMP'; other.write_text(self.sidecar.read_text())
        self.assertIn('membership changed', gps.proposal_problem(p))
        other.unlink()
        p = self.proposal(); self.sidecar.unlink()
        self.assertIn('changed', gps.proposal_problem(p))

    def test_unsupported_jpeg_variants_and_extensions(self):
        for name, args in [('progressive.jpg', ['-interlace', 'Plane']),
                           ('wrong.png', []), ('image.dat', [])]:
            target = self.folder / name
            if name in ('wrong.png', 'image.dat'): shutil.copyfile(self.image, target)
            else: subprocess.run(['magick', '-size', '12x8', 'xc:blue', *args, str(target)], check=True, capture_output=True)
            p = gps.build_manual_proposal(str(target), self.config)
            self.assertEqual('blocked', p['status'], p)
            self.assertIn('Progressive JPEG' if name == 'progressive.jpg' else 'matching extension', p['blocked'][0])

    def test_noatime_failure_fails_closed(self):
        before = [signature(p) for p in (self.image, self.sidecar)]
        with patch('kim_preview.os.open', side_effect=PermissionError('no protected access')):
            p = self.proposal()
            inspection = gps.inspect_editor_gps(str(self.image))
        self.assertEqual('blocked', p['status']); self.assertIn('access time', p['blocked'][0])
        self.assertTrue(inspection['blocked'])
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_gps_only_and_combined_review_close_retain_all_drafts(self):
        editor = self.editor(); path = str(self.image)
        p = self.proposal(); editor.gps_drafts[path] = p
        self.assertEqual([path], editor._proposal_paths())
        editor._refresh_pending(); self.assertTrue(editor.review_button.isEnabled())
        plans = []
        def review(dialog):
            plans.append(dialog.plan)
            self.assertFalse(dialog.apply_button.isEnabled())
            dialog.back_button.click()
            return QDialog.Rejected
        with patch.object(ReviewDialog, 'exec', review): editor.review_changes()
        self.assertTrue(plans[0]); self.assertTrue(all(r.get('gps') for r in plans[0]))
        editor.field_controls['title']['edit'].setText('Description retained')
        draft = editor.drafts[path]['title']
        with patch.object(ReviewDialog, 'exec', review): editor.review_changes()
        self.assertTrue(any(r['field'] == 'Title' and r['status'] == 'valid' for r in plans[-1]))
        self.assertTrue(any(r.get('gps') for r in plans[-1]))
        self.assertIs(p, editor.gps_drafts[path]); self.assertIs(draft, editor.drafts[path]['title'])

    def test_explicit_replacement_cancel_and_navigation_retention(self):
        editor = self.editor(); path = str(self.image)
        p = self.proposal(); editor.gps_drafts[path] = p
        editor.field_controls['title']['edit'].setText('Retained')
        draft = editor.drafts[path]['title']
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel), patch.object(LocationDialog, 'exec') as run:
            editor.add_gps_location(); run.assert_not_called()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), patch.object(LocationDialog, 'exec', lambda self: QDialog.Rejected):
            editor.add_gps_location()
        self.assertIs(p, editor.gps_drafts[path]); self.assertIs(draft, editor.drafts[path]['title'])
        replacement = self.proposal(latitude='12')
        def accept(dialog):
            self.assertEqual(self.config['latitude'], dialog.inputs['latitude'].text())
            dialog.timer.stop(); dialog.proposal = replacement
            return QDialog.Accepted
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), patch.object(LocationDialog, 'exec', accept):
            editor.add_gps_location()
        self.assertIs(replacement, editor.gps_drafts[path]); self.assertIs(draft, editor.drafts[path]['title'])
        editor._image_changed(-1); editor._image_changed(0)
        self.assertIs(replacement, editor.gps_drafts[path])

    def test_editor_close_protects_and_explicit_discard_clears_gps(self):
        editor = self.editor(); path = str(self.image); p = self.proposal()
        editor.gps_drafts[path] = p
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            event = QCloseEvent(); editor.closeEvent(event)
        self.assertFalse(event.isAccepted()); self.assertIs(p, editor.gps_drafts[path])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            event = QCloseEvent(); editor.closeEvent(event)
        self.assertFalse(editor.gps_drafts); self.assertTrue(editor._closing)

    def test_proposal_dialog_has_no_publication_settings_or_map_side_effects(self):
        before = [signature(p) for p in (self.image, self.sidecar)]
        with patch('kim_location.build_plan', side_effect=AssertionError('publication planner')), \
             patch('kim_location.allocate', side_effect=AssertionError('allocate output')), \
             patch('kim_location.assignments', side_effect=AssertionError('writer arguments')), \
             patch('kim_location_dialog.save_plan', side_effect=AssertionError('save plan')), \
             patch('kim_location_dialog.persist_units', side_effect=AssertionError('settings write')), \
             patch('kim_location_map.save_settings', side_effect=AssertionError('map settings write')), \
             patch('kim_location_map.QNetworkDiskCache', side_effect=AssertionError('map disk cache')):
            dialog = self.dialog()
            self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None)
            self.assertEqual('valid', dialog.proposal['status'])
            self.assertTrue(dialog.apply_button.isEnabled())
            self.assertFalse(hasattr(dialog, 'output_create'))
            self.assertFalse(dialog.location_map.store.persistent)
            self.assertIsNone(dialog.location_map.store.network)
            dialog.location_map.online.click()
            with patch('kim_location_map.capability_problems', return_value=[]):
                dialog.location_map.store.initialize()
            self.assertIsNone(dialog.location_map.store.network.cache())
            dialog.unit_choice.setCurrentIndex((dialog.unit_choice.currentIndex() + 1) % dialog.unit_choice.count())
            self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None and dialog.photo_preview.worker is None)
            dialog.accept(); self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_cancellation_interrupts_worker_and_prevents_late_acceptance(self):
        from kim_process import checkpoint
        started = []
        def slow(path, config, *, cancelled):
            with gps.inspection_context(cancelled=cancelled):
                started.append(True)
                while True: checkpoint(); time.sleep(.01)
        with patch('kim_location_dialog.build_manual_proposal', slow):
            dialog = self.dialog(); dialog.timer.stop(); dialog._start_proposal()
            self.wait_for(lambda: bool(started))
            dialog.reject(); self.wait_for(lambda: dialog.worker is None)
            dialog.accept()
            self.assertIsNone(dialog.proposal); self.assertEqual(QDialog.Rejected, dialog.result())

    def test_editor_shutdown_interrupts_active_gps_input(self):
        from kim_process import checkpoint
        editor = self.editor(); started = []; dialogs = []
        before = [signature(p) for p in (self.image, self.sidecar)]
        def slow(path, config, *, cancelled):
            with gps.inspection_context(cancelled=cancelled):
                started.append(True)
                while True: checkpoint(); time.sleep(.01)
        def run(dialog):
            dialogs.append(dialog)
            dialog.timer.stop(); dialog._start_proposal()
            def shut_down():
                if not started: QTimer.singleShot(10, shut_down); return
                editor.closeEvent(QCloseEvent())
            QTimer.singleShot(10, shut_down)
            QTimer.singleShot(3000, dialog.reject)
            return QDialog.exec(dialog)
        with patch('kim_location_dialog.build_manual_proposal', slow), patch.object(LocationDialog, 'exec', run):
            editor.add_gps_location()
        self.assertTrue(started); self.assertTrue(editor._closing)
        self.assertFalse(editor.gps_drafts); self.assertIsNone(editor._gps_dialog)
        self.assertIsNone(dialogs[0].worker); self.assertIsNone(dialogs[0].proposal)
        self.assertEqual(before, [signature(p) for p in (self.image, self.sidecar)])

    def test_view_on_map_still_uses_existing_report_dialog(self):
        editor = self.editor(); p = self.proposal(); editor.gps_drafts[str(self.image)] = p
        with patch('kim_location_dialog.LocationDialog') as dialog:
            editor.view_gps_on_map()
            dialog.assert_called_once_with('report', [str(self.image)], 'create', None)
            dialog.return_value.exec.assert_called_once()
        self.assertIs(p, editor.gps_drafts[str(self.image)])


if __name__ == '__main__': unittest.main()
