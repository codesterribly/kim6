"""Focused Recipes contracts and real, disposable image integration."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
import kim_recipe_core as core
from kim_recipe_image import ImageHandler


def recipe(steps=None):
    return {'schema': 1, 'id': 'test', 'name': 'Test', 'media': 'image',
            'steps': steps or [{'op': 'file.rename_output', 'pattern': '{stem}_copy'}],
            'destination': {'mode': 'beside'}}


class RecipeContracts(unittest.TestCase):
    def test_strict_schema(self):
        cases = []
        r = recipe(); r['command'] = 'touch /tmp/never'; cases.append(r)
        r = recipe(); r['steps'] = [{'op': 'shell', 'command': 'true'}]; cases.append(r)
        r = recipe(); r['schema'] = True; cases.append(r)
        r = recipe(); r['media'] = 'video'; cases.append(r)
        r = recipe(); r['steps'] = [{'op': 'image.convert', 'format': 'jpeg', 'quality': True}]; cases.append(r)
        for name in ('../escape', '{stem.__class__}', '{stem!r}', '{date:%Y}', '', '{unknown}'):
            cases.append(recipe([{'op': 'file.rename_output', 'pattern': name}]))
        for r in cases:
            with self.subTest(r=r), self.assertRaises(core.RecipeError): core.validate(r)
        with self.assertRaises(core.RecipeError): core.strict_json('{"schema":1,"schema":2}')
        with self.assertRaises(core.RecipeError): core.strict_json('[NaN]')

    def test_enabled_validation_and_order(self):
        original = recipe([{'op': 'image.rotate', 'degrees': 90}])
        self.assertNotIn('enabled', core.validate(original)['steps'][0])
        for value in (0, 1, None, 'false'):
            invalid = recipe([{'op': 'image.rotate', 'degrees': 90, 'enabled': value}])
            with self.assertRaises(core.RecipeError): core.validate(invalid)
        for step in ({'op': 'image.convert', 'format': 'jpeg', 'quality': 999, 'enabled': False},
                     {'op': 'unknown', 'enabled': False},
                     {'op': 'file.rename_output', 'pattern': '../escape', 'enabled': False}):
            with self.assertRaises(core.RecipeError): core.validate(recipe([step]))
        steps = [{'op': 'metadata.strip_all', 'enabled': False},
                 {'op': 'image.convert', 'format': 'png', 'quality': 90, 'enabled': False},
                 {'op': 'image.rotate', 'degrees': 90}]
        core.validate(recipe(steps))
        steps[0]['enabled'] = True
        with self.assertRaises(core.RecipeError): core.validate(recipe(steps))
        blank = {'op': 'metadata.copyright', 'creator': '', 'enabled': False}
        core.validate(recipe([blank]))
        blank['enabled'] = True
        core.validate(recipe([blank]))  # Missing combined fields now inherit Settings.

    def test_single_builtin_web_export_defaults(self):
        recipes = core.builtins()
        self.assertEqual(len(recipes), 1)
        r = recipes[0]
        self.assertEqual((r['name'], r['media']), ('Web Export', 'image'))
        self.assertEqual(r['destination'], {'mode': 'subfolder', 'folder': 'Web'})
        self.assertEqual([s['op'] for s in r['steps']], [
            'image.auto_orient', 'image.resize', 'image.color', 'image.convert',
            'metadata.strip_all', 'metadata.creator', 'metadata.copyright_notice',
            'metadata.usage_rights', 'file.rename_output'])
        self.assertEqual([s.get('enabled', True) for s in r['steps']], [True]*5 + [False]*3 + [True])
        self.assertEqual(r['steps'][1], {'op': 'image.resize', 'max_width': 1600, 'max_height': 1600, 'upscale': False})
        self.assertEqual(r['steps'][3], {'op': 'image.convert', 'format': 'jpeg', 'quality': 95})
        self.assertEqual(r['steps'][-1]['pattern'], '{filename}_web')

    def test_settings_are_literal_and_environment_precedence(self):
        from kim_recipe_image import copyright_settings, SETTING_KEYS
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'kim6'; config.mkdir()
            sentinel = Path(tmp)/'must-not-exist'
            literal = '$(touch ' + str(sentinel) + ')'
            (config/'settings.conf').write_text('KIM_COPYRIGHT_CREATOR=' + literal + '\nKIM_COPYRIGHT_NOTICE=Copyright {YEAR}\nKIM_COPYRIGHT_USAGE_RIGHTS=Portfolio\n')
            env = {k: v for k, v in os.environ.items() if k not in SETTING_KEYS.values()}
            env['XDG_CONFIG_HOME'] = tmp
            with patch.dict(os.environ, env, clear=True):
                values = copyright_settings()
                self.assertEqual(values, {'creator': literal, 'notice': 'Copyright {YEAR}', 'rights': 'Portfolio'})
                self.assertFalse(sentinel.exists())
                with patch.dict(os.environ, {'KIM_COPYRIGHT_CREATOR': 'Override'}):
                    self.assertEqual(copyright_settings()['creator'], 'Override')

    def test_settings_override_representation_and_validation(self):
        h = ImageHandler()
        for op in ('metadata.creator', 'metadata.copyright_notice', 'metadata.usage_rights'):
            for step in ({'op': op}, {'op': op, 'value': None}, {'op': op, 'value': 'Recipe value'},
                         {'op': op, 'value': '', 'enabled': False}):
                core.validate(recipe([step]))
            for value in (True, 123, {}, []):
                with self.assertRaises(core.RecipeError): core.validate(recipe([{'op': op, 'value': value}]))
        with patch('kim_recipe_image.copyright_settings', return_value={'creator': 'Default One'}) as settings:
            self.assertEqual(h.parameter_value({'op': 'metadata.creator'}, 'value'), 'Default One')
            settings.return_value = {'creator': 'Default Two'}
            self.assertEqual(h.parameter_value({'op': 'metadata.creator', 'value': None}, 'value'), 'Default Two')
            self.assertEqual(h.parameter_value({'op': 'metadata.creator', 'value': 'Custom'}, 'value'), 'Custom')
        with patch('kim_recipe_image.copyright_settings', side_effect=AssertionError('Override must not read Settings')):
            h.validate_context([{'op': 'metadata.creator', 'value': 'Custom'}])
            h.validate_context([{'op': 'metadata.creator', 'value': '', 'enabled': False}])
            h.validate_context([{'op': 'metadata.creator', 'value': ''}])  # Explicit blank leaves the field unchanged.

    def test_destinations(self):
        for dest in ({'mode': 'overwrite'}, {'mode': 'subfolder', 'folder': '../x'},
                     {'mode': 'directory', 'ask': False}, {'mode': 'directory', 'ask': 'yes'},
                     {'mode': 'beside', 'path': '/tmp'}):
            r = recipe(); r['destination'] = dest
            with self.assertRaises(core.RecipeError): core.validate(r)

    def test_order_rejection(self):
        with self.assertRaises(core.RecipeError):
            core.validate(recipe([{'op':'metadata.strip_all'},{'op':'image.auto_orient'}]))
        # Conversion declares final encoding; a later rotation remains ordered
        # pixel work and does not imply an intermediate JPEG encode.
        steps=[{'op':'image.convert','format':'jpeg','quality':90},{'op':'image.rotate','degrees':90}]
        self.assertEqual(core.validate(recipe(steps))['steps'],steps)

    def test_storage_atomic_and_defensive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'recipes.json'
            core.save_users([recipe()], path)
            self.assertEqual(core.read_recipes(path), [recipe()])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            before = path.read_bytes()
            with self.assertRaises(core.RecipeError): core.save_users([recipe(), recipe()], path)
            self.assertEqual(path.read_bytes(), before)
            path.unlink(); target = Path(tmp)/'target'; target.write_text('untouched')
            path.symlink_to(target)
            with self.assertRaises(core.RecipeError): core.save_users([recipe()], path)
            with self.assertRaises(OSError): core.read_recipes(path)
            self.assertEqual(target.read_text(), 'untouched')
            path.unlink(); os.link(target, path)
            with self.assertRaises(core.RecipeError): core.save_users([recipe()], path)
            path.unlink(); path.write_text('[{"bad":true}]')
            with self.assertRaises(core.RecipeError): core.read_recipes(path)

    def test_create_only_race_symlink_hardlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); staged = base/'stage'; staged.write_bytes(b'new')
            original = base/'original'; original.write_bytes(b'old')
            (base/'out.jpg').symlink_to(original)
            os.link(original, base/'out_1.jpg')
            fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
            self.addCleanup(os.close, fd)
            real_link = os.link
            def race(src, dst, **kwargs):
                if dst == 'out_2.jpg': (base/dst).write_bytes(b'racer')
                return real_link(src, dst, **kwargs)
            with patch.object(core.os, 'link', side_effect=race):
                self.assertEqual(core.publish(staged, fd, 'out.jpg'), 'out_3.jpg')
            self.assertEqual(original.read_bytes(), b'old')
            self.assertEqual((base/'out_2.jpg').read_bytes(), b'racer')
            self.assertEqual((base/'out_3.jpg').read_bytes(), b'new')

    def test_install_registration(self):
        for filename in ('install.sh', 'uninstall.sh'):
            data = (ROOT/filename).read_text()
            for relative in ('bin/kim_recipe_core.py', 'bin/kim_recipe_image.py',
                             'bin/kim_recipe_dialog.py', 'recipes/builtins.json', 'kim_recipes.desktop'):
                self.assertIn(relative, data)
            self.assertIn('"$RUNTIME/recipes"', data)
        self.assertIn('Exec=kim_all recipe --choose -- %F', (ROOT/'src/kim_recipes.desktop.in').read_text())
        self.assertIn('kim_recipe_core.py', (ROOT/'src/bin/kim_all').read_text())
        for r in core.builtins(): core.validate(r)


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
class RealRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'source.jpg'
        subprocess.run(['magick', '-size', '40x20', 'xc:red', str(self.source)], check=True)
        subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2020:01:02 03:04:05',
                        '-OffsetTimeOriginal=+00:00', '-GPSLatitude=20', '-GPSLongitude=30', str(self.source)],
                       check=True, capture_output=True)
        self.before = self.source.read_bytes()
        self.mtime = self.source.stat().st_mtime_ns

    def assert_original(self):
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(self.source.stat().st_mtime_ns, self.mtime)
        self.assertFalse(list(self.base.rglob('.kim6-stage.*')))

    def test_ordered_capture_name_strip(self):
        steps = [{'op': 'metadata.shift_capture', 'seconds': 86400},
                 {'op': 'file.rename_output', 'pattern': '{date}_{index}'}, {'op': 'metadata.strip_all'}]
        r = recipe(steps)
        row = core.preview(r, [self.source])[0]
        self.assertTrue(row.output.endswith('20200103_030405_1.jpg'))
        self.assertEqual(row.properties['compressed_size'], 'unknown')
        results = core.execute(r, [self.source]); self.assertTrue(results[0]['ok'], results)
        self.assertEqual(Path(results[0]['output']).name, '20200103_030405_1.jpg')
        steps[0], steps[1] = steps[1], steps[0]
        self.assertTrue(core.preview(recipe(steps), [self.source])[0].output.endswith('20200102_030405_1.jpg'))
        steps = [{'op': 'metadata.strip_all'}, {'op': 'file.rename_output', 'pattern': '{date}'}]
        self.assertTrue(core.preview(recipe(steps), [self.source])[0].problems)
        self.assert_original()

    def test_pixels_metadata_collision_and_partial_batch(self):
        r = recipe([{'op': 'image.auto_orient'}, {'op': 'image.rotate', 'degrees': 90},
                    {'op': 'image.resize', 'max_width': 10, 'max_height': 10, 'upscale': False},
                    {'op': 'image.convert', 'format': 'png', 'quality': 90},
                    {'op': 'metadata.strip_gps'}, {'op': 'metadata.copyright', 'creator': 'Test'},
                    {'op': 'file.rename_output', 'pattern': '{stem}'}])
        occupied = self.base/'source.png'; occupied.write_bytes(b'occupied')
        rows = core.preview(r, [self.source]); self.assertEqual(rows[0].properties['width'], 5)
        self.assertIn('nonstandard', '; '.join(rows[0].metadata))
        results = core.execute(r, [self.source, self.base/'missing.jpg'])
        self.assertTrue(results[0]['ok'], results); self.assertFalse(results[1]['ok'])
        self.assertEqual(Path(results[0]['output']).name, 'source_1.png')
        self.assertEqual(occupied.read_bytes(), b'occupied'); self.assert_original()

    def test_rename_only_byte_copy_source_alias(self):
        r = recipe([{'op': 'file.rename_output', 'pattern': '{stem}'}])
        results = core.execute(r, [self.source]); self.assertTrue(results[0]['ok'], results)
        self.assertEqual(Path(results[0]['output']).read_bytes(), self.before)
        self.assertNotEqual(Path(results[0]['output']).stat().st_ino, self.source.stat().st_ino)
        self.assert_original()

    def test_cross_folder_collision(self):
        other = self.base/'other'; other.mkdir(); duplicate = other/self.source.name
        duplicate.write_bytes(self.before)
        r = recipe(); r['destination'] = {'mode': 'directory', 'ask': True}
        results = core.execute(r, [self.source, duplicate], self.base)
        self.assertTrue(all(row['ok'] for row in results), results)
        self.assertNotEqual(results[0]['output'], results[1]['output']); self.assert_original()

    def test_missing_dependency_failure_and_symlinks(self):
        with patch('kim_recipe_image.shutil.which', return_value=None):
            result = core.execute(recipe(), [self.source])
        self.assertFalse(result[0]['ok']); self.assertIn('Missing dependency', result[0]['error'])
        link = self.base/'linked.jpg'; link.symlink_to(self.source)
        self.assertFalse(core.execute(recipe(), [link])[0]['ok'])
        folder = self.base/'folder'; folder.symlink_to(self.base, target_is_directory=True)
        r = recipe(); r['destination'] = {'mode': 'subfolder', 'folder': 'folder'}
        self.assertFalse(core.execute(r, [self.source])[0]['ok']); self.assert_original()

    def test_destination_swap_after_verification_never_publishes(self):
        real_verify = ImageHandler.verify
        for replacement in ('directory', 'symlink'):
            with self.subTest(replacement=replacement):
                destination = self.base / ('output-' + replacement)
                destination.mkdir()
                detached = self.base / ('detached-' + replacement)
                outside = self.base / ('outside-' + replacement)
                outside.mkdir()
                sentinel = outside / 'sentinel'
                sentinel.write_bytes(b'other directory owner')
                r = recipe()
                r['destination'] = {'mode': 'directory', 'ask': False,
                                    'path': str(destination)}

                def swap(handler, output, state):
                    real_verify(handler, output, state)
                    destination.rename(detached)
                    if replacement == 'symlink':
                        destination.symlink_to(outside, target_is_directory=True)
                    else:
                        destination.mkdir()

                with patch.object(ImageHandler, 'verify', swap):
                    result = core.execute(r, [self.source])[0]
                self.assertFalse(result['ok'], result)
                self.assertIn('Destination directory changed', result['error'])
                self.assertEqual(list(detached.iterdir()), [])
                self.assertEqual(sentinel.read_bytes(), b'other directory owner')
                self.assertEqual(list(outside.iterdir()), [sentinel])
                if replacement == 'directory':
                    self.assertEqual(list(destination.iterdir()), [])
                else:
                    self.assertTrue(destination.is_symlink())
                self.assert_original()

    def test_builtins(self):
        for r in core.builtins():
            results = core.execute(r, [self.source]); self.assertTrue(results[0]['ok'], results)
        self.assert_original()

    def test_date_sync_and_metadata_order(self):
        r = recipe([{'op': 'metadata.copyright', 'creator': 'Discarded'}, {'op': 'metadata.strip_all'},
                    {'op': 'metadata.copyright', 'creator': 'Final'}])
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        r = recipe([{'op': 'metadata.shift_capture', 'seconds': 60}, {'op': 'file.sync_date'}])
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        self.assertEqual(Path(result[0]['output']).stat().st_mtime, 1577934305)
        self.assert_original()

    def test_verification_failure_removes_stage_and_keeps_completed_output(self):
        real_verify = ImageHandler.verify
        count = [0]
        def verify(handler, output, state):
            count[0] += 1
            if count[0] == 2:
                raise core.RecipeError('Injected verification failure')
            return real_verify(handler, output, state)
        with patch.object(ImageHandler, 'verify', verify):
            result = core.execute(recipe(), [self.source, self.source])
        self.assertTrue(result[0]['ok']); self.assertFalse(result[1]['ok'])
        self.assertTrue(Path(result[0]['output']).exists())
        self.assertFalse((self.base/'source_copy_1.jpg').exists()); self.assert_original()

    def test_recognized_ai_and_gps_fields(self):
        subprocess.run(['exiftool', '-overwrite_original',
                        '-XMP-iptcExt:AISystemUsed=Example',
                        '-XMP-iptcExt:DigitalSourceType=http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia',
                        '-XMP-exif:GPSDestLatitude=10', str(self.source)], check=True, capture_output=True)
        self.before = self.source.read_bytes(); self.mtime = self.source.stat().st_mtime_ns
        r = recipe([{'op': 'metadata.strip_ai'}, {'op': 'metadata.strip_gps'}])
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        remaining = subprocess.run(['exiftool', '-s3', '-XMP-iptcExt:AISystemUsed',
            '-XMP-iptcExt:DigitalSourceType', '-XMP-exif:GPSDestLatitude', result[0]['output']], capture_output=True, text=True)
        self.assertEqual(remaining.stdout, ''); self.assert_original()

    def test_percent_flip_avif_and_preserved_icc(self):
        source = self.base/'plain.png'
        subprocess.run(['magick', '-size', '41x21', 'xc:blue', str(source)], check=True)
        for fmt in ('jpeg', 'png', 'webp', 'avif'):
            r = recipe([{'op': 'image.resize_percent', 'percent': 33},
                        {'op': 'image.flip', 'axis': 'vertical'},
                        {'op': 'image.convert', 'format': fmt, 'quality': 85}])
            result = core.execute(r, [source])
            if fmt == 'avif' and not result[0]['ok'] and 'writer unavailable' in result[0]['error']:
                continue
            self.assertTrue(result[0]['ok'], result)
            if fmt == 'webp':
                self.assertFalse(core.preview(recipe(), [Path(result[0]['output'])])[0].problems)
        r = recipe([{'op': 'image.convert', 'format': 'avif', 'quality': 85}])
        self.assertTrue(core.execute(r, [self.source])[0]['ok'])
        from kim_recipe_image import srgb_profile
        try:
            profile = srgb_profile()
        except core.RecipeError:
            self.skipTest('sRGB profile unavailable')
        subprocess.run(['exiftool', '-overwrite_original', '-ICC_Profile<=' + profile, str(source)], check=True, capture_output=True)
        r = recipe([{'op': 'image.resize_percent', 'percent': 50}, {'op': 'image.color', 'mode': 'preserve'}])
        result = core.execute(r, [source]); self.assertTrue(result[0]['ok'], result)
        self.assert_original()

    def test_blank_copyright_fields_preserve_rights(self):
        from kim_recipe_image import COPYRIGHT_TAGS, selected_metadata
        saved = {'creator': 'Previous creator', 'notice': 'Existing copyright', 'rights': 'Existing usage rights'}
        args = ['-' + tag + '=' + saved[field] for field, tags in COPYRIGHT_TAGS.items() for tag in tags]
        subprocess.run(['exiftool', '-overwrite_original'] + args + [str(self.source)], check=True, capture_output=True)
        self.before = self.source.read_bytes(); self.mtime = self.source.stat().st_mtime_ns
        r = recipe([{'op': 'metadata.copyright', 'creator': 'New creator', 'notice': '', 'rights': '   '}])
        row = core.preview(r, [self.source])[0]
        self.assertIn('Existing copyright', '; '.join(row.metadata))
        self.assertIn('Existing usage rights', '; '.join(row.metadata))
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        tags = selected_metadata(Path(result[0]['output']), [tag for group in COPYRIGHT_TAGS.values() for tag in group])
        for field, group in COPYRIGHT_TAGS.items():
            for tag in group:
                value = tags[tag]
                if isinstance(value, list): value = value[0]
                self.assertEqual(value, 'New creator' if field == 'creator' else saved[field], tag)
        for step in ({'op': 'metadata.copyright'}, {'op': 'metadata.copyright', 'notice': '', 'creator': '  ', 'rights': ''}):
            core.validate(recipe([step]))  # Combined fields retain inheritance / explicit blank distinctions.
        self.assert_original()

    def test_copyright_year_uses_logical_capture_date_in_order(self):
        from kim_recipe_image import selected_metadata
        shift = {'op': 'metadata.shift_capture', 'seconds': -3 * 86400}
        notice = {'op': 'metadata.copyright', 'notice': 'Copyright {YEAR} Example'}
        for steps, year in (([shift, notice], '2019'), ([notice, shift], '2020')):
            r = recipe(steps)
            row = core.preview(r, [self.source])[0]
            self.assertIn('Copyright ' + year + ' Example', '; '.join(row.metadata))
            result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
            values = selected_metadata(Path(result[0]['output']), ('EXIF:Copyright', 'IPTC:CopyrightNotice', 'XMP-dc:Rights'))
            self.assertTrue(all(value == 'Copyright ' + year + ' Example' for value in values.values()), values)
        stripped = recipe([{'op': 'metadata.strip_all'}, notice])
        self.assertFalse(core.preview(stripped, [self.source])[0].problems)
        result = core.execute(stripped, [self.source]); self.assertTrue(result[0]['ok'], result)
        values = selected_metadata(Path(result[0]['output']), ('EXIF:DateTimeOriginal', 'EXIF:Copyright'))
        self.assertIsNone(values['EXIF:DateTimeOriginal'])
        self.assertEqual(values['EXIF:Copyright'], 'Copyright 2020 Example')
        self.assert_original()

    def test_orientation_six_explicit_transforms_match_pixels_and_tags(self):
        subprocess.run(['magick', '-size', '40x20', 'xc:white', '-fill', 'red', '-draw',
                        'rectangle 0,0 9,6', '-fill', 'blue', '-draw', 'rectangle 20,10 39,19',
                        str(self.source)], check=True)
        subprocess.run(['exiftool', '-overwrite_original', '-EXIF:Orientation#=6',
                        '-XMP-tiff:Orientation#=6', str(self.source)], check=True, capture_output=True)
        self.before = self.source.read_bytes(); self.mtime = self.source.stat().st_mtime_ns
        for step, args, dimensions in (
                ({'op': 'image.rotate', 'degrees': 90}, ['-rotate', '90'], (40, 20)),
                ({'op': 'image.flip', 'axis': 'horizontal'}, ['-flop'], (20, 40)),
                ({'op': 'image.flip', 'axis': 'vertical'}, ['-flip'], (20, 40))):
            r = recipe([step, {'op': 'image.convert', 'format': 'png', 'quality': 90}])
            row = core.preview(r, [self.source])[0]
            self.assertFalse(row.problems, row.problems)
            self.assertEqual((row.properties['width'], row.properties['height']), dimensions)
            self.assertEqual(row.properties['orientation'], 1)
            result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
            output = result[0]['output']
            expected = subprocess.check_output(['magick', str(self.source), '-auto-orient'] + args + ['-depth', '8', 'RGB:-'])
            actual = subprocess.check_output(['magick', output, '-depth', '8', 'RGB:-'])
            self.assertEqual(actual, expected)
            orientations = subprocess.check_output(['exiftool', '-s3', '-n', '-EXIF:Orientation', '-XMP-tiff:Orientation', output], text=True).splitlines()
            self.assertEqual(orientations, ['1', '1'])
        self.assert_original()

    def test_preview_reports_final_states_and_unselected_destination(self):
        r = recipe([{'op': 'metadata.shift_capture', 'seconds': 86400},
                    {'op': 'metadata.copyright', 'creator': 'Must disappear', 'notice': 'Copyright {YEAR}'},
                    {'op': 'file.sync_date'}, {'op': 'metadata.strip_all'},
                    {'op': 'metadata.copyright', 'creator': 'Final creator'}])
        r['destination'] = {'mode': 'directory', 'ask': True}
        row = core.preview(r, [self.source])[0]
        self.assertFalse(row.problems, row.problems)
        self.assertEqual(row.output, '<choose directory at run>/source_recipe.jpg')
        summary = '; '.join(row.metadata)
        self.assertNotIn('Must disappear', summary)
        self.assertNotIn('Copyright 2020', summary)
        self.assertIn('Final creator', summary)
        self.assertIn('Capture time: absent', summary)
        self.assertIn('Output timestamp: 2020-01-03', summary)
        self.assertEqual(row.properties['compressed_size'], 'unknown')
        result = core.execute(r, [self.source])
        self.assertFalse(result[0]['ok']); self.assertIn('Choose a destination', result[0]['error'])
        chosen = core.preview(r, [self.source], self.base)[0]
        self.assertEqual(chosen.output, str(self.base/'source_recipe.jpg'))
        self.assert_original()

    def test_strip_all_requires_normalized_orientation_six(self):
        subprocess.run(['exiftool', '-overwrite_original', '-EXIF:Orientation#=6', str(self.source)],
                       check=True, capture_output=True)
        self.before = self.source.read_bytes(); self.mtime = self.source.stat().st_mtime_ns
        strip = {'op': 'metadata.strip_all'}
        invalid = recipe([strip])
        row = core.preview(invalid, [self.source])[0]
        self.assertIn('earlier image.auto_orient', row.problems[0])
        from kim_recipe_image import run
        before = set(self.base.iterdir())
        with patch('kim_recipe_image.run', wraps=run) as commands:
            result = core.execute(invalid, [self.source])
        self.assertFalse(result[0]['ok'])
        self.assertIn('will not silently re-encode', result[0]['error'])
        self.assertFalse([call for call in commands.call_args_list
                          if call.args[0][0] == 'magick' and call.args[0][1] != 'identify'])
        self.assertEqual(set(self.base.iterdir()), before)
        valid = recipe([{'op': 'image.auto_orient'}, strip])
        row = core.preview(valid, [self.source])[0]
        self.assertFalse(row.problems, row.problems)
        self.assertEqual((row.properties['width'], row.properties['height']), (20, 40))
        result = core.execute(valid, [self.source]); self.assertTrue(result[0]['ok'], result)
        output = result[0]['output']
        self.assertNotEqual(output, str(self.source))
        self.assertEqual(subprocess.check_output(['magick', 'identify', '-format', '%wx%h', output], text=True), '20x40')
        self.assertEqual(subprocess.check_output(['exiftool', '-s3', '-Orientation', output], text=True), '')
        equivalent = recipe([{'op': 'image.rotate', 'degrees': 90}, strip])
        self.assertFalse(core.preview(equivalent, [self.source])[0].problems)
        self.assert_original()

    def test_disabled_steps_copy_and_reenabled_preview_execution(self):
        steps = [{'op': 'image.resize_percent', 'percent': 50, 'enabled': False},
                 {'op': 'image.convert', 'format': 'png', 'quality': 90, 'enabled': False},
                 {'op': 'metadata.strip_all', 'enabled': False},
                 {'op': 'file.rename_output', 'pattern': '{stem}_custom', 'enabled': False}]
        r = recipe(steps)
        row = core.preview(r, [self.source])[0]
        self.assertEqual((row.format, row.properties['width'], row.properties['height']), ('jpeg', 40, 20))
        self.assertTrue(row.output.endswith('source_recipe.jpg'))
        self.assertIn('Capture time: 2020-', '; '.join(row.metadata))
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        self.assertEqual(Path(result[0]['output']).read_bytes(), self.before)
        for step in steps: step['enabled'] = True
        row = core.preview(r, [self.source])[0]
        self.assertEqual((row.format, row.properties['width'], row.properties['height']), ('png', 20, 10))
        self.assertIn('Capture time: absent', row.metadata)
        occupied = self.base/'source_custom.png'; occupied.write_bytes(b'occupied')
        result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
        self.assertTrue(result[0]['output'].endswith('source_custom_1.png'))
        self.assertEqual(occupied.read_bytes(), b'occupied')
        default = core.preview(recipe([{'op': 'image.resize_percent', 'percent': 50}]), [self.source])[0]
        self.assertEqual(default.properties['width'], 20)
        self.assert_original()

    def test_cli_honors_disabled_steps(self):
        custom = self.base/'disabled.json'
        custom.write_text(json.dumps(recipe([{'op': 'image.rotate', 'degrees': 90, 'enabled': False}])))
        command = [sys.executable, str(ROOT/'src/bin/kim_recipe_core.py'), '--recipe', str(custom)]
        checked = subprocess.run(command + ['--preview', '--', str(self.source)], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)[0]['properties']['width'], 40)
        result = subprocess.run(command + ['--', str(self.source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)[0]['output']).read_bytes(), self.before)
        self.assert_original()

    def test_builtin_optional_rights_after_strip_and_logical_year(self):
        from kim_recipe_image import COPYRIGHT_TAGS, selected_metadata, SETTING_KEYS
        config = self.base/'config'/'kim6'; config.mkdir(parents=True)
        values = {'creator': 'Example Artist', 'notice': 'Copyright {YEAR} Example', 'rights': 'Portfolio only'}
        (config/'settings.conf').write_text(''.join(SETTING_KEYS[k] + '=' + v + '\n' for k, v in values.items()))
        env = {k: v for k, v in os.environ.items() if k not in SETTING_KEYS.values()}
        env['XDG_CONFIG_HOME'] = str(config.parent)
        tags = [tag for group in COPYRIGHT_TAGS.values() for tag in group]
        private = ['EXIF:DateTimeOriginal', 'EXIF:OffsetTimeOriginal', 'EXIF:CreateDate', 'GPS:GPSLatitude', 'GPS:GPSLongitude']
        with patch.dict(os.environ, env, clear=True):
            base = core.builtins()[0]
            result = core.execute(base, [self.source]); self.assertTrue(result[0]['ok'], result)
            output = Path(result[0]['output']); baseline = output.read_bytes()
            self.assertTrue(all(v is None for v in selected_metadata(output, tags + private).values()))
            for field, op in (('creator', 'metadata.creator'), ('notice', 'metadata.copyright_notice'), ('rights', 'metadata.usage_rights')):
                r = copy.deepcopy(base)
                next(s for s in r['steps'] if s['op'] == op)['enabled'] = True
                result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
                actual = selected_metadata(Path(result[0]['output']), tags + private)
                for other, group in COPYRIGHT_TAGS.items():
                    for tag in group:
                        expected = values[field].replace('{YEAR}', '2020') if other == field else None
                        value = actual[tag][0] if isinstance(actual[tag], list) else actual[tag]
                        self.assertEqual(value, expected, tag)
                self.assertTrue(all(actual[tag] is None for tag in private))
            r = copy.deepcopy(base)
            r['steps'].insert(4, {'op': 'metadata.shift_capture', 'seconds': -3*86400})
            for step in r['steps']:
                if step['op'] in ('metadata.creator', 'metadata.copyright_notice', 'metadata.usage_rights'):
                    step['enabled'] = True
            row = core.preview(r, [self.source])[0]
            self.assertFalse(row.problems, row.problems)
            self.assertIn('Copyright 2019 Example', '; '.join(row.metadata))
            self.assertIn('Capture time: absent', row.metadata)
            result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
            actual = selected_metadata(Path(result[0]['output']), tags + private)
            self.assertEqual(actual['EXIF:Copyright'], 'Copyright 2019 Example')
            self.assertTrue(all(actual[tag] is None for tag in private))
            self.assertEqual(output.read_bytes(), baseline)
        self.assert_original()

    def test_blank_settings_fail_without_erasing_metadata(self):
        from kim_recipe_image import SETTING_KEYS
        config = self.base/'config'/'kim6'; config.mkdir(parents=True)
        (config/'settings.conf').write_text(''.join(key + '=\n' for key in SETTING_KEYS.values()))
        env = {k: v for k, v in os.environ.items() if k not in SETTING_KEYS.values()}
        env['XDG_CONFIG_HOME'] = str(config.parent)
        with patch.dict(os.environ, env, clear=True):
            for op in ('metadata.creator', 'metadata.copyright_notice', 'metadata.usage_rights'):
                r = recipe([{'op': op}])
                row = core.preview(r, [self.source])[0]
                self.assertIn('no inherited Settings value', row.problems[0])
                self.assertFalse(core.execute(r, [self.source])[0]['ok'])
            disabled = recipe([{'op': 'metadata.creator', 'enabled': False}])
            result = core.execute(disabled, [self.source]); self.assertTrue(result[0]['ok'], result)
            self.assertEqual(Path(result[0]['output']).read_bytes(), self.before)
            missing_date = self.base/'no-date.jpg'
            subprocess.run(['magick', '-size', '4x2', 'xc:red', str(missing_date)], check=True)
            with patch.dict(os.environ, {'KIM_COPYRIGHT_NOTICE': 'Copyright {YEAR}'}):
                row = core.preview(recipe([{'op': 'metadata.strip_all'}, {'op': 'metadata.copyright_notice'}]), [missing_date])[0]
                self.assertIn('needs a capture date', row.problems[0])
        self.assert_original()

    def test_disabled_auto_orient_keeps_strip_guard(self):
        subprocess.run(['exiftool', '-overwrite_original', '-Orientation#=6', str(self.source)], check=True, capture_output=True)
        self.before = self.source.read_bytes(); self.mtime = self.source.stat().st_mtime_ns
        r = recipe([{'op': 'image.auto_orient', 'enabled': False}, {'op': 'metadata.strip_all'}])
        self.assertIn('normalized orientation', core.preview(r, [self.source])[0].problems[0])
        self.assertFalse(core.execute(r, [self.source])[0]['ok'])
        r['steps'][0]['enabled'] = True
        self.assertFalse(core.preview(r, [self.source])[0].problems)
        r['steps'][1]['enabled'] = False
        self.assertEqual(core.preview(r, [self.source])[0].properties['orientation'], 1)
        self.assert_original()

    def test_saved_inheritance_and_overrides_follow_settings_without_private_metadata(self):
        from kim_recipe_image import selected_metadata, SETTING_KEYS
        config = self.base/'config'/'kim6'; config.mkdir(parents=True)
        settings = config/'settings.conf'
        env = {k: v for k, v in os.environ.items() if k not in SETTING_KEYS.values()}
        env['XDG_CONFIG_HOME'] = str(config.parent)
        inherited = recipe([{'op': 'metadata.strip_all'}, {'op': 'metadata.creator'},
                            {'op': 'metadata.copyright_notice', 'value': 'Copyright {YEAR} Custom'},
                            {'op': 'metadata.usage_rights', 'value': 'Custom license'}])
        inherited['id'] = 'inherited-test'
        with patch.dict(os.environ, env, clear=True):
            core.save_users([inherited])
            stored = core.config_path().read_bytes()
            outputs = []
            for creator in ('Settings One', 'Settings Two'):
                settings.write_text('KIM_COPYRIGHT_CREATOR=' + creator + '\nKIM_COPYRIGHT_NOTICE=Global notice\nKIM_COPYRIGHT_USAGE_RIGHTS=Global license\n')
                before = settings.read_bytes()
                saved = core.load_users()[0]
                row = core.preview(saved, [self.source])[0]
                self.assertIn(creator, '; '.join(row.metadata))
                self.assertIn('Copyright 2020 Custom', '; '.join(row.metadata))
                result = core.execute(saved, [self.source]); self.assertTrue(result[0]['ok'], result)
                output = Path(result[0]['output']); outputs.append((output, output.read_bytes()))
                actual = selected_metadata(output, ('EXIF:Artist', 'IPTC:By-line', 'XMP-dc:Creator',
                    'EXIF:Copyright', 'XMP-xmpRights:UsageTerms', 'EXIF:DateTimeOriginal', 'GPS:GPSLatitude'))
                self.assertEqual(actual['EXIF:Artist'], creator)
                self.assertEqual(actual['EXIF:Copyright'], 'Copyright 2020 Custom')
                self.assertEqual(actual['XMP-xmpRights:UsageTerms'], 'Custom license')
                self.assertIsNone(actual['EXIF:DateTimeOriginal']); self.assertIsNone(actual['GPS:GPSLatitude'])
                self.assertEqual(settings.read_bytes(), before)
            self.assertEqual(core.config_path().read_bytes(), stored)
            self.assertNotEqual(outputs[0][0], outputs[1][0])
            self.assertEqual(outputs[0][0].read_bytes(), outputs[0][1])
        self.assert_original()

    def test_manual_rights_work_with_blank_settings_and_explicit_blank_is_distinct(self):
        from kim_recipe_image import selected_metadata, SETTING_KEYS
        config = self.base/'config'/'kim6'; config.mkdir(parents=True)
        settings = config/'settings.conf'; settings.write_text(''.join(key + '=\n' for key in SETTING_KEYS.values()))
        before = settings.read_bytes()
        env = {k: v for k, v in os.environ.items() if k not in SETTING_KEYS.values()}
        env['XDG_CONFIG_HOME'] = str(config.parent)
        with patch.dict(os.environ, env, clear=True):
            r = core.builtins()[0]
            for step in r['steps']:
                if step['op'] == 'metadata.creator': step.update(enabled=True, value='Entered in recipe')
                if step['op'] == 'metadata.copyright_notice': step.update(enabled=True, value='Copyright {YEAR} Manual')
                if step['op'] == 'metadata.usage_rights': step.update(enabled=True, value='Manual terms')
            result = core.execute(r, [self.source]); self.assertTrue(result[0]['ok'], result)
            output = Path(result[0]['output']); payload = output.read_bytes()
            actual = selected_metadata(output, ('EXIF:Artist', 'EXIF:Copyright', 'XMP-xmpRights:UsageTerms', 'EXIF:DateTimeOriginal', 'GPS:GPSLatitude'))
            self.assertEqual(actual['EXIF:Artist'], 'Entered in recipe')
            self.assertEqual(actual['EXIF:Copyright'], 'Copyright 2020 Manual')
            self.assertEqual(actual['XMP-xmpRights:UsageTerms'], 'Manual terms')
            self.assertIsNone(actual['EXIF:DateTimeOriginal']); self.assertIsNone(actual['GPS:GPSLatitude'])
            creator = next(s for s in r['steps'] if s['op'] == 'metadata.creator')
            creator['value'] = ''
            row = core.preview(r, [self.source])[0]
            self.assertFalse(row.problems)
            blank_result=core.execute(r, [self.source]); self.assertTrue(blank_result[0]['ok'], blank_result)
            self.assertIsNone(selected_metadata(Path(blank_result[0]['output']), ('EXIF:Artist',))['EXIF:Artist'])
            self.assertEqual(output.read_bytes(), payload)
            creator['enabled'] = False
            self.assertFalse(core.preview(r, [self.source])[0].problems)
            self.assertEqual(settings.read_bytes(), before)
        self.assert_original()

    def test_cli_dispatch(self):
        result = subprocess.run(['bash', str(ROOT/'src/bin/kim_all'), 'recipe', '--recipe',
                                 'web-export', '--preview', '--', str(self.source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]['format'], 'jpeg')
        custom = self.base/'recipe.json'
        custom.write_text(json.dumps(recipe([{'op': 'metadata.strip_all'}, {'op': 'metadata.shift_capture', 'seconds': 1}])))
        failed = subprocess.run(['bash', str(ROOT/'src/bin/kim_all'), 'recipe', '--recipe', str(custom), '--', str(self.source)], capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertNotIn('Traceback', failed.stderr)
        self.assertIn('removes capture metadata', failed.stdout)
        self.assertIn('Set a specific date', failed.stdout)


class RecipePackagingTests(unittest.TestCase):
    def test_disposable_install_run_and_uninstall(self):
        import test_manual_installation as packaging
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp)/'checkout'
            shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns('.git', '__pycache__', '.codex', '.agents'))
            helper = packaging.ManualInstallationTests()
            helper.setUp()
            helper.env['XDG_CONFIG_HOME'] = str(Path(tmp)/'config')
            self.addCleanup(helper.doCleanups)
            with patch.object(packaging, 'ROOT', checkout):
                helper.run_installer('install.sh')
                for relative in ('bin/kim_recipe_core.py', 'bin/kim_recipe_image.py',
                                 'bin/kim_recipe_dialog.py', 'bin/kim_recipe_run.py', 'recipes/builtins.json'):
                    self.assertEqual((helper.runtime/relative).read_bytes(), (ROOT/'src'/relative).read_bytes())
                menu = helper.prefix/'kim_recipes.desktop'
                self.assertIn('recipe --choose -- %F', menu.read_text())
                self.assertIn('Actions=KIMRecipe0Run;KIMRecipe1Editor;', menu.read_text())
                self.assertIn('X-KDE-Submenu=KIM6 Recipes', menu.read_text())
                self.assertNotIn('X-KDE-Priority', menu.read_text())
                self.assertNotIn('Choose Saved Recipe', menu.read_text())
                command = ['bash', str(helper.runtime/'bin/kim_all'), 'recipe', '--list']
                result = subprocess.run(command, capture_output=True, text=True, env=helper.env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(json.loads(result.stdout)), 1)
                unrelated = helper.prefix/'user-unrelated.desktop'
                unrelated.write_text('unrelated service menu')
                helper.run_installer('uninstall.sh')
                self.assertEqual(unrelated.read_text(), 'unrelated service menu')
                self.assertFalse(menu.exists())
                self.assertFalse((helper.runtime/'recipes').exists())


class RecipeGuiTests(unittest.TestCase):
    def run_gui(self, code):
        import importlib.util
        if importlib.util.find_spec('PySide6') is None:
            self.skipTest('PySide6 unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            settle = """
def _wait_for_preview(widget):
    import time
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance(); end=time.monotonic()+15
    while (widget.preview_worker is not None or widget.preview_pending or widget.timer.isActive()) and time.monotonic()<end:
        app.processEvents(); time.sleep(.005)
    app.processEvents()
    assert widget.preview_worker is None and not widget.preview_pending
"""
            result = subprocess.run([sys.executable, '-c', settle+code], capture_output=True, text=True,
                timeout=30, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen',
                                 'XDG_CONFIG_HOME': tmp, 'PYTHONPATH': str(ROOT/'src/bin'),
                                 'KIM_COPYRIGHT_CREATOR': '', 'KIM_COPYRIGHT_NOTICE': '', 'KIM_COPYRIGHT_USAGE_RIGHTS': ''})
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_examples_handler_parameters_and_unsaved_switching(self):
        self.run_gui("""
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox, QFormLayout, QSpinBox
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import read_recipes, config_path, handler
app = QApplication([])
with patch('kim_recipe_dialog.preview', return_value=[]) as preview:
    w = RecipeWidget()
    with patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=(['example-a.jpg', 'example-b.png'], '')):
        w.choose_examples()
    assert w.files == [] and w.example_files == ['example-a.jpg', 'example-b.png']
    _wait_for_preview(w)
    assert preview.call_args.args[1] == [w.example_files[0]]
    with patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=([], '')), patch('kim_recipe_dialog.RunRecipeDialog') as confirmation:
        w.load_photos_and_run()
        assert not confirmation.called and w.run_dialog is None
    w.duplicate()
    own_index = w.active_index
    w.name.setText('Unsaved name'); w.changed()
    with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Cancel):
        w.selector.setCurrentIndex(0)
    assert w.selector.currentIndex() == own_index and w.recipe['name'] == 'Unsaved name'
    with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Save):
        w.selector.setCurrentIndex(0)
    assert w.active_index == 0
    assert read_recipes(config_path())[0]['name'] == 'Unsaved name'
    w.selector.setCurrentIndex(own_index)
    w.name.setText('Discard me'); w.changed()
    with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Discard):
        w.selector.setCurrentIndex(0)
    w.selector.setCurrentIndex(own_index)
    assert w.name.text() == 'Unsaved name'
    w.name.setText(''); w.changed()
    with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Save), patch.object(w, 'error') as error:
        w.selector.setCurrentIndex(0)
    assert w.active_index == own_index and w.selector.currentIndex() == own_index and error.called
    w.name.setText('Unsaved name'); w.changed()
    definitions = handler('image').operation_definitions()
    definitions['test.handler_owned'] = {'parameters': {'amount': {'type': 'integer', 'default': 13, 'minimum': -9, 'maximum': 99}}}
    with patch('kim_recipe_dialog.handler') as selected_handler:
        media_handler = handler('image')
        media_handler.operation_definitions = lambda: definitions
        selected_handler.return_value = media_handler
        w.select(own_index, force=True)
    w.add_step('test.handler_owned')
    control = w.form.itemAt(0, QFormLayout.FieldRole).widget()
    assert isinstance(control, QSpinBox)
    assert (control.value(), control.minimum(), control.maximum()) == (13, -9, 99)
    control.setValue(17)
    assert w.recipe['steps'][-1] == {'op': 'test.handler_owned', 'amount': 17}
    w.remove_step()
    w.close()
""")

    def test_serial_worker_responsive_cancellation_and_execution_authorization(self):
        self.run_gui("""
import threading
from unittest.mock import patch
from PySide6.QtCore import QTimer, QEventLoop, QThread
from PySide6.QtWidgets import QApplication
from kim_recipe_run import RunRecipeDialog
from kim_recipe_core import builtins, PreviewRow, config_path
app = QApplication([])
started = threading.Event(); release = threading.Event(); calls = []
published = config_path().parent.parent/'completed-output'
def execute(recipe, files, chosen, start_index):
    assert QThread.currentThread() != app.thread()
    calls.append((files, start_index)); started.set()
    assert release.wait(10)
    published.write_text('completed')
    return [{'source': files[0], 'output': str(published), 'ok': True}]
def preview(recipe, files, chosen, start_index):
    return [PreviewRow(files[0], '/output/photo.jpg', 'image', 'jpeg')]
with patch('kim_recipe_run.preview', side_effect=preview), patch('kim_recipe_run.execute', side_effect=execute):
    w = RunRecipeDialog(builtins()[0], ['authorized-first.jpg', 'authorized-second.jpg'])
    loop = QEventLoop(); watchdog = QTimer(); watchdog.setSingleShot(True); watchdog.timeout.connect(loop.quit); watchdog.start(15000)
    ticks = []
    def tick():
        ticks.append(1)
        if w.worker is None and w.run_button.isEnabled() and not calls:
            w.start_execution(); original = w.worker; w.start_execution(); assert w.worker is original
        if started.is_set() and len(ticks) >= 3 and w.worker is not None:
            w.progress.canceled.emit(); release.set()
        if calls and w.worker is None:
            loop.quit()
    heartbeat = QTimer(); heartbeat.setInterval(10); heartbeat.timeout.connect(tick); heartbeat.start()
    loop.exec(); heartbeat.stop(); watchdog.stop()
    assert len(ticks) >= 3 and calls == [(['authorized-first.jpg'], 1)], calls
    assert published.read_text() == 'completed'
    assert 'cancelled before remaining files' in w.summary.text() and 'skipped: 1' in w.summary.text()
    assert 'authorized-second.jpg' in w.diagnostics.toPlainText()
    assert str(published) in w.diagnostics.toPlainText()
    assert w.files == ['authorized-first.jpg', 'authorized-second.jpg']
    w.close()
""")

    def test_delete_confirmation_and_unsaved_edits(self):
        self.run_gui("""
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import read_recipes, config_path
app = QApplication([])
w = RecipeWidget()
with patch('kim_recipe_dialog.QMessageBox.question') as question:
    w.remove()
    assert not question.called and w.immutable
w.duplicate(); assert w.save()
saved = config_path().read_bytes()
saved_name = w.recipe['name']
w.name.setText('Unsaved rename'); w.changed()
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Cancel) as question:
    w.remove()
    assert saved_name in question.call_args.args[2]
assert config_path().read_bytes() == saved
assert w.recipe['name'] == 'Unsaved rename' and len(w.users) == 1
with patch('kim_recipe_dialog.QMessageBox.question', side_effect=[QMessageBox.Yes, QMessageBox.Cancel]) as question:
    w.remove()
    assert question.call_count == 2
assert config_path().read_bytes() == saved and w.recipe['name'] == 'Unsaved rename'
with patch('kim_recipe_dialog.QMessageBox.question', side_effect=[QMessageBox.Yes, QMessageBox.Discard]):
    w.remove()
assert read_recipes(config_path()) == [] and w.immutable
w.duplicate()
w.name.setText('Save before removal'); w.changed()
with patch('kim_recipe_dialog.QMessageBox.question', side_effect=[QMessageBox.Yes, QMessageBox.Save]):
    w.remove()
assert read_recipes(config_path()) == [] and w.immutable
w.close()
""")

    def test_builtin_session_toggles_and_user_persistence(self):
        self.run_gui("""
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import config_path, builtins, read_recipes
app = QApplication([])
w = RecipeWidget()
original = builtins()[0]
assert w.steps.count() == 9
assert all(w.steps.item(i).checkState() == Qt.Unchecked for i in (5, 6, 7))
assert 'Resize to Fit' in w.steps.item(1).text() and '1600' in w.steps.item(1).text()
assert 'JPEG, quality 95' in w.steps.item(3).text()
assert w.management_buttons['Duplicate to Edit'].isEnabled()
assert not w.management_buttons['Save'].isEnabled()
w.steps.item(1).setCheckState(Qt.Unchecked)
assert w.recipe['steps'][1]['enabled'] is False
assert w.shipped[0] == original and builtins()[0] == original
assert w.steps.item(1).flags() & Qt.ItemIsEnabled
w.parameter(1, 'max_width', 5)
assert w.recipe['steps'][1]['max_width'] == 5
with patch('kim_recipe_dialog.QMessageBox.question') as question:
    assert w.protect_unsaved()
    assert not question.called
w.selector.activated.emit(0)
assert w.recipe == original
w.steps.item(5).setCheckState(Qt.Checked)
w.update_preview()
assert 'no inherited Settings value' in w.status.text()
assert not config_path().exists()
w.selector.activated.emit(0)
assert w.recipe == original
w.duplicate()
index = w.active_index
w.steps.item(1).setCheckState(Qt.Unchecked)
assert w.recipe != w.baseline
assert w.save()
assert read_recipes(config_path())[0]['steps'][1]['enabled'] is False
w.steps.item(1).setCheckState(Qt.Checked)
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Cancel):
    w.selector.setCurrentIndex(0)
assert w.active_index == index and w.recipe['steps'][1]['enabled'] is True
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Discard):
    w.selector.setCurrentIndex(0)
assert w.recipe == original
w.selector.setCurrentIndex(index)
assert w.recipe['steps'][1]['enabled'] is False
assert builtins()[0] == original
w.close()
""")

    def test_two_panel_preview_example_selection(self):
        self.run_gui("""
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import PreviewRow
app = QApplication([])
def planned(recipe, files, **kwargs):
    return [PreviewRow(files[0], '/photos/Web/' + files[0].split('/')[-1], 'image', 'jpeg',
        {'width': 1600, 'height': 800, 'original_width': 2000, 'original_height': 1000, 'quality': 95},
        ['Capture time: absent', 'GPS: absent', 'ICC: sRGB pixels; ICC profile stripped'])]
with patch('kim_recipe_dialog.preview', side_effect=planned) as preview:
    w = RecipeWidget(files=['/photos/first.jpg', '/photos/second.jpg'])
    w.resize(1150, 820); w.show(); app.processEvents(); _wait_for_preview(w)
    assert w.splitter.orientation() == Qt.Horizontal and w.splitter.count() == 2
    assert w.splitter.sizes()[0] > w.splitter.sizes()[1] > 0
    assert w.table.columnCount() == 2
    assert w.table.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert not w.table.horizontalScrollBar().isVisible()
    assert w.reset_examples.isHidden()
    assert w.example_selector.count() == 2
    assert preview.call_args.args[1] == ['/photos/first.jpg']
    w.example_selector.setCurrentIndex(1); _wait_for_preview(w)
    assert preview.call_args.args[1] == ['/photos/second.jpg']
    assert preview.call_args.kwargs['start_index'] == 2
    with patch('kim_recipe_dialog.QFileDialog.getOpenFileNames', return_value=(['/custom/example.png'], '')):
        w.choose_examples(); _wait_for_preview(w); _wait_for_preview(w)
    assert not w.reset_examples.isHidden()
    assert preview.call_args.args[1] == ['/custom/example.png']
    assert w.files == ['/photos/first.jpg', '/photos/second.jpg']
    w.reset_examples.click(); _wait_for_preview(w)
    assert w.reset_examples.isHidden() and w.example_files is None
    assert w.example_selector.count() == 2
    values = {w.table.item(i, 0).text(): w.table.item(i, 1).text() for i in range(w.table.rowCount())}
    assert 'Compressed size' not in values
    assert values['GPS'] == 'None detected (recognized fields)' and values['Originals'] == 'Always unchanged'
    w.duplicate()
    assert w.folder.isVisible() and not w.ask.isVisible()
    w.mode.setCurrentIndex(w.mode.findData('directory'))
    assert w.ask.isVisible() and w.directory_row.isVisible() and not w.folder.isVisible()
    w.ask.setChecked(True)
    assert not w.directory_row.isVisible()
    w.mode.setCurrentIndex(w.mode.findData('beside'))
    assert not w.ask.isVisible() and not w.directory_row.isVisible() and not w.folder.isVisible()
    w.close()
""")

    @unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
    def test_gui_toggles_update_actual_text_plan(self):
        self.run_gui("""
import subprocess
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import config_path
app = QApplication([])
sample = config_path().parent.parent/'sample.png'
subprocess.run(['magick', '-size', '2000x1000', 'xc:red', str(sample)], check=True)
before = sample.read_bytes()
w = RecipeWidget(files=[str(sample)])
def values():
    _wait_for_preview(w)
    return {w.table.item(i, 0).text(): w.table.item(i, 1).text() for i in range(w.table.rowCount())}
assert values()['Final format'] == 'JPEG'
assert values()['Output dimensions'].startswith('1600 × 800')
w.steps.item(3).setCheckState(Qt.Unchecked); w.update_preview()
assert values()['Final format'] == 'PNG'
w.steps.item(1).setCheckState(Qt.Unchecked); w.update_preview()
assert values()['Output dimensions'].startswith('2000 × 1000')
w.steps.item(4).setCheckState(Qt.Unchecked); w.update_preview()
assert values()['ICC'] == 'sRGB ICC'
w.steps.item(2).setCheckState(Qt.Unchecked); w.update_preview()
assert values()['ICC'] == 'Not included — no input profile detected'
w.steps.item(1).setCheckState(Qt.Checked); w.update_preview()
assert values()['Output dimensions'].startswith('1600 × 800')
assert sample.read_bytes() == before
assert not (sample.parent/'Web').exists()
w.close()
""")

    def test_editable_settings_fields_overrides_and_reset_inheritance(self):
        self.run_gui("""
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import config_path
from kim_recipe_image import SETTING_KEYS
app = QApplication([])
for key in SETTING_KEYS.values(): os.environ.pop(key, None)
settings = config_path().with_name('settings.conf'); settings.parent.mkdir(parents=True)
settings.write_text('KIM_COPYRIGHT_CREATOR=Sample Artist\\nKIM_COPYRIGHT_NOTICE=Copyright {YEAR} Sample\\nKIM_COPYRIGHT_USAGE_RIGHTS=Sample Terms\\n')
original = settings.read_bytes()
w = RecipeWidget()
for row, value in ((5, 'Sample Artist'), (6, 'Copyright {YEAR} Sample'), (7, 'Sample Terms')):
    w.steps.setCurrentRow(row)
    field = w.parameter_widgets['value']
    assert isinstance(field, QLineEdit) and field.isEnabled() and not field.isReadOnly()
    assert field.text() == value
    assert w.parameter_modes['value'].text() == 'Inherited from KIM6 Settings'
    assert not w.is_dirty()
    field.setText(value); field.textEdited.emit(value)
    assert w.recipe['steps'][row]['value'] == value and w.is_dirty()
    assert '[modified for this run]' in w.selector.currentText()
    w.parameter_resets['value'].click()
    assert w.recipe['steps'][row].get('value') is None
    assert w.parameter_widgets['value'].text() == value and not w.is_dirty()
assert settings.read_bytes() == original
settings.write_text('KIM_COPYRIGHT_CREATOR=\\nKIM_COPYRIGHT_NOTICE=\\nKIM_COPYRIGHT_USAGE_RIGHTS=\\n')
blank = settings.read_bytes()
w.steps.setCurrentRow(5); w.update_preview()
assert w.parameter_widgets['value'].text() == '' and not w.is_dirty()
w.parameter_widgets['value'].setText('Manually entered')
w.parameter_widgets['value'].textEdited.emit('Manually entered')
w.steps.item(5).setCheckState(Qt.Checked); w.update_preview()
assert 'no inherited Settings value' not in w.status.text()
assert w.recipe['steps'][5]['value'] == 'Manually entered'
w.parameter_resets['value'].click()
assert w.parameter_widgets['value'].text() == ''
assert w.recipe['steps'][5].get('value') is None
assert 'no inherited Settings value' in w.status.text()
assert w.recipe['steps'][5]['enabled'] is True
w.steps.item(5).setCheckState(Qt.Unchecked); w.update_preview()
assert 'no inherited Settings value' not in w.status.text()
assert not w.is_dirty()
assert settings.read_bytes() == blank and not config_path().exists()
w.close()
""")

    def test_builtin_temporary_parameters_duplicate_save_and_inherited_updates(self):
        self.run_gui("""
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import kim_recipe_core as core
from kim_recipe_dialog import RecipeWidget
from kim_recipe_image import SETTING_KEYS
app = QApplication([])
for key in SETTING_KEYS.values(): os.environ.pop(key, None)
settings = core.config_path().with_name('settings.conf'); settings.parent.mkdir(parents=True)
settings.write_text('KIM_COPYRIGHT_CREATOR=Settings One\\n')
builtins_path = Path(core.__file__).resolve().parent.parent/'recipes'/'builtins.json'
shipped = builtins_path.read_bytes()
w = RecipeWidget(); assert not w.reset_builtin.isEnabled()
w.steps.setCurrentRow(1); w.parameter_widgets['max_width'].setValue(1800)
w.steps.setCurrentRow(3); w.parameter_widgets['quality'].setValue(87)
w.steps.setCurrentRow(5)
w.parameter_widgets['value'].setText('Temporary Artist'); w.parameter_widgets['value'].textEdited.emit('Temporary Artist')
w.steps.item(5).setCheckState(Qt.Checked)
assert w.is_dirty() and w.reset_builtin.isEnabled()
assert w.selector.currentText() == 'Web Export [modified for this run]'
assert not core.config_path().exists() and builtins_path.read_bytes() == shipped
w.reset_builtin.click()
assert not w.is_dirty() and w.selector.currentText() == 'Web Export [built-in]'
assert w.recipe['steps'][1]['max_width'] == 1600 and w.recipe['steps'][3]['quality'] == 95
assert all(not w.recipe['steps'][i]['enabled'] for i in (5, 6, 7))
w.steps.setCurrentRow(5)
assert w.parameter_widgets['value'].text() == 'Settings One'
w.parameter_widgets['value'].setText('Duplicated Artist'); w.parameter_widgets['value'].textEdited.emit('Duplicated Artist')
w.steps.item(5).setCheckState(Qt.Checked)
w.duplicate()
assert w.is_dirty() and w.management_buttons['Save'].isEnabled()
assert core.load_users() == []
assert w.save()
assert core.load_users()[0]['steps'][5]['value'] == 'Duplicated Artist'
w.steps.setCurrentRow(5)
w.parameter_widgets['value'].setText('Saved override'); w.parameter_widgets['value'].textEdited.emit('Saved override')
assert w.selector.currentText().endswith('*') and w.management_buttons['Save'].isEnabled()
assert w.save() and not w.is_dirty() and not w.selector.currentText().endswith('*')
settings.write_text('KIM_COPYRIGHT_CREATOR=Settings Two\\n'); unchanged = settings.read_bytes()
w.update_preview()
assert w.parameter_widgets['value'].text() == 'Saved override'
assert core.load_users()[0]['steps'][5]['value'] == 'Saved override'
w.parameter_resets['value'].click()
assert w.parameter_widgets['value'].text() == 'Settings Two' and w.is_dirty()
assert w.save() and core.load_users()[0]['steps'][5].get('value') is None
settings.write_text('KIM_COPYRIGHT_CREATOR=Settings Three\\n'); unchanged = settings.read_bytes()
w.update_preview()
assert w.parameter_widgets['value'].text() == 'Settings Three' and not w.is_dirty()
assert settings.read_bytes() == unchanged and builtins_path.read_bytes() == shipped
w.selector.setCurrentIndex(0)
assert w.recipe == core.builtins()[0]
assert w.recipe['steps'][5].get('value') is None and not w.recipe['steps'][5]['enabled']
w.close()
""")

    def test_step_defaults_and_reliable_dirty_indicators(self):
        self.run_gui("""
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import config_path
app = QApplication([])
w = RecipeWidget()
w.new()
w.add_step('image.resize')
w.steps.item(1).setCheckState(Qt.Unchecked)
assert w.save()
assert not w.is_dirty() and not w.management_buttons['Save'].isEnabled()
baseline = config_path().read_bytes()
w.steps.setCurrentRow(1)
width = w.parameter_widgets['max_width']
width.setValue(3000)
assert w.is_dirty() and w.selector.currentText().endswith('*') and w.management_buttons['Save'].isEnabled()
width.setValue(2048)
assert not w.is_dirty() and not w.selector.currentText().endswith('*')
width.setValue(3000)
w.step_defaults_button.click()
assert w.recipe['steps'][1] == {'op': 'image.resize', 'max_width': 2048, 'max_height': 2048, 'upscale': False, 'enabled': False}
assert not w.is_dirty() and w.recipe['steps'][0]['pattern'] == '{filename}_recipe'
w.steps.item(0).setCheckState(Qt.Unchecked); assert w.is_dirty()
w.steps.item(0).setCheckState(Qt.Checked); assert not w.is_dirty()
w.steps.setCurrentRow(0); w.steps.setCurrentRow(1); assert not w.is_dirty()
with patch('kim_recipe_dialog.preview', return_value=[]):
    w.set_examples(['/examples/Photo One.jpg', '/examples/Photo Two.jpg'])
    w.example_selector.setCurrentIndex(1)
    assert not w.is_dirty() and not w.management_buttons['Save'].isEnabled()
assert config_path().read_bytes() == baseline
for op, key, changed in (('image.rotate', 'degrees', 180), ('image.convert', 'quality', 77),
                         ('image.color', 'mode', 'srgb'), ('file.rename_output', 'pattern', '{stem}_changed')):
    w.add_step(op)
    row = w.steps.currentRow()
    w.steps.item(row).setCheckState(Qt.Unchecked)
    w.parameter(row, key, changed)
    assert w.step_defaults_button.text() == 'Reset Step Defaults'
    w.step_defaults_button.click()
    assert w.recipe['steps'][row][key] == w.definitions[op]['parameters'][key]['default']
    assert w.recipe['steps'][row]['enabled'] is False
w.close()
""")

    def test_operation_toolbar_arrow_layout_and_preview_label(self):
        self.run_gui("""
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QToolButton
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeyEvent
from kim_recipe_dialog import RecipeWidget
app = QApplication([])
with patch('kim_recipe_dialog.preview', return_value=[]):
    w = RecipeWidget(files=['/photos/Photo One.jpg', '/photos/Photo Two.jpg'])
    w.resize(1180, 850); w.show(); app.processEvents()
    assert w.example_label.text() == 'Example photo (preview only)'
    assert w.example_selector.currentText() == 'Photo One.jpg'
    assert isinstance(w.move_up, QToolButton) and isinstance(w.move_down, QToolButton)
    assert w.move_up.text() == '' and w.move_down.text() == ''
    assert w.move_up.toolTip() and w.move_down.toolTip()
    assert w.move_up.shortcut().toString() == 'Alt+Up'
    assert w.move_down.shortcut().toString() == 'Alt+Down'
    assert not w.move_up.isEnabled() and not w.move_down.isEnabled()
    if w.move_up.icon().isNull(): assert w.move_up.arrowType() == Qt.UpArrow
    if w.move_down.icon().isNull(): assert w.move_down.arrowType() == Qt.DownArrow
    assert w.operation_bar.count() == 2
    assert w.operation.text() == 'Add Operation…' and [b.text() for b in w.step_buttons] == ['Remove']
    assert w.operation.mapTo(w, QPoint()).y() < w.steps.mapTo(w, QPoint()).y()
    assert w.move_up.mapTo(w, QPoint()).x() >= w.steps.mapTo(w, QPoint(w.steps.width(), 0)).x()
    w.duplicate(); assert w.save()
    assert not w.move_up.isEnabled() and w.move_down.isEnabled()
    w.steps.setFocus()
    QApplication.sendEvent(w.steps, QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    QApplication.sendEvent(w.steps, QKeyEvent(QEvent.KeyRelease, Qt.Key_Down, Qt.NoModifier))
    assert w.steps.currentRow() == 1 and w.move_up.isEnabled()
    w.steps.setCurrentRow(w.steps.count()-1)
    assert w.move_up.isEnabled() and not w.move_down.isEnabled()
    w.steps.setCurrentRow(2)
    w.move_up.click()
    assert w.steps.currentRow() == 1 and w.is_dirty()
    w.move_down.click()
    assert w.steps.currentRow() == 2 and not w.is_dirty()
    w.selector.setCurrentIndex(0)
    assert not w.move_up.isEnabled() and not w.move_down.isEnabled()
    w.close()
""")

    def test_reusable_widget_management_offscreen(self):
        import importlib.util
        if importlib.util.find_spec('PySide6') is None:
            self.skipTest('PySide6 unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            code = """
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from kim_recipe_dialog import RecipeWidget
from kim_recipe_core import read_recipes, config_path
app = QApplication([])
w = RecipeWidget()
assert w.immutable
w.duplicate()
assert not w.immutable
w.name.setText('GUI test'); w.changed(); w.save()
assert read_recipes(config_path())[0]['name'] == 'GUI test'
w.add_step('image.flip')
assert w.recipe['steps'][-1]['op'] == 'image.flip'
w.move(-1); assert w.recipe['steps'][-2]['op'] == 'image.flip'
w.remove_step(); w.save()
assert not w.is_dirty()
with patch('kim_recipe_dialog.QMessageBox.question', return_value=QMessageBox.Yes):
    w.remove()
assert read_recipes(config_path()) == []
w.close()
"""
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                timeout=30, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen',
                                 'XDG_CONFIG_HOME': tmp, 'PYTHONPATH': str(ROOT/'src/bin'),
                                 'KIM_COPYRIGHT_CREATOR': '', 'KIM_COPYRIGHT_NOTICE': '', 'KIM_COPYRIGHT_USAGE_RIGHTS': ''})
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
