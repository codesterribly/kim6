"""Real GPS source access on fresh ext4 fixtures, without timestamp restoration."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
from kim_location import read_many, summarize, build_plan
from kim_preview import identity, save_plan
from metadata_integrity import sha256_noatime


def signature(path):
    info = path.stat()
    return sha256_noatime(path), info.st_size, info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns


def protected_copy(source, target):
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOATIME | os.O_NOFOLLOW), 'rb') as stream:
        with target.open('xb') as output:
            shutil.copyfileobj(stream, output)


class GPSSourceIOTests(unittest.TestCase):
    def setUp(self):
        if not all(shutil.which(tool) for tool in ('exiftool', 'magick', 'identify')):
            self.skipTest('ExifTool and ImageMagick required')
        self.temp = tempfile.TemporaryDirectory(prefix='.kim6-gps-test-', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.control = self.folder / 'control'
        self.control.mkdir()
        dispatcher = (ROOT / 'src/bin/kim_all').read_text()
        marker = '\nmain "$@"\n'
        self.assertEqual(1, dispatcher.count(marker))
        self.bash = self.control / 'dispatcher-functions'
        self.bash.write_text(dispatcher.replace(marker, '\n'))

    def fixture(self, name='雪 photo.jpg', *, gps=True):
        prepared = self.control / ('prepared' + Path(name).suffix)
        subprocess.run(['magick', '-size', '40x20', 'gradient:red-blue',
                        '-profile', '/usr/share/color/icc/colord/AdobeRGB1998.icc', str(prepared)],
                       check=True, capture_output=True)
        args = ['exiftool', '-overwrite_original', '-Artist=GPS test',
                '-XMP-dc:Description=Caption retained', '-XMP-dc:Title-fr=Titre',
                '-DateTimeOriginal=2026:11:15 12:00:00']
        if gps:
            args += ['-GPSLatitude=48.5', '-GPSLongitude=2.25', '-GPSLatitudeRef=N',
                     '-GPSLongitudeRef=E', '-GPSAltitude=100', '-GPSAltitudeRef=0']
        subprocess.run([*args, str(prepared)], check=True, capture_output=True)
        # Preload an exact byte-copy's metadata so a prior ordinary read cannot
        # mask the independently tested stage or publisher's first source read.
        data = read_many([str(prepared)])[str(prepared)]
        self.assertNotIn('error', data, data)
        source = self.folder / name
        source.parent.mkdir(parents=True, exist_ok=True)
        protected_copy(prepared, source)
        self.assertLess(source.stat().st_atime_ns, source.stat().st_mtime_ns)
        return source, {'raw': data['raw'], 'identity': identity(source), 'complete': True}

    def plan(self, source, data, kind='apply', **config):
        config = config or dict(method='manual', latitude='40.25', longitude='-71.5', altitude='50')
        target = self.folder / ('approved-result' + source.suffix)
        plan = build_plan(kind, 'create', [str(source)], config, [str(target)], cache={str(source): data})
        self.assertEqual('change', plan['entries'][0]['status'], plan['entries'][0])
        path = self.control / 'preview.approved'
        save_plan(path, plan)
        return path, target, plan

    def shell(self, body, *args):
        script = 'source "$1"\nDISPATCHER_DIR="$2"\nshift 2\n' + body
        return subprocess.run(['bash', '-c', script, 'bash', str(self.bash), str(ROOT/'src/bin'), *map(str,args)],
                              capture_output=True, text=True, timeout=30)

    def publish(self, source, output, *, mode='create', cancel=False):
        return self.shell('''
KIMDIR="$1"
cmd=location-apply
location_plan="$KIMDIR/preview.approved"
cancel_requested="$5"
progress_cancelled() { [ "$cancel_requested" = true ]; }
expected=()
status=0
metadata_publish_one "$2" "$3" "$4" '' expected || status=$?
cleanup_stages
exit "$status"
''', self.control, source, output, mode, 'true' if cancel else 'false')

    def test_inspection_preserves_exact_signature(self):
        source, _ = self.fixture()
        before = signature(source)
        result = read_many([str(source)])[str(source)]
        self.assertNotIn('error', result, result)
        self.assertEqual([48.5, 2.25], summarize(result['raw'])['position'])
        self.assertEqual(before, signature(source))

    def test_report_is_selective_and_publication_planning_upgrades_its_cache(self):
        source, data = self.fixture()
        before = signature(source)
        cache = {}
        report = build_plan('report', 'create', [str(source)], {}, cache=cache)
        self.assertEqual(summarize(data['raw']), report['entries'][0]['location_before'])
        self.assertFalse(any(key.endswith(':Artist') for key in cache[str(source)]['raw']))
        self.assertFalse(cache[str(source)]['complete'])
        plan = build_plan('apply', 'create', [str(source)],
                          dict(method='manual', latitude='40.25', longitude='-71.5'),
                          [str(self.folder / 'new.jpg')], cache=cache)
        self.assertTrue(cache[str(source)]['complete'])
        self.assertTrue(any(key.endswith(':Artist') for key in cache[str(source)]['raw']))
        self.assertEqual('change', plan['entries'][0]['status'])
        self.assertEqual(before, signature(source))

    def test_stage_preserves_exact_signature_and_expected_gps(self):
        source, data = self.fixture()
        plan_path, output, _ = self.plan(source, data)
        output = self.control / ('staged' + source.suffix)
        before = signature(source)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'src/bin/kim_location.py'),
                                 'stage', str(plan_path), str(source), str(output)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, signature(source))
        info = read_many([str(output)])[str(output)]
        self.assertEqual([40.25, -71.5], summarize(info['raw'])['position'])

    def test_gps_publisher_preserves_exact_source_and_approved_destination(self):
        source, data = self.fixture()
        sidecar = source.with_suffix('.xmp')
        sidecar.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
        sidecar_before = signature(sidecar)
        plan_path, output, _ = self.plan(source, data)
        before = signature(source)
        result = self.publish(source, output)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(output.is_file())
        self.assertEqual(before, signature(source))
        self.assertEqual(sidecar_before, signature(sidecar))
        self.assertFalse(list(self.folder.glob('.kim6-stage.*')))

    def test_supported_staging_formats_preserve_source_and_embedded_metadata(self):
        for suffix in ('.png', '.webp', '.avif'):
            with self.subTest(format=suffix):
                source, data = self.fixture('source' + suffix)
                plan_path, _output, _plan = self.plan(source, data)
                stage = self.control / ('stage' + suffix)
                before = signature(source)
                result = subprocess.run([sys.executable, '-B', str(ROOT/'src/bin/kim_location.py'),
                                         'stage', str(plan_path), str(source), str(stage)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(before, signature(source))
                published = self.publish(source, self.folder / ('approved-result' + suffix))
                self.assertEqual(0, published.returncode, published.stderr)
                self.assertEqual(before, signature(source))

    def test_precision_publication_uses_approved_grid_position(self):
        source, data = self.fixture()
        _plan_path, output, plan = self.plan(source, data, 'reduce', grid=1000)
        expected = plan['entries'][0]['approved_location']['position']
        self.assertNotEqual([48.5, 2.25], expected)
        before = signature(source)
        result = self.publish(source, output)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, signature(source))
        result = summarize(read_many([str(output)])[str(output)]['raw'])['position']
        for actual, approved in zip(result, expected):
            self.assertAlmostEqual(approved, actual, places=8)

    def test_cancel_and_occupied_destination_never_publish(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                source, data = self.fixture('cancel' + str(cancel) + '.jpg')
                _plan_path, output, _plan = self.plan(source, data)
                if not cancel:
                    output.write_bytes(b'Existing destination')
                before = signature(source)
                result = self.publish(source, output, cancel=cancel)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(before, signature(source))
                if cancel:
                    self.assertFalse(output.exists())
                else:
                    self.assertEqual(b'Existing destination', output.read_bytes())
                    output.unlink()
                self.assertFalse(list(self.folder.rglob('.kim6-stage.*')))
                self.assertFalse(list(self.control.glob('location-source-*')))

    def test_repeated_and_absent_gps_inspection_is_safe(self):
        source, _data = self.fixture(gps=False)
        before = signature(source)
        for _ in range(3):
            records = read_many([str(source)])
            self.assertNotIn('error', records[str(source)])
            self.assertIsNone(summarize(records[str(source)]['raw'])['position'])
        self.assertEqual(before, signature(source))

    def test_noatime_permission_failure_does_not_fall_back(self):
        source = Path('/etc/hosts')
        if source.stat().st_uid in (os.geteuid(),) or os.geteuid() == 0:
            self.skipTest('Requires readable input owned by another user')
        before = source.stat()
        result = read_many([str(source)])[str(source)]
        self.assertIn('without changing its access time', result['error'])
        self.assertEqual(before.st_atime_ns, source.stat().st_atime_ns)

    def test_tiff_preexisting_offset_rejection_preserves_source(self):
        source, data = self.fixture('source.tiff')
        plan_path, _target, _plan = self.plan(source, data)
        stage = self.control / 'stage.tiff'
        before = signature(source)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'src/bin/kim_location.py'),
                                 'stage', str(plan_path), str(source), str(stage)],
                                capture_output=True, text=True, timeout=30)
        # Confirmed against the pre-task implementation: TIFF StripOffsets move
        # under ExifTool and the existing metadata guard rejects that change.
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Unrelated descriptive, date, orientation or rights metadata changed', result.stderr)
        self.assertFalse(stage.exists())
        self.assertEqual(before, signature(source))

    def test_source_change_before_stage_is_rejected_without_further_mutation(self):
        source, data = self.fixture()
        plan_path, output, _plan = self.plan(source, data)
        with source.open('ab') as stream:
            stream.write(b'External source change')
        changed = signature(source)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'src/bin/kim_location.py'),
                                 'stage', str(plan_path), str(source), str(output)],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(output.exists())
        self.assertEqual(changed, signature(source))

    def test_failed_stage_never_publishes_and_cleans_owned_snapshots(self):
        source, data = self.fixture()
        _plan_path, output, _plan = self.plan(source, data)
        tool = self.control / 'bin'
        tool.mkdir()
        broken = tool / 'exiftool'
        broken.write_text('#!/bin/sh\necho "fixture stage failure" >&2\nexit 1\n')
        broken.chmod(0o700)
        before = signature(source)
        with patch.dict(os.environ, PATH=str(tool) + os.pathsep + os.environ['PATH']):
            result = self.publish(source, output)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(output.exists())
        self.assertEqual(before, signature(source))
        self.assertFalse(list(self.folder.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.control.glob('location-source*')))

    def test_explicit_overwrite_policy_remains_available(self):
        source, data = self.fixture()
        plan = build_plan('apply', 'overwrite', [str(source)],
                          dict(method='manual', latitude='40.25', longitude='-71.5'),
                          [str(source)], cache={str(source): data})
        self.assertEqual('change', plan['entries'][0]['status'])
        save_plan(self.control/'preview.approved', plan)
        before = signature(source)
        result = self.publish(source, source, mode='overwrite')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual(before[0], signature(source)[0])
        self.assertEqual([40.25, -71.5], summarize(read_many([str(source)])[str(source)]['raw'])['position'])

    def test_reference_image_and_gpx_reads_preserve_their_signatures(self):
        reference, _reference_data = self.fixture('reference.jpg')
        source, data = self.fixture('destination.jpg', gps=False)
        before = {p: signature(p) for p in (reference, source)}
        plan = build_plan('apply', 'create', [str(source)],
                          dict(method='photo', reference=str(reference)),
                          [str(self.folder/'from-reference.jpg')], cache={str(source): data})
        self.assertEqual('change', plan['entries'][0]['status'])
        self.assertEqual([48.5, 2.25], plan['entries'][0]['approved_location']['position'])
        self.assertEqual(before, {p: signature(p) for p in before})
        track = self.folder/'track 雪.gpx'
        track.write_text('<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><trk><trkseg><trkpt lat="40" lon="-71"><time>2026-11-15T12:00:00Z</time></trkpt></trkseg></trk></gpx>')
        from kim_location import parse_gpx
        track_before = signature(track)
        self.assertEqual(1, parse_gpx(str(track))['count'])
        self.assertEqual(track_before, signature(track))
        plan = build_plan('gpx', 'create', [str(source)],
                          dict(gpx=str(track), timezone='UTC', seconds='0', gap='300', sync=[]),
                          [str(self.folder/'from-track.jpg')])
        self.assertEqual('change', plan['entries'][0]['status'], plan['entries'][0])
        self.assertEqual([40.0, -71.0], plan['entries'][0]['approved_location']['position'])
        save_plan(self.control/'preview.approved', plan)
        output = Path(plan['entries'][0]['target'])
        published = self.publish(source, output)
        self.assertEqual(0, published.returncode, published.stderr)
        self.assertEqual(before, {p: signature(p) for p in before})
        self.assertEqual(track_before, signature(track))

    def test_actual_viewer_and_cancelled_review_preserve_image_and_sidecar(self):
        from PySide6.QtWidgets import QApplication
        from kim_location_dialog import LocationDialog
        app = QApplication.instance() or QApplication([])
        source, _data = self.fixture()
        sidecar = source.with_suffix('.xmp')
        sidecar.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
        before = {p: signature(p) for p in (source, sidecar)}
        config = self.control/'config'/'kim6'
        config.mkdir(parents=True)
        (config/'settings.conf').write_text('KIM_LOCATION_ONLINE_MAPS=no\nKIM_LOCATION_UNITS=metric\n')
        def wait(condition):
            end = time.monotonic() + 10
            while not condition():
                app.processEvents()
                if time.monotonic() > end:
                    self.fail('GPS dialog did not settle')
                time.sleep(.002)
            app.processEvents()
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(config.parent)):
            for kind in ('report', 'apply'):
                with self.subTest(kind=kind):
                    target = self.folder/'not-published.jpg'
                    initial = None if kind == 'report' else dict(method='manual', latitude='40.25', longitude='-71.5')
                    dialog = LocationDialog(kind, [str(source)], 'create', [str(target)], initial)
                    dialog.show()
                    try:
                        wait(lambda: dialog.plan is not None and dialog.worker is None and not dialog.timer.isActive())
                        if kind == 'report':
                            dialog.accept()
                            self.assertTrue(dialog.isVisible(), 'Read-only viewer cannot approve a write')
                        else:
                            self.assertTrue(dialog.apply_button.isEnabled())
                        dialog.reject()
                        wait(lambda: not dialog.isVisible())
                        self.assertIsNone(dialog.worker)
                        self.assertIsNone(dialog.thumbnail_worker)
                        self.assertIsNone(dialog.photo_preview.worker)
                        self.assertFalse(target.exists())
                        self.assertEqual(before, {p: signature(p) for p in before})
                    finally:
                        dialog.reject()
                        wait(lambda: not dialog.isVisible())

    def test_dispatcher_real_review_gate_publication_and_cancellation(self):
        from support import Workspace
        for operation, cancel in (('apply', False), ('reduce', False), ('apply', True)):
            with self.subTest(operation=operation, cancel=cancel):
                workspace = Workspace()
                self.addCleanup(workspace.close)
                workspace.env['KIM_TEST_EXTRA_ROOTS'] = json.dumps([str(self.folder)])
                workspace.env['KIM_POLICY'] = 'create'
                workspace.env['GPS_TEST_CANCEL'] = 'yes' if cancel else 'no'
                trace = workspace.control/'gps-ui.jsonl'
                workspace.env['GPS_TEST_TRACE'] = str(trace)
                for name in ('exiftool', 'identify', 'magick', 'chmod', 'touch'):
                    executable = workspace.bin/name
                    executable.unlink()
                    executable.symlink_to(shutil.which(name))
                workspace.use_real_mv()
                config = workspace.control/'config'/'kim6'
                config.mkdir(exist_ok=True)
                (config/'settings.conf').write_text('KIM_LOCATION_ONLINE_MAPS=no\nKIM_LOCATION_UNITS=metric\n')
                # Automate native user choices in the real Qt dialogs. Reading,
                # planning, review validation, staging and publication are real.
                driver = workspace.control/'gps-user.py'
                driver.write_text('''import sys,os,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import QTimer
from kim_location_dialog import LocationDialog,show_location_result
from kim_preview import save_plan
app=QApplication([])
app.setQuitOnLastWindowClosed(False)
def log(record):
    with Path(os.environ['GPS_TEST_TRACE']).open('a') as stream:
        stream.write(json.dumps(record)+'\\n')
args=sys.argv[1:]
if args[0]=='--result':
    fields=Path(args[1]).read_bytes().decode().split('\\0')[:-1]
    count=int(fields[5]); ok=int(fields[0])
    log(dict(phase='result',ok=ok,saved=fields[6+count:6+count+ok]))
    timer=QTimer()
    timer.timeout.connect(lambda: app.activeModalWidget().reject() if app.activeModalWidget() else None)
    timer.start(10)
    show_location_result(args[1],args[2])
    sys.exit(0)
kind,result,policy,seeds_path,*files=args
seeds=Path(seeds_path).read_bytes().decode().split('\\0')[:-1] if seeds_path!='-' else None
initial=dict(method='manual',latitude='40.25',longitude='-71.5',altitude='50') if kind=='apply' else None
dialog=LocationDialog(kind,files,policy,seeds,initial)
started=time.monotonic(); attempted=False
def choose():
    global attempted
    if time.monotonic()-started>12:
        print('GPS user driver timed out: '+dialog.summary.text(),file=sys.stderr)
        dialog.reject();return
    if attempted or dialog.worker or dialog.timer.isActive() or not dialog.plan:return
    if dialog.apply_button is None or not dialog.apply_button.isEnabled():
        print('GPS review blocked: '+repr(dialog.plan),file=sys.stderr)
        dialog.reject();return
    attempted=True
    targets=[entry.get('target') for entry in dialog.plan['entries'] if entry['status']=='change']
    assert all(not Path(target).exists() for target in targets)
    log(dict(phase=policy,files=dialog.files,targets=targets,button=dialog.apply_button.text(),
             approved=[entry.get('approved_location') for entry in dialog.plan['entries']]))
    if policy!='select' and os.environ.get('GPS_TEST_CANCEL')=='yes':dialog.cancel_button.click()
    else:dialog.apply_button.click()
timer=QTimer();timer.timeout.connect(choose);timer.start(10)
status=dialog.exec()
if status!=QDialog.Accepted:sys.exit(130)
if policy=='select':Path(result).write_text(json.dumps(dict(dialog.config(),files=dialog.files)))
else:save_plan(result,dialog.plan)
''')
                python = workspace.bin/'python3'
                python.unlink()
                python.write_text('#!' + sys.executable + '\n' + '''import os,sys
from pathlib import Path
args=sys.argv[1:]
index=1 if args[:1]==['-B'] else 0
if len(args)>index and Path(args[index]).name=='kim_location_dialog.py':
    driver=str(Path(__file__).resolve().parent.parent/'gps-user.py')
    os.execv(sys.executable,[sys.executable,'-B',driver,*args[index+1:]])
os.execv(sys.executable,[sys.executable,*args])
''')
                python.chmod(0o700)
                source, _data = self.fixture(f"cli-inputs/-雪 ' $ GPS {operation} {cancel}.jpg")
                before = signature(source)
                result = subprocess.run([str(workspace.dispatcher), 'location-'+operation, '--', str(source)],
                                        cwd=workspace.root, env=workspace.env, capture_output=True, text=True, timeout=45)
                self.assertEqual(before, signature(source))
                events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
                review = next(event for event in events if event['phase']=='create')
                self.assertEqual([str(source)], review['files'])
                self.assertEqual('Apply changes', review['button'])
                if cancel:
                    self.assertNotEqual(0, result.returncode)
                    self.assertFalse(any(event['phase']=='result' for event in events))
                    self.assertFalse(any(Path(path).exists() for path in review['targets']))
                else:
                    self.assertEqual(0, result.returncode, result.stderr)
                    receipt = next(event for event in events if event['phase']=='result')
                    self.assertEqual(1, receipt['ok'])
                    self.assertEqual(review['targets'], receipt['saved'])
                    self.assertNotEqual(str(source), receipt['saved'][0])
                    raw = read_many(receipt['saved'])[receipt['saved'][0]]['raw']
                    position = summarize(raw)['position']
                    for actual, approved in zip(position, review['approved'][0]['position']):
                        self.assertAlmostEqual(actual, approved, places=8)
                self.assertFalse(list(self.folder.rglob('.kim6-stage.*')))
                self.assertFalse(list((workspace.control/'tmp').glob('kim.*')))

    def test_selective_report_retains_supported_location_representations(self):
        prepared = self.control/'rich.jpg'
        subprocess.run(['magick', '-size', '40x20', 'xc:red', str(prepared)], check=True, capture_output=True)
        subprocess.run(['exiftool', '-overwrite_original', '-GPSLatitude=48.5', '-GPSLongitude=2.25',
                        '-GPSLatitudeRef=N', '-GPSLongitudeRef=E', '-GPSAltitude=100',
                        '-XMP-exif:GPSLatitude=48.5', '-XMP-exif:GPSLongitude=2.25',
                        '-XMP-photoshop:City=Ville',
                        '-XMP-iptcExt:LocationShown=[{GPSLatitude=10,GPSLongitude=20,City=Other place}]',
                        '-XMP-dc:Description-fr=Texte conservé', str(prepared)], check=True, capture_output=True)
        full = read_many([str(prepared)])[str(prepared)]
        self.assertNotIn('error', full)
        source = self.folder/'rich 雪.jpg'
        protected_copy(prepared, source)
        before = signature(source)
        cache = {}
        report = build_plan('report', 'create', [str(source)], {}, cache=cache)
        self.assertEqual(summarize(full['raw']), report['entries'][0]['location_before'])
        self.assertTrue(any(key.startswith('XMP-iptcExt:') for key in cache[str(source)]['raw']))
        self.assertTrue(any(key.startswith('XMP-exif:') for key in cache[str(source)]['raw']))
        self.assertTrue(any(key.startswith('GPS:') for key in cache[str(source)]['raw']))
        self.assertEqual(before, signature(source))

    def test_cancellation_during_protected_copy_removes_only_its_own_output(self):
        from kim_location import copy_source_snapshot
        from kim_process import inspection_context, ProcessError
        source, _data = self.fixture()
        before = signature(source)
        output = self.control/'partial.jpg'
        calls = []
        def cancelled():
            calls.append(True)
            return len(calls) > 1
        with inspection_context(cancelled=cancelled):
            with self.assertRaises(ProcessError):
                copy_source_snapshot(str(source), output, identity(source))
        self.assertFalse(output.exists())
        self.assertEqual(before, signature(source))
        output.write_bytes(b'Existing output')
        with self.assertRaises(FileExistsError):
            copy_source_snapshot(str(source), output, identity(source))
        self.assertEqual(b'Existing output', output.read_bytes())
        self.assertEqual(before, signature(source))

    def test_unsupported_gif_stays_readonly(self):
        source = self.folder/'still.gif'
        subprocess.run(['magick', '-size', '40x20', 'xc:red', str(source)], check=True, capture_output=True)
        before = signature(source)
        plan = build_plan('apply', 'create', [str(source)],
                          dict(method='manual', latitude='40.25', longitude='-71.5'),
                          [str(self.folder/'blocked.gif')])
        self.assertEqual('error', plan['entries'][0]['status'])
        self.assertIn('GPS writes require verified', plan['entries'][0]['error'])
        self.assertFalse((self.folder/'blocked.gif').exists())
        self.assertEqual(before, signature(source))

    def test_apng_stays_blocked_without_mutating_source(self):
        import struct
        from test_png_metadata_container import fixture, chunk
        source = self.folder/'animated.png'
        source.write_bytes(fixture(
            chunk(b'acTL', struct.pack('>II', 1, 0)),
            chunk(b'fcTL', struct.pack('>IIIIIHHBB', 0, 1, 1, 0, 0, 1, 10, 0, 0))))
        before = signature(source)
        target = self.folder/'blocked-animation.png'
        plan = build_plan('apply', 'create', [str(source)],
                          dict(method='manual', latitude='40.25', longitude='-71.5'), [str(target)])
        self.assertEqual('error', plan['entries'][0]['status'])
        self.assertFalse(target.exists())
        self.assertEqual(before, signature(source))

    def test_atomic_publication_failure_keeps_original_and_removes_staging(self):
        source, data = self.fixture()
        _plan_path, output, _plan = self.plan(source, data)
        tools = self.control/'late-failure-bin'
        tools.mkdir()
        marker = self.control/'publication-attempted'
        link = tools/'ln'
        link.write_text("#!/bin/sh\nprintf called > '" + str(marker) + "'\nexit 1\n")
        link.chmod(0o700)
        before = signature(source)
        with patch.dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH']):
            result = self.publish(source, output)
        self.assertNotEqual(0, result.returncode)
        self.assertTrue(marker.is_file(), 'Failure must occur at publication after verification')
        self.assertFalse(output.exists())
        self.assertEqual(before, signature(source))
        self.assertFalse(list(self.folder.rglob('.kim6-stage.*')))
        self.assertFalse(list(self.control.glob('location-source*')))
