"""Action-level coverage for safe HTML galleries and photo collages."""
import shutil
import base64
import unittest
from pathlib import Path

from support import Workspace


class GalleryCollageTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.ppm('source/photo.ppm')
        self.w.path('out').mkdir()
        shutil.copytree(Path(__file__).resolve().parents[1] / 'src/gallery', self.w.path('gallery'))

    def test_gallery_never_reuses_or_overwrites_an_occupied_output_directory(self):
        self.w.use_real_gallery_collage()
        self.w.respond('xdg-open', status=0)
        sentinel = self.w.path('out/index.html')
        sentinel.write_text('user-owned gallery index')
        before = self.w.observe(sentinel)
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertEqual(self.w.observe(sentinel), before)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(path.is_dir() and path.name.startswith('kim-gallery-')
                            for path in self.w.path('out').iterdir()))

    def test_modern_grid_layout_retains_sources_and_exact_canvas(self):
        self.w.use_real_gallery_collage()
        other = self.w.ppm('source/second.ppm')
        output = self.w.path('out/grid.png')
        before = (self.w.observe(self.source), self.w.observe(other))
        result = self.w.dispatch(
            'pelemele', '--layout', 'grid', '--canvas', '400x300',
            '--fit', 'fit', '--gap', '12', '--frame', 'none',
            '--no-shadow', '--output', output, '--', self.source, other,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.w.observe(self.source), self.w.observe(other)), before)
        self.assertTrue(output.is_file())
        dims = self.w.command('identify', '-regard-warnings', '-format',
                              '%m|%w|%h|%T|%n|%#\\n', '--', output)
        self.assertTrue(dims.stdout.startswith('PNG|400|300|'), dims.stdout)

    def _assert_modern_layout(self, layout):
        self.w.use_real_gallery_collage()
        second = self.w.ppm('source/second.ppm')
        inputs = (self.source, second)
        before = tuple(self.w.observe(source) for source in inputs)
        output = self.w.path(f'out/{layout}.png')
        result = self.w.dispatch(
            'pelemele', '--layout', layout, '--canvas', '400x300',
            '--gap', '12', '--fit', 'fill', '--frame', 'thin',
            '--no-shadow', '--output', output, '--', *inputs,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        dimensions = self.w.command('identify', '-regard-warnings', '-format',
                                    '%m|%w|%h|%T|%n|%#\\n', '--', output)
        self.assertTrue(dimensions.stdout.startswith('PNG|400|300|'), dimensions.stdout)
        self.assertEqual(tuple(self.w.observe(source) for source in inputs), before)
        self.assertFalse(any(path.name == 'collage-tiles' for path in
                             self.w.path('out').rglob('*')))
        self.assertFalse(any(path.name.startswith('.kim6-stage.') for path in
                             self.w.path('out').iterdir()))

    def test_mosaic_layout_keeps_sources_and_cleans_tiles(self):
        self._assert_modern_layout('mosaic')

    def test_hero_layout_keeps_sources_and_cleans_tiles(self):
        self._assert_modern_layout('hero')

    def test_filmstrip_layout_keeps_sources_and_cleans_tiles(self):
        self._assert_modern_layout('filmstrip')

    def test_grid_failure_does_not_replace_existing_output_or_leave_staging(self):
        self.w.use_real_gallery_collage()
        target = self.w.path('out/previous.png')
        target.write_bytes(b'previous content')
        old = self.w.observe(target)
        self.w.approve_overwrite()
        self.w.respond('magick', status=1)
        result = self.w.dispatch('pelemele', '--layout', 'grid', '--canvas', '400x300',
                                 '--no-shadow', '--output', target, '--', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), old)
        self.assertFalse(any(path.name.startswith('.kim6-stage.') for path in
                             self.w.path('out').iterdir()))

    def test_collage_interactive_options_are_exposed(self):
        self.w.use_real_gallery_collage()
        target = self.w.path('out/interactive.png')
        # Cancel at custom canvas selection to check the full layout UI up to
        # that point without performing a large 3840px encode.
        self.w.respond_to('kdialog', 'Choose a collage layout:', {'stdout': 'grid\n'})
        self.w.respond_to('kdialog', 'Collage canvas size:', {'stdout': 'custom\n'})
        self.w.respond_to('kdialog', 'Canvas dimensions (WIDTHxHEIGHT):', {'stdout': '400x300\n'})
        self.w.respond_to('kdialog', 'Drop shadows:', {'stdout': 'false\n'})
        self.w.respond_to('kdialog', 'Photo order:', {'stdout': 'selected\n'})
        self.w.respond_to('kdialog', '--getsavefilename', {'stdout': str(target) + '\n'})
        result = self.w.dispatch('pelemele', '--', self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_file())
        dialogs = [call['argv'] for call in result.calls if call['tool'] == 'kdialog']
        self.assertTrue(any('Drop shadows:' in argv for argv in dialogs))
        self.assertTrue(any('Photo order:' in argv for argv in dialogs))
        self.assertTrue(any('Collage background:' in argv for argv in dialogs))
        self.assertTrue(any('Custom canvas size' in repr(argv) for argv in dialogs))

    def test_gallery_template_fallback_has_offline_lightbox(self):
        self.w.use_real_gallery_collage()
        gallery_resources = self.w.path('gallery')
        (gallery_resources / 'index.part1').unlink()
        (gallery_resources / 'index.part2').unlink()
        self.w.respond('xdg-open', status=0)
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        directories = [path for path in self.w.path('out').iterdir()
                       if path.name.startswith('kim-gallery-') and path.is_dir()]
        self.assertEqual(len(directories), 1)
        html = (directories[0] / 'index.html').read_text()
        self.assertIn('class="lightbox"', html)
        self.assertIn('ArrowLeft', html)
        self.assertIn('ArrowRight', html)
        self.assertNotIn('https://cdn.', html)

    def test_gallery_resolution_selector_supports_high_resolution(self):
        self.w.use_real_gallery_collage()
        self.w.respond_to('kdialog', 'Gallery image resolution:', {'stdout': '3840\n'})
        self.w.respond('xdg-open', status=0)
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(call['tool'] == 'magick' and '3840x3840>' in call['argv']
                            for call in result.calls))

    def test_modern_collage_rejects_invalid_canvas_before_publication(self):
        self.w.use_real_gallery_collage()
        output = self.w.path('out/invalid.png')
        result = self.w.dispatch(
            'pelemele', '--layout', 'mosaic', '--canvas', '400x0',
            '--no-shadow', '--output', output, '--', self.source,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_pelemele_dispatcher_creates_a_collage_artifact(self):
        self.w.use_real_gallery_collage()
        output = self.w.path('out/collage.png')
        result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '1x1',
                                 '--rotation', '0', '--no-shadow', '--output', output,
                                 '--', self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 0)
        self.assertIn('PNG', self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', output).stdout)

    def test_gallery_builds_escaped_relative_assets_from_mixed_sources(self):
        self.w.use_real_gallery_collage()
        first = self.w.path('left/ <&"雪>.ppm')
        second = self.w.path('right/ <&"雪>.ppm')
        first.parent.mkdir(); second.parent.mkdir()
        first.write_bytes(self.source.read_bytes())
        second.write_bytes(self.source.read_bytes())
        first_before, second_before = self.w.observe(first), self.w.observe(second)
        self.w.respond_to('kdialog', 'Kim - Title:', {'stdout': 'A <title> & "show"\n'})
        self.w.respond_to('kdialog', 'Kim - Author:', {'stdout': "O'Neil & Co\n"})
        self.w.respond_to('kdialog', 'Kim - Number of columns:', {'stdout': '1\n'})
        self.w.sequence('date', [{'stdout': '20261020-123456\n'}, {'stdout': '20261020\n'}])
        self.w.respond('xdg-open', status=0)
        result = self.w.dispatch('gallery', self.w.root, first, second)
        self.assertEqual(result.returncode, 0, result.stderr)
        gallery = self.w.path('out/kim-gallery-20261020-123456')
        html = (gallery / 'index.html').read_text()
        self.assertIn('A &lt;title&gt; &amp; &quot;show&quot;', html)
        self.assertIn('O&#39;Neil &amp; Co', html)
        self.assertIn('&lt;&amp;&quot;雪&gt;.ppm', html)
        self.assertIn('href="images/image_1.ppm"', html)
        self.assertIn('src="thumbs/image_2.png"', html)
        self.assertIn('<main class="gallery"', html)
        self.assertIn('class="lightbox"', html)
        self.assertTrue((gallery / 'images/image_1.ppm').is_file())
        self.assertTrue((gallery / 'thumbs/image_1.png').is_file())
        dims = self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', gallery / 'images/image_1.ppm')
        self.assertIn('|3|2|', dims.stdout)
        self.assertEqual(len(list((gallery / 'images').iterdir())), 2)
        self.assertEqual(self.w.observe(first), first_before)
        self.assertEqual(self.w.observe(second), second_before)
        thumb_dims = self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', gallery / 'thumbs/image_1.png')
        self.assertIn('PNG|3|2|', thumb_dims.stdout)
        browser_calls = [call for call in result.calls if call['tool'] == 'xdg-open']
        self.assertEqual(len(browser_calls), 1)
        self.assertIn(str(gallery / 'index.html'), browser_calls[0]['argv'])

    def test_gallery_suffix_collision_and_symlink_are_never_replaced(self):
        self.w.use_real_gallery_collage()
        self.w.sequence('date', [{'stdout': '20261020-123456\n'}, {'stdout': '20261020\n'}])
        occupied = self.w.path('out/kim-gallery-20261020-123456')
        occupied.mkdir(); (occupied / 'sentinel').write_text('mine')
        linked = self.w.path('out/kim-gallery-20261020-123456_1')
        linked.symlink_to(occupied, target_is_directory=True)
        self.w.respond('xdg-open', status=0)
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((occupied / 'sentinel').read_text(), 'mine')
        self.assertTrue(linked.is_symlink())
        self.assertTrue(self.w.path('out/kim-gallery-20261020-123456_2/index.html').is_file())

    def test_gallery_partial_producer_failure_publishes_nothing_and_cleans_stage(self):
        self.w.use_real_gallery_collage()
        self.w.respond('magick', status=1, output_base64=base64.b64encode(b'partial').decode())
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(path.name.startswith('kim-gallery-') for path in self.w.path('out').iterdir()))
        self.assertFalse(any(path.name.startswith('.kim6-stage.') for path in self.w.path('out').iterdir()))

    def test_gallery_directory_publication_failure_leaves_no_partial_public_tree(self):
        self.w.use_real_gallery_collage()
        self.w.respond('xdg-open', status=0)
        self.w.respond('mv', status=1)
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(path.name.startswith('kim-gallery-') for path in self.w.path('out').iterdir()))
        self.assertFalse(any(path.name.startswith('.kim6-stage.') for path in self.w.path('out').iterdir()))

    def test_gallery_no_clobber_publication_preserves_directory_created_during_processing(self):
        self.w.use_real_gallery_collage()
        self.w.sequence('date', [{'stdout': '20261020-123456\n'}, {'stdout': '20261020\n'}])
        target = self.w.path('out/kim-gallery-20261020-123456')
        self.w.respond('magick', passthrough=True,
                       writes={'out/kim-gallery-20261020-123456/sentinel': 'concurrent owner'})
        result = self.w.dispatch('gallery', self.w.root, self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target / 'sentinel').read_text(), 'concurrent owner')
        self.assertFalse((target / 'index.html').exists())
        self.assertFalse(any(path.name.startswith('.kim6-stage.') for path in self.w.path('out').iterdir()))

    def test_gallery_cancellation_after_asset_generation_prevents_directory_publication(self):
        self.w.use_real_gallery_collage()
        second = self.w.path('source/second.ppm')
        second.write_bytes(self.source.read_bytes())
        self.w.respond('magick', passthrough=True, interrupt='gone')
        result = self.w.dispatch('gallery', self.w.root, self.source, second)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(path.name.startswith('kim-gallery-') for path in self.w.path('out').iterdir()))
        self.assertFalse(any(call['tool'] in ('mv', 'ln') for call in result.calls))
        self.assertEqual(len([call for call in result.calls if call['tool'] == 'magick']), 1)

    def test_collage_invalid_producer_output_and_service_loss_are_never_published(self):
        self.w.use_real_gallery_collage()
        target = self.w.path('out/collage.png')
        target.write_bytes(b'owned destination')
        original = self.w.observe(target)
        self.w.approve_overwrite()
        self.w.respond('magick', status=0, output_base64=base64.b64encode(b'invalid').decode())
        result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '1x1',
                                 '--rotation', '0', '--no-shadow', '--output', target, '--', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), original)
        self.assertFalse(any(call['tool'] == 'mv' for call in result.calls))

    def test_collage_stops_before_publication_when_service_disappears_after_production(self):
        self.w.use_real_gallery_collage()
        second = self.w.path('source/second.ppm')
        second.write_bytes(self.source.read_bytes())
        target = self.w.path('out/collage.png')
        target.write_bytes(b'authorized existing output')
        original = self.w.observe(target)
        self.w.approve_overwrite()
        self.w.respond('magick', passthrough=True, interrupt='gone')
        result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '1x1',
                                 '--rotation', '0', '--no-shadow', '--output', target, '--', self.source, second)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), original)
        self.assertFalse(any(call['tool'] in ('mv', 'ln') for call in result.calls))
        self.assertTrue(any(call['tool'] == 'qdbus' and call['argv'][2] == 'close' for call in result.calls))
        self.assertEqual(len([call for call in result.calls if call['tool'] == 'magick' and call['argv'][:1] == ['--']]), 1)

    def test_collage_publication_failure_preserves_authorized_destination(self):
        self.w.use_real_gallery_collage()
        target = self.w.path('out/collage.png')
        target.write_bytes(b'authorized prior collage')
        before = self.w.observe(target)
        self.w.approve_overwrite()
        self.w.respond_to('mv', str(target), {'status': 73, 'stderr': 'injected publication failure'})
        result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '1x1',
                                 '--rotation', '0', '--no-shadow', '--output', target, '--', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), before)
        self.assertFalse(any(call['tool'] == 'cp' for call in result.calls))

    def test_collage_random_rotation_is_seeded_and_preserves_shadow_setting(self):
        self.w.use_real_gallery_collage()
        second = self.w.path('source/second.ppm')
        second.write_bytes(self.source.read_bytes())
        rotations = []
        signatures = []
        for name in ('random-one.png', 'random-two.png'):
            output = self.w.path('out/' + name)
            result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '2x1',
                                     '--overlap', '0', '--background', '#ffffff', '--border', '2',
                                     '--random-rotation', '15', '--seed', '1234', '--shadow',
                                     '--output', output, '--', self.source, second)
            self.assertEqual(result.returncode, 0, result.stderr)
            tile_calls = [call['argv'] for call in result.calls
                          if call['tool'] == 'magick' and call['argv'][:1] == ['--']]
            rotations.append([argv[argv.index('-rotate') + 1] for argv in tile_calls])
            self.assertTrue(all('-shadow' in argv for argv in tile_calls))
            signature = self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', output)
            signatures.append(signature.stdout)
        self.assertEqual(rotations[0], rotations[1])
        self.assertEqual(signatures[0], signatures[1])

    def test_collage_preserves_selected_tile_order_and_real_pixel_content(self):
        self.w.use_real_gallery_collage()
        red = self.w.path('left/red[0].ppm')
        green = self.w.path('right/green.ppm')
        red.parent.mkdir(); green.parent.mkdir()
        red.write_bytes(b'P6\n2 2\n255\n' + bytes([255, 0, 0] * 4))
        green.write_bytes(b'P6\n2 2\n255\n' + bytes([0, 255, 0] * 4))
        output = self.w.path('out/ordered.png')
        result = self.w.dispatch('pelemele', '--size', '10x10', '--tile', '2x1',
                                 '--overlap', '0', '--background', 'white', '--border', '0',
                                 '--rotation', '0', '--no-shadow', '--output', output, '--', red, green)
        self.assertEqual(result.returncode, 0, result.stderr)
        dimensions = self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', output)
        self.assertIn('PNG|24|12|', dimensions.stdout)
        pixels = self.w.command('identify', '-regard-warnings', '-format',
                                '%[pixel:p{5,5}]|%[pixel:p{17,5}]', '--', output)
        self.assertEqual(pixels.stdout, 'srgb(255,0,0)|srgb(0,255,0)')

    def test_collage_accepts_spaced_safe_background_colors(self):
        self.w.use_real_gallery_collage()
        output = self.w.path('out/spaced-color.png')
        result = self.w.dispatch('pelemele', '--size', '20x20', '--tile', '1x1',
                                 '--overlap', '0', '--background', 'light goldenrod',
                                 '--rotation', '0', '--no-shadow', '--output', output, '--', self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_file())

    def test_collage_uses_options_and_never_changes_source_or_occupied_target(self):
        self.w.use_real_gallery_collage()
        before = self.w.observe(self.source)
        second = self.w.path('source/second.ppm')
        second.write_bytes(self.source.read_bytes())
        output = self.w.path('out/collage.png')
        output.write_bytes(b'user destination')
        prior = self.w.observe(output)
        result = self.w.dispatch('pelemele', '--size', '40x40', '--tile', '2x1',
                                 '--overlap', '0', '--background', 'white', '--border', '0',
                                 '--rotation', '0', '--no-shadow', '--output', output, '--',
                                 self.source, second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertEqual(self.w.observe(output), prior)
        numbered = self.w.path('out/collage_1.png')
        self.assertTrue(numbered.is_file())
        dims = self.w.command('identify', '-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n', '--', numbered)
        _, width, height, *_ = dims.stdout.strip().split('|')
        width, height = int(width), int(height)
        self.assertGreater(width, 40)
        self.assertGreater(height, 0)

    def test_collage_never_follows_output_symlink_or_aliases_a_selected_source(self):
        self.w.use_real_gallery_collage()
        sentinel = self.w.path('out/sentinel.png')
        sentinel.write_bytes(b'user-owned target')
        link = self.w.path('out/link.png')
        link.symlink_to(sentinel)
        result = self.w.dispatch('pelemele', '--size', '20x20', '--tile', '1x1',
                                 '--rotation', '0', '--no-shadow', '--output', link, '--', self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b'user-owned target')
        self.assertTrue(self.w.path('out/link_1.png').is_file())

        selected_png = self.w.path('source/selected.png')
        selected_png.write_bytes(self.source.read_bytes())
        before = self.w.observe(selected_png)
        self.w.approve_overwrite()
        alias = self.w.dispatch('pelemele', '--size', '20x20', '--tile', '1x1',
                                '--rotation', '0', '--no-shadow', '--output', selected_png,
                                '--', selected_png)
        self.assertNotEqual(alias.returncode, 0)
        self.assertEqual(self.w.observe(selected_png), before)


if __name__ == '__main__':
    unittest.main()
