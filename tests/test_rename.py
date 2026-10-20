"""Rename planning and filesystem publication through the dispatcher boundary."""
import os
import subprocess
import shutil
import unittest
import base64
from support import Workspace


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.jpeg('input/PHOTO 雪.JPG')
        self.w.env['KIM_POLICY'] = 'overwrite'

    def clean(self):
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertEqual(list((self.w.control / 'tmp').iterdir()), [])

    def test_preflight_refuses_dangling_destination_without_modifying_batch(self):
        second = self.w.jpeg('other/SECOND.JPG')
        occupied = self.w.path('other/second.JPG')
        occupied.symlink_to('missing')
        before = {p: self.w.observe(p) for p in (self.source, second, occupied)}
        result = self.w.dispatch('rename', 'lowercase', self.source, second)
        self.assertNotEqual(result.returncode, 0)
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state)
        self.assertEqual(result.outputs, {})
        self.clean()

    def test_move_uses_no_clobber_link_before_source_removal(self):
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', self.source)
        destination = self.source.with_name('photo 雪.JPG')
        self.assertFalse(self.source.exists())
        self.assertEqual(self.w.observe(destination).inode, before.inode)
        self.assertEqual(self.w.observe(destination).mtime_ns, before.mtime_ns)
        links = [c for c in result.calls if c['tool'] == 'ln']
        self.assertEqual(len(links), 1)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.clean()

    def test_sequential_custom_base_start_padding_and_extensions(self):
        second = self.w.png('other/next.png')
        self.w.respond_to('kdialog', '--inputbox', [
            {'stdout': 'Album_\n'}, {'stdout': '08\n'}, {'stdout': '4\n'}])
        result = self.w.dispatch('rename', 'sequential', self.source, second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.source.with_name('Album_0008.JPG').read_bytes(), self.w.jpeg('.control/ref.jpg').read_bytes())
        self.assertTrue(second.with_name('Album_0009.png').is_file())
        self.assertFalse(self.source.exists())
        self.assertFalse(second.exists())
        self.clean()

    def test_create_restores_mode_and_nanosecond_mtime_before_publication(self):
        self.w.env['KIM_POLICY'] = 'create'
        self.source.chmod(0o640)
        os.utime(self.source, ns=(1600000000000000000, 1600000001123456789))
        before = self.w.observe(self.source)
        self.w.respond('cp', output_base64=base64.b64encode(self.source.read_bytes()).decode())
        result = self.w.dispatch('rename', 'lowercase', self.source)
        output = self.source.with_name('photo 雪.JPG')
        self.assertEqual(self.w.observe(output).mtime_ns, before.mtime_ns, result.stderr)
        self.assertEqual(self.w.observe(output).mode, before.mode)
        self.assertEqual(self.w.observe(self.source), before)
        self.clean()

    def test_real_copy_preserves_extended_attributes(self):
        os.setxattr(self.source, b'user.kim6', b'fixture metadata')
        self.w.env['KIM_POLICY'] = 'create'
        self.w.use_real_rename_files()
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.assertEqual(os.getxattr(self.source.with_name('photo 雪.JPG'), b'user.kim6'),
                         b'fixture metadata', result.stderr)
        self.clean()

    def real(self):
        self.w.use_real_rename_files()
        self.w.use_real_metadata_tools()

    def failed(self, result, before):
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state, result.stderr)
        self.assertEqual(result.outputs, {})
        self.clean()

    def cross_destination(self):
        for parent in (self.w.production.parents[2], __import__('pathlib').Path('/dev/shm')):
            if parent.is_dir() and os.access(parent, os.W_OK) and parent.stat().st_dev != self.source.stat().st_dev:
                destination = self.w.add_filesystem_root(parent) / 'output'
                destination.mkdir()
                return destination
        self.skipTest('A second writable local filesystem is unavailable')

    def force_cross_device_branch(self):
        # Only device discovery is simulated: the copy, byte comparison,
        # metadata preparation, no-clobber publication and unlink use real files.
        self.w.respond_to('stat', '%d', [{'stdout': '1\n'}, {'stdout': '2\n'},
                                        {'passthrough': True}, {'passthrough': True}])

    def test_real_move_preserves_inode_metadata_and_bytes(self):
        self.real()
        os.utime(self.source, ns=(1600000000000000000, 1600000001123456789))
        self.source.chmod(0o604)
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.assertEqual(self.w.observe(self.source.with_name('photo 雪.JPG')), before, result.stderr)
        self.assertFalse(self.source.exists())
        self.clean()

    def test_real_create_is_independent_and_preserves_metadata(self):
        self.real()
        self.w.env['KIM_POLICY'] = 'create'
        os.utime(self.source, ns=(1600000000000000000, 1600000001987654321))
        self.source.chmod(0o640)
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', self.source)
        after = self.w.observe(self.source.with_name('photo 雪.JPG'))
        self.assertEqual(self.w.observe(self.source), before)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual((after.sha256, after.mode, after.mtime_ns), (before.sha256, before.mode, before.mtime_ns))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.clean()

    def test_cross_device_branch_copies_validates_then_removes_source(self):
        self.real()
        self.force_cross_device_branch()
        destination = self.w.path('out'); destination.mkdir()
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', destination, self.source)
        output = destination / 'photo 雪.JPG'
        after = self.w.observe(output)
        self.assertEqual((after.sha256, after.mode, after.mtime_ns), (before.sha256, before.mode, before.mtime_ns), result.stderr)
        self.assertNotEqual(after.inode, before.inode)
        self.assertFalse(self.source.exists())
        tools = [c['tool'] for c in result.calls]
        self.assertLess(tools.index('cp'), tools.index('cmp'))
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.clean()

    def test_source_unlink_failure_retains_both_names_and_reports_destination(self):
        self.real()
        before = self.w.observe(self.source)
        self.w.respond_to('rm', str(self.source), {'status': 13})
        result = self.w.dispatch('rename', 'lowercase', self.source)
        destination = self.source.with_name('photo 雪.JPG')
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(self.w.observe(destination), before)
        self.assertTrue(any('Destination retained:' in ' '.join(c['argv']) and str(destination) in ' '.join(c['argv'])
                            for c in result.calls if c['tool'] == 'kdialog'))
        self.clean()

    def test_cross_device_unlink_failure_retains_original_and_copy(self):
        self.real(); self.force_cross_device_branch()
        before = self.w.observe(self.source)
        self.w.respond_to('rm', str(self.source), {'status': 13})
        result = self.w.dispatch('rename', 'lowercase', self.source)
        output = self.source.with_name('photo 雪.JPG')
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(output.read_bytes(), self.source.read_bytes(), result.stderr)
        self.clean()

    def test_publication_race_never_replaces_newly_occupied_destination(self):
        self.real()
        before = self.w.observe(self.source)
        self.w.respond('ln', status=17, writes={'input/photo 雪.JPG': 'unselected concurrent entry'})
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(self.source.with_name('photo 雪.JPG').read_text(), 'unselected concurrent entry')
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()

    def test_copy_publication_failure_preserves_source_and_existing_entry(self):
        self.real(); self.w.env['KIM_POLICY'] = 'create'
        before = self.w.observe(self.source)
        self.w.respond('ln', status=17, writes={'input/photo 雪.JPG': 'occupied after planning'})
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(self.source.with_name('photo 雪.JPG').read_text(), 'occupied after planning')
        self.clean()

    def test_partial_copy_failure_cleans_only_owned_stage(self):
        self.real(); self.w.env['KIM_POLICY'] = 'create'
        before = self.w.observe(self.source)
        self.w.respond('cp', output_base64=base64.b64encode(b'partial').decode(), status=1)
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.failed(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'ln' for c in result.calls))

    def test_zero_exit_changed_copy_is_not_published(self):
        self.real(); self.force_cross_device_branch()
        before = self.w.observe(self.source)
        self.w.respond('cp', output_base64=base64.b64encode(b'wrong bytes').decode())
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.failed(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'ln' for c in result.calls))

    def test_timestamp_failure_does_not_publish(self):
        self.real(); self.w.env['KIM_POLICY'] = 'create'
        before = self.w.observe(self.source)
        self.w.respond('touch', status=1)
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.failed(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'ln' for c in result.calls))

    def test_mixed_directories_relative_paths_leading_dashes_and_unicode(self):
        second = self.w.jpeg('other/-SECOND 雪.JPG')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        self.real()
        result = self.w.dispatch('rename', 'lowercase', 'input/PHOTO 雪.JPG', 'other/-SECOND 雪.JPG')
        for source, name in ((self.source, 'photo 雪.JPG'), (second, '-second 雪.JPG')):
            self.assertEqual(self.w.observe(source.with_name(name)), before[source], result.stderr)
            self.assertFalse(source.exists())
        self.clean()

    def test_duplicate_basename_create_to_selected_directory_is_numbered(self):
        self.real(); self.w.env['KIM_POLICY'] = 'create'
        second = self.w.png('other/PHOTO 雪.JPG')
        destination = self.w.path('out'); destination.mkdir()
        before = {p: self.w.observe(p) for p in (self.source, second)}
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', destination, self.source, second)
        self.assertEqual((destination / 'photo 雪.JPG').read_bytes(), self.source.read_bytes(), result.stderr)
        self.assertEqual((destination / 'photo 雪_1.JPG').read_bytes(), second.read_bytes())
        for path, state in before.items(): self.assertEqual(self.w.observe(path), state)
        self.clean()

    def test_duplicate_move_targets_abort_complete_batch(self):
        second = self.w.png('other/PHOTO 雪.JPG')
        destination = self.w.path('out'); destination.mkdir()
        before = {p: self.w.observe(p) for p in (self.source, second)}
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', destination, self.source, second)
        self.assertNotEqual(result.returncode, 0)
        self.failed(result, before)
        self.assertFalse(any(c['tool'] in ('cp', 'ln', 'mv') for c in result.calls))

    def test_existing_selected_source_target_chain_is_rejected(self):
        second = self.w.png('input/photo 雪.JPG')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        result = self.w.dispatch('rename', 'lowercase', self.source, second)
        self.assertNotEqual(result.returncode, 0)
        self.failed(result, before)

    def test_hardlink_symlink_and_duplicate_selection_abort(self):
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', self.source, self.source)
        self.assertNotEqual(result.returncode, 0)
        self.failed(result, {self.source: before})
        alias = self.w.path('input/alias.JPG'); alias.symlink_to(self.source.name)
        before_all = {p: self.w.observe(p) for p in (self.source, alias)}
        result = self.w.dispatch('rename', 'lowercase', alias)
        self.assertNotEqual(result.returncode, 0); self.failed(result, before_all)
        alias.unlink(); os.link(self.source, alias)
        before_all = {p: self.w.observe(p) for p in (self.source, alias)}
        result = self.w.dispatch('rename', 'lowercase', self.source)
        self.assertNotEqual(result.returncode, 0); self.failed(result, before_all)

    def test_newline_in_selection_aborts_before_changing_any_file(self):
        second = self.w.jpeg('other/LINE\nBREAK.JPG')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        result = self.w.dispatch('rename', 'lowercase', self.source, second)
        self.assertNotEqual(result.returncode, 0); self.failed(result, before)

    def test_path_injection_from_dialog_is_rejected(self):
        before = self.w.observe(self.source)
        self.w.respond_to('kdialog', '--inputbox', {'stdout': '../escape/'})
        result = self.w.dispatch('rename', 'addprefix', self.source)
        self.assertNotEqual(result.returncode, 0); self.failed(result, {self.source: before})

    def test_destination_symlink_parent_resolves_safely(self):
        self.real()
        out = self.w.path('out'); out.mkdir()
        link = self.w.path('linked output'); link.symlink_to(out, target_is_directory=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', link, self.source)
        self.assertEqual(self.w.observe(out / 'photo 雪.JPG'), before, result.stderr)
        self.clean()

    def test_sequential_skips_occupied_numbers_and_preserves_existing_files(self):
        occupied = self.w.jpeg('input/wallpaper_001.JPG')
        dangling = self.w.path('input/wallpaper_002.JPG'); dangling.symlink_to('missing')
        before = {p: self.w.observe(p) for p in (occupied, dangling)}
        result = self.w.dispatch('rename', 'sequential', self.source)
        self.assertTrue(self.source.with_name('wallpaper_003.JPG').is_file(), result.stderr)
        for path, state in before.items(): self.assertEqual(self.w.observe(path), state)
        self.clean()

    def test_interactive_numbering_and_directory_chooser(self):
        self.w.respond_to('kdialog', 'Rename destination:', {'stdout': 'directory'})
        result = self.w.dispatch('rename', 'interactive', self.source)
        self.assertTrue(self.w.path('out/wallpaper_001.JPG').is_file(), result.stderr)
        self.clean()

    def test_literal_replacement_keeps_pattern_characters_and_ampersands_literal(self):
        source = self.w.jpeg('input/A[1]&.JPG')
        self.w.respond_to('kdialog', '--inputbox', [{'stdout': '[1]&'}, {'stdout': '&x'}])
        result = self.w.dispatch('rename', 'overwrite', source)
        self.assertTrue(source.with_name('A&x.JPG').is_file(), result.stderr)
        self.assertFalse(source.exists())
        self.clean()

    def test_actual_cross_filesystem_move_preserves_bytes_attributes_and_timestamps(self):
        self.real()
        destination = self.cross_destination()
        self.assertNotEqual(destination.stat().st_dev, self.source.stat().st_dev)
        self.source.chmod(0o640)
        os.utime(self.source, ns=(1600000000000000000, 1600000001123456789))
        os.setxattr(self.source, b'user.kim6', b'cross-device fixture')
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', destination, self.source)
        output = destination / 'photo 雪.JPG'
        after = self.w.observe(output)
        self.assertEqual((after.sha256, after.mode, after.mtime_ns), (before.sha256, before.mode, before.mtime_ns), result.stderr)
        self.assertEqual(os.getxattr(output, b'user.kim6'), b'cross-device fixture')
        self.assertFalse(self.source.exists())
        self.assertFalse(list(destination.glob('.kim6-stage.*')))
        self.clean()

    def test_actual_cross_filesystem_unlink_failure_retains_both(self):
        self.real()
        destination = self.cross_destination()
        self.assertNotEqual(destination.stat().st_dev, self.source.stat().st_dev)
        before = self.w.observe(self.source)
        self.w.respond_to('rm', str(self.source), {'status': 13})
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', destination, self.source)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual((destination / 'photo 雪.JPG').read_bytes(), self.source.read_bytes(), result.stderr)
        self.assertTrue(any('Destination retained:' in ' '.join(c['argv']) for c in result.calls))
        self.assertFalse(list(destination.glob('.kim6-stage.*')))
        self.clean()

    def test_real_exif_date_collisions_and_mixed_directory_sources(self):
        self.real()
        second = self.w.jpeg('other/SECOND.JPG')
        for source in (self.source, second):
            subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                            '-DateTimeOriginal=2020:03:14 15:09:26', str(source)],
                           check=True, capture_output=True)
        before = {p: self.w.observe(p) for p in (self.source, second)}
        destination = self.w.path('out'); destination.mkdir()
        occupied = self.w.path('out/20200314_150926.JPG'); occupied.write_bytes(b'keep')
        result = self.w.dispatch('rename', 'exifdate', '--output-dir', destination, self.source, second)
        self.assertEqual(occupied.read_bytes(), b'keep')
        for source, index in ((self.source, 1), (second, 2)):
            self.assertFalse(source.exists())
            self.assertEqual(self.w.observe(destination / f'20200314_150926_{index}.JPG'), before[source], result.stderr)
        self.clean()

    def test_missing_date_is_reported_without_moving_source_or_blocking_valid_item(self):
        self.real()
        dated = self.w.jpeg('other/DATED.JPG')
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', '-CreateDate=2021:04:05 06:07:08', str(dated)],
                       check=True, capture_output=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'exifdate', self.source, dated)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertTrue(dated.with_name('20210405_060708.JPG').exists(), result.stderr)
        self.assertTrue(any('Succeeded: 1' in ' '.join(c['argv']) and 'Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assertTrue(any(c['tool'] == 'qdbus' and c['argv'][2] == 'org.freedesktop.DBus.Properties.Set'
                            and c['argv'][-1] == '2' for c in result.calls))
        self.clean()

    def test_invalid_destination_is_reported_without_fallback(self):
        before = self.w.observe(self.source)
        result = self.w.dispatch('rename', 'lowercase', '--output-dir', self.w.path('missing'), self.source)
        self.assertNotEqual(result.returncode, 0)
        self.failed(result, {self.source: before})
        self.assertTrue(any(c['tool'] == 'kdialog' and '--error' in c['argv'] for c in result.calls))


def mode_case(mode, name, dialogs, expected):
    def test(self):
        source = self.w.jpeg('other/' + name)
        self.real()
        if dialogs:
            self.w.respond_to('kdialog', '--inputbox', [{'stdout': value} for value in dialogs])
        before = self.w.observe(source)
        result = self.w.dispatch('rename', mode, source)
        self.assertEqual(self.w.observe(source.with_name(expected)), before, result.stderr)
        if expected != name: self.assertFalse(source.exists())
        self.clean()
    return test


for mode, name, dialogs, expected in (
    ('uppercase', 'photo 雪.jpg', [], 'PHOTO 雪.jpg'),
    ('lowercase', ' .PHOTO 名.JPG', [], ' .photo 名.JPG'),
    ('spacestodash', 'One Two.png', [], 'One-Two.png'),
    ('dashestospace', 'One-Two.png', [], 'One Two.png'),
    ('addprefix', 'name.PNG', ['pre_'], 'pre_name.PNG'),
    ('addsuffix', 'name.PNG', ['_post'], 'name_post.PNG'),
    ('overwrite', 'old-old.PNG', ['old', 'new'], 'new-new.PNG'),
    ('lowercase', '.HIDDEN', [], '.hidden'),
    ('lowercase', 'PHOTO', [], 'photo'),
    ('lowercase', 'photo.JPG', [], 'photo.JPG'),
):
    setattr(RenameTests, 'test_mode_' + mode + '_' + name.replace(' ', '_'), mode_case(mode, name, dialogs, expected))


def date_case(preset, expected):
    def test(self):
        self.real()
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2020:03:14 15:09:26', str(self.source)], check=True, capture_output=True)
        before = self.w.observe(self.source)
        self.w.respond_to('kdialog', 'EXIF date rename pattern:', {'stdout': str(preset)})
        result = self.w.dispatch('rename', 'exifdate', self.source)
        self.assertEqual(self.w.observe(self.source.with_name(expected + '.JPG')), before, result.stderr)
        self.assertFalse(self.source.exists())
        self.clean()
    return test


for preset, expected in ((1, '20200314_150926'), (2, '2020-03-14_15-09-26'),
                         (3, '2020-14-03_15-09-26'), (4, 'IMG-20200314_150926')):
    setattr(RenameTests, 'test_real_date_format_' + str(preset), date_case(preset, expected))


def interruption_case(mode, phase, state):
    def test(self):
        self.real(); self.w.env['KIM_POLICY'] = mode
        second = self.w.jpeg('other/SECOND.JPG')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        if phase == 'before':
            self.w.respond_to('qdbus', 'wasCancelled', {'interrupt': state, 'status': 2})
        elif phase == 'publication':
            # Two preflight checks, begin-item, early item check, final gate.
            self.w.respond_to('qdbus', 'wasCancelled', [{'stdout': 'false\n'}] * 4 +
                [{'interrupt': state, 'stdout': 'unexpected\n'} if state == 'malformed' else {'interrupt': state, 'status': 2}])
        else:
            if phase == 'copy':
                self.w.respond('cp', interrupt=state, passthrough=True)
            else:
                self.w.sequence('touch', [{'passthrough': True}, {'passthrough': True},
                                          {'interrupt': state, 'passthrough': True}])
        result = self.w.dispatch('rename', 'lowercase', self.source, second)
        self.failed(result, before)
        self.assertFalse(any(c['tool'] == 'ln' for c in result.calls))
        self.assertLessEqual(len([c for c in result.calls if c['tool'] == 'cp']), 1)
        self.assertNotIn('could not close owned progress', result.stderr)
    return test


for mode, phase, state in (
    ('overwrite', 'before', 'cancelled'), ('create', 'before', 'gone'),
    ('create', 'copy', 'gone'), ('create', 'metadata', 'cancelled'),
    ('overwrite', 'publication', 'gone'), ('create', 'publication', 'query_failed'),
    ('overwrite', 'publication', 'owner_failed'), ('create', 'publication', 'malformed'),
):
    setattr(RenameTests, 'test_interruption_' + '_'.join((mode, phase, state)), interruption_case(mode, phase, state))


def test_actual_cross_filesystem_move_keeps_original_access_time(self):
    self.real()
    destination = self.cross_destination()
    access = 1500000000123456789
    modified = 1600000000123456789
    os.utime(self.source, ns=(access, modified))
    # Snapshots intentionally hash fixtures, updating atime. For this assertion
    # invoke the same public dispatcher without pre/post snapshot reads.
    result = subprocess.run([str(self.w.dispatcher), 'rename', 'lowercase', '--output-dir',
                             str(destination), str(self.source)], cwd=self.w.root, env=self.w.env,
                            capture_output=True, text=True, timeout=10)
    self.assertEqual(result.returncode, 0, result.stderr)
    info = (destination / 'photo 雪.JPG').stat()
    self.assertEqual(info.st_atime_ns, access)
    self.assertEqual(info.st_mtime_ns, modified)
    self.assertFalse(self.source.exists())
    self.assertFalse(list(destination.glob('.kim6-stage.*')))
    self.clean()


RenameTests.test_actual_cross_filesystem_move_keeps_original_access_time = test_actual_cross_filesystem_move_keeps_original_access_time


def test_stage_allocation_failure_preserves_source(self):
    self.w.env['KIM_POLICY'] = 'create'
    before = self.w.observe(self.source)
    self.w.respond_to('mktemp', str(self.source.parent / '.kim6-stage.XXXXXX'), {'status': 1})
    result = self.w.dispatch('rename', 'lowercase', self.source)
    self.failed(result, {self.source: before})
    self.assertFalse(any(c['tool'] == 'ln' for c in result.calls))


RenameTests.test_stage_allocation_failure_preserves_source = test_stage_allocation_failure_preserves_source


def test_source_change_after_preflight_is_not_moved(self):
    self.w.respond_to('qdbus', 'setLabelText', {'writes': {'input/PHOTO 雪.JPG': 'external source update'}})
    result = self.w.dispatch('rename', 'lowercase', self.source)
    self.assertEqual(self.source.read_text(), 'external source update')
    self.assertFalse(self.source.with_name('photo 雪.JPG').exists())
    self.assertFalse(any(c['tool'] in ('ln', 'cp') for c in result.calls))
    self.clean()


RenameTests.test_source_change_after_preflight_is_not_moved = test_source_change_after_preflight_is_not_moved


def test_source_replaced_after_publication_is_not_removed(self):
    self.w.respond('ln', writes={'input/PHOTO 雪.JPG': 'replacement source entry',
                                'input/photo 雪.JPG': 'already published bytes'})
    result = self.w.dispatch('rename', 'lowercase', self.source)
    self.assertEqual(self.source.read_text(), 'replacement source entry')
    self.assertEqual(self.source.with_name('photo 雪.JPG').read_text(), 'already published bytes')
    self.assertFalse(any(c['tool'] == 'rm' and c['argv'] == ['--', str(self.source)] for c in result.calls))
    self.assertTrue(any('Destination retained:' in ' '.join(c['argv']) for c in result.calls))
    self.clean()


RenameTests.test_source_replaced_after_publication_is_not_removed = test_source_replaced_after_publication_is_not_removed


def test_cancellation_after_publication_retains_both_and_stops_batch(self):
    self.real()
    second = self.w.jpeg('other/SECOND.JPG')
    before = {p: self.w.observe(p) for p in (self.source, second)}
    self.w.respond('ln', interrupt='gone', passthrough=True)
    result = self.w.dispatch('rename', 'lowercase', self.source, second)
    for path, state in before.items(): self.assertEqual(self.w.observe(path), state)
    self.assertEqual(self.source.with_name('photo 雪.JPG').read_bytes(), self.source.read_bytes())
    self.assertFalse(second.with_name('second.JPG').exists())
    self.assertEqual(len([c for c in result.calls if c['tool'] == 'ln']), 1)
    self.assertTrue(any('Destination retained:' in ' '.join(c['argv']) for c in result.calls))
    self.clean()


RenameTests.test_cancellation_after_publication_retains_both_and_stops_batch = test_cancellation_after_publication_retains_both_and_stops_batch


def test_cancellation_between_items_keeps_completed_move(self):
    self.real()
    second = self.w.jpeg('other/SECOND.JPG')
    before = self.w.observe(second)
    self.w.respond_to('qdbus', 'org.freedesktop.DBus.Properties.Set', [{}, {}, {'interrupt': 'gone'}])
    result = self.w.dispatch('rename', 'lowercase', self.source, second)
    self.assertFalse(self.source.exists())
    self.assertTrue(self.source.with_name('photo 雪.JPG').is_file())
    self.assertEqual(self.w.observe(second), before)
    self.assertFalse(second.with_name('second.JPG').exists())
    self.assertTrue(any('Succeeded: 1' in ' '.join(c['argv']) and 'Failed: 1' in ' '.join(c['argv']) for c in result.calls))
    self.clean()


RenameTests.test_cancellation_between_items_keeps_completed_move = test_cancellation_between_items_keeps_completed_move


def test_failed_move_does_not_undo_completed_items_or_block_later_items(self):
    self.real()
    second = self.w.jpeg('other/SECOND.JPG')
    self.w.respond_to('ln', str(self.source), {'status': 1})
    before = self.w.observe(self.source)
    result = self.w.dispatch('rename', 'lowercase', self.source, second)
    self.assertEqual(self.w.observe(self.source), before)
    self.assertFalse(second.exists())
    self.assertTrue(second.with_name('second.JPG').is_file())
    self.assertTrue(any('Succeeded: 1' in ' '.join(c['argv']) and 'Failed: 1' in ' '.join(c['argv']) for c in result.calls))
    self.clean()


RenameTests.test_failed_move_does_not_undo_completed_items_or_block_later_items = test_failed_move_does_not_undo_completed_items_or_block_later_items


def test_symlinked_parent_with_trailing_newline_is_rejected_without_path_confusion(self):
    physical = self.w.path('physical\n'); physical.mkdir()
    selected = physical / 'PHOTO.JPG'; selected.write_bytes(b'selected data')
    other = self.w.path('physical'); other.mkdir()
    unselected = other / 'PHOTO.JPG'; unselected.write_bytes(b'unselected data')
    alias = self.w.path('alias'); alias.symlink_to(physical, target_is_directory=True)
    before = {p: self.w.observe(p) for p in (selected, unselected)}
    result = self.w.dispatch('rename', 'lowercase', alias / selected.name)
    self.assertNotEqual(result.returncode, 0)
    self.failed(result, before)


RenameTests.test_symlinked_parent_with_trailing_newline_is_rejected_without_path_confusion = test_symlinked_parent_with_trailing_newline_is_rejected_without_path_confusion
