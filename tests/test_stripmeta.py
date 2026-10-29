"""K22: staged metadata removal through the isolated dispatcher boundary."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from support import Workspace


ICC_PROFILE = base64.b64decode('AAABzGxjbXMCEAAAbW50clJHQiBYWVogB+IAAwAUAAkADgAdYWNzcE1TRlQAAAAAc2F3c2N0cmwAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1oYW5kF8tE0Q3K4ckDPiCFSmdOqQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJZGVzYwAAAPAAAABfY3BydAAAAQwAAAAMd3RwdAAAARgAAAAUclhZWgAAASwAAAAUZ1hZWgAAAUAAAAAUYlhZWgAAAVQAAAAUclRSQwAAAWgAAABkZ1RSQwAAAWgAAABkYlRSQwAAAWgAAABkZGVzYwAAAAAAAAAFdTIwMgAAAAAAAAAAAAAAAHRleHQAAAAAQ0MwAFhZWiAAAAAAAADzUQABAAAAARbMWFlaIAAAAAAAAKxpAABHcP///4FYWVogAAAAAAAAKmoAAKzjAAAHrVhZWiAAAAAAAAAgAwAAC60AAMv/Y3VydgAAAAAAAAAsAAABUwKlA/gFTgbWCJgKjwzDDzER3BTDF+gbTB7wItUm+itiMAw0+jorP6JFXUtfUadYN18NZixtlHVFfT+FhI4Tlu6gE6mGs0S9T8eo0k7dQuiG9Bb//w==')

class StripmetaTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.jpeg('input/photo 雪.jpg')
        self.w.approve_overwrite()

    def dispatch(self, *sources):
        return self.w.dispatch('stripmeta', *(sources or (self.source,)))

    def clean(self):
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.w.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((self.w.control / 'tmp').iterdir()), [])

    def produce(self, payload=None, **options):
        self.w.respond('exiftool', output_base64=base64.b64encode(
            self.source.read_bytes() if payload is None else payload).decode(), **options)

    def failed(self, result, before):
        for p, state in before.items():
            self.assertEqual(self.w.observe(p), state)
        self.assertEqual(result.outputs, {})
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()

    def tags(self, source):
        return json.loads(subprocess.run([shutil.which('exiftool'), '-j', '-G1', str(source)],
            check=True, capture_output=True, text=True).stdout)[0]

    def annotate(self, source):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', '-EXIF:Artist=fixture',
            '-GPSLatitude=42', '-GPSLongitude=3', '-XMP:Title=private title',
            '-IPTC:Keywords=private keyword', '-Comment=private comment', str(source)],
            check=True, capture_output=True)

    def test_real_success_uses_destination_local_stage(self):
        self.annotate(self.source)
        original_tags = self.tags(self.source)
        for key in ('IFD0:Artist', 'GPS:GPSLatitude', 'GPS:GPSLongitude', 'XMP-dc:Title',
                    'IPTC:Keywords', 'File:Comment'):
            self.assertIn(key, original_tags)
        self.source.chmod(0o640)
        os.utime(self.source, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        before = self.w.observe(self.source)
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        result = self.dispatch()
        producer = next(c for c in result.calls if c['tool'] == 'exiftool' and '-o' in c['argv'])
        stage = Path(producer['argv'][producer['argv'].index('-o') + 1])
        self.assertEqual(stage.parent.parent, self.source.parent)
        after = self.w.observe(self.source)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual(after.mtime_ns, before.mtime_ns)
        self.assertEqual(after.mode, before.mode)
        tags = self.tags(self.source)
        for key in ('IFD0:Artist', 'GPS:GPSLatitude', 'GPS:GPSLongitude', 'XMP-dc:Title',
                    'IPTC:Keywords', 'File:Comment'):
            self.assertNotIn(key, tags)
        self.assertFalse(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()

    def test_create_preserves_source_and_output_nanoseconds(self):
        self.annotate(self.source)
        self.source.chmod(0o604)
        os.utime(self.source, ns=(1_600_000_000_000_000_000, 1_600_000_001_987_654_321))
        before = self.w.observe(self.source)
        self.w.env['KIM_POLICY'] = 'create'
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        result = self.dispatch()
        output = self.source.with_name('photo 雪_stripped.jpg')
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(output.stat().st_mtime_ns, before.mtime_ns)
        self.assertEqual(output.stat().st_mode & 0o777, before.mode)
        self.assertEqual(set(result.outputs), {'input/photo 雪_stripped.jpg'})
        self.clean()

    def test_prefix_collision_numbering_including_dangling_symlink(self):
        self.w.env['KIM_POLICY'] = 'create'
        self.w.env['KIM_NAME_AFFIX_POSITION'] = 'prefix'
        occupied = self.w.path('input/stripped_photo 雪.jpg')
        occupied.write_bytes(b'occupied')
        dangling = self.w.path('input/stripped_photo 雪-1.jpg')
        dangling.symlink_to('missing')
        before = {p: self.w.observe(p) for p in (self.source, occupied, dangling)}
        self.produce()
        result = self.dispatch()
        self.assertEqual(set(result.outputs), {'input/stripped_photo 雪-2.jpg'})
        for p, state in before.items():
            self.assertEqual(self.w.observe(p), state)
        self.clean()

    def test_batch_failure_then_success_and_duplicate_basenames(self):
        second = self.w.jpeg('other/photo 雪.jpg')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        self.w.env['KIM_POLICY'] = 'create'
        self.w.sequence('exiftool', [{'status': 23},
            {'output_base64': base64.b64encode(second.read_bytes()).decode()}])
        result = self.dispatch(self.source, second)
        self.assertEqual(set(result.outputs), {'other/photo 雪_stripped.jpg'})
        for p, state in before.items():
            self.assertEqual(self.w.observe(p), state)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) and 'Succeeded: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()

    def test_newly_occupied_create_target_is_preserved(self):
        self.w.env['KIM_POLICY'] = 'create'
        self.produce(writes={'input/photo 雪_stripped.jpg': 'concurrent destination'})
        before = self.w.observe(self.source)
        result = self.dispatch()
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(self.source.with_name('photo 雪_stripped.jpg').read_bytes(), b'concurrent destination')
        self.assertTrue(any(e['tool'] == 'ln' and e['status'] != 0 for e in result.events))
        self.clean()

    def test_no_effect_keeps_existing_successful_replacement_behavior(self):
        self.produce()
        before = self.w.observe(self.source)
        self.dispatch()
        after = self.w.observe(self.source)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual(after.sha256, before.sha256)
        self.assertEqual(after.mtime_ns, before.mtime_ns)
        self.clean()

    def test_cancel_before_processing_starts_no_producer(self):
        self.w.respond_to('kdialog', '--progressbar',
            {'stdout': 'org.kde.kdialog-test /ProgressDialog\n', 'cancel': True})
        before = {self.source: self.w.observe(self.source)}
        result = self.dispatch()
        self.failed(result, before)
        self.assertFalse(any(c['tool'] == 'exiftool' for c in result.calls))

    def test_cancel_after_production_stops_batch(self):
        second = self.w.jpeg('input/second.jpg')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        self.produce(cancel=True)
        result = self.dispatch(self.source, second)
        self.failed(result, before)
        self.assertEqual(len([c for c in result.calls if c['tool'] == 'exiftool' and '-o' in c['argv']]), 1)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))

    def test_cancel_during_timestamp_preparation_prevents_publication(self):
        self.produce()
        self.w.respond('touch', cancel=True)
        before = {self.source: self.w.observe(self.source)}
        self.failed(self.dispatch(), before)


    def test_real_orientation_icc_and_thumbnail_policy(self):
        profile = ICC_PROFILE
        profile_path = self.w.path('.control/retained.icc')
        profile_path.write_bytes(profile)
        thumbnail = self.w.jpeg('.control/thumbnail.jpg')
        self.annotate(self.source)
        subprocess.run([shutil.which('exiftool'), '-overwrite_original',
            '-EXIF:Orientation#=6', '-ICC_Profile<=' + str(profile_path),
            '-ThumbnailImage<=' + str(thumbnail), str(self.source)], check=True, capture_output=True)
        before_pixels = subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
            check=True, capture_output=True).stdout
        self.assertTrue(subprocess.run([shutil.which('exiftool'), '-b', '-ThumbnailImage', str(self.source)],
            check=True, capture_output=True).stdout)
        self.w.use_real_stripmeta()
        self.dispatch()
        self.assertEqual(subprocess.run([shutil.which('identify'), '-format', '%#', str(self.source)],
            check=True, capture_output=True).stdout, before_pixels)
        info = subprocess.run([shutil.which('identify'), '-format', '%[orientation] %w %h', str(self.source)],
            check=True, capture_output=True).stdout
        self.assertEqual(info, b'RightTop 3 2')
        self.assertEqual(subprocess.run([shutil.which('exiftool'), '-b', '-ICC_Profile', str(self.source)],
            check=True, capture_output=True).stdout, profile)
        self.assertEqual(subprocess.run([shutil.which('exiftool'), '-b', '-ThumbnailImage', str(self.source)],
            check=True, capture_output=True).stdout, b'')
        self.assertEqual(subprocess.run([shutil.which('magick'), str(self.source), '-auto-orient',
            '-format', '%w %h', 'info:'], check=True, capture_output=True).stdout, b'2 3')
        self.clean()

    def test_unsupported_input_decoder_never_starts_producer(self):
        self.w.respond('identify', status=127)
        before = {self.source: self.w.observe(self.source)}
        result = self.dispatch()
        self.failed(result, before)
        self.assertFalse(any(c['tool'] == 'exiftool' for c in result.calls))

    def test_stage_allocation_failure_preserves_source(self):
        self.w.sequence('mktemp', [{'passthrough': True}, {'status': 73}])
        before = {self.source: self.w.observe(self.source)}
        result = self.dispatch()
        self.failed(result, before)
        self.assertFalse(any(c['tool'] == 'exiftool' for c in result.calls))

    def test_overwrite_selected_symlink_preserves_link_and_referent(self):
        link = self.w.path('input/selected.jpg')
        link.symlink_to(self.source.name)
        before = {p: self.w.observe(p) for p in (link, self.source)}
        self.produce()
        self.failed(self.dispatch(link), before)


    def test_nondefault_png_gamma_survives_container_reconstruction(self):
        source = self.w.path('input/linear.png')
        subprocess.run([shutil.which('magick'), '-size', '3x2',
                        'xc:red', '-set', 'gamma', '1', str(source)], check=True)
        before = self.w.image_info(source)
        before_time = source.stat().st_mtime_ns
        self.w.use_real_stripmeta()
        self.w.use_real_metadata_tools()
        self.w.use_real_mv()
        result = self.dispatch(source)
        self.assertEqual(0, result.returncode, (result.stderr, result.events))
        self.assertEqual(before, self.w.image_info(source))
        self.assertEqual(before_time, source.stat().st_mtime_ns)
        self.clean()

    def test_pdf_policy_removes_visible_tags_but_retains_revision_history(self):
        source = self.w.path('input/history.pdf')
        # Put Author in the original PDF revision, rather than in an ExifTool
        # update (which ExifTool can replace). No external PDF writer needed.
        stream = b'1 0 0 rg 0 0 3 2 re f\n'
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
            b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 3 2] /Resources << >> /Contents 4 0 R >>',
            b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream',
            b'<< /Author (K22 synthetic private author) >>']
        data = bytearray(b'%PDF-1.4\n')
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
        xref = len(data)
        data.extend(b'xref\n0 6\n0000000000 65535 f \n')
        for offset in offsets[1:]:
            data.extend(f'{offset:010d} 00000 n \n'.encode())
        data.extend(f'trailer\n<< /Size 6 /Root 1 0 R /Info 5 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        source.write_bytes(data)
        self.assertEqual(subprocess.run([shutil.which('exiftool'), '-s3', '-Author', str(source)],
            check=True, capture_output=True).stdout.strip(), b'K22 synthetic private author')
        self.w.use_real_stripmeta()
        before = self.w.observe(source)
        result = self.dispatch(source)
        self.assertNotEqual(self.w.observe(source).inode, before.inode)
        self.assertEqual(subprocess.run([shutil.which('exiftool'), '-s3', '-Author', str(source)],
            check=True, capture_output=True).stdout, b'')
        data = source.read_bytes()
        ends = [i for i in range(len(data)) if data.startswith(b'%%EOF', i)]
        self.assertGreaterEqual(len(ends), 2)
        previous = self.w.path('.control/previous-revision.pdf')
        previous.write_bytes(data[:ends[-2] + 5] + b'\n')
        self.assertEqual(subprocess.run([shutil.which('exiftool'), '-s3', '-Author', str(previous)],
            check=True, capture_output=True).stdout.strip(), b'K22 synthetic private author')
        self.assertFalse(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()


    def test_icc_changes_are_rejected_even_with_identical_decoded_pixels(self):
        bare = self.source.read_bytes()
        profile = self.w.path('.control/profile.icc')
        encoded = self.w.jpeg('.control/profile-image.jpg')
        images = []
        for data in (ICC_PROFILE, ICC_PROFILE.replace(b'CC0', b'CC1')):
            profile.write_bytes(data)
            encoded.write_bytes(bare)
            subprocess.run([shutil.which('exiftool'), '-overwrite_original',
                '-ICC_Profile<=' + str(profile), str(encoded)], check=True, capture_output=True)
            images.append(encoded.read_bytes())
        for mode in ('create', 'overwrite'):
            self.w.set_policy_for_test(mode)
            for name, original, output in (('lost', images[0], bare),
                    ('changed', images[0], images[1]), ('added', bare, images[0])):
                with self.subTest(mode=mode, change=name):
                    self.source.write_bytes(original)
                    before = {self.source: self.w.observe(self.source)}
                    self.produce(output)
                    result = self.dispatch()
                    self.failed(result, before)
                    self.assertFalse(any(c['tool'] in ('ln', 'mv') for c in result.calls))

    def test_profile_validation_failure_preserves_source(self):
        for response in ({'status': 73}, {'stdout': '[{"ICC_Profile":"invalid"}]'}):
            with self.subTest(response=response):
                before = {self.source: self.w.observe(self.source)}
                self.produce()
                self.w.respond_to('exiftool', '-ICC_Profile', response)
                self.failed(self.dispatch(), before)



def failure_case(mode, scenario):
    def test(self):
        self.w.set_policy_for_test(mode)
        existing = self.source.with_name('photo 雪_stripped.jpg')
        existing.write_bytes(b'preexisting destination')
        before = {p: self.w.observe(p) for p in (self.source, existing)}
        payload = self.source.read_bytes()
        options = {}
        tool, status = 'exiftool', 0
        if scenario == 'before':
            options['status'] = 23; status = 23
        elif scenario == 'valid_then_failure':
            options['status'] = 23; status = 23
        elif scenario == 'partial':
            payload = b'nonempty partial output'; options['status'] = 23; status = 23
        elif scenario == 'corrupt': payload = b'not an image'
        elif scenario == 'truncated': payload = payload[:-20]
        elif scenario == 'empty': payload = b''
        elif scenario in ('encoding', 'dimensions', 'pixels', 'extra_frame'):
            output = self.w.path('.control/wrong.' + ('gif' if scenario == 'extra_frame' else 'png'))
            args = {'encoding': [str(self.source)], 'dimensions': ['-size','2x2','xc:red'],
                    'pixels': ['-size','3x2','xc:red'],
                    'extra_frame': [str(self.source), str(self.source)]}[scenario]
            subprocess.run([shutil.which('magick'), *args, str(output)], check=True)
            if scenario in ('dimensions', 'pixels'):
                jpeg = output.with_suffix('.jpg')
                subprocess.run([shutil.which('magick'), str(output), str(jpeg)], check=True)
                output = jpeg
            payload = output.read_bytes()
        elif scenario == 'publication':
            tool, status = ('mv' if mode == 'overwrite' else 'ln'), 73
            self.w.respond(tool, status=status)
        elif scenario in ('chmod', 'touch'):
            tool, status = scenario, 73
            self.w.respond(tool, status=status)
        elif scenario == 'encoder':
            options['status'] = 127; status = 127
        elif scenario == 'decoder':
            tool, status = 'identify', 127
            self.w.sequence('identify', [{'passthrough': True}, {'status': status}])
        if scenario == 'before':
            self.w.respond('exiftool', **options)
        else:
            self.produce(payload, **options)
        result = self.dispatch()
        self.failed(result, before)
        self.assertTrue(any(e['tool'] == tool and e['status'] == status for e in result.events))
        self.assertFalse(any(c['tool'] == 'cp' for c in result.calls))
        if scenario != 'publication':
            self.assertFalse(any(c['tool'] in ('ln', 'mv') for c in result.calls))
    return test


for _mode in ('create', 'overwrite'):
    for _scenario in ('before','valid_then_failure','partial','corrupt','truncated','empty','encoding','dimensions',
                      'pixels','extra_frame','publication','chmod','touch','encoder','decoder'):
        setattr(StripmetaTests, 'test_' + _mode + '_preserves_on_' + _scenario, failure_case(_mode, _scenario))


def format_case(extension, frames=1):
    def test(self):
        source = self.w.path('input/real.' + extension)
        subprocess.run([shutil.which('magick'), *([str(self.source)] * frames), str(source)],
            check=True, capture_output=True)
        before = self.w.observe(source)
        self.w.use_real_stripmeta()
        result = self.dispatch(source)
        self.assertFalse(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls), result.calls)
        self.assertNotEqual(self.w.observe(source).inode, before.inode)
        self.assertEqual(source.stat().st_mtime_ns, before.mtime_ns)
        decoded = subprocess.run([shutil.which('identify'), '-regard-warnings', '+ping',
            '-format', '%w %h\n', str(source)], check=True, capture_output=True).stdout
        self.assertEqual(decoded, b'3 2\n' * frames)
        self.clean()
    return test


for _extension, _frames in (('jpg',1),('png',1),('tiff',1),('gif',2),('webp',1),('pdf',1),('avif',1),('heic',1)):
    setattr(StripmetaTests, 'test_real_format_' + _extension, format_case(_extension, _frames))


def frame_case(count):
    def test(self):
        source = self.w.path('input/source.gif')
        output = self.w.path('.control/wrong.gif')
        subprocess.run([shutil.which('magick'), str(self.source), str(self.source), str(source)], check=True)
        subprocess.run([shutil.which('magick'), *([str(self.source)] * count), str(output)], check=True)
        self.source = source
        before = {source: self.w.observe(source)}
        self.produce(output.read_bytes())
        self.failed(self.dispatch(), before)
    return test

for _count in (1,3):
    setattr(StripmetaTests, 'test_rejects_wrong_frame_count_' + str(_count), frame_case(_count))
