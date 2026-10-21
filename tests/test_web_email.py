"""Action-level web export and resize-to-email behavior."""
import unittest
import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from support import Workspace


class WebEmailTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

    def test_web_export_accepts_action_local_preset_arguments(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo with [brackets].ppm')
        output_dir = self.w.path('export')
        output_dir.mkdir()
        before = self.w.observe(source)
        result = self.w.dispatch('webexport', '--size', '2x2', '--quality', '81',
                                 '--format', 'webp', '--output-dir', output_dir,
                                 '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(source), before)
        outputs = list(output_dir.iterdir())
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].name, 'photo with [brackets]_web.webp')
        self.assertEqual(self.w.image_info(outputs[0])[:3], ('WEBP', 2, 1))

    def test_web_export_uses_config_format_and_env_precedence_and_keep_encoding(self):
        self.w.use_real_web_email()
        self.w.configure('WEB_EXPORT_FORMAT', 'webp')
        self.w.configure('WEB_EXPORT_QUALITY', '63')
        source = self.w.ppm('input/portrait.ppm')
        destination = self.w.path('exports')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--output-dir', destination,
                                 '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.image_info(next(destination.iterdir()))[0], 'WEBP')

        self.w.env['KIM_WEB_FORMAT'] = 'keep'
        second = self.w.path('exports-keep')
        second.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--output-dir', second,
                                 '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = next(second.iterdir())
        self.assertEqual(output.suffix, '.ppm')
        self.assertEqual(self.w.image_info(output)[0], 'PPM')

    def test_web_export_encodes_each_supported_configured_format(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        formats = subprocess.run([magick, '-list', 'format'], capture_output=True, text=True, check=True).stdout
        source = self.w.ppm('input/photo.ppm')
        for extension, expected, format_line in (
            ('jpg', 'JPEG', r'^\s*JPEG\*?\s'),
            ('webp', 'WEBP', r'^\s*WEBP\*?\s'),
            ('avif', 'AVIF', r'^\s*AVIF\*?\s'),
        ):
            with self.subTest(extension=extension):
                if not any(__import__('re').search(format_line, line) and len(line.split()) > 2
                           and 'w' in line.split()[2] for line in formats.splitlines()):
                    continue
                destination = self.w.path('exports-' + extension)
                destination.mkdir()
                result = self.w.dispatch('webexport', '--size', '2x2', '--quality', '82',
                                         '--format', extension, '--output-dir', destination,
                                         '--', source)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = next(destination.iterdir())
                self.assertEqual(output.suffix, '.' + extension)
                self.assertEqual(self.w.image_info(output), (expected, 2, 1))

    def test_web_export_preserves_all_decodable_animation_frames(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        if not magick:
            self.skipTest('ImageMagick is unavailable')
        first = self.w.ppm('input/first.ppm')
        second = self.w.ppm('input/second.ppm')
        second.write_bytes(b'P6\n3 2\n255\n' + bytes.fromhex(
            '000000 000000 000000 000000 ffffff 000000'))
        animation = self.w.path('input/animation.gif')
        subprocess.run([magick, str(first), str(second), str(animation)], check=True,
                       capture_output=True, timeout=15)
        before = self.w.observe(animation)
        output_dir = self.w.path('exports')
        output_dir.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--output-dir', output_dir, '--', animation)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = next(output_dir.iterdir())
        decoded = subprocess.run([magick, 'identify', '-format', '%m %w %h %n\\n',
                                  str(output)], check=True, capture_output=True,
                                 text=True, timeout=15).stdout.splitlines()
        self.assertEqual(decoded, ['GIF 3 2 2', 'GIF 3 2 2'])
        self.assertEqual(self.w.observe(animation), before)

    def test_web_export_rejects_apng_when_image_magick_would_flatten_frames(self):
        self.w.use_real_conversion()
        self.w.use_real_video_tools()
        first = self.w.ppm('input/apng-first.ppm')
        second = self.w.ppm('input/apng-second.ppm')
        second.write_bytes(b'P6\n3 2\n255\n' + bytes.fromhex(
            '000000 000000 000000 000000 ffffff 000000'))
        source_gif = self.w.path('input/source.gif')
        subprocess.run([shutil.which('magick'), '-delay', '10', str(first),
                        '-delay', '20', str(second), str(source_gif)], check=True,
                       capture_output=True, timeout=15)
        apng = self.w.dispatch('convert', 'apng', source_gif)
        self.assertTrue(source_gif.with_suffix('.apng').is_file(), apng.events)
        source = source_gif.with_suffix('.apng')
        before = self.w.observe(source)
        self.w.use_real_web_email()
        destination = self.w.path('apng-export')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call['tool'] == 'magick' for call in result.calls))
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(self.w.observe(source), before)

    def test_web_export_normalizes_orientation_and_embeds_srgb_profile_by_default(self):
        self.w.use_real_web_email()
        exiftool = shutil.which('exiftool')
        if not exiftool:
            self.skipTest('ExifTool is unavailable for the orientation/profile fixture')
        from test_stripmeta import ICC_PROFILE
        profile = self.w.path('.control/test.icc')
        profile.write_bytes(ICC_PROFILE)
        source = self.w.jpeg('input/oriented.jpg')
        subprocess.run([exiftool, '-overwrite_original', '-EXIF:Orientation#=6',
                        '-ICC_Profile<=' + str(profile), str(source)], check=True, capture_output=True)
        before = self.w.observe(source)
        destination = self.w.path('exports')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '4x4', '--quality', '75',
                                 '--format', 'jpg', '--output-dir', destination,
                                 '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = next(destination.iterdir())
        self.assertEqual(self.w.image_info(output), ('JPEG', 3, 4))
        self.assertEqual(self.w.observe(source), before)
        profile_result = subprocess.run([exiftool, '-b', '-ICC_Profile', str(output)],
                                        check=True, capture_output=True)
        self.assertTrue(profile_result.stdout, 'default sRGB export carries its output ICC profile')
        orientation = subprocess.run([exiftool, '-s3', '-Orientation', str(output)],
                                     check=True, capture_output=True, text=True)
        self.assertEqual(orientation.stdout.strip(), '')

    def test_web_export_performs_real_adobe_rgb_to_srgb_transform(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        adobe = Path('/usr/share/color/icc/colord/AdobeRGB1998.icc')
        srgb = Path('/usr/share/color/icc/ghostscript/srgb.icc')
        if not magick or not adobe.is_file() or not srgb.is_file():
            self.skipTest('ImageMagick and Adobe RGB/sRGB profiles are required')
        ppm = self.w.ppm('input/adobe-source.ppm')
        ppm.write_bytes(b'P6\n3 2\n255\n' + bytes.fromhex(
            '9a5a32 8040b0 30a080 6050a0 b07040 2288aa'))
        source = self.w.path('input/adobe-source.tif')
        subprocess.run([magick, str(ppm), '-profile', str(adobe), str(source)],
                       check=True, capture_output=True, timeout=15)
        before = self.w.observe(source)
        source_pixel = subprocess.run([magick, str(source), '-format', '%[pixel:p{0,0}]', 'info:'],
                                      check=True, capture_output=True, text=True).stdout
        destination = self.w.path('srgb-export')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--output-dir', destination, '--', source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output = destination / 'adobe-source_web.tif'
        output_pixel = subprocess.run([magick, str(output), '-format', '%[pixel:p{0,0}]', 'info:'],
                                      check=True, capture_output=True, text=True).stdout
        self.assertNotEqual(output_pixel, source_pixel, 'ICC conversion changes encoded color samples')
        profile_name = subprocess.run([magick, str(output), '-format', '%[profile:icc]', 'info:'],
                                      check=True, capture_output=True, text=True).stdout
        self.assertRegex(profile_name, r'(?i)sRGB')
        self.assertEqual(self.w.observe(source), before)

    def test_web_export_transforms_display_p3_and_tagged_cmyk_when_profiles_exist(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        exiftool = shutil.which('exiftool')
        srgb = Path('/usr/share/color/icc/ghostscript/srgb.icc')
        profiles = (
            ('display-p3', Path('/usr/share/color/icc/DisplayP3-v2-micro.icc'), 'RGB'),
            ('tagged-cmyk', Path('/usr/share/color/icc/ghostscript/default_cmyk.icc'), 'CMYK'),
        )
        available = [(name, profile, space) for name, profile, space in profiles if profile.is_file()]
        if not magick or not exiftool or not srgb.is_file() or not available:
            self.skipTest('ImageMagick, ExifTool, or Display P3/CMYK ICC profiles are unavailable')
        for name, profile, space in available:
            with self.subTest(profile=name):
                ppm = self.w.ppm('input/' + name + '.ppm')
                ppm.write_bytes(b'P6\n3 2\n255\n' + bytes.fromhex(
                    'ff1808 8040b0 30a080 6050a0 b07040 2288aa'))
                source = self.w.path('input/' + name + '.tif')
                args = [magick, str(ppm)]
                if space == 'CMYK':
                    args.extend(['-profile', str(srgb)])
                args.extend(['-profile', str(profile), str(source)])
                subprocess.run(args, check=True, capture_output=True, timeout=15)
                before = self.w.observe(source)
                source_pixel = subprocess.run([magick, str(source), '-format', '%[pixel:p{0,0}]', 'info:'],
                                              check=True, capture_output=True, text=True).stdout
                destination = self.w.path(name + '-srgb')
                destination.mkdir()
                result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                         '--output-dir', destination, '--', source)
                self.assertEqual(result.returncode, 0, (name, result.stderr, result.events))
                output = destination / (name + '_web.tif')
                output_pixel = subprocess.run([magick, str(output), '-format', '%[pixel:p{0,0}]', 'info:'],
                                              check=True, capture_output=True, text=True).stdout
                self.assertNotEqual(output_pixel, source_pixel,
                                    'profile transform must change encoded samples when source profile differs')
                output_profile = subprocess.run([magick, str(output), '-format', '%[profile:icc]', 'info:'],
                                                check=True, capture_output=True, text=True).stdout
                self.assertRegex(output_profile, r'(?i)sRGB')
                self.assertEqual(self.w.observe(source), before)

    def test_web_preserve_mode_retains_embedded_profile_and_config_fallback(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        adobe = Path('/usr/share/color/icc/colord/AdobeRGB1998.icc')
        if not magick or not adobe.is_file():
            self.skipTest('Adobe RGB ICC profile is unavailable')
        source_ppm = self.w.ppm('input/profile.ppm')
        source = self.w.path('input/profile.tif')
        subprocess.run([magick, str(source_ppm), '-profile', str(adobe), str(source)],
                       check=True, capture_output=True, timeout=15)
        self.w.configure('WEB_COLOR_MODE', 'preserve')
        destination = self.w.path('preserve-export')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--output-dir', destination, '--', source)
        self.assertEqual(result.returncode, 0, (result.stderr, result.events))
        output_profile = subprocess.run([magick, str(destination / 'profile_web.tif'),
                                          '-format', '%[profile:icc]', 'info:'],
                                        check=True, capture_output=True, text=True).stdout
        self.assertRegex(output_profile, r'(?i)Adobe RGB')

        self.w.env['KIM_WEB_COLOR_MODE'] = 'srgb'
        override = self.w.path('environment-srgb-export')
        override.mkdir()
        overridden = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                     '--output-dir', override, '--', source)
        self.assertEqual(overridden.returncode, 0, (overridden.stderr, overridden.events))
        override_profile = subprocess.run([magick, str(override / 'profile_web.tif'),
                                             '-format', '%[profile:icc]', 'info:'],
                                           check=True, capture_output=True, text=True).stdout
        self.assertRegex(override_profile, r'(?i)sRGB')

    def test_web_export_rejects_untagged_cmyk_in_srgb_mode(self):
        self.w.use_real_web_email()
        magick = shutil.which('magick')
        if not magick:
            self.skipTest('ImageMagick is unavailable')
        ppm = self.w.ppm('input/cmyk-pixels.ppm')
        source = self.w.path('input/untagged-cmyk.tif')
        subprocess.run([magick, str(ppm), '-colorspace', 'CMYK', str(source)],
                       check=True, capture_output=True, timeout=15)
        before = self.w.observe(source)
        destination = self.w.path('cmyk-export')
        destination.mkdir()
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--color', 'srgb', '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertEqual(self.w.observe(source), before)

    def test_web_collision_and_service_loss_never_replace_or_publish(self):
        self.w.use_real_web_email()
        source = self.w.jpeg('input/photo.jpg')
        destination = self.w.path('exports')
        destination.mkdir()
        occupied = destination / 'photo_web.webp'
        occupied.write_bytes(b'user-owned')
        self.w.env['KIM_WEB_FORMAT'] = 'webp'
        self.w.respond('magick', passthrough=True, interrupt='gone')
        result = self.w.dispatch('webexport', '--size', '2x2', '--output-dir', destination,
                                 '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(occupied.read_bytes(), b'user-owned')
        self.assertFalse((destination / 'photo_web_1.webp').exists())
        self.assertFalse(any(call['tool'] in ('ln', 'mv') for call in result.calls))

    def test_web_export_rejects_invalid_zero_exit_artifacts_before_publication(self):
        source = self.w.ppm('input/photo.ppm')
        destination = self.w.path('exports')
        destination.mkdir()
        self.w.env.update({'KIM_WEB_FORMAT': 'webp'})
        self.w.respond('magick', status=0, output_base64=base64.b64encode(b'not a webp').decode())
        result = self.w.dispatch('webexport', '--size', '2x2', '--quality', '75',
                                 '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])

    def test_web_export_rejects_jpeg_bytes_under_webp_and_nonempty_failed_output(self):
        source = self.w.ppm('input/photo.ppm')
        destination = self.w.path('exports')
        destination.mkdir()
        self.w.respond('magick', status=0,
                       output_base64=base64.b64encode(self.w.jpeg('input/valid.jpg').read_bytes()).decode())
        self.w.env['KIM_WEB_FORMAT'] = 'webp'
        result = self.w.dispatch('webexport', '--size', '2x2', '--quality', '75',
                                 '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])

    def test_web_export_rejects_valid_but_unexpectedly_small_resize_output(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        destination = self.w.path('exports')
        destination.mkdir()
        tiny = self.w.path('.control/tiny.ppm')
        tiny.write_bytes(b'P6\n1 1\n255\n\xff\x00\x00')
        self.w.respond('magick', status=0,
                       output_base64=base64.b64encode(tiny.read_bytes()).decode())
        result = self.w.dispatch('webexport', '--size', '3x2', '--format', 'keep',
                                 '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])

        self.w.respond('magick', status=1,
                       output_base64=base64.b64encode(b'partial but nonempty').decode())
        result = self.w.dispatch('webexport', '--size', '2x2', '--quality', '75',
                                 '--output-dir', destination, '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(destination.iterdir()), [])

    def test_email_size_option_attaches_only_valid_completed_images(self):
        self.w.use_real_web_email()
        first = self.w.ppm('input/fail [one].ppm')
        second = self.w.ppm('input/good 雪.ppm')
        first_before = self.w.observe(first)
        second_before = self.w.observe(second)
        self.w.sequence('magick', [
            {'status': 1, 'output_base64': base64.b64encode(b'partial').decode()},
            {'passthrough': True},
        ])
        result = self.w.dispatch('resizeandsend', '--size', '2x2', '--', first, second)
        self.assertNotEqual(result.returncode, 0, 'an image failure must be reflected in action status')
        mail = next(call for call in result.calls if call['tool'] == 'kmail')
        self.assertIn('--attach', mail['argv'])
        attached = [Path(mail['argv'][index + 1]) for index, value in enumerate(mail['argv'][:-1])
                    if value == '--attach']
        self.assertEqual(len(attached), 1)
        self.assertTrue(attached[0].name.startswith('good 雪__send_2.'))
        self.assertEqual(self.w.image_info(attached[0])[:3], ('PPM', 2, 1))
        self.assertTrue(attached[0].is_file(), 'successful handoff attachments must outlive the action')
        self.assertNotIn('stages', [path.name for path in attached])
        self.assertEqual(self.w.observe(first), first_before)
        self.assertEqual(self.w.observe(second), second_before)

    def test_email_rejects_valid_but_unexpectedly_small_resize_output(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        tiny = self.w.path('.control/tiny.ppm')
        tiny.write_bytes(b'P6\n1 1\n255\n\xff\x00\x00')
        self.w.respond('magick', status=0,
                       output_base64=base64.b64encode(tiny.read_bytes()).decode())
        result = self.w.dispatch('resizeandsend', '--size', '3x2', '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call['tool'] in ('kmail', 'thunderbird', 'xdg-email')
                             for call in result.calls))

    def test_email_client_failure_removes_only_its_persistent_attachment_directory(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        self.w.respond('kmail', status=42)
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list((Path(self.w.env['XDG_DATA_HOME']) / 'kim6/email-attachments').glob('attachments.*')))
        self.assertEqual(self.w.image_info(source)[0], 'PPM')

    def test_email_all_size_presets_and_custom_geometry_are_action_local(self):
        self.w.use_real_web_email()
        source = self.w.jpeg('input/photo.jpg')
        expected_dimensions = {
            '1600x1600': (1600, 1067), '1200x1200': (1200, 800),
            '800x800': (800, 533), '600x600': (600, 400),
            '300x300': (300, 200), '2x2': (2, 1),
        }
        for size, expected in expected_dimensions.items():
            with self.subTest(size=size):
                result = self.w.dispatch('resizeandsend', '--size', size, '--', source)
                self.assertEqual(result.returncode, 0, result.stderr)
                producer = next(call for call in result.calls if call['tool'] == 'magick')
                self.assertIn(size, producer['argv'])
                attachment_args = next(call for call in result.calls if call['tool'] == 'kmail')['argv']
                path = Path(attachment_args[1])
                self.assertTrue(path.is_file())
                self.assertEqual(self.w.image_info(path)[1:], expected)

    def test_email_multiple_unicode_bracket_and_leading_dash_attachments_are_explicit(self):
        self.w.use_real_web_email()
        left = self.w.path('left/-same [one].ppm')
        right = self.w.path('right/same [one].ppm')
        left.parent.mkdir(); right.parent.mkdir()
        left.write_bytes(self.w.ppm('input/base.ppm').read_bytes())
        right.write_bytes(left.read_bytes())
        first, second = self.w.observe(left), self.w.observe(right)
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', left, right)
        self.assertEqual(result.returncode, 0, result.stderr)
        mail = next(call for call in result.calls if call['tool'] == 'kmail')
        paths = [Path(mail['argv'][index + 1]) for index, value in enumerate(mail['argv'][:-1])
                 if value == '--attach']
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1])
        self.assertIn('[one]', paths[0].name)
        self.assertEqual([path.read_bytes() for path in paths], [left.read_bytes(), right.read_bytes()])
        self.assertEqual(self.w.observe(left), first)
        self.assertEqual(self.w.observe(right), second)
        self.assertEqual(len(mail['argv']), 4)

    def test_email_corrects_a_misleading_source_extension_and_refuses_source_links(self):
        self.w.use_real_web_email()
        source = self.w.path('input/misleading.jpg')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(self.w.ppm('input/pixels.ppm').read_bytes())
        before = self.w.observe(source)
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        mail = next(call for call in result.calls if call['tool'] == 'kmail')
        attachment = Path(mail['argv'][1])
        self.assertTrue(attachment.name.endswith('.ppm'))
        self.assertEqual(self.w.image_info(attachment)[0], 'PPM')
        self.assertEqual(self.w.observe(source), before)

        link = self.w.path('input/link.ppm')
        link.symlink_to(source)
        rejected = self.w.dispatch('resizeandsend', '--size', 'full', '--', link)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(any(call['tool'] in ('kmail', 'thunderbird', 'xdg-email')
                             for call in rejected.calls))

    def test_email_service_loss_before_first_item_stops_without_mail_handoff(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        (self.w.control / 'progress-state').write_text('gone')
        result = self.w.dispatch('resizeandsend', '--size', '2x2', '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call['tool'] in ('magick', 'cp', 'kmail', 'thunderbird', 'xdg-email')
                             for call in result.calls))
        self.assertFalse(list((Path(self.w.env['XDG_DATA_HOME']) / 'kim6/email-attachments').glob('attachments.*')))

    def test_email_thunderbird_and_xdg_email_receive_safe_multiple_file_arguments(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/space 雪 [a].ppm')
        self.w.bin.joinpath('kmail').unlink()
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        thunderbird = next(call for call in result.calls if call['tool'] == 'thunderbird')
        self.assertEqual(thunderbird['argv'][0], '-compose')
        self.assertIn('%20', thunderbird['argv'][1])
        self.assertIn('%E9%9B%AA', thunderbird['argv'][1])

        self.w.bin.joinpath('thunderbird').unlink()
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        xdg = next(call for call in result.calls if call['tool'] == 'xdg-email')
        self.assertEqual(xdg['argv'][0::2], ['--attach'])
        self.assertEqual(len(xdg['argv']), 2)

    def test_email_rejects_zero_exit_invalid_output_and_does_not_open_a_client(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        before = self.w.observe(source)
        self.w.respond('magick', status=0,
                       output_base64=base64.b64encode(b'invalid pixels').decode())
        result = self.w.dispatch('resizeandsend', '--size', '2x2', '--', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call['tool'] in ('kmail', 'thunderbird', 'xdg-email') for call in result.calls))
        self.assertEqual(self.w.observe(source), before)

    def test_email_cancellation_keeps_prior_completed_files_but_stops_handoff_and_batch(self):
        self.w.use_real_web_email()
        sources = [self.w.ppm(f'input/photo-{number}.ppm') for number in range(3)]
        self.w.sequence('magick', [{'passthrough': True},
                                   {'passthrough': True, 'interrupt': 'gone'}])
        result = self.w.dispatch('resizeandsend', '--size', '2x2', '--', *sources)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len([call for call in result.calls if call['tool'] == 'magick']), 2)
        self.assertFalse(any(call['tool'] in ('kmail', 'thunderbird', 'xdg-email') for call in result.calls))
        folders = list((Path(self.w.env['XDG_DATA_HOME']) / 'kim6/email-attachments').glob('attachments.*'))
        self.assertEqual(len(folders), 1)
        self.assertEqual(len(list(folders[0].iterdir())), 1)

    def test_email_no_client_fallback_keeps_images_in_reported_persistent_location(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        for client in ('kmail', 'thunderbird', 'xdg-email'):
            (self.w.bin / client).unlink()
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        message = next(call for call in result.calls if call['tool'] == 'kdialog' and '--msgbox' in call['argv'])
        self.assertIn('delete the folder when finished', message['argv'][-1])
        reported = next((Path(self.w.env['XDG_DATA_HOME']) / 'kim6/email-attachments').glob('attachments.*'))
        self.assertIn(str(reported), message['argv'][-1])
        self.assertTrue(reported.is_dir())
        attachments = list(reported.iterdir())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].read_bytes(), source.read_bytes())
        self.assertEqual(self.w.image_info(attachments[0])[:3], ('PPM', 3, 2))

    def test_email_async_client_can_read_attachments_after_action_process_exits(self):
        self.w.use_real_web_email()
        source = self.w.ppm('input/photo.ppm')
        client = self.w.bin / 'kmail'
        client.unlink()
        client.write_text('''#!/usr/bin/python3
import json, os, subprocess, sys
root = os.environ['KIM_TEST_ROOT']
record = os.path.join(root, '.control', 'async-args.json')
open(record, 'w').write(json.dumps(sys.argv[1:]))
worker = os.path.join(root, '.control', 'async-read.py')
open(worker, 'w').write("import json, os, sys, time\\n"+
  "time.sleep(0.4)\\nargs=json.load(open(sys.argv[1]))\\n"+
  "paths=[args[i+1] for i,v in enumerate(args[:-1]) if v=='--attach']\\n"+
  "json.dump([os.path.exists(p) and os.path.getsize(p)>0 for p in paths], open(sys.argv[2],'w'))\\n")
subprocess.Popen(['/usr/bin/python3', worker, record, os.path.join(root,'.control','async-read.json')], start_new_session=True)
''')
        client.chmod(0o700)
        result = self.w.dispatch('resizeandsend', '--size', 'full', '--', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        ready = self.w.control / 'async-read.json'
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(ready.exists(), 'asynchronous fake client did not inspect the attachment')
        self.assertEqual(json.loads(ready.read_text()), [True])


if __name__ == '__main__':
    unittest.main()
