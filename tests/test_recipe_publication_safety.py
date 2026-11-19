"""Phase 1: reviewed recipe outputs stay exact and publish complete or not at all."""
import os
import copy
import errno
import json
import sys
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_recipes as base
import kim_recipe_core as core


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'image tools required')
class RecipePublicationSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kimng-phase1-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'photo.png'
        subprocess.run(['magick', '-size', '16x12', 'xc:red', str(self.source)],
                       check=True, capture_output=True)
        self.before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        self.recipe = base.recipe()
        self.output = self.root / 'photo_copy.png'

    def tearDown(self):
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), self.before)
        self.assertFalse(list(self.root.rglob('.kimng-stage.*')))

    def test_existing_output_blocks_review_without_numbering(self):
        self.output.write_bytes(b'occupied')
        row = core.preview(self.recipe, [self.source])[0]
        self.assertEqual(row.output, str(self.output))
        self.assertTrue(row.problems, 'Occupied exact output must block approval')
        result = core.execute(self.recipe, [self.source])[0]
        self.assertFalse(result['ok'])
        self.assertEqual(self.output.read_bytes(), b'occupied')
        self.assertFalse((self.root / 'photo_copy_1.png').exists())

    def approved(self, recipe=None, sources=None):
        recipe = recipe or self.recipe
        sources = sources or [self.source]
        return core.approve_rows(recipe, sources, core.preview(recipe, sources))

    def test_late_collision_blocks_without_replanning(self):
        approved = self.approved()
        self.output.write_bytes(b'racer')
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertIn('collision', result['error'])
        self.assertEqual(self.output.read_bytes(), b'racer')
        self.assertFalse((self.root / 'photo_copy_1.png').exists())

    def test_success_uses_immutable_reviewed_operations_and_output(self):
        rows = core.preview(self.recipe, [self.source])
        approved = core.approve_rows(self.recipe, [self.source], rows)
        with self.assertRaises(FrozenInstanceError): approved[0].output = 'changed'
        rows[0].output = str(self.root / 'changed.png')
        rows[0].properties.clear()
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['output'], str(self.output))
        self.assertEqual(self.output.read_bytes(), self.before[0])
        self.assertEqual(self.output.stat().st_mode & 0o111, 0)

    def test_edited_recipe_or_review_row_cannot_reuse_approval(self):
        rows = core.preview(self.recipe, [self.source])
        approved = core.approve_rows(self.recipe, [self.source], rows)
        changed = copy.deepcopy(self.recipe)
        changed['steps'][0]['pattern'] = '{stem}_other'
        result = core.execute(changed, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        rows[0].output = str(self.root / 'other.png')
        with self.assertRaises(core.RecipeError): core.approve_rows(self.recipe, [self.source], rows)
        self.assertFalse(self.output.exists())

    def test_changed_destination_cannot_reuse_approval(self):
        approved = self.approved()
        folder = self.root / 'changed'; folder.mkdir()
        changed = copy.deepcopy(self.recipe)
        changed['destination'] = {'mode': 'directory', 'ask': False, 'path': str(folder)}
        self.assertFalse(core.execute(changed, [self.source], approved_plan=approved)[0]['ok'])
        self.assertEqual(list(folder.iterdir()), [])

    def test_same_batch_duplicate_outputs_block_all_members(self):
        other = self.root / 'other'; other.mkdir()
        duplicate = other / self.source.name; duplicate.write_bytes(self.before[0])
        self.recipe['destination'] = {'mode': 'directory', 'ask': False, 'path': str(self.root)}
        sources = [self.source, duplicate]
        rows = core.preview(self.recipe, sources)
        self.assertTrue(all(row.problems for row in rows))
        self.assertEqual([row.output for row in rows], [str(self.output)] * 2)
        results = core.execute(self.recipe, sources)
        self.assertTrue(all(not r['ok'] for r in results))
        self.assertFalse(self.output.exists())

    def test_each_occupied_entry_type_blocks_without_touching_it(self):
        sentinel = self.root / 'sentinel'; sentinel.write_bytes(b'keep')
        for kind in ('symlink', 'dangling', 'hardlink', 'directory', 'fifo'):
            with self.subTest(kind=kind):
                if kind == 'symlink': self.output.symlink_to(sentinel)
                elif kind == 'dangling': self.output.symlink_to(self.root / 'missing')
                elif kind == 'hardlink': os.link(sentinel, self.output)
                elif kind == 'directory': self.output.mkdir()
                else: os.mkfifo(self.output)
                row = core.preview(self.recipe, [self.source])[0]
                self.assertTrue(row.problems)
                self.assertFalse(core.execute(self.recipe, [self.source])[0]['ok'])
                self.assertTrue(os.path.lexists(self.output))
                self.assertEqual(sentinel.read_bytes(), b'keep')
                if kind == 'directory': self.output.rmdir()
                else: self.output.unlink()

    def test_replaced_or_modified_source_since_review_blocks(self):
        approved = self.approved()
        replacement = self.root / 'replacement'; replacement.write_bytes(self.before[0])
        os.replace(replacement, self.source)
        self.assertFalse(core.execute(self.recipe, [self.source], approved_plan=approved)[0]['ok'])
        approved = self.approved()
        with self.source.open('ab') as stream: stream.write(b'external change')
        self.before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        self.assertFalse(core.execute(self.recipe, [self.source], approved_plan=approved)[0]['ok'])
        self.assertFalse(self.output.exists())

    def test_source_change_during_processing_blocks(self):
        approved = self.approved()
        from kim_recipe_image import ImageHandler
        verify = ImageHandler.verify
        def change(handler, output, state):
            verify(handler, output, state)
            with self.source.open('ab') as stream: stream.write(b'external change')
            self.before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        with patch.object(ImageHandler, 'verify', change):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertIn('Source changed', result['error'])
        self.assertFalse(self.output.exists())

    def test_destination_and_ancestor_replacement_since_review_block(self):
        for level in ('destination', 'ancestor'):
            with self.subTest(level=level):
                ancestor = self.root / level; ancestor.mkdir()
                destination = ancestor / 'out'; destination.mkdir()
                recipe = copy.deepcopy(self.recipe)
                recipe['destination'] = {'mode': 'directory', 'ask': False, 'path': str(destination)}
                approved = self.approved(recipe)
                moved = destination if level == 'destination' else ancestor
                moved.rename(moved.with_name(moved.name + '-old'))
                moved.mkdir()
                if level == 'ancestor': (moved / 'out').mkdir()
                result = core.execute(recipe, [self.source], approved_plan=approved)[0]
                self.assertFalse(result['ok'], result)
                self.assertEqual(list(destination.iterdir()), [])

    def test_missing_subfolder_is_bound_to_parent_and_created_once_for_batch(self):
        second = self.root / 'second.png'; second.write_bytes(self.before[0])
        self.recipe['destination'] = {'mode': 'subfolder', 'folder': 'new'}
        sources = [self.source, second]
        approved = self.approved(self.recipe, sources)
        self.assertFalse((self.root / 'new').exists())
        results = core.execute(self.recipe, sources, approved_plan=approved)
        self.assertTrue(all(r['ok'] for r in results), results)
        self.assertEqual({Path(r['output']).name for r in results}, {'photo_copy.png', 'second_copy.png'})

    def test_five_crop_images_to_new_shared_web_directory(self):
        from kim_image_ops import CROP_DEFAULTS
        sources = [self.source]
        for index in range(1, 5):
            source = self.root / f'photo{index}.png'
            source.write_bytes(self.before[0])
            sources.append(source)
        recipe = copy.deepcopy(self.recipe)
        recipe['steps'].insert(0, dict(op='image.crop', **{**CROP_DEFAULTS, 'aspect': '1:1'}))
        for name in ('Web', 'Existing'):
            with self.subTest(directory=name):
                directory = self.root / name
                if name == 'Existing': directory.mkdir()
                recipe['destination'] = {'mode': 'directory', 'ask': False, 'path': str(directory)}
                rows = core.preview(recipe, sources)
                self.assertEqual([row.problems for row in rows], [[]] * 5)
                approved = core.approve_rows(recipe, sources, rows)
                progress = []
                results = core.execute(recipe, sources, approved_plan=approved,
                                       progress=lambda result, index, total: progress.append((index, total, result['ok'])))
                self.assertEqual(progress, [(index, 5, True) for index in range(1, 6)])
                self.assertEqual([result['output'] for result in results], [row.output for row in rows])
                self.assertTrue(all(Path(result['output']).is_file() for result in results))

    def test_independently_created_subfolder_requires_new_review(self):
        self.recipe['destination'] = {'mode': 'subfolder', 'folder': 'new'}
        approved = self.approved()
        (self.root / 'new').mkdir()
        result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertEqual(list((self.root / 'new').iterdir()), [])

    def test_atomic_link_observes_only_a_complete_synced_stage(self):
        approved = self.approved()
        real_link, real_fsync = os.link, os.fsync
        synced = set()
        def fsync(fd):
            synced.add((os.fstat(fd).st_dev, os.fstat(fd).st_ino))
            return real_fsync(fd)
        def link(stage, name, **kwargs):
            stage = Path(stage)
            self.assertFalse(self.output.exists())
            self.assertEqual(stage.read_bytes(), self.before[0])
            self.assertTrue(stage.parent.name.startswith('.kimng-stage.'))
            self.assertEqual(stage.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(stage.parent.parent.stat().st_ino, self.root.stat().st_ino)
            self.assertIn((stage.stat().st_dev, stage.stat().st_ino), synced)
            real_link(stage, name, **kwargs)
            self.assertEqual(self.output.read_bytes(), self.before[0])
        with patch.object(core.os, 'link', side_effect=link), patch.object(core.os, 'fsync', side_effect=fsync):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)

    def test_racer_at_atomic_link_cannot_be_replaced(self):
        approved = self.approved()
        real_link = os.link
        def race(stage, name, **kwargs):
            self.output.write_bytes(b'last instant racer')
            return real_link(stage, name, **kwargs)
        with patch.object(core.os, 'link', side_effect=race):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertIn('collision', result['error'])
        self.assertEqual(self.output.read_bytes(), b'last instant racer')

    def test_unsupported_link_or_permission_error_fails_closed(self):
        approved = self.approved()
        for error in (errno.EOPNOTSUPP, errno.EXDEV, errno.ENOSYS, errno.EPERM, errno.EACCES):
            with self.subTest(errno=error), patch.object(core.os, 'link', side_effect=OSError(error, 'injected link failure')):
                result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
                self.assertFalse(result['ok'])
                if error != errno.EACCES: self.assertIn('Unsupported destination filesystem', result['error'])
                self.assertFalse(self.output.exists())
                self.assertFalse(list(self.root.rglob('.kimng-stage.*')))

    def test_failed_stage_sync_never_publishes(self):
        approved = self.approved()
        with patch.object(core.os, 'fsync', side_effect=OSError(errno.EIO, 'sync failed')):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())

    def test_post_publication_sync_failure_reports_published_output(self):
        approved = self.approved()
        real_sync = os.fsync
        def fsync(fd):
            if self.output.exists(): raise OSError(errno.EIO, 'post-link sync failure')
            return real_sync(fd)
        with patch.object(core.os, 'fsync', side_effect=fsync):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)
        self.assertIn('published', result['warning'])
        self.assertEqual(self.output.read_bytes(), self.before[0])

    def test_cancellation_after_render_cleans_stage_without_final_entry(self):
        from kim_process import inspection_context
        from kim_recipe_image import ImageHandler
        approved = self.approved()
        verify = ImageHandler.verify
        stopped = False
        def cancel(handler, output, state):
            nonlocal stopped
            verify(handler, output, state)
            stopped = True
        with inspection_context(cancelled=lambda: stopped), patch.object(ImageHandler, 'verify', cancel):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertTrue(result['cancelled'])
        self.assertFalse(self.output.exists())

    def test_earlier_batch_success_survives_late_collision_and_cancellation(self):
        from kim_process import inspection_context
        for mode in ('collision', 'cancel'):
            with self.subTest(mode=mode):
                second = self.root / 'second.png'; second.write_bytes(self.before[0])
                sources = [self.source, second]
                approved = self.approved(self.recipe, sources)
                stopped = False
                second_output = self.root / 'second_copy.png'
                def completed(result, index, total):
                    nonlocal stopped
                    if index == 1:
                        if mode == 'cancel': stopped = True
                        else: second_output.write_bytes(b'racer')
                with inspection_context(cancelled=lambda: stopped):
                    results = core.execute(self.recipe, sources, approved_plan=approved, progress=completed)
                self.assertTrue(results[0]['ok'])
                self.assertEqual(self.output.read_bytes(), self.before[0])
                if mode == 'collision':
                    self.assertEqual(len(results), 2)
                    self.assertFalse(results[1]['ok'])
                    self.assertEqual(second_output.read_bytes(), b'racer')
                    second_output.unlink()
                else:
                    self.assertEqual(len(results), 1)
                    self.assertFalse(second_output.exists())
                self.output.unlink()

    def test_cli_exact_output_success_and_collision_exit_status(self):
        path = self.root / 'recipe.json'; path.write_text(json.dumps(self.recipe))
        command = [sys.executable, '-B', str(base.ROOT / 'src/bin/kim_recipe_core.py'),
                   '--recipe', str(path), '--', str(self.source)]
        env = dict(os.environ, XDG_CONFIG_HOME=str(self.root / 'config'))
        first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)[0]['output'], str(self.output))
        second = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(second.returncode, 1, second.stderr)
        self.assertIn('collision', json.loads(second.stdout)[0]['error'])
        self.assertFalse((self.root / 'photo_copy_1.png').exists())

    def test_crop_and_logo_use_frozen_state_and_verified_reference_identity(self):
        from kim_image_ops import CROP_DEFAULTS, OVERLAY_DEFAULTS
        logo = self.root / 'logo.png'
        subprocess.run(['magick', '-size', '4x4', 'xc:blue', str(logo)], check=True, capture_output=True)
        crop = dict(op='image.crop', **CROP_DEFAULTS); crop['aspect'] = '1:1'
        overlay = dict(op='image.overlay', **OVERLAY_DEFAULTS)
        overlay.update(kind='image', logo=str(logo), size=25)
        self.recipe['steps'] = [crop, overlay, {'op': 'file.rename_output', 'pattern': '{stem}_copy'}]
        approved = self.approved()
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)
        dimensions = subprocess.check_output(['magick', 'identify', '-format', '%wx%h', str(self.output)])
        self.assertEqual(dimensions, b'12x12')
        self.output.unlink()
        approved = self.approved()
        subprocess.run(['magick', '-size', '4x4', 'xc:green', str(logo)], check=True, capture_output=True)
        result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertIn('Watermark image changed since planning', result['error'])
        self.assertFalse(self.output.exists())

    def test_reviewed_synthetic_psd_plan_executes_after_inspection_cleanup(self):
        source = self.root / 'layered.psd'
        subprocess.run(['magick', str(self.source), '-type', 'TrueColor', '-depth', '8', str(source)],
                       check=True, capture_output=True)
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        recipe = base.recipe([{'op': 'image.convert', 'format': 'png', 'quality': 90},
                              {'op': 'file.rename_output', 'pattern': '{stem}_copy'}])
        approved = self.approved(recipe, [source])
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            result = core.execute(recipe, [source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['output'], str(self.root / 'layered_copy.png'))
        self.assertEqual(subprocess.check_output(['magick', 'identify', '-format', '%wx%h', result['output']]), b'16x12')
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)

    def test_cleanup_failure_after_publication_preserves_success(self):
        approved = self.approved()
        actual = tempfile.TemporaryDirectory
        class FailedCleanup(actual):
            def __exit__(self, *args):
                super().__exit__(*args)
                raise OSError(errno.EIO, 'injected cleanup failure')
        with patch.object(core.tempfile, 'TemporaryDirectory', FailedCleanup):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertTrue(result['ok'], result)
        self.assertIn('cleanup failed', result['warning'])
        self.assertEqual(self.output.read_bytes(), self.before[0])

    def test_unsupported_directory_sync_fails_closed_with_diagnosis(self):
        import stat
        approved = self.approved()
        actual = os.fsync
        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(errno.EINVAL, 'directory sync unsupported')
            actual(fd)
        with patch.object(core.os, 'fsync', side_effect=fsync):
            result = core.execute(self.recipe, [self.source], approved_plan=approved)[0]
        self.assertFalse(result['ok'])
        self.assertIn('Unsupported destination filesystem', result['error'])
        self.assertFalse(self.output.exists())


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'image tools required')
class RecipePublicationGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    setUp = RecipePublicationSafety.setUp
    tearDown = RecipePublicationSafety.tearDown

    def wait(self, predicate):
        import time
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate(), 'Qt worker did not finish')

    def runner(self, sources=None):
        from kim_recipe_run import RunRecipeDialog
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.root / 'config')):
            dialog = RunRecipeDialog(self.recipe, list(map(str, sources or [self.source])))
        self.addCleanup(dialog.close)
        self.wait(lambda: dialog.preflight_worker is None)
        return dialog

    def crop(self, sources=None):
        from kim_crop_standalone import CropReview
        dialog = CropReview(self.recipe, list(map(str, sources or [self.source])))
        self.addCleanup(dialog.close)
        self.app.processEvents()
        self.wait(lambda: dialog.worker is None)
        return dialog

    def test_runner_blocks_all_duplicate_rows_before_apply(self):
        other = self.root / 'other'; other.mkdir()
        duplicate = other / self.source.name; duplicate.write_bytes(self.before[0])
        self.recipe['destination'] = {'mode': 'directory', 'ask': False, 'path': str(self.root)}
        dialog = self.runner([self.source, duplicate])
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertEqual(dialog.problem_count, 2)
        self.assertEqual(dialog.ready_count, 0)
        self.assertTrue(all(row.problems for row in dialog.rows.values()))

    def test_runner_late_collision_uses_the_reviewed_plan(self):
        dialog = self.runner()
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertEqual(dialog.approved_plan[0].output, str(self.output))
        self.output.write_bytes(b'racer')
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            dialog.start_execution()
            self.wait(lambda: dialog.worker is None)
        self.assertEqual(len(dialog.results), 1)
        self.assertFalse(dialog.results[0]['ok'])
        self.assertIn('collision', dialog.diagnostics.toPlainText())
        self.assertEqual(self.output.read_bytes(), b'racer')

    def test_runner_destination_change_invalidates_old_approval(self):
        dialog = self.runner()
        old = dialog.approved_plan
        folder = self.root / 'chosen'; folder.mkdir()
        dialog.recipe['destination'] = {'mode': 'directory', 'ask': True}
        dialog.execution_recipe['destination'] = {'mode': 'directory', 'ask': True}
        dialog.chosen = str(folder)
        dialog.start_preflight()
        self.assertFalse(dialog.run_button.isEnabled())
        self.assertIsNone(dialog.approved_plan)
        self.wait(lambda: dialog.preflight_worker is None)
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertNotEqual(old[0].output, dialog.approved_plan[0].output)
        self.assertEqual(dialog.approved_plan[0].output, str(folder / self.output.name))

    def test_crop_late_collision_executes_its_exact_approved_output(self):
        from kim_crop_standalone import CropExecution
        dialog = self.crop()
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(dialog.table.item(0, 3).text(), self.output.name)
        dialog.approve()
        self.assertEqual(dialog.approved_plan[0].output, str(self.output))
        self.output.write_bytes(b'crop racer')
        worker = CropExecution(dialog.approved, [str(self.source)], dialog.approved_plan)
        with patch('kim_recipe_image.ImageHandler.plan', side_effect=AssertionError('replanned')):
            worker.run()
        self.assertFalse(worker.error, worker.error)
        self.assertFalse(worker.results[0]['ok'])
        self.assertEqual(self.output.read_bytes(), b'crop racer')
        self.assertFalse((self.root / 'photo_copy_1.png').exists())

    def test_crop_numbers_existing_and_duplicate_targets(self):
        self.output.write_bytes(b'occupied')
        dialog = self.crop()
        self.assertTrue(dialog.apply_button.isEnabled(), dialog.status.text())
        numbered = self.output.with_name(
            self.output.stem + '_1' + self.output.suffix
        )
        self.assertEqual(dialog.review_rows[0].output, str(numbered))
        self.assertEqual(dialog.review_rows[0].approved.output, str(numbered))
        self.assertEqual(self.output.read_bytes(), b'occupied')
        self.assertFalse(numbered.exists())

        dialog.close()
        self.output.unlink()

        other = self.root / 'other'
        other.mkdir()
        duplicate = other / self.source.name
        duplicate.write_bytes(self.before[0])

        self.recipe['destination'] = {
            'mode': 'directory',
            'ask': False,
            'path': str(self.root),
        }
        dialog = self.crop([self.source, duplicate])

        self.assertTrue(dialog.apply_button.isEnabled(), dialog.status.text())
        outputs = [row.output for row in dialog.review_rows]
        self.assertEqual(len(outputs), 2)
        self.assertEqual(len(set(outputs)), 2)
        self.assertTrue(all(not row.problems for row in dialog.review_rows))
        self.assertTrue(all(
            row.approved.output == row.output for row in dialog.review_rows
        ))
        self.assertTrue(all(not Path(path).exists() for path in outputs))

    def test_crop_numbered_output_late_collision_never_renumbers(self):
        from kim_crop_standalone import CropExecution

        self.output.write_bytes(b'occupied')
        dialog = self.crop()
        self.assertTrue(dialog.apply_button.isEnabled(), dialog.status.text())

        numbered = self.output.with_name(
            self.output.stem + '_1' + self.output.suffix
        )
        self.assertEqual(dialog.review_rows[0].output, str(numbered))

        dialog.approve()
        self.assertEqual(dialog.approved_plan[0].output, str(numbered))

        numbered.write_bytes(b'late collision')

        worker = CropExecution(
            dialog.approved,
            [str(self.source)],
            approved_plan=dialog.approved_plan,
        )
        worker.run()

        self.assertFalse(worker.error, worker.error)
        self.assertTrue(worker.results)
        self.assertFalse(worker.results[0]['ok'])
        self.assertIn('collision', worker.results[0]['error'].lower())

        self.assertEqual(self.output.read_bytes(), b'occupied')
        self.assertEqual(numbered.read_bytes(), b'late collision')
        self.assertFalse(
            self.output.with_name(
                self.output.stem + '_2' + self.output.suffix
            ).exists()
        )
        self.assertEqual(self.source.read_bytes(), self.before[0])

    def test_gui_workers_require_the_review_snapshot(self):
        from kim_recipe_run import RecipeWorker
        from kim_crop_standalone import CropExecution
        for cls in (RecipeWorker, CropExecution):
            worker = cls(self.recipe, [str(self.source)])
            worker.run()
            self.assertIn('Missing approved publication plan', worker.error)
            self.assertFalse(self.output.exists())
