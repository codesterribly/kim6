"""Literal Settings reads, using only disposable filesystem objects."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from kim_recipe_image import literal_settings
from kim_recipe_core import RecipeError
from kim_settings_dialog import load_settings, save_settings, DEFAULTS


class SettingsSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='kim6-settings-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'kim6/settings.conf'
        self.path.parent.mkdir()
        env = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.root)})
        env.start(); self.addCleanup(env.stop)

    def test_missing_literal_values_precedence_and_atomic_replacement(self):
        self.assertEqual(load_settings(self.path), DEFAULTS)
        self.assertEqual(literal_settings({'KIM_COPYRIGHT_USAGE_RIGHTS': ''}), {'KIM_COPYRIGHT_USAGE_RIGHTS': ''})
        values = {**DEFAULTS, 'KIM_COPYRIGHT_USAGE_RIGHTS': '雪 $HOME; literal',
                  'KIM_AFFIX_COMPRESSED': 'small', 'KIM_WEB_QUALITY_JPEG': '83',
                  'KIM_LOCATION_UNITS': 'imperial', 'KIM_LOCATION_ONLINE_MAPS': 'yes'}
        save_settings(self.path, values)
        self.assertEqual(load_settings(self.path), values)
        self.assertEqual(literal_settings({'KIM_COPYRIGHT_USAGE_RIGHTS': ''})['KIM_COPYRIGHT_USAGE_RIGHTS'], '雪 $HOME; literal')
        with patch.dict(os.environ, {'KIM_COPYRIGHT_USAGE_RIGHTS': 'environment'}):
            self.assertEqual(literal_settings({'KIM_COPYRIGHT_USAGE_RIGHTS': ''})['KIM_COPYRIGHT_USAGE_RIGHTS'], 'environment')
        replacement = self.root / 'replacement'
        replacement.write_text('KIM_LOCATION_UNITS=metric\n')
        os.replace(replacement, self.path)
        self.assertEqual(load_settings(self.path)['KIM_LOCATION_UNITS'], 'metric')

    def test_malformed_oversized_and_directory_rejected_by_both_consumers(self):
        for payload in (b'KIM_POLICY=\xff', b'KIM_POLICY=create\0', b'x' * (1024 * 1024 + 1)):
            with self.subTest(payload=payload[:30]):
                self.path.write_bytes(payload)
                with self.assertRaises((OSError, ValueError)): load_settings(self.path)
                with self.assertRaises((OSError, RecipeError)): literal_settings({'KIM_POLICY': 'prompt'})
        self.path.unlink(); self.path.mkdir()
        with self.assertRaises((OSError, ValueError)): load_settings(self.path)
        with self.assertRaises((OSError, RecipeError)): literal_settings({})

    def test_symlinks_including_dangling_are_rejected(self):
        target = self.root / 'target'; target.write_text('KIM_POLICY=create')
        for destination in (target, self.root / 'missing'):
            self.path.symlink_to(destination)
            try:
                with self.assertRaises((OSError, ValueError)): load_settings(self.path)
                with self.assertRaises((OSError, RecipeError)): literal_settings({})
            finally:
                self.path.unlink()
        self.assertEqual(target.read_text(), 'KIM_POLICY=create')

    def test_fifo_read_returns_without_a_writer(self):
        os.mkfifo(self.path)
        code = ('import sys; from pathlib import Path; from kim_settings_dialog import load_settings; '
                'load_settings(Path(sys.argv[1]))')
        result = subprocess.run([sys.executable, '-B', '-c', code, str(self.path)],
                                env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src/bin')},
                                capture_output=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'regular file', result.stderr)
