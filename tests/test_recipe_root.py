"""Root rendering and disposable installation synchronization."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_recipes as base
import kim_recipe_core as core
import kim_recipe_menu as menu


class RootTests(unittest.TestCase):
    def test_virtual_assignment_and_reserved_categories(self):
        r = base.recipe(); library = core.RecipeLibrary([r])
        library.move_recipe(r['id'], core.ROOT_FOLDER)
        core.validate_library(dict(schema=1, recipes=library.recipes, folders=[]))
        self.assertEqual(core.library_groups(library)[1][2], [r])
        for name in ['ROOT', 'Built-In', 'unfiled']:
            with self.assertRaises(core.RecipeError): library.create_folder(name)
        with self.assertRaises(core.RecipeError): library.delete_folder(core.ROOT_FOLDER)
        library.move_recipe(r['id']); self.assertNotIn('folder', r)
        self.assertNotIn('folder', core.builtins()[0])

    def test_render_order_duplicates_escaping_confirmation(self):
        a = base.recipe(); a.update(id='z', name='Same;= % 雪 \\"', folder=core.ROOT_FOLDER)
        b = dict(a, id='a')
        result = menu.render(core.RecipeLibrary([a, b]), Path('/tmp/space $`"%/kim_all'))
        self.assertIn('Actions=KIMRoot-a;KIMRoot-z;_SEPARATOR_;KIMRecipe0Run;KIMRecipe1Editor;', result)
        self.assertIn('[Desktop Action _SEPARATOR_]\nName=Separator', result)
        self.assertIn('--run-id a -- %F', result)
        self.assertNotIn('--recipe ', result)
        self.assertIn('[a]', result); self.assertIn('[z]', result)
        self.assertNotIn('TopLevel', result)
        a['name'] = 'bad\nExec=evil'
        with self.assertRaises(core.RecipeError): menu.render(core.RecipeLibrary([a]), Path('/bin/kim_all'))
        empty = menu.render(core.RecipeLibrary(), Path('/bin/kim_all'))
        self.assertIn('Actions=KIMRecipe0Run;KIMRecipe1Editor;', empty)
        self.assertNotIn('_SEPARATOR_', empty)

    def test_quick_launcher_preserves_files_and_requires_confirmation(self):
        import sys
        import types
        from unittest.mock import Mock
        launcher = types.ModuleType('kim_recipe_run')
        launcher.launch_run = Mock(return_value=0)
        files = ['/tmp/a b.jpg', '/tmp/quote";雪%.png', '--leading.jpg']
        with patch.dict(sys.modules, {'kim_recipe_run': launcher}), patch.object(sys, 'argv', ['recipe', '--run-id', 'stable-id', '--', *files]), patch.object(core, 'execute') as execute:
            self.assertEqual(core.main(), 0)
            launcher.launch_run.assert_called_once_with('stable-id', files)
            execute.assert_not_called()

    def test_atomic_repeat_foreign_symlink_and_saved_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); target = root/'kim_recipes.desktop'; dispatcher = root/'kim6/bin/kim_all'
            library = core.RecipeLibrary(); target.write_text(menu.render(library, dispatcher)); target.chmod(0o755)
            with patch.object(menu, 'installed_paths', return_value=(target, dispatcher)), patch.object(menu, 'load_library', return_value=library), patch.object(menu.shutil, 'which', return_value=None):
                self.assertFalse(menu.sync_menu())
                r = base.recipe(); r['folder'] = core.ROOT_FOLDER; library.recipes.append(r)
                self.assertTrue(menu.sync_menu()); self.assertEqual(target.stat().st_mode & 0o777, 0o755)
                before = target.read_bytes()
                r['name'] = 'Renamed'
                with patch.object(menu.os, 'replace', side_effect=PermissionError('read only')):
                    with self.assertRaises(PermissionError): menu.sync_menu()
                self.assertEqual(target.read_bytes(), before)
                self.assertTrue(menu.sync_menu())
                r.pop('folder'); self.assertTrue(menu.sync_menu())
                self.assertFalse(menu.sync_menu())
                target.write_text('foreign')
                with self.assertRaises(core.RecipeError): menu.sync_menu()
                target.unlink(); target.symlink_to(root/'other')
                with self.assertRaises(core.RecipeError): menu.sync_menu()

    def test_save_warning_preserves_library_and_nonroot_does_not_sync(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}), patch.object(menu, 'sync_menu', side_effect=PermissionError('read only')) as sync:
            r = base.recipe(); core.save_library(core.RecipeLibrary([r])); sync.assert_not_called()
            r['folder'] = core.ROOT_FOLDER
            self.assertIn('Recipe saved', core.save_library(core.RecipeLibrary([r])))
            self.assertEqual(core.load_users()[0]['folder'], core.ROOT_FOLDER)
            core.save_library(core.RecipeLibrary([r])); self.assertEqual(sync.call_count, 1)

class RootEditorTests(unittest.TestCase):
    run_gui = base.RecipeGuiTests.run_gui

    def test_root_drafts_saved_changes_and_duplicate_identity(self):
        self.run_gui('''
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import ROOT_FOLDER, load_users
app = QApplication([])
w = RecipeWidget(['/tmp/selected photograph 雪.jpg'])
with patch('kim_recipe_menu.sync_menu', return_value=False) as sync:
    w.duplicate()
    original_id = w.recipe['id']
    w.library_folder.setCurrentIndex(w.library_folder.findData(ROOT_FOLDER))
    assert not load_users() and not sync.called
    assert w.save() and sync.call_count == 1
    assert load_users()[0]['folder'] == ROOT_FOLDER
    w.duplicate()
    assert w.recipe['id'] != original_id
    assert len(load_users()) == 1 and sync.call_count == 1
    assert w.save() and sync.call_count == 2
    w.library_folder.setCurrentIndex(w.library_folder.findData(None))
    assert w.save() and sync.call_count == 3
    assert w.files == ['/tmp/selected photograph 雪.jpg']
w.close()
''')


class RootInstallerTests(unittest.TestCase):
    def test_nondefault_prefix_reinstall_and_uninstall_preserves_library(self):
        from test_manual_installation import ManualInstallationTests
        import json
        fixture = ManualInstallationTests('test_installed_menus_use_installed_dispatcher')
        fixture.setUp()
        try:
            config = fixture.base / 'config'
            (config / 'kim6').mkdir(parents=True)
            r = base.recipe(); r['folder'] = core.ROOT_FOLDER
            library = config / 'kim6/recipes.json'
            library.write_text(json.dumps(dict(schema=1, recipes=[r], folders=[])))
            fixture.env['XDG_CONFIG_HOME'] = str(config)
            for _ in range(2):
                fixture.run_installer('install.sh')
                rendered = (fixture.prefix / 'kim_recipes.desktop').read_text()
                self.assertIn('Actions=KIMRoot-test;_SEPARATOR_;KIMRecipe0Run;KIMRecipe1Editor;', rendered)
                self.assertIn('Exec="' + str(fixture.runtime / 'bin/kim_all') + '" recipe --run-id test -- %F', rendered)
            fixture.run_installer('uninstall.sh')
            self.assertTrue(library.exists())
            self.assertFalse((fixture.prefix / 'kim_recipes.desktop').exists())
        finally:
            fixture.doCleanups()
