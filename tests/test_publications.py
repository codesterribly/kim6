"""Action-level publication tests for albums, print layouts, TIFF and GIF."""
import os
import base64
import shutil
import subprocess
import unittest
from pathlib import Path

from support import Workspace


class PublicationActionTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env['KIM_POLICY'] = 'create'
        self.w.path('out').mkdir()
        self.first = self.color_ppm('input/first 雪.ppm', (255, 0, 0))
        self.second = self.color_ppm('other/second green.ppm', (0, 255, 0))

    def color_ppm(self, name, rgb, width=2, height=3):
        path = self.w.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f'P6\n{width} {height}\n255\n'.encode() + bytes(rgb) * width * height)
        return path

    def dialogs(self, prompt, choice, output):
        self.w.respond_to('kdialog', prompt, {'stdout': str(choice) + '\n'})
        self.w.respond_to('kdialog', '--getsavefilename', {'stdout': str(output) + '\n'})

    def real(self):
        self.w.use_real_publication_tools()

    def calls(self, result, tool):
        return [call for call in result.calls if call['tool'] == tool]

    def page_info(self, path):
        executable = shutil.which('pdfinfo')
        if not executable:
            self.skipTest('pdfinfo unavailable')
        output = subprocess.run([executable, str(path)], check=True, capture_output=True, text=True).stdout
        values = {}
        for line in output.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                values[key.strip()] = value.strip()
        return values

    def pdf_image_extents(self, path):
        executable = shutil.which('pdfimages')
        if not executable:
            self.skipTest('pdfimages unavailable')
        output = subprocess.run([executable, '-list', str(path)], check=True,
                                capture_output=True, text=True).stdout
        return [(int(fields[3]), int(fields[4]), int(fields[12]), int(fields[13])) for line in output.splitlines()
                if len(fields := line.split()) > 13 and fields[2] == 'image']

    def clean(self):
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.w.root.rglob('.kim6-publish.lock')))
        self.assertEqual(list((self.w.control / 'tmp').iterdir()), [])

    def invoke(self, kind, output):
        if kind == 'album':
            self.dialogs('Kim - Select album type:', 1, output)
            return self.w.dispatch('album', self.w.root, self.first, self.second)
        if kind == 'print':
            self.dialogs('Kim - Select print layout:', 1, output)
            return self.w.dispatch('print', self.w.root, self.first, self.second)
        if kind == 'tiffjoin':
            return self.w.dispatch('tiffjoin', '--output', output, '--', self.first, self.second)
        if kind == 'animate':
            return self.w.dispatch('animate', '--delay', '25', '--loop', '0', '--output', output,
                                   '--', self.first, self.second)
        raise AssertionError('unknown publication action')

    def test_producer_and_validation_failures_preserve_sources_and_existing_targets(self):
        self.real()
        extensions = {'album': 'pdf', 'print': 'pdf', 'tiffjoin': 'tiff', 'animate': 'gif'}
        for kind, extension in extensions.items():
            for failure in ('partial', 'invalid'):
                with self.subTest(action=kind, failure=failure):
                    self.w.env['KIM_POLICY'] = 'overwrite'
                    output = self.w.path(f'out/{kind}-{failure}.{extension}')
                    output.write_bytes(b'preserve destination')
                    before_sources = (self.w.observe(self.first), self.w.observe(self.second))
                    before_output = self.w.observe(output)
                    body = b'partial output' if failure == 'partial' else b'invalid output'
                    self.w.respond('magick', status=19 if failure == 'partial' else 0,
                                   output_base64=base64.b64encode(body).decode())
                    result = self.invoke(kind, output)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.w.observe(self.first), before_sources[0])
                    self.assertEqual(self.w.observe(self.second), before_sources[1])
                    self.assertEqual(self.w.observe(output), before_output)
                    self.assertFalse(any(call['tool'] in ('ln', 'mv') for call in result.calls))
                    self.clean()

    def test_create_collisions_are_numbered_for_every_publication_action(self):
        self.real()
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                self.w.env['KIM_POLICY'] = 'create'
                output = self.w.path(f'out/{kind}.{extension}')
                output.write_bytes(b'keep this occupied entry')
                before = output.read_bytes()
                result = self.invoke(kind, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_bytes(), before)
                numbered = output.with_name(f'{output.stem}_1{output.suffix}')
                self.assertTrue(numbered.is_file())
                if extension == 'pdf':
                    self.assertEqual(self.page_info(numbered).get('Pages'), '2' if kind == 'album' else '1')
                else:
                    formats = subprocess.run([shutil.which('identify'), '-format', '%m\\n', str(numbered)],
                                             check=True, capture_output=True, text=True).stdout.splitlines()
                    self.assertEqual(formats, ['TIFF', 'TIFF'] if extension == 'tiff' else ['GIF', 'GIF'])
                self.clean()

    def test_invalid_destination_parent_fails_without_fallback_or_publication(self):
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                self.w.env['KIM_POLICY'] = 'create'
                output = self.w.path(f'out/missing-parent/{kind}.{extension}')
                before_sources = (self.w.observe(self.first), self.w.observe(self.second))
                result = self.invoke(kind, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.parent.exists())
                self.assertFalse(output.exists())
                self.assertEqual(self.w.observe(self.first), before_sources[0])
                self.assertEqual(self.w.observe(self.second), before_sources[1])
                self.assertFalse(any(call['tool'] in ('ln', 'mv') for call in result.calls))
                self.clean()

    def test_selected_source_cannot_be_used_as_derived_destination(self):
        self.w.env['KIM_POLICY'] = 'overwrite'
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                source = self.color_ppm(f'input/selected.{extension}', (127, 70, 201))
                before = self.w.observe(source)
                if kind == 'album':
                    self.dialogs('Kim - Select album type:', 1, source)
                    result = self.w.dispatch('album', self.w.root, source)
                elif kind == 'print':
                    self.dialogs('Kim - Select print layout:', 1, source)
                    result = self.w.dispatch('print', self.w.root, source)
                elif kind == 'tiffjoin':
                    result = self.w.dispatch('tiffjoin', '--output', source, '--', source)
                else:
                    result = self.w.dispatch('animate', '--delay', '25', '--loop', '0',
                                             '--output', source, '--', source)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.w.observe(source), before)
                self.assertFalse(any(call['tool'] in ('magick', 'ln', 'mv') for call in result.calls))
                self.clean()

    def test_service_loss_after_production_prevents_all_four_publications(self):
        self.real()
        self.w.use_real_mv()
        self.w.env['KIM_POLICY'] = 'overwrite'
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                output = self.w.path(f'out/{kind}-retained.{extension}')
                output.write_bytes(b'keep old output')
                before = self.w.observe(output)
                (self.w.control / 'progress-state').unlink(missing_ok=True)
                self.w.respond('magick', interrupt='gone', passthrough=True)
                result = self.invoke(kind, output)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.w.observe(output), before)
                self.assertFalse(any(call['tool'] in ('ln', 'mv') for call in result.calls))
                self.clean()

    def test_cancel_before_production_starts_no_publication_work(self):
        self.real()
        self.w.env['KIM_POLICY'] = 'create'
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                output = self.w.path(f'out/{kind}-cancelled.{extension}')
                (self.w.control / 'progress-state').write_text('cancelled')
                before_sources = (self.w.observe(self.first), self.w.observe(self.second))
                result = self.invoke(kind, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
                self.assertFalse(any(call['tool'] in ('magick', 'ln', 'mv') for call in result.calls))
                self.assertEqual(self.w.observe(self.first), before_sources[0])
                self.assertEqual(self.w.observe(self.second), before_sources[1])
                (self.w.control / 'progress-state').unlink()
                self.clean()

    def test_authorized_overwrite_publishes_valid_outputs_without_touching_sources(self):
        self.real()
        self.w.use_real_mv()
        self.w.env['KIM_POLICY'] = 'overwrite'
        for kind, extension in (('album', 'pdf'), ('print', 'pdf'),
                                ('tiffjoin', 'tiff'), ('animate', 'gif')):
            with self.subTest(action=kind):
                output = self.w.path(f'out/{kind}-replace.{extension}')
                output.write_bytes(b'old authorized output')
                before_sources = (self.w.observe(self.first), self.w.observe(self.second))
                before_target = self.w.observe(output)
                result = self.invoke(kind, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.w.observe(self.first), before_sources[0])
                self.assertEqual(self.w.observe(self.second), before_sources[1])
                after_target = self.w.observe(output)
                self.assertTrue(after_target.exists)
                self.assertNotEqual(after_target.inode, before_target.inode)
                if extension == 'pdf':
                    self.assertEqual(self.page_info(output).get('Pages'), '2' if kind == 'album' else '1')
                else:
                    formats = subprocess.run([shutil.which('identify'), '-format', '%m\n', str(output)],
                                             check=True, capture_output=True, text=True).stdout.splitlines()
                    self.assertEqual(formats, ['TIFF', 'TIFF'] if extension == 'tiff' else ['GIF', 'GIF'])
                self.assertTrue(any(event['tool'] == 'mv' and
                                    ('--no-copy' in event['argv'] or '--exchange' in event['argv']) and
                                    event['status'] == 0 for event in result.events))
                self.clean()

    def test_album_layout_one_produces_ordered_multipage_pdf(self):
        self.real()
        output = self.w.path('out/album.pdf')
        self.dialogs('Kim - Select album type:', 1, output)
        result = self.w.dispatch('album', self.w.root, self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = self.page_info(output)
        self.assertEqual(info.get('Pages'), '2')
        self.assertEqual(info.get('Page size'), '595 x 842 pts (A4)')
        prefix = self.w.path('out/rendered')
        render = subprocess.run([shutil.which('pdftoppm'), '-f', '1', '-l', '2', '-scale-to', '32',
                                 '-png', str(output), str(prefix)], check=True, capture_output=True)
        rendered = [prefix.parent / f'rendered-{number}.png' for number in (1, 2)]
        pixels = [subprocess.run([shutil.which('magick'), 'identify', '-format', '%[pixel:p{16,16}]',
                                  str(image)], check=True, capture_output=True, text=True).stdout
                  for image in rendered]
        self.assertEqual(pixels, ['srgb(254,0,0)', 'srgb(0,254,0)'])
        self.assertTrue(any(call['tool'] == 'magick' and call['argv'][0] == 'montage'
                            for call in result.calls))
        self.clean()

    def test_album_two_by_two_layout_fits_ordered_images_on_landscape_page(self):
        self.real()
        inputs = [
            self.color_ppm(f'album-grid/{name}.ppm', color, 13, 9)
            for name, color in (('red', (255, 0, 0)), ('green', (0, 255, 0)),
                                ('blue', (0, 0, 255)), ('yellow', (255, 255, 0)))
        ]
        output = self.w.path('out/grid.pdf')
        self.dialogs('Kim - Select album type:', 5, output)
        result = self.w.dispatch('album', self.w.root, *inputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = self.page_info(output)
        self.assertEqual(info.get('Pages'), '1')
        self.assertEqual(info.get('Page size'), '842 x 595 pts (A4)')
        prefix = self.w.path('out/grid-render')
        subprocess.run([shutil.which('pdftoppm'), '-f', '1', '-l', '1', '-scale-to', '128',
                        '-png', str(output), str(prefix)], check=True, capture_output=True)
        image = Path(f'{prefix}-1.png')
        points = [(32, 22), (96, 22), (32, 67), (96, 67)]
        pixels = [subprocess.run([shutil.which('magick'), 'identify', '-format',
                                  f'%[pixel:p{{{x},{y}}}]', str(image)], check=True,
                                 capture_output=True, text=True).stdout for x, y in points]
        self.assertEqual(pixels, ['srgb(254,0,0)', 'srgb(0,254,0)',
                                  'srgb(0,0,254)', 'srgb(254,254,0)'])
        images = self.pdf_image_extents(output)
        self.assertEqual(images, [(840, 580, 72, 72)])
        self.clean()

    def test_all_eight_album_presets_are_available(self):
        self.real()
        page_sizes = {
            1: '595 x 842 pts (A4)', 2: '842 x 595 pts (A4)',
            3: '842 x 595 pts (A4)', 4: '595 x 842 pts (A4)',
            5: '842 x 595 pts (A4)', 6: '595 x 842 pts (A4)',
            7: '842 x 595 pts (A4)', 8: '842 x 595 pts (A4)',
        }
        for number in range(1, 9):
            with self.subTest(layout=number):
                output = self.w.path(f'out/album-{number}.pdf')
                self.dialogs('Kim - Select album type:', number, output)
                result = self.w.dispatch('album', self.w.root, self.first)
                self.assertEqual(result.returncode, 0, result.stderr)
                info = self.page_info(output)
                self.assertEqual(info.get('Pages'), '1')
                self.assertEqual(info.get('Page size'), page_sizes[number])
                self.clean()

    def test_all_seven_print_presets_match_documented_orientation(self):
        self.real()
        expected = {
            1: ('842 x 595 pts (A4)', 1, [(756, 530, 72, 72)]),
            2: ('842 x 1191 pts (A3)', 1, [(293, 870, 72, 72)]),
            3: ('842 x 1191 pts (A3)', 1, [(336, 870, 72, 72)]),
            4: ('842 x 1191 pts (A3)', 1, [(379, 1040, 72, 72)]),
            5: ('842 x 595 pts (A4)', 2, [(719, 577, 72, 72), (719, 577, 72, 72)]),
            6: ('595 x 842 pts (A4)', 1, [(510, 620, 72, 72)]),
            7: ('595 x 842 pts (A4)', 1, [(480, 800, 72, 72)]),
        }
        fixture_sizes = {1: (13, 9), 2: (2, 3), 3: (23, 30), 4: (13, 18),
                         5: (25, 20), 6: (2, 3), 7: (2, 3)}
        physical_cm = {1: (13, 9, 2, 2), 2: (10, 15, 1, 2), 3: (11.5, 15, 1, 2),
                       4: (13, 18, 1, 2), 5: (25, 20, 1, 1)}
        for number, (page_size, expected_pages, expected_extents) in expected.items():
            with self.subTest(layout=number):
                width, height = fixture_sizes[number]
                first = self.color_ppm(f'print-input-{number}/first.ppm', (255, 0, 0), width, height)
                second = self.color_ppm(f'print-input-{number}/second.ppm', (0, 255, 0), width, height)
                output = self.w.path(f'out/print-{number}.pdf')
                self.dialogs('Kim - Select print layout:', number, output)
                result = self.w.dispatch('print', self.w.root, first, second)
                self.assertEqual(result.returncode, 0, result.stderr)
                info = self.page_info(output)
                self.assertEqual(info.get('Page size'), page_size)
                self.assertEqual(info.get('Pages'), str(expected_pages))
                image_extents = self.pdf_image_extents(output)
                self.assertEqual(image_extents, expected_extents)
                if number in physical_cm:
                    target_width, target_height, columns, rows = physical_cm[number]
                    raster_width, raster_height, xppi, yppi = image_extents[0]
                    actual_width = raster_width / columns / xppi * 2.54
                    actual_height = raster_height / rows / yppi * 2.54
                    self.assertAlmostEqual(actual_width, target_width, delta=0.5)
                    self.assertAlmostEqual(actual_height, target_height, delta=0.5)
                prefix = self.w.path(f'out/print-render-{number}')
                subprocess.run([shutil.which('pdftoppm'), '-f', '1', '-l', str(expected_pages),
                                '-scale-to', '128', '-png', str(output), str(prefix)],
                               check=True, capture_output=True)
                for page in range(1, expected_pages + 1):
                    image = Path(f'{prefix}-{page}.png')
                    means = subprocess.run([shutil.which('magick'), 'identify', '-format',
                                            '%[fx:mean.r] %[fx:mean.g]', str(image)],
                                           check=True, capture_output=True, text=True).stdout.split()
                    self.assertEqual(len(means), 2)
                    red_mean, green_mean = map(float, means)
                    if number == 5:
                        if page == 1:
                            self.assertGreater(red_mean, green_mean, f'page {page} should contain first (red) input')
                        else:
                            self.assertGreater(green_mean, red_mean, f'page {page} should contain second (green) input')
                    else:
                        self.assertLess(red_mean, 0.99999, f'page {page} omits red input')
                        self.assertLess(green_mean, 0.99999, f'page {page} omits green input')
                self.clean()

    def test_tiffjoin_preserves_selection_order_and_all_sources(self):
        self.real()
        output = self.w.path('out/joined 雪.tiff')
        self.dialogs('TIFF output', 'unused', output)
        before = (self.first.read_bytes(), self.second.read_bytes())
        result = self.w.dispatch('tiffjoin', self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.first.read_bytes(), before[0])
        self.assertEqual(self.second.read_bytes(), before[1])
        images = subprocess.run([shutil.which('identify'), '-format', '%[pixel:p{0,0}]\n',
                                 str(output)], check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(images), 2)
        self.assertEqual(images, ['srgb(255,0,0)', 'srgb(0,255,0)'])
        self.clean()

    def test_animate_preserves_order_delay_and_infinite_loop(self):
        self.real()
        output = self.w.path('out/animation 雪.gif')
        self.dialogs('Animation output', 'unused', output)
        self.w.respond_to('kdialog', 'Delay between images in centiseconds (100 is one second):', {'stdout': '25\n'})
        self.w.respond_to('kdialog', 'Animation loop count (0 means infinite):', {'stdout': '0\n'})
        before = (self.first.read_bytes(), self.second.read_bytes())
        result = self.w.dispatch('animate', self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.first.read_bytes(), self.second.read_bytes()), before)
        frames = subprocess.run([shutil.which('identify'), '-format', '%T|%[iterations]\n',
                                 str(output)], check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(frames), 2)
        self.assertEqual([item.split('|')[0] for item in frames], ['25', '25'])
        self.assertEqual([subprocess.run([shutil.which('magick'), 'identify', '-format', '%[pixel:p{0,0}]',
                                          f'{output}[{number}]'], check=True, capture_output=True, text=True).stdout
                          for number in (0, 1)], ['srgb(255,0,0)', 'srgb(0,255,0)'])
        verbose = subprocess.run([shutil.which('identify'), '-verbose', str(output)], check=True,
                                 capture_output=True, text=True).stdout
        self.assertEqual(verbose.count('Iterations: 0'), 2)
        self.clean()

    def test_animate_accepts_single_play_without_loop_extension(self):
        self.real()
        output = self.w.path('out/once.gif')
        result = self.w.dispatch('animate', '--delay', '25', '--loop', '1', '--output', output,
                                 '--', self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = subprocess.run([shutil.which('identify'), '-format', '%m\n', str(output)],
                                check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(frames, ['GIF', 'GIF'])
        self.assertNotIn(b'NETSCAPE2.0', output.read_bytes())
        self.clean()

    def test_animate_accepts_zero_delay_default(self):
        self.real()
        output = self.w.path('out/zero-delay.gif')
        result = self.w.dispatch('animate', '--delay', '0', '--loop', '0', '--output', output,
                                 '--', self.first, self.second)
        self.assertEqual(result.returncode, 0, result.stderr)
        delays = subprocess.run([shutil.which('identify'), '-format', '%T\n', str(output)],
                                check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(delays, ['0', '0'])
        self.clean()

    def test_animate_rejects_valid_gif_with_wrong_frame_dimensions(self):
        self.real()
        wrong_one = self.color_ppm('fixtures/wrong-one.ppm', (255, 0, 0), 3, 2)
        wrong_two = self.color_ppm('fixtures/wrong-two.ppm', (0, 255, 0), 3, 2)
        wrong_gif = self.w.path('fixtures/wrong-dimensions.gif')
        subprocess.run([shutil.which('magick'), '--', str(wrong_one), str(wrong_two),
                        '-set', 'delay', '25', '-loop', '0', str(wrong_gif)], check=True,
                       capture_output=True)
        payload = base64.b64encode(wrong_gif.read_bytes()).decode()
        self.w.respond('magick', output_base64=payload)
        output = self.w.path('out/wrong-dimensions.gif')
        result = self.w.dispatch('animate', '--delay', '25', '--loop', '0', '--output', output,
                                 '--', self.first, self.second)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(output.exists())
        self.clean()

    def test_occupied_create_output_is_numbered_and_preserved(self):
        self.real()
        output = self.w.path('out/album.pdf')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'keep existing')
        before = output.read_bytes()
        self.dialogs('Kim - Select album type:', 1, output)
        result = self.w.dispatch('album', self.w.root, self.first)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), before)
        self.assertTrue((output.parent / 'album_1.pdf').is_file())
        self.clean()

    def test_invalid_montage_output_is_not_published(self):
        output = self.w.path('out/album.pdf')
        self.dialogs('Kim - Select album type:', 1, output)
        self.w.respond('magick', output_base64='bm90IGEgcGRm')
        result = self.w.dispatch('album', self.w.root, self.first)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.clean()

    def test_cancellation_before_publication_keeps_existing_pdf(self):
        self.real()
        output = self.w.path('out/album.pdf')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'preserve me')
        before = output.read_bytes()
        self.dialogs('Select album type:', 1, output)
        self.w.respond('magick', interrupt='gone', passthrough=True)
        self.w.env['KIM_POLICY'] = 'overwrite'
        result = self.w.dispatch('album', self.w.root, self.first)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), before)
        self.assertFalse(any(call['tool'] == 'mv' for call in result.calls))
        self.clean()


if __name__ == '__main__':
    unittest.main()
