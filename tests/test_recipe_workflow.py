"""Focused library, native service-menu, editor, and confirmation workflow contracts."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_recipes as base
import kim_recipe_core as core

ROOT = Path(__file__).resolve().parents[1]


class RecipeFolderTests(unittest.TestCase):
    def test_legacy_library_empty_folders_moves_and_stable_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'recipes.json'; original = base.recipe()
            path.write_text(json.dumps([original]))
            library = core.read_library(path)
            portfolio = library.create_folder('Portfolio')
            empty = library.create_folder('Empty Folder')
            library.move_recipe(original['id'], portfolio)
            core.save_library(library, path)
            payload = json.loads(path.read_text())
            self.assertEqual(payload['schema'], 1)
            self.assertEqual(len(payload['folders']), 2)
            library = core.read_library(path)
            library.rename_folder(portfolio, 'Portfolio Renamed')
            self.assertEqual(library.recipes[0]['id'], original['id'])
            self.assertEqual(library.recipes[0]['folder'], portfolio)
            library.move_recipe(original['id'], empty)
            library.delete_folder(empty)
            self.assertNotIn('folder', library.recipes[0])
            self.assertEqual(len(library.recipes), 1)
            core.save_library(library, path)
            core.save_users(library.recipes, path)
            self.assertEqual(core.read_library(path).folders[0]['id'], portfolio)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse((Path(tmp)/'Portfolio').exists())

    def test_invalid_and_duplicate_folders_are_rejected(self):
        library = core.RecipeLibrary()
        library.create_folder('Portfolio')
        for name in ('', ' ', '../nested', 'a/b', 'a\\b', 'a\nb', 'a\x7fb', 'x'*61, 'Unfiled', 'Built-In', 'portfolio', 'Ｐortfolio'):
            with self.subTest(name=name), self.assertRaises(core.RecipeError): library.create_folder(name)
        data = {'schema': 1, 'recipes': [], 'folders': [{'id': 'folder-one', 'name': 'One', 'parent': 'folder-two'}]}
        with self.assertRaises(core.RecipeError): core.validate_library(data)
        recipe = base.recipe(); recipe['folder'] = 'missing'
        with self.assertRaises(core.RecipeError): core.validate_library({'schema': 1, 'recipes': [recipe], 'folders': []})

    def test_saved_recipe_references_use_ids_not_names(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}):
            first = base.recipe(); first['name'] = 'Same Name'
            second = base.recipe(); second.update(id='second', name='Same Name')
            second['steps'][0]['pattern'] = '{stem}_second'
            core.save_library(core.RecipeLibrary([first, second]))
            self.assertEqual(core.lookup_recipe('second')['steps'][0]['pattern'], '{stem}_second')
            with self.assertRaises(core.RecipeError): core.lookup_recipe('Same Name')
            with self.assertRaises(core.RecipeError): core.lookup_recipe('../recipes.json')


class RecipeMenuTests(unittest.TestCase):
    def test_empty_native_template_and_nonroot_save(self):
        import configparser
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ROOT/'src/kim_recipes.desktop.in')
        entry = parser['Desktop Entry']
        self.assertEqual(entry['Actions'], 'KIMRecipe0Run;KIMRecipe1Editor;')
        self.assertEqual(entry['_X-KDE-Submenu'], 'KIM6 Recipes')
        self.assertNotIn('X-KDE-Priority', entry)
        self.assertEqual(parser['Desktop Action KIMRecipe0Run']['Exec'], 'kim_all recipe --choose -- %F')
        self.assertEqual(parser['Desktop Action KIMRecipe1Editor']['Exec'], 'kim_all recipe --editor')
        self.assertEqual(len(parser.sections()), 3)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}):
            core.save_library(core.RecipeLibrary([base.recipe()]))
            self.assertEqual(list(Path(tmp).rglob('*.desktop')), [])

    def test_generic_cli_preserves_verbatim_files_and_boundary(self):
        # No QtTest dependency: mock only the dialog launcher at the CLI boundary.
        import types
        paths = ['/tmp/space name.jpg', '/tmp/$cash `tick` ; quote " %.png', '--literal.jpg']
        launcher = types.ModuleType('kim_recipe_run')
        from unittest.mock import Mock
        launcher.launch_run = Mock(return_value=0)
        with patch.dict(sys.modules, {'kim_recipe_run': launcher}), patch.object(sys, 'argv', ['kim_recipe_core.py', '--choose', '--', *paths]):
            self.assertEqual(core.main(), 0)
        launcher.launch_run.assert_called_once_with(None, paths)

    def test_grouped_library_has_stable_ids_sorted_names_and_empty_folders(self):
        a = base.recipe(); a.update(id='a', name='same', folder='z')
        b = base.recipe(); b.update(id='b', name='Same', folder='a')
        library = core.RecipeLibrary([a, b], [{'id': 'z', 'name': 'Zoo'}, {'id': 'a', 'name': 'alpha'}, {'id': 'empty', 'name': 'Empty'}])
        groups = core.library_groups(library)
        self.assertEqual([g[1] for g in groups], ['Built-In', 'Root', 'alpha', 'Empty', 'Zoo', 'Unfiled'])
        self.assertEqual(groups[2][2][0]['id'], 'b')
        library.rename_folder('a', 'renamed')
        self.assertEqual(b['folder'], 'a')
        self.assertEqual(core.library_groups(core.RecipeLibrary())[0][2][0]['id'], 'web-export')


WAIT = '''
def settle(dialog):
    loop = QEventLoop()
    timer = QTimer(); timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if dialog.preflight_worker is None and dialog.worker is None and getattr(dialog, 'add_worker', None) is None and getattr(dialog, 'editor_dialog', None) is None else None)
    deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
    timer.start(); deadline.start(15000); loop.exec(); timer.stop(); deadline.stop()
    assert dialog.preflight_worker is None and dialog.worker is None and getattr(dialog, 'add_worker', None) is None and getattr(dialog, 'editor_dialog', None) is None, 'Worker did not finish'
'''


class WorkflowGuiTests(unittest.TestCase):
    run_gui = base.RecipeGuiTests.run_gui

    def test_generic_selector_search_stable_ids_and_editor_round_trips(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from kim_recipe_core import RecipeLibrary, save_library, load_library, builtins, PreviewRow
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
a = builtins()[0]; a.update(id='a', name='Same', folder='alpha')
b = builtins()[0]; b.update(id='b', name='Same')
save_library(RecipeLibrary([b, a], [{'id': 'alpha', 'name': 'Alpha'}, {'id': 'empty', 'name': 'Empty'}]))
def preview(recipe, files, chosen, start_index):
    return [PreviewRow(files[0], '/planned/' + recipe['id'] + str(start_index) + '.jpg', 'image', 'jpeg')]
files = ['/Dolphin/photo $one.jpg', '/Dolphin/photo two.jpg']
with patch('kim_recipe_run.preview', side_effect=preview), patch('kim_recipe_run.execute') as execute:
    w = RunRecipeDialog(None, files)
    assert w.selected_id is None and w.selector.currentIndex() == -1
    assert w.preflight_worker is None and not w.run_button.isEnabled()
    assert w.selector.placeholderText() == 'Choose a recipe…'
    assert not w.selector.model().item(0).isEnabled()
    w.search.setText('ALPHA'); assert w.selector.findData('a') >= 0 and w.selector.findData('b') == -1
    w.selector.setCurrentIndex(w.selector.findData('a')); settle(w)
    assert w.recipe['id'] == 'a' and w.run_button.isEnabled()
    w.inputs.setCurrentItem(w.inputs.topLevelItem(1))
    selected_preview = w.inputs.currentItem()
    chosen = w.chosen = '/previous-context'
    def save_new(dialog):
        editor = dialog.widget
        assert editor.from_run
        editor.load_photos_and_run(); assert editor.run_dialog is None
        editor.new(); new_id = editor.recipe['id']
        assert not any(r['id'] == new_id for r in load_library().recipes)
        editor.name.setText('New saved'); editor.changed()
        editor.library_folder.setCurrentIndex(editor.library_folder.findData('alpha'))
        assert editor.save() and editor.saved_new_recipe_id == new_id
        dialog.accept()
    with patch('kim_recipe_dialog.RecipeDialog.open', lambda dialog: QTimer.singleShot(0,lambda:save_new(dialog))): w.create_recipe()
    settle(w)
    new_id = w.selected_id
    assert w.recipe['name'] == 'New saved' and w.recipe['folder'] == 'alpha'
    assert w.files == files and w.inputs.currentItem() is selected_preview and w.chosen == chosen
    def cancel_draft(dialog):
        dialog.widget.duplicate()
        assert dialog.widget.saved_new_recipe_id is None
        with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Discard): dialog.reject()
        return QDialog.Rejected
    for i in range(3):
        with patch('kim_recipe_dialog.RecipeDialog.open', lambda dialog: QTimer.singleShot(0,lambda:cancel_draft(dialog))): w.create_recipe()
        settle(w)
        assert w.selected_id == new_id and w.files == files and w.inputs.currentItem() is selected_preview
    assert len(load_library().recipes) == 3 and not execute.called
    # A deleted selected definition cannot be silently replaced or executed.
    library = load_library(); library.recipes = [r for r in library.recipes if r['id'] != new_id]; save_library(library)
    w.start_execution(); assert not execute.called and not w.run_button.isEnabled()
    assert 'Unknown saved recipe' in w.summary.text()
    w.close()
''')

    def test_builtin_only_and_large_library_keyboard_search(self):
        self.run_gui('''
import copy
from unittest.mock import patch
from PySide6.QtCore import QEvent, Qt, QTimer, QEventLoop
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from kim_recipe_core import RecipeLibrary, save_library, builtins, PreviewRow
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
empty = RunRecipeDialog(None, ['/input.jpg'])
assert [empty.selector.itemData(i) for i in range(empty.selector.count()) if empty.selector.itemData(i)] == ['web-export']
assert empty.selector.currentIndex() == -1 and not empty.run_button.isEnabled()
empty.reject()
recipes = []
for i in range(200):
    r = copy.deepcopy(builtins()[0]); r.update(id='user-' + str(i), name='Preset ' + str(i), folder='collection')
    recipes.append(r)
recipes[137]['name'] = 'Target preset'
save_library(RecipeLibrary(recipes, [{'id': 'collection', 'name': 'Collection'}]))
with patch('kim_recipe_run.preview', return_value=[PreviewRow('/input.jpg')]):
    w = RunRecipeDialog(None, ['/input.jpg']); w.show(); app.processEvents()
    w.search.setFocus()
    QApplication.sendEvent(w.search, QKeyEvent(QEvent.KeyPress, Qt.Key_T, Qt.NoModifier, 'TARGET'))
    assert w.selector.count() == 2 and w.selected_id is None
    w.selector.setFocus()
    QApplication.sendEvent(w.selector, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    settle(w)
    assert w.selected_id == 'user-137' and w.run_button.isEnabled()
    assert w.files == ['/input.jpg']
    w.close()
''')

    def test_rapid_recipe_changes_invalidate_queued_preflight_results(self):
        self.run_gui('''
import threading
from unittest.mock import patch
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from kim_recipe_core import RecipeLibrary, save_library, builtins, PreviewRow
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
a = builtins()[0]; a.update(id='a', name='First')
b = builtins()[0]; b.update(id='b', name='Second')
save_library(RecipeLibrary([a, b]))
started = threading.Event(); release = threading.Event(); calls = []
def preview(recipe, files, chosen, start_index):
    calls.append(recipe['id'])
    if len(calls) == 1:
        started.set(); assert release.wait(10)
    return [PreviewRow(files[0], '/planned/' + recipe['id'] + '.jpg', 'image', 'jpeg')]
with patch('kim_recipe_run.preview', side_effect=preview), patch('kim_recipe_run.execute') as execute:
    w = RunRecipeDialog(None, ['/selected.jpg'])
    w.selector.setCurrentIndex(w.selector.findData('a'))
    loop = QEventLoop(); timer = QTimer(); timer.setInterval(10)
    def switch():
        if not started.is_set(): return
        timer.stop()
        for recipe_id in ('b', 'a', 'b'):
            w.selector.setCurrentIndex(w.selector.findData(recipe_id))
            assert not w.run_button.isEnabled() and not w.rows and w.properties.rowCount() == 0
            w.start_execution(); assert not execute.called
        release.set(); loop.quit()
    timer.timeout.connect(switch); timer.start(); QTimer.singleShot(12000, loop.quit); loop.exec()
    settle(w)
    assert calls == ['a', 'b'], calls
    assert w.recipe['id'] == 'b' and w.rows[0].output == '/planned/b.jpg'
    assert w.run_button.isEnabled() and w.reviewed_generation == w.generation
    w.reject(); assert not execute.called
''')

    def test_editor_folder_management_and_empty_library_workflow(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import load_library
app = QApplication([])
w = RecipeWidget(); assert w.files == []
with patch('kim_recipe_dialog.QInputDialog.getText', return_value=('Portfolio', True)):
    w.create_folder()
folder_id = load_library().folders[0]['id']
assert load_library().recipes == []
w.duplicate(); recipe_id = w.recipe['id']
w.library_folder.setCurrentIndex(w.library_folder.findData(folder_id))
assert w.is_dirty() and w.save()
assert load_library().recipes[0]['folder'] == folder_id
assert w.recipe['destination']['folder'] == 'Web'
with patch('kim_recipe_dialog.QInputDialog.getItem', return_value=('Portfolio', True)), patch('kim_recipe_dialog.QInputDialog.getText', return_value=('Portfolio New', True)):
    w.rename_folder()
assert load_library().folders[0] == {'id': folder_id, 'name': 'Portfolio New'}
assert load_library().recipes[0]['id'] == recipe_id
with patch('kim_recipe_dialog.QInputDialog.getItem', return_value=('Portfolio New', True)), patch('kim_recipe_dialog.QMessageBox.exec', return_value=QMessageBox.Cancel):
    w.delete_folder()
assert len(load_library().folders) == 1
with patch('kim_recipe_dialog.QInputDialog.getItem', return_value=('Portfolio New', True)), patch('kim_recipe_dialog.QMessageBox.exec', return_value=QMessageBox.Yes):
    w.delete_folder()
assert load_library().folders == []
assert load_library().recipes[0]['id'] == recipe_id and 'folder' not in load_library().recipes[0]
w.close()
''')

    def test_editor_load_run_resolves_changes_and_never_executes_automatically(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import config_path
app = QApplication([])
w = RecipeWidget(); w.set_examples(['/example-only.jpg']); w.duplicate()
w.name.setText('Changed'); w.changed()
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Cancel), patch('kim_recipe_dialog.QFileDialog.getOpenFileNames') as picker:
    w.load_photos_and_run(); assert not picker.called
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Save), patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=(['/selected-one.jpg', '/selected-two.jpg'], '')), patch('kim_recipe_dialog.RunRecipeDialog') as confirmation, patch('kim_recipe_run.execute') as execute:
    confirmation.return_value.exec.return_value = QDialog.Rejected
    w.load_photos_and_run()
    assert confirmation.call_args.args[0]['name'] == 'Changed'
    assert confirmation.call_args.args[1] == ['/selected-one.jpg', '/selected-two.jpg']
    assert not execute.called
w.name.setText('Discarded'); w.changed()
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Discard), patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=(['/selected.jpg'], '')), patch('kim_recipe_dialog.RunRecipeDialog') as confirmation:
    w.load_photos_and_run(); assert confirmation.call_args.args[0]['name'] == 'Changed'
assert not w.is_dirty()
with patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=([], '')), patch('kim_recipe_dialog.RunRecipeDialog') as confirmation:
    w.load_photos_and_run(); assert not confirmation.called
w.selector.setCurrentIndex(0); w.parameter(3, 'quality', 88)
stored = config_path().read_bytes()
with patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=(['/selected.jpg'], '')), patch('kim_recipe_dialog.RunRecipeDialog') as confirmation:
    w.load_photos_and_run(); assert confirmation.call_args.args[0]['steps'][3]['quality'] == 88
assert config_path().read_bytes() == stored
w.close()
''')

    def test_stable_id_launch_selects_saved_recipe_without_execution(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog
from kim_recipe_core import RecipeLibrary, save_library, builtins
from kim_recipe_run import launch_run
app = QApplication([])
r = builtins()[0]; r.update(id='saved-id', name='Display Name', folder='portfolio')
save_library(RecipeLibrary([r], [{'id': 'portfolio', 'name': 'Portfolio'}]))
with patch('kim_recipe_run.RunRecipeDialog') as confirmation, patch('kim_recipe_run.execute') as execute:
    confirmation.return_value.exec.return_value = QDialog.Rejected
    launch_run('saved-id', ['/selected.jpg'])
    assert confirmation.call_args.args[0]['id'] == 'saved-id'
    assert confirmation.call_args.args[1] == ['/selected.jpg']
    assert confirmation.call_args.args[2][0]['name'] == 'Portfolio'
    assert not execute.called
with patch('kim_recipe_run.QMessageBox.critical') as error, patch('kim_recipe_run.execute') as execute:
    assert launch_run('deleted-id', ['/selected.jpg']) == 1
    assert 'Unknown saved recipe id' in error.call_args.args[2]
    assert not execute.called
''')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_complete_batch_preflight_reports_every_input_and_blocks_run(self):
        self.run_gui('''
import subprocess
from pathlib import Path
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins, config_path
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
base = config_path().parent.parent
first = base/'first photo.jpg'; second = base/'second.jpg'; bad = base/'unsupported.txt'
for path in (first, second): subprocess.run(['magick', '-size', '40x20', 'xc:red', str(path)], check=True)
subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2020:01:02 03:04:05', str(first)], check=True, capture_output=True)
bad.write_text('not media')
before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (first, second, bad)}
r = builtins()[0]; r.update(id='proofs', name='Client Proofs', folder='portfolio')
r['steps'] = [{'op': 'metadata.strip_all'}, {'op': 'metadata.creator', 'enabled': False}, {'op': 'metadata.copyright_notice', 'value': 'Copyright {YEAR} Example'}]
files = [str(first), str(second), str(bad)]
w = RunRecipeDialog(r, files, [{'id': 'portfolio', 'name': 'Portfolio'}]); settle(w)
assert w.heading.text() == 'Recipe: Portfolio / Client Proofs'
assert w.inputs.topLevelItemCount() == 3 and w.files == files
assert '1 ready; 2 problems' in w.summary.text() and not w.run_button.isEnabled()
assert 'Copyright {YEAR} needs a capture date' in w.diagnostics.toPlainText()
assert 'Set Capture Date' in w.diagnostics.toPlainText()
assert w.operations.topLevelItemCount() == 3 and 'Disabled' in w.operations.topLevelItem(1).text(0)
assert 'Not included' in w.operations.topLevelItem(1).child(0).text(0)
w.inputs.setCurrentItem(w.inputs.topLevelItem(1))
labels = {w.properties.item(i, 0).text() for i in range(w.properties.rowCount())}
assert 'Original dimensions' in labels and 'Output dimensions' not in labels and 'Final format' not in labels
assert 'Compressed size' not in labels and w.files == files
w.reject()
for p, state in before.items(): assert (p.read_bytes(), p.stat().st_mtime_ns) == state
assert not (base/'Web').exists()
''')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_run_confirmation_displayed_dimensions_collisions_and_real_publication(self):
        self.run_gui('''
import subprocess
from pathlib import Path
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins, config_path
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
base = config_path().parent.parent; source = base/'source.jpg'; occupied = base/'source_1.jpg'
subprocess.run(['magick', '-size', '40x20', 'xc:red', str(source)], check=True)
subprocess.run(['exiftool', '-overwrite_original', '-Orientation#=6', str(source)], check=True, capture_output=True)
original = source.read_bytes(); mtime = source.stat().st_mtime_ns; occupied.write_bytes(b'occupied')
r = builtins()[0]; r['steps'] = [{'op': 'file.rename_output', 'pattern': '{stem}'}]; r['destination'] = {'mode': 'beside'}
w = RunRecipeDialog(r, [str(source)]); assert not w.run_button.isEnabled(); settle(w)
assert w.run_button.isEnabled() and w.run_button.text() == 'Run Recipe on 1 File'
values = {w.properties.item(i, 0).text(): w.properties.item(i, 1).text() for i in range(w.properties.rowCount())}
assert values['Original dimensions'].startswith('20 × 40') and values['Output dimensions'].startswith('20 × 40')
assert values['File modified'] == 'When exported' and 'Compressed size' not in values
assert 'plans to save' in values['Publication'] and 'source_2.jpg' in values['Publication']
assert not (base/'source_2.jpg').exists()
w.start_execution(); worker = w.worker; w.start_execution(); assert w.worker is worker
settle(w)
assert len(w.results) == 1 and w.results[0]['ok']
assert (base/'source_2.jpg').read_bytes() == original
assert occupied.read_bytes() == b'occupied' and source.read_bytes() == original and source.stat().st_mtime_ns == mtime
w.close()
''')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_ask_destination_and_inherited_confirmation_snapshot(self):
        self.run_gui('''
import os
import subprocess
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer, QEventLoop
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins, config_path
from kim_recipe_image import SETTING_KEYS, selected_metadata
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
''' + WAIT + '''
for key in SETTING_KEYS.values(): os.environ.pop(key, None)
base = config_path().parent.parent; settings = config_path().with_name('settings.conf'); settings.parent.mkdir(parents=True)
settings.write_text('KIM_COPYRIGHT_CREATOR=Confirmed Artist\\n')
source = base/'source.jpg'; output = base/'output'; output.mkdir()
subprocess.run(['magick', '-size', '40x20', 'xc:blue', str(source)], check=True)
subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2020:01:02 03:04:05', '-GPSLatitude=20', str(source)], check=True, capture_output=True)
original = source.read_bytes(); mtime = source.stat().st_mtime_ns
r = builtins()[0]; r['steps'][5]['enabled'] = True; r['steps'][6].update(enabled=True, value='Copyright {YEAR} Custom')
r['destination'] = {'mode': 'directory', 'ask': True}
w = RunRecipeDialog(r, [str(source)]); settle(w)
assert not w.run_button.isEnabled() and 'Choose an output directory' in w.diagnostics.toPlainText()
creator = w.operations.topLevelItem(5).child(0).text(0)
assert 'Confirmed Artist' in creator and 'inherited from Settings' in creator
assert 'recipe override' in w.operations.topLevelItem(6).child(0).text(0)
values = {w.properties.item(i, 0).text(): w.properties.item(i, 1).text() for i in range(w.properties.rowCount())}
# The unresolved directory is an error; no final property is presented as reliable yet.
assert values['Output plan'].startswith('Unavailable')
settings.write_text('KIM_COPYRIGHT_CREATOR=Later Artist\\n')
with patch('kim_recipe_run.QFileDialog.getExistingDirectory', return_value=str(output)):
    w.select_destination()
settle(w); assert w.run_button.isEnabled()
values = {w.properties.item(i, 0).text(): w.properties.item(i, 1).text() for i in range(w.properties.rowCount())}
assert values['Creator / Artist (EXIF)'] == '"Confirmed Artist"'
assert values['Usage Rights (XMP-xmpRights)'] == 'Removed'
assert w.chosen == str(output) and r['destination'] == {'mode': 'directory', 'ask': True}
w.start_execution(); settle(w)
assert w.results[0]['ok'], w.results
actual = selected_metadata(Path(w.results[0]['output']), ('EXIF:Artist', 'EXIF:Copyright', 'EXIF:DateTimeOriginal', 'GPS:GPSLatitude'))
assert actual == {'EXIF:Artist': 'Confirmed Artist', 'EXIF:Copyright': 'Copyright 2020 Custom', 'EXIF:DateTimeOriginal': None, 'GPS:GPSLatitude': None}, actual
assert source.read_bytes() == original and source.stat().st_mtime_ns == mtime
w.close()
''')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_invalid_order_clears_predictions_but_keeps_valid_source_info(self):
        self.run_gui('''
import subprocess,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from kim_recipe_core import config_path
from kim_recipe_dialog import RecipeWidget
app = QApplication([])
source = config_path().parent.parent/'oriented.jpg'
subprocess.run(['magick', '-size', '40x20', 'xc:red', str(source)], check=True)
subprocess.run(['exiftool', '-overwrite_original', '-Orientation#=6', str(source)], check=True, capture_output=True)
w = RecipeWidget(files=[str(source)]); w.duplicate()
def settle_editor():
    deadline=time.monotonic()+10
    while w.preview_worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.005)
    assert w.preview_worker is None, 'Editor preview did not finish'
settle_editor()
def values(): return {w.table.item(i, 0).text(): w.table.item(i, 1).text() for i in range(w.table.rowCount())}
assert values()['Original dimensions'].startswith('20 × 40') and values()['Output dimensions'].startswith('20 × 40')
assert 'Compressed size' not in values() and values()['GPS'].startswith('Removed')
gps_row = next(i for i in range(w.table.rowCount()) if w.table.item(i, 0).text() == 'GPS')
assert w.table.item(gps_row, 1).font().italic()
w.steps.setCurrentRow(3); w.move(1); w.update_preview()
settle_editor()
assert values()['Original dimensions'].startswith('20 × 40')
assert 'Final format' not in values() and 'Output filename' not in values()
assert 'Move Convert Format above Remove All Metadata' in values()['Validation problem']
w.close()
''')

    def test_large_preflight_remains_responsive_and_cancels_before_execution(self):
        self.run_gui('''
import threading
from unittest.mock import patch
from PySide6.QtCore import QEventLoop, QTimer, QThread
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins, PreviewRow
from kim_recipe_run import RunRecipeDialog
app = QApplication([])
started = threading.Event(); release = threading.Event(); calls = []
def preview(recipe, files, chosen, start_index):
    assert QThread.currentThread() != app.thread()
    calls.append(files[0]); started.set(); assert release.wait(10)
    return [PreviewRow(files[0])]
with patch('kim_recipe_run.preview', side_effect=preview), patch('kim_recipe_run.execute') as execute:
    w = RunRecipeDialog(builtins()[0], ['file-' + str(i) for i in range(50)])
    loop = QEventLoop(); timer = QTimer(); timer.setInterval(10); ticks = []
    def tick():
        ticks.append(1)
        if started.is_set() and len(ticks) >= 3:
            w.reject(); release.set()
        if w.preflight_worker is None: loop.quit()
    timer.timeout.connect(tick); timer.start()
    deadline = QTimer(); deadline.setSingleShot(True); deadline.timeout.connect(lambda: (release.set(), loop.quit())); deadline.start(15000)
    loop.exec(); timer.stop(); deadline.stop()
    assert len(ticks) >= 3 and len(calls) == 1 and not execute.called
    assert w.preflight_worker is None and not w.run_button.isEnabled()
    assert len(w.files) == 50
    w.close()
''')


if __name__ == '__main__': unittest.main()
