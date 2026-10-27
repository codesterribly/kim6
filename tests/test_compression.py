"""K19 JPEG compression through the existing isolated dispatcher boundary."""
import base64
import os
from pathlib import Path
import shutil
import struct
import subprocess
import unittest
from support import Workspace


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.source = self.workspace.jpeg('input/photo 雪.jpg')
        self.workspace.env['KIM_POLICY'] = 'create'

    def dispatch(self, quality='75', *sources):
        return self.workspace.dispatch('compress', quality, self.source.parent, *(sources or (self.source,)))

    def assert_clean(self):
        self.assertFalse(list(self.workspace.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.workspace.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((self.workspace.control / 'tmp').iterdir()), [])

    def test_real_create_is_staged_and_fully_decodable(self):
        before = self.workspace.observe(self.source)
        self.workspace.use_real_compression()
        result = self.dispatch()
        output = self.source.with_name('photo 雪_compressed.jpg')
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = subprocess.run([shutil.which('identify'), '-regard-warnings', '+ping',
                                  '-format', '%m %w %h', '-'], input=output.read_bytes(), capture_output=True)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertEqual(decoded.stdout, b'JPEG 3 2')
        call = next(c for c in result.calls if c['tool'] == 'magick')
        stage = Path(call['argv'][-1].removeprefix('JPEG:'))
        self.assertNotEqual(stage, output)
        self.assertEqual(stage.parent.parent, output.parent)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_quality_08_is_decimal_eight(self):
        self.workspace.use_real_compression()
        result = self.dispatch('08')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.source.with_name('photo 雪_compressed.jpg').exists())
        call = next(c for c in result.calls if c['tool'] == 'magick')
        self.assertEqual(call['argv'][call['argv'].index('-quality') + 1], '8')
        self.assert_clean()

    def test_non_jpeg_content_named_jpg_is_rejected(self):
        self.source.write_bytes(self.workspace.png('.control/reference.png').read_bytes())
        before = self.workspace.observe(self.source)
        self.workspace.use_real_compression()
        result = self.dispatch()
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_wrong_jpeg_dimensions_are_rejected(self):
        fixture = self.workspace.path('.control/small.jpg')
        subprocess.run([shutil.which('magick'), '-size', '1x1', 'xc:red', str(fixture)], check=True)
        self.workspace.respond('magick', output_base64=base64.b64encode(fixture.read_bytes()).decode())
        result = self.dispatch()
        self.assertFalse(self.source.with_name('photo 雪_compressed.jpg').exists())
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.assert_clean()

    def test_real_orientation_and_icc_are_preserved(self):
        # Compact Rec2020 micro ICC fixture; its embedded copyright is CC0.
        profile = base64.b64decode('AAABzGxjbXMCEAAAbW50clJHQiBYWVogB+IAAwAUAAkADgAdYWNzcE1TRlQAAAAAc2F3c2N0cmwAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1oYW5kF8tE0Q3K4ckDPiCFSmdOqQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJZGVzYwAAAPAAAABfY3BydAAAAQwAAAAMd3RwdAAAARgAAAAUclhZWgAAASwAAAAUZ1hZWgAAAUAAAAAUYlhZWgAAAVQAAAAUclRSQwAAAWgAAABkZ1RSQwAAAWgAAABkYlRSQwAAAWgAAABkZGVzYwAAAAAAAAAFdTIwMgAAAAAAAAAAAAAAAHRleHQAAAAAQ0MwAFhZWiAAAAAAAADzUQABAAAAARbMWFlaIAAAAAAAAKxpAABHcP///4FYWVogAAAAAAAAKmoAAKzjAAAHrVhZWiAAAAAAAAAgAwAAC60AAMv/Y3VydgAAAAAAAAAsAAABUwKlA/gFTgbWCJgKjwzDDzER3BTDF+gbTB7wItUm+itiMAw0+jorP6JFXUtfUadYN18NZixtlHVFfT+FhI4Tlu6gE6mGs0S9T8eo0k7dQuiG9Bb//w==')
        exif = (b'Exif\0\0II*\0\x08\0\0\0' + struct.pack('<H', 1)
                + struct.pack('<HHI', 0x112, 3, 1) + struct.pack('<H', 6) + b'\0\0' + struct.pack('<I', 0))
        def segment(marker, data):
            return b'\xff' + bytes([marker]) + struct.pack('>H', len(data) + 2) + data
        self.source.write_bytes(self.source.read_bytes()[:2] + segment(0xe1, exif)
                                + segment(0xe2, b'ICC_PROFILE\0\x01\x01' + profile)
                                + self.source.read_bytes()[2:])
        self.workspace.use_real_compression()
        result = self.dispatch('100')
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_name('photo 雪_compressed.jpg')
        info = subprocess.run([shutil.which('identify'), '-format', '%[orientation] %[profiles] %w %h', str(output)],
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual(info, 'RightTop exif,icc 3 2')
        profile_out = subprocess.run([shutil.which('magick'), str(output), 'ICC:-'], capture_output=True, check=True).stdout
        self.assertEqual(profile_out, profile)
        def displayed(path):
            return subprocess.run([shutil.which('magick'), str(path), '-auto-orient', '-depth', '8', 'RGB:-'],
                                  capture_output=True, check=True).stdout
        original_pixels, output_pixels = displayed(self.source), displayed(output)
        self.assertEqual(len(original_pixels), len(output_pixels))
        self.assertLess(sum(abs(a-b) for a,b in zip(original_pixels, output_pixels)) / len(original_pixels), 8)
        self.assert_clean()

    def test_cancel_after_production_preserves_original(self):
        before = self.workspace.observe(self.source)
        self.workspace.approve_overwrite()
        self.workspace.respond('magick', output_base64=base64.b64encode(self.source.read_bytes()).decode(), cancel=True)
        result = self.dispatch()
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.assert_clean()

    def test_create_keeps_source_mode_but_has_new_mtime(self):
        self.source.chmod(0o640)
        os.utime(self.source, (1_600_000_000, 1_600_000_000))
        before = self.workspace.observe(self.source)
        self.workspace.use_real_compression()
        result = self.dispatch()
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.source.with_name('photo 雪_compressed.jpg')
        self.assertEqual(output.stat().st_mode & 0o777, 0o640)
        self.assertNotEqual(output.stat().st_mtime_ns, before.mtime_ns)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assert_clean()

    def test_real_overwrite_has_new_mtime_and_keeps_mode(self):
        self.workspace.approve_overwrite()
        self.source.chmod(0o640)
        os.utime(self.source, (1_600_000_000, 1_600_000_000))
        before = self.workspace.observe(self.source)
        self.workspace.use_real_compression()
        self.workspace.use_real_mv()
        result = self.dispatch('100')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.workspace.observe(self.source).inode, before.inode)
        self.assertNotEqual(self.source.stat().st_mtime_ns, before.mtime_ns)
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o640)
        decoded = subprocess.run([shutil.which('identify'), '-regard-warnings', '+ping',
                                  '-format', '%m %w %h', '-'], input=self.source.read_bytes(), capture_output=True)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertEqual(decoded.stdout, b'JPEG 3 2')
        self.assertTrue(any(e['tool'] == 'mv' and e['status'] == 0 for e in result.events))
        self.assert_clean()

    def test_prefix_suffix_collisions_and_duplicate_basename_batch(self):
        second = self.workspace.jpeg('other/photo 雪.jpg')
        destination = self.workspace.path('exports')
        destination.mkdir()
        occupied = destination / 'compressed_photo 雪.jpg'
        occupied.symlink_to('missing')
        before = {p: self.workspace.observe(p) for p in (self.source, second, occupied)}
        self.workspace.env['KIM_NAME_AFFIX_POSITION'] = 'prefix'
        self.workspace.use_real_compression()
        result = self.workspace.dispatch('compress', '75', destination, self.source, second)
        self.assertEqual(set(result.outputs), {'exports/compressed_photo 雪_1.jpg', 'exports/compressed_photo 雪_2.jpg'})
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        self.assert_clean()

    def test_jpeg_content_with_different_extension_still_encodes_jpeg(self):
        source = self.workspace.jpeg('input/space 雪.png')
        self.workspace.use_real_compression()
        result = self.dispatch('75', source)
        output = source.with_name('space 雪_compressed.png')
        self.assertEqual(result.returncode, 0, result.stderr)
        decoded = subprocess.run([shutil.which('identify'), '-regard-warnings', '+ping',
                                  '-format', '%m', '-'], input=output.read_bytes(), capture_output=True)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)
        self.assertEqual(decoded.stdout, b'JPEG')
        self.assert_clean()

    def test_explicit_baseline_jpeg_disables_progressive_scan(self):
        self.workspace.use_real_compression()
        result = self.workspace.dispatch('compress', '--quality', '85', '--jpeg-baseline', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.source.with_name('photo 雪_compressed.jpg')
        verbose = subprocess.run([shutil.which('identify'), '-verbose', str(output)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertRegex(verbose, r'Interlace:\s+None')

    def test_progressive_jpeg_option_remains_decodable(self):
        self.workspace.use_real_compression()
        result = self.workspace.dispatch('compress', '--quality', '85', '--jpeg-progressive', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.source.with_name('photo 雪_compressed.jpg')
        verbose = subprocess.run([shutil.which('identify'), '-verbose', str(output)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertRegex(verbose, r'Interlace:\s+(JPEG|Plane)')
        self.assertEqual(0, subprocess.run([shutil.which('identify'), str(output)],
                                            capture_output=True).returncode)

    def test_custom_quality_dialog_exposes_scan_and_huffman_optimization_choices(self):
        self.workspace.use_real_compression()
        result = self.workspace.dispatch('compress', '--custom', '--', str(self.source))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(self.source.with_name('photo 雪_compressed.jpg').is_file())
        menus = [c['argv'] for c in result.calls if c['tool'] == 'kdialog' and '--menu' in c['argv']]
        self.assertEqual(2, len(menus))
        self.assertIn('progressive', menus[0])
        self.assertIn('yes', menus[1])

    def test_newly_occupied_destination_is_never_deleted(self):
        self.workspace.respond('magick', output_base64=base64.b64encode(self.source.read_bytes()).decode(),
                               writes={'input/photo 雪_compressed.jpg': 'other invocation'})
        result = self.dispatch()
        self.assertEqual(self.source.with_name('photo 雪_compressed.jpg').read_bytes(), b'other invocation')
        self.assertTrue(any(e['tool'] == 'ln' and e['status'] != 0 for e in result.events))
        self.assert_clean()

    def test_jpeg_huffman_optimization_option_reaches_real_encoder(self):
        source = self.workspace.jpeg("input/optimized.jpg")
        self.workspace.env["KIM_POLICY"] = "create"
        self.workspace.use_real_compression()
        result = self.workspace.dispatch("compress", "--quality", "82", "--jpeg-optimize", "--", source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(any(call["tool"] == "magick" and "jpeg:optimize-coding=true" in call["argv"]
                            for call in result.calls))
        output = source.with_name("optimized_compressed.jpg")
        self.assertEqual(0, subprocess.run([shutil.which("identify"), "-regard-warnings", str(output)],
                                           capture_output=True).returncode)
        self.assert_clean()

    def test_cancel_before_prompt_prevents_production(self):
        self.workspace.env.pop('KIM_POLICY')
        self.workspace.respond_to('kdialog', '--radiolist', {'status': 2})
        result = self.dispatch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))
        self.assert_clean()

    def test_batch_continues_after_failed_item(self):
        second = self.workspace.jpeg('input/second 雪.jpg')
        before = {p: self.workspace.observe(p) for p in (self.source, second)}
        self.workspace.sequence('magick', [{'status': 23},
            {'output_base64': base64.b64encode(second.read_bytes()).decode()}])
        result = self.dispatch('75', self.source, second)
        self.assertEqual(set(result.outputs), {'input/second 雪_compressed.jpg'})
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) and 'Succeeded: 1' in ' '.join(c['argv']) for c in result.calls))
        for p, state in before.items():
            self.assertEqual(self.workspace.observe(p), state)
        self.assert_clean()


def quality_case(quality, accepted):
    def test(self):
        self.workspace.use_real_compression()
        before = self.workspace.observe(self.source)
        result = self.dispatch(quality)
        self.assertEqual(result.returncode == 0, accepted, result.stderr)
        self.assertEqual(self.source.with_name('photo 雪_compressed.jpg').exists(), accepted)
        self.assertEqual(self.workspace.observe(self.source), before)
        self.assertEqual(any(c['tool'] == 'magick' for c in result.calls), accepted)
        self.assert_clean()
    return test


for _quality, _accepted in (('1', True), ('100', True), ('0', False), ('101', False),
                             ('-1', False), ('1.5', False), ('abc', False), ('999999999999999999999', False)):
    setattr(CompressionTests, 'test_quality_' + _quality.replace('.', '_').replace('-', 'minus'),
            quality_case(_quality, _accepted))


def failure_case(mode, scenario):
    def test(self):
        w = self.workspace
        w.set_policy_for_test(mode)
        output = self.source if mode == 'overwrite' else self.source.with_name('photo 雪_compressed.jpg')
        sentinel = w.jpeg('retained.jpg')
        if scenario == 'source_symlink':
            self.source.unlink()
            self.source.symlink_to('../retained.jpg')
        before = {p: w.observe(p) for p in (self.source, sentinel, output)}
        payload = sentinel.read_bytes()
        response = {'output_base64': base64.b64encode(payload).decode()}
        tool, status = 'magick', 0
        if scenario == 'before':
            response = {'status': 23}; status = 23
        elif scenario == 'partial':
            response = {'status': 23, 'output_base64': base64.b64encode(b'partial bytes').decode()}; status = 23
        elif scenario in ('empty', 'invalid', 'truncated', 'wrong_encoding'):
            data = {'empty': b'', 'invalid': b'garbage', 'truncated': payload[:-25],
                    'wrong_encoding': w.png('.control/wrong.png').read_bytes()}[scenario]
            response = {'output_base64': base64.b64encode(data).decode()}
        elif scenario == 'publication':
            tool, status = ('mv' if mode == 'overwrite' else 'ln'), 73
            w.respond(tool, status=status)
        elif scenario == 'encoder':
            response = {'status': 127, 'stderr': 'encoder unavailable\n'}; status = 127
        elif scenario == 'metadata':
            tool, status = 'chmod', 73
            w.respond(tool, status=status)
        elif scenario == 'cancel':
            response['cancel'] = True
        elif scenario == 'staging':
            tool, status = 'mktemp', 73
            w.sequence(tool, [{'passthrough': True}, {'status': status}])
        w.respond('magick', **response)
        result = self.dispatch()
        for p, state in before.items():
            self.assertEqual(w.observe(p), state)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls), result.calls)
        self.assertTrue(any(e['tool'] == tool and e['status'] == status for e in result.events), result.events)
        self.assertFalse(any(c['tool'] == 'cp' for c in result.calls))
        self.assert_clean()
    return test


for _mode in ('create', 'overwrite'):
    for _scenario in ('before', 'partial', 'empty', 'invalid', 'truncated', 'wrong_encoding',
                      'publication', 'encoder', 'metadata', 'cancel', 'staging'):
        setattr(CompressionTests, 'test_' + _mode + '_preservation_on_' + _scenario,
                failure_case(_mode, _scenario))
setattr(CompressionTests, 'test_overwrite_source_symlink_is_preserved', failure_case('overwrite', 'source_symlink'))


if __name__ == '__main__':
    unittest.main()
