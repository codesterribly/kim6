"""Rotation and reflection through the dispatcher, using six asymmetric pixels."""
import os
import base64
import shutil
import subprocess
import unittest
from support import Workspace
from test_stripmeta import ICC_PROFILE


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.png('input/photo 雪.png')
        self.w.approve_overwrite()
        self.w.use_real_transform()

    def pixels(self, path):
        result = subprocess.run([shutil.which('magick'), str(path), '-depth', '8', 'rgb:-'],
                                check=True, capture_output=True)
        data = result.stdout
        colors = ['ff0000', '00ff00', '0000ff', 'ffff00', 'ff00ff', '00ffff']
        return [colors.index(data[n:n+3].hex()) for n in range(0, len(data), 3)]

    def clean(self):
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.w.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((self.w.control / 'tmp').iterdir()), [])

    def test_real_clockwise_rotation_preserves_permissions_and_nanoseconds(self):
        self.source.chmod(0o640)
        os.utime(self.source, ns=(1600000000000000000, 1600000001123456789))
        before = self.w.observe(self.source)
        self.w.use_real_mv()
        self.w.use_real_metadata_tools()
        result = self.w.dispatch('rotate', '90', self.source)
        self.assertEqual(self.pixels(self.source), [3, 0, 4, 1, 5, 2], result.stderr)
        self.assertEqual(self.w.observe(self.source).mtime_ns, before.mtime_ns)
        self.assertEqual(self.w.observe(self.source).mode, before.mode)
        self.clean()

    def annotate(self, path, *tags):
        subprocess.run([shutil.which('exiftool'), '-overwrite_original', *tags, str(path)],
                       check=True, capture_output=True)

    def attach_icc(self):
        profile = self.w.path('.control/test.icc')
        profile.write_bytes(ICC_PROFILE)
        self.annotate(self.source, '-ICC_Profile<=' + str(profile))

    def test_lost_icc_profile_is_not_published(self):
        payload = self.source.read_bytes()
        self.attach_icc()
        before = self.w.observe(self.source)
        self.w.respond('magick', stdout='3 2\n', output_base64=base64.b64encode(payload).decode())
        result = self.w.dispatch('flipflop', 'flip', self.source)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
        self.clean()

    def dimensions(self, path):
        return subprocess.run([shutil.which('identify'), '-format', '%m %w %h\n', str(path)],
                              check=True, capture_output=True, text=True).stdout.strip()

    def assert_failed_unchanged(self, result, before):
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state, result.stderr)
        self.assertEqual(result.outputs, {})
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls), result.calls)
        self.assertFalse(any(c['tool'] == 'mogrify' for c in result.calls))
        self.clean()

    def fixture(self, relative, *options):
        output = self.w.path(relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([shutil.which('magick'), str(self.source), *options, str(output)],
                       check=True, capture_output=True)
        return output

    def test_real_exif_auto_orientation_and_wrapper(self):
        source = self.fixture('input/oriented.tiff')
        self.annotate(source, '-Orientation#=6', '-Artist=keep me')
        before = self.w.observe(source)
        result = self.w.dispatch('rotatewithexif', source)
        self.assertEqual(self.pixels(source), [3, 0, 4, 1, 5, 2], result.stderr)
        self.assertEqual(self.dimensions(source), 'TIFF 2 3')
        tags = subprocess.run([shutil.which('exiftool'), '-s3', '-Orientation#', '-Artist', str(source)],
                              check=True, capture_output=True, text=True).stdout.splitlines()
        # Verified against the legacy mogrify -auto-orient command on an owned
        # TIFF: ImageMagick resets orientation and drops the TIFF Artist tag.
        # Do not invent blanket restoration of metadata in this migration.
        self.assertEqual(tags, ['1'])
        self.assertEqual(self.w.observe(source).mtime_ns, before.mtime_ns)
        self.clean()

    def test_real_icc_and_metadata_retained(self):
        self.attach_icc()
        self.annotate(self.source, '-XMP:Title=private title', '-EXIF:Artist=fixture')
        result = self.w.dispatch('rotate', '90', self.source)
        profile = subprocess.run([shutil.which('exiftool'), '-b', '-ICC_Profile', str(self.source)],
                                 check=True, capture_output=True).stdout
        self.assertEqual(profile, ICC_PROFILE, result.stderr)
        tags = subprocess.run([shutil.which('exiftool'), '-s3', '-XMP:Title', '-Artist', str(self.source)],
                              check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertIn('private title', tags)
        self.assertIn('fixture', tags)
        self.assertEqual(self.pixels(self.source), [3, 0, 4, 1, 5, 2])
        self.clean()

    def test_real_animated_gif_frames_timing_and_order(self):
        source = self.w.path('input/animated.gif')
        subprocess.run([shutil.which('magick'), '-delay', '7', str(self.source),
                        '-delay', '13', str(self.source), '-loop', '3', str(source)],
                       check=True, capture_output=True)
        result = self.w.dispatch('rotate', '90', source)
        metadata = subprocess.run([shutil.which('identify'), '-format', '%w %h %T\n', str(source)],
                                  check=True, capture_output=True, text=True).stdout
        self.assertEqual(metadata, '2 3 7\n2 3 13\n', result.stderr)
        self.assertEqual(self.pixels(source), [3, 0, 4, 1, 5, 2] * 2)
        self.clean()

    def test_batch_spaces_unicode_and_parent_symlink(self):
        source2 = self.w.png('input/another image.png')
        parent = self.w.path('linked parent')
        parent.symlink_to(self.source.parent, target_is_directory=True)
        result = self.w.dispatch('rotate', '180', self.source, parent / source2.name)
        for source in (self.source, source2):
            self.assertEqual(self.pixels(source), [5, 4, 3, 2, 1, 0], result.stderr)
        self.clean()

    def test_duplicate_selection_is_not_transformed_twice(self):
        result = self.w.dispatch('rotate', '90', self.source, self.source)
        self.assertEqual(self.pixels(self.source), [3, 0, 4, 1, 5, 2], result.stderr)
        self.assertEqual(len([c for c in result.calls if c['tool'] == 'magick']), 1)
        self.assertTrue(any('Failed: 1' in ' '.join(c['argv']) for c in result.calls))
        self.clean()

    def test_selected_symlink_and_hardlink_are_refused(self):
        alias = self.w.path('input/alias.png')
        alias.symlink_to(self.source.name)
        before = {p: self.w.observe(p) for p in (self.source, alias)}
        result = self.w.dispatch('rotate', '90', alias)
        self.assert_failed_unchanged(result, before)
        alias.unlink()
        os.link(self.source, alias)
        before = {p: self.w.observe(p) for p in (self.source, alias)}
        result = self.w.dispatch('flipflop', 'flop', self.source, alias)
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state)
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))
        self.clean()

    def test_preexisting_sibling_outputs_remain_untouched(self):
        occupied = self.w.png('input/photo 雪_rotated.png')
        dangling = self.w.path('input/photo 雪_flipped.png')
        dangling.symlink_to('absent')
        before = {p: self.w.observe(p) for p in (occupied, dangling)}
        # Explicit in-place approval is configured in setUp.
        result = self.w.dispatch('rotate', '90', self.source)
        self.assertEqual(self.pixels(self.source), [3, 0, 4, 1, 5, 2], result.stderr)
        for path, state in before.items():
            self.assertEqual(self.w.observe(path), state)
        self.clean()

    def test_failure_of_metadata_preparation_preserves_source(self):
        before = self.w.observe(self.source)
        self.w.respond('touch', status=1)
        result = self.w.dispatch('rotate', '90', self.source)
        self.assert_failed_unchanged(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))

    def test_failure_of_permissions_preserves_source(self):
        before = self.w.observe(self.source)
        self.w.respond('chmod', status=1)
        result = self.w.dispatch('flipflop', 'flip', self.source)
        self.assert_failed_unchanged(result, {self.source: before})

    def test_failure_of_staging_preserves_source(self):
        before = self.w.observe(self.source)
        self.w.respond_to('mktemp', str(self.source.parent / '.kim6-stage.XXXXXX'), {'status': 1})
        result = self.w.dispatch('rotate', '90', self.source)
        self.assert_failed_unchanged(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))

    def test_failure_of_publication_preserves_source(self):
        before = self.w.observe(self.source)
        self.w.respond('mv', status=1)
        result = self.w.dispatch('rotate', '90', self.source)
        self.assert_failed_unchanged(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'cp' for c in result.calls))

    def test_unavailable_decoder_preserves_source(self):
        before = self.w.observe(self.source)
        self.w.respond('identify', status=127)
        result = self.w.dispatch('rotate', '90', self.source)
        self.assert_failed_unchanged(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))

    def test_invalid_angle_and_mode_do_not_start_producer(self):
        before = self.w.observe(self.source)
        for args in (('rotate', 'abc'), ('rotate', '90 -strip'), ('flipflop', 'unknown')):
            result = self.w.dispatch(*args, self.source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.w.observe(self.source), before)
            self.assertFalse(any(c['tool'] == 'magick' for c in result.calls))
            self.clean()


def real_transform_case(action, argument, pixels, dimensions):
    def test(self):
        os.utime(self.source, ns=(1600000000000000000, 1600000001123456789))
        before = self.w.observe(self.source)
        self.source.chmod(0o604)
        result = self.w.dispatch(action, argument, self.source)
        self.assertEqual(self.pixels(self.source), pixels, result.stderr)
        self.assertEqual(self.dimensions(self.source), 'PNG ' + dimensions)
        self.assertEqual(self.w.observe(self.source).mode, 0o604)
        if action == 'rotate':
            self.assertEqual(self.w.observe(self.source).mtime_ns, before.mtime_ns)
        else:
            self.assertGreater(self.w.observe(self.source).mtime_ns, before.mtime_ns)
        self.assertFalse(any(c['tool'] == 'mogrify' for c in result.calls))
        producer = next(c for c in result.calls if c['tool'] == 'magick')
        from pathlib import Path
        self.assertEqual(Path(producer['argv'][-1].split(':', 1)[-1]).parent.parent, self.source.parent)
        self.clean()
    return test


for name, args in {
    '180': ('rotate', '180', [5, 4, 3, 2, 1, 0], '3 2'),
    '270': ('rotate', '270', [2, 5, 1, 4, 0, 3], '2 3'),
    'negative90': ('rotate', '-90', [2, 5, 1, 4, 0, 3], '2 3'),
    'signed360': ('rotate', '+360', [0, 1, 2, 3, 4, 5], '3 2'),
    'vertical': ('flipflop', 'flip', [3, 4, 5, 0, 1, 2], '3 2'),
    'horizontal': ('flipflop', 'flop', [2, 1, 0, 5, 4, 3], '3 2'),
    'dashed_flip': ('flipflop', '-flip', [3, 4, 5, 0, 1, 2], '3 2'),
}.items():
    setattr(TransformTests, 'test_real_' + name, real_transform_case(*args))


def producer_failure_case(kind):
    def test(self):
        before = self.w.observe(self.source)
        payload = self.source.read_bytes()
        response = {'stdout': '2 3\n'}
        if kind == 'nonzero':
            response['status'] = 1
        elif kind == 'partial':
            response.update(status=1, output_base64=base64.b64encode(payload[:35]).decode())
        elif kind == 'corrupt':
            response['output_base64'] = base64.b64encode(b'not an image').decode()
        elif kind == 'truncated':
            response['output_base64'] = base64.b64encode(payload[:55]).decode()
        elif kind == 'wrong_encoding':
            # Correct dimensions isolate the encoding check from geometry.
            wrong = self.fixture('.control/wrong.jpg', '-rotate', '90')
            response.update(stdout='2 3\n', output_base64=base64.b64encode(wrong.read_bytes()).decode())
        elif kind in ('wrong_dimensions', 'extra_frame', 'empty'):
            response['output_base64'] = base64.b64encode(b'' if kind == 'empty' else payload).decode()
            if kind == 'extra_frame':
                response['stdout'] = '3 2\n3 2\n'
        self.w.respond('magick', **response)
        result = self.w.dispatch('rotate', '90', self.source)
        self.assert_failed_unchanged(result, {self.source: before})
        self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))
    return test


for kind in ('nonzero', 'partial', 'corrupt', 'truncated', 'wrong_encoding',
             'wrong_dimensions', 'extra_frame', 'empty'):
    setattr(TransformTests, 'test_producer_' + kind, producer_failure_case(kind))


def interruption_case(action, argument, phase, state):
    def test(self):
        second = self.w.png('input/next.png')
        before = {p: self.w.observe(p) for p in (self.source, second)}
        injection = {'interrupt': state, 'passthrough': True}
        if phase == 'before':
            self.w.respond_to('qdbus', 'wasCancelled', {'interrupt': state, 'status': 2})
        elif phase == 'input':
            self.w.respond('identify', **injection)
        elif phase == 'production':
            # Injection at the external producer boundary, followed by real work.
            self.w.respond('magick', **injection)
        elif phase == 'metadata':
            self.w.respond('chmod', **injection)
        result = self.w.dispatch(action, argument, self.source, second)
        self.assert_failed_unchanged(result, before)
        self.assertFalse(any(c['tool'] in ('mv', 'ln') for c in result.calls))
        self.assertLessEqual(len([c for c in result.calls if c['tool'] == 'magick']),
                             0 if phase in ('before', 'input') else 1)
        self.assertTrue(any(c['tool'] == 'qdbus' and c['argv'][2] == 'close' for c in result.calls)
                        or state == 'gone')
    return test


for action, argument, phase, state in (
    ('rotate', '90', 'before', 'cancelled'),
    ('rotate', 'EXIF', 'input', 'gone'),
    ('rotate', '-45.5', 'production', 'gone'),
    ('rotate', '90', 'metadata', 'cancelled'),
    ('flipflop', 'flip', 'before', 'gone'),
    ('flipflop', 'flop', 'input', 'cancelled'),
    ('flipflop', 'flip', 'production', 'query_failed'),
    ('flipflop', 'flop', 'metadata', 'owner_failed'),
    ('rotate', '90', 'metadata', 'malformed'),
):
    setattr(TransformTests, 'test_interruption_' + '_'.join((action, argument.replace('-', 'minus'), phase, state)),
            interruption_case(action, argument, phase, state))


def format_case(extension):
    def test(self):
        source = self.fixture('input/format.' + extension)
        before = self.w.observe(source)
        result = self.w.dispatch('rotate', '90', source)
        self.assertNotEqual(self.w.observe(source).inode, before.inode, result.stderr)
        expected = {'jpg': 'JPEG', 'png': 'PNG', 'gif': 'GIF', 'tiff': 'TIFF',
                    'bmp': 'BMP', 'webp': 'WEBP', 'ppm': 'PPM', 'tga': 'TGA'}[extension]
        actual = self.dimensions(source)
        self.assertEqual(actual.split()[-2:], ['2', '3'])
        self.assertTrue(actual.startswith(expected), actual)
        self.clean()
    return test


for extension in ('jpg', 'png', 'gif', 'tiff', 'bmp', 'webp', 'ppm', 'tga'):
    setattr(TransformTests, 'test_real_format_' + extension, format_case(extension))


def angle_case(angle, dimensions):
    def test(self):
        result = self.w.dispatch('rotate', angle, self.source)
        self.assertEqual(self.dimensions(self.source), 'PNG ' + dimensions, result.stderr)
        self.assertFalse(any('Failed:' in ' '.join(c['argv']) for c in result.calls))
        self.clean()
    return test


for name, angle, dimensions in (('45', '45', '5 6'), ('decimal', '12.5', '5 4'),
                                 ('negative_decimal', '-12.5', '5 4'),
                                 ('landscape_conditional', '90>', '2 3'),
                                 ('portrait_conditional_noop', '90<', '3 2')):
    setattr(TransformTests, 'test_real_custom_' + name, angle_case(angle, dimensions))


def unchanged_encoding_case(name):
    def test(self):
        source = self.w.path('input/' + name)
        source.write_bytes(self.source.read_bytes())
        result = self.w.dispatch('rotate', '90', source)
        self.assertEqual(self.pixels(source), [3, 0, 4, 1, 5, 2], result.stderr)
        self.assertEqual(self.dimensions(source), 'PNG 2 3')
        self.clean()
    return test


for name in ('extensionless', 'misleading.jpg'):
    setattr(TransformTests, 'test_real_encoding_' + name.replace('.', '_'), unchanged_encoding_case(name))


def test_consistent_but_wrong_right_angle_dimensions_are_rejected(self):
    before = self.w.observe(self.source)
    self.w.respond('magick', stdout='3 2\n',
                   output_base64=base64.b64encode(self.source.read_bytes()).decode())
    result = self.w.dispatch('rotate', '90', self.source)
    self.assert_failed_unchanged(result, {self.source: before})
    self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))


TransformTests.test_consistent_but_wrong_right_angle_dimensions_are_rejected = test_consistent_but_wrong_right_angle_dimensions_are_rejected


def exif_orientation_case(orientation, pixels, dimensions):
    def test(self):
        source = self.fixture('input/exif.tiff')
        self.annotate(source, '-Orientation#=' + str(orientation))
        result = self.w.dispatch('rotate', 'EXIF', source)
        self.assertEqual(self.pixels(source), pixels, result.stderr)
        self.assertEqual(self.dimensions(source), 'TIFF ' + dimensions)
        self.clean()
    return test


for orientation, pixels, dimensions in (
    (1, [0, 1, 2, 3, 4, 5], '3 2'),
    (2, [2, 1, 0, 5, 4, 3], '3 2'),
    (3, [5, 4, 3, 2, 1, 0], '3 2'),
    (4, [3, 4, 5, 0, 1, 2], '3 2'),
    (5, [0, 3, 1, 4, 2, 5], '2 3'),
    (7, [5, 2, 4, 1, 3, 0], '2 3'),
    (8, [2, 5, 1, 4, 0, 3], '2 3'),
):
    setattr(TransformTests, 'test_real_exif_orientation_' + str(orientation),
            exif_orientation_case(orientation, pixels, dimensions))


def test_real_optimized_gif_preserves_composited_pixels(self):
    second = self.fixture('input/second.png', '-fill', 'red', '-draw', 'point 2,1')
    source = self.w.path('input/optimized.gif')
    subprocess.run([shutil.which('magick'), '-delay', '7', str(self.source),
                    '-delay', '13', str(second), '-layers', 'Optimize', str(source)],
                   check=True, capture_output=True)
    result = self.w.dispatch('rotate', '90', source)
    actual = subprocess.run([shutil.which('magick'), str(source), '-coalesce', '-depth', '8', 'rgb:-'],
                            check=True, capture_output=True).stdout
    colors = [bytes.fromhex(x) for x in ('ff0000', '00ff00', '0000ff', 'ffff00', 'ff00ff', '00ffff')]
    expected = b''.join(colors[i] for i in [3, 0, 4, 1, 5, 2, 3, 0, 4, 1, 0, 2])
    self.assertEqual(actual, expected, result.stderr)
    self.assertFalse(any('Failed:' in ' '.join(c['argv']) for c in result.calls))
    self.clean()


TransformTests.test_real_optimized_gif_preserves_composited_pixels = test_real_optimized_gif_preserves_composited_pixels


def test_interruption_between_items_keeps_completed_replacement(self):
    second = self.w.png('input/second.png')
    before = self.w.observe(second)
    # Progress initialization sets autoClose and value; the third Set acknowledges
    # the completed first item, then the next shared check sees service loss.
    self.w.respond_to('qdbus', 'org.freedesktop.DBus.Properties.Set',
                      [{}, {}, {'interrupt': 'gone'}])
    result = self.w.dispatch('rotate', '90', self.source, second)
    self.assertEqual(self.pixels(self.source), [3, 0, 4, 1, 5, 2], result.stderr)
    self.assertEqual(self.w.observe(second), before)
    self.assertEqual(len([c for c in result.calls if c['tool'] == 'magick']), 1)
    self.clean()


TransformTests.test_interruption_between_items_keeps_completed_replacement = test_interruption_between_items_keeps_completed_replacement


def test_missing_decoded_frame_preserves_original(self):
    source = self.w.path('input/two.gif')
    subprocess.run([shutil.which('magick'), str(self.source), str(self.source), str(source)],
                   check=True, capture_output=True)
    one = self.fixture('.control/one.gif')
    before = self.w.observe(source)
    self.w.respond('magick', stdout='3 2\n3 2\n', output_base64=base64.b64encode(one.read_bytes()).decode())
    result = self.w.dispatch('rotate', '180', source)
    self.assert_failed_unchanged(result, {source: before})
    self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))


TransformTests.test_missing_decoded_frame_preserves_original = test_missing_decoded_frame_preserves_original


def test_extra_decoded_frame_preserves_original(self):
    source = self.fixture('input/one.gif')
    payload = self.w.path('.control/two.gif')
    subprocess.run([shutil.which('magick'), str(source), str(source), str(payload)],
                   check=True, capture_output=True)
    before = self.w.observe(source)
    self.w.respond('magick', stdout='3 2\n', output_base64=base64.b64encode(payload.read_bytes()).decode())
    result = self.w.dispatch('rotate', '180', source)
    self.assert_failed_unchanged(result, {source: before})
    self.assertFalse(any(c['tool'] == 'mv' for c in result.calls))


TransformTests.test_extra_decoded_frame_preserves_original = test_extra_decoded_frame_preserves_original
