"""Focused Milestone 3 tests for Recipe Editor parameter authoring and Preview Settings."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'bin'))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))

import kim_recipe_core as core
import kim_recipe_params as params
from metadata_integrity import sha256_noatime

HAS_PYSIDE6 = importlib.util.find_spec('PySide6') is not None
HAS_MEDIA_TOOLS = bool(shutil.which('magick') and shutil.which('exiftool'))

if HAS_PYSIDE6:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox
    from kim_recipe_author_ui import (
        ConditionEditorWidget,
        ParameterEditorDialog,
        StepActivationDialog,
    )
    from kim_recipe_dialog import RecipeWidget, make_editor_dialog
    from kim_recipe_param_ui import ParameterFormWidget, PreviewSettingsDialog
    from kim_recipe_run import RunRecipeDialog, verify_editor_handoff
    from demo_parameterized_runner import DEMO_RECIPE, build_new_draft


def close_editor(dialog):
    """Shut down editor timers/workers cleanly without blocking on modal teardown prompts."""
    w = dialog.widget
    w.timer.stop()
    w.preview_pending = False
    if w.preview_worker is not None:
        w.preview_worker.requestInterruption()
        w.preview_worker.wait(5000)
        QApplication.instance().processEvents()
    if w.recipe is not None:
        w.baseline = copy.deepcopy(w.recipe)
        w.draft_ids.discard(w.recipe['id'])
    dialog.close()
    dialog.deleteLater()
    QApplication.instance().processEvents()


def settle_editor(widget, timeout=15.0):
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while (
        widget.preview_worker is not None
        or widget.timer.isActive()
    ) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(4):
        app.processEvents()
    assert widget.preview_worker is None, 'preview_worker did not finish'


def settle_runner(dialog, timeout=15.0):
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while (
        dialog.preflight_worker is not None
        or dialog.worker is not None
        or dialog.add_worker is not None
        or dialog.filters_worker is not None
        or dialog._addition_queue
    ) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(4):
        app.processEvents()
    assert dialog.preflight_worker is None
    assert dialog.worker is None


def make_test_jpeg(path, *, width=400, height=200, gps=True, artist='Author Artist'):
    subprocess.run(['magick', '-size', f'{width}x{height}', 'xc:#2b5876', str(path)], check=True)
    args = ['exiftool', '-overwrite_original', f'-Artist={artist}']
    if gps:
        args += ['-GPSLatitude=45.5', '-GPSLatitudeRef=N', '-GPSLongitude=122.6', '-GPSLongitudeRef=W']
    args.append(str(path))
    subprocess.run(args, check=True, capture_output=True)


def observe_source(path):
    info = os.lstat(path)
    return (sha256_noatime(path), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class AuthoringHelperTests(unittest.TestCase):
    """Pure-Python authoring helper checks (no Qt required)."""

    def test_01_id_generation_compatibility_and_reordering(self):
        self.assertEqual(params.generate_parameter_id('Client or project name'), 'client_or_project_name')
        self.assertEqual(
            params.generate_parameter_id('Client or project name', {'client_or_project_name'}),
            'client_or_project_name_2',
        )
        self.assertEqual(params.generate_parameter_id('123 Size'), 'p_123_size')

        # Compatibility filtering excludes incompatible types & impossible constraint intersections.
        recipe = {
            'schema': 4,
            'id': 'compat-test',
            'name': 'Compat Test',
            'description': 'Check field compatibility.',
            'media': 'image',
            'parameters': [
                {'id': 'title', 'label': 'Title', 'type': 'text', 'required': True},
                {'id': 'flag', 'label': 'Flag', 'type': 'boolean', 'default': True},
                {'id': 'edge', 'label': 'Edge', 'type': 'integer', 'minimum': 300, 'maximum': 8000, 'default': 1600},
                {'id': 'qual', 'label': 'Quality', 'type': 'integer', 'minimum': 50, 'maximum': 100, 'default': 95},
            ],
            'steps': [
                {'op': 'image.resize', 'max_width': 1600, 'max_height': 1600, 'upscale': False},
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95},
            ],
            'destination': {'mode': 'beside'},
        }
        # Quality (1..100) accepts qual (50..100), rejects edge (300..8000), title, flag!
        q_compat = [p['id'] for p in params.compatible_parameters_for_field(recipe, 1, 'quality')]
        self.assertEqual(q_compat, ['qual'])
        # max_width (1..100000) accepts edge and qual, rejects title and flag.
        w_compat = [p['id'] for p in params.compatible_parameters_for_field(recipe, 0, 'max_width')]
        self.assertEqual(w_compat, ['edge', 'qual'])

        # Reordering preserves visibility dependency order.
        cond_recipe = copy.deepcopy(DEMO_RECIPE)
        # Moving do_resize (index 1) down past max_edge (index 2) violates visible_when!
        ok, msg = params.can_reorder_parameter(cond_recipe, 1, 1)
        self.assertFalse(ok)
        self.assertIn('Maximum image dimension', msg)
        # Moving max_edge (index 2) up above do_resize (index 1) also fails!
        ok2, msg2 = params.can_reorder_parameter(cond_recipe, 2, -1)
        self.assertFalse(ok2)
        self.assertIn('Resize images to fit', msg2)
        # Moving strip_gps (index 4) up above jpeg_quality (index 3) succeeds!
        ok3, msg3 = params.can_reorder_parameter(cond_recipe, 4, -1)
        self.assertTrue(ok3)
        self.assertEqual(msg3, '')

    def test_02_parameter_references_and_condition_summary(self):
        refs = params.parameter_references(DEMO_RECIPE, 'project_name')
        kinds = {r['kind'] for r in refs}
        self.assertEqual(kinds, {'filename_template', 'destination_template'})

        edge_refs = params.parameter_references(DEMO_RECIPE, 'max_edge')
        self.assertEqual(len(edge_refs), 2)
        self.assertEqual({r['field'] for r in edge_refs}, {'max_width', 'max_height'})

        params_by_id = {p['id']: p for p in DEMO_RECIPE['parameters']}
        self.assertEqual(
            params.summarize_condition({'param': 'do_resize', 'equals': True}, params_by_id),
            'Resize images to fit is Yes',
        )


@unittest.skipUnless(HAS_PYSIDE6, 'PySide6 required')
class RecipeEditorAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'config')})
        env.start()
        self.addCleanup(env.stop)

    # 1, 27: Ordinary fixed Recipe editing & ordinary Editor-to-Runner handoff remain unchanged.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_01_ordinary_editor_unchanged_and_ordinary_handoff(self):
        img = self.base / 'sample.jpg'
        make_test_jpeg(img)

        dlg = make_editor_dialog(files=[str(img)])
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Ordinary built-in starts on Operations tab, Parameters count omitted, Preview Settings hidden, no dev draft button.
        self.assertEqual(w.splitter.count(), 2)
        self.assertEqual(w.workspace_tabs.currentIndex(), 0)
        self.assertEqual(w.workspace_tabs.tabText(0), 'Operations')
        self.assertEqual(w.workspace_tabs.tabText(1), 'Parameters')
        self.assertEqual(w.workspace_tabs.tabText(2), 'Preview')
        self.assertFalse(hasattr(dlg, 'new_dev_draft_button'))
        self.assertFalse(w.preview_settings_button.isVisibleTo(w))
        self.assertFalse(params.is_parameterized(w.recipe))

        # Create & save an ordinary User Recipe normally.
        w.new()
        w.name.setText('Ordinary Export')
        w.changed()
        self.assertTrue(w.is_dirty())
        self.assertTrue(w.save())
        self.assertFalse(w.is_dirty())

        # Ordinary saved-definition handoff verification still succeeds.
        saved = verify_editor_handoff(copy.deepcopy(w.recipe), copy.deepcopy(w.baseline))
        self.assertEqual(saved['id'], w.recipe['id'])

    # 2, 3, 4, 5, 6, 7, 8, 9: Field bindings, sharing, incompatibility, unbinding, rename, delete guard, reorder.
    def test_02_field_bindings_sharing_rename_delete_guard_and_reorder(self):
        draft = build_new_draft()
        draft['steps'].insert(1, {'op': 'image.resize', 'max_width': 1920, 'max_height': 1080, 'upscale': False})

        dlg = make_editor_dialog(dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Create parameter derived from image.resize.max_width (2).
        def fake_add_exec(dialog_self):
            dialog_self.label_edit.setText('Maximum edge')
            dialog_self._try_accept()
            return QDialog.Accepted

        with patch.object(ParameterEditorDialog, 'exec', fake_add_exec):
            created = w.bind_field_to_new_parameter(1, 'max_width')
        self.assertIsNotNone(created)
        pid = created['id']
        self.assertEqual(w.recipe['steps'][1]['bindings'], {'max_width': pid})
        # Literal fallback value (1920) stays intact!
        self.assertEqual(w.recipe['steps'][1]['max_width'], 1920)
        self.assertTrue(w.is_dirty())

        # Share same parameter with max_height (3).
        self.assertTrue(w.bind_field_to_parameter(1, 'max_height', pid))
        self.assertEqual(w.recipe['steps'][1]['bindings'], {'max_width': pid, 'max_height': pid})
        self.assertEqual(w.recipe['steps'][1]['max_height'], 1080)

        # Incompatible parameter excluded from field menu (4): add a text parameter, ensure NOT offered for max_width.
        w.recipe['parameters'].append({'id': 'note_text', 'label': 'Client note', 'type': 'text', 'required': True})
        self.assertTrue(params.validate_authored(w.recipe))  # (6) required without default is valid!
        compat_ids = [p['id'] for p in params.compatible_parameters_for_field(w.recipe, 1, 'max_width', w.definitions)]
        self.assertIn(pid, compat_ids)
        self.assertNotIn('note_text', compat_ids)

        # Rename parameter label without breaking bindings (7).
        def fake_rename_exec(dialog_self):
            dialog_self.label_edit.setText('Target dimension')
            dialog_self._try_accept()
            return QDialog.Accepted

        with patch.object(ParameterEditorDialog, 'exec', fake_rename_exec):
            self.assertTrue(w.edit_parameter(pid))
        self.assertEqual(w.recipe['parameters'][0]['id'], pid)
        self.assertEqual(w.recipe['parameters'][0]['label'], 'Target dimension')
        self.assertEqual(w.recipe['steps'][1]['bindings'], {'max_width': pid, 'max_height': pid})
        params.validate_authored(w.recipe)

        # Referenced parameter cannot be silently deleted (8).
        with patch.object(QMessageBox, 'warning') as warn_mock:
            self.assertFalse(w.remove_parameter(pid))
            warn_mock.assert_called_once()
        self.assertTrue(any(p['id'] == pid for p in w.recipe['parameters']))

        # Unbind max_height -> returns to original literal fallback 1080 without deleting shared parameter (5).
        self.assertTrue(w.unbind_field(1, 'max_height'))
        self.assertEqual(w.recipe['steps'][1]['max_height'], 1080)
        self.assertEqual(w.recipe['steps'][1]['bindings'], {'max_width': pid})
        self.assertTrue(any(p['id'] == pid for p in w.recipe['parameters']))

        # Unbind max_width too -> now parameter is unreferenced and CAN be deleted!
        self.assertTrue(w.unbind_field(1, 'max_width'))
        self.assertNotIn('bindings', w.recipe['steps'][1])
        self.assertEqual(w.recipe['steps'][1]['max_width'], 1920)
        self.assertTrue(w.remove_parameter(pid))
        self.assertFalse(any(p['id'] == pid for p in w.recipe['parameters']))

        # Valid reorder succeeds, invalid visibility reorder rejected (9).
        w.recipe['parameters'] = [
            {'id': 'ctrl', 'label': 'Control', 'type': 'boolean', 'default': True},
            {'id': 'child', 'label': 'Child', 'type': 'text', 'visible_when': {'param': 'ctrl', 'equals': True}},
            {'id': 'other', 'label': 'Other', 'type': 'text'},
        ]
        with patch.object(w, 'error') as err_mock:
            self.assertFalse(w.move_parameter('ctrl', 1))
            err_mock.assert_called_once()
        self.assertTrue(w.move_parameter('other', -1))
        self.assertEqual([p['id'] for p in w.recipe['parameters']], ['ctrl', 'other', 'child'])

    # 10, 11, 12: Conditional visibility widget, conditional step activation, mutually exclusive branches.
    def test_03_conditions_activation_and_mutually_exclusive_branches(self):
        earlier = [
            {'id': 'do_resize', 'label': 'Resize images', 'type': 'boolean', 'default': True},
            {'id': 'target', 'label': 'Delivery profile', 'type': 'choice', 'default': 'web',
             'choices': [{'value': 'web', 'label': 'Web JPEG'}, {'value': 'print', 'label': 'Print TIFF'}]},
        ]
        # ConditionEditorWidget equality, membership (in), and conjunction (all) (10).
        ce = ConditionEditorWidget(earlier, verb='Show', target_label='Maximum dimension')
        self.addCleanup(ce.deleteLater)
        ce.set_condition({
            'all': [
                {'param': 'do_resize', 'equals': True},
                {'param': 'target', 'in': ['web', 'print']},
            ]
        })
        self.assertEqual(
            ce.condition(),
            {'all': [{'param': 'do_resize', 'equals': True}, {'param': 'target', 'in': ['web', 'print']}]},
        )
        self.assertIn('Resize images is Yes', ce.summary_label.text())
        self.assertIn('Web JPEG or Print TIFF', ce.summary_label.text())

        # Mutually exclusive choice-controlled branches in Editor (11, 12).
        branch_draft = {
            'schema': 4,
            'id': 'dev-draft-branches',
            'name': 'Branch Test',
            'description': 'Mutually exclusive formats.',
            'media': 'image',
            'parameters': copy.deepcopy(earlier),
            'steps': [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95,
                 'enabled_when': {'param': 'target', 'equals': 'web'}},
                {'op': 'image.convert', 'format': 'tiff', 'quality': 90,
                 'enabled_when': {'param': 'target', 'equals': 'print'}},
            ],
            'destination': {'mode': 'beside'},
        }
        dlg = make_editor_dialog(dev_draft=branch_draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        self.assertIn('(conditional)', w.steps.item(0).text())
        self.assertIn('(conditional)', w.steps.item(1).text())
        self.assertNotIn('optional', w.steps.item(0).text().casefold())

        # Resolve web vs print branch cleanly.
        web_concrete = params.resolve_recipe(w.recipe, {'target': 'web'})
        self.assertTrue(web_concrete['steps'][0]['enabled'])
        self.assertFalse(web_concrete['steps'][1]['enabled'])
        print_concrete = params.resolve_recipe(w.recipe, {'target': 'print'})
        self.assertFalse(print_concrete['steps'][0]['enabled'])
        self.assertTrue(print_concrete['steps'][1]['enabled'])

        # StepActivationDialog builds a valid condition cleanly.
        act_dlg = StepActivationDialog(
            step_label='Convert Format',
            enabled=True,
            enabled_when={'param': 'target', 'equals': 'web'},
            available_params=earlier,
        )
        self.addCleanup(act_dlg.deleteLater)
        act_dlg._try_accept()
        self.assertTrue(act_dlg.result_enabled)
        self.assertEqual(act_dlg.result_enabled_when, {'param': 'target', 'equals': 'web'})

    # 13, 14: Filename and destination subfolder variable insertion.
    def test_04_filename_and_subfolder_variable_insertion(self):
        draft = copy.deepcopy(DEMO_RECIPE)
        draft['id'] = 'dev-draft-templates'
        dlg = make_editor_dialog(dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Filename step (index 5) offers source tokens AND compatible parameters, not boolean/conditional max_edge.
        w.steps.setCurrentRow(5)
        self.app.processEvents()
        pat_menu = QMenu()
        w._populate_pattern_insert_menu(5, w.parameter_widgets['pattern'], pat_menu)
        pat_labels = [act.text() for act in pat_menu.actions() if not act.isSeparator()]
        self.assertIn('Original filename', pat_labels)
        self.assertIn('Image capture date', pat_labels)
        self.assertIn('Sequence number', pat_labels)
        self.assertIn('Client or project name', pat_labels)
        self.assertNotIn('Resize images to fit', pat_labels)  # boolean excluded
        self.assertNotIn('Maximum image dimension', pat_labels)  # conditional param excluded on unconditional step!

        # Inserting a token updates pattern & remains neutral when Preview Settings empty.
        w.parameter_widgets['pattern'].setText('{filename}')
        w._insert_template_token(w.parameter_widgets['pattern'], '_{param:project_name}', is_pattern=True, row=5)
        self.assertEqual(w.recipe['steps'][5]['pattern'], '{filename}_{param:project_name}')
        self.assertIn('example values', w.filename_example.text().casefold())

        # Subfolder insert menu offers ONLY compatible unconditional parameters, NO source tokens!
        w._populate_subfolder_insert_menu()
        sub_labels = [act.text() for act in w.folder_insert_menu.actions()]
        self.assertIn('Client or project name', sub_labels)
        self.assertNotIn('Original filename', sub_labels)
        self.assertNotIn('Image capture date', sub_labels)
        self.assertNotIn('Maximum image dimension', sub_labels)
        w.folder.setText('')
        w._insert_template_token(w.folder, '{param:project_name}', is_pattern=False)
        self.assertEqual(w.recipe['destination'], {'mode': 'subfolder', 'folder': '{param:project_name}'})

    # 15, 16, 17, 18, 19, 20, 21: Preview Settings, dirty isolation, neutral guidance, live preview, stale worker, header cache.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_05_preview_settings_dirty_state_stale_worker_and_cache(self):
        img = self.base / 'landscape.jpg'
        make_test_jpeg(img, width=400, height=200)
        draft = copy.deepcopy(DEMO_RECIPE)
        draft['id'] = 'dev-draft-preview'

        dlg = make_editor_dialog(files=[str(img)], dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # PreviewSettingsDialog reuses ParameterFormWidget with neutral initial validation (15).
        ps = PreviewSettingsDialog(w.recipe, entered_values={})
        self.addCleanup(ps.deleteLater)
        self.assertIsInstance(ps.form, ParameterFormWidget)
        self.assertEqual(ps.form.field_error('project_name'), '')
        self.assertFalse(ps.reset_button.isEnabled())
        ps.form.field_widget('project_name').setText('Marathon')
        self.assertTrue(ps.reset_button.isEnabled())

        # Incomplete preview answers show ONE neutral guidance panel, NOT duplicated in an empty table (18).
        preview_tab = w.workspace_tabs.widget(2)
        self.assertEqual(w.status.text(), '')
        self.assertTrue(w.preview_guidance_panel.isVisibleTo(preview_tab))
        self.assertEqual(
            w.preview_guidance_label.text(),
            'Set example values to preview this Recipe.',
        )
        self.assertEqual(w.preview_settings_button.text(), 'Set example values…')
        self.assertEqual(ps.apply_button.text(), 'Update Preview')
        self.assertFalse(w.table.isVisibleTo(preview_tab))
        self.assertFalse(w.preview_tools.isVisibleTo(preview_tab))
        self.assertFalse(w.is_dirty())
        self.assertIsNone(w.preview_worker)

        # Supplying preview values generates concrete preview WITHOUT making authored recipe dirty (16, 19)
        # and without resetting the active tab.
        w.workspace_tabs.setCurrentIndex(2)
        authored_before = copy.deepcopy(w.recipe)
        w._preview_values_by_recipe[w.recipe['id']] = {'project_name': 'Marathon', 'max_edge': 300}
        w.update_preview()
        settle_editor(w)
        self.assertEqual(w.workspace_tabs.currentIndex(), 2)
        self.assertFalse(w.preview_guidance_panel.isVisibleTo(preview_tab))
        self.assertTrue(w.table.isVisibleTo(preview_tab))
        self.assertTrue(w.preview_tools.isVisibleTo(preview_tab))
        self.assertEqual(w.recipe, authored_before)
        self.assertFalse(w.is_dirty())
        # Verify concrete preview populated Files -> Output filename = Marathon_landscape.jpg & header cached (21)!
        files_group = w.table.groups['Files']
        file_rows = {files_group.child(i).text(0): files_group.child(i).text(1) for i in range(files_group.childCount())}
        self.assertEqual(file_rows['Output filename'], 'Marathon_landscape.jpg')
        self.assertIn(str(img.absolute()), w.checked_inputs)

        # Stale worker completion cannot overwrite newer preview (20).
        class FakeStaleWorker:
            generation = w.preview_generation - 1
            recipe = {'id': 'old'}
            sample = str(img)
            checked_inputs = {}
            row = core.PreviewRow(str(img), output='/tmp/STALE_WRONG.jpg')
            def isInterruptionRequested(self): return False
            def deleteLater(self): pass

        w.preview_worker = FakeStaleWorker()
        w.preview_finished()
        files_group = w.table.groups['Files']
        file_rows = {files_group.child(i).text(0): files_group.child(i).text(1) for i in range(files_group.childCount())}
        self.assertEqual(file_rows['Output filename'], 'Marathon_landscape.jpg')

        # Changing authored default DOES update dirty state (17).
        w.recipe['parameters'][2]['default'] = 1200
        w.update_modified()
        self.assertTrue(w.is_dirty())

    # 22: Specialized Crop and Watermark configuration preserves bindings and literal fallbacks.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_06_specialized_crop_and_watermark_preserves_bindings(self):
        from kim_image_ops import OVERLAY_DEFAULTS
        from kim_image_ops_dialog import ImageOperationDialog

        img = self.base / 'photo.jpg'
        make_test_jpeg(img, width=400, height=200)
        draft = {
            'schema': 4,
            'id': 'dev-draft-overlay',
            'name': 'Parameterized Watermark',
            'description': 'Overlay with bound opacity and condition.',
            'media': 'image',
            'parameters': [
                {'id': 'add_mark', 'label': 'Add watermark', 'type': 'boolean', 'default': True},
                {'id': 'mark_opacity', 'label': 'Watermark opacity', 'type': 'integer',
                 'minimum': 10, 'maximum': 100, 'default': 40,
                 'visible_when': {'param': 'add_mark', 'equals': True}},
            ],
            'steps': [
                {
                    **dict(op='image.overlay', **{**OVERLAY_DEFAULTS, 'value': 'Proof', 'opacity': 70}),
                    'enabled_when': {'param': 'add_mark', 'equals': True},
                    'bindings': {'opacity': 'mark_opacity'},
                },
                {'op': 'file.rename_output', 'pattern': '{filename}_marked'},
            ],
            'destination': {'mode': 'beside'},
        }
        dlg = make_editor_dialog(files=[str(img)], dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Supply preview override mark_opacity=25; open ImageOperationDialog, accept with a change to anchor only.
        w._preview_values_by_recipe[w.recipe['id']] = {'mark_opacity': 25}
        seen_recipes = []

        def fake_ops_exec(ops_dlg):
            # Must receive concrete resolved recipe (no 'parameters' key, opacity=25)!
            seen_recipes.append(copy.deepcopy(ops_dlg.recipe))
            ops_dlg.step['anchor'] = 'top_left'
            return QDialog.Accepted

        with patch.object(ImageOperationDialog, 'exec', fake_ops_exec):
            w.configure_image_operation(0)

        self.assertEqual(len(seen_recipes), 1)
        self.assertFalse(params.is_parameterized(seen_recipes[0]))
        self.assertEqual(seen_recipes[0]['steps'][0]['opacity'], 25)
        # Bindings, enabled_when, and original literal fallback (opacity=70) are ALL preserved!
        updated = w.recipe['steps'][0]
        self.assertEqual(updated['anchor'], 'top_left')
        self.assertEqual(updated['bindings'], {'opacity': 'mark_opacity'})
        self.assertEqual(updated['enabled_when'], {'param': 'add_mark', 'equals': True})
        self.assertEqual(updated['opacity'], 70)

    # 23, 24, 25, 26: Dev draft -> Runner Settings -> Review -> Real Execution, AND persistence rejected safely.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_07_dev_draft_runner_handoff_real_execution_and_persistence_rejection(self):
        img = self.base / 'trail.jpg'
        make_test_jpeg(img, width=400, height=200, gps=True, artist='Trail Author')
        before_source = observe_source(img)

        draft = copy.deepcopy(DEMO_RECIPE)
        draft['id'] = 'dev-draft-e2e'
        dlg = make_editor_dialog(files=[str(img)], dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # 26: Saving parameterized Recipe is rejected safely and never writes recipes.json!
        with patch.object(w, 'error') as err_mock:
            self.assertFalse(w.save())
            err_mock.assert_called_once()
            self.assertIn('disabled', str(err_mock.call_args[0][0]).casefold())
        self.assertFalse((self.base / 'config' / 'kimng' / 'recipes.json').exists())
        self.assertFalse(w.shortcut_checkbox.isEnabled())

        # 23, 24, 25: Hand off temporary dev draft into Runner -> Settings -> Review -> Real Execution!
        captured_runner = []

        def fake_runner_exec(runner):
            captured_runner.append(runner)
            self.assertEqual(runner.runner_phase, 'settings')
            self.assertEqual(runner.windowTitle(), 'KIMng - Run a Recipe - Settings')
            runner.settings_page.form.field_widget('project_name').setText('Sierra')
            runner.settings_page.form.field_widget('max_edge').setValue(300)
            runner.enter_review_from_settings()
            settle_runner(runner)
            self.assertEqual(runner.runner_phase, 'review')
            self.assertTrue(runner.run_button.isEnabled())
            runner.start_execution()
            settle_runner(runner)
            self.assertTrue(runner.execution_succeeded, runner.results)
            return QDialog.Accepted

        with patch.object(RunRecipeDialog, 'exec', fake_runner_exec):
            w.load_photos_and_run([str(img)])

        self.assertEqual(len(captured_runner), 1)
        expected_out = self.base / 'Sierra' / 'Sierra_trail.jpg'
        self.assertTrue(expected_out.is_file())

        from kim_recipe_image import inspect, selected_metadata
        _, fmt, width, height = inspect(expected_out)
        self.assertEqual((fmt, width, height), ('jpeg', 300, 150))
        meta = selected_metadata(expected_out, ('EXIF:Artist', 'GPS:GPSLatitude'))
        self.assertEqual(meta['EXIF:Artist'], 'Trail Author')
        self.assertIsNone(meta['GPS:GPSLatitude'])
        # Original file content, size, mtime, ctime untouched.
        self.assertEqual(observe_source(img), before_source)

    # Milestone 3A: Two-pane tabbed workspace, summaries, single Activation control, menu & footer.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_08_two_pane_tabbed_workspace_switching_and_summaries(self):
        img = self.base / 'sample.jpg'
        make_test_jpeg(img, width=400, height=200)
        draft = copy.deepcopy(DEMO_RECIPE)
        draft['id'] = 'dev-draft-m3a-layout'

        dlg = make_editor_dialog(files=[str(img)], dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Two-pane splitter and 1366x768-friendly default dialog geometry.
        self.assertEqual(w.splitter.count(), 2)
        self.assertLessEqual(dlg.width(), 1280)
        self.assertLessEqual(dlg.height(), 720)

        # Save Recipe button lives in the left library pane beneath Import/Export with Ctrl+S.
        save_btn = w.management_buttons['Save']
        self.assertEqual(save_btn.text(), 'Save Recipe')
        self.assertIsNot(save_btn.parentWidget(), dlg)
        self.assertIs(save_btn.parentWidget(), w.transfer_button.parentWidget())
        self.assertFalse(save_btn.shortcut().isEmpty())

        # Consolidated Selected Recipe menu preserves actions and enablement.
        menu_texts = [
            act.text() for act in w.selected_recipe_menu.actions()
            if not act.isSeparator()
        ]
        self.assertEqual(menu_texts, ['Duplicate Recipe', 'Move to Folder…', 'Rename', 'Delete'])
        self.assertTrue(w.management_buttons['Duplicate to Edit'].isEnabled())
        self.assertTrue(w.move_recipe_button.isEnabled())
        self.assertTrue(w.management_buttons['Rename'].isEnabled())
        self.assertTrue(w.management_buttons['Delete'].isEnabled())

        # Tab labels and default tab.
        self.assertEqual(w.workspace_tabs.currentIndex(), 0)
        self.assertEqual(w.workspace_tabs.tabText(0), 'Operations')
        self.assertEqual(w.workspace_tabs.tabText(1), 'Parameters (5)')
        self.assertEqual(w.workspace_tabs.tabText(2), 'Preview')

        # Parameter-aware operation summaries (presentation only, never "optional").
        step_texts = [w.steps.item(i).text() for i in range(w.steps.count())]
        self.assertEqual(step_texts[0], 'Auto-orient')
        self.assertEqual(step_texts[1], 'Resize to Fit: Maximum image dimension (conditional)')
        self.assertEqual(step_texts[2], 'Color Profile: sRGB')
        self.assertEqual(step_texts[3], 'Convert Format: JPEG, ask for quality')
        self.assertEqual(step_texts[4], 'Remove GPS metadata (conditional)')
        self.assertEqual(step_texts[5], 'Rename Output File: uses Client or project name')
        for text in step_texts:
            self.assertNotIn('optional', text.casefold())

        # Inline Run this operation control in Step settings (no redundant top Activation button).
        self.assertFalse(hasattr(w, 'step_activation_button'))
        w.steps.setCurrentRow(1)
        self.app.processEvents()
        self.assertIsNotNone(w.step_run_mode_combo)
        mode_labels = [
            w.step_run_mode_combo.itemText(i)
            for i in range(w.step_run_mode_combo.count())
        ]
        self.assertEqual(
            mode_labels,
            ['Always', 'Never', 'Ask when running', 'Only when a condition is met…'],
        )
        self.assertEqual(w.step_run_mode_combo.currentData(), 'ask')

        # Single-parameter subfolder loads into simple "Ask when running" mode without exposing raw syntax.
        self.assertEqual(w.folder.text(), '{param:project_name}')
        self.assertEqual(w.subfolder_mode.currentData(), 'ask')
        self.assertEqual(w.subfolder_param_combo.currentData(), 'project_name')
        self.assertFalse(w.folder_row.isVisibleTo(w.destination_group))
        self.assertTrue(w.subfolder_ask_row.isVisibleTo(w.destination_group))
        w.steps.setCurrentRow(5)
        self.app.processEvents()
        self.assertEqual(w.parameter_widgets['pattern'].text(), '{param:project_name}_{filename}')
        self.assertEqual(
            w.pattern_summary.text(),
            'Pattern uses: Client or project name, Original filename',
        )

        # Tab switching never marks dirty, never resets values, never triggers redundant inspection.
        w._preview_values_by_recipe[w.recipe['id']] = {'project_name': 'Cascade'}
        w.update_preview()
        settle_editor(w)
        gen_before = w.preview_generation
        self.assertFalse(w.is_dirty())

        w.workspace_tabs.setCurrentIndex(1)
        self.app.processEvents()
        w.workspace_tabs.setCurrentIndex(2)
        self.app.processEvents()
        w.workspace_tabs.setCurrentIndex(0)
        self.app.processEvents()

        self.assertFalse(w.is_dirty())
        self.assertEqual(w.preview_generation, gen_before)
        self.assertEqual(w.current_preview_values(), {'project_name': 'Cascade'})

        # Refreshing parameters while on the Parameters tab does not reset the active tab.
        w.workspace_tabs.setCurrentIndex(1)
        self.app.processEvents()
        w._refresh_parameters_section()
        self.assertEqual(w.workspace_tabs.currentIndex(), 1)

    # Milestone 3A: Parameters tab empty state vs populated 5-parameter table.
    def test_09_parameters_tab_empty_and_populated_table(self):
        # Ordinary built-in Recipe: empty state without Add button.
        dlg = make_editor_dialog()
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        expected_tab_tip = (
            'Let a Recipe ask for different settings each time it runs, '
            'such as a project name, image dimensions or JPEG quality.'
        )
        ps = w.parameters_section
        self.assertEqual(w.workspace_tabs.tabText(1), 'Parameters')
        self.assertEqual(w.workspace_tabs.tabToolTip(1), expected_tab_tip)
        self.assertTrue(ps.empty_panel.isVisibleTo(ps))
        self.assertFalse(ps.table_panel.isVisibleTo(ps))
        self.assertFalse(ps.empty_add_button.isVisibleTo(ps))

        # Editable new User Recipe: concise empty state without redundant intro sentence.
        w.new()
        settle_editor(w)
        self.assertFalse(ps.intro_label.isVisibleTo(ps))
        self.assertTrue(ps.empty_panel.isVisibleTo(ps))
        self.assertTrue(ps.empty_add_button.isVisibleTo(ps))
        self.assertEqual(ps.empty_add_button.text(), 'Add question…')
        self.assertEqual(ps.empty_heading.text(), 'Let your Recipe ask questions')
        self.assertEqual(
            ps.empty_label.text(),
            'Ask for settings such as JPEG quality, image dimensions or a project name when running this Recipe.',
        )
        self.assertEqual(
            ps.empty_guidance.text(),
            "Choose Ask when running in an operation's settings to create a question.",
        )

        # Populated 5-parameter Recipe: intro sentence shown with 3-column table.
        draft = copy.deepcopy(DEMO_RECIPE)
        draft['id'] = 'dev-draft-m3a-params'
        dlg2 = make_editor_dialog(dev_draft=draft)
        self.addCleanup(close_editor, dlg2)
        w2 = dlg2.widget
        settle_editor(w2)

        ps2 = w2.parameters_section
        self.assertTrue(ps2.intro_label.isVisibleTo(ps2))
        self.assertEqual(
            ps2.intro_label.text(),
            'Parameters let you ask questions whose answers control Recipe settings.',
        )
        self.assertEqual(w2.workspace_tabs.tabText(1), 'Parameters (5)')
        self.assertEqual(w2.workspace_tabs.tabToolTip(1), expected_tab_tip)
        self.assertFalse(ps2.empty_panel.isVisibleTo(ps2))
        self.assertTrue(ps2.table_panel.isVisibleTo(ps2))
        self.assertEqual(ps2.tree.columnCount(), 3)
        self.assertEqual(
            [ps2.tree.headerItem().text(c) for c in range(3)],
            ['Question', 'Default answer', 'Used in'],
        )
        self.assertEqual(ps2.add_button.text(), 'Add question…')
        self.assertEqual(ps2.tree.topLevelItemCount(), 5)
        rows = [
            tuple(ps2.tree.topLevelItem(i).text(c) for c in range(3))
            for i in range(5)
        ]
        self.assertEqual(rows[0], ('Client or project name', 'Ask each time', 'Filename, Subfolder'))
        self.assertEqual(rows[1][0], 'Resize images to fit')
        self.assertEqual(rows[1][1], 'Yes')
        self.assertIn('Resize to Fit', rows[1][2])
        self.assertEqual(rows[2], ('Maximum image dimension', '1600 px', 'Resize to Fit: Maximum width, Maximum height'))
        self.assertEqual(rows[3], ('JPEG quality', '95', 'Convert Format: JPEG quality'))
        self.assertEqual(rows[4], ('Remove GPS metadata', 'Yes', 'Remove GPS metadata'))
        # Answer type remains available via tooltip without cluttering table columns.
        self.assertIn('Answer type: Whole number', ps2.tree.topLevelItem(2).toolTip(0))

    # Milestone 3B: Add/Edit Parameter dialog, placeholders, defaults, Runner preview & Advanced settings.
    def test_10_m3b_parameter_dialog_basic_advanced_preview_and_placeholders(self):
        # 1. New manual question starts empty with gray instructional placeholder (NOT saved as data!).
        add_dlg = ParameterEditorDialog()
        self.addCleanup(add_dlg.deleteLater)
        self.assertEqual(add_dlg.windowTitle(), 'KIMng - Add Parameter')
        self.assertEqual(add_dlg.label_edit.text(), '')
        self.assertEqual(add_dlg.label_edit.placeholderText(), 'e.g. Client or project name')
        self.assertFalse(add_dlg.is_advanced_expanded())
        self.assertTrue(add_dlg.default_ask_radio.isChecked())

        # Attempting to accept with empty question fails (placeholder never becomes authored text).
        add_dlg._try_accept()
        self.assertIsNone(add_dlg.result_param)
        self.assertTrue(add_dlg.error_label.isVisibleTo(add_dlg))

        # Enter real question + literal default 'Marathon' and verify live read-only Runner example!
        add_dlg.label_edit.setText('Client or project name')
        add_dlg.default_literal_radio.setChecked(True)
        self.assertEqual(add_dlg._default_widget.placeholderText(), 'e.g. Marathon')
        self.assertEqual(add_dlg._default_widget.text(), '')
        add_dlg._default_widget.setText('Marathon')
        self.app.processEvents()
        self.assertEqual(add_dlg._preview_caption.text(), 'Client or project name:')
        self.assertEqual(add_dlg._preview_control.text(), 'Marathon')
        self.assertTrue(add_dlg._preview_control.isReadOnly())

        add_dlg._try_accept()
        self.assertIsNotNone(add_dlg.result_param)
        self.assertEqual(add_dlg.result_param['label'], 'Client or project name')
        self.assertEqual(add_dlg.result_param['default'], 'Marathon')

        # 2. Existing question loads real text, preserves stable ID on rewording, and keeps Advanced data across collapse.
        earlier = [{'id': 'do_resize', 'label': 'Resize images to fit', 'type': 'boolean', 'default': True}]
        existing = {
            'id': 'max_edge',
            'label': 'Maximum image dimension',
            'type': 'integer',
            'minimum': 300,
            'maximum': 8000,
            'default': 1600,
            'help': 'Fits within this limit while keeping proportions.',
            'visible_when': {'param': 'do_resize', 'equals': True},
        }
        edit_dlg = ParameterEditorDialog(
            param=copy.deepcopy(existing),
            earlier_params=earlier,
            locked_type=True,
        )
        self.addCleanup(edit_dlg.deleteLater)
        self.assertEqual(edit_dlg.windowTitle(), 'KIMng - Edit Parameter')
        self.assertEqual(edit_dlg.label_edit.text(), 'Maximum image dimension')
        self.assertFalse(edit_dlg.is_advanced_expanded())
        self.assertFalse(edit_dlg.type_combo.isEnabled())

        # Expand, collapse without editing Advanced, reword question -> all Advanced settings & stable ID survive!
        edit_dlg._set_advanced_expanded(True)
        self.assertTrue(edit_dlg.is_advanced_expanded())
        self.assertEqual(edit_dlg.help_edit.toPlainText(), existing['help'])
        self.assertEqual(edit_dlg.min_edit.text(), '300')
        self.assertEqual(edit_dlg.max_edit.text(), '8000')
        edit_dlg._set_advanced_expanded(False)
        edit_dlg.label_edit.setText('Max output dimension')
        edit_dlg._try_accept()
        self.assertEqual(edit_dlg.result_param['id'], 'max_edge')
        self.assertEqual(edit_dlg.result_param['label'], 'Max output dimension')
        self.assertEqual(edit_dlg.result_param['minimum'], 300)
        self.assertEqual(edit_dlg.result_param['maximum'], 8000)
        self.assertEqual(edit_dlg.result_param['help'], existing['help'])
        self.assertEqual(edit_dlg.result_param['visible_when'], existing['visible_when'])

        # 3. Validation error inside collapsed Advanced settings reveals Advanced automatically!
        bad_dlg = ParameterEditorDialog(param={'type': 'integer'})
        self.addCleanup(bad_dlg.deleteLater)
        bad_dlg.label_edit.setText('Dimension')
        bad_dlg.min_edit.setText('not_a_number')
        self.assertFalse(bad_dlg.is_advanced_expanded())
        bad_dlg._try_accept()
        self.assertIsNone(bad_dlg.result_param)
        self.assertTrue(bad_dlg.is_advanced_expanded())
        self.assertIn('whole number', bad_dlg.error_label.text().casefold())

    # Milestone 3B: Workflow B (shared resize shortcut) & Workflow C (inline optional GPS activation) + compound preservation.
    def test_11_m3b_inline_activation_compound_preservation_and_shared_resize(self):
        draft = build_new_draft()
        draft['steps'] = [
            {'op': 'image.auto_orient'},
            {'op': 'image.resize', 'max_width': 1600, 'max_height': 1600, 'upscale': False},
            {'op': 'metadata.strip_gps'},
            {'op': 'file.rename_output', 'pattern': '{filename}_export'},
        ]
        dlg = make_editor_dialog(dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Workflow C: Switch Remove GPS Location to 'Ask when running' directly from inline combo (NO modal dialog!).
        w.steps.setCurrentRow(2)
        self.app.processEvents()
        with patch.object(StepActivationDialog, 'exec', side_effect=AssertionError('Must not open advanced dialog!')):
            idx = w.step_run_mode_combo.findData('ask')
            w.step_run_mode_combo.setCurrentIndex(idx)
            self.app.processEvents()

        self.assertEqual(len(w.recipe.get('parameters', [])), 1)
        gps_param = w.recipe['parameters'][0]
        self.assertEqual(gps_param['type'], 'boolean')
        self.assertEqual(gps_param['default'], True)
        self.assertEqual(
            w.recipe['steps'][2]['enabled_when'],
            {'param': gps_param['id'], 'equals': True},
        )
        self.assertIn('(conditional)', w.steps.item(2).text())
        # Toggle default inline to No and back to Yes cleanly.
        w.step_run_default_combo.setCurrentIndex(w.step_run_default_combo.findData(False))
        self.assertFalse(w.recipe['parameters'][0]['default'])
        w.step_run_default_combo.setCurrentIndex(w.step_run_default_combo.findData(True))
        self.assertTrue(w.recipe['parameters'][0]['default'])

        # Workflow B: Shared Resize to Fit shortcut binds max_width & max_height to ONE ordinary integer parameter!
        w.steps.setCurrentRow(1)
        self.app.processEvents()
        self.assertIsNotNone(w.shared_resize_check)
        self.assertTrue(w.shared_resize_check.isEnabled())
        self.assertFalse(w.shared_resize_check.isChecked())
        w.shared_resize_check.setChecked(True)
        self.app.processEvents()

        resize_step = w.recipe['steps'][1]
        self.assertEqual(set(resize_step['bindings'].keys()), {'max_width', 'max_height'})
        shared_pid = resize_step['bindings']['max_width']
        self.assertEqual(resize_step['bindings']['max_height'], shared_pid)
        self.assertEqual(resize_step['max_width'], 1600)
        self.assertEqual(resize_step['max_height'], 1600)
        shared_param = next(p for p in w.recipe['parameters'] if p['id'] == shared_pid)
        self.assertEqual(shared_param['type'], 'integer')
        self.assertEqual(shared_param['default'], 1600)
        params.validate_authored(w.recipe)

        # Unchecking shared shortcut restores fixed literal values WITHOUT silently deleting the parameter.
        w.shared_resize_check.setChecked(False)
        self.app.processEvents()
        self.assertNotIn('bindings', w.recipe['steps'][1])
        self.assertEqual(w.recipe['steps'][1]['max_width'], 1600)
        self.assertEqual(w.recipe['steps'][1]['max_height'], 1600)
        self.assertTrue(any(p['id'] == shared_pid for p in w.recipe['parameters']))

        # Conflicting partial binding disables shortcut with clear guidance and never replaces it!
        self.assertTrue(w.bind_field_to_parameter(1, 'max_width', shared_pid))
        w.steps.setCurrentRow(1)
        self.app.processEvents()
        self.assertFalse(w.shared_resize_check.isEnabled())
        self.assertIsNotNone(w.shared_resize_note)
        self.assertIn('separate settings', w.shared_resize_note.text().casefold())
        self.assertEqual(w.recipe['steps'][1]['bindings'], {'max_width': shared_pid})

        # Existing compound condition remains in 'condition' mode; canceling dialog leaves definition unchanged!
        w.recipe['parameters'].append({
            'id': 'profile',
            'label': 'Profile',
            'type': 'choice',
            'default': 'web',
            'choices': [{'value': 'web', 'label': 'Web'}, {'value': 'print', 'label': 'Print'}],
        })
        compound = {'all': [{'param': gps_param['id'], 'equals': True}, {'param': 'profile', 'equals': 'web'}]}
        w.recipe['steps'][2]['enabled_when'] = copy.deepcopy(compound)
        w.steps.setCurrentRow(2)
        self.app.processEvents()
        self.assertEqual(w.step_run_mode_combo.currentData(), 'condition')
        self.assertEqual(w.recipe['steps'][2]['enabled_when'], compound)
        with patch.object(StepActivationDialog, 'exec', return_value=QDialog.Rejected):
            self.assertFalse(w.configure_step_activation(2))
        self.assertEqual(w.recipe['steps'][2]['enabled_when'], compound)

    # Milestone 3B: Subfolder simple/advanced modes, compound patterns, literal braces & unsupported Save disabled.
    def test_12_m3b_subfolder_modes_compound_templates_and_literal_braces(self):
        # 1. Compound pattern loads cleanly into 'advanced' mode without losing data.
        compound_draft = copy.deepcopy(DEMO_RECIPE)
        compound_draft['id'] = 'dev-draft-compound-sub'
        compound_draft['destination'] = {'mode': 'subfolder', 'folder': '{param:project_name}_web'}
        dlg = make_editor_dialog(dev_draft=compound_draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        self.assertEqual(w.subfolder_mode.currentData(), 'advanced')
        self.assertTrue(w.folder_row.isVisibleTo(w.destination_group))
        self.assertTrue(w.folder_insert_button.isVisibleTo(w.destination_group))
        self.assertEqual(w.folder.text(), '{param:project_name}_web')

        # Dirty parameterized temporary draft keeps Save DISABLED (never appears available!).
        w.name.setText('Edited Draft Name')
        w.changed()
        self.assertTrue(w.is_dirty())
        self.assertFalse(w.management_buttons['Save'].isEnabled())

        # Switching to 'No subfolder' -> {'mode': 'beside'}, then 'Use a fixed name' -> {'mode': 'subfolder', ...}
        w.subfolder_mode.setCurrentIndex(w.subfolder_mode.findData('none'))
        self.app.processEvents()
        self.assertEqual(w.recipe['destination'], {'mode': 'beside'})

        w.subfolder_mode.setCurrentIndex(w.subfolder_mode.findData('fixed'))
        self.app.processEvents()
        w.folder.setText('{Drafts}')
        w.changed()
        self.assertEqual(w.recipe['destination'], {'mode': 'subfolder', 'folder': '{Drafts}'})
        # Reloading literal brace folder name keeps it in 'fixed' mode (never reinterpreted as template!).
        w._sync_subfolder_widgets_from_recipe()
        self.assertEqual(w.subfolder_mode.currentData(), 'fixed')
        self.assertEqual(w.folder.text(), '{Drafts}')

    # Milestone 3B: Acceptance Workflow A end-to-end through real UI + Section 11 multiline help wrapping.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_13_m3b_workflow_a_end_to_end_and_preview_help_wrapping(self):
        img = self.base / 'runner_photo.jpg'
        make_test_jpeg(img, width=400, height=200, gps=True, artist='Runner Author')
        before_source = observe_source(img)

        # Start from a clean temporary draft with no parameters yet.
        draft = build_new_draft()
        draft['id'] = 'dev-draft-workflow-a'
        dlg = make_editor_dialog(files=[str(img)], dev_draft=draft)
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)

        # Step 1-4: Choose Subfolder -> Ask when running, create "Client or project name" with default "Marathon".
        def fake_create_client_param(dialog_self):
            self.assertEqual(dialog_self.windowTitle(), 'KIMng - Add Parameter')
            self.assertEqual(dialog_self.label_edit.text(), '')
            self.assertEqual(dialog_self.label_edit.placeholderText(), 'e.g. Client or project name')
            dialog_self.label_edit.setText('Client or project name')
            dialog_self.default_literal_radio.setChecked(True)
            dialog_self._default_widget.setText('Marathon')
            dialog_self._try_accept()
            return QDialog.Accepted

        with patch.object(ParameterEditorDialog, 'exec', fake_create_client_param):
            w.subfolder_mode.setCurrentIndex(w.subfolder_mode.findData('ask'))
            self.app.processEvents()

        self.assertEqual(w.subfolder_mode.currentData(), 'ask')
        self.assertEqual(len(w.recipe['parameters']), 1)
        pid = w.recipe['parameters'][0]['id']
        self.assertEqual(w.recipe['parameters'][0]['label'], 'Client or project name')
        self.assertEqual(w.recipe['parameters'][0]['default'], 'Marathon')
        self.assertEqual(w.recipe['destination'], {'mode': 'subfolder', 'folder': '{param:' + pid + '}'})

        # Step 5: Reuse the same question in Rename Output File.
        rename_row = next(i for i, s in enumerate(w.recipe['steps']) if s['op'] == 'file.rename_output')
        w.steps.setCurrentRow(rename_row)
        self.app.processEvents()
        w.parameter_widgets['pattern'].setText('_{filename}')
        w.parameter_widgets['pattern'].setCursorPosition(0)
        w._insert_template_token(
            w.parameter_widgets['pattern'], '{param:' + pid + '}', is_pattern=True, row=rename_row
        )
        self.assertEqual(w.recipe['steps'][rename_row]['pattern'], '{param:' + pid + '}_{filename}')

        # Step 6: Enter a DIFFERENT temporary example value ('Cascade') in Preview Settings without altering default!
        def fake_preview_exec(ps_dlg):
            ps_dlg.form.field_widget(pid).setText('Cascade')
            return QDialog.Accepted

        with patch.object(PreviewSettingsDialog, 'exec', fake_preview_exec):
            self.assertTrue(w.open_preview_settings())
        settle_editor(w)
        # Authored default stays 'Marathon' while example preview uses 'Cascade'!
        self.assertEqual(w.recipe['parameters'][0]['default'], 'Marathon')
        self.assertEqual(w.current_preview_values()[pid], 'Cascade')
        self.assertEqual(w.destination_summary.text(), 'Example subfolder: Cascade')

        # Step 7-8: Run through Runner Settings -> Review -> Real Execution!
        def fake_runner_exec(runner):
            self.assertEqual(runner.runner_phase, 'settings')
            # Runner shows the real question 'Client or project name:' with authored default 'Marathon'!
            self.assertEqual(runner.settings_page.form.field_label(pid).text(), 'Client or project name:')
            self.assertEqual(runner.settings_page.form.field_widget(pid).text(), 'Marathon')
            runner.enter_review_from_settings()
            settle_runner(runner)
            self.assertEqual(runner.runner_phase, 'review')
            self.assertTrue(runner.run_button.isEnabled())
            runner.start_execution()
            settle_runner(runner)
            self.assertTrue(runner.execution_succeeded, runner.results)
            return QDialog.Accepted

        with patch.object(RunRecipeDialog, 'exec', fake_runner_exec):
            w.load_photos_and_run([str(img)])

        expected_out = self.base / 'Marathon' / 'Marathon_runner_photo.jpg'
        self.assertTrue(expected_out.is_file())
        self.assertEqual(observe_source(img), before_source)

        # Section 11: Verify multiline help text in PreviewSettingsDialog is NEVER clipped across widths & toggles!
        ps_help = PreviewSettingsDialog(copy.deepcopy(DEMO_RECIPE), entered_values={})
        self.addCleanup(ps_help.deleteLater)
        ps_help.show()
        for width in (420, 560, 760):
            ps_help.resize(width, 460)
            for _ in range(5):
                self.app.processEvents()
            help_lbl = ps_help.form._rows['max_edge']['help_label']
            required_h = help_lbl.heightForWidth(help_lbl.width())
            self.assertGreaterEqual(
                help_lbl.height(),
                required_h,
                f'Help label clipped at dialog width {width}: actual={help_lbl.height()} < required={required_h}',
            )
        # Toggle conditional field off and back on, confirm help height remains unclipped!
        ps_help.form.field_widget('do_resize').setChecked(False)
        self.app.processEvents()
        ps_help.form.field_widget('do_resize').setChecked(True)
        for _ in range(5):
            self.app.processEvents()
        help_lbl = ps_help.form._rows['max_edge']['help_label']
        self.assertGreaterEqual(help_lbl.height(), help_lbl.heightForWidth(help_lbl.width()))

    def test_14_m4a_operation_picker_answer_controls_and_types(self):
        from PySide6.QtCore import Qt
        from kim_recipe_dialog import OperationPicker
        from kim_recipe_author_ui import PARAMETER_TYPE_DISPLAY
        from kim_recipe_params import parameter_references

        # 1. All 30 registered operations have descriptions and appear in OperationPicker.
        defs = core.handler('image').operation_definitions()
        self.assertEqual(len(defs), 30)
        self.assertIn('metadata.reduce_gps', defs)
        self.assertIn('metadata.set_description', defs)
        self.assertIn('metadata.set_keywords', defs)
        for op_id, d in defs.items():
            self.assertTrue(
                bool((d.get('description') or '').strip()),
                f'Operation {op_id} missing description',
            )
        picker = OperationPicker(defs)
        self.addCleanup(picker.deleteLater)
        self.assertLessEqual(picker.height(), 420)
        self.assertTrue(bool(picker.description_label.text().strip()))
        listed_ops = set()
        for i in range(picker.tree.topLevelItemCount()):
            cat = picker.tree.topLevelItem(i)
            for j in range(cat.childCount()):
                listed_ops.add(cat.child(j).data(0, Qt.UserRole))
        self.assertEqual(listed_ops, set(defs.keys()))

        # 2. Human-readable answer type labels.
        self.assertEqual(PARAMETER_TYPE_DISPLAY['number'], 'Decimal number')
        self.assertEqual(PARAMETER_TYPE_DISPLAY['choice'], 'List of choices')

        # 3. Edit Parameter shows "This answer controls" for used and unused parameters.
        refs = parameter_references(DEMO_RECIPE, 'project_name', definitions=defs)
        used_dlg = ParameterEditorDialog(
            param=copy.deepcopy(DEMO_RECIPE['parameters'][0]),
            references=refs,
            recipe=DEMO_RECIPE,
        )
        self.addCleanup(used_dlg.deleteLater)
        self.assertIsNotNone(used_dlg.controls_group)
        self.assertEqual(used_dlg.controls_group.title(), 'This answer controls')
        self.assertIn('Destination: Subfolder', used_dlg.controls_label.text())
        self.assertIn('Filename', used_dlg.controls_label.text())

        unused_dlg = ParameterEditorDialog(
            param={'id': 'unused_q', 'label': 'Unused question', 'type': 'text'},
            references=[],
            recipe=DEMO_RECIPE,
        )
        self.addCleanup(unused_dlg.deleteLater)
        self.assertIn('Not used yet', unused_dlg.controls_label.text())

    def test_15_selected_image_retention_and_deliberate_removal_sync(self):
        img1 = self.base / 'ret_one.jpg'
        img2 = self.base / 'ret_two.jpg'
        make_test_jpeg(img1, width=200, height=150)
        make_test_jpeg(img2, width=200, height=150)

        # 1. Editor opened with 2 selected images -> Runner removes 1 image -> Editor reflects 1 image
        #    and never silently restores the deliberately removed image.
        dlg = make_editor_dialog(files=[str(img1), str(img2)])
        self.addCleanup(close_editor, dlg)
        w = dlg.widget
        settle_editor(w)
        self.assertEqual(dlg.run_selected_button.text(), 'Run with 2 selected images')

        def fake_remove_one(runner_self):
            runner_self.replace_files([str(img2)], preflight=False)
            return QDialog.Rejected

        with patch.object(RunRecipeDialog, 'exec', fake_remove_one):
            w.load_photos_and_run(list(w.files))
        self.assertEqual(w.files, [str(img2)])
        self.assertEqual(dlg.run_selected_button.text(), 'Run with 1 selected image')
        self.assertTrue(dlg.run_selected_button.isVisibleTo(dlg))

        # 2. Runner clears all images -> Editor switches to Choose images & run… (never restores cleared).
        def fake_clear_all(runner_self):
            runner_self.replace_files([], preflight=False)
            return QDialog.Rejected

        with patch.object(RunRecipeDialog, 'exec', fake_clear_all):
            w.load_photos_and_run(list(w.files))
        self.assertEqual(w.files, [])
        self.assertFalse(dlg.run_selected_button.isVisibleTo(dlg))
        self.assertTrue(dlg.choose_images_button.isVisibleTo(dlg))

        # 3. Editor with 0 images -> Choose images & run… picks [img1, img2] -> Editor retains them.
        def fake_keep(runner_self):
            return QDialog.Rejected

        with patch('kim_recipe_dialog.choose_images', return_value=[str(img1), str(img2)]), \
             patch.object(RunRecipeDialog, 'exec', fake_keep):
            w.load_photos_and_run()
        self.assertEqual(w.files, [str(img1), str(img2)])
        self.assertEqual(dlg.run_selected_button.text(), 'Run with 2 selected images')


if __name__ == '__main__':
    unittest.main()
