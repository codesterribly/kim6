"""K20 resizing at the isolated dispatcher boundary, with real geometry/codec tests."""
import base64
import os
from pathlib import Path
import shutil
import subprocess
import struct
import unittest
import zlib
from support import Workspace


class ResizeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.source = self.workspace.png('input/photo 雪.png')
        self.workspace.env['KIM_POLICY'] = 'create'

    def dispatch(self, geometry='2x2', destination='', sources=None):
        return self.workspace.dispatch('resize', geometry, destination, *(sources or (self.source,)))

    def assert_clean(self):
        self.assertFalse(list(self.workspace.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.workspace.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((self.workspace.control / 'tmp').iterdir()), [])

    def decoded(self, path):
        result = subprocess.run([shutil.which('identify'), '-regard-warnings', '+ping',
                                 '-format', '%m %w %h\n', 'TGA:-' if path.suffix in ('.tga', '.vda') else '-'], input=path.read_bytes(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode().strip()

    def test_large_frame_dimensions_need_only_one_producer(self):
        # Metadata streams model large decoded frames without pixel buffers.
        # Literals cover percentage, aspect ratio, force, shrink and area syntax.
        for width, height, geometry, dimensions in (
            (6000, 4000, '50%', '3000 2000'),
            (8256, 5504, '25%', '2064 1376'),
            (12000, 8000, '900x900', '900 600'),
            (9504, 6336, '1920x1080', '1620 1080'),
            (9504, 6336, '1920x1080!', '1920 1080'),
            (6000, 4000, '8000x8000>', '6000 4000'),
            (9504, 6336, '1000000@', '1225 816'),
        ):
            with self.subTest(geometry=geometry, source=(width, height)):
                self.workspace.sequence('identify', [
                    {'stdout': f'PNG {width} {height}\n'},
                    {'stdout': f'PNG {dimensions}\n'},
                ])
                self.workspace.respond('magick', stdout=dimensions + '\n',
                    output_base64=base64.b64encode(self.source.read_bytes()).decode())
                result = self.dispatch(geometry)
                self.assertEqual(len([c for c in result.calls if c['tool'] == 'magick']), 1)
                self.assertTrue(result.outputs)
                for name in result.outputs:
                    (self.workspace.root / name).unlink()
                self.assert_clean()

    def test_large_multi_frame_dimensions_use_one_producer(self):
        source = self.workspace.png('input/frames.gif')
        self.workspace.sequence('identify', [
            {'stdout': 'GIF 6000 4000\nGIF 9504 6336\n'},
            {'stdout': 'GIF 3000 2000\nGIF 4752 3168\n'},
        ])
        self.workspace.respond('magick', stdout='3000 2000\n4752 3168\n',
            output_base64=base64.b64encode(source.read_bytes()).decode())
        result = self.dispatch('50%', sources=[source])
        self.assertTrue(result.outputs)
        self.assertEqual(len([c for c in result.calls if c['tool'] == 'magick']), 1)
        self.assert_clean()

    def test_real_large_photograph_dimensions(self):
        for width, height, geometry, expected in (
            (6000, 4000, '50%', 'PNG 3000 2000'),
            (9504, 6336, '1920x1080', 'PNG 1620 1080'),
        ):
            with self.subTest(source=(width, height), geometry=geometry):
                # One-bit PNG built a scanline at a time: no full-size fixture
                # canvas, and only the actual decoder/resize needs pixel memory.
                compressor = zlib.compressobj()
                compressed = bytearray()
                row = bytes(1 + (width + 7) // 8)
                for _ in range(height):
                    compressed.extend(compressor.compress(row))
                compressed.extend(compressor.flush())
                def chunk(kind, data):
                    return (struct.pack('>I', len(data)) + kind + data +
                            struct.pack('>I', zlib.crc32(kind + data)))
                source = self.workspace.path(f'input/large-{width}.png')
                source.write_bytes(b'\x89PNG\r\n\x1a\n' +
                    chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 1, 0, 0, 0, 0)) +
                    chunk(b'IDAT', bytes(compressed)) + chunk(b'IEND', b''))
                self.workspace.use_real_resize()
                before = self.workspace.observe(source)
                result = self.dispatch(geometry, sources=[source])
                self.assertEqual(self.decoded(source.with_name(source.stem + '_resized.png')), expected)
                self.assertEqual(self.workspace.observe(source), before)
                self.assertEqual(len([c for c in result.calls if c['tool'] == 'magick']), 1)
                self.assert_clean()

    def test_missing_or_extra_producer_frame_dimensions_prevent_publication(self):
        for stream in ('', '3 2\n3 2\n', 'invalid\n'):
            with self.subTest(stream=stream):
                before = self.workspace.observe(self.source)
                self.workspace.respond('magick', stdout=stream,
                    output_base64=base64.b64encode(self.source.read_bytes()).decode())
                result = self.dispatch('3x2')
                self.assertEqual(result.outputs, {})
                self.assertEqual(self.workspace.observe(self.source), before)
                self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
                self.assert_clean()

    def test_real_create_stages_locally_and_preserves_aspect_ratio(self):
        self.workspace.use_real_resize()
        before = self.workspace.observe(self.source)
        result = self.dispatch()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_name('photo 雪_resized.png')
        self.assertEqual(self.decoded(output), 'PNG 2 1')
        producer = next(c for c in result.calls if c['tool'] == 'magick' and c['argv'][0] == '--')
        stage = Path(producer['argv'][-1])
        self.assertNotEqual(stage, output)
        self.assertEqual(stage.parent.parent, output.parent)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_percent_option_resizes_without_changing_aspect_ratio(self):
        source = self.workspace.png('input/percent.png')
        subprocess.run([shutil.which('magick'), '-size', '8x4', 'xc:red', str(source)], check=True)
        self.workspace.use_real_resize()
        result = self.workspace.dispatch('resize', '--percent', '50', '--', str(source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.decoded(source.with_name('percent_resized.png')), 'PNG 4 2')

    def test_percent_option_rejects_out_of_range_values_before_production(self):
        for value in ('0', '1001', '1.5', '-25'):
            with self.subTest(value=value):
                result = self.workspace.dispatch('resize', '--percent', value, '--', str(self.source))
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))

    def test_percent_enlargement_is_explicit_and_keeps_aspect_ratio(self):
        source = self.workspace.png('input/enlarge.png')
        subprocess.run([shutil.which('magick'), '-size', '8x4', 'xc:blue', str(source)], check=True)
        self.workspace.use_real_resize()
        result = self.workspace.dispatch('resize', '--percent', '150', '--', str(source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.decoded(source.with_name('enlarge_resized.png')), 'PNG 12 6')

    def test_invalid_explicit_destination_does_not_fall_back(self):
        self.workspace.use_real_resize()
        before = self.workspace.observe(self.source)
        result = self.dispatch(destination=self.workspace.path('missing/destination'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['tool'] == 'magick' and c['argv'][0] == '--' for c in result.calls))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertEqual(result.outputs, {})
        self.assert_clean()

    def test_wrong_dimensions_are_rejected(self):
        self.workspace.respond('magick', stdout='2 1\n', output_base64=base64.b64encode(self.source.read_bytes()).decode())
        result = self.dispatch()
        self.assertFalse(self.source.with_name('photo 雪_resized.png').exists())
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_wrong_encoding_is_rejected(self):
        payload = self.workspace.jpeg('.control/wrong.jpg').read_bytes()
        self.workspace.respond('magick', stdout='3 2\n', output_base64=base64.b64encode(payload).decode())
        result = self.dispatch('3x2')
        self.assertFalse(self.source.with_name('photo 雪_resized.png').exists())
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_cancellation_prevents_publication_and_next_batch_item(self):
        second = self.workspace.png('input/second.png')
        before = {p: self.workspace.observe(p) for p in (self.source, second)}
        self.workspace.approve_overwrite()
        self.workspace.respond('magick', stdout='3 2\n', output_base64=base64.b64encode(self.source.read_bytes()).decode(), cancel=True)
        result = self.dispatch('3x2', sources=[self.source, second])
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        producers = [c for c in result.calls if c['tool'] == 'magick' and c['argv'][0] == '--']
        self.assertEqual(len(producers), 1)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.assert_clean()

    def test_real_overwrite_has_fresh_mtime_and_keeps_mode(self):
        self.workspace.approve_overwrite()
        self.workspace.use_real_resize()
        self.workspace.use_real_mv()
        self.source.chmod(0o640)
        os.utime(self.source, (1_600_000_000, 1_600_000_000))
        before = self.workspace.observe(self.source)
        result = self.dispatch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.decoded(self.source), 'PNG 2 1')
        self.assertNotEqual(self.workspace.observe(self.source).inode, before.inode)
        self.assertNotEqual(self.source.stat().st_mtime_ns, before.mtime_ns)
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o640)
        self.assert_clean()

    def test_real_create_keeps_source_and_has_fresh_mtime(self):
        self.workspace.use_real_resize()
        self.source.chmod(0o640)
        os.utime(self.source, (1_600_000_000, 1_600_000_000))
        before = self.workspace.observe(self.source)
        self.dispatch()
        output = self.source.with_name('photo 雪_resized.png')
        self.assertNotEqual(output.stat().st_mtime_ns, before.mtime_ns)
        self.assertEqual(output.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_prefix_collision_numbering_and_duplicate_basenames(self):
        second = self.workspace.png('other/photo 雪.png')
        destination = self.workspace.path('exports')
        destination.mkdir()
        occupied = destination / 'resized_photo 雪.png'
        occupied.write_bytes(b'preexisting export')
        dangling = destination / 'resized_photo 雪_1.png'
        dangling.symlink_to('missing')
        before = {p: self.workspace.observe(p) for p in (self.source, second, occupied, dangling)}
        self.workspace.env['KIM_NAME_AFFIX_POSITION'] = 'prefix'
        self.workspace.use_real_resize()
        result = self.dispatch(destination=destination, sources=[self.source, second])
        self.assertEqual(set(result.outputs), {'exports/resized_photo 雪_2.png', 'exports/resized_photo 雪_3.png'})
        for name in result.outputs:
            self.assertEqual(self.decoded(self.workspace.path(name)), 'PNG 2 1')
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        self.assert_clean()

    def test_regular_file_explicit_destination_is_rejected(self):
        destination = self.workspace.png('not-a-directory.png')
        before = self.workspace.observe(destination)
        result = self.dispatch(destination=destination)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.workspace.observe(destination), before)
        self.assertEqual(result.outputs, {})
        self.assert_clean()

    def test_inaccessible_staging_reports_failure_without_fallback(self):
        destination = self.workspace.path('exports')
        destination.mkdir()
        before = self.workspace.observe(self.source)
        self.workspace.sequence('mktemp', [{'passthrough': True}, {'status': 73}])
        self.workspace.respond('magick', status=23)
        result = self.dispatch(destination=destination)
        self.assertEqual(result.outputs, {})
        self.assertFalse(any(c['tool'] == 'magick' and c['argv'][0] == '--' for c in result.calls))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_newly_occupied_destination_is_preserved(self):
        self.workspace.respond('magick', stdout='3 2\n', output_base64=base64.b64encode(self.source.read_bytes()).decode(),
                               writes={'input/photo 雪_resized.png': 'other invocation'})
        result = self.dispatch('3x2')
        self.assertEqual(self.source.with_name('photo 雪_resized.png').read_bytes(), b'other invocation')
        self.assertTrue(any(e['tool'] == 'ln' and e['status'] != 0 for e in result.events))
        self.assert_clean()

    def test_cancel_before_production_does_not_start_batch(self):
        self.workspace.use_real_resize()
        self.workspace.respond_to('kdialog', '--progressbar',
                                  {'stdout': 'org.kde.kdialog-test /ProgressDialog\n', 'cancel': True})
        result = self.dispatch()
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_clean()

    def test_cancel_during_metadata_preparation_prevents_publication(self):
        self.workspace.approve_overwrite()
        self.workspace.use_real_resize()
        self.workspace.respond('chmod', cancel=True)
        before = self.workspace.observe(self.source)
        result = self.dispatch()
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.assert_clean()

    def test_failed_batch_item_does_not_prevent_next_success(self):
        second = self.workspace.png('input/second.png')
        self.workspace.sequence('magick', [{'status': 23},
            {'stdout': '3 2\n', 'output_base64': base64.b64encode(second.read_bytes()).decode()}])
        result = self.dispatch('3x2', sources=[self.source, second])
        self.assertEqual(set(result.outputs), {'input/second_resized.png'})
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) and 'Succeeded: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_multi_frame_gif_preserves_frames_and_geometry(self):
        source = self.workspace.path('input/animated.gif')
        subprocess.run([shutil.which('magick'), '-size', '3x2', 'xc:red', '-size', '3x2', 'xc:blue',
                        '-loop', '0', str(source)], check=True)
        self.workspace.use_real_resize()
        self.dispatch(sources=[source])
        self.assertEqual(self.decoded(source.with_name('animated_resized.gif')), 'GIF 2 1\nGIF 2 1')
        self.assert_clean()

    def test_filename_suffix_continues_selecting_output_format(self):
        source = self.workspace.png('input/misnamed.jpg')
        self.workspace.use_real_resize()
        self.dispatch(sources=[source])
        self.assertEqual(self.decoded(source.with_name('misnamed_resized.jpg')), 'JPEG 2 1')
        self.assert_clean()

    def test_exif_orientation_icc_and_existing_metadata_are_preserved(self):
        source = self.workspace.jpeg('input/oriented 雪.jpg')
        # Same embedded CC0 Rec2020 micro profile used by the K19 fixture.
        profile = base64.b64decode('AAABzGxjbXMCEAAAbW50clJHQiBYWVogB+IAAwAUAAkADgAdYWNzcE1TRlQAAAAAc2F3c2N0cmwAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1oYW5kF8tE0Q3K4ckDPiCFSmdOqQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJZGVzYwAAAPAAAABfY3BydAAAAQwAAAAMd3RwdAAAARgAAAAUclhZWgAAASwAAAAUZ1hZWgAAAUAAAAAUYlhZWgAAAVQAAAAUclRSQwAAAWgAAABkZ1RSQwAAAWgAAABkYlRSQwAAAWgAAABkZGVzYwAAAAAAAAAFdTIwMgAAAAAAAAAAAAAAAHRleHQAAAAAQ0MwAFhZWiAAAAAAAADzUQABAAAAARbMWFlaIAAAAAAAAKxpAABHcP///4FYWVogAAAAAAAAKmoAAKzjAAAHrVhZWiAAAAAAAAAgAwAAC60AAMv/Y3VydgAAAAAAAAAsAAABUwKlA/gFTgbWCJgKjwzDDzER3BTDF+gbTB7wItUm+itiMAw0+jorP6JFXUtfUadYN18NZixtlHVFfT+FhI4Tlu6gE6mGs0S9T8eo0k7dQuiG9Bb//w==')
        exif = (b'Exif\0\0II*\0\x08\0\0\0' + struct.pack('<H', 1)
                + struct.pack('<HHI', 0x112, 3, 1) + struct.pack('<H', 6) + b'\0\0' + struct.pack('<I', 0))
        def segment(marker, data):
            return b'\xff' + bytes([marker]) + struct.pack('>H', len(data) + 2) + data
        data = source.read_bytes()
        source.write_bytes(data[:2] + segment(0xe1, exif)
                           + segment(0xe2, b'ICC_PROFILE\0\x01\x01' + profile)
                           + segment(0xfe, b'existing resize comment') + data[2:])
        before = self.workspace.observe(source)
        self.workspace.use_real_resize()
        result = self.dispatch(sources=[source])
        self.assertEqual(result.returncode, 0, result.stderr)
        output = source.with_name('oriented 雪_resized.jpg')
        self.assertEqual(self.decoded(output), 'JPEG 2 1')
        info = subprocess.run([shutil.which('identify'), '-format', '%[orientation] %[profiles] %[comment]', str(output)],
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual(info, 'RightTop exif,icc existing resize comment')
        profile_out = subprocess.run([shutil.which('magick'), str(output), 'ICC:-'], capture_output=True, check=True).stdout
        self.assertEqual(profile_out, profile)
        displayed = subprocess.run([shutil.which('magick'), str(output), '-auto-orient', '-format', '%w %h', 'info:'],
                                   capture_output=True, text=True, check=True).stdout
        self.assertEqual(displayed, '1 2')
        self.assertEqual(self.workspace.observe(source), before)
        self.assert_clean()

    def test_no_extension_retains_input_encoding(self):
        source = self.workspace.png('input/no-extension')
        self.workspace.use_real_resize()
        result = self.dispatch(sources=[source])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.decoded(source.with_name('no-extension_resized')), 'PNG 2 1')
        self.assert_clean()


    def test_cancel_during_input_preparation_prevents_production(self):
        self.workspace.respond('identify', stdout='PNG 3 2\n', cancel=True)
        self.workspace.respond('magick', output_base64=base64.b64encode(self.source.read_bytes()).decode())
        result = self.dispatch('3x2')
        self.assertFalse(any(c['tool'] == 'magick' and c['argv'][0] == '--' for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_clean()

    def test_tga_output_rejects_wrong_encoding(self):
        source = self.workspace.path('input/targa.tga')
        subprocess.run([shutil.which('magick'), str(self.source), str(source)], check=True)
        self.workspace.respond('magick', output_base64=base64.b64encode(self.workspace.jpeg('.control/wrong.jpg').read_bytes()).decode())
        before = self.workspace.observe(source)
        result = self.dispatch('3x2', sources=[source])
        self.assertEqual(self.workspace.observe(source), before)
        self.assertFalse(source.with_name('targa_resized.tga').exists())
        self.assertTrue(any(c['tool'] == 'magick' and c['argv'][:1] == ['--'] for c in result.calls))
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()


def geometry_case(geometry, dimensions):
    def test(self):
        self.workspace.use_real_resize()
        result = self.dispatch(geometry)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.decoded(self.source.with_name('photo 雪_resized.png')), 'PNG ' + dimensions)
        self.assert_clean()
    return test


# Literal expected dimensions reflect existing ImageMagick resize semantics.
for _geometry, _dimensions in (
        ('300x300', '300 200'), ('600x600', '600 400'), ('800x800', '800 533'),
        ('1024x1024', '1024 683'), ('1280x1280', '1280 853'), ('1400x1400', '1400 933'),
        ('1600x1600', '1600 1067'), ('1920x1920', '1920 1280'), ('2560x2560', '2560 1707'),
        ('3440x3440', '3440 2293'), ('3840x3840', '3840 2560'),
        ('50%', '2 1'), ('2x2!', '2 2'), ('2x2^', '3 2'), ('4x4>', '3 2'),
        ('2x2<', '3 2'), ('4@', '2 2'), ('2', '2 1'), ('x3', '5 3'),
        ('2x2+1+1', '2 1'), ('0x0', '1 1')):
    setattr(ResizeTests, 'test_geometry_' + _geometry, geometry_case(_geometry, _dimensions))


def failure_case(mode, scenario):
    def test(self):
        w = self.workspace
        w.set_policy_for_test(mode)
        output = self.source if mode == 'overwrite' else self.source.with_name('photo 雪_resized.png')
        before = {p: w.observe(p) for p in (self.source, output)}
        response = {'output_base64': base64.b64encode(self.source.read_bytes()).decode()}
        tool, status = 'magick', 0
        if scenario == 'before':
            response = {'status': 23}; status = 23
        elif scenario == 'partial':
            response = {'status': 23, 'output_base64': base64.b64encode(b'partial output').decode()}; status = 23
        elif scenario in ('empty', 'corrupt', 'truncated', 'wrong_encoding'):
            data = {'empty': b'', 'corrupt': b'garbage', 'truncated': self.source.read_bytes()[:45],
                    'wrong_encoding': w.jpeg('.control/wrong.jpg').read_bytes()}[scenario]
            response = {'output_base64': base64.b64encode(data).decode()}
        elif scenario == 'publication':
            tool, status = ('mv' if mode == 'overwrite' else 'ln'), 73
            w.respond(tool, status=status)
        elif scenario == 'encoder':
            response = {'status': 127, 'stderr': 'missing encoder\n'}; status = 127
        elif scenario == 'decoder':
            tool, status = 'identify', 127
            w.respond(tool, status=status)
        elif scenario == 'metadata':
            tool, status = 'chmod', 73
            w.respond(tool, status=status)
        response['stdout'] = '3 2\n'
        w.respond('magick', **response)
        result = self.dispatch('3x2')
        for p, state in before.items():
            self.assertEqual(w.observe(p), state)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls), result.calls)
        self.assertTrue(any(e['tool'] == tool and e['status'] == status for e in result.events), result.events)
        self.assertFalse(any(c['tool'] == 'cp' for c in result.calls))
        self.assert_clean()
    return test


for _mode in ('create', 'overwrite'):
    for _scenario in ('before', 'partial', 'empty', 'corrupt', 'truncated', 'wrong_encoding',
                      'publication', 'encoder', 'decoder', 'metadata'):
        setattr(ResizeTests, 'test_' + _mode + '_preserves_on_' + _scenario, failure_case(_mode, _scenario))


def invalid_geometry_case(geometry):
    def test(self):
        destination = self.source.with_name('photo 雪_resized.png')
        destination.write_bytes(b'preexisting destination')
        source_bytes = self.source.read_bytes()
        before = {p: self.workspace.observe(p) for p in (self.source, destination)}
        self.workspace.use_real_resize()
        # Trace the existing dispatcher to establish that publication helpers
        # are never entered, including an early-returning publication helper.
        self.workspace.env['SHELLOPTS'] = 'xtrace'
        for mode in ('create', 'overwrite'):
            with self.subTest(mode=mode):
                self.workspace.set_policy_for_test(mode)
                result = self.dispatch(geometry)
                self.assertEqual(self.source.read_bytes(), source_bytes)
                for path, state in before.items():
                    self.assertEqual(self.workspace.observe(path), state)
                self.assertEqual(result.outputs, {})
                self.assertTrue(any(e['tool'] == 'magick' and e['status'] != 0
                                    for e in result.events))
                self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
                self.assertFalse(any(c['tool'] in ('ln', 'mv') for c in result.calls))
                self.assertIn('+ action_resize ', result.stderr)
                self.assertNotIn('commit_tmp_to_target', result.stderr)
                self.assertNotIn('atomic_overwrite_file', result.stderr)
                self.assert_clean()
    return test


for _geometry in ('nonsense', '1xnoheight', '100000x100000!', '99999999999999999999x99999999999999999999'):
    setattr(ResizeTests, 'test_invalid_geometry_' + _geometry, invalid_geometry_case(_geometry))


def format_case(extension, magic):
    def test(self):
        source = self.workspace.path('input/format.' + extension)
        subprocess.run([shutil.which('magick'), str(self.source), str(source)], check=True)
        self.workspace.use_real_resize()
        result = self.dispatch(sources=[source])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.decoded(source.with_name('format_resized.' + extension)), magic + ' 2 1')
        self.assert_clean()
    return test


for _extension, _magic in (('jpg', 'JPEG'), ('gif', 'GIF'), ('tiff', 'TIFF'), ('bmp', 'BMP'),
                            ('webp', 'WEBP'), ('avif', 'AVIF'), ('heic', 'HEIC'), ('pdf', 'PDF'),
                            ('png8', 'PNG'), ('tif', 'TIFF'), ('pnm', 'PPM'), ('heif', 'HEIC'), ('pjpeg', 'JPEG'),
                            ('j2c', 'JP2'), ('jpc', 'JP2'), ('jpm', 'JP2'),
                            ('epdf', 'PDF'), ('pdfa', 'PDF'), ('ai', 'PDF'), ('ptif', 'TIFF'), ('apng', 'PNG'), ('tga', 'TGA'), ('vda', 'TGA')):
    setattr(ResizeTests, 'test_real_format_' + _extension, format_case(_extension, _magic))


if __name__ == '__main__':
    unittest.main()
