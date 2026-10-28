"""Focused tests for metadata-only photographer workflows."""
import json
import os
import shutil
import subprocess
import unittest

from support import Workspace
from test_stripmeta import ICC_PROFILE


class MetadataActionTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('exiftool') or not shutil.which('magick'):
            self.skipTest('ExifTool and ImageMagick are required for metadata fixtures')
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.jpeg('input/photo 雪.jpg')
        self.w.approve_overwrite()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()

    def tag(self, name):
        result = subprocess.run([shutil.which('exiftool'), '-s3', name, str(self.source)],
                                check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def set_tags(self, *args):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', *args,
                        str(self.source)], check=True, capture_output=True)

    def assert_clean(self):
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))

    def test_gps_mode_removes_coordinates_and_preserves_unrelated_metadata(self):
        self.set_tags('-GPSLatitude=42', '-GPSLongitude=3', '-DateTimeOriginal=2024:02:29 23:45:00',
                      '-Artist=Photographer', '-Copyright=Rights', '-XMP-dc:Title=Caption')
        before_pixels = self.w.image_info(self.source)
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', self.tag('-GPSLatitude'))
        self.assertEqual('', self.tag('-GPSLongitude'))
        self.assertEqual('2024:02:29 23:45:00', self.tag('-DateTimeOriginal'))
        self.assertEqual('Photographer', self.tag('-Artist'))
        self.assertEqual('Rights', self.tag('-Copyright'))
        self.assertEqual('Caption', self.tag('-XMP-dc:Title'))
        self.assertEqual(before_pixels, self.w.image_info(self.source))
        self.assert_clean()

    def test_gps_mode_removes_xmp_and_iptc_extension_coordinates(self):
        self.set_tags('-XMP-exif:GPSLatitude=42.5', '-XMP:GPSLongitude=3.25',
                      '-XMP-iptcExt:LocationShownGPSLatitude=42.5',
                      '-XMP-iptcExt:LocationShownGPSLongitude=3.25',
                      '-XMP-iptcExt:RatingRegionGPSLatitude=42.5',
                      '-XMP-iptcExt:RatingRegionGPSLongitude=3.25',
                      '-XMP-iptcExt:LocationShownCity=Example City',
                      '-XMP-dc:Description=Keep this caption')
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        for tag in ('-XMP-exif:GPSLatitude', '-XMP:GPSLongitude',
                    '-XMP-iptcExt:LocationShownGPSLatitude',
                    '-XMP-iptcExt:LocationShownGPSLongitude',
                    '-XMP-iptcExt:RatingRegionGPSLatitude',
                    '-XMP-iptcExt:RatingRegionGPSLongitude'):
            self.assertEqual('', self.tag(tag), tag)
        self.assertEqual('Example City', self.tag('-XMP-iptcExt:LocationShownCity'))
        self.assertEqual('Keep this caption', self.tag('-XMP-dc:Description'))

    def test_metadata_edit_preserves_pixels_icc_permissions_and_nanosecond_mtime(self):
        profile = self.w.path('.control/photo.icc')
        profile.write_bytes(ICC_PROFILE)
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', '-GPSLatitude=42',
                        '-ICC_Profile<=' + str(profile), str(self.source)], check=True, capture_output=True)
        self.source.chmod(0o640)
        os.utime(self.source, ns=(1_600_000_000_000_000_000, 1_600_000_001_234_567_891))
        before_pixels = subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
                                       check=True, capture_output=True).stdout
        before_profile = subprocess.run([shutil.which('exiftool'), '-b', '-ICC_Profile', str(self.source)],
                                        check=True, capture_output=True).stdout
        self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertEqual(before_pixels, subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
                                                        check=True, capture_output=True).stdout)
        self.assertEqual(before_profile, subprocess.run([shutil.which('exiftool'), '-b', '-ICC_Profile', str(self.source)],
                                                         check=True, capture_output=True).stdout)
        self.assertEqual(0o640, self.source.stat().st_mode & 0o777)
        self.assertEqual(1_600_000_001_234_567_891, self.source.stat().st_mtime_ns)

    def test_metadata_edits_support_tiff_and_reject_raw_extensions(self):
        tiff = self.w.path('input/landscape.tiff')
        subprocess.run([shutil.which('magick'), str(self.source), str(tiff)], check=True, capture_output=True)
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', '-GPSLatitude=42', str(tiff)],
                       check=True, capture_output=True)
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(tiff))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', self.tag_at(tiff, '-GPSLatitude'))
        raw = self.w.path('input/reference.dng')
        raw.write_bytes(self.source.read_bytes())
        before = self.w.observe(raw)
        result = self.w.dispatch('copyright', '--creator', 'Name', '--', str(raw))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(raw))

    def test_copyright_config_defaults_and_environment_precedence(self):
        self.w.configure('COPYRIGHT_CREATOR', 'Config Creator')
        self.w.env['KIM_COPYRIGHT_CREATOR'] = 'Environment Creator'
        result = self.w.dispatch('copyright', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('Environment Creator', self.tag('-Artist'))

    def test_interactive_copyright_prompts_three_independent_fields(self):
        self.w.sequence('kdialog', [
            {'stdout': 'Interactive creator'}, {'stdout': 'Interactive notice'},
            {'stdout': ''}, {'stdout': 'org.kde.kdialog-test /ProgressDialog'}])
        result = self.w.dispatch('copyright', '--interactive', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('Interactive creator', self.tag('-Artist'))
        self.assertEqual('Interactive notice', self.tag('-Copyright'))
        self.assertEqual('', self.tag('-XMP-xmpRights:UsageTerms'))
        self.assertEqual(3, len([c for c in result.calls if c['tool'] == 'kdialog' and '--inputbox' in c['argv']]))

    def test_missing_exiftool_fails_closed(self):
        before = self.w.observe(self.source)
        (self.w.bin / 'exiftool').unlink()
        result = self.w.dispatch('timeshift', '--offset', '+01:00:00', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))

    def test_copyright_updates_only_selected_nonempty_fields(self):
        self.set_tags('-GPSLatitude=42', '-Artist=Old creator', '-Copyright=Old rights',
                      '-DateTimeOriginal=2021:02:03 04:05:06')
        result = self.w.dispatch('copyright', '--creator', 'Example Photographer', '--notice',
                                 'Copyright © {YEAR} Example Photographer', '--usage-rights',
                                 'Licensed for editorial use', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('Example Photographer', self.tag('-Artist'))
        self.assertEqual('Example Photographer', self.tag('-IPTC:By-line'))
        self.assertEqual('Example Photographer', self.tag('-XMP-dc:Creator'))
        self.assertEqual('Copyright © 2021 Example Photographer', self.tag('-Copyright'))
        self.assertEqual('Copyright © 2021 Example Photographer', self.tag('-IPTC:CopyrightNotice'))
        self.assertEqual('Copyright © 2021 Example Photographer', self.tag('-XMP-dc:Rights'))
        self.assertEqual('Licensed for editorial use', self.tag('-XMP-xmpRights:UsageTerms'))
        self.assertEqual('42 deg 0\' 0.00"', self.tag('-GPSLatitude'))
        self.assert_clean()

    def test_timeshift_updates_capture_fields_without_filesystem_time_change(self):
        self.set_tags('-DateTimeOriginal=2024:02:28 23:30:00', '-CreateDate=2024:02:28 23:30:00',
                      '-ModifyDate=2024:02:28 23:30:00', '-GPSDateStamp=2024:02:28')
        os.utime(self.source, ns=(1_600_000_000_000_000_001, 1_600_000_001_123_456_789))
        mtime = self.source.stat().st_mtime_ns
        result = self.w.dispatch('timeshift', '--offset', '+00:30:00', '--fields', 'all', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:02:29 00:00:00', self.tag('-DateTimeOriginal'))
        self.assertEqual('2024:02:29 00:00:00', self.tag('-CreateDate'))
        self.assertEqual('2024:02:29 00:00:00', self.tag('-ModifyDate'))
        self.assertEqual('2024:02:28', self.tag('-GPSDateStamp'))
        self.assertEqual(mtime, self.source.stat().st_mtime_ns)
        self.assert_clean()

    def test_ai_system_tags_removed_without_erasing_other_metadata(self):
        version = subprocess.run(
            [shutil.which('exiftool'), '-ver'], check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        parts = version.split('.')
        if (int(parts[0]), int(parts[1])) < (13, 40):
            self.skipTest('ExifTool 13.40+ required for IPTC AI system tags')

        self.set_tags(
            '-XMP-iptcExt:AISystemUsed=Example Model',
            '-XMP-iptcExt:AISystemVersionUsed=1.2',
            '-XMP-iptcExt:DigitalSourceType=negativeFilm',
            '-Artist=Photographer',
            '-GPSLatitude=42',
        )
        before = self.w.image_info(self.source)

        result = self.w.dispatch(
            'stripmeta', '--mode', 'ai', '--', str(self.source)
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', self.tag('-XMP-iptcExt:AISystemUsed'))
        self.assertEqual('', self.tag('-XMP-iptcExt:AISystemVersionUsed'))
        self.assertEqual(
            'negativeFilm',
            self.tag('-XMP-iptcExt:DigitalSourceType'),
        )
        self.assertEqual('Photographer', self.tag('-Artist'))
        self.assertTrue(self.tag('-GPSLatitude'))
        self.assertEqual(before, self.w.image_info(self.source))
        self.assert_clean()

    def test_gps_extended_iptc_coordinates_preserve_location_text(self):
        self.set_tags(
            '-XMP-iptcExt:LocationCreatedGPSLatitude=42.5',
            '-XMP-iptcExt:LocationCreatedGPSLongitude=3.25',
            '-XMP-iptcExt:LocationShownGPSAltitude=200',
            '-XMP-iptcExt:LocationCreatedCity=Example City',
            '-Artist=Photographer',
        )

        result = self.w.dispatch(
            'stripmeta', '--mode', 'gps', '--', str(self.source)
        )

        self.assertEqual(0, result.returncode, result.stderr)
        for tag in (
            '-XMP-iptcExt:LocationCreatedGPSLatitude',
            '-XMP-iptcExt:LocationCreatedGPSLongitude',
            '-XMP-iptcExt:LocationShownGPSAltitude',
        ):
            self.assertEqual('', self.tag(tag), tag)

        self.assertEqual(
            'Example City',
            self.tag('-XMP-iptcExt:LocationCreatedCity'),
        )
        self.assertEqual('Photographer', self.tag('-Artist'))
        self.assert_clean()

    def test_ai_only_removal_does_not_remove_copyright_or_gps(self):
        self.set_tags('-XMP-iptcExt:DigitalSourceType=trainedAlgorithmicMedia',
                      '-XMP-iptcExt:AIPromptInformation=synthetic prompt',
                      '-XMP-iptcExt:AIPromptWriterName=ExampleGenAI',
                      '-Artist=Photographer', '-GPSLatitude=42')
        self.assertEqual('trainedAlgorithmicMedia', self.tag('-XMP-iptcExt:DigitalSourceType'))
        self.assertEqual('synthetic prompt', self.tag('-XMP-iptcExt:AIPromptInformation'))
        result = self.w.dispatch('stripmeta', '--mode', 'ai', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', self.tag('-XMP-iptcExt:DigitalSourceType'))
        self.assertEqual('', self.tag('-XMP-iptcExt:AIPromptInformation'))
        self.assertEqual('', self.tag('-XMP-iptcExt:AIPromptWriterName'))
        self.assertEqual('Photographer', self.tag('-Artist'))
        self.assertNotEqual('', self.tag('-GPSLatitude'))
        self.assert_clean()

    def test_ai_mode_keeps_non_ai_digital_source_type_and_generic_software(self):
        self.set_tags('-XMP-iptcExt:DigitalSourceType=negativeFilm',
                      '-XMP-iptcExt:AIPromptInformation=synthetic prompt',
                      '-XMP:CreatorTool=Ordinary image editor')
        result = self.w.dispatch('stripmeta', '--mode', 'ai', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('negativeFilm', self.tag('-XMP-iptcExt:DigitalSourceType'))
        self.assertEqual('Ordinary image editor', self.tag('-XMP:CreatorTool'))
        self.assertEqual('', self.tag('-XMP-iptcExt:AIPromptInformation'))

    def test_gps_plus_ai_removes_both_without_touching_rights(self):
        self.set_tags('-GPSLatitude=42', '-XMP-iptcExt:DigitalSourceType=trainedAlgorithmicMedia',
                      '-XMP-iptcExt:AIPromptInformation=synthetic prompt', '-Copyright=Photographer rights')
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--remove-ai', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('', self.tag('-GPSLatitude'))
        self.assertEqual('', self.tag('-XMP-iptcExt:DigitalSourceType'))
        self.assertEqual('', self.tag('-XMP-iptcExt:AIPromptInformation'))
        self.assertEqual('Photographer rights', self.tag('-Copyright'))

    def test_timestamp_capture_only_preserves_subseconds_and_timezone_tags(self):
        self.set_tags('-DateTimeOriginal=2024:03:10 01:30:00', '-CreateDate=2024:03:10 01:30:00',
                      '-ModifyDate=2024:03:10 01:30:00', '-SubSecTimeOriginal=123',
                      '-OffsetTimeOriginal=-05:00', '-GPSDateStamp=2024:03:10')
        before_create = self.tag('-CreateDate')
        before_modify = self.tag('-ModifyDate')
        result = self.w.dispatch('timeshift', '--offset', '-01:00:00', '--fields', 'capture',
                                 '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:03:10 00:30:00', self.tag('-DateTimeOriginal'))
        self.assertEqual(before_create, self.tag('-CreateDate'))
        self.assertEqual(before_modify, self.tag('-ModifyDate'))
        self.assertEqual('123', self.tag('-SubSecTimeOriginal'))
        self.assertEqual('-05:00', self.tag('-OffsetTimeOriginal'))
        self.assertEqual('2024:03:10', self.tag('-GPSDateStamp'))

    def test_interactive_timeshift_shows_exiftool_before_after_preview(self):
        self.set_tags('-DateTimeOriginal=2024:01:31 23:45:00', '-CreateDate=2024:01:31 23:45:00',
                      '-ModifyDate=2024:01:31 23:45:00')
        self.w.sequence('kdialog', [
            {'stdout': '+00:30:00'}, {'stdout': 'all'}, {'status': 0},
            {'stdout': 'org.kde.kdialog-test /ProgressDialog'}])
        result = self.w.dispatch('timeshift', '--interactive', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:02:01 00:15:00', self.tag('-DateTimeOriginal'))
        preview = next(c for c in result.calls if c['tool'] == 'kdialog' and '--yesno' in c['argv'])
        self.assertIn('2024:01:31 23:45:00', preview['argv'][-1])
        self.assertIn('2024:02:01 00:15:00', preview['argv'][-1])

    def test_create_mode_preserves_source_and_uses_numbered_derived_file(self):
        self.set_tags('-GPSLatitude=42', '-Artist=Original')
        self.w.env['KIM_POLICY'] = 'create'
        target = self.source.with_name('photo 雪_gps.jpg')
        target.write_bytes(b'occupied')
        before = self.w.observe(self.source)
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(b'occupied', target.read_bytes())
        output = self.source.with_name('photo 雪_gps-1.jpg')
        self.assertTrue(output.is_file())
        self.assertEqual('', self.tag_at(output, '-GPSLatitude'))

    def test_copyright_create_mode_preserves_source_and_numbers_collisions(self):
        self.set_tags('-Artist=Original')
        self.w.env['KIM_POLICY'] = 'create'
        occupied = self.source.with_name('photo 雪_copyright.jpg')
        occupied.write_bytes(b'user-owned')
        before = self.w.observe(self.source)
        result = self.w.dispatch('copyright', '--creator', 'New Creator', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.w.observe(self.source))
        self.assertEqual(b'user-owned', occupied.read_bytes())
        output = self.source.with_name('photo 雪_copyright-1.jpg')
        self.assertTrue(output.is_file())
        self.assertEqual('New Creator', self.tag_at(output, '-Artist'))

    def test_publication_failure_preserves_overwrite_source(self):
        self.set_tags('-GPSLatitude=42', '-Artist=Original')
        before = self.w.observe(self.source)
        self.w.metadata_fault(metadata_publication_fail=True)
        result = self.w.dispatch('copyright', '--creator', 'Changed', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))
        self.assertEqual('Original', self.tag('-Artist'))
        self.assert_clean()

    def tag_at(self, path, name):
        result = subprocess.run([shutil.which('exiftool'), '-s3', name, str(path)],
                                check=True, capture_output=True, text=True)
        return result.stdout.strip()

    def test_invalid_timestamp_offset_fails_before_metadata_edit(self):
        result = self.w.dispatch('timeshift', '--offset', '+01:60:00', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in result.calls))

    def test_metadata_noops_do_not_publish_a_file(self):
        gps = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertEqual(0, gps.returncode, gps.stderr)
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in gps.calls))
        self.set_tags('-Artist=Unchanged', '-IPTC:By-line=Unchanged', '-XMP-dc:Creator=Unchanged')
        copyright = self.w.dispatch('copyright', '--creator', 'Unchanged', '--', str(self.source))
        self.assertEqual(0, copyright.returncode, copyright.stderr)
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in copyright.calls))
        missing_time = self.w.dispatch('timeshift', '--offset', '+01:00:00', '--fields', 'all',
                                       '--', str(self.source))
        self.assertEqual(0, missing_time.returncode, missing_time.stderr)
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in missing_time.calls))

    def test_ai_removal_is_noop_for_generic_creator_tool_only(self):
        self.set_tags('-XMP:CreatorTool=Ordinary editor')
        before = self.w.observe(self.source)
        result = self.w.dispatch('stripmeta', '--mode', 'ai', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in result.calls))

    def test_failed_metadata_producer_preserves_original_and_destination(self):
        self.set_tags('-GPSLatitude=42')
        self.w.metadata_fault(metadata_fail_output=23)
        destination = self.source.with_name('photo 雪_gps.jpg')
        destination.write_bytes(b'preexisting')
        before = {p: self.w.observe(p) for p in (self.source, destination)}
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))

    def test_service_disappearance_after_stage_never_publishes(self):
        self.set_tags('-Artist=Old')
        self.w.metadata_fault(metadata_disappear_after_output=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('copyright', '--creator', 'New', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual('Old', self.tag('-Artist'))
        self.assertFalse(any(c['tool'] in ('mv', 'ln') for c in result.calls))
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))

    def test_cancel_after_stage_allocation_cleans_owned_stage_before_producer(self):
        self.set_tags('-GPSLatitude=42')
        self.w.metadata_fault(metadata_cancel_after_stage=True)
        before = self.w.observe(self.source)
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))
        self.assertFalse(any(c['tool'] == 'exiftool' and '-o' in c['argv'] for c in result.calls))
        self.assertFalse(any(c['tool'] in ('mv', 'ln') for c in result.calls))
        self.assert_clean()

    def test_timestamp_validation_rejects_wrong_but_successful_producer_date(self):
        self.set_tags('-DateTimeOriginal=2024:02:28 23:30:00', '-CreateDate=2024:02:28 23:30:00',
                      '-ModifyDate=2024:02:28 23:30:00')
        before = self.w.observe(self.source)
        self.w.metadata_fault(metadata_wrong_timestamp=True)
        result = self.w.dispatch('timeshift', '--offset', '+00:30:00', '--fields', 'all',
                                 '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))
        self.assertFalse(any(c['tool'] in ('mv', 'ln') for c in result.calls))
        self.assert_clean()

    def test_zero_exit_corrupt_metadata_output_is_rejected(self):
        self.set_tags('-GPSLatitude=42')
        before = self.w.observe(self.source)
        self.w.metadata_fault(metadata_corrupt_output=True)
        result = self.w.dispatch('stripmeta', '--mode', 'gps', '--', str(self.source))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, self.w.observe(self.source))
        self.assert_clean()

    def test_timestamp_year_rollover(self):
        self.set_tags('-DateTimeOriginal=2019:12:31 23:30:00')
        result = self.w.dispatch('timeshift', '--offset', '+01:00:00', '--fields', 'capture',
                                 '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2020:01:01 00:30:00', self.tag('-DateTimeOriginal'))

    def test_duplicate_selection_shifts_a_source_only_once(self):
        self.set_tags('-DateTimeOriginal=2024:01:01 12:00:00')
        parent_alias = self.w.path('input-alias')
        parent_alias.symlink_to(self.source.parent, target_is_directory=True)
        alias = str(parent_alias / self.source.name)
        result = self.w.dispatch('timeshift', '--offset', '+01:00:00', '--fields', 'capture',
                                 '--', str(self.source), alias)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('2024:01:01 13:00:00', self.tag('-DateTimeOriginal'))

    def test_leading_dash_filename_and_mixed_batch_partial_failure(self):
        first = self.w.path('input/-first photo.jpg')
        first.write_bytes(self.source.read_bytes())
        self.set_tags('-Artist=Old', '-GPSLatitude=42')
        raw = self.w.path('input/unsupported.dng')
        raw.write_bytes(self.source.read_bytes())
        first_before = self.w.observe(first)
        raw_before = self.w.observe(raw)
        self.w.env['KIM_POLICY'] = 'create'
        result = self.w.dispatch('copyright', '--creator', 'Batch Photographer', '--',
                                 str(first), str(raw))
        self.assertNotEqual(0, result.returncode)
        output = first.with_name('-first photo_copyright.jpg')
        self.assertTrue(output.is_file())
        self.assertEqual('Batch Photographer', self.tag_at(output, '-Artist'))
        self.assertEqual(first_before, self.w.observe(first))
        self.assertEqual(raw_before, self.w.observe(raw))

    def test_create_rejects_selected_symlink_and_overwrite_rejects_hardlink(self):
        link = self.w.path('input/selected.jpg')
        link.symlink_to(self.source.name)
        result = self.w.dispatch('copyright', '--creator', 'New', '--', str(link))
        self.assertNotEqual(0, result.returncode)
        self.assertTrue(link.is_symlink())
        self.set_tags('-DateTimeOriginal=2024:01:01 12:00:00')
        hardlink = self.w.path('input/hardlink.jpg')
        os.link(self.source, hardlink)
        result = self.w.dispatch('timeshift', '--offset', '+01:00:00', '--', str(hardlink))
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.source.stat().st_ino, hardlink.stat().st_ino)


if __name__ == '__main__':
    unittest.main()
