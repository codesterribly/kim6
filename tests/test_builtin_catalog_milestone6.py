#!/usr/bin/env python3
"""Milestone 6 verification for the approved built-in Recipe catalog."""
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src' / 'bin'))

import kim_recipe_core as core
import kim_recipe_params as kp


def sha256_noatime(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOATIME)
    h = hashlib.sha256()
    with os.fdopen(fd, 'rb') as stream:
        while chunk := stream.read(65536):
            h.update(chunk)
    return h.hexdigest()


def source_sig(path: Path) -> dict:
    st = path.stat()
    return {
        'sha256': sha256_noatime(path),
        'size': st.st_size,
        'atime_ns': st.st_atime_ns,
        'mtime_ns': st.st_mtime_ns,
        'ctime_ns': st.st_ctime_ns,
    }


def age_file(path: Path) -> None:
    os.utime(path, ns=(10**18, 15 * 10**17))


def make_rich_fixture(path: Path, *, width=2400, height=1600) -> None:
    subprocess.run(
        ['magick', '-size', f'{width}x{height}', 'xc:navy', '-fill', 'gold',
         '-draw', f'rectangle 0,0 {width // 2},{height // 2}', '-depth', '8', str(path)],
        check=True, timeout=20, capture_output=True,
    )
    subprocess.run(
        [
            'exiftool', '-overwrite_original',
            '-Artist=Original Photographer',
            '-Copyright=Original Copyright 2024',
            '-XMP-xmpRights:UsageTerms=Original Editorial Terms',
            '-XMP-dc:Description=Sunset over the rocky coast',
            '-IPTC:Caption-Abstract=Sunset over the rocky coast',
            '-IPTC:Keywords=coast',
            '-IPTC:Keywords=sunset',
            '-DateTimeOriginal=2024:07:04 18:30:00',
            '-OffsetTimeOriginal=-04:00',
            '-GPSLatitude=44.3876', '-GPSLatitudeRef=N',
            '-GPSLongitude=68.2039', '-GPSLongitudeRef=W',
            str(path),
        ],
        check=True, timeout=20, capture_output=True,
    )
    age_file(path)


def read_meta(path: Path) -> dict:
    out = subprocess.check_output(
        ['exiftool', '-json', '-Artist', '-Copyright', '-XMP-xmpRights:UsageTerms',
         '-XMP-dc:Description', '-IPTC:Caption-Abstract', '-IPTC:Keywords',
         '-DateTimeOriginal', '-GPSLatitude', '-GPSLongitude', str(path)],
        timeout=20, text=True,
    )
    return json.loads(out)[0]


def identify_info(path: Path) -> tuple[str, int, int]:
    out = subprocess.check_output(
        ['identify', '-format', '%m|%w|%h', str(path)],
        timeout=20, text=True,
    ).strip()
    fmt, w, h = out.split('|')
    return fmt, int(w), int(h)


class BuiltinCatalogMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self._old_xdg = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = str(Path(self.temp.name) / 'xdg')
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._old_xdg is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = self._old_xdg

    def test_catalog_hierarchy_ids_descriptions_and_schemas(self):
        catalog = core.builtin_catalog()
        by_id = {r['id']: (cat, r) for cat, r in catalog}
        expected = [
            ('Common', 'web-export', 'Web Export', False),
            ('Common', 'share-privately', 'Share Privately', False),
            ('Adventure', 'protect-sensitive-locations', 'Protect Sensitive Locations', True),
            ('Asset Management', 'create-client-proofs', 'Create Client Proofs', True),
            ('Asset Management', 'prepare-client-delivery', 'Prepare Client Delivery', True),
            ('Asset Management', 'prepare-editorial-submission', 'Prepare Editorial Submission', True),
            ('Asset Management', 'organize-by-capture-date', 'Organize by Capture Date', True),
            ('Asset Management', 'apply-photographer-attribution', 'Apply Photographer Attribution', True),
        ]
        self.assertEqual(len(catalog), len(expected))
        for (exp_cat, exp_id, exp_name, exp_param), (cat, r) in zip(expected, catalog):
            self.assertEqual(cat, exp_cat)
            self.assertEqual(r['id'], exp_id)
            self.assertEqual(r['name'], exp_name)
            self.assertEqual(kp.is_parameterized(r), exp_param)
            self.assertNotIn('folder', r)
            self.assertNotIn('dolphin_shortcut', r)
            self.assertNotIn('\u2014', r['description'])
            kp.validate_authored(r)
            concrete = kp.resolve_recipe(r, {}, validated=True)
            core.validate(concrete)

        # Verify advanced parameter placement on Create Client Proofs and Prepare Client Delivery.
        proofs = by_id['create-client-proofs'][1]
        proof_ord = [p['id'] for p in proofs['parameters'] if not p.get('advanced', False)]
        proof_adv = [p['id'] for p in proofs['parameters'] if p.get('advanced', False)]
        self.assertEqual(proof_ord, ['project_name', 'max_dimension'])
        self.assertIn('jpeg_quality', proof_adv)
        self.assertIn('remove_gps', proof_adv)
        self.assertIn('apply_attribution', proof_adv)

        delivery = by_id['prepare-client-delivery'][1]
        deliv_ord = [p['id'] for p in delivery['parameters'] if not p.get('advanced', False)]
        deliv_adv = [p['id'] for p in delivery['parameters'] if p.get('advanced', False)]
        self.assertEqual(deliv_ord, ['project_name'])
        self.assertIn('jpeg_quality', deliv_adv)
        self.assertIn('apply_attribution', deliv_adv)


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
class BuiltinCatalogExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.xdg_dir = self.base / 'xdg'
        self.cfg_dir = self.xdg_dir / 'kimng'
        self.cfg_dir.mkdir(parents=True)
        self._old_xdg = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = str(self.xdg_dir)
        self.addCleanup(self._restore_env)

        self.large_jpg = self.base / 'harbor_large.jpg'
        self.small_jpg = self.base / 'harbor_small.jpg'
        self.src_png = self.base / 'studio_master.png'
        make_rich_fixture(self.large_jpg, width=2400, height=1600)
        make_rich_fixture(self.small_jpg, width=800, height=600)
        make_rich_fixture(self.src_png, width=640, height=480)
        self.before_large = source_sig(self.large_jpg)
        self.before_small = source_sig(self.small_jpg)
        self.before_png = source_sig(self.src_png)

    def _restore_env(self):
        if self._old_xdg is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = self._old_xdg

    def _assert_originals_intact(self):
        self.assertEqual(source_sig(self.large_jpg), self.before_large)
        self.assertEqual(source_sig(self.small_jpg), self.before_small)
        self.assertEqual(source_sig(self.src_png), self.before_png)

    def test_01_share_privately_strips_all_metadata_and_no_upscale(self):
        recipe = core.lookup_recipe('share-privately')
        concrete = kp.resolve_recipe(recipe, {}, validated=True)
        res = core.execute(concrete, [self.large_jpg, self.small_jpg])
        self.assertTrue(all(r['ok'] for r in res), res)

        out_large = Path(res[0]['output'])
        out_small = Path(res[1]['output'])
        self.assertEqual(out_large, self.base / 'Private' / 'harbor_large_private.jpg')
        self.assertEqual(out_small, self.base / 'Private' / 'harbor_small_private.jpg')

        fmt_l, wl, hl = identify_info(out_large)
        self.assertEqual((fmt_l, wl, hl), ('JPEG', 2048, 1365))
        fmt_s, ws, hs = identify_info(out_small)
        self.assertEqual((fmt_s, ws, hs), ('JPEG', 800, 600))

        meta = read_meta(out_large)
        for forbidden in ('Artist', 'Copyright', 'UsageTerms', 'Description', 'Caption-Abstract', 'Keywords', 'GPSLatitude', 'GPSLongitude'):
            self.assertNotIn(forbidden, meta, f'Expected {forbidden} stripped in Share Privately: {meta}')
        self._assert_originals_intact()

    def test_02_create_client_proofs_default_and_custom(self):
        recipe = core.lookup_recipe('create-client-proofs')

        # Default: Proofs/<stem>_proof.jpg, <=1600, GPS removed, rights & caption preserved.
        c_def = kp.resolve_recipe(recipe, {}, validated=True)
        res_def = core.execute(c_def, [self.large_jpg, self.small_jpg])
        self.assertTrue(all(r['ok'] for r in res_def), res_def)
        out_def = Path(res_def[0]['output'])
        self.assertEqual(out_def, self.base / 'Proofs' / 'harbor_large_proof.jpg')
        self.assertEqual(identify_info(out_def), ('JPEG', 1600, 1067))
        self.assertEqual(identify_info(Path(res_def[1]['output'])), ('JPEG', 800, 600))
        meta_def = read_meta(out_def)
        self.assertNotIn('GPSLatitude', meta_def)
        self.assertNotIn('GPSLongitude', meta_def)
        self.assertEqual(meta_def.get('Artist'), 'Original Photographer')
        self.assertEqual(meta_def.get('Copyright'), 'Original Copyright 2024')
        self.assertEqual(meta_def.get('Description'), 'Sunset over the rocky coast')

        # Custom: Acme subfolder, max_dimension=800, keep GPS, explicit creator only (leaves Copyright intact).
        c_cust = kp.resolve_recipe(
            recipe,
            {
                'project_name': 'Acme',
                'max_dimension': 800,
                'jpeg_quality': 85,
                'remove_gps': False,
                'apply_attribution': True,
                'creator': 'Studio Proof Author',
                'copyright_notice': '',
                'usage_rights': '',
            },
            validated=True,
        )
        res_cust = core.execute(c_cust, [self.large_jpg])
        self.assertTrue(res_cust[0]['ok'], res_cust)
        out_cust = Path(res_cust[0]['output'])
        self.assertEqual(out_cust, self.base / 'Proofs' / 'Acme' / 'harbor_large_proof.jpg')
        self.assertEqual(identify_info(out_cust), ('JPEG', 800, 533))
        meta_cust = read_meta(out_cust)
        self.assertIn('GPSLatitude', meta_cust)
        self.assertEqual(meta_cust.get('Artist'), 'Studio Proof Author')
        self.assertEqual(meta_cust.get('Copyright'), 'Original Copyright 2024')
        self._assert_originals_intact()

    def test_03_prepare_client_delivery_full_res_and_no_silent_overwrite(self):
        # Configure KIMng Settings to verify default run NEVER silently overwrites existing attribution.
        (self.cfg_dir / 'settings.conf').write_text(
            'KIM_COPYRIGHT_CREATOR=Settings Default Studio\n'
            'KIM_COPYRIGHT_NOTICE=Settings Notice 2026\n'
            'KIM_COPYRIGHT_USAGE_RIGHTS=Settings Rights\n',
            encoding='utf-8',
        )
        recipe = core.lookup_recipe('prepare-client-delivery')

        # Default run: full resolution, Delivery subfolder, existing metadata untouched.
        c_def = kp.resolve_recipe(recipe, {}, validated=True)
        res_def = core.execute(c_def, [self.large_jpg])
        self.assertTrue(res_def[0]['ok'], res_def)
        out_def = Path(res_def[0]['output'])
        self.assertEqual(out_def, self.base / 'Delivery' / 'harbor_large_delivery.jpg')
        self.assertEqual(identify_info(out_def), ('JPEG', 2400, 1600))
        meta_def = read_meta(out_def)
        self.assertEqual(meta_def.get('Artist'), 'Original Photographer')
        self.assertEqual(meta_def.get('Copyright'), 'Original Copyright 2024')
        self.assertEqual(meta_def.get('Description'), 'Sunset over the rocky coast')

        # Explicit attribution enabled: inherits Settings defaults unless overridden.
        c_exp = kp.resolve_recipe(
            recipe,
            {'project_name': 'ClientFinal', 'apply_attribution': True},
            validated=True,
        )
        res_exp = core.execute(c_exp, [self.large_jpg])
        self.assertTrue(res_exp[0]['ok'], res_exp)
        out_exp = Path(res_exp[0]['output'])
        self.assertEqual(out_exp, self.base / 'Delivery' / 'ClientFinal' / 'harbor_large_delivery.jpg')
        meta_exp = read_meta(out_exp)
        self.assertEqual(meta_exp.get('Artist'), 'Settings Default Studio')
        self.assertEqual(meta_exp.get('Copyright'), 'Settings Notice 2026')
        self.assertEqual(meta_exp.get('UsageTerms'), 'Settings Rights')
        self._assert_originals_intact()

    def test_04_apply_photographer_attribution_preserves_format_and_unrelated_metadata(self):
        recipe = core.lookup_recipe('apply-photographer-attribution')

        # Empty answers (no Settings): leaves existing attribution & unrelated metadata intact, PNG stays PNG.
        c_empty = kp.resolve_recipe(recipe, {}, validated=True)
        res_empty = core.execute(c_empty, [self.src_png])
        self.assertTrue(res_empty[0]['ok'], res_empty)
        out_empty = Path(res_empty[0]['output'])
        self.assertEqual(out_empty, self.base / 'Attributed' / 'studio_master_attributed.png')
        self.assertEqual(identify_info(out_empty), ('PNG', 640, 480))
        meta_empty = read_meta(out_empty)
        self.assertEqual(meta_empty.get('Artist'), 'Original Photographer')
        self.assertEqual(meta_empty.get('Copyright'), 'Original Copyright 2024')
        self.assertEqual(meta_empty.get('Description'), 'Sunset over the rocky coast')

        # Remove first output to test explicit partial update on the same PNG.
        out_empty.unlink()
        c_part = kp.resolve_recipe(
            recipe,
            {'creator': 'Updated Artist Only', 'copyright_notice': '', 'usage_rights': ''},
            validated=True,
        )
        res_part = core.execute(c_part, [self.src_png])
        self.assertTrue(res_part[0]['ok'], res_part)
        meta_part = read_meta(Path(res_part[0]['output']))
        self.assertEqual(meta_part.get('Artist'), 'Updated Artist Only')
        self.assertEqual(meta_part.get('Copyright'), 'Original Copyright 2024')
        self.assertEqual(meta_part.get('Description'), 'Sunset over the rocky coast')
        self.assertIn('GPSLatitude', meta_part)
        self._assert_originals_intact()

    def test_05_duplicate_and_late_collision_protection_on_new_builtins(self):
        recipe = core.lookup_recipe('share-privately')
        concrete = kp.resolve_recipe(recipe, {}, validated=True)
        # Duplicate source in same batch -> blocked by block_output_collisions.
        rows = core.preview(concrete, [self.small_jpg, self.small_jpg])
        core.block_output_collisions(rows)
        self.assertTrue(all(row.problems for row in rows))

        # Late collision: approve clean plan, then create target on disk before execute -> fails closed.
        clean_rows = core.preview(concrete, [self.small_jpg])
        plan = core.approve_rows(concrete, [self.small_jpg], clean_rows)
        target = Path(clean_rows[0].output)
        target.parent.mkdir(parents=True, exist_ok=True)
        sentinel = b'SENTINEL_DO_NOT_OVERWRITE'
        target.write_bytes(sentinel)
        res = core.execute(concrete, [self.small_jpg], approved_plan=plan)
        self.assertFalse(res[0]['ok'])
        self.assertEqual(target.read_bytes(), sentinel)
        self._assert_originals_intact()

    def test_06_protect_sensitive_locations_remove_reduce_all_grids_and_edge_cases(self):
        import kim_location as kloc

        recipe = core.lookup_recipe('protect-sensitive-locations')
        # 1. Conditional visibility: precision_grid hidden for 'remove', visible for 'reduce'.
        ev_rem = kp.evaluate_parameters(recipe, {'protection_mode': 'remove'}, validated=True)
        self.assertEqual([p['id'] for p in ev_rem['active']], ['protection_mode'])
        ev_red = kp.evaluate_parameters(recipe, {'protection_mode': 'reduce'}, validated=True)
        self.assertEqual([p['id'] for p in ev_red['active']], ['protection_mode', 'precision_grid'])

        # 2. Operation order validation: pixel op after metadata.reduce_gps rejected.
        bad_order = {
            'schema': 3, 'id': 'bad-gps-order', 'name': 'Bad Order', 'description': '',
            'media': 'image', 'destination': {'mode': 'beside'},
            'steps': [
                {'op': 'metadata.reduce_gps', 'grid': '1000'},
                {'op': 'image.resize', 'max_width': 800, 'max_height': 800, 'upscale': False},
            ],
        }
        with self.assertRaises(core.RecipeError):
            core.validate(bad_order)

        # Build a rich JPEG fixture with altitude, direction, destination GPS, XMP GPS, and place names.
        gps_rich = self.base / 'alpine_peak.jpg'
        make_rich_fixture(gps_rich, width=1000, height=700)
        subprocess.run(
            [
                'exiftool', '-overwrite_original',
                '-GPSAltitude=1450', '-GPSAltitudeRef#=0',
                '-GPSImgDirection=135.5', '-GPSImgDirectionRef=T',
                '-GPSDestLatitude=44.4000', '-GPSDestLatitudeRef=N',
                '-GPSDestLongitude=68.2500', '-GPSDestLongitudeRef=W',
                '-XMP-exif:GPSLatitude=44.3876 N', '-XMP-exif:GPSLongitude=68.2039 W',
                '-IPTC:City=Bar Harbor', '-IPTC:Country-PrimaryLocationName=USA',
                str(gps_rich),
            ],
            check=True, timeout=20, capture_output=True,
        )
        age_file(gps_rich)
        before_rich = source_sig(gps_rich)

        # 3. Default mode ('remove') on JPEG and PNG: strips all GPS, preserves format & unrelated metadata.
        c_rem = kp.resolve_recipe(recipe, {'protection_mode': 'remove'}, validated=True)
        res_rem = core.execute(c_rem, [gps_rich, self.src_png])
        self.assertTrue(all(r['ok'] for r in res_rem), res_rem)
        out_jpg = Path(res_rem[0]['output'])
        out_png = Path(res_rem[1]['output'])
        self.assertEqual(out_jpg, self.base / 'Protected Locations' / 'alpine_peak_protected.jpg')
        self.assertEqual(out_png, self.base / 'Protected Locations' / 'studio_frame_protected.png' if out_png.name.startswith('studio_frame') else self.base / 'Protected Locations' / 'studio_master_protected.png')
        self.assertEqual(identify_info(out_jpg), ('JPEG', 1000, 700))
        self.assertEqual(identify_info(out_png), ('PNG', 640, 480))
        meta_rem = read_meta(out_jpg)
        self.assertNotIn('GPSLatitude', meta_rem)
        self.assertNotIn('GPSLongitude', meta_rem)
        self.assertEqual(meta_rem.get('Artist'), 'Original Photographer')
        self.assertEqual(meta_rem.get('Copyright'), 'Original Copyright 2024')
        self.assertEqual(meta_rem.get('Description'), 'Sunset over the rocky coast')
        out_jpg.unlink()
        out_png.unlink()

        # 4. Reduce precision at ALL 4 supported grids (100, 1000, 5000, 10000 m).
        for grid_str in ('100', '1000', '5000', '10000'):
            expected_pos, _ = kloc.generalize([44.3876, -68.2039], int(grid_str))
            c_red = kp.resolve_recipe(
                recipe,
                {'protection_mode': 'reduce', 'precision_grid': grid_str},
                validated=True,
            )
            res_red = core.execute(c_red, [gps_rich])
            self.assertTrue(res_red[0]['ok'], f'grid={grid_str}: {res_red}')
            out_path = Path(res_red[0]['output'])
            self.assertEqual(identify_info(out_path), ('JPEG', 1000, 700))
            out_data = kloc.read_many([str(out_path)], complete=True)[str(out_path)]
            out_info = kloc.summarize(out_data['raw'])
            self.assertIsNotNone(out_info['position'])
            self.assertTrue(
                kloc.same_position(out_info['position'], expected_pos),
                f'grid={grid_str}: {out_info["position"]} != {expected_pos}',
            )
            # Altitude, direction, destination, and place-name tags must be cleared.
            raw_json = subprocess.check_output(
                ['exiftool', '-json', '-GPSAltitude', '-GPSImgDirection',
                 '-GPSDestLatitude', '-IPTC:City', '-Artist', '-Copyright', '-XMP-dc:Description', str(out_path)],
                timeout=20, text=True,
            )
            checked = json.loads(raw_json)[0]
            for cleared in ('GPSAltitude', 'GPSImgDirection', 'GPSDestLatitude', 'City'):
                self.assertNotIn(cleared, checked, f'grid={grid_str} leaked {cleared}: {checked}')
            self.assertEqual(checked.get('Artist'), 'Original Photographer')
            self.assertEqual(checked.get('Copyright'), 'Original Copyright 2024')
            self.assertEqual(checked.get('Description'), 'Sunset over the rocky coast')
            out_path.unlink()

        # 5. Image without GPS: remove succeeds, reduce explicitly blocks in preview.
        no_gps = self.base / 'no_gps.jpg'
        subprocess.run(['magick', '-size', '200x150', 'xc:green', str(no_gps)], check=True, timeout=20)
        age_file(no_gps)
        before_nogps = source_sig(no_gps)
        c_red_1k = kp.resolve_recipe(recipe, {'protection_mode': 'reduce', 'precision_grid': '1000'}, validated=True)
        rows_nogps = core.preview(c_red_1k, [no_gps])
        self.assertTrue(rows_nogps[0].problems)
        self.assertIn('No camera GPS coordinates', rows_nogps[0].problems[0])

        # 6. Malformed/conflicting GPS metadata: reduce explicitly blocks in preview.
        bad_gps = self.base / 'conflicting_gps.jpg'
        make_rich_fixture(bad_gps, width=200, height=150)
        subprocess.run(
            ['exiftool', '-overwrite_original', '-XMP-exif:GPSLatitude=10.0 N', '-XMP-exif:GPSLongitude=10.0 E', str(bad_gps)],
            check=True, timeout=20, capture_output=True,
        )
        age_file(bad_gps)
        before_bad = source_sig(bad_gps)
        rows_bad = core.preview(c_red_1k, [bad_gps])
        self.assertTrue(rows_bad[0].problems)
        self.assertIn('GPS precision reduction blocked', rows_bad[0].problems[0])

        # Verify all original images preserved all 5 integrity attributes.
        self.assertEqual(source_sig(gps_rich), before_rich)
        self.assertEqual(source_sig(no_gps), before_nogps)
        self.assertEqual(source_sig(bad_gps), before_bad)
        self._assert_originals_intact()

    def test_07_organize_by_capture_date_nested_destinations_and_safety(self):
        recipe = core.lookup_recipe('organize-by-capture-date')

        # Build fixtures across different years, dates, formats, and source directories.
        dir_a = self.base / 'roll_a'
        dir_b = self.base / 'roll_b'
        dir_a.mkdir()
        dir_b.mkdir()
        img_2024 = dir_a / 'IMG_2024.jpg'
        img_2026_a = dir_a / 'IMG_2026A.jpg'
        img_2026_b = dir_a / 'IMG_2026B.png'
        img_roll_b = dir_b / 'IMG_ROLLB.jpg'
        img_nodate = dir_a / 'IMG_NODATE.jpg'
        img_baddate = dir_a / 'IMG_BADDATE.jpg'

        make_rich_fixture(img_2024, width=320, height=200)  # DateTimeOriginal=2024:07:04
        make_rich_fixture(img_2026_a, width=320, height=200)
        subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2026:11:20 09:15:00', str(img_2026_a)], check=True, capture_output=True)
        age_file(img_2026_a)
        make_rich_fixture(img_2026_b, width=240, height=180)
        subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2026:11:21 16:45:00', str(img_2026_b)], check=True, capture_output=True)
        age_file(img_2026_b)
        make_rich_fixture(img_roll_b, width=300, height=200)
        subprocess.run(['exiftool', '-overwrite_original', '-DateTimeOriginal=2026:11:20 12:00:00', str(img_roll_b)], check=True, capture_output=True)
        age_file(img_roll_b)

        subprocess.run(['magick', '-size', '120x90', 'xc:gray', str(img_nodate)], check=True, capture_output=True)
        age_file(img_nodate)
        subprocess.run(['magick', '-size', '120x90', 'xc:gray', str(img_baddate)], check=True, capture_output=True)
        subprocess.run(['exiftool', '-overwrite_original', '-m', '-EXIF:DateTimeOriginal#=2026:13:45 99:00:00', str(img_baddate)], check=True, capture_output=True)
        age_file(img_baddate)

        sigs_before = {p: source_sig(p) for p in (img_2024, img_2026_a, img_2026_b, img_roll_b, img_nodate, img_baddate)}

        # 1. Invalid project names, traversal, absolute paths, and separator injection must be rejected.
        for bad_proj in ('../escape', 'a/b', 'a\\b', '/etc/passwd', '.', '..'):
            with self.assertRaises(core.RecipeError, msg=f'Expected rejection for {bad_proj!r}'):
                kp.resolve_recipe(recipe, {'project_name': bad_proj}, validated=True)

        # 2. Preview without project: resolves nested paths per image and creates ZERO directories.
        c_noproj = kp.resolve_recipe(recipe, {'project_name': ''}, validated=True)
        self.assertEqual(c_noproj['destination']['folder'], 'By Date/{year}/{capture_date}')
        rows = core.preview(c_noproj, [img_2024, img_2026_a, img_2026_b, img_roll_b])
        self.assertFalse((dir_a / 'By Date').exists(), 'Preview must never create directories')
        self.assertFalse((dir_b / 'By Date').exists(), 'Preview must never create directories')
        self.assertEqual(rows[0].output, str(dir_a / 'By Date' / '2024' / '2024-07-04' / 'IMG_2024.jpg'))
        self.assertEqual(rows[1].output, str(dir_a / 'By Date' / '2026' / '2026-11-20' / 'IMG_2026A.jpg'))
        self.assertEqual(rows[2].output, str(dir_a / 'By Date' / '2026' / '2026-11-21' / 'IMG_2026B.png'))
        self.assertEqual(rows[3].output, str(dir_b / 'By Date' / '2026' / '2026-11-20' / 'IMG_ROLLB.jpg'))

        # 3. Execute without project: byte-for-byte identical copies across mixed dates & source dirs.
        res = core.execute(c_noproj, [img_2024, img_2026_a, img_2026_b, img_roll_b])
        self.assertTrue(all(r['ok'] for r in res), res)
        for src, r in zip((img_2024, img_2026_a, img_2026_b, img_roll_b), res):
            out = Path(r['output'])
            self.assertTrue(out.is_file())
            self.assertEqual(sha256_noatime(out), sha256_noatime(src), f'Copy not byte-for-byte equal for {src.name}')
            self.assertEqual(out.stat().st_size, src.stat().st_size)

        # 4. Execute WITH project name ('Malta') + explicit shared destination directory.
        shared_dest = self.base / 'shared_archive'
        shared_dest.mkdir()
        c_proj = kp.resolve_recipe(recipe, {'project_name': 'Malta'}, validated=True)
        self.assertEqual(c_proj['destination']['folder'], 'By Date/Malta/{year}/{capture_date}')
        res_shared = core.execute(c_proj, [img_2024, img_2026_a], chosen=str(shared_dest))
        self.assertTrue(all(r['ok'] for r in res_shared), res_shared)
        self.assertEqual(Path(res_shared[0]['output']), shared_dest / 'By Date' / 'Malta' / '2024' / '2024-07-04' / 'IMG_2024.jpg')
        self.assertEqual(Path(res_shared[1]['output']), shared_dest / 'By Date' / 'Malta' / '2026' / '2026-11-20' / 'IMG_2026A.jpg')
        self.assertEqual(sha256_noatime(Path(res_shared[0]['output'])), sha256_noatime(img_2024))

        # 5. Missing and malformed capture dates must block explicitly (never substitute mtime).
        rows_missing = core.preview(c_noproj, [img_nodate, img_baddate])
        self.assertTrue(rows_missing[0].problems)
        self.assertIn('Capture date metadata is missing or invalid', rows_missing[0].problems[0])
        self.assertTrue(rows_missing[1].problems)
        self.assertIn('Capture date metadata is missing or invalid', rows_missing[1].problems[0])

        # 6. Symlink escape prevention on nested destination.
        sym_root = self.base / 'sym_test'
        sym_root.mkdir()
        outside = self.base / 'outside_target'
        outside.mkdir()
        (sym_root / 'By Date').symlink_to(outside)
        rows_sym = core.preview(c_noproj, [img_2024], chosen=str(sym_root))
        self.assertTrue(rows_sym[0].problems)
        self.assertIn('symlink', rows_sym[0].problems[0].lower())

        # 7. Intra-batch duplicate collision + existing collision + late collision fail-closed.
        dup_root = self.base / 'dup_nested'
        dup_root.mkdir()
        rows_dup = core.preview(c_noproj, [img_2024, img_2024], chosen=str(dup_root))
        self.assertTrue(all(r.problems for r in rows_dup))

        # Existing collision (already published into shared_dest above).
        rows_exist = core.preview(c_proj, [img_2024], chosen=str(shared_dest))
        self.assertTrue(rows_exist[0].problems)
        self.assertIn('already exists', rows_exist[0].problems[0])

        # Late collision: approve clean nested plan, then create target externally before execute -> fails closed.
        late_root = self.base / 'late_nested'
        late_root.mkdir()
        clean_rows = core.preview(c_noproj, [img_2024], chosen=str(late_root))
        plan = core.approve_rows(c_noproj, [img_2024], clean_rows, chosen=str(late_root))
        late_target = Path(clean_rows[0].output)
        late_target.parent.mkdir(parents=True, exist_ok=True)
        late_target.write_bytes(b'LATE_SENTINEL')
        res_late = core.execute(c_noproj, [img_2024], chosen=str(late_root), approved_plan=plan)
        self.assertFalse(res_late[0]['ok'])
        self.assertEqual(late_target.read_bytes(), b'LATE_SENTINEL')

        # 8. All 5 original-image integrity attributes preserved on every source.
        for p, before in sigs_before.items():
            self.assertEqual(source_sig(p), before, f'Source integrity violated for {p.name}')

    def test_08_prepare_editorial_submission_and_descriptive_metadata_ops(self):
        from kim_recipe_image import ImageHandler

        # 1. Verify operation picker registration, labels, categories, descriptions, and order validation.
        handler = ImageHandler()
        defs = handler.operation_definitions()
        for op in ('metadata.set_description', 'metadata.set_keywords'):
            self.assertIn(op, defs)
            self.assertEqual(defs[op]['category'], 'Metadata & Copyright')
            self.assertTrue(defs[op].get('description'))
        self.assertEqual(defs['metadata.set_keywords']['parameters']['mode']['choices'], ('unchanged', 'append', 'replace'))

        # Operation-order validation: pixel/convert steps after descriptive metadata ops must fail.
        with self.assertRaises(core.RecipeError):
            handler.validate_order([
                {'op': 'metadata.set_description', 'value': 'Test'},
                {'op': 'image.resize', 'max_width': 1000, 'max_height': 1000, 'upscale': False},
            ])
        with self.assertRaises(core.RecipeError):
            handler.validate_order([
                {'op': 'metadata.set_keywords', 'mode': 'append', 'keywords': 'a, b'},
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 90},
            ])

        # 2. Build a rich editorial fixture with EXIF capture, camera Make/Model, GPS,
        #    IPTC caption, XMP Description (x-default + fr language alt), IPTC & XMP keywords, and rights.
        ed_src = self.base / 'editorial_src.jpg'
        subprocess.run(
            ['magick', '-size', '3200x2000', 'xc:navy', '-fill', 'gold',
             '-draw', 'rectangle 0,0 1600,1000', '-depth', '8', str(ed_src)],
            check=True, timeout=20, capture_output=True,
        )
        subprocess.run(
            [
                'exiftool', '-overwrite_original',
                '-IPTC:CodedCharacterSet=UTF8',
                '-EXIF:Make=Fujifilm', '-EXIF:Model=X-T5',
                '-DateTimeOriginal=2025:09:15 10:20:30', '-OffsetTimeOriginal=+02:00',
                '-GPSLatitude=35.8989', '-GPSLatitudeRef=N',
                '-GPSLongitude=14.5146', '-GPSLongitudeRef=E',
                '-Artist=Original Author', '-Copyright=© 2025 Original Author',
                '-XMP-xmpRights:UsageTerms=Original Editorial License',
                '-XMP-dc:Description-x-default=Original Valletta harbor',
                '-XMP-dc:Description-fr=Port de La Valette',
                '-IPTC:Caption-Abstract=Original Valletta harbor',
                '-XMP-dc:Subject=malta', '-XMP-dc:Subject=harbor',
                '-IPTC:Keywords=malta', '-IPTC:Keywords=harbor',
                str(ed_src),
            ],
            check=True, timeout=20, capture_output=True,
        )
        age_file(ed_src)
        before_sig = source_sig(ed_src)

        def read_all_ed_meta(path: Path) -> dict:
            out = subprocess.check_output(
                ['exiftool', '-json', '-G1', '-a',
                 '-EXIF:Make', '-EXIF:Model', '-EXIF:DateTimeOriginal',
                 '-EXIF:GPSLatitude', '-EXIF:Artist', '-EXIF:Copyright',
                 '-XMP-xmpRights:UsageTerms',
                 '-XMP-dc:Description*', '-IPTC:Caption-Abstract',
                 '-XMP-dc:Subject', '-IPTC:Keywords', str(path)],
                timeout=20, text=True,
            )
            return json.loads(out)[0]

        def as_list(v):
            if v is None:
                return []
            return v if isinstance(v, list) else [v]

        recipe = core.lookup_recipe('prepare-editorial-submission')

        # 3. Default execution: full resolution, Editorial/, all existing metadata preserved unchanged.
        concrete_default = kp.resolve_recipe(recipe, {})
        res_def = core.execute(concrete_default, [ed_src])
        self.assertTrue(res_def[0]['ok'], res_def[0].get('error'))
        out_def = self.base / 'Editorial' / 'editorial_src_editorial.jpg'
        self.assertEqual(Path(res_def[0]['output']), out_def)
        self.assertEqual(identify_info(out_def), ('JPEG', 3200, 2000))
        m_def = read_all_ed_meta(out_def)
        self.assertEqual(m_def.get('IFD0:Make'), 'Fujifilm')
        self.assertEqual(m_def.get('IFD0:Model'), 'X-T5')
        self.assertEqual(m_def.get('ExifIFD:DateTimeOriginal'), '2025:09:15 10:20:30')
        self.assertIsNotNone(m_def.get('GPS:GPSLatitude'))
        self.assertEqual(m_def.get('IFD0:Artist'), 'Original Author')
        self.assertEqual(m_def.get('IFD0:Copyright'), '© 2025 Original Author')
        self.assertEqual(m_def.get('XMP-xmpRights:UsageTerms'), 'Original Editorial License')
        self.assertEqual(m_def.get('XMP-dc:Description'), 'Original Valletta harbor')
        self.assertEqual(m_def.get('XMP-dc:Description-fr'), 'Port de La Valette')
        self.assertEqual(m_def.get('IPTC:Caption-Abstract'), 'Original Valletta harbor')
        self.assertEqual(as_list(m_def.get('XMP-dc:Subject')), ['malta', 'harbor'])
        self.assertEqual(as_list(m_def.get('IPTC:Keywords')), ['malta', 'harbor'])

        # 4. Non-default: project name, optional resize (2400), non-ASCII caption update,
        #    keyword append with duplicates & non-ASCII, and explicit attribution.
        concrete_custom = kp.resolve_recipe(recipe, {
            'project_name': 'Magazine',
            'max_dimension': '2400',
            'caption': 'Valletta café at dusk — autumn issue',
            'keyword_mode': 'append',
            'keywords': 'harbor, café; editorial, café',
            'apply_attribution': True,
            'creator': 'Jane Editorial',
            'copyright_notice': '© 2026 Jane Editorial',
            'usage_rights': 'First Print Rights',
        })
        res_cust = core.execute(concrete_custom, [ed_src])
        self.assertTrue(res_cust[0]['ok'], res_cust[0].get('error'))
        out_cust = self.base / 'Editorial' / 'Magazine' / 'editorial_src_editorial.jpg'
        self.assertEqual(Path(res_cust[0]['output']), out_cust)
        self.assertEqual(identify_info(out_cust), ('JPEG', 2400, 1500))
        m_cust = read_all_ed_meta(out_cust)
        # Updated fields
        self.assertEqual(m_cust.get('XMP-dc:Description'), 'Valletta café at dusk — autumn issue')
        self.assertEqual(m_cust.get('IPTC:Caption-Abstract'), 'Valletta café at dusk — autumn issue')
        # Preserved non-default XMP language alternative!
        self.assertEqual(m_cust.get('XMP-dc:Description-fr'), 'Port de La Valette')
        # Appended deduplicated keywords
        self.assertEqual(as_list(m_cust.get('XMP-dc:Subject')), ['malta', 'harbor', 'café', 'editorial'])
        self.assertEqual(as_list(m_cust.get('IPTC:Keywords')), ['malta', 'harbor', 'café', 'editorial'])
        # Attribution + preserved camera/date/GPS
        self.assertEqual(m_cust.get('IFD0:Artist'), 'Jane Editorial')
        self.assertEqual(m_cust.get('IFD0:Copyright'), '© 2026 Jane Editorial')
        self.assertEqual(m_cust.get('XMP-xmpRights:UsageTerms'), 'First Print Rights')
        self.assertEqual(m_cust.get('IFD0:Make'), 'Fujifilm')
        self.assertEqual(m_cust.get('IFD0:Model'), 'X-T5')
        self.assertEqual(m_cust.get('ExifIFD:DateTimeOriginal'), '2025:09:15 10:20:30')

        # 5. Explicit keyword Replace + custom dimension (never upscales small images).
        small_src = self.base / 'small_ed.jpg'
        make_rich_fixture(small_src, width=800, height=600)
        small_before = source_sig(small_src)
        concrete_rep = kp.resolve_recipe(recipe, {
            'project_name': 'ReplaceRun',
            'max_dimension': 'custom',
            'custom_max_dimension': 2000,
            'keyword_mode': 'replace',
            'keywords': 'architecture; Valletta, heritage',
        })
        res_rep = core.execute(concrete_rep, [small_src])
        self.assertTrue(res_rep[0]['ok'], res_rep[0].get('error'))
        out_rep = self.base / 'Editorial' / 'ReplaceRun' / 'small_ed_editorial.jpg'
        self.assertEqual(identify_info(out_rep), ('JPEG', 800, 600))  # Never upscaled
        m_rep = read_all_ed_meta(out_rep)
        self.assertEqual(as_list(m_rep.get('XMP-dc:Subject')), ['architecture', 'Valletta', 'heritage'])
        self.assertEqual(as_list(m_rep.get('IPTC:Keywords')), ['architecture', 'Valletta', 'heritage'])
        # Existing caption preserved when caption parameter left blank
        self.assertEqual(m_rep.get('XMP-dc:Description'), 'Sunset over the rocky coast')

        # 6. Empty Replace must block explicitly (never silently clear keywords).
        concrete_empty_rep = kp.resolve_recipe(recipe, {
            'project_name': 'EmptyReplace',
            'keyword_mode': 'replace',
            'keywords': '   ',
        })
        rows_empty = core.preview(concrete_empty_rep, [ed_src])
        self.assertTrue(rows_empty[0].problems)
        self.assertIn('Replace', rows_empty[0].problems[0])

        # 7. Standalone descriptive metadata recipe does NOT re-encode pixels (encode == False).
        no_reencode_recipe = {
            'schema': 3,
            'id': 'desc-copy-only',
            'name': 'Descriptive Metadata Only',
            'description': 'Apply caption and keywords without re-encoding.',
            'media': 'image',
            'steps': [
                {'op': 'metadata.set_description', 'value': 'Copy-only caption'},
                {'op': 'metadata.set_keywords', 'mode': 'append', 'keywords': 'copyonly'},
                {'op': 'file.rename_output', 'pattern': '{filename}_meta'},
            ],
            'destination': {'mode': 'subfolder', 'folder': 'MetaOnly'},
        }
        rows_copy = core.preview(no_reencode_recipe, [ed_src])
        self.assertFalse(rows_copy[0].problems, rows_copy[0].problems)
        state_copy = handler.plan(ed_src, no_reencode_recipe['steps'], 1)
        self.assertFalse(state_copy['encode'])
        res_copy = core.execute(no_reencode_recipe, [ed_src])
        self.assertTrue(res_copy[0]['ok'], res_copy[0].get('error'))
        m_copy = read_all_ed_meta(Path(res_copy[0]['output']))
        self.assertEqual(m_copy.get('XMP-dc:Description'), 'Copy-only caption')
        self.assertEqual(m_copy.get('XMP-dc:Description-fr'), 'Port de La Valette')
        self.assertEqual(as_list(m_copy.get('XMP-dc:Subject')), ['malta', 'harbor', 'copyonly'])

        # 8. Format safety: pixel-export format (BMP) blocks descriptive metadata writes cleanly.
        bmp_recipe = copy.deepcopy(no_reencode_recipe)
        bmp_recipe['steps'].insert(0, {'op': 'image.convert', 'format': 'bmp', 'quality': None})
        rows_bmp = core.preview(bmp_recipe, [ed_src])
        self.assertTrue(rows_bmp[0].problems)
        self.assertIn('BMP', rows_bmp[0].problems[0])

        # 9. Source 5-attribute integrity preserved on all inputs.
        self.assertEqual(source_sig(ed_src), before_sig)
        self.assertEqual(source_sig(small_src), small_before)

    def test_09_create_client_proofs_optional_watermarks_and_safety(self):
        from PySide6.QtWidgets import QApplication
        from kim_recipe_param_ui import ParameterFormWidget, WatermarkImageChooser

        recipe = core.lookup_recipe('create-client-proofs')

        # 1. Parameter security: text param cannot bind to image.overlay.logo;
        #    watermark_image cannot store hardcoded default or accept relative path.
        bad_text_logo = copy.deepcopy(recipe)
        for p in bad_text_logo['parameters']:
            if p['id'] == 'watermark_image':
                p['type'] = 'text'
        with self.assertRaises(core.RecipeError):
            kp.validate_authored(bad_text_logo)

        bad_default_logo = copy.deepcopy(recipe)
        for p in bad_default_logo['parameters']:
            if p['id'] == 'watermark_image':
                p['default'] = '/tmp/hardcoded.png'
        with self.assertRaises(core.RecipeError):
            kp.validate_authored(bad_default_logo)

        with self.assertRaises(core.RecipeError):
            kp.resolve_recipe(recipe, {
                'add_watermark': True,
                'watermark_type': 'image',
                'watermark_image': 'relative/logo.png',
            })

        with self.assertRaises(core.RecipeError):
            kp.resolve_recipe(recipe, {
                'add_watermark': True,
                'watermark_type': 'image',
                'watermark_image': '',
            })

        # 2. Conditional control visibility in ParameterFormWidget.
        app = QApplication.instance() or QApplication([])
        form = ParameterFormWidget()
        self.addCleanup(form.deleteLater)
        form.set_recipe(recipe)
        form.show()
        form.set_advanced_expanded(True, user=True)
        app.processEvents()

        self.assertFalse(form.row_visible('watermark_type'))
        self.assertFalse(form.row_visible('watermark_text'))
        self.assertFalse(form.row_visible('watermark_image'))
        self.assertFalse(form.row_visible('watermark_position'))
        self.assertFalse(form.row_visible('watermark_opacity'))
        self.assertFalse(form.row_visible('watermark_size'))

        # Enable watermark -> text mode defaults visible, image hidden.
        form.field_widget('add_watermark').setChecked(True)
        app.processEvents()
        self.assertTrue(form.row_visible('watermark_type'))
        self.assertTrue(form.row_visible('watermark_text'))
        self.assertFalse(form.row_visible('watermark_image'))
        self.assertTrue(form.row_visible('watermark_position'))
        self.assertTrue(form.row_visible('watermark_opacity'))
        self.assertTrue(form.row_visible('watermark_size'))
        self.assertFalse(form.has_errors())

        # Switch to image mode -> WatermarkImageChooser (read-only) visible, text hidden, invalid until chosen.
        wt = form.field_widget('watermark_type')
        wt.setCurrentIndex(wt.findData('image'))
        app.processEvents()
        self.assertFalse(form.row_visible('watermark_text'))
        self.assertTrue(form.row_visible('watermark_image'))
        chooser = form.field_widget('watermark_image')
        self.assertIsInstance(chooser, WatermarkImageChooser)
        self.assertTrue(chooser.display.isReadOnly())
        self.assertTrue(form.has_errors())

        # 3. Create synthetic transparent PNG watermark asset and record 5-attribute signature.
        logo = self.base / 'studio_logo.png'
        subprocess.run(
            ['magick', '-size', '200x100', 'xc:none',
             '-fill', 'rgba(255,255,255,0.9)', '-draw', 'roundrectangle 10,10 190,90 12,12',
             '-fill', 'rgba(220,30,30,0.95)', '-draw', 'circle 100,50 100,20',
             'PNG32:' + str(logo)],
            check=True, timeout=20, capture_output=True,
        )
        age_file(logo)
        logo_before = source_sig(logo)

        # Choosing logo makes form valid.
        chooser.set_path(str(logo))
        app.processEvents()
        self.assertFalse(form.has_errors())

        # 4. Compare unwatermarked default vs text-watermarked vs image-watermarked outputs.
        def pixel_digest(path: Path) -> str:
            raw = subprocess.check_output(['magick', str(path), 'RGB:-'], timeout=20)
            return hashlib.sha256(raw).hexdigest()

        c_plain = kp.resolve_recipe(recipe, {'project_name': 'Plain'})
        r_plain = core.execute(c_plain, [self.large_jpg])
        self.assertTrue(r_plain[0]['ok'], r_plain[0].get('error'))
        out_plain = self.base / 'Proofs' / 'Plain' / 'harbor_large_proof.jpg'
        self.assertEqual(Path(r_plain[0]['output']), out_plain)
        plain_pixels = pixel_digest(out_plain)

        # Enabled text watermark
        c_text = kp.resolve_recipe(recipe, {
            'project_name': 'TextWM',
            'add_watermark': True,
            'watermark_type': 'text',
            'watermark_text': 'CLIENT PROOF',
            'watermark_position': 'center',
            'watermark_opacity': 75,
            'watermark_size': 10.0,
        })
        r_text = core.execute(c_text, [self.large_jpg])
        self.assertTrue(r_text[0]['ok'], r_text[0].get('error'))
        out_text = self.base / 'Proofs' / 'TextWM' / 'harbor_large_proof.jpg'
        self.assertEqual(Path(r_text[0]['output']), out_text)
        self.assertEqual(identify_info(out_text), ('JPEG', 1600, 1067))
        self.assertNotEqual(pixel_digest(out_text), plain_pixels)
        m_text = read_meta(out_text)
        self.assertIsNone(m_text.get('GPSLatitude'))
        self.assertEqual(m_text.get('Artist'), 'Original Photographer')

        # Enabled image watermark
        c_img = kp.resolve_recipe(recipe, {
            'project_name': 'LogoWM',
            'add_watermark': True,
            'watermark_type': 'image',
            'watermark_image': str(logo),
            'watermark_position': 'bottom_right',
            'watermark_opacity': 80,
            'watermark_size': 20.0,
        })
        r_img = core.execute(c_img, [self.large_jpg])
        self.assertTrue(r_img[0]['ok'], r_img[0].get('error'))
        out_img = self.base / 'Proofs' / 'LogoWM' / 'harbor_large_proof.jpg'
        self.assertEqual(Path(r_img[0]['output']), out_img)
        self.assertEqual(identify_info(out_img), ('JPEG', 1600, 1067))
        self.assertNotEqual(pixel_digest(out_img), plain_pixels)
        self.assertNotEqual(pixel_digest(out_img), pixel_digest(out_text))

        # 5. Invalid / missing / symlink watermark assets block cleanly during Review Changes.
        c_missing = kp.resolve_recipe(recipe, {
            'project_name': 'MissingWM',
            'add_watermark': True,
            'watermark_type': 'image',
            'watermark_image': str(self.base / 'does_not_exist.png'),
        })
        rows_missing = core.preview(c_missing, [self.large_jpg])
        self.assertTrue(rows_missing[0].problems)
        self.assertIn('Missing or unreadable watermark image', rows_missing[0].problems[0])

        sym_logo = self.base / 'logo_symlink.png'
        sym_logo.symlink_to(logo)
        c_sym = kp.resolve_recipe(recipe, {
            'project_name': 'SymWM',
            'add_watermark': True,
            'watermark_type': 'image',
            'watermark_image': str(sym_logo),
        })
        rows_sym = core.preview(c_sym, [self.large_jpg])
        self.assertTrue(rows_sym[0].problems)
        self.assertIn('symlink', rows_sym[0].problems[0].lower())

        corrupt_logo = self.base / 'corrupt_logo.png'
        corrupt_logo.write_bytes(b'not a real png image')
        c_corrupt = kp.resolve_recipe(recipe, {
            'project_name': 'CorruptWM',
            'add_watermark': True,
            'watermark_type': 'image',
            'watermark_image': str(corrupt_logo),
        })
        rows_corrupt = core.preview(c_corrupt, [self.large_jpg])
        self.assertTrue(rows_corrupt[0].problems)

        # Verify all 5 integrity attributes on BOTH original image AND watermark asset before mut_logo copy.
        self._assert_originals_intact()
        self.assertEqual(source_sig(logo), logo_before)

        # 6. Watermark asset changed after Review Changes approval -> fails closed, no output published.
        mut_logo = self.base / 'mutable_logo.png'
        subprocess.run(
            ['magick', '-size', '200x100', 'xc:blue', 'PNG32:' + str(mut_logo)],
            check=True, timeout=20, capture_output=True,
        )
        age_file(mut_logo)
        c_mut = kp.resolve_recipe(recipe, {
            'project_name': 'MutatedWM',
            'add_watermark': True,
            'watermark_type': 'image',
            'watermark_image': str(mut_logo),
        })
        rows_mut = core.preview(c_mut, [self.large_jpg])
        self.assertFalse(rows_mut[0].problems, rows_mut[0].problems)
        approved_plan = core.approve_rows(c_mut, [self.large_jpg], rows_mut)
        # Mutate logo asset after approval
        subprocess.run(
            ['magick', '-size', '200x100', 'xc:red', 'PNG32:' + str(mut_logo)],
            check=True, timeout=20, capture_output=True,
        )
        res_mut = core.execute(c_mut, [self.large_jpg], approved_plan=approved_plan)
        self.assertFalse(res_mut[0]['ok'])
        self.assertIn('Watermark image changed since planning', res_mut[0]['error'])
        self.assertFalse((self.base / 'Proofs' / 'MutatedWM' / 'harbor_large_proof.jpg').exists())

        # 7. Verify all 5 integrity attributes on BOTH original image AND watermark asset.
        self._assert_originals_intact()
        self.assertEqual(source_sig(logo), logo_before)


if __name__ == '__main__':
    unittest.main()
