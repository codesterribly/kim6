"""Native Qt regression checks for Run and Crop review usability."""
import unittest
import test_recipes as base


class ReviewUsabilityTests(unittest.TestCase):
    run_gui = base.RecipeGuiTests.run_gui

    def test_selected_files_have_eight_visible_rows(self):
        self.run_gui('''
from PySide6.QtWidgets import QApplication
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
d = RunRecipeDialog(None, [f'/tmp/photo{i}.jpg' for i in range(12)])
d.resize(1120, 680); d.show(); app.processEvents()
height = d.inputs.sizeHintForRow(0)
assert d.inputs.viewport().height() >= height * 8, (d.inputs.viewport().height(), height)
assert d.diagnostics.isHidden(), 'Empty diagnostics reserve space'
assert d.inputs.columnWidth(1) < 120, 'Status wastes filename space'
d.reject()
''')

    def test_crop_review_has_five_columns_and_plain_output_label(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins
from kim_crop_standalone import CropReview
app = QApplication([])
with patch.object(CropReview, 'recheck'):
    d = CropReview(builtins()[0], ['/tmp/photo.jpg'])
    d.show(); app.processEvents()
    assert d.table.columnCount() == 5
    assert [d.table.horizontalHeaderItem(i).text() for i in range(5)] == ['Image', 'Original', 'Planned', 'Output', 'Status']
    assert not hasattr(d, 'output_path') and not hasattr(d, 'output_directory')
    assert d.output_label.text() == 'Output: '
    assert d.output_label.textInteractionFlags() & __import__('PySide6.QtCore', fromlist=['Qt']).Qt.TextSelectableByMouse
    assert d.output_label.metaObject().className() == 'QLabel'
    d.reject()
''')

    def test_crop_validation_errors_keep_their_original_classification(self):
        self.run_gui('''
import time
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kim_recipe_core import PreviewRow, builtins
from kim_crop_standalone import CropReview
app = QApplication([])
row = PreviewRow('/tmp/unsupported.img', problems=['Source format is unsupported'])
with patch('kim_crop_standalone.preview', return_value=[row]):
    d = CropReview(builtins()[0], ['/tmp/unsupported.img']); d.show()
    end = time.monotonic()+5
    while (d.worker is not None or not d.review_rows) and time.monotonic()<end:
        app.processEvents(); time.sleep(.005)
    app.processEvents()
    assert '1 image has other validation problems.' in d.status.text(), d.status.text()
    assert 'already exists' not in d.status.text() and 'share a planned output' not in d.status.text()
    d.details_button.click()
    assert 'Source format is unsupported' in d.details.toPlainText()
    d.reject()
''')

    def test_geometry_splitter_and_expansion_persistence(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
d = RunRecipeDialog(None, ['/tmp/example.jpg']); d.show(); app.processEvents()
d.resize(700, 610); d.splitter.setSizes([420, 240])
d.operations_button.setChecked(True); d.properties_button.setChecked(True)
sizes = d.splitter.sizes(); d.reject()
e = RunRecipeDialog(None, ['/tmp/example.jpg']); e.show(); app.processEvents()
assert e.size() == d.size(), (e.size(), d.size())
assert abs(e.splitter.sizes()[0] - sizes[0]) <= 5
assert e.operations_button.isChecked() and e.properties_button.isChecked()
from kim_review_ui import clamp_review_geometry, restore_splitter
for width, height in [(1366, 768), (1920, 1080)]:
    screen = type('Screen', (), {'availableGeometry': lambda self: QRect(0, 0, width, height)})()
    with patch.object(e, 'screen', return_value=screen):
        e.resize(9000, 9000); e.move(8000, 8000); clamp_review_geometry(e)
        assert e.width() <= width - 24 and e.height() <= height - 40
        assert e.x() >= 0 and e.x() + e.width() <= width
        assert e.y() >= 0 and e.y() + e.height() <= height
        e.resize(min(1120, width-24), min(680, height-40))
        e.operations_button.setChecked(False); e.properties_button.setChecked(False)
        app.processEvents()
        # A one-row queue has the same viewport allocation as a batch.
        assert e.inputs.viewport().height() >= 8 * e.inputs.sizeHintForRow(0)
e.settings.setValue('splitter', ['broken'])
restore_splitter(e.splitter, e.settings, 'splitter', [650, 430])
assert all(n > 0 for n in e.splitter.sizes())
e.reject()
''')

    def test_technical_disclosures_hide_empty_content(self):
        self.run_gui('''
from PySide6.QtWidgets import QApplication
from kim_recipe_core import PreviewRow
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
d = RunRecipeDialog(None, []); d.show(); app.processEvents()
assert d.diagnostics.isHidden() and d.technical_details_button.isHidden()
assert d.warning_view.isHidden() and d.operations_panel.isHidden() and d.properties.isHidden()
d.operations_button.click(); assert d.operations_panel.isVisible()
d.operations_button.click(); assert d.operations_panel.isHidden()
d.properties_button.click(); assert d.properties.isVisible()
d.diagnostics.setPlainText('Detailed failure')
assert d.technical_details_button.isVisible() and d.diagnostics.isHidden()
d.technical_details_button.click(); assert d.diagnostics.isVisible()
d.technical_details_button.click(); assert d.diagnostics.isHidden()
d.diagnostics.clear(); assert d.technical_details_button.isHidden()
row = PreviewRow('/tmp/source.psd', warnings=['PSD compatibility: best-effort reconstruction', 'Unprofiled RGB/grayscale source assumed sRGB'])
d.warning_view.set_rows([row]); assert d.warning_view.isVisible()
assert 'PSD' in d.warning_view.summary.text() and 'sRGB' in d.warning_view.summary.text()
d.warning_view.expand.click()
assert 'best-effort reconstruction' in d.warning_view.details.toPlainText()
assert d.warning_view.details.isVisible()
d.warning_view.expand.click(); assert d.warning_view.details.isHidden()
d.warning_view.set_rows([]); assert d.warning_view.isHidden()
d.reject()
''')

    def test_crop_column_widths_persist(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins
from kim_crop_standalone import CropReview
app = QApplication([])
with patch.object(CropReview, 'recheck'):
    d = CropReview(builtins()[0], []); d.show(); app.processEvents()
    d.table.setColumnWidth(3, 180); d.table.setColumnWidth(0, 170); d.reject()
    e = CropReview(builtins()[0], []); e.show(); app.processEvents()
    assert e.table.columnWidth(3) == 180 and e.table.columnWidth(0) == 170
    assert sum(e.table.columnWidth(i) for i in range(5)) <= e.table.viewport().width()
    from PySide6.QtWidgets import QHeaderView
    assert all(e.table.horizontalHeader().sectionResizeMode(i) == QHeaderView.Interactive for i in range(5))
    e.reject()
''')


REAL = '''
import copy
import subprocess
import time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from kim_recipe_core import builtins, config_path, RecipeLibrary, save_library, load_library, execute
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
root = config_path().parent.parent
first_dir = root/'first'; second_dir = root/'second'; shared = root/'shared'
for directory in (first_dir, second_dir, shared): directory.mkdir()
first = first_dir/'sample.png'; second = second_dir/'sample.png'
for source in (first, second):
    subprocess.run(['magick', '-size', '24x16', 'xc:red', str(source)], check=True)
files = [str(first), str(second)]
before = {source: (source.read_bytes(), source.stat().st_mtime_ns) for source in (first, second)}
def settle(d):
    end = time.monotonic()+18
    while time.monotonic()<end:
        app.processEvents()
        if d.worker is None and d.preflight_worker is None and d.editor_dialog is None: break
        time.sleep(.005)
    app.processEvents()
    assert d.worker is None and d.preflight_worker is None and d.editor_dialog is None

def unchanged():
    for source, value in before.items():
        assert (source.read_bytes(), source.stat().st_mtime_ns) == value
'''


class RealReviewUsabilityTests(unittest.TestCase):
    run_gui = base.RecipeGuiTests.run_gui

    def test_original_default_and_mixed_source_directories(self):
        self.run_gui(REAL + '''
recipe = builtins()[0]; stored = copy.deepcopy(recipe)
d = RunRecipeDialog(recipe, files); settle(d)
assert d.run_button.isEnabled() and 'Web subfolder beside each source' in d.destination_label.text()
assert [Path(d.rows[i].output).parent for i in range(2)] == [first_dir/'Web', second_dir/'Web']
assert not (first_dir/'Web').exists()
assert d.recipe == recipe == stored == builtins()[0]
d.reject(); unchanged()
''')

    def test_beside_override_invalidates_plan_and_executes_reviewed_paths(self):
        self.run_gui(REAL + '''
d = RunRecipeDialog(builtins()[0], files); settle(d)
previous = d.approved_plan; generation = d.generation
d.destination_choice.setCurrentIndex(1)
assert d.approved_plan is None and not d.run_button.isEnabled() and d.generation > generation
settle(d)
assert d.approved_plan != previous and d.run_button.isEnabled()
assert d.execution_recipe['destination'] == {'mode': 'beside'}
assert d.recipe == builtins()[0]
outputs = [d.rows[i].output for i in range(2)]
assert [Path(p).parent for p in outputs] == [first_dir, second_dir]
# The old frozen plan cannot authorize the new destination.
assert not execute(d.execution_recipe, files, approved_plan=previous)[0]['ok']
d.start_execution(); settle(d)
assert d.execution_succeeded and [r['output'] for r in d.results] == outputs
assert all(Path(p).is_file() for p in outputs)
assert not (first_dir/'Web').exists()
d.reject(); unchanged()
''')

    def test_shared_override_binds_review_and_execution(self):
        self.run_gui(REAL + '''
# Distinct names avoid a batch collision in the shared destination.
renamed = second.with_name('different.png'); second.rename(renamed)
files[1] = str(renamed); before[renamed] = before.pop(second)
d = RunRecipeDialog(builtins()[0], files); settle(d)
with patch('kim_recipe_run.QFileDialog.getExistingDirectory', return_value=str(shared)):
    d.destination_choice.setCurrentIndex(2)
assert d.approved_plan is None and not d.run_button.isEnabled()
settle(d)
assert d.run_button.isEnabled() and d.chosen == str(shared)
outputs = [d.rows[i].output for i in range(2)]
assert all(Path(p).parent == shared for p in outputs)
assert str(shared) in d.destination_label.text()
d.start_execution(); settle(d)
assert d.execution_succeeded and [r['output'] for r in d.results] == outputs
assert d.recipe == builtins()[0]
d.reject(); unchanged()
''')

    def test_duplicate_batch_blocking_summary(self):
        self.run_gui(REAL + '''
d = RunRecipeDialog(builtins()[0], files); d.show(); settle(d)
with patch('kim_recipe_run.QFileDialog.getExistingDirectory', return_value=str(shared)):
    d.destination_choice.setCurrentIndex(2)
settle(d)
text = d.blocking_summary.text()
assert d.blocking_summary.isVisible() and '2 images have conflicting output filenames.' in text
assert text.count('Multiple selected sources') == 1
assert 'already exist on disk' not in text
assert d.rows[0].output in d.blocking_summary.toolTip()
assert not d.run_button.isEnabled() and d.approved_plan is None
assert all(d.inputs.topLevelItem(i).text(1) == 'Blocked' for i in range(2))
assert 'multiple selected sources' in d.inputs.topLevelItem(0).toolTip(1)
d.technical_details_button.click(); assert d.diagnostics.isVisible()
d.destination_choice.setCurrentIndex(0); settle(d)
assert d.run_button.isEnabled() and 'Web subfolder' in d.destination_label.text()
d.reject(); unchanged()
''')

    def test_disk_collision_blocking_summary(self):
        self.run_gui(REAL + '''
d = RunRecipeDialog(builtins()[0], [files[0]]); settle(d)
output = Path(d.rows[0].output); output.parent.mkdir(); output.write_bytes(b'occupied')
d.start_preflight(); d.show(); settle(d)
assert d.blocking_summary.isVisible() and '1 image would use an output filename that already exists on disk.' in d.blocking_summary.text()
assert 'Multiple selected sources' not in d.blocking_summary.text()
assert str(output) in d.blocking_summary.toolTip()
assert d.output_path.text() == str(output)
assert not d.run_button.isEnabled() and d.approved_plan is None
d.start_execution(); assert d.worker is None and output.read_bytes() == b'occupied'
d.reject(); unchanged()
''')

    def test_user_recipe_editor_preserves_queue_and_invalidates_changed_plan(self):
        self.run_gui(REAL + '''
recipe = builtins()[0]; recipe.update(id='user-test', name='My export')
save_library(RecipeLibrary([recipe]))
d = RunRecipeDialog(recipe, files); settle(d)
d.inputs.setCurrentItem(d.inputs.topLevelItem(1)); selected = d.inputs.currentItem()
old_plan = d.approved_plan
assert d.edit_button.text() == 'Edit recipe…'
d.edit_recipe(); app.processEvents()
editor = d.editor_dialog.widget
assert editor.recipe['id'] == recipe['id'] and not editor.immutable
assert not d.run_button.isEnabled()
editor.name.setText('Updated export'); editor.changed(); assert editor.save()
d.editor_dialog.accept(); settle(d)
assert d.files == files and d.inputs.currentItem() is selected
assert d.recipe['name'] == 'Updated export' and d.approved_plan != old_plan
assert d.worker is None and not d.results and d.run_button.isEnabled()
d.reject(); unchanged()
''')

    def test_builtin_customization_uses_unsaved_duplicate_workflow(self):
        self.run_gui(REAL + '''
stored = builtins()[0]
d = RunRecipeDialog(stored, files); settle(d)
old_plan = d.approved_plan
assert d.edit_button.text() == 'Customize built-in…'
d.edit_recipe(); app.processEvents()
editor = d.editor_dialog.widget
assert editor.immutable and editor.recipe['id'] == stored['id']
assert load_library().recipes == [] and editor.saved_recipe_id is None
editor.management_buttons['Duplicate to Edit'].click()
assert not editor.immutable and editor.recipe['id'] != stored['id']
assert editor.recipe['destination'] == stored['destination']
assert editor.recipe['steps'] == stored['steps']
assert load_library().recipes == []
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Discard):
    d.editor_dialog.reject()
settle(d)
assert d.files == files and d.recipe == stored == builtins()[0]
assert d.approved_plan == old_plan and not d.results
assert load_library().recipes == []
d.reject(); unchanged()
''')

    def test_crop_output_label_shows_complete_filename_and_executes_approved_name(self):
        self.run_gui(REAL + '''
from kim_crop_standalone import CropReview, CropExecution
from kim_image_ops import CROP_DEFAULTS
long_source = first.with_name('a_very_long_descriptive_source_filename_' * 3 + '.png')
first.rename(long_source); before[long_source] = before.pop(first)
recipe = {'schema': 3, 'id': 'crop-check', 'name': 'Crop', 'description': '', 'media': 'image',
          'steps': [dict(op='image.crop', **{**CROP_DEFAULTS, 'aspect': '1:1'}),
                    {'op': 'file.rename_output', 'pattern': '{stem}_crop'}],
          'destination': {'mode': 'beside'}}
d = CropReview(recipe, [str(long_source)]); d.show()
end = time.monotonic()+15
while (d.worker is not None or not d.review_rows) and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.worker is None and d.apply_button.isEnabled(), d.status.text()
output = d.review_rows[0].output
assert d.output_label.text() == 'Output: ' + Path(output).name and d.output_label.isVisible()
assert d.output_label.textInteractionFlags() & __import__('PySide6.QtCore', fromlist=['Qt']).Qt.TextSelectableByMouse
assert d.table.item(0, 3).toolTip() == Path(output).name
assert d.table.columnCount() == 5
assert d.windowTitle() == 'KIMng - Crop - Review Changes'
d.approve(); assert d.approved_plan
worker = CropExecution(d.approved, d.files, approved_plan=d.approved_plan)
worker.run()
assert not worker.error and worker.results[0]['ok'], (worker.error, worker.results)
assert worker.results[0]['output'] == output and Path(output).is_file()
unchanged()
''')

    def test_crop_review_accepts_new_shared_web_directory(self):
        self.run_gui(REAL + '''
from kim_crop_standalone import CropReview, CropExecution
from kim_image_ops import CROP_DEFAULTS
sources = []
for index in range(5):
    source = first_dir / (('long_descriptive_source_filename_' * 4) + f'{index}.png')
    subprocess.run(['magick', '-size', '24x16', 'xc:blue', str(source)], check=True)
    sources.append(str(source))
recipe = {'schema': 3, 'id': 'crop-check', 'name': 'Crop', 'description': '', 'media': 'image',
          'steps': [dict(op='image.crop', **{**CROP_DEFAULTS, 'aspect': '1:1'}),
                    {'op': 'file.rename_output', 'pattern': '{stem}_crop'}],
          'destination': {'mode': 'beside'}}
d = CropReview(recipe, sources); d.show()
end = time.monotonic()+15
while (d.worker is not None or not d.review_rows) and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
web = first_dir/'Web'; web.mkdir()
occupied = web/(('long_descriptive_source_filename_' * 4) + '0_crop.png')
occupied.write_bytes(b'occupied')
d.destination_entry.setText(str(web)); d.submit_destination()
end = time.monotonic()+15
while d.worker is not None and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.apply_button.isEnabled(), d.status.text()
assert '5 ready, 0 blocked' in d.status.text()
assert Path(d.review_rows[0].output).name == occupied.stem + '_1' + occupied.suffix
assert occupied.read_bytes() == b'occupied'
web2 = first_dir/'Web2'
d.destination_entry.setText(str(web2)); d.submit_destination()
end = time.monotonic()+15
while d.worker is not None and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.apply_button.isEnabled(), d.status.text()
outputs = [row.output for row in d.review_rows]
assert len(outputs) == 5 and all(Path(path).parent == web2 for path in outputs)
from PySide6.QtCore import QRect
for width, height in [(1366, 768), (1920, 1080)]:
    screen = type('Screen', (), {'availableGeometry': lambda self, w=width, h=height: QRect(0, 0, w, h)})()
    with patch.object(d, 'screen', return_value=screen):
        d.resize(width-24, min(680, height-40)); app.processEvents()
        assert sum(d.table.columnWidth(i) for i in range(5)) <= d.table.viewport().width()
        assert not d.table.horizontalScrollBar().isVisible()
d.table.setCurrentCell(3, 3)
assert d.output_label.text() == 'Output: ' + Path(outputs[3]).name
d.approve(); assert d.approved_plan
worker = CropExecution(d.approved, d.files, approved_plan=d.approved_plan)
worker.run()
assert not worker.error and len(worker.results) == 5, (worker.error, worker.results)
assert [result['output'] for result in worker.results] == outputs
assert all(result['ok'] and Path(result['output']).is_file() for result in worker.results)
''')

    def test_crop_duplicate_batch_summary_and_destination_recheck(self):
        self.run_gui(REAL + '''
from kim_crop_standalone import CropReview
recipe = {'schema': 3, 'id': 'duplicate-crop', 'name': 'Crop', 'description': '', 'media': 'image',
          'steps': [{'op': 'file.rename_output', 'pattern': '{stem}_copy'}],
          'destination': {'mode': 'directory', 'ask': False, 'path': str(shared)}}
d = CropReview(recipe, files); d.show()
end = time.monotonic()+15
while (d.worker is not None or not d.review_rows) and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.apply_button.isEnabled(), d.status.text()
assert '2 images selected, 2 ready, 0 blocked.' in d.status.text()
shared_outputs = [row.output for row in d.review_rows]
assert len(set(shared_outputs)) == 2
assert all(Path(path).parent == shared for path in shared_outputs)
assert not any(row.problems for row in d.review_rows)
d.destination_entry.clear(); d.submit_destination()
end = time.monotonic()+15
while d.worker is not None and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.apply_button.isEnabled(), d.status.text()
assert '2 images selected, 2 ready, 0 blocked.' in d.status.text()
d.reject(); unchanged()
''')

    def test_cancelled_directory_choice_blocks_until_default_is_restored(self):
        self.run_gui(REAL + '''
d = RunRecipeDialog(builtins()[0], [files[0]]); settle(d)
with patch('kim_recipe_run.QFileDialog.getExistingDirectory', return_value=''):
    d.destination_choice.setCurrentIndex(2)
settle(d)
assert not d.run_button.isEnabled() and d.approved_plan is None
assert 'Choose a directory before running' in d.destination_label.text()
d.start_execution(); assert d.worker is None
d.destination_choice.setCurrentIndex(0); settle(d)
assert d.run_button.isEnabled() and d.recipe == builtins()[0]
d.reject(); unchanged()
''')

    def test_crop_disk_collision_summary_and_details_disable_apply(self):
        self.run_gui(REAL + '''
from kim_crop_standalone import CropReview
recipe = {'schema': 3, 'id': 'crop-check', 'name': 'Crop', 'description': '', 'media': 'image',
          'steps': [{'op': 'file.rename_output', 'pattern': '{stem}_crop'}],
          'destination': {'mode': 'beside'}}
output = first.with_name('sample_crop.png'); output.write_bytes(b'occupied')
d = CropReview(recipe, [files[0]]); d.show()
end = time.monotonic()+15
while (d.worker is not None or not d.review_rows) and time.monotonic()<end:
    app.processEvents(); time.sleep(.005)
assert d.worker is None and d.apply_button.isEnabled(), d.status.text()
numbered = output.with_name(output.stem + '_1' + output.suffix)
assert d.output_label.text() == 'Output: ' + numbered.name
assert d.table.item(0, 4).text() == 'Ready'
assert '1 image selected, 1 ready, 0 blocked.' in d.status.text()
assert d.review_rows[0].output == str(numbered)
assert not numbered.exists()
d.approve()
assert d.approved_plan is not None
assert d.approved_plan[0].output == str(numbered)
assert output.read_bytes() == b'occupied'
d.reject(); unchanged()
''')

    def test_saved_customization_selects_user_copy_without_mutating_builtin(self):
        self.run_gui(REAL + '''
stored = builtins()[0]
d = RunRecipeDialog(stored, files); settle(d)
d.edit_recipe(); app.processEvents()
editor = d.editor_dialog.widget
editor.management_buttons['Duplicate to Edit'].click()
new_id = editor.recipe['id']
editor.name.setText('My customized export'); editor.changed()
assert editor.save()
d.editor_dialog.accept(); settle(d)
assert d.selected_id == new_id and d.edit_button.text() == 'Edit recipe…'
assert d.files == files and builtins()[0] == stored
assert load_library().recipes[0]['id'] == new_id
assert d.worker is None and not d.results
d.reject(); unchanged()
''')

    def test_crop_default_columns_fit_desktop_widths_and_remain_resizable(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins
from kim_crop_standalone import CropReview
app = QApplication([])
with patch.object(CropReview, 'recheck'):
    d = CropReview(builtins()[0], ['/tmp/photo.jpg'])
    screen = type('Screen', (), {'availableGeometry': lambda self: QRect(0, 0, 1920, 1080)})()
    with patch.object(d, 'screen', return_value=screen):
        d.resize(1050, 600); d.show(); app.processEvents()
        ratio = d.table.columnWidth(0) / d.table.columnWidth(3)
        assert .8 <= ratio <= 1.2, (ratio, [d.table.columnWidth(i) for i in range(5)])
        assert sum(d.table.columnWidth(i) for i in range(5)) <= d.table.viewport().width()
        assert d.table.columnWidth(1) < 160 and d.table.columnWidth(4) < 120, [d.table.columnWidth(i) for i in range(5)]
        d.resize(1400, 650); app.processEvents()
        assert sum(d.table.columnWidth(i) for i in range(5)) <= d.table.viewport().width()
        d.table.setColumnWidth(3, 280)
        d.resize(1100, 650); app.processEvents()
        assert d.table.columnWidth(3) <= 280
        assert sum(d.table.columnWidth(i) for i in range(5)) <= d.table.viewport().width()
        saved_widths = [d.table.columnWidth(i) for i in range(5)]
    d.close()
    e = CropReview(builtins()[0], ['/tmp/photo.jpg'])
    e.show(); app.processEvents()
    assert sum(e.table.columnWidth(i) for i in range(5)) <= e.table.viewport().width()
    assert e.table.columnWidth(3) <= saved_widths[3]
    assert e.table.columnWidth(3) > 0
    e.reject()
''')
