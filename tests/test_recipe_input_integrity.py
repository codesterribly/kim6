"""A successful real Recipe operation must preserve the selected source."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/bin'))
from kim_recipe_core import approve_rows, builtins, execute, preview
from kim_recipe_params import resolve_recipe
from metadata_integrity import sha256_noatime


def signature(path):
    info = path.stat()
    return (sha256_noatime(path), info.st_size, info.st_atime_ns,
            info.st_mtime_ns, info.st_ctime_ns)


class SourceIntegrity(unittest.TestCase):
    def test_web_export(self):
        recipe = resolve_recipe(next(r for r in builtins() if r['id'] == 'web-export'))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.jpg'
            subprocess.run(['magick', '-size', '80x60', 'xc:navy', str(source)],
                           check=True, timeout=10)
            os.utime(source, ns=(10**18, 15*10**17))
            before = signature(source)
            rows = preview(recipe, [source])
            self.assertFalse(rows[0].problems, rows[0].problems)
            self.assertEqual(before, signature(source))
            approved = approve_rows(recipe, [source], rows, None)
            results = execute(recipe, [source], approved_plan=approved)
            self.assertTrue(results[0]['ok'], results)
            self.assertEqual(before, signature(source))

    def test_unavailable_noatime_blocks_preview_and_execution(self):
        from unittest.mock import patch
        recipe = resolve_recipe(next(r for r in builtins() if r['id'] == 'web-export'))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.jpg'
            subprocess.run(['magick', '-size', '12x8', 'xc:red', str(source)],
                           check=True, timeout=10)
            os.utime(source, ns=(10**18, 15*10**17))
            original = signature(source)
            rows = preview(recipe, [source])
            approved = approve_rows(recipe, [source], rows, None)
            with patch.object(os, 'O_NOATIME', None):
                blocked = preview(recipe, [source])
                result = execute(recipe, [source], approved_plan=approved)
            self.assertIn('Protected source inspection', blocked[0].problems[0])
            self.assertFalse(result[0]['ok'])
            self.assertFalse(Path(rows[0].output).exists())
            self.assertEqual(signature(source), original)
