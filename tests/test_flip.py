"""Flip review contracts and real derivative publication on owned images."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from metadata_integrity import sha256_noatime
from support import Workspace


def automate_flip_review(workspace, **options):
    """Click the real Qt review; keep planning, decoding and publication real."""
    workspace.subprocess_timeout = 45
    helper = workspace.control / 'kim_action_dialog.py'
    original = workspace.control / 'kim_action_dialog_real.py'
    if not original.exists():
        shutil.copyfile(helper, original)
    (workspace.control / 'flip-test-options.json').write_text(json.dumps(options))
    helper.write_text('''import json
from pathlib import Path
import sys
import kim_action_dialog_real as ui
root = Path(__file__).parent
options = json.loads((root / 'flip-test-options.json').read_text())
if sys.argv[1] == 'flip-output-review':
    execute = ui.FlipReviewDialog.exec
    def review(dialog):
        def click():
            if dialog.pending:
                ui.QTimer.singleShot(10, click)
                return
            if options.get('destination'):
                ui.QFileDialog.getExistingDirectory = lambda *args: options['destination']
                button = next(button for button in dialog.findChildren(ui.QPushButton)
                              if button.text() == 'Change Destination…')
                button.click()
            rows = [{'source': row['path'], 'target': row['target'],
                     'name': row['result_name'].text(),
                     'directory': row['result_directory'].text(),
                     'original_colour': row['original'].pixmap().toImage().pixelColor(0, 0).name()
                         if row['ready'] else None,
                     'result_colour': row['result'].pixmap().toImage().pixelColor(0, 0).name()
                         if row['ready'] else None}
                    for row in dialog.rows]
            (root / 'flip-reviewed.json').write_text(json.dumps(rows))
            if options.get('cancel') or not dialog.apply.isEnabled():
                dialog.reject()
                return
            if options.get('change_source'):
                Path(dialog.rows[0]['path']).write_bytes(b'changed after preview')
            dialog.apply.click()
            if dialog.isVisible():
                dialog.reject()
        ui.QTimer.singleShot(0, click)
        ui.QTimer.singleShot(5000, dialog.reject)
        return execute(dialog)
    ui.FlipReviewDialog.exec = review
result = ui.main()
if (sys.argv[1] == 'flip-source-read' and sys.argv[4] == 'magick'
        and options.get('late_collision') and result == 0):
    plan = json.loads(Path(sys.argv[2]).read_text())
    entry = next(entry for entry in plan['entries'] if entry['source'] == sys.argv[3])
    Path(entry['target']).write_bytes(b'late collision; preserve me')
sys.exit(result)
''')


def signature(path):
    info = path.stat()
    return (sha256_noatime(path), info.st_size, info.st_atime_ns,
            info.st_mtime_ns, info.st_ctime_ns)


class FlipPublicationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        # Real tools consume inherited stdin, with the usual safe filesystem
        # adapters retaining destination-local staging and atomic link checks.
        for tool in ('magick', 'identify', 'exiftool'):
            executable = shutil.which(tool)
            self.assertIsNotNone(executable)
            adapter = self.workspace.bin / tool
            adapter.unlink()
            adapter.symlink_to(executable)
        self.workspace.env['MAGICK_THREAD_LIMIT'] = '1'
        self.workspace.env['MAGICK_TEMPORARY_PATH'] = str(self.workspace.control / 'tmp')

    def exercise(self, operation, count=1, destination=None, prefix=False, collision=False):
        workspace = self.workspace
        sources = [workspace.png(f'{directory}/photo.part 雪.png')
                   for directory in ('first', 'second')[:count]]
        if prefix:
            settings = Path(workspace.env['XDG_CONFIG_HOME']) / 'kimng/settings.conf'
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text('KIM_NAME_AFFIX_POSITION=prefix\n'
                                'KIM_AFFIX_FLIPPED_HORIZONTAL=mirror\n'
                                'KIM_AFFIX_FLIPPED_VERTICAL=upside\n')
        tag = ('mirror' if operation == 'flop' else 'upside') if prefix else (
            'flipped_horizontal' if operation == 'flop' else 'flipped_vertical')
        filename = f'{tag}_photo.part 雪.png' if prefix else f'photo.part 雪_{tag}.png'
        if destination:
            destination = workspace.path(destination)
            destination.mkdir()
        protected = {}
        if collision:
            parent = destination or sources[0].parent
            for name in (filename, filename[:-4] + '_1.png'):
                occupied = parent / name
                occupied.write_bytes(b'existing output; preserve me')
                protected[occupied] = signature(occupied)
        automate_flip_review(workspace, destination=str(destination) if destination else None)
        before = {source: signature(source) for source in sources}
        result = workspace.dispatch('flipflop', operation, '--', *sources)
        self.assertEqual(0, result.returncode, result.stderr)
        reviewed = json.loads((workspace.control / 'flip-reviewed.json').read_text())
        self.assertEqual(count, len(reviewed))
        expected_names = []
        for index, source in enumerate(sources):
            number = index + 2 if destination and collision else 2 if index == 0 and collision else index if destination else 0
            expected = filename[:-4] + f'_{number}.png' if number else filename
            target = (destination or source.parent) / expected
            expected_names.append(str(target.relative_to(workspace.root)))
            row = reviewed[index]
            self.assertEqual(str(target), row['target'])
            self.assertEqual(target.name, row['name'])
            self.assertEqual(str(target.parent), row['directory'])
            self.assertEqual('#ff0000', row['original_colour'])
            self.assertEqual('#0000ff' if operation == 'flop' else '#ffff00', row['result_colour'])
            payload = workspace._read_without_atime(target)
            pixels = subprocess.run([shutil.which('magick'), '-', '-depth', '8', 'rgb:-'],
                                    input=payload, capture_output=True, check=True).stdout
            colours = [pixels[offset:offset + 3].hex() for offset in range(0, len(pixels), 3)]
            self.assertEqual(['0000ff', '00ff00', 'ff0000', '00ffff', 'ff00ff', 'ffff00']
                             if operation == 'flop' else
                             ['ffff00', 'ff00ff', '00ffff', 'ff0000', '00ff00', '0000ff'], colours)
            self.assertEqual(before[source], signature(source))
        self.assertEqual(set(expected_names), set(result.outputs))
        for path, original in protected.items():
            self.assertEqual(original, signature(path))
        self.assertFalse(list(workspace.root.rglob('.kimng-stage.*')))

    def test_horizontal_single_beside_source(self):
        self.exercise('flop')

    def test_vertical_multiple_beside_different_sources(self):
        self.exercise('flip', count=2)

    def test_horizontal_multiple_changed_destination_prefix_and_collisions(self):
        self.exercise('flop', count=2, destination='exports', prefix=True, collision=True)

    def test_vertical_single_configured_name_and_collision(self):
        self.exercise('flip', prefix=True, collision=True)

    def test_cancel_publishes_nothing_and_preserves_every_source_field(self):
        source = self.workspace.png('input/photo.png')
        before = signature(source)
        automate_flip_review(self.workspace, cancel=True)
        result = self.workspace.dispatch('flipflop', 'flop', source)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual({}, result.outputs)
        self.assertEqual(before, signature(source))

    def test_processing_cancel_stops_the_producer_before_cleanup(self):
        source = self.workspace.png('input/photo.png')
        before = signature(source)
        automate_flip_review(self.workspace)
        producer = self.workspace.bin / 'magick'
        producer.unlink()
        producer.write_text('#!' + sys.executable + '\n'
                            'import os, time\nfrom pathlib import Path\n'
                            'root = Path(os.environ["KIM_TEST_ROOT"]) / ".control"\n'
                            '(root / "producer.pid").write_text(str(os.getpid()))\n'
                            '(root / "progress-state").write_text("cancelled")\n'
                            'time.sleep(5)\n'
                            '(root / "producer.finished").write_text("not cancelled")\n')
        producer.chmod(0o700)
        result = self.workspace.dispatch('flipflop', 'flop', source)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual({}, result.outputs)
        self.assertFalse((self.workspace.control / 'producer.finished').exists())
        pid = int((self.workspace.control / 'producer.pid').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertEqual(before, signature(source))
        self.assertFalse(list(self.workspace.root.rglob('.kimng-stage.*')))

    def test_late_collision_is_preserved_without_renaming_output(self):
        source = self.workspace.png('input/photo.png')
        before = signature(source)
        automate_flip_review(self.workspace, late_collision=True)
        result = self.workspace.dispatch('flipflop', 'flip', source)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual({'input/photo_flipped_vertical.png': b'late collision; preserve me'}, result.outputs)
        self.assertEqual(before, signature(source))
        self.assertFalse(list(self.workspace.root.rglob('.kimng-stage.*')))

    def test_source_change_after_review_cannot_publish(self):
        source = self.workspace.png('input/photo.png')
        automate_flip_review(self.workspace, change_source=True)
        result = self.workspace.dispatch('flipflop', 'flop', source)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual({'input/photo.png': b'changed after preview'}, result.outputs)

    def test_originals_remain_unchanged_even_with_overwrite_preferences(self):
        self.workspace.approve_overwrite()
        self.exercise('flop')

    def test_jpeg_with_icc_preserves_sources_and_publishes_reviewed_name(self):
        from test_stripmeta import ICC_PROFILE
        source = self.workspace.jpeg('input/portrait 雪.jpg')
        profile = self.workspace.control / 'test.icc'
        profile.write_bytes(ICC_PROFILE)
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-ICC_Profile<=' + str(profile), str(source)], check=True, capture_output=True)
        before = signature(source)
        automate_flip_review(self.workspace)
        result = self.workspace.dispatch('flipflop', 'flop', source)
        self.assertEqual(0, result.returncode, result.stderr)
        target = source.with_name('portrait 雪_flipped_horizontal.jpg')
        reviewed = json.loads((self.workspace.control / 'flip-reviewed.json').read_text())
        self.assertEqual(str(target), reviewed[0]['target'])
        self.assertEqual(target.name, reviewed[0]['name'])
        actual = subprocess.run([shutil.which('exiftool'), '-b', '-ICC_Profile', str(target)],
                                check=True, capture_output=True).stdout
        self.assertEqual(ICC_PROFILE, actual)
        self.assertEqual(before, signature(source))

    def test_publication_on_workspace_filesystem_preserves_fresh_source(self):
        root = self.workspace.add_filesystem_root(Path.cwd()) / 'images'
        root.mkdir()
        fixture = self.workspace.png('input/fixture.png')
        source = root / 'fresh 雪.png'
        source.write_bytes(self.workspace._read_without_atime(fixture))
        before = signature(source)
        automate_flip_review(self.workspace)
        result = self.workspace.dispatch('flipflop', 'flip', source)
        self.assertEqual(0, result.returncode, result.stderr)
        target = root / 'fresh 雪_flipped_vertical.png'
        reviewed = json.loads((self.workspace.control / 'flip-reviewed.json').read_text())
        self.assertEqual(str(target), reviewed[0]['target'])
        self.assertEqual(target.name, reviewed[0]['name'])
        self.assertTrue(target.is_file())
        self.assertEqual({source, target}, set(root.iterdir()))
        self.assertEqual(before, signature(source))


class FlipReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
        import kim_action_dialog
        cls.ui = kim_action_dialog
        cls.app = cls.ui.QApplication.instance() or cls.ui.QApplication([])

    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.source = self.workspace.png('input/photo.png')
        self.inputs = self.workspace.control / 'flip.inputs'
        self.approved = self.workspace.control / 'approved.json'

    def test_malformed_requests_are_rejected_instead_of_suppressed(self):
        for payload, message in ((b'source\\0target\\0', 'Incomplete'),
                                 (b'source\0target', 'Incomplete'),
                                 (b'source\0', 'Invalid'), (b'\0target\0', 'Invalid')):
            with self.subTest(payload=payload):
                self.inputs.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, message):
                    self.ui.flip_output_review(self.inputs, self.approved, 'create', 'flop')
                self.assertFalse(self.approved.exists())

    def test_noatime_denial_fails_closed_without_delegating_a_read(self):
        from kim_preview import base_entry, finish_entry
        entry = base_entry(self.source)
        entry['atime_ns'] = self.source.stat().st_atime_ns
        finish_entry(entry, str(self.source.with_name('result.png')), 'create')
        plan = {'policy': 'create', 'config': {'flip': 'flop'}, 'entries': [entry]}
        self.approved.write_text(json.dumps(plan))
        before = signature(self.source)
        with patch('kim_preview.os.open', side_effect=PermissionError('fixture denial')), \
             patch('kim_process.run_process') as run:
            with self.assertRaisesRegex(ValueError, 'access time'):
                self.ui.flip_source_read(self.approved, str(self.source), ['identify', '-'])
        run.assert_not_called()
        self.assertEqual(before, signature(self.source))

    def test_destination_edits_invalidate_apply_until_a_valid_plan_is_reviewed(self):
        target = self.source.with_name('photo_flipped_horizontal.png')
        self.inputs.write_bytes(os.fsencode(self.source) + b'\0' + os.fsencode(target) + b'\0')
        before = signature(self.source)

        def review(window):
            self.assertFalse(window.apply.isEnabled())
            while window.pending:
                window.load_next()
            self.assertTrue(window.apply.isEnabled())
            choice = window.findChild(self.ui.QComboBox)
            directory = window.findChild(self.ui.QLineEdit)
            update = next(button for button in window.findChildren(self.ui.QPushButton)
                          if button.text() == 'Update preview')
            self.assertEqual('beside', choice.currentData())
            self.assertEqual(str(target), window.rows[0]['target'])
            choice.setCurrentIndex(choice.findData('shared'))
            self.assertFalse(window.apply.isEnabled())
            directory.setText(str(self.workspace.root / 'missing'))
            update.click()
            self.assertFalse(window.apply.isEnabled())
            directory.setText(str(self.source.parent))
            self.assertFalse(window.apply.isEnabled())
            update.click()
            self.assertTrue(window.apply.isEnabled())
            self.assertEqual(str(target), window.rows[0]['target'])
            choice.setCurrentIndex(choice.findData('beside'))
            self.assertTrue(window.apply.isEnabled())
            return self.ui.QDialog.Rejected

        with patch.object(self.ui.FlipReviewDialog, 'exec', review):
            self.assertEqual(130, self.ui.flip_output_review(self.inputs, self.approved, 'create', 'flop'))
        self.app.processEvents()
        self.assertFalse(self.approved.exists())
        self.assertFalse(target.exists())
        self.assertEqual(before, signature(self.source))


if __name__ == '__main__':
    unittest.main()
