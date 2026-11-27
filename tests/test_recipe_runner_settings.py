"""Focused Milestone 2 tests for contextual Recipe Runner Settings (Option B)."""
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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLineEdit, QSpinBox
    from kim_recipe_param_ui import ParameterFormWidget, RecipeSettingsPage
    from kim_recipe_run import RunRecipeDialog
    from demo_parameterized_runner import DEMO_RECIPE


def settle(dialog, timeout=15.0):
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
    app.processEvents()
    assert dialog.preflight_worker is None, 'preflight_worker did not finish'
    assert dialog.worker is None, 'worker did not finish'
    assert dialog.add_worker is None, 'add_worker did not finish'


def make_test_jpeg(path, *, width=80, height=60, gps=True, artist='Original Artist'):
    subprocess.run(['magick', '-size', f'{width}x{height}', 'xc:navy', str(path)], check=True)
    args = ['exiftool', '-overwrite_original', f'-Artist={artist}']
    if gps:
        args += ['-GPSLatitude=45.5', '-GPSLatitudeRef=N', '-GPSLongitude=122.6', '-GPSLongitudeRef=W']
    args.append(str(path))
    subprocess.run(args, check=True, capture_output=True)


def observe_source(path):
    info = os.lstat(path)
    return (
        sha256_noatime(path),
        info.st_size,
        info.st_atime_ns,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


@unittest.skipUnless(HAS_PYSIDE6, 'PySide6 required')
class ParameterFormWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    # 3, 4, 5: Effective constraints, required without defaults (unset state), False and 0 handling.
    def test_unset_required_boolean_integer_and_zero_false_values(self):
        recipe = {
            'schema': 4,
            'id': 'unset-test',
            'name': 'Unset Test',
            'description': 'Test unset state vs False and zero.',
            'media': 'image',
            'parameters': [
                {'id': 'req_bool', 'label': 'Require upscale', 'type': 'boolean', 'required': True},
                {'id': 'req_int', 'label': 'PNG level', 'type': 'integer', 'required': True},
                {'id': 'req_choice', 'label': 'Color mode', 'type': 'choice', 'required': True,
                 'choices': [{'value': 'preserve', 'label': 'Keep original profile'}, {'value': 'srgb', 'label': 'Convert to sRGB'}]},
                {'id': 'req_num', 'label': 'Rotation angle', 'type': 'number', 'required': True},
            ],
            'steps': [
                {'op': 'image.resize', 'max_width': 1600, 'max_height': 1600, 'upscale': False, 'bindings': {'upscale': 'req_bool'}},
                {'op': 'image.rotate', 'degrees': 0, 'bindings': {'degrees': 'req_num'}},
                {'op': 'image.color', 'mode': 'preserve', 'bindings': {'mode': 'req_choice'}},
                {'op': 'image.compress', 'preset': 'custom', 'quality': 85, 'png_level': 6,
                 'jpeg_progressive': True, 'jpeg_optimize': False, 'bindings': {'png_level': 'req_int'}},
            ],
            'destination': {'mode': 'beside'},
        }
        form = ParameterFormWidget()
        self.addCleanup(form.deleteLater)
        form.set_recipe(recipe)

        # Required boolean without default uses combo starting at "Choose…", NOT False.
        bool_w = form.field_widget('req_bool')
        self.assertIsInstance(bool_w, QComboBox)
        self.assertEqual(bool_w.currentText(), 'Choose…')

        # Required bounded integer inherits effective bounds (0..9 from png_level),
        # with unset sentinel -1 ("Not set"), NOT 0.
        int_w = form.field_widget('req_int')
        self.assertIsInstance(int_w, QSpinBox)
        self.assertEqual(int_w.minimum(), -1)
        self.assertEqual(int_w.maximum(), 9)
        self.assertEqual(int_w.value(), -1)

        # Choice displays human-readable labels, not internal identifiers.
        choice_w = form.field_widget('req_choice')
        self.assertEqual(choice_w.itemText(1), 'Keep original profile')
        self.assertEqual(choice_w.itemText(2), 'Convert to sRGB')

        # All four required fields initially produce errors and no active values.
        self.assertTrue(form.has_errors())
        self.assertEqual(set(form.evaluation()['errors']), {'req_bool', 'req_int', 'req_choice', 'req_num'})
        self.assertEqual(form.active_values(), {})

        # Selecting False ("No"), 0, choice, and 0.0 satisfies all required inputs.
        bool_w.setCurrentIndex(2)  # No -> False
        int_w.setValue(0)
        choice_w.setCurrentIndex(2)  # srgb
        num_w = form.field_widget('req_num')
        self.assertIsInstance(num_w, QLineEdit)
        num_w.setText('0')

        self.assertFalse(form.has_errors())
        self.assertEqual(
            form.active_values(),
            {'req_bool': False, 'req_int': 0, 'req_choice': 'srgb', 'req_num': 0.0},
        )

        # Invalid numeric text blocks immediately without crashing.
        num_w.setText('not-a-number')
        self.assertTrue(form.has_errors())
        self.assertIn('req_num', form.evaluation()['errors'])
        self.assertNotIn('req_num', form.active_values())

        # Out-of-range numeric value (-500 outside -360..360 inherited from image.rotate.degrees) blocks.
        num_w.setText('-500')
        self.assertTrue(form.has_errors())
        self.assertIn('req_num', form.evaluation()['errors'])

        # Reset restores unset state cleanly.
        form.reset_to_defaults()
        self.assertEqual(bool_w.currentIndex(), 0)
        self.assertEqual(int_w.value(), -1)
        self.assertEqual(num_w.text(), '')
        self.assertTrue(form.has_errors())

    # 6: Conditional visibility preserves widget identity, focus/values in memory, excludes inactive values.
    def test_conditional_visibility_preserves_widgets_and_hidden_values(self):
        form = ParameterFormWidget()
        self.addCleanup(form.deleteLater)
        form.set_recipe(DEMO_RECIPE)

        project_w = form.field_widget('project_name')
        resize_w = form.field_widget('do_resize')
        edge_w = form.field_widget('max_edge')
        self.assertIsInstance(resize_w, QCheckBox)
        self.assertIsInstance(edge_w, QSpinBox)
        self.assertEqual(edge_w.suffix(), ' px')
        self.assertTrue(form.row_visible('max_edge'))

        project_w.setText('Alpine')
        edge_w.setValue(1200)
        self.assertEqual(form.active_values()['max_edge'], 1200)

        # Uncheck resize -> max_edge hides, value stays in memory, excluded from active_values().
        resize_w.setChecked(False)
        self.assertFalse(form.row_visible('max_edge'))
        self.assertIs(form.field_widget('max_edge'), edge_w)  # Widget NOT rebuilt!
        self.assertEqual(form.entered_values()['max_edge'], 1200)
        self.assertNotIn('max_edge', form.active_values())

        # Re-check resize -> max_edge reappears with 1200 restored and revalidated.
        resize_w.setChecked(True)
        self.assertTrue(form.row_visible('max_edge'))
        self.assertEqual(edge_w.value(), 1200)
        self.assertEqual(form.active_values()['max_edge'], 1200)


@unittest.skipUnless(HAS_PYSIDE6, 'PySide6 required')
class RunnerContextualSettingsTests(unittest.TestCase):
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

    # 1: Ordinary Recipe skips Settings page and goes straight to Review Changes.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_01_ordinary_recipe_skips_settings_direct_review(self):
        img = self.base / 'sample.jpg'
        make_test_jpeg(img)
        dialog = RunRecipeDialog(core.builtins()[0], [str(img)])
        self.addCleanup(dialog.close)
        settle(dialog)

        self.assertEqual(dialog.runner_phase, 'review')
        self.assertEqual(dialog.review_stack.currentIndex(), 1)
        self.assertFalse(dialog.settings_back_button.isVisibleTo(dialog))
        self.assertFalse(dialog.review_button.isVisibleTo(dialog))
        self.assertTrue(dialog.run_button.isVisibleTo(dialog))
        self.assertTrue(dialog.run_button.isEnabled())

    # 2, 7, 8, 9, 10, 11, 14, 15, 16: Full Settings -> Review -> Settings -> Review & destination override & cancel.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_02_parameterized_runner_lifecycle_round_trips_and_cancel(self):
        img1 = self.base / 'one.jpg'
        img2 = self.base / 'two.jpg'
        make_test_jpeg(img1, width=100, height=50, gps=True)
        make_test_jpeg(img2, width=80, height=60, gps=True)
        demo_before = copy.deepcopy(DEMO_RECIPE)

        # Start parameterized Runner with 1 image -> opens on Settings page (index 2), no preflight.
        dialog = RunRecipeDialog(DEMO_RECIPE, [str(img1)])
        self.addCleanup(dialog.close)
        self.app.processEvents()

        self.assertEqual(dialog.runner_phase, 'settings')
        self.assertEqual(dialog.review_stack.currentIndex(), 2)
        self.assertIsNone(dialog.preflight_worker)
        self.assertIsNone(dialog.execution_recipe)
        self.assertTrue(dialog.review_button.isVisibleTo(dialog))
        self.assertFalse(dialog.review_button.isEnabled())  # project_name missing
        self.assertFalse(dialog.run_button.isVisibleTo(dialog))
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertFalse(dialog.settings_back_button.isVisibleTo(dialog))

        # Invalid path traversal in project_name shows immediate natural inline error,
        # disables Review Changes, and stays in Settings if called directly.
        proj_w = dialog.settings_page.form.field_widget('project_name')
        proj_w.setText('../bad')
        self.assertFalse(dialog.review_button.isEnabled())
        self.assertIn('separator', dialog.settings_page.form.field_error('project_name').casefold())
        dialog.enter_review_from_settings()
        self.assertEqual(dialog.runner_phase, 'settings')
        self.assertEqual(dialog.review_stack.currentIndex(), 2)
        self.assertIsNone(dialog.execution_recipe)
        self.assertIsNone(dialog.preflight_worker)

        # Queue mutation while in Settings (adding img2) must NOT start preflight and preserves entered text.
        proj_w.setText('ClientAlpha')
        dialog.settings_page.form.field_widget('max_edge').setValue(1200)
        dialog.settings_page.form.field_widget('strip_gps').setChecked(False)
        dialog.add_files([str(img2)])
        settle(dialog)
        self.assertEqual(dialog.runner_phase, 'settings')
        self.assertEqual(len(dialog.files), 2)
        self.assertIsNone(dialog.execution_recipe)
        self.assertEqual(proj_w.text(), 'ClientAlpha')
        self.assertTrue(dialog.review_button.isEnabled())

        # Click Review changes -> compiles concrete snapshot, switches to page 1, runs preflight.
        dialog.enter_review_from_settings()
        settle(dialog)
        self.assertEqual(dialog.runner_phase, 'review')
        self.assertEqual(dialog.review_stack.currentIndex(), 1)
        self.assertTrue(dialog.settings_back_button.isVisibleTo(dialog))
        self.assertFalse(dialog.review_button.isVisibleTo(dialog))
        self.assertTrue(dialog.run_button.isVisibleTo(dialog))
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertIsNotNone(dialog.approved_plan)

        # Shared parameter max_edge resolved into both max_width and max_height.
        self.assertEqual(dialog.execution_recipe['steps'][1]['max_width'], 1200)
        self.assertEqual(dialog.execution_recipe['steps'][1]['max_height'], 1200)
        # strip_gps=False -> step 4 is disabled in execution_recipe and labeled "(Disabled)" in UI!
        self.assertFalse(dialog.execution_recipe['steps'][4]['enabled'])
        self.assertIn('(Disabled)', dialog.operations.topLevelItem(4).text(0))
        self.assertIn('5 enabled, 6 total', dialog.operations_panel.title())
        # Destination displays resolved subfolder name, never raw {param:...}.
        self.assertIn('ClientAlpha', dialog.destination_label.text())
        self.assertNotIn('{param:', dialog.destination_label.text())

        # Destination override after parameter resolution uses latest resolved snapshot.
        gen_before = dialog.generation
        idx_beside = dialog.destination_choice.findData('beside')
        dialog.destination_choice.setCurrentIndex(idx_beside)
        settle(dialog)
        self.assertGreater(dialog.generation, gen_before)
        self.assertEqual(dialog.execution_recipe['destination'], {'mode': 'beside'})
        self.assertEqual(dialog.execution_recipe['steps'][1]['max_width'], 1200)
        self.assertTrue(dialog.run_button.isEnabled())
        # Restore default destination.
        dialog.destination_choice.setCurrentIndex(dialog.destination_choice.findData('default'))
        settle(dialog)
        self.assertEqual(dialog.execution_recipe['destination'], {'mode': 'subfolder', 'folder': 'ClientAlpha'})

        # Back to settings immediately invalidates approval and preserves queue & values.
        gen_review = dialog.generation
        dialog.open_settings_page()
        self.assertEqual(dialog.runner_phase, 'settings')
        self.assertEqual(dialog.review_stack.currentIndex(), 2)
        self.assertGreater(dialog.generation, gen_review)
        self.assertIsNone(dialog.approved_plan)
        self.assertIsNone(dialog.validated_snapshot)
        self.assertIsNone(dialog.execution_recipe)
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertEqual(len(dialog.files), 2)
        self.assertEqual(proj_w.text(), 'ClientAlpha')

        # Toggle do_resize=False and return to Review -> fresh plan with resize disabled!
        dialog.settings_page.form.field_widget('do_resize').setChecked(False)
        dialog.enter_review_from_settings()
        settle(dialog)
        self.assertFalse(dialog.execution_recipe['steps'][1]['enabled'])
        self.assertIn('(Disabled)', dialog.operations.topLevelItem(1).text(0))
        self.assertEqual(dialog.rows[0].properties['width'], 100)  # full width preserved

        # Cancel without executing creates zero outputs and leaves DEMO_RECIPE unchanged.
        dialog.reject()
        self.assertFalse((self.base / 'ClientAlpha').exists())
        self.assertEqual(DEMO_RECIPE, demo_before)

    # 12, 13: Recipe switching with active workers and stale preflight completion rejection.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_03_recipe_switching_and_stale_preflight_rejection(self):
        img = self.base / 'img.jpg'
        make_test_jpeg(img)

        # Start with ordinary recipe, then immediately switch to parameterized while preflight runs.
        dialog = RunRecipeDialog(core.builtins()[0], [str(img)])
        self.addCleanup(dialog.close)
        old_gen = dialog.generation
        dialog.apply_recipe(DEMO_RECIPE)
        settle(dialog)

        self.assertEqual(dialog.runner_phase, 'settings')
        self.assertEqual(dialog.review_stack.currentIndex(), 2)
        self.assertGreater(dialog.generation, old_gen)
        self.assertIsNone(dialog.approved_plan)
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertFalse(dialog._restart)

        # Simulate a stale worker emitting inspected/finished while in settings mode.
        class FakeStaleWorker:
            generation = old_gen
            cancelled = False
            checked_inputs = {}
            recipe = core.builtins()[0]
            files = [str(img)]
            chosen = None
            def deleteLater(self): pass

        stale = FakeStaleWorker()
        dialog.preflight_worker = stale
        dialog._restart = True
        dialog.preflight_finished()
        self.assertIsNone(dialog.approved_plan)
        self.assertIsNone(dialog.validated_snapshot)
        self.assertIsNone(dialog.preflight_worker)
        self.assertFalse(dialog.run_button.isEnabled())

    # 17: Standalone Crop and Watermark isolation.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_04_standalone_watermark_and_crop_isolation(self):
        img = self.base / 'photo.jpg'
        make_test_jpeg(img)
        from kim_image_ops import OVERLAY_DEFAULTS, CROP_DEFAULTS
        from kim_image_ops_dialog import ImageOperationDialog

        # Standalone Watermark RunRecipeDialog has NO review_stack, NO settings_page, keeps Back (131).
        overlay_recipe = {
            'schema': 3,
            'id': 'standalone-overlay',
            'name': 'Add Watermark / Overlay',
            'description': '',
            'media': 'image',
            'steps': [
                dict(op='image.overlay', **{**OVERLAY_DEFAULTS, 'value': 'Proof'}),
                {'op': 'file.rename_output', 'pattern': '{filename}_watermarked'},
            ],
            'destination': {'mode': 'beside'},
        }
        runner = RunRecipeDialog(overlay_recipe, [str(img)], operation_title='Add Watermark / Overlay')
        self.addCleanup(runner.close)
        settle(runner)
        self.assertFalse(hasattr(runner, 'review_stack'))
        self.assertFalse(hasattr(runner, 'settings_page'))
        self.assertFalse(hasattr(runner, 'review_button'))
        self.assertFalse(hasattr(runner, 'settings_back_button'))
        self.assertTrue(hasattr(runner, 'back_button'))
        self.assertEqual(runner.runner_phase, 'review')
        self.assertTrue(runner.run_button.isEnabled())

        # Standalone Crop dialog builds schema-3 concrete recipe cleanly.
        crop_dlg = ImageOperationDialog(dict(op='image.crop', **CROP_DEFAULTS), [str(img)])
        self.addCleanup(crop_dlg.close)
        built = crop_dlg.build_recipe()
        self.assertEqual(built['schema'], 3)
        self.assertFalse(params.is_parameterized(built))
        core.validate(built)

    # 18, 19, 20: Real derivative execution, metadata/dimensions verification, and collision protection.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_05_real_execution_and_collision_protection(self):
        img = self.base / 'hike.jpg'
        make_test_jpeg(img, width=400, height=200, gps=True, artist='Trail Photographer')
        before_source = observe_source(img)
        self.assertEqual(observe_source(img), before_source)

        dialog = RunRecipeDialog(DEMO_RECIPE, [str(img)])
        self.addCleanup(dialog.close)
        dialog.settings_page.form.field_widget('project_name').setText('Cascade')
        dialog.settings_page.form.field_widget('do_resize').setChecked(True)
        dialog.settings_page.form.field_widget('max_edge').setValue(300)
        dialog.settings_page.form.field_widget('jpeg_quality').setValue(95)
        dialog.settings_page.form.field_widget('strip_gps').setChecked(True)

        dialog.enter_review_from_settings()
        settle(dialog)
        self.assertTrue(dialog.run_button.isEnabled())

        expected_out = self.base / 'Cascade' / 'Cascade_hike.jpg'
        self.assertEqual(dialog.rows[0].output, str(expected_out))

        # Execute approved plan!
        dialog.start_execution()
        settle(dialog)
        self.assertTrue(dialog.execution_succeeded, dialog.results)
        self.assertTrue(expected_out.is_file())

        # Verify output dimensions resized 400x200 -> 300x150, GPS stripped, Artist preserved.
        from kim_recipe_image import inspect, selected_metadata
        _, fmt, w, h = inspect(expected_out)
        self.assertEqual((fmt, w, h), ('jpeg', 300, 150))
        meta = selected_metadata(expected_out, ('EXIF:Artist', 'GPS:GPSLatitude'))
        self.assertEqual(meta['EXIF:Artist'], 'Trail Photographer')
        self.assertIsNone(meta['GPS:GPSLatitude'])

        # Verify source file content, size, mtime and ctime remain untouched.
        after_source = observe_source(img)
        self.assertEqual(
            (after_source[0], after_source[1], after_source[3], after_source[4]),
            (before_source[0], before_source[1], before_source[3], before_source[4]),
        )

        # Existing collision protection: running again numbers during review (Cascade_hike_1.jpg),
        # AND creating that reviewed target on disk AFTER approval blocks publication atomically!
        dialog.open_settings_page()
        dialog.enter_review_from_settings()
        settle(dialog)
        numbered_out = self.base / 'Cascade' / 'Cascade_hike_1.jpg'
        self.assertEqual(dialog.rows[0].output, str(numbered_out))
        self.assertTrue(dialog.run_button.isEnabled())

        # Simulate post-review collision on disk -> publication MUST refuse to overwrite!
        numbered_out.write_bytes(b'existing-protected-file')
        dialog.start_execution()
        settle(dialog)
        self.assertFalse(dialog.execution_succeeded)
        self.assertEqual(numbered_out.read_bytes(), b'existing-protected-file')
        self.assertFalse(dialog.results[0]['ok'])

    # Milestone 2A: Neutral initial validation, natural inline errors, compact layout, tooltips, reset.
    def test_06_m2a_neutral_validation_compact_layout_tooltips_and_reset(self):
        page = RecipeSettingsPage()
        self.addCleanup(page.deleteLater)
        page.resize(620, 560)
        page.set_recipe(DEMO_RECIPE)
        self.app.processEvents()

        form = page.form
        proj_w = form.field_widget('project_name')
        edge_w = form.field_widget('max_edge')
        qual_w = form.field_widget('jpeg_quality')
        gps_w = form.field_widget('strip_gps')
        resize_w = form.field_widget('do_resize')

        # 1. Neutral initial presentation: NO red inline error on unanswered required field,
        #    while strict evaluation still blocks Review Changes.
        self.assertTrue(form.has_errors())
        self.assertEqual(form.field_error('project_name'), '')
        self.assertFalse(form._rows['project_name']['error_label'].isVisibleTo(form))
        self.assertEqual(proj_w.placeholderText(), 'Enter a name')
        self.assertEqual(
            form._rows['project_name']['help_label'].text(),
            'Required. Used for the output folder and filename prefix.',
        )

        # 2. Consistent trailing colons on labeled fields, none on checkboxes.
        self.assertEqual(form.field_label('project_name').text(), 'Client or project name:')
        self.assertEqual(form.field_label('max_edge').text(), 'Maximum image dimension:')
        self.assertEqual(form.field_label('jpeg_quality').text(), 'JPEG quality:')
        self.assertEqual(form.field_label('do_resize').text(), '')
        self.assertEqual(resize_w.text(), 'Resize images to fit')
        self.assertEqual(gps_w.text(), 'Remove GPS metadata')
        self.assertNotIn('help_label', form._rows['do_resize'])
        self.assertNotIn('help_label', form._rows['jpeg_quality'])
        self.assertNotIn('help_label', form._rows['strip_gps'])

        # 3. Numeric range text is in tooltips, NOT auto-appended to visible help paragraphs.
        self.assertNotIn('Allowed range', form._rows['max_edge']['help_label'].text())
        self.assertIn('300 to 8000 px', edge_w.toolTip())
        self.assertIn('1 to 100', qual_w.toolTip())
        self.assertIn('detail', qual_w.toolTip().casefold())
        self.assertIn('GPS', gps_w.toolTip())

        # 4. Compact numeric control widths (do not stretch across full form width).
        self.assertLessEqual(edge_w.maximumWidth(), 210)
        self.assertLessEqual(qual_w.maximumWidth(), 210)
        self.assertEqual(form._rows['max_edge']['container'].layout().contentsMargins().left(), 20)

        # 5. Reset to defaults disabled initially, enabled on any change, disabled on reset.
        self.assertTrue(form.is_at_defaults())
        self.assertFalse(page.reset_button.isEnabled())

        # Nonempty invalid value (path separator & whitespace-only) shows natural inline error.
        proj_w.setText('a/b')
        self.assertTrue(form.has_errors())
        self.assertIn('separator', form.field_error('project_name').casefold())
        self.assertNotIn("Parameter '", form.field_error('project_name'))
        self.assertTrue(page.reset_button.isEnabled())

        proj_w.setText('   ')
        self.assertTrue(form.has_errors())
        self.assertIn('spaces', form.field_error('project_name').casefold())

        # Clearing required field back to empty restores neutral presentation (no red error).
        proj_w.setText('')
        self.assertTrue(form.has_errors())
        self.assertEqual(form.field_error('project_name'), '')
        self.assertFalse(form._rows['project_name']['error_label'].isVisibleTo(form))
        self.assertFalse(page.reset_button.isEnabled())

        # Invalid numeric text and out-of-range numeric values show natural errors and enable Reset.
        num_recipe = {
            'schema': 4,
            'id': 'num-err-test',
            'name': 'Numeric Error Test',
            'description': 'Test numeric text validation.',
            'media': 'image',
            'parameters': [
                {'id': 'angle', 'label': 'Rotation angle', 'type': 'number', 'required': True},
            ],
            'steps': [
                {'op': 'image.rotate', 'degrees': 0, 'bindings': {'degrees': 'angle'}},
            ],
            'destination': {'mode': 'beside'},
        }
        page.set_recipe(num_recipe)
        angle_w = page.form.field_widget('angle')
        self.assertEqual(page.form.field_error('angle'), '')
        self.assertFalse(page.reset_button.isEnabled())
        angle_w.setText('abc')
        self.assertEqual(page.form.field_error('angle'), 'Enter a valid number.')
        self.assertTrue(page.reset_button.isEnabled())
        angle_w.setText('999')
        self.assertIn('-360', page.form.field_error('angle'))
        self.assertIn('360', page.form.field_error('angle'))
        self.assertNotIn("Parameter '", page.form.field_error('angle'))
        angle_w.setText('')
        self.assertEqual(page.form.field_error('angle'), '')
        self.assertFalse(page.reset_button.isEnabled())

    # Milestone 2A: Pure-Python live Example output (templates, braces, conditional ops, {date}, zero I/O).
    def test_07_m2a_example_output_pure_python_and_edge_cases(self):
        # 1. Hidden when Recipe has no parameterized filename or destination templates.
        no_tpl_recipe = {
            'schema': 4,
            'id': 'no-tpl',
            'name': 'No Template',
            'description': 'Only quality parameterized.',
            'media': 'image',
            'parameters': [
                {'id': 'q', 'label': 'JPEG quality', 'type': 'integer', 'default': 90},
            ],
            'steps': [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 90, 'bindings': {'quality': 'q'}},
            ],
            'destination': {'mode': 'beside'},
        }
        self.assertFalse(params.has_parameterized_output_templates(no_tpl_recipe))
        page = RecipeSettingsPage()
        self.addCleanup(page.deleteLater)
        page.set_recipe(no_tpl_recipe)
        self.assertFalse(page.example_group.isVisibleTo(page))

        # 2. Visible for DEMO_RECIPE, updates live, zero subprocess/preflight calls.
        self.assertTrue(params.has_parameterized_output_templates(DEMO_RECIPE))
        with patch('subprocess.run', side_effect=AssertionError('Must not invoke external tools')):
            page.set_recipe(DEMO_RECIPE)
            page.set_example_source('/nonexistent/landscape.jpg')
            self.assertTrue(page.example_group.isVisibleTo(page))
            self.assertEqual(
                page.example_qualification.text(),
                'Example only. Exact output paths are confirmed during Review Changes.',
            )
            # Initially incomplete -> neutral prompt, never raw {param:...}.
            self.assertTrue(page.example_prompt.isVisibleTo(page))
            self.assertNotIn('{param:', page.example_prompt.text())
            self.assertEqual(page.example_filename.text(), '')

            # Valid input -> exact example filename and subfolder.
            proj_w = page.form.field_widget('project_name')
            proj_w.setText('Marathon')
            self.assertEqual(page.example_filename.text(), 'Marathon_landscape.jpg')
            self.assertEqual(page.example_subfolder.text(), 'Marathon')
            self.assertFalse(page.example_prompt.isVisibleTo(page))

            # Switching selected source filename updates example immediately.
            page.set_example_source('/nonexistent/portrait.png')
            self.assertEqual(page.example_filename.text(), 'Marathon_portrait.jpg')

            # Literal braces in user input stay literal (never expanded as capture date!).
            proj_w.setText('{date}')
            self.assertEqual(page.example_filename.text(), '{date}_portrait.jpg')
            self.assertEqual(page.example_subfolder.text(), '{date}')

            # Invalid separator hides preview cleanly and shows neutral prompt.
            proj_w.setText('bad/sub')
            self.assertEqual(page.example_filename.text(), '')
            self.assertTrue(page.example_prompt.isVisibleTo(page))
            self.assertNotIn('{param:', page.example_prompt.text())

        # 3. Capture-date templates never invent a fake capture date.
        date_tpl_recipe = {
            'schema': 4,
            'id': 'date-tpl',
            'name': 'Date Template',
            'description': 'Uses capture date token.',
            'media': 'image',
            'parameters': [
                {'id': 'tag', 'label': 'Trip name', 'type': 'text', 'required': True},
            ],
            'steps': [
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95},
                {'op': 'file.rename_output', 'pattern': '{param:tag}_{date}_{filename}'},
            ],
            'destination': {'mode': 'subfolder', 'folder': '{param:tag}'},
        }
        res = params.preview_output_example(date_tpl_recipe, {'tag': 'Alps'}, source_name='peak.jpg')
        self.assertTrue(res['complete'])
        self.assertIsNone(res['filename'])
        self.assertEqual(res['subfolder'], 'Alps')
        self.assertIn('capture date', res['note'].casefold())

        # 4. Conditional rename operation activation respected in example output.
        cond_rename_recipe = {
            'schema': 4,
            'id': 'cond-rename',
            'name': 'Conditional Rename',
            'description': 'Toggle rename.',
            'media': 'image',
            'parameters': [
                {'id': 'add_prefix', 'label': 'Add prefix', 'type': 'boolean', 'default': False},
                {'id': 'prefix', 'label': 'Prefix', 'type': 'text', 'default': 'Web',
                 'visible_when': {'param': 'add_prefix', 'equals': True}},
            ],
            'steps': [
                {'op': 'image.convert', 'format': 'png', 'quality': 90},
                {'op': 'file.rename_output', 'pattern': '{param:prefix}_{filename}',
                 'enabled_when': {'param': 'add_prefix', 'equals': True}},
            ],
            'destination': {'mode': 'beside'},
        }
        res_off = params.preview_output_example(cond_rename_recipe, {'add_prefix': False}, source_name='shot.jpg')
        self.assertEqual(res_off['filename'], 'shot.png')
        res_on = params.preview_output_example(cond_rename_recipe, {'add_prefix': True, 'prefix': 'Web'}, source_name='shot.jpg')
        self.assertEqual(res_on['filename'], 'Web_shot.png')

    # Milestone 2A: Runner titles, buttons, blank queue statuses, initial focus, Review formatting & scroll-to-top.
    @unittest.skipUnless(HAS_MEDIA_TOOLS, 'ImageMagick and ExifTool required')
    def test_08_m2a_runner_titles_buttons_queue_focus_review_formatting_and_scroll(self):
        img1 = self.base / 'landscape.jpg'
        img2 = self.base / 'lake_reflection.jpg'
        make_test_jpeg(img1, width=1600, height=1066, gps=True)
        make_test_jpeg(img2, width=1200, height=900, gps=True)

        # Ordinary Recipe uses consistent Review Changes title.
        ordinary = RunRecipeDialog(core.builtins()[0], [str(img1)])
        self.addCleanup(ordinary.close)
        settle(ordinary)
        self.assertEqual(ordinary.windowTitle(), 'KIMng - Run a Recipe - Review Changes')
        self.assertIn('Web subfolder beside each source', ordinary.destination_label.text())
        ordinary.close()

        # Parameterized Recipe opens in Settings with exact title, buttons, blank statuses, and focus.
        dialog = RunRecipeDialog(DEMO_RECIPE, [str(img1), str(img2)])
        self.addCleanup(dialog.close)
        dialog.show()
        for _ in range(5):
            self.app.processEvents()

        self.assertEqual(dialog.windowTitle(), 'KIMng - Run a Recipe - Settings')
        self.assertEqual(dialog.review_button.text(), 'Review Changes')
        self.assertEqual(dialog.settings_back_button.text(), 'Back')
        self.assertFalse(dialog.review_button.isEnabled())
        self.assertFalse(dialog.settings_page.reset_button.isEnabled())

        # Selected-image Status column is blank during Settings phase.
        self.assertEqual(dialog.inputs.topLevelItem(0).text(1), '')
        self.assertEqual(dialog.inputs.topLevelItem(1).text(1), '')

        # Initial keyboard focus lands on first unanswered required field (project_name).
        proj_w = dialog.settings_page.form.field_widget('project_name')
        self.assertIs(dialog.focusWidget(), proj_w)

        # Selecting second image in Settings updates live Example output without starting preflight.
        proj_w.setText('Marathon')
        self.assertEqual(dialog.settings_page.example_filename.text(), 'Marathon_landscape.jpg')
        dialog.inputs.setCurrentItem(dialog.inputs.topLevelItem(1))
        self.app.processEvents()
        self.assertEqual(dialog.settings_page.example_filename.text(), 'Marathon_lake_reflection.jpg')
        self.assertIsNone(dialog.preflight_worker)
        dialog.inputs.setCurrentItem(dialog.inputs.topLevelItem(0))

        # Enter Review Changes -> verify title, statuses, formatting, provenance, scroll-to-top.
        dialog.enter_review_from_settings()
        settle(dialog)
        self.assertEqual(dialog.windowTitle(), 'KIMng - Run a Recipe - Review Changes')
        self.assertEqual(dialog.inputs.topLevelItem(0).text(1), 'Ready')
        self.assertEqual(dialog.inputs.topLevelItem(1).text(1), 'Ready')
        self.assertEqual(dialog.destination_label.text(), 'Subfolder beside each source: Marathon')

        # Check Output properties scroll starts at top.
        vbar = dialog.properties.verticalScrollBar()
        self.assertEqual(vbar.value(), vbar.minimum())

        # Expand all properties, scroll down manually, then select image 2 -> scroll must NOT be forced back.
        dialog.properties.expandAll()
        self.app.processEvents()
        if vbar.maximum() > vbar.minimum():
            vbar.setValue(vbar.maximum())
            moved = vbar.value()
            self.assertGreater(moved, vbar.minimum())
            dialog.inputs.setCurrentItem(dialog.inputs.topLevelItem(1))
            self.app.processEvents()
            # _scroll_review_to_top was already consumed once on entry.
            self.assertFalse(dialog._scroll_review_to_top)

        # Verify Review operation presentation & consistent (from run settings) provenance.
        op_texts = {}
        for i in range(dialog.operations.topLevelItemCount()):
            top = dialog.operations.topLevelItem(i)
            children = [top.child(j).text(0) for j in range(top.childCount())]
            op_texts[top.text(0)] = children

        self.assertIn('1. Auto-orient', op_texts)
        self.assertIn('Maximum width: 1600 px (from run settings)', op_texts['2. Resize to Fit'])
        self.assertIn('Maximum height: 1600 px (from run settings)', op_texts['2. Resize to Fit'])
        self.assertIn('Allow upscaling: No', op_texts['2. Resize to Fit'])
        self.assertIn('Color profile: sRGB', op_texts['3. Color Profile'])
        self.assertIn('Format: JPEG', op_texts['4. Convert Format'])
        self.assertIn('Quality: 95 (from run settings)', op_texts['4. Convert Format'])
        self.assertIn(
            'Output filename pattern: Marathon_{filename} (from run settings)',
            op_texts['6. Rename Output File'],
        )
        # Never mark unchanged literal fields as (from run settings).
        self.assertFalse(any('(from run settings)' in line for line in op_texts['3. Color Profile']))

        # Click Back -> title returns to Settings, queue statuses blank, values preserved, Reset enabled.
        dialog.open_settings_page()
        self.assertEqual(dialog.windowTitle(), 'KIMng - Run a Recipe - Settings')
        self.assertEqual(dialog.inputs.topLevelItem(0).text(1), '')
        self.assertEqual(dialog.inputs.topLevelItem(1).text(1), '')
        self.assertEqual(proj_w.text(), 'Marathon')
        self.assertTrue(dialog.settings_page.reset_button.isEnabled())

        # Click Reset to defaults -> restores defaults, neutral presentation, disables Reset & Review Changes.
        dialog.settings_page.reset_button.click()
        self.assertEqual(proj_w.text(), '')
        self.assertEqual(dialog.settings_page.form.field_error('project_name'), '')
        self.assertFalse(dialog.settings_page.reset_button.isEnabled())
        self.assertFalse(dialog.review_button.isEnabled())
        self.assertIsNone(dialog.approved_plan)

    def test_09_m4a_progress_completion_summary_and_open_output_dir(self):
        from kim_recipe_run import JobProgressDialog

        # 1. JobProgressDialog has right-aligned non-stretched Cancel button.
        prog = JobProgressDialog('Running recipe…', 'Cancel all', 0, 2)
        self.addCleanup(prog.deleteLater)
        prog.show()
        self.app.processEvents()
        self.assertLess(prog.cancel_button.width(), prog.width() // 2)

        # 2. Clean Recipe execution shows human-readable summary, collapses Technical details,
        #    and exposes Open output directory pointing to actual output directory.
        img1 = self.base / 'sample_m4a.jpg'
        make_test_jpeg(img1, width=1200, height=800)
        runner = RunRecipeDialog(core.builtins()[0], [str(img1)])
        self.addCleanup(runner.close)
        settle(runner)
        self.assertTrue(runner.run_button.isEnabled())
        runner.start_execution()
        deadline = time.monotonic() + 30.0
        while runner.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        for _ in range(5):
            self.app.processEvents()
        self.assertTrue(runner.execution_succeeded)
        self.assertEqual(runner.windowTitle(), 'KIMng - Run a Recipe - Results')
        self.assertEqual(runner.summary.text(), '1 image successfully processed.')
        self.assertFalse(runner.technical_details_button.isChecked())
        self.assertFalse(runner.diagnostics.isVisible())
        self.assertTrue(runner.open_output_button.isVisibleTo(runner))
        self.assertEqual(runner._selected_output_directory(), self.base / 'Web')
        self.assertIn('Elapsed time:', runner.diagnostics.toPlainText())

    def test_10_blocked_review_keeps_technical_details_collapsed_until_requested(self):
        # Preflight duplicate-output block must keep Technical details collapsed by default
        # so Recipe operations and Output properties stay visible, while preserving full diagnostics.
        img1 = self.base / 'dup_a.jpg'
        img2 = self.base / 'dup_b.jpg'
        make_test_jpeg(img1, width=320, height=200)
        make_test_jpeg(img2, width=320, height=200)

        dup_recipe = {
            'schema': 3,
            'id': 'user-dup-compact-test',
            'name': 'Duplicate Compact Test',
            'description': 'Forces duplicate output filename.',
            'media': 'image',
            'dolphin_shortcut': False,
            'steps': [
                {'op': 'image.convert', 'enabled': True, 'format': 'jpeg', 'quality': 90},
                {'op': 'file.rename_output', 'enabled': True, 'pattern': 'same_name'},
            ],
            'destination': {'mode': 'beside'},
        }
        runner = RunRecipeDialog(dup_recipe, [str(img1), str(img2)])
        self.addCleanup(runner.close)
        settle(runner)
        self.assertFalse(runner.run_button.isEnabled())
        self.assertEqual(runner.problem_count, 2)
        self.assertTrue(runner.blocking_summary.isVisibleTo(runner))
        self.assertIn('conflicting output filenames', runner.blocking_summary.text())
        self.assertTrue(runner.technical_details_button.isVisibleTo(runner))
        self.assertFalse(runner.technical_details_button.isChecked())
        self.assertFalse(runner.diagnostics.isVisibleTo(runner))
        self.assertTrue(bool(runner.diagnostics.toPlainText().strip()))

        # Calling editor_finished when no editor is active must not raise.
        runner.editor_finished(0)


if __name__ == '__main__':
    unittest.main()
