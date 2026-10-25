"""Date synchronization at the public kim_all dispatcher boundary."""
import os
from datetime import datetime
import shutil
import subprocess
import unittest
from support import Workspace


class DateSyncTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('exiftool') or not shutil.which('magick'):
            self.skipTest('ExifTool and ImageMagick are required')
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env['TZ'] = 'America/New_York'
        self.source = self.w.jpeg('input/photo 雪.jpg')
        self.w.env['KIM_POLICY'] = 'overwrite'
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2024:02:29 23:59:58',
                        '-SubSecTimeOriginal=123456789', str(self.source)],
                       check=True, capture_output=True)

    def tag(self, name, path=None):
        return subprocess.run([shutil.which('exiftool'), '-s3', name, str(path or self.source)],
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_exif_to_filesystem_uses_camera_wall_time_and_nanoseconds(self):
        os.utime(self.source, ns=(1_700_000_000_123_456_789, 1_700_000_001_987_654_321))
        before = self.w.observe(self.source)
        original_atime = self.source.stat().st_atime_ns
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:02:29 23:59:58', datetime.fromtimestamp(
            self.source.stat().st_mtime_ns / 1e9).strftime('%Y:%m:%d %H:%M:%S'))
        self.assertEqual(123456789, self.source.stat().st_mtime_ns % 1_000_000_000)
        self.assertEqual(original_atime, self.source.stat().st_atime_ns)
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)

    def test_exif_to_filesystem_create_mode_publishes_byte_identical_copy(self):
        self.w.env['KIM_POLICY'] = 'create'
        os.utime(self.source, ns=(1_700_000_000_123_456_789, 1_700_000_001_987_654_321))
        before = self.w.observe(self.source)
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.source.with_name('photo 雪_datesync.jpg')
        self.assertTrue(output.is_file())
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)
        self.assertEqual(before.mtime_ns, self.source.stat().st_mtime_ns)
        self.assertEqual(123456789, output.stat().st_mtime_ns % 1_000_000_000)

    def test_filesystem_to_exif_preserves_mtime_and_source_in_overwrite_mode(self):
        os.utime(self.source, ns=(1_710_000_000_000_000_001, 1_710_000_001_234_567_890))
        before = self.w.observe(self.source)
        pixels = subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
                                check=True, capture_output=True).stdout
        # The pixel probe above intentionally reads content; establish the
        # source atime baseline after test setup and that probe are complete.
        os.utime(self.source, ns=(1_710_000_000_000_000_001, 1_710_000_001_234_567_890))
        original_atime = self.source.stat().st_atime_ns
        result = self.w.dispatch('datesync', '--direction', 'file-to-exif', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(original_atime, self.source.stat().st_atime_ns)
        self.assertEqual('2024:03:09 11:00:01', self.tag('-DateTimeOriginal'))
        after_pixels = subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
                                       check=True, capture_output=True).stdout
        self.assertEqual(pixels, after_pixels)
        self.assertEqual(before.mtime_ns, self.source.stat().st_mtime_ns)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))

    def test_missing_capture_time_fails_without_changing_bytes_or_mtime(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', '-DateTimeOriginal=', str(self.source)],
                       check=True, capture_output=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)
        self.assertEqual(before.mtime_ns, self.source.stat().st_mtime_ns)

    def test_explicit_exif_offset_is_honored_and_matching_file_time_is_noop(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2024:01:01 01:00:00', '-OffsetTimeOriginal=+02:00',
                        str(self.source)], check=True, capture_output=True)
        first = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual('2023:12:31 18:00:00', datetime.fromtimestamp(
            self.source.stat().st_mtime_ns / 1e9).strftime('%Y:%m:%d %H:%M:%S'))
        mtime = self.source.stat().st_mtime_ns
        second = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(mtime, self.source.stat().st_mtime_ns)

    def test_filesystem_to_exif_create_mode_preserves_original_and_emits_copy(self):
        self.w.env['KIM_POLICY'] = 'create'
        os.utime(self.source, ns=(1_700_000_000_000_000_000, 1_710_000_001_234_567_890))
        before = self.w.observe(self.source)
        result = self.w.dispatch('datesync', '--direction', 'file-to-exif', '--fields', 'all',
                                 '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.source.with_name('photo 雪_datesync.jpg')
        self.assertTrue(output.is_file())
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)
        self.assertEqual('2024:03:09 11:00:01', self.tag('-DateTimeOriginal', output))
        self.assertEqual('2024:03:09 11:00:01', self.tag('-CreateDate', output))
        self.assertEqual('2024:03:09 11:00:01', self.tag('-ModifyDate', output))

    def test_file_to_exif_uses_existing_offset_without_changing_its_claim(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-OffsetTimeOriginal=+02:00', str(self.source)], check=True, capture_output=True)
        os.utime(self.source, ns=(1_710_000_000_000_000_000, 1_710_000_001_234_567_890))
        result = self.w.dispatch('datesync', '--direction', 'file-to-exif', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:03:09 18:00:01', self.tag('-DateTimeOriginal'))
        self.assertEqual('+02:00', self.tag('-OffsetTimeOriginal'))

    def test_all_fields_mode_updates_fields_even_if_capture_date_already_matches(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2024:03:09 11:00:01',
                        '-SubSecTimeOriginal=234567890',
                        '-CreateDate=', '-ModifyDate=', str(self.source)], check=True, capture_output=True)
        os.utime(self.source, ns=(1_710_000_000_000_000_000, 1_710_000_001_234_567_890))
        result = self.w.dispatch('datesync', '--direction', 'file-to-exif', '--fields', 'all', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:03:09 11:00:01', self.tag('-CreateDate'))
        self.assertEqual('2024:03:09 11:00:01', self.tag('-ModifyDate'))

    def test_nonexistent_dst_wall_time_is_rejected_without_touching_source(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2024:03:10 02:30:00', '-OffsetTimeOriginal=',
                        str(self.source)], check=True, capture_output=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)
        self.assertEqual(before.mtime_ns, self.source.stat().st_mtime_ns)

    def test_ambiguous_dst_wall_time_is_rejected_without_touching_source(self):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                        '-DateTimeOriginal=2024:11:03 01:30:00', '-OffsetTimeOriginal=',
                        str(self.source)], check=True, capture_output=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before.sha256, self.w.observe(self.source).sha256)
        self.assertEqual(before.mtime_ns, self.source.stat().st_mtime_ns)

    def test_duplicate_selection_is_processed_once(self):
        result = self.w.dispatch('datesync', '--direction', 'exif-to-file', '--',
                                 str(self.source), str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, len([c for c in result.calls if c['tool'] == 'qdbus' and c['argv'][2] == 'setLabelText']))
