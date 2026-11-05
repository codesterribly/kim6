"""Step 2 work counts and safety decisions, using disposable generated images.

Run only this module: python3 -B tests/run.py --pattern test_processing_reuse.py
Counts describe tool requests / presentation work, not elapsed-time speedups.
"""
import collections
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_recipes as base
import kim_recipe_core as core
import kim_recipe_image as image
import kim_image_ops as ops
import kim_location as location
import kim_preview as approval
from kim_psd_source import inspection_context, srgb, PSDError


class GeneratedImages(unittest.TestCase):
    def setUp(self):
        if not shutil.which('magick') or not shutil.which('exiftool'):
            self.skipTest('Real image tools required')
        self.tmp = tempfile.TemporaryDirectory(prefix='kim6-step2-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source.jpg'
        self.command('magick', '-size', '40x30', 'xc:red', '-profile', srgb(), self.source)

    def command(self, *args):
        return subprocess.run(list(map(str, args)), check=True, capture_output=True, timeout=30).stdout

    def location_plan(self, policy='create'):
        target = self.source if policy == 'overwrite' else self.root/'exact name.jpg'
        plan = location.build_plan('apply', policy, [str(self.source)],
                                   {'latitude': '40', 'longitude': '-70'}, seeds=[str(target)])
        self.assertEqual(plan['entries'][0]['status'], 'change')
        path = self.root/'approved.json'
        path.write_text(json.dumps(plan))
        return plan, path, target

    def invoke(self, module, command, path, *args):
        with patch.object(sys, 'argv', ['helper', command, str(path), *map(str, args)]), \
                contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO())):
            return module.main()

    def test_recipe_cold_tool_counts_and_distinct_metadata(self):
        self.command('exiftool', '-overwrite_original', '-EXIF:Artist=EXIF artist',
                     '-XMP-dc:Creator=XMP creator', '-IPTC:By-line=IPTC author',
                     '-EXIF:DateTimeOriginal=2020:01:02 03:04:05', '-SubSecTimeOriginal=00123',
                     '-OffsetTimeOriginal=+05:30', '-XMP-exif:DateTimeOriginal=2021:02:03 04:05:06.123-02:00',
                     '-XMP-iptcExt:AISystemUsed=Test system', '-GPSLatitude=40', '-GPSLongitude=-70', self.source)
        counts = collections.Counter()
        run = image.run
        def counted(args, *a, **kw):
            counts[args[0]] += 1
            return run(args, *a, **kw)
        with patch.object(image, 'run', counted):
            row = core.preview(base.recipe(), [self.source])[0]
        self.assertFalse(row.problems, row.problems)
        self.assertEqual(counts, {'exiftool': 3, 'magick': 2})
        details = '\n'.join(row.metadata)
        for expected in ('EXIF artist', 'XMP creator', 'IPTC author', 'Test system',
                         'GPS: present', 'ICC: preserved sRGB', 'EXIF DateTimeOriginal'):
            self.assertIn(expected, details)
        info = image.inspect(self.source)[0]
        self.assertEqual(info['SubSecTimeOriginal'], '00123')
        self.assertEqual(info['OffsetTimeOriginal'], '+05:30')
        self.assertEqual(info['_date_fields']['EXIF:DateTimeOriginal'], '2020:01:02 03:04:05')
        self.assertEqual(info['_date_fields']['XMP-exif:DateTimeOriginal'], '2021:02:03 04:05:06.123-02:00')

    def test_shared_logo_counts_replacement_generation_and_private_snapshot(self):
        logo = self.root/'logo.png'
        self.command('magick', '-size', '8x6', 'xc:blue', '-profile', srgb(), logo)
        step = dict(op='image.overlay', **ops.OVERLAY_DEFAULTS)
        step.update(kind='image', logo=str(logo), size=20)
        calls = collections.Counter(); run = image.run
        def counted(args, *a, **kw):
            calls[args[0]] += 1
            return run(args, *a, **kw)
        with patch.object(image, 'run', counted), ops.logo_inspections():
            records = [ops.overlay_plan(self.source, 40+i, 30+i, step) for i in range(10)]
            self.assertEqual(calls, {'exiftool': 2, 'magick': 3})
            self.assertEqual(records[-1]['width'], 49)
            self.assertTrue(records[0]['warnings'])  # Opaque logo notice retained.
            old = records[0]
            self.command('magick', '-size', '10x5', 'xc:green', logo)
            fresh = ops.overlay_plan(self.source, 40, 30, step)
            self.assertNotEqual(old['identity'], fresh['identity'])
            with self.assertRaisesRegex(core.RecipeError, 'changed since planning'):
                ops.overlay_arguments(self.source, {'overlays': [old], 'profile_srgb': True}, self.root)
        with patch.object(image, 'run', counted), ops.logo_inspections():
            ops.overlay_plan(self.source, 40, 30, step)
        self.assertEqual(calls, {'exiftool': 6, 'magick': 9})
        logo.unlink(); logo.symlink_to(self.source)
        with self.assertRaisesRegex(core.RecipeError, 'symlink'):
            ops.inspect_logo(logo)

    def test_logo_policy_and_cancellation_invalidate_reuse(self):
        logo = self.root/'logo.png'; policy = self.root/'policy.icc'
        self.command('magick', '-size', '8x6', 'xc:blue', logo)
        shutil.copyfile(srgb(), policy)
        with patch.object(image, 'srgb_profile', return_value=str(policy)), ops.logo_inspections(), patch.object(image, 'run', wraps=image.run) as run:
            ops.inspect_logo(logo)
            initial = run.call_count
            with inspection_context(cancelled=lambda: True), self.assertRaises(PSDError):
                ops.inspect_logo(logo)
            policy.write_bytes(policy.read_bytes())
            ops.inspect_logo(logo)
            self.assertEqual(run.call_count, initial * 2)

    def test_gps_combined_phase_counts_and_exact_destination(self):
        plan, path, target = self.location_plan()
        stage = self.root/'stage.jpg'; counts = collections.Counter()
        read, digest = Path.read_text, location.approval_digest
        def read_count(p, *a, **kw):
            if p == path: counts['loads'] += 1
            return read(p, *a, **kw)
        def digest_count(*a):
            counts['digests'] += 1
            return digest(*a)
        original = self.source.read_bytes()
        with patch.object(Path, 'read_text', read_count), patch.object(location, 'approval_digest', digest_count):
            self.invoke(approval, 'entry', path, self.source)
            self.invoke(location, 'stage', path, self.source, stage)
            self.invoke(approval, 'guard', path, target)
            self.invoke(approval, 'guard', path, target)
        self.assertEqual(counts, {'loads': 4, 'digests': 4})
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(target.exists())
        self.assertEqual(plan['entries'][0]['target'], str(target))
        location.verify_output(plan, str(self.source), str(stage))
        wrong = self.root/'wrong.jpg'; shutil.copyfile(self.source, wrong)
        with self.assertRaisesRegex(ValueError, 'differs'): location.verify_output(plan, str(self.source), str(wrong))

    def test_gps_rejects_changed_plan_source_dependency_and_destination(self):
        for change in ('plan', 'source', 'dependency', 'destination', 'hardlink', 'symlink'):
            with self.subTest(change=change):
                # Each scenario gets an independent current approval.
                plan, path, target = self.location_plan()
                dep = self.root/'track.gpx'; dep.write_text('track before')
                if change == 'dependency':
                    plan['dependencies'] = [{'path': str(dep), 'identity': approval.identity(dep)}]
                    plan['approval_digest'] = location.approval_digest(plan)
                    path.write_text(json.dumps(plan)); dep.write_text('track after')
                elif change == 'plan':
                    plan['entries'][0]['args'][-1] = '-GPSLongitude=1'
                    path.write_text(json.dumps(plan))
                elif change == 'source':
                    stamp = self.source.stat().st_mtime_ns
                    self.command('exiftool', '-overwrite_original', '-Artist=changed', self.source)
                    os.utime(self.source, ns=(stamp, stamp))
                elif change == 'destination': target.write_text('occupied')
                elif change == 'hardlink': os.link(self.source, target)
                elif change == 'symlink': target.symlink_to(self.source)
                with self.assertRaises(ValueError): self.invoke(approval, 'entry', path, self.source)
                if target.is_symlink() or target.exists(): target.unlink()
        # Authorized overwrite still verifies the selected source as destination.
        plan, path, target = self.location_plan('overwrite')
        self.invoke(location, 'stage', path, self.source, self.root/'overwrite-stage.jpg')
        self.invoke(approval, 'guard', path, target)

    def test_missing_gps_plan_cannot_reuse_previous_skip(self):
        shell = (base.ROOT/'src/bin/kim_all').read_text()
        begin = re.search(r'^progress_begin_item\(\) \{\n.*?^\}', shell, re.M | re.S)[0]
        script = begin + '''
preview_active() { [ -f "$KIMDIR/preview.approved" ]; }
progress_cancelled() { exit 90; }
location_plan="$KIMDIR/preview.approved"
PREVIEW_ITEM_STATE=skip
progress_begin_item ref source
'''
        result = subprocess.run(['bash', '-c', script], capture_output=True,
                                env=dict(os.environ, KIMDIR=str(self.root)), timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b'')

    def test_gps_live_checks_run_again_during_combined_stage(self):
        plan, path, target = self.location_plan()
        process = location.location_process
        def replace_destination(*a, **kw):
            result = process(*a, **kw)
            target.write_text('occupied during staging')
            return result
        with patch.object(location, 'location_process', replace_destination), self.assertRaisesRegex(ValueError, 'Destination changed'):
            self.invoke(location, 'stage', path, self.source, self.root/'stage.jpg')

    def test_batched_metadata_publication_preserves_source_pixels_profile_and_collision(self):
        from support import Workspace
        with contextlib.closing(Workspace()) as workspace:
            workspace.subprocess_timeout = 40
            source = workspace.jpeg('input/photo.jpg')
            workspace.use_real_metadata_tools(); workspace.use_real_mv()
            (workspace.bin/'python3').symlink_to(sys.executable)
            workspace.env['KIM_POLICY'] = 'create'
            # Exercise the existing native encoded-data verifier as well.
            workspace.env['KIM_JPEG_WEBP_ENGINE'] = 'native'
            self.command('exiftool', '-overwrite_original', '-GPSLatitude=40', '-GPSLongitude=-70',
                         '-Artist=Preserved author', '-ICC_Profile<='+srgb(), source)
            occupied = source.with_name('photo_gps.jpg'); occupied.write_bytes(b'occupied')
            before = workspace.observe(source)
            result = workspace.dispatch('stripmeta', '--mode', 'gps', '--', str(source))
            self.assertEqual(result.returncode, 0, result.stderr)
            queries = [call for call in result.calls if call['tool'] == 'exiftool' and '-G0:1:4' in call['argv']]
            self.assertEqual(len(queries), 1)
            self.assertEqual(workspace.observe(source), before)
            self.assertEqual(occupied.read_bytes(), b'occupied')
            output = source.with_name('photo_gps-1.jpg')
            self.assertTrue(output.is_file())
            self.assertEqual(self.command('exiftool', '-s3', '-GPS:all', output), b'')
            self.assertEqual(self.command('exiftool', '-s3', '-Artist', output).strip(), b'Preserved author')
            self.assertEqual(self.command('exiftool', '-b', '-ICC_Profile', output),
                             self.command('exiftool', '-b', '-ICC_Profile', source))
            self.assertEqual(self.command('magick', source, '-format', '%#', 'info:'),
                             self.command('magick', output, '-format', '%#', 'info:'))
            self.assertFalse(list(workspace.root.rglob('.kim6-stage.*')))

    def test_removal_union_equivalence_and_actual_exiftool_counts(self):
        shell = (base.ROOT/'src/bin/kim_all').read_text()
        def function(name):
            return re.search(r'^'+name+r'\(\) \{\n.*?^\}', shell, re.M | re.S)[0]
        helpers = function('metadata_query')+'\n'+function('metadata_verify_expected')
        wrapper = self.root/'bin'; wrapper.mkdir(); log = self.root/'calls'
        executable = wrapper/'exiftool'
        executable.write_text('#!/bin/sh\nprintf x >> "$COUNT_LOG"\nexec '+shlex.quote(shutil.which('exiftool'))+' "$@"\n')
        executable.chmod(0o700)
        tags = ['-GPS:all', '-XMP-exif:GPS*', '-XMP:GPS*'] + [
            '-XMP-iptcExt:'+place+field for place in ('LocationShown', 'LocationCreated', 'RatingRegion')
            for field in ('GPSLatitude', 'GPSLongitude', 'GPSAltitude', 'GPSAltitudeRef')]
        pairs = [tag+'\034' for tag in tags]
        def check(batched, expected=pairs):
            log.write_text('')
            script = helpers+'\nexpected=('+ ' '.join(map(shlex.quote, expected))+')\n'
            if batched: script += 'metadata_verify_expected "$1" expected\n'
            else:
                script += '''rc=0
for pair in "${expected[@]}"; do
 tag="${pair%%$'\\034'*}"; value="${pair#*$'\\034'}"
 actual="$(metadata_query "$1" "$tag")" || rc=1
 [ "$actual" = "$value" ] || rc=1
done
exit "$rc"
'''
            result = subprocess.run(['bash', '-c', script, 'check', str(self.source)], capture_output=True,
                                    env=dict(os.environ, KIMDIR=str(self.root), COUNT_LOG=str(log),
                                             PATH=str(wrapper)+os.pathsep+os.environ['PATH']), timeout=30)
            return result.returncode, len(log.read_text())
        self.assertEqual(check(False), (0, 15))
        self.assertEqual(check(True), (0, 1))
        self.command('exiftool', '-overwrite_original', '-XMP-iptcExt:LocationShownCity=Retained city', self.source)
        self.assertEqual(check(False), (0, 15))
        self.assertEqual(check(True), (0, 1))
        for tag in ('-GPSLatitude=40', '-XMP-exif:GPSLatitude=41', '-XMP-iptcExt:LocationShownGPSLatitude=42'):
            self.command('exiftool', '-overwrite_original', tag, self.source)
            self.assertEqual(check(False), (1, 15))
            self.assertEqual(check(True), (1, 1))
        # Scalar and list print conversion stays equivalent, including empty values.
        self.command('exiftool', '-overwrite_original', '-XMP-dc:Creator=One', '-SubSecTimeOriginal=', self.source)
        expected = ['-XMP-dc:Creator\034One', '-SubSecTimeOriginal\034']
        self.assertEqual(check(False, expected), (0, 2))
        self.assertEqual(check(True, expected), (0, 2))

    def test_removal_rejects_malformed_duplicate_and_structured_responses(self):
        shell = (base.ROOT/'src/bin/kim_all').read_text()
        helper = re.search(r'^metadata_verify_expected\(\) \{\n.*?^\}', shell, re.M | re.S)[0]
        responses = [
            ('[]', 1), ('{}', 1), ('not JSON', 1),
            ('[{"SourceFile":"fixture","GPS:Latitude":0}]', 1),
            ('[{"SourceFile":"fixture","XMP:Location":{"GPSLatitude":40}}]', 1),
            ('[{"SourceFile":"fixture","GPS:Latitude":[]}]', 1),
            ('[{"SourceFile":"fixture","GPS:Latitude":"","GPS:Latitude":""}]', 1),
            ('[{"SourceFile":"fixture","Error":"inspection failed"}]', 1),
            ('[{"SourceFile":"fixture"}]', 0),
            ('[{"SourceFile":"fixture","GPS:Latitude":""}]', 0),
        ]
        for response, expected in responses:
            with self.subTest(response=response):
                script = helper + '\nexiftool() { printf \'%s\\n\' ' + shlex.quote(response) + '; }\n'
                script += "expected=('-GPS:all'" + "$'\\034'" + ")\nmetadata_verify_expected fixture expected\n"
                result = subprocess.run(['bash', '-c', script], capture_output=True,
                                        env=dict(os.environ, KIMDIR=str(self.root)), timeout=5)
                self.assertEqual(result.returncode, expected)


class PresentationReuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_controlled_batches_counts_gating_stale_results_and_selected_properties(self):
        import kim_recipe_run as gui
        class Rows(dict):
            visits = 0
            def values(self):
                for row in super().values(): self.visits += 1; yield row
            def items(self):
                for row in super().items(): self.visits += 1; yield row
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}):
            for n in (10, 100, 500):
                with self.subTest(rows=n), patch.object(gui.RunRecipeDialog, 'start_preflight'):
                    w = gui.RunRecipeDialog(base.recipe(), ['/synthetic/source.jpg']*n)
                    w.invalidate_preflight(); w.rows = Rows()
                    sender = SimpleNamespace(generation=w.generation)
                    with patch.object(gui.RunRecipeDialog, 'sender', return_value=sender), \
                            patch.object(gui, 'property_fields', wraps=gui.property_fields) as fields:
                        for i in range(n):
                            row = core.PreviewRow('/synthetic/source.jpg', identity=(1, 1), warnings=['Unprofiled RGB/grayscale synthetic'])
                            w.inspected(row, i)
                            self.assertFalse(w.run_button.isEnabled())
                        self.assertEqual(w.rows.visits, 0)
                        self.assertEqual(fields.call_count, 1)
                        w.reviewed_generation = w.generation; w.update_summary()
                        self.assertTrue(w.run_button.isEnabled())
                        self.assertIn(f'{n} ready; 0 problems', w.summary.text())
                        w.inspected(core.PreviewRow('bad', problems=['first issue']), 1)
                        self.assertFalse(w.run_button.isEnabled()); self.assertIn('first issue', w.diagnostics.toPlainText())
                        w.inspected(core.PreviewRow('cancelled', properties={'_cancelled': True}), 1)
                        self.assertFalse(w.run_button.isEnabled()); self.assertNotIn('first issue', w.diagnostics.toPlainText())
                        sender.generation -= 1
                        w.inspected(core.PreviewRow('stale', problems=['stale issue']), 0)
                        self.assertEqual(w.rows[0].source, '/synthetic/source.jpg')
                    w.invalidate_preflight()
                    self.assertEqual(w.ready_count, 0); self.assertFalse(w.run_button.isEnabled())
                    w.deleteLater(); self.app.processEvents()


if __name__ == '__main__': unittest.main()
