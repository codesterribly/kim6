"""Desktop Entry encoding and synchronization in disposable installations."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
import kim_recipe_menu as menu
from kim_recipe_core import RecipeError, RecipeLibrary
import test_manual_installation as installation


class DesktopExecTests(unittest.TestCase):
    def test_encoding_literals(self):
        cases = [('/tmp/ordinary/kim_all', '"/tmp/ordinary/kim_all"'),
                 ('/tmp/a b/kim_all', '"/tmp/a b/kim_all"'),
                 ('/tmp/$/kim_all', '"/tmp/\\\\$/kim_all"'),
                 ('/tmp/\\/kim_all', '"/tmp/\\\\\\\\/kim_all"'),
                 ('/tmp/"/kim_all', '"/tmp/\\\\"/kim_all"'),
                 ('/tmp/`/kim_all', '"/tmp/\\\\`/kim_all"'),
                 ('/tmp/%F/kim_all', '"/tmp/%%F/kim_all"'),
                 ('/tmp/&#雪/kim_all', '"/tmp/&#雪/kim_all"')]
        for path, expected in cases:
            with self.subTest(path=path): self.assertEqual(menu.exec_argument(path), expected)

    def test_control_characters_are_rejected(self):
        for code in [*range(32), *range(127, 160)]:
            with self.subTest(code=code), self.assertRaises(RecipeError):
                menu.exec_argument('/tmp/' + chr(code) + '/kim_all')

    def test_installer_rejects_controls_before_creating_prefix(self):
        with tempfile.TemporaryDirectory(prefix='kim6-control-') as tmp:
            for control in ('\t', '\n', '\r', '\x7f', '\x85'):
                prefix = Path(tmp) / ('bad' + control)
                result = subprocess.run(['bash', str(ROOT / 'install.sh'), '--prefix', str(prefix)],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(prefix.exists())

    @unittest.skipUnless(shutil.which('kreadconfig6'), 'KDE KConfig reader unavailable')
    def test_kde_decodes_desktop_string_layer(self):
        with tempfile.TemporaryDirectory(prefix='kim6-kconfig-') as tmp:
            path = Path(tmp) / 'probe.desktop'
            executable = '/tmp/space $ back\\ quote" tick` %F & # 雪/kim_all'
            path.write_text('[Desktop Entry]\nExec=' + menu.exec_argument(executable) + ' -- %F\n')
            result = subprocess.run(['kreadconfig6', '--file', str(path), '--group',
                                     'Desktop Entry', '--key', 'Exec'],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.rstrip('\n'),
                             r'"/tmp/space \$ back\\ quote\" tick\` %%F & # 雪/kim_all" -- %F')

    def test_installer_and_recipe_sync_share_encoding(self):
        fixture = installation.ManualInstallationTests('test_installed_menus_use_installed_dispatcher')
        fixture.setUp()
        try:
            fixture.prefix = fixture.base / 'space $ back\\ quote" tick` %F & # 雪'
            fixture.runtime = fixture.prefix / 'kim6'
            fixture.env.update(XDG_CONFIG_HOME=str(fixture.base / 'config'),
                               PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen')
            # Do not regenerate the checkout's documentation during this test.
            (fixture.base / 'test-bin/id').write_text('#!/bin/sh\nprintf "0\\n"\n')
            (fixture.base / 'test-bin/id').chmod(0o755)
            result = fixture.run_installer('install.sh')
            self.assertNotIn('Recipes shortcuts were not synchronized', result.stderr)
            encoded = menu.exec_argument(str(fixture.runtime / 'bin/kim_all'))
            for template in (ROOT / 'src').glob('kim_*.desktop.in'):
                before = template.read_text()
                after = (fixture.prefix / template.name.removesuffix('.in')).read_text()
                expected = re.sub(r'^Exec=kim_all(?=[ \t]|$)', lambda _: 'Exec=' + encoded,
                                  before, flags=re.M)
                if template.name == 'kim_recipes.desktop.in':
                    expected = menu.render(RecipeLibrary(), fixture.runtime / 'bin/kim_all')
                self.assertEqual(after, expected)
            # Run the installed headless synchronizer, using only fixture paths.
            for _ in range(2):
                sync = subprocess.run([sys.executable, '-B', str(fixture.runtime / 'bin/kim_recipe_core.py'),
                                       '--sync-menu'], env=fixture.env, capture_output=True, text=True, timeout=10)
                self.assertEqual(sync.returncode, 0, sync.stderr)
            fixture.run_installer('install.sh')
            fixture.run_installer('uninstall.sh')
            self.assertFalse(fixture.runtime.exists())
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
