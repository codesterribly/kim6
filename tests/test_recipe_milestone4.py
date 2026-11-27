"""Comprehensive Milestone 4 tests: Permanent Recipes, Portable Exchange, Remembered Answers & Progressive Disclosure."""
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'bin'))
sys.path.insert(0, str(ROOT / 'tests'))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import kim_recipe_core as core
import kim_recipe_menu as menu
import kim_recipe_params as params
from kim_recipe_author_ui import ParameterEditorDialog
from kim_recipe_dialog import make_editor_dialog
from kim_recipe_param_ui import ParameterFormWidget, PreviewSettingsDialog
from kim_recipe_run import RunRecipeDialog
from metadata_integrity import sha256_noatime

APP = QApplication.instance() or QApplication([])


def pump(rounds=8):
    for _ in range(rounds):
        APP.processEvents()


def settle_editor(widget, timeout_ms=8000):
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        pump(4)
        if widget.preview_worker is None and not widget.timer.isActive():
            pump(4)
            return
        time.sleep(0.01)
    raise AssertionError('Editor preview worker did not settle in time')


def close_editor(dlg):
    """Deterministic teardown preventing unattended protect_unsaved() dialogs."""
    w = dlg.widget
    w.timer.stop()
    if w.preview_worker is not None:
        w.preview_worker.requestInterruption()
        w.preview_worker.wait(5000)
        w.preview_worker = None
    if w.recipe is not None:
        w.baseline = copy.deepcopy(w.recipe)
        w.draft_ids.discard(w.recipe.get('id'))
    dlg.close()
    dlg.deleteLater()
    pump(4)


def settle_runner(dialog, timeout_ms=10000):
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        pump(4)
        if (
            dialog.preflight_worker is None
            and dialog.worker is None
            and dialog.add_worker is None
            and dialog.filters_worker is None
        ):
            pump(4)
            return
        time.sleep(0.01)
    raise AssertionError('Runner workers did not settle in time')


def make_test_jpeg(path: Path, *, width=320, height=200):
    subprocess.run(
        ['magick', '-size', f'{width}x{height}', 'xc:steelblue', str(path)],
        check=True,
        capture_output=True,
    )


def make_param_recipe(
    recipe_id='user-m4-export',
    name='Client Delivery',
    *,
    dolphin_shortcut=False,
    folder=None,
    req_advanced=False,
):
    recipe = {
        'schema': core.AUTHORED_SCHEMA,
        'id': recipe_id,
        'name': name,
        'description': 'Deliver resized client images with optional advanced quality.',
        'dolphin_shortcut': dolphin_shortcut,
        'media': 'image',
        'parameters': [
            {
                'id': 'client_name',
                'label': 'Client name',
                'type': 'text',
                'required': True,
                'remember': True,
                'advanced': False,
                'help': 'Used in the subfolder and filename prefix.',
            },
            {
                'id': 'resize_on',
                'label': 'Resize images',
                'type': 'boolean',
                'default': True,
                'remember': True,
                'advanced': False,
            },
            {
                'id': 'max_edge',
                'label': 'Longest side',
                'type': 'integer',
                'minimum': 100,
                'maximum': 4000,
                'default': 1200,
                'remember': False,
                'advanced': False,
                'visible_when': {'param': 'resize_on', 'equals': True},
            },
            {
                'id': 'jpeg_quality',
                'label': 'JPEG quality',
                'type': 'integer',
                'minimum': 60,
                'maximum': 100,
                'default': 92,
                'remember': True,
                'advanced': True,
                'help': 'Adjust compression quality.',
            },
        ],
        'steps': [
            {'op': 'image.auto_orient'},
            {
                'op': 'image.resize_long_edge',
                'pixels': 1200,
                'upscale': False,
                'bindings': {'pixels': 'max_edge'},
                'enabled_when': {'param': 'resize_on', 'equals': True},
            },
            {
                'op': 'image.convert',
                'format': 'jpeg',
                'quality': 92,
                'bindings': {'quality': 'jpeg_quality'},
            },
            {'op': 'file.rename_output', 'pattern': '{param:client_name}_{filename}'},
        ],
        'destination': {'mode': 'subfolder', 'folder': '{param:client_name}'},
    }
    if req_advanced:
        recipe['parameters'].append({
            'id': 'archive_tag',
            'label': 'Archive code',
            'type': 'text',
            'required': True,
            'remember': False,
            'advanced': True,
        })
        recipe['steps'][-1]['pattern'] = '{param:client_name}_{param:archive_tag}_{filename}'
    if folder is not None:
        recipe['folder'] = folder
    return recipe


def make_fixed_recipe(recipe_id='user-m4-fixed', name='Quick JPEG', *, dolphin_shortcut=False):
    return {
        'schema': core.AUTHORED_SCHEMA,
        'id': recipe_id,
        'name': name,
        'description': 'Fixed JPEG export.',
        'dolphin_shortcut': dolphin_shortcut,
        'media': 'image',
        'steps': [
            {'op': 'image.convert', 'format': 'jpeg', 'quality': 90},
            {'op': 'file.rename_output', 'pattern': '{filename}_quick'},
        ],
        'destination': {'mode': 'beside'},
    }


class Milestone4SchemaAndExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config_home = self.base / 'config'
        self.data_home = self.base / 'data'
        self.config_home.mkdir()
        self.data_home.mkdir()
        env = patch.dict(
            os.environ,
            {
                'XDG_CONFIG_HOME': str(self.config_home),
                'XDG_DATA_HOME': str(self.data_home),
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def test_01_schema_contracts_and_historical_rejection_non_destructive(self):
        self.assertEqual(core.CONCRETE_SCHEMA, 3)
        self.assertEqual(core.AUTHORED_SCHEMA, 4)
        self.assertEqual(core.LIBRARY_SCHEMA, 5)
        self.assertEqual(core.REMEMBERED_SCHEMA, 1)

        # Historical schema-4 library rejected cleanly without modifying disk file.
        lib_path = self.config_home / 'kimng' / 'recipes.json'
        lib_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_bytes = json.dumps({'schema': 4, 'recipes': [], 'folders': []}).encode('utf-8')
        lib_path.write_bytes(legacy_bytes)
        with self.assertRaises(core.RecipeError):
            core.read_library(lib_path)
        self.assertEqual(lib_path.read_bytes(), legacy_bytes)

        # Historical schema-3 portable file rejected cleanly.
        legacy_portable = self.base / 'old.kimrecipe.json'
        legacy_portable.write_text(json.dumps({
            **make_fixed_recipe(),
            'schema': 3,
        }), encoding='utf-8')
        with self.assertRaises(core.RecipeError):
            core.read_portable_recipe(legacy_portable)

        # Concrete schema 3 rejected by validate_authored.
        with self.assertRaises(core.RecipeError):
            params.validate_authored({**make_fixed_recipe(), 'schema': 3})

        # Non-boolean 'advanced' rejected strictly.
        for bad in (1, 0, 'true', None, []):
            bad_r = make_param_recipe()
            bad_r['parameters'][0]['advanced'] = bad
            with self.assertRaisesRegex(core.RecipeError, 'advanced'):
                params.validate_authored(bad_r)

        # Resolved concrete snapshot has schema 3 and no authored metadata.
        concrete = params.resolve_recipe(
            make_param_recipe(),
            {'client_name': 'Acme', 'resize_on': True, 'max_edge': 800, 'jpeg_quality': 88},
        )
        self.assertEqual(concrete['schema'], core.CONCRETE_SCHEMA)
        self.assertNotIn('parameters', concrete)
        core.validate(concrete)

    def test_02_portable_and_bundle_exchange_preserve_authored_and_exclude_local_state(self):
        folder_root = {'id': 'folder-work', 'name': 'Work', 'parent_id': None}
        folder_sub = {'id': 'folder-clients', 'name': 'Clients', 'parent_id': 'folder-work'}
        param_r = make_param_recipe(
            recipe_id='user-orig-param',
            name='Client Delivery',
            dolphin_shortcut=True,
            folder='folder-clients',
        )
        fixed_r = make_fixed_recipe(
            recipe_id='user-orig-fixed',
            name='Quick JPEG',
            dolphin_shortcut=True,
        )

        # Save remembered values locally to verify they never leak into exports.
        core.save_remembered_values('user-orig-param', {'client_name': 'SecretClient', 'jpeg_quality': 80})

        # Individual portable export/import.
        portable_path = self.base / 'client_delivery.kimrecipe.json'
        core.write_portable_recipe(param_r, portable_path)
        raw_portable = json.loads(portable_path.read_text(encoding='utf-8'))
        self.assertEqual(raw_portable['schema'], core.AUTHORED_SCHEMA)
        self.assertNotIn('dolphin_shortcut', raw_portable)
        self.assertNotIn('folder', raw_portable)
        self.assertNotIn('SecretClient', portable_path.read_text(encoding='utf-8'))

        imported = core.read_portable_recipe(portable_path)
        self.assertEqual(imported['schema'], core.AUTHORED_SCHEMA)
        self.assertEqual([p['id'] for p in imported['parameters']], [p['id'] for p in param_r['parameters']])
        self.assertTrue(imported['parameters'][3]['advanced'])
        self.assertTrue(imported['parameters'][3]['remember'])

        # Library bundle export & merge into a non-empty library (verifies Recipe ID remap NEVER remaps param IDs).
        bundle_path = self.base / 'library.kimrecipes.json'
        src_lib = core.RecipeLibrary([param_r, fixed_r], [folder_root, folder_sub])
        core.write_recipe_bundle(src_lib, bundle_path)
        raw_bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
        self.assertEqual(raw_bundle['kind'], 'kimng-recipe-bundle')
        self.assertEqual(raw_bundle['schema'], core.LIBRARY_SCHEMA)
        self.assertNotIn('SecretClient', bundle_path.read_text(encoding='utf-8'))

        read_bundle = core.read_recipe_bundle(bundle_path)
        existing = core.RecipeLibrary([copy.deepcopy(param_r)], [copy.deepcopy(folder_root), copy.deepcopy(folder_sub)])
        merged, imported_recipes = core.merge_recipe_bundle(existing, read_bundle)
        self.assertEqual(len(imported_recipes), 2)
        self.assertEqual(len(merged.recipes), 3)
        merged_param = [r for r in merged.recipes if r['name'].startswith('Client Delivery') and r['id'] != 'user-orig-param'][0]
        # Parameter IDs, bindings, conditions, and template refs must remain completely intact!
        self.assertEqual(
            [p['id'] for p in merged_param['parameters']],
            ['client_name', 'resize_on', 'max_edge', 'jpeg_quality'],
        )
        self.assertTrue(merged_param['parameters'][3]['advanced'])
        self.assertTrue(merged_param['parameters'][3]['remember'])
        self.assertFalse(merged_param['dolphin_shortcut'])
        params.validate_authored(merged_param)

    def test_03_remembered_storage_security_permissions_and_validation(self):
        rem_path = core.remembered_path()
        core.save_remembered_values('user-r1', {'client_name': 'Alpha', 'jpeg_quality': 85})
        self.assertTrue(rem_path.exists())
        self.assertEqual(rem_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            core.load_remembered_values('user-r1'),
            {'client_name': 'Alpha', 'jpeg_quality': 85},
        )

        # Symlink target must be rejected safely.
        target = self.base / 'target_rem.json'
        target.write_text('untouched', encoding='utf-8')
        rem_path.unlink()
        rem_path.symlink_to(target)
        with self.assertRaises(core.RecipeError):
            core.save_remembered_values('user-r1', {'client_name': 'Beta'})
        self.assertEqual(target.read_text(encoding='utf-8'), 'untouched')
        rem_path.unlink()

        # Precedence & invalid/disabled/inactive remembered value discarding.
        authored = make_param_recipe()
        valid = params.initial_remembered_values(
            authored,
            {
                'client_name': 'ValidCo',
                'resize_on': False,
                'max_edge': 900,        # remember=False AND inactive -> discarded
                'jpeg_quality': 999,    # out of bounds -> discarded
                'removed_param': 'foo', # undeclared -> discarded
            },
        )
        self.assertEqual(valid, {'client_name': 'ValidCo', 'resize_on': False})

        # Clear specific keys vs whole Recipe.
        core.save_remembered_values('user-r1', {'client_name': 'Alpha', 'jpeg_quality': 85})
        core.clear_remembered_values('user-r1', ['jpeg_quality'])
        self.assertEqual(core.load_remembered_values('user-r1'), {'client_name': 'Alpha'})
        core.clear_remembered_values('user-r1')
        self.assertEqual(core.load_remembered_values('user-r1'), {})

    @unittest.skipUnless(shutil.which('magick'), 'ImageMagick required')
    def test_04_cli_noninteractive_fixed_ok_and_parameterized_rejected(self):
        img = self.base / 'cli_sample.jpg'
        make_test_jpeg(img)
        before_sha = sha256_noatime(img)

        fixed = make_fixed_recipe('user-cli-fixed', 'CLI Fixed')
        param = make_param_recipe('user-cli-param', 'CLI Param')
        core.save_library(core.RecipeLibrary([fixed, param], []))

        # Parameterized Recipe rejected with clear diagnostic and non-zero exit.
        res_param = subprocess.run(
            [sys.executable, str(ROOT / 'src/bin/kim_recipe_core.py'), '--recipe', 'user-cli-param', str(img)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res_param.returncode, 0)
        self.assertIn('asks for settings', (res_param.stderr + res_param.stdout).casefold())
        self.assertEqual(sha256_noatime(img), before_sha)

        # Fixed schema-4 Recipe compiles and executes cleanly.
        res_fixed = subprocess.run(
            [sys.executable, str(ROOT / 'src/bin/kim_recipe_core.py'), '--recipe', 'user-cli-fixed', str(img)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_fixed.returncode, 0, res_fixed.stderr)
        self.assertTrue((self.base / 'cli_sample_quick.jpg').exists())
        self.assertEqual(sha256_noatime(img), before_sha)


class Milestone4ProgressiveDisclosureAndWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config_home = self.base / 'config'
        self.data_home = self.base / 'data'
        self.config_home.mkdir()
        self.data_home.mkdir()
        env = patch.dict(
            os.environ,
            {
                'XDG_CONFIG_HOME': str(self.config_home),
                'XDG_DATA_HOME': str(self.data_home),
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def test_05_progressive_disclosure_shared_form_and_preview_settings(self):
        # 1. Optional/defaulted advanced question starts collapsed; expanding/collapsing never mutates values.
        recipe = make_param_recipe()
        form = ParameterFormWidget()
        self.addCleanup(form.deleteLater)
        form.set_recipe(recipe)
        self.assertTrue(form.has_active_advanced())
        self.assertFalse(form.is_advanced_expanded())

        form.set_advanced_expanded(True)
        self.assertTrue(form.is_advanced_expanded())
        form.field_widget('jpeg_quality').setValue(78)
        form.set_advanced_expanded(False)
        self.assertFalse(form.is_advanced_expanded())
        self.assertEqual(form.active_values()['jpeg_quality'], 78)

        # User-expanded state is preserved across updates.
        form.set_advanced_expanded(True)
        form.field_widget('client_name').setText('Nordic')
        self.assertTrue(form.is_advanced_expanded())

        # 2. Unanswered required advanced question auto-expands without premature red error.
        req_adv_recipe = make_param_recipe(req_advanced=True)
        form2 = ParameterFormWidget()
        self.addCleanup(form2.deleteLater)
        form2.set_recipe(req_adv_recipe)
        self.assertTrue(form2.is_advanced_expanded())
        self.assertEqual(form2.field_error('archive_tag'), '')

        # 3. Recipe with no active advanced questions hides the Advanced settings section.
        no_adv = make_param_recipe()
        no_adv['parameters'][3]['advanced'] = False
        form3 = ParameterFormWidget()
        self.addCleanup(form3.deleteLater)
        form3.set_recipe(no_adv)
        self.assertFalse(form3.has_active_advanced())
        self.assertTrue(form3._advanced_toggle.isHidden())

        # 4. Conditional advanced question hides section when condition becomes false.
        cond_adv = make_param_recipe()
        cond_adv['parameters'][3]['visible_when'] = {'param': 'resize_on', 'equals': True}
        cond_adv['steps'][2]['enabled_when'] = {'param': 'resize_on', 'equals': True}
        form4 = ParameterFormWidget()
        self.addCleanup(form4.deleteLater)
        form4.set_recipe(cond_adv)
        self.assertTrue(form4.has_active_advanced())
        form4.field_widget('resize_on').setChecked(False)
        self.assertFalse(form4.has_active_advanced())
        self.assertTrue(form4._advanced_toggle.isHidden())

        # 5. Editor PreviewSettingsDialog reuses the exact same ParameterFormWidget grouping!
        prev_dlg = PreviewSettingsDialog(recipe)
        self.addCleanup(prev_dlg.deleteLater)
        self.assertTrue(prev_dlg.form.has_active_advanced())
        self.assertFalse(prev_dlg.form.is_advanced_expanded())

        # 6. ParameterEditorDialog round-trips 'advanced' checkbox cleanly.
        ed = ParameterEditorDialog(
            param=recipe['parameters'][3],
            existing_ids=['client_name', 'resize_on', 'max_edge', 'jpeg_quality'],
            earlier_params=recipe['parameters'][:3],
            locked_type=True,
        )
        self.addCleanup(ed.deleteLater)
        self.assertTrue(ed.advanced_display_check.isChecked())
        ed.advanced_display_check.setChecked(False)
        built = ed.build_parameter()
        self.assertNotIn('advanced', built)
        ed.advanced_display_check.setChecked(True)
        built2 = ed.build_parameter()
        self.assertIs(built2['advanced'], True)

    @unittest.skipUnless(shutil.which('magick'), 'ImageMagick required')
    def test_06_permanent_save_reopen_duplicate_delete_and_dolphin_shortcut(self):
        img = self.base / 'alpine.jpg'
        make_test_jpeg(img)

        # Save a parameterized Recipe with unanswered required parameter and Dolphin shortcut enabled.
        dlg = make_editor_dialog(files=[str(img)])
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        w.append_recipe(
            make_param_recipe(
                recipe_id='user-m4-alpine',
                name='Alpine Export',
                dolphin_shortcut=True,
            )
        )
        settle_editor(w)
        self.assertTrue(w.management_buttons['Save'].isEnabled())
        self.assertTrue(w.shortcut_checkbox.isEnabled())
        with patch.object(w, 'error'):
            self.assertTrue(w.save())
        saved_id = w.saved_recipe_id
        self.assertEqual(saved_id, 'user-m4-alpine')

        # Verify Dolphin service menu rendering includes the parameterized Recipe shortcut!
        desktop_text = menu.render(core.load_library(), ROOT / 'src' / 'bin' / 'kim_all')
        self.assertIn(saved_id, desktop_text)
        self.assertIn('Alpine\\sExport', desktop_text)
        self.assertIn('--run-id ' + saved_id + ' -- %F', desktop_text)

        # Reopen fresh Editor and verify full authored fidelity + discovery tooltip + shortcut star!
        dlg2 = make_editor_dialog(files=[str(img)])
        self.addCleanup(close_editor, dlg2)
        w2 = dlg2.widget
        settle_editor(w2)
        tree_item = w2.recipe_tree_items[saved_id]
        self.assertTrue(tree_item.text(0).startswith('★ Alpine Export'))
        self.assertIn('Asks for settings when running.', tree_item.toolTip(0))

        # Seed remembered answer, duplicate Recipe, verify independent ID & NO remembered copy.
        core.save_remembered_values(saved_id, {'client_name': 'Matterhorn', 'jpeg_quality': 82})
        w2.select(len(w2.shipped) + next(i for i, r in enumerate(w2.users) if r['id'] == saved_id))
        w2.duplicate()
        dup_id = w2.recipe['id']
        self.assertNotEqual(dup_id, saved_id)
        self.assertEqual(core.load_remembered_values(dup_id), {})
        with patch.object(w2, 'error'):
            self.assertTrue(w2.save())

        # Disabling remember on jpeg_quality and saving prunes stale remembered entry.
        idx_orig = len(w2.shipped) + next(i for i, r in enumerate(w2.users) if r['id'] == saved_id)
        w2.select(idx_orig)
        w2.recipe['parameters'][3]['remember'] = False
        w2.update_modified()
        with patch.object(w2, 'error'):
            self.assertTrue(w2.save())
        self.assertEqual(core.load_remembered_values(saved_id), {'client_name': 'Matterhorn'})

        # Deleting the Recipe cleans up its remembered answers.
        with patch.object(w2, 'error'), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            w2.remove()
        self.assertEqual(core.load_remembered_values(saved_id), {})

    @unittest.skipUnless(shutil.which('magick'), 'ImageMagick required')
    def test_07_remembered_lifecycle_runner_editor_roundtrip_and_collision_fail_closed(self):
        img = self.base / 'summit.jpg'
        make_test_jpeg(img, width=400, height=240)
        before_sha = sha256_noatime(img)

        saved = make_param_recipe(recipe_id='user-m4-live', name='Summit Delivery', dolphin_shortcut=True)
        core.save_library(core.RecipeLibrary([saved], []))

        # 1. Open Runner -> verify discovery tooltip, Edit Recipe enabled, Settings page, Advanced collapsed.
        runner = RunRecipeDialog(saved, [str(img)], [])
        self.addCleanup(runner.deleteLater)
        settle_runner(runner)
        self.assertEqual(runner.runner_phase, 'settings')
        self.assertTrue(runner.edit_button.isEnabled())
        self.assertFalse(runner.settings_page.form.is_advanced_expanded())
        self.assertTrue(runner.settings_page.clear_remembered_button.isHidden())
        idx = runner.selector.findData('user-m4-live')
        self.assertIn('Asks for settings when running.', runner.selector.itemData(idx, Qt.ToolTipRole))

        # 2. Fill values (including advanced), enter review, run to completion -> remembered persisted!
        runner.settings_page.form.field_widget('client_name').setText('Everest')
        runner.settings_page.form.set_advanced_expanded(True)
        runner.settings_page.form.field_widget('jpeg_quality').setValue(84)
        runner.enter_review_from_settings()
        settle_runner(runner)
        self.assertEqual(runner.runner_phase, 'review')
        self.assertTrue(runner.run_button.isEnabled())
        runner.start_execution()
        settle_runner(runner)
        self.assertTrue(runner.execution_succeeded, runner.results)
        self.assertTrue((self.base / 'Everest' / 'Everest_summit.jpg').exists())
        self.assertEqual(sha256_noatime(img), before_sha)

        # Remembered values saved for remember=True only (NOT max_edge which has remember=False!).
        rem = core.load_remembered_values('user-m4-live')
        self.assertEqual(rem, {'client_name': 'Everest', 'resize_on': True, 'jpeg_quality': 84})

        # 3. Reopen Runner -> initialized from remembered values; Reset does NOT touch disk; Clear does!
        runner2 = RunRecipeDialog(saved, [str(img)], [])
        self.addCleanup(runner2.deleteLater)
        settle_runner(runner2)
        self.assertEqual(runner2.settings_page.form.field_widget('client_name').text(), 'Everest')
        self.assertEqual(runner2.settings_page.form.field_widget('jpeg_quality').value(), 84)
        self.assertFalse(runner2.settings_page.form.is_advanced_expanded())
        self.assertFalse(runner2.settings_page.clear_remembered_button.isHidden())

        # Reset to defaults leaves persistent remembered intact.
        runner2.settings_page.form.reset_to_defaults()
        self.assertEqual(runner2.settings_page.form.field_widget('client_name').text(), '')
        self.assertEqual(runner2.settings_page.form.field_widget('jpeg_quality').value(), 92)
        self.assertEqual(core.load_remembered_values('user-m4-live')['client_name'], 'Everest')

        # 4. Failed run (late destination collision) must NOT overwrite remembered values!
        runner2.settings_page.form.field_widget('client_name').setText('K2')
        runner2.settings_page.form.field_widget('jpeg_quality').setValue(71)
        runner2.enter_review_from_settings()
        settle_runner(runner2)
        # Create late collision AFTER preflight approval!
        collision_dir = self.base / 'K2'
        collision_dir.mkdir(exist_ok=True)
        collision_file = collision_dir / 'K2_summit.jpg'
        collision_file.write_bytes(b'existing-protected')
        runner2.start_execution()
        settle_runner(runner2)
        self.assertFalse(runner2.execution_succeeded)
        self.assertEqual(collision_file.read_bytes(), b'existing-protected')
        # Remembered values must still be 'Everest' / 84, NOT 'K2' / 71!
        self.assertEqual(core.load_remembered_values('user-m4-live')['client_name'], 'Everest')
        self.assertEqual(core.load_remembered_values('user-m4-live')['jpeg_quality'], 84)

        # 5. Clear remembered clears disk and hides button.
        runner2.open_settings_page()
        runner2._clear_remembered_for_current_recipe()
        self.assertEqual(core.load_remembered_values('user-m4-live'), {})
        self.assertTrue(runner2.settings_page.clear_remembered_button.isHidden())

        # 6. Runner-to-Editor round-trip: modifying saved Recipe invalidates approval and filters stale session values.
        runner2.settings_page.form.field_widget('client_name').setText('Denali')
        runner2.enter_review_from_settings()
        settle_runner(runner2)
        self.assertEqual(runner2.runner_phase, 'review')

        modified = copy.deepcopy(saved)
        modified['parameters'][0]['label'] = 'Expedition name'
        core.save_library(core.RecipeLibrary([modified], []))

        class _FakeWidget:
            saved_recipe_id = 'user-m4-live'

        class _FakeEditorDialog:
            widget = _FakeWidget()
            run_request = None
            def deleteLater(self):
                pass

        runner2.editor_dialog = _FakeEditorDialog()
        runner2._editor_previous = (copy.deepcopy(saved), copy.deepcopy(saved))
        runner2.editor_finished(QDialog.Rejected)
        settle_runner(runner2)
        # Approval invalidated, returned to Settings with updated label, valid session value preserved!
        self.assertEqual(runner2.runner_phase, 'settings')
        self.assertIsNone(runner2.approved_plan)
        self.assertEqual(runner2.files, [str(img)])
        self.assertEqual(runner2.settings_page.form.field_widget('client_name').text(), 'Denali')


if __name__ == '__main__':
    unittest.main()
