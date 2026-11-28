"""Focused field-action UI coverage using disposable GPS fixtures."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
import test_metadata_editor_gps as fixtures
import kim_metadata_gps_actions as actions
from kim_metadata_reader import MetadataRecord, MetadataEntry, read_metadata
from kim_metadata_browser import (MetadataBrowser, MetadataOverview, TagModel,
    ComparisonModel, ComparisonData)
from kim_metadata_compare import compare_records
from kim_metadata_sources import OverviewPreferences, MetadataSourcePreferences, OVERVIEW_DEFAULTS
from PySide6.QtCore import Qt, QSettings, QEvent, QPointF
from PySide6.QtWidgets import QApplication, QDialog, QTableView, QToolButton, QLabel, QWidget
from PySide6.QtGui import QMouseEvent


def entry(name, value, source='/image.jpg', groups=('EXIF', 'GPS', 'Location')):
    return MetadataEntry(name, groups, None, value, source, ':'.join((*groups, name)))


class GPSFieldActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def record(self, source='/image.jpg', prefix='GPS', groups=('EXIF', 'GPS', 'Location')):
        return MetadataRecord('/image.jpg', [entry(prefix + 'Latitude', 12, source, groups),
            entry(prefix + 'Longitude', 34, source, groups),
            entry(prefix + 'LatitudeRef', 'North', source, groups),
            entry(prefix + 'LongitudeRef', 'East', source, groups)])

    def test_native_and_technical_camera_fields_use_their_own_record(self):
        record = self.record()
        record.entries.append(entry('GPSAltitude', 80))
        for item in record.entries:
            field = actions.gps_field(record, item)
            self.assertTrue(field.camera)
            self.assertEqual([12, 34], field.position)
            self.assertEqual('Edit GPS', actions.field_actions(object(), field)[1][0])

    def test_sidecar_destination_depicted_and_structured_keep_provenance(self):
        for source, prefix, groups, category in (
            ('/sidecar.xmp', 'GPS', ('XMP', 'XMP-exif', 'Location'), 'camera'),
            ('/image.jpg', 'GPSDest', ('EXIF', 'GPS', 'Location'), 'destination'),
            ('/image.jpg', 'LocationShownGPS', ('XMP', 'XMP-iptcExt', 'Location'), 'depicted'),
            ('/image.jpg', 'LocationCreated.GPS', ('XMP', 'XMP-iptcExt', 'Location'), 'structured')):
            with self.subTest(prefix=prefix, source=source):
                record = self.record(source, prefix, groups)
                field = actions.gps_field(record, record.entries[0])
                self.assertEqual([12, 34], field.position)
                self.assertFalse(field.camera)
                self.assertIn(category, field.provenance)
                self.assertTrue(actions.field_actions(object(), field)[0][2])
                edit = actions.field_actions(object(), field)[1]
                self.assertFalse(edit[2]); self.assertIn('unsupported', edit[3])

    def test_incomplete_conflicting_and_invalid_coordinates_do_not_map(self):
        record = self.record()
        record.entries.pop(1)
        field = actions.gps_field(record, record.entries[0])
        self.assertFalse(actions.field_actions(object(), field)[0][2])
        record = self.record()
        record.entries.append(entry('GPSLatitude', 88))
        self.assertIsNone(actions.gps_field(record, record.entries[0]).position)
        record = self.record()
        record.entries.append(entry('GPSMapDatum', 'Tokyo'))
        self.assertFalse(actions.gps_field(record, record.entries[0]).camera)

    def test_coordinate_pair_never_crosses_storage_namespaces(self):
        record = MetadataRecord('/image.jpg', [
            entry('GPSLatitude', 12, groups=('QuickTime', 'Keys', 'Location')),
            entry('GPSLongitude', 34, groups=('QuickTime', 'UserData', 'Location'))])
        for item in record.entries:
            field = actions.gps_field(record, item)
            self.assertIsNone(field.position)
            self.assertFalse(field.camera)

    def test_derived_position_maps_exact_value_and_cannot_edit_camera(self):
        record = self.record()
        derived = entry('GPSPosition', '51 deg 30\' 0" N, 0 deg 6\' 0" W', groups=('Composite', 'Location'))
        record.entries.append(derived)
        field = actions.gps_field(record, derived)
        self.assertEqual((51.5, -.1), field.position)
        self.assertFalse(field.camera)
        with patch.object(actions, 'show_field_map') as show:
            actions.dispatch(object(), field, actions.field_actions(object(), field)[0])
        self.assertEqual((51.5, -.1), show.call_args.args[2])

    def test_browser_edit_dispatches_the_field_image_only(self):
        field = actions.gps_field(self.record(), self.record().entries[0])
        owner = SimpleNamespace()
        with patch('kim_location_dialog.LocationDialog') as dialog, patch('kim_metadata_editor.MetadataEditor') as editor, patch.object(actions, 'proposal_problem', return_value=''):
            dialog.return_value.exec.return_value = QDialog.Accepted
            proposal = dialog.return_value.proposal
            editor.return_value.gps_drafts = {}
            actions.dispatch(owner, field, actions.field_actions(owner, field)[1])
            self.assertIs(proposal, editor.return_value.gps_drafts[field.path])
        editor.assert_called_once_with(['/image.jpg'])
        editor.return_value.show.assert_called_once_with()
        with patch('kim_metadata_editor.MetadataEditor') as editor:
            sidecar = actions.gps_field(self.record('/sidecar.xmp'), self.record('/sidecar.xmp').entries[0])
            actions.dispatch(owner, sidecar, actions.field_actions(owner, sidecar)[1])
            editor.assert_not_called()

    def test_browser_add_and_edit_open_gps_dialog_before_any_editor(self):
        for record in (MetadataRecord('/empty.jpg'), self.record()):
            with self.subTest(path=record.path):
                owner = SimpleNamespace()
                field = actions.gps_field(record)
                with patch('kim_location_dialog.LocationDialog') as dialog, patch('kim_metadata_editor.MetadataEditor') as editor:
                    dialog.return_value.exec.return_value = QDialog.Rejected
                    actions.dispatch(owner, field, actions.field_actions(owner, field)[1])
                    dialog.assert_called_once_with('apply', [record.path], 'proposal', None)
                    editor.assert_not_called()

    def test_browser_rechecks_proposal_freshness_before_opening_editor(self):
        owner = SimpleNamespace()
        field = actions.gps_field(self.record())
        with patch('kim_location_dialog.LocationDialog') as dialog, \
             patch('kim_metadata_editor.MetadataEditor') as editor, \
             patch.object(actions, 'proposal_problem', return_value='Sidecar changed'), \
             patch.object(actions.QMessageBox, 'warning') as warning:
            dialog.return_value.exec.return_value = QDialog.Accepted
            actions.dispatch(owner, field, actions.field_actions(owner, field)[1])
            editor.assert_not_called()
            warning.assert_called_once_with(owner, 'GPS proposal changed', 'Sidecar changed')
            dialog.return_value.reject.assert_called_once_with()
            self.assertIsNone(owner._gps_dialog)

    def test_overview_no_gps_and_no_pins_is_discoverable(self):
        settings = QSettings(str(Path('/tmp') / f'kim-gps-fields-{os.getpid()}.ini'), QSettings.IniFormat)
        self.addCleanup(lambda: Path(settings.fileName()).unlink(missing_ok=True))
        prefs = OverviewPreferences(settings); prefs.save([])
        self.assertIn('GPSLatitude', prefs.selectors)
        overview = MetadataOverview(MetadataSourcePreferences(settings), prefs)
        self.addCleanup(overview.deleteLater)
        overview.set_record(MetadataRecord('/empty.jpg'))
        controls = overview.findChildren(QToolButton, 'gpsFieldAction')
        location_buttons = [
            button for button in overview.findChildren(QToolButton)
            if button.objectName() == 'editGpsLocation'
        ]
        self.assertEqual(1, len(location_buttons))
        self.assertEqual('Add GPS location…', location_buttons[0].text())
        self.assertTrue(location_buttons[0].isEnabled())
        self.assertFalse(location_buttons[0].icon().isNull())
        self.assertFalse(location_buttons[0].isHidden())
        self.assertTrue(all(not button.isEnabled() for button in controls if button.text() == 'Map'))
        self.assertFalse(overview.show_empty.isChecked())

    def test_painted_actions_work_without_row_widgets_or_eager_fetch(self):
        record = self.record()
        record.entries += [entry('MakerField' + str(i), i, groups=('MakerNotes', 'Maker', 'Image')) for i in range(2000)]
        model = TagModel(False, None); model.set_record(record)
        view = QTableView(); view.setModel(model); view.resize(800, 400); view.show()
        self.addCleanup(view.close)
        delegate = actions.GPSActionDelegate(view, view, lambda index: actions.gps_field(model.record, index.data(Qt.UserRole)))
        self.app.processEvents()
        index = model.index(0, 1)
        field, buttons = delegate.buttons(index, view.visualRect(index))
        self.assertTrue(field.camera)
        with patch.object(actions, 'dispatch') as dispatch:
            point = QPointF(buttons[0][1].center())
            for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                event = QMouseEvent(kind, point, point, Qt.LeftButton,
                                    Qt.LeftButton if kind == QEvent.MouseButtonPress else Qt.NoButton, Qt.NoModifier)
                QApplication.sendEvent(view.viewport(), event)
        dispatch.assert_called_once()
        self.assertEqual(256, model.rowCount())
        self.assertEqual([], view.findChildren(QToolButton))
        self.assertLess(len(record._gps_field_actions[0]['/image.jpg']), 10)

    def test_compare_actions_use_left_and_right_records(self):
        left = self.record(); right = self.record()
        right.path = '/right.jpg'
        right.entries = [entry(item.name, item.value, right.path, item.groups) for item in right.entries]
        rows = tuple(compare_records(left, right))
        model = ComparisonModel(None)
        model.set_result(ComparisonData(rows, tuple(range(len(rows))), (), {}, 0, 0, 0), False)
        owner = SimpleNamespace(compared_paths=(left.path, right.path), _comparison_gps_records=(left, right))
        for column, path in ((1, left.path), (2, right.path)):
            field = MetadataBrowser._comparison_gps_field(owner, model.index(0, column))
            self.assertEqual(path, field.path)
            self.assertEqual([12, 34], field.position)
            with patch('kim_location_dialog.LocationDialog') as dialog, patch('kim_metadata_editor.MetadataEditor') as editor:
                dialog.return_value.exec.return_value = QDialog.Rejected
                actions.dispatch(owner, field, actions.field_actions(owner, field)[1])
                dialog.assert_called_once_with('apply', [path], 'proposal', None)
                editor.assert_not_called()

    def test_compare_missing_camera_gps_offers_add_for_missing_image(self):
        left = self.record(); right = MetadataRecord('/right.jpg')
        rows = tuple(compare_records(left, right))
        model = ComparisonModel(None)
        model.set_result(ComparisonData(rows, tuple(range(len(rows))), (), {}, 0, 0, 0), False)
        owner = SimpleNamespace(compared_paths=(left.path, right.path), _comparison_gps_records=(left, right))
        field = MetadataBrowser._comparison_gps_field(owner, model.index(0, 2))
        self.assertEqual(right.path, field.path)
        buttons = actions.field_actions(owner, field)
        self.assertFalse(buttons[0][2])
        self.assertEqual('Add GPS', buttons[1][0])
        with patch('kim_location_dialog.LocationDialog') as dialog, patch('kim_metadata_editor.MetadataEditor') as editor, patch.object(actions, 'proposal_problem', return_value=''):
            dialog.return_value.exec.return_value = QDialog.Accepted
            editor.return_value.gps_drafts = {}
            actions.dispatch(owner, field, buttons[1])
        editor.assert_called_once_with([right.path])


class EditorGPSFieldActionTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.GPSProposalTests.setUpClass.__func__)
    setUp = fixtures.GPSProposalTests.setUp
    editor = fixtures.GPSProposalTests.editor
    wait_for = fixtures.GPSProposalTests.wait_for
    proposal = fixtures.GPSProposalTests.proposal

    def test_empty_altitude_pin_offers_add_for_camera_without_coordinates(self):
        fixtures.subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)],
                                check=True, capture_output=True)
        editor = self.editor()
        altitude = next(field for field in OVERVIEW_DEFAULTS if field.label == 'GPS altitude')
        editor.overview_preferences.fields = [altitude]
        record = read_metadata([str(self.image)])[str(self.image)]
        with patch.object(editor, '_full_record', return_value=record):
            editor._refresh_editor_pins()
        widgets = editor._readonly_pins[altitude.key]
        self.assertEqual(0, widgets['gps_actions'].count())
        self.assertFalse(editor.gps_section.isHidden())
        self.assertEqual(
            'Add GPS location…',
            editor.add_gps_button.text()
        )
        self.assertTrue(editor.add_gps_button.isEnabled())
        self.assertFalse(editor.add_gps_button.icon().isNull())
        self.assertFalse(editor.view_gps_button.icon().isNull())
        self.assertEqual('', editor.view_gps_button.text())
        self.assertTrue(editor.view_gps_button.isEnabled())
        with patch.object(editor, 'add_gps_location') as add:
            context = actions.gps_field(record)
            dispatch_action = actions.field_actions(editor, context)[1]
            actions.dispatch(editor, context, dispatch_action)
        add.assert_called_once_with()

    def test_altitude_actions_follow_information_icon_in_heading(self):
        fixtures.subprocess.run(['exiftool', '-overwrite_original', '-GPSAltitude=80', '-GPSAltitudeRef=0', str(self.image)],
                                check=True, capture_output=True)
        editor = self.editor()
        altitude = next(field for field in OVERVIEW_DEFAULTS if field.label == 'GPS altitude')
        editor.overview_preferences.fields = [altitude]
        record = read_metadata([str(self.image)])[str(self.image)]
        with patch.object(editor, '_full_record', return_value=record):
            editor._refresh_editor_pins()
        widgets = editor._readonly_pins[altitude.key]
        card_layout = widgets['card'].layout()
        heading = card_layout.itemAt(0).layout()
        self.assertIs(widgets['details'], heading.itemAt(1).widget())
        self.assertIs(widgets['gps_actions'], heading.itemAt(2).layout())
        self.assertIs(widgets['value'], card_layout.itemAt(1).widget())
        self.assertLessEqual(
            widgets['value'].maximumHeight(),
            widgets['value'].fontMetrics().lineSpacing() * 2 + 8,
        )
        self.assertEqual(0, widgets['gps_actions'].count())
        self.assertEqual('', editor.view_gps_button.text())
        self.assertFalse(editor.view_gps_button.icon().isNull())
        self.assertTrue(editor.view_gps_button.isEnabled())
        self.assertEqual(
            'Edit GPS location…',
            editor.add_gps_button.text()
        )
        self.assertFalse(editor.add_gps_button.icon().isNull())
        self.assertTrue(editor.add_gps_button.isEnabled())
        editor.overview_preferences.fields = [field for field in OVERVIEW_DEFAULTS if field.label in ('GPS position', 'GPS altitude')]
        editor.overview.set_record(record)
        labels = [button.text() for button in editor.overview.findChildren(QToolButton, 'gpsFieldAction')]
        # Keep the sidecar's own map action. Camera editing belongs
        # to the Location heading, not a duplicate field action.
        self.assertEqual(['Map', 'Edit GPS location…'], labels)
        location_button = editor.overview.findChild(
            QToolButton, 'editGpsLocation'
        )
        self.assertIsNotNone(location_button)
        self.assertEqual('Edit GPS location…', location_button.text())
        self.assertTrue(location_button.isEnabled())
        self.assertFalse(location_button.icon().isNull())

    def test_editor_views_preserve_drafts_and_image_sidecar_integrity(self):
        before = [fixtures.signature(path) for path in (self.image, self.sidecar)]
        members = set(self.folder.iterdir())
        editor = self.editor(); path = str(self.image)
        proposal = self.proposal(); editor.gps_drafts[path] = proposal
        draft = fixtures.Draft('set', 'Keep title')
        editor.drafts[path] = {'title': draft}
        editor._refresh_pending()
        self.assertIn('Proposed:', editor.sources_gps_status.text())
        self.assertIn('Edit GPS location…', [button.text() for button in editor.sources_gps_section.findChildren(QToolButton)])
        record = read_metadata([path])[path]
        editor.overview.set_record(record)
        labels = [button.text() for button in editor.overview.findChildren(QToolButton, 'gpsFieldAction')]
        self.assertIn('Edit GPS location…', labels)
        discard = editor.overview.findChild(
            QToolButton, 'discardGpsLocation'
        )
        self.assertIsNotNone(discard)
        self.assertEqual('Discard change', discard.text())
        self.assertTrue(discard.isEnabled())
        self.assertFalse(discard.isHidden())
        native = next(item for item in record.entries if item.name == 'GPSLatitude' and 'GPS' in item.groups)
        field = actions.gps_field(record, native)
        with patch.object(editor, 'add_gps_location') as edit:
            actions.dispatch(editor, field, actions.field_actions(editor, field)[1])
        edit.assert_called_once_with()
        with patch.object(actions, 'show_field_map') as show:
            actions.dispatch(editor, field, actions.field_actions(editor, field)[0])
        self.assertEqual([48.5, 2.25], show.call_args.args[2])
        sidecar = next(item for item in record.entries if item.name == 'GPSLatitude' and item.source == str(self.sidecar))
        sidecar_field = actions.gps_field(record, sidecar)
        self.assertEqual([10, 20], sidecar_field.position)
        self.assertFalse(actions.field_actions(editor, sidecar_field)[1][2])
        self.assertEqual(members, set(self.folder.iterdir()))
        self.assertIs(proposal, editor.gps_drafts[path]); self.assertIs(draft, editor.drafts[path]['title'])
        self.assertIsInstance(editor.all_table.itemDelegateForColumn(1), actions.GPSActionDelegate)
        self.assertEqual(before, [fixtures.signature(item) for item in (self.image, self.sidecar)])


class BrowserDirectGPSRoutingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.GPSProposalTests.setUpClass.__func__)
    setUp = fixtures.GPSProposalTests.setUp
    editor = fixtures.GPSProposalTests.editor
    wait_for = fixtures.GPSProposalTests.wait_for

    def route(self, interact, *, browser=False):
        from kim_location_dialog import LocationDialog
        owner = MetadataBrowser([str(self.image)]) if browser else QWidget()
        owner._closing = False
        self.addCleanup(owner.deleteLater)
        created = []
        def create(paths):
            self.assertTrue(selected[0], 'Editor constructed before successful GPS input')
            editor = self.editor(paths=paths)
            created.append(editor)
            return editor
        selected = [False]
        def run(dialog):
            self.assertEqual([], created)
            self.assertEqual([str(self.image)], dialog.files)
            self.assertTrue(dialog.proposal_only)
            dialog.show()
            interact(dialog, owner)
            selected[0] = dialog.result() == QDialog.Accepted
            return dialog.result()
        record = read_metadata([str(self.image)])[str(self.image)]
        field = actions.gps_field(record)
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.folder / 'config')}), \
             patch.object(LocationDialog, 'exec', run), \
             patch('kim_metadata_editor.MetadataEditor', side_effect=create), \
             patch('kim_location.build_plan', side_effect=AssertionError('publication planner')), \
             patch('kim_location.allocate', side_effect=AssertionError('allocate output')), \
             patch('kim_location.assignments', side_effect=AssertionError('writer arguments')), \
             patch('kim_location_dialog.save_plan', side_effect=AssertionError('save plan')):
            actions.dispatch(owner, field, actions.field_actions(owner, field)[1])
        self.assertIsNone(owner._gps_dialog)
        if browser:
            self.wait_for(lambda: owner.worker is None and not owner.preview_workers and not owner.thumbnail_workers
                          and owner._comparison_worker is None and owner._tag_filter_worker is None)
        return owner, created

    def test_browser_add_starts_empty_then_retains_selection_in_visible_editor(self):
        fixtures.subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)],
                                check=True, capture_output=True)
        before = [fixtures.signature(p) for p in (self.image, self.sidecar)]
        members = set(self.folder.iterdir())
        proposals = []
        def select(dialog, owner):
            self.wait_for(lambda: dialog.gps_snapshot is not None and dialog.photo_preview.worker is None)
            self.assertEqual('', dialog.inputs['latitude'].text())
            self.assertEqual('', dialog.inputs['longitude'].text())
            self.assertIsNone(dialog.proposal)
            self.assertFalse(dialog.photo_preview.canvas.image.isNull())
            self.assertTrue(dialog.location_map.canvas.interactive)
            dialog.location_map.canvas.position_changed.emit([-23.5, 0])
            self.wait_for(lambda: dialog.proposal is not None and dialog.worker is None and not dialog.timer.isActive())
            proposals.append(dialog.proposal)
            dialog.apply_button.click()
            self.assertEqual(QDialog.Accepted, dialog.result())
        owner, created = self.route(select)
        self.assertEqual(1, len(created))
        editor = created[0]
        self.assertTrue(editor.isVisible())
        self.assertIs(proposals[0], editor.gps_drafts[str(self.image)])
        self.assertEqual([-23.5, 0], proposals[0]['proposed']['position'])
        review = fixtures.ReviewDialog(editor._combined_plan(), editor)
        review.show(); self.app.processEvents()
        self.assertTrue(review.apply_button.isVisible())
        self.assertFalse(review.apply_button.isEnabled())
        review.reject()
        self.assertEqual([editor], owner._gps_editors)
        self.assertEqual(before, [fixtures.signature(p) for p in (self.image, self.sidecar)])
        self.assertEqual(members, set(self.folder.iterdir()))

    def test_browser_edit_prefills_verified_camera_values_then_cancel_creates_no_editor(self):
        fixtures.subprocess.run(['exiftool', '-overwrite_original', '-GPSAltitude=80', '-GPSAltitudeRef=0',
                                '-GPSImgDirection=123', '-GPSImgDirectionRef=T', str(self.image)],
                                check=True, capture_output=True)
        before = [fixtures.signature(p) for p in (self.image, self.sidecar)]
        def cancel(dialog, owner):
            self.wait_for(lambda: dialog.gps_snapshot is not None)
            self.assertEqual('48.5', dialog.inputs['latitude'].text())
            self.assertEqual('2.25', dialog.inputs['longitude'].text())
            self.assertEqual(80, float(dialog.altitude_metres))
            self.assertEqual('123.0', dialog.inputs['direction'].text())
            dialog.reject()
            self.wait_for(lambda: dialog.worker is None and dialog.inspection_worker is None and dialog.photo_preview.worker is None)
            dialog.accept()
            self.assertNotEqual(QDialog.Accepted, dialog.result())
            self.assertIsNone(dialog.proposal)
        owner, created = self.route(cancel)
        self.assertEqual([], created)
        self.assertFalse(getattr(owner, '_gps_editors', []))
        self.assertEqual(before, [fixtures.signature(p) for p in (self.image, self.sidecar)])

    def test_browser_add_immediate_cancel_never_accepts_late_inspection(self):
        fixtures.subprocess.run(['exiftool', '-overwrite_original', '-GPS:all=', str(self.image)],
                                check=True, capture_output=True)
        def cancel(dialog, owner):
            self.app.processEvents()
            dialog.reject()
            self.wait_for(lambda: dialog.worker is None and dialog.inspection_worker is None and dialog.photo_preview.worker is None)
            dialog.accept()
            self.assertIsNone(dialog.proposal)
            self.assertNotEqual(QDialog.Accepted, dialog.result())
        owner, created = self.route(cancel)
        self.assertEqual([], created)

    def test_browser_close_cancels_gps_workers_and_cannot_reveal_editor(self):
        def close(dialog, owner):
            self.app.processEvents()
            owner.close()
            self.wait_for(lambda: dialog.worker is None and dialog.inspection_worker is None and dialog.photo_preview.worker is None)
            self.assertTrue(dialog.closing)
            self.assertIsNone(dialog.proposal)
            dialog.accept()
            self.assertNotEqual(QDialog.Accepted, dialog.result())
        owner, created = self.route(close, browser=True)
        self.assertEqual([], created)
        self.assertTrue(owner._closing)
        self.assertFalse(owner.isVisible())
