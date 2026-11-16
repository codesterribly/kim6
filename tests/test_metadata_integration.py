"""Dolphin metadata launch contracts and isolated installed-runtime checks."""
import json
import configparser
from pathlib import Path
import subprocess
import sys
import unittest

import test_manual_installation as installation
from metadata_integrity import sha256_noatime
from support import Workspace


METADATA_MODULES = (
    'kim_metadata_browser', 'kim_metadata_compare', 'kim_metadata_editor',
    'kim_metadata_reader', 'kim_metadata_sources',
)


def signature(path):
    info = path.stat()
    return (sha256_noatime(path), info.st_size, info.st_atime_ns,
            info.st_mtime_ns, info.st_ctime_ns)


class MetadataDispatchTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.launches = self.workspace.control / 'metadata-launches.jsonl'
        # Stub the external GUI process, not the metadata modules' internals.
        python = self.workspace.bin / 'python3'
        python.unlink()
        python.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:1] == ['-B']:
    args = args[1:]
if args[:1] == ['-c']:
    if os.environ.get('KIM_TEST_MISSING_QT'):
        print("No module named 'PySide6'", file=sys.stderr)
        sys.exit(1)
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
root = Path(os.environ['KIM_TEST_ROOT']) / '.control'
with (root / 'metadata-launches.jsonl').open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
if os.environ.get('KIM_TEST_LAUNCH_FAILURE'):
    print('fixture GUI launch failure', file=sys.stderr)
    sys.exit(7)
''')
        python.chmod(0o755)

    def test_each_action_opens_one_window_with_the_complete_ordered_selection(self):
        first = self.workspace.jpeg('first/photo 雪.jpg')
        second = self.workspace.jpeg('second/another image.jpg')
        sidecar = second.with_suffix('.xmp')
        sidecar.write_text('sidecar fixture')
        before = {path: signature(path) for path in (first, second, sidecar)}
        for command, module in (('metadata-view', 'kim_metadata_browser.py'),
                                ('metadata-edit', 'kim_metadata_editor.py')):
            with self.subTest(command=command):
                self.launches.unlink(missing_ok=True)
                result = self.workspace.dispatch(command, '--', second, first)
                self.assertEqual(0, result.returncode, result.stderr)
                calls = [json.loads(line) for line in self.launches.read_text().splitlines()]
                self.assertEqual([[str(self.workspace.control / module), str(second), str(first)]], calls)
                self.assertEqual({}, result.outputs)
                self.assertFalse(any(call['tool'] in ('magick', 'identify', 'mktemp', 'ln', 'mv')
                                     for call in result.calls))
                self.assertFalse(any('--radiolist' in call['argv'] or '--progressbar' in call['argv']
                                     for call in result.calls))
                self.assertEqual(before, {path: signature(path) for path in before})

    def test_single_leading_hyphen_name_and_optional_delimiter(self):
        source = self.workspace.jpeg('-photo 雪 with spaces.jpg')
        for command, module in (('metadata-view', 'kim_metadata_browser.py'),
                                ('metadata-edit', 'kim_metadata_editor.py')):
            for delimiter in ((), ('--',)):
                with self.subTest(command=command, delimiter=delimiter):
                    self.launches.unlink(missing_ok=True)
                    result = self.workspace.dispatch(command, *delimiter, source.name)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual([[str(self.workspace.control / module), source.name]],
                                     [json.loads(line) for line in self.launches.read_text().splitlines()])

    def test_missing_selection_or_runtime_fails_with_actionable_native_error(self):
        source = self.workspace.jpeg('photo.jpg')
        for command in ('metadata-view', 'metadata-edit'):
            for args in ((), ('--',)):
                with self.subTest(command=command, args=args):
                    result = self.workspace.dispatch(command, *args)
                    self.assert_failure(result, 'Select at least one image')
            for missing, message in (
                ('bin/python3', 'python3'), ('bin/exiftool', 'ExifTool'),
                ('kim_metadata_reader.py', 'Reinstall KIM6'),
                ('kim_metadata_browser.py' if command == 'metadata-view'
                 else 'kim_metadata_editor.py', 'Reinstall KIM6'),
            ):
                with self.subTest(command=command, missing=missing):
                    path = self.workspace.control / missing
                    hidden = path.with_name(path.name + '.unavailable')
                    path.rename(hidden)
                    try:
                        result = self.workspace.dispatch(command, '--', source)
                        self.assert_failure(result, message)
                    finally:
                        hidden.rename(path)
            self.workspace.env['KIM_TEST_MISSING_QT'] = '1'
            try:
                result = self.workspace.dispatch(command, '--', source)
                self.assert_failure(result, 'Install PySide6')
            finally:
                del self.workspace.env['KIM_TEST_MISSING_QT']

    def assert_failure(self, result, message):
        self.assertNotEqual(0, result.returncode)
        errors = [call for call in result.calls if call['tool'] == 'kdialog'
                  and '--error' in call['argv']]
        self.assertTrue(errors, result.stderr)
        self.assertIn(message, errors[-1]['argv'][-1])
        self.assertFalse(self.launches.exists())
        self.assertEqual({}, result.outputs)

    def test_gui_failure_reports_diagnostic_and_preserves_exit_status(self):
        source = self.workspace.jpeg('photo.jpg')
        self.workspace.env['KIM_TEST_LAUNCH_FAILURE'] = '1'
        for command in ('metadata-view', 'metadata-edit'):
            with self.subTest(command=command):
                result = self.workspace.dispatch(command, '--', source)
                self.assertEqual(7, result.returncode)
                errors = [call for call in result.calls if '--error' in call['argv']]
                self.assertTrue(errors)
                self.assertIn('fixture GUI launch failure', errors[-1]['argv'][-1])
                self.assertEqual({}, result.outputs)

    def test_metadata_actions_do_not_require_processing_dependencies(self):
        source = self.workspace.jpeg('photo.jpg')
        for tool in ('magick', 'identify', 'ffmpeg', 'ffprobe'):
            (self.workspace.bin / tool).unlink()
        for command in ('metadata-view', 'metadata-edit'):
            with self.subTest(command=command):
                result = self.workspace.dispatch(command, '--', source)
                self.assertEqual(0, result.returncode, result.stderr)


class MetadataMenuTests(unittest.TestCase):
    def test_actions_append_to_existing_group_and_forward_the_complete_selection(self):
        menu = configparser.ConfigParser(interpolation=None)
        menu.read(installation.ROOT / 'src/kim_metadata.desktop.in')
        self.assertEqual('KIM6 - Organize/Metadata', menu['Desktop Entry']['_X-KDE-Submenu'])
        self.assertEqual(
            '00CheckExtensions;01Rename;02SetDates;04SetCopyright;04Overlay;'
            '05StripMetadata;06ViewMetadata;07EditMetadata;', menu['Desktop Entry']['Actions'])
        for action, label, command in (
            ('06ViewMetadata', 'View metadata…', 'metadata-view'),
            ('07EditMetadata', 'Edit metadata…', 'metadata-edit'),
        ):
            with self.subTest(action=action):
                section = menu['Desktop Action ' + action]
                self.assertEqual(label, section['_Name'])
                self.assertEqual(f'kim_all {command} -- %F', section['Exec'])


class MetadataInstallationTests(unittest.TestCase):
    def setUp(self):
        self.installation = installation.ManualInstallationTests('test_installed_menus_use_installed_dispatcher')
        self.installation.setUp()
        self.addCleanup(self.installation.doCleanups)
        fixture = self.installation
        fixture.env.update(XDG_CONFIG_HOME=str(fixture.base / 'config'),
                           PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
        # Exercise the installer without regenerating checkout documentation.
        identity = fixture.base / 'test-bin/id'
        identity.write_text('#!/bin/sh\nprintf "0\\n"\n')
        identity.chmod(0o755)

    def test_metadata_modules_install_import_and_uninstall_without_checkout(self):
        fixture = self.installation
        fixture.run_installer('install.sh')
        for name in METADATA_MODULES:
            installed = fixture.runtime / 'bin' / (name + '.py')
            self.assertTrue(installed.is_file(), name)
            self.assertEqual(0o644, installed.stat().st_mode & 0o777)
        result = subprocess.run([
            sys.executable, '-I', '-B', '-c',
            'import importlib, pathlib, sys; root=pathlib.Path(sys.argv[1]); '
            'sys.path.insert(0, str(root)); '
            'modules=[importlib.import_module(name) for name in sys.argv[2:]]; '
            'assert all(pathlib.Path(module.__file__).parent == root for module in modules)',
            str(fixture.runtime / 'bin'), *METADATA_MODULES,
        ], cwd=fixture.base, env=fixture.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        # Exercise real installed widgets and ExifTool against fresh sources.
        workspace = Workspace()
        self.addCleanup(workspace.close)
        first = workspace.jpeg('first/photo 雪.jpg')
        second = workspace.jpeg('second/-another image.jpg')
        sidecar = first.with_suffix('.xmp')
        sidecar.write_text('''<x:xmpmeta xmlns:x="adobe:ns:meta/">
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">Dolphin fixture</rdf:li></rdf:Alt></dc:title>
</rdf:Description></rdf:RDF></x:xmpmeta>''')
        before = {path: signature(path) for path in (first, second, sidecar)}
        driver = '''import importlib, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
from PySide6.QtWidgets import QApplication
module = importlib.import_module(sys.argv[2])
app = QApplication([])
paths = sys.argv[4:]
window = getattr(module, sys.argv[3])(paths)
window.show()
def wait(condition):
    deadline = time.monotonic() + 10
    while not condition():
        app.processEvents()
        time.sleep(0.01)
        assert time.monotonic() < deadline, "Application loading timed out"
    app.processEvents()
if hasattr(window, 'overview_records'):
    wait(lambda: window.overview_records.get(paths[0]) is not None)
    assert not window.records, "Opening Browser must not extract complete records"
    for row, path in enumerate(paths):
        window.image_list.setCurrentRow(row)
        wait(lambda: window.overview_records.get(path) is not None and window.previews.get(path) is not None)
        window.tabs.setCurrentIndex(1)
        wait(lambda: window.records.get(path) is not None)
        window.tabs.setCurrentIndex(0)
else:
    for row, path in enumerate(paths):
        window.file_list.setCurrentRow(row)
        wait(lambda: window.records.get(path) is not None and window.previews.get(path) is not None)
    assert not window.full_records, "Opening Editor must not extract complete records"
assert window.paths == paths, window.paths
assert list(window.records) == paths, list(window.records)
for record in window.records.values():
    assert record.error is None, record.error
    assert record.entries, "No metadata extracted"
assert window.records[paths[0]].sidecars == [str(pathlib.Path(paths[0]).with_suffix('.xmp'))]
assert any(entry.value == 'Dolphin fixture' for entry in window.records[paths[0]].entries)
assert len(window.previews) == len(paths), "Missing cached previews"
window.close()
wait(lambda: not window.isVisible())
'''
        for module, widget in (('kim_metadata_browser', 'MetadataBrowser'),
                               ('kim_metadata_editor', 'MetadataEditor')):
            with self.subTest(installed_application=module):
                result = subprocess.run([
                    sys.executable, '-I', '-B', '-c', driver, str(fixture.runtime / 'bin'),
                    module, widget, str(first), str(second),
                ], cwd=fixture.base, env=fixture.env, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(before, {path: signature(path) for path in before})
        fixture.run_installer('uninstall.sh')
        self.assertTrue(all(not (fixture.runtime / 'bin' / (name + '.py')).exists()
                            for name in METADATA_MODULES))


if __name__ == '__main__':
    unittest.main()
