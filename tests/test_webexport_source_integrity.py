"""Strict 5-attribute source-integrity regression tests for standalone Web Export (kim_all webexport)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))

from metadata_integrity import sha256_noatime


def signature(path: Path):
    info = path.stat()
    return (
        sha256_noatime(path),
        info.st_size,
        info.st_atime_ns,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def age_file(path: Path):
    os.utime(path, ns=(10**18, 15 * 10**17))


def make_fixture(path: Path, *, width=120, height=80):
    subprocess.run(
        [
            'magick',
            '-size',
            f'{width}x{height}',
            'xc:navy',
            '-fill',
            'orange',
            '-draw',
            f'rectangle {width // 2},0 {width - 1},{height - 1}',
            '-depth',
            '8',
            str(path),
        ],
        check=True,
        timeout=15,
        capture_output=True,
    )


def image_info(path: Path):
    out = subprocess.check_output(
        ['identify', '-regard-warnings', '-format', '%m|%w|%h', str(path)],
        timeout=10,
        text=True,
    )
    fmt, w, h = out.strip().split('|')
    return fmt, int(w), int(h)


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
class StandaloneWebExportSourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kimng-m5b-webexport-', dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin_dir = self.base / 'bin'
        self.stub_dir = self.base / 'stubs'
        self.config_home = self.base / 'config'
        self.data_home = self.base / 'data'
        self.work_dir = self.base / 'work'
        for d in (self.bin_dir, self.stub_dir, self.config_home, self.data_home, self.work_dir):
            d.mkdir(parents=True)

        # Mirror kim_all and its Python companions into an isolated dispatcher dir.
        shutil.copy2(ROOT / 'src/bin/kim_all', self.bin_dir / 'kim_all')
        (self.bin_dir / 'kim_all').chmod(0o755)
        for py in (ROOT / 'src/bin').glob('*.py'):
            shutil.copy2(py, self.bin_dir / py.name)

        # Drive the REAL WebExportReview Qt dialog non-blocking (accepting when Apply is enabled).
        review_shim = self.bin_dir / 'kim_webexport_review.py'
        review_shim.write_text(
            f"""#!/usr/bin/env python3
import sys
sys.path.insert(0, {str(ROOT / 'src/bin')!r})
from PySide6.QtCore import QTimer
import kim_webexport_review as real_review
orig_exec = real_review.WebExportReview.exec
def auto_exec(self):
    QTimer.singleShot(0, self.accept if self.apply.isEnabled() else self.reject)
    return orig_exec(self)
real_review.WebExportReview.exec = auto_exec
raise SystemExit(real_review.main())
""",
            encoding='utf-8',
        )
        review_shim.chmod(0o755)

        # Minimal non-blocking kdialog & qdbus stubs (all image tools are 100% real).
        kdialog = self.stub_dir / 'kdialog'
        kdialog.write_text(
            '#!/usr/bin/env bash\n'
            'if [ "${1:-}" = "--progressbar" ] || [[ " $* " == *" --progressbar "* ]]; then\n'
            '  echo "org.kde.kdialog-test /ProgressDialog"\n'
            'fi\n'
            'exit 0\n',
            encoding='utf-8',
        )
        kdialog.chmod(0o755)
        for qname in ('qdbus', 'qdbus6'):
            qstub = self.stub_dir / qname
            qstub.write_text(
                '#!/usr/bin/env bash\n'
                'if [[ " $* " == *" wasCancelled "* ]]; then echo "false"; fi\n'
                'exit 0\n',
                encoding='utf-8',
            )
            qstub.chmod(0o755)

        self.env = dict(os.environ)
        self.env['PATH'] = f'{self.stub_dir}:{os.environ.get("PATH", "")}'
        self.env['XDG_CONFIG_HOME'] = str(self.config_home)
        self.env['XDG_DATA_HOME'] = str(self.data_home)
        self.env['QT_QPA_PLATFORM'] = 'offscreen'

    def run_webexport(self, *args, extra_env=None):
        env = dict(self.env)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.bin_dir / 'kim_all'), 'webexport', *map(str, args)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_01_positive_control_ordinary_read_advances_atime(self):
        src = self.work_dir / 'positive.jpg'
        make_fixture(src)
        age_file(src)
        before = signature(src)
        self.assertEqual(before, signature(src))
        _ = src.read_bytes()
        after = signature(src)
        self.assertNotEqual(after[2], before[2], 'Test filesystem must advance atime on ordinary reads')
        self.assertEqual((after[0], after[1], after[3], after[4]), (before[0], before[1], before[3], before[4]))

    def test_02_standalone_webexport_preserves_all_five_attributes_and_affix(self):
        src = self.work_dir / 'fixed_src.jpg'
        make_fixture(src, width=200, height=100)
        subprocess.run(
            ['exiftool', '-overwrite_original', '-Artist=Original Artist', '-XMP-dc:Title=Keep Untouched', str(src)],
            check=True,
            timeout=15,
            capture_output=True,
        )
        age_file(src)
        before = signature(src)
        self.assertEqual(before, signature(src))

        result = self.run_webexport(
            '--size', '100x100', '--format', 'jpg', '--', src,
            extra_env={'KIM_AFFIX_WEB': 'WACKAWACKA'},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        after = signature(src)
        self.assertEqual(after, before, f'Source attributes changed: before={before} after={after}')

        out = src.parent / 'fixed_src_WACKAWACKA.jpg'
        self.assertTrue(out.exists(), list(src.parent.iterdir()))
        self.assertEqual(image_info(out), ('JPEG', 100, 50))
        tags = json.loads(
            subprocess.check_output(['exiftool', '-j', '-Artist', '-XMP:Title', str(out)], timeout=15)
        )[0]
        self.assertNotIn('Artist', tags)
        self.assertNotIn('Title', tags)

    def test_03_standalone_webexport_formats_png_webp_tiff_gif_and_psd(self):
        for ext in ('png', 'webp', 'tiff', 'gif', 'psd'):
            with self.subTest(ext=ext):
                src = self.work_dir / f'sample_{ext}.{ext}'
                make_fixture(src, width=96, height=72)
                age_file(src)
                before = signature(src)
                out_dir = self.work_dir / f'out_{ext}'
                out_dir.mkdir()
                result = self.run_webexport(
                    '--size', '64x64', '--format', 'jpg', '--output-dir', out_dir, '--', src,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(signature(src), before, f'{ext} source attributes changed')
                outputs = list(out_dir.iterdir())
                self.assertEqual(len(outputs), 1)
                self.assertEqual(image_info(outputs[0]), ('JPEG', 64, 48))

    def test_04_collision_numbering_preserves_occupied_and_source_integrity(self):
        src = self.work_dir / 'collide.jpg'
        make_fixture(src, width=80, height=60)
        age_file(src)
        before = signature(src)
        occupied = src.parent / 'collide_WACKAWACKA.jpg'
        occupied.write_bytes(b'sentinel-occupied')

        result = self.run_webexport(
            '--size', '80x60', '--format', 'jpg', '--', src,
            extra_env={'KIM_AFFIX_WEB': 'WACKAWACKA'},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(signature(src), before)
        self.assertEqual(occupied.read_bytes(), b'sentinel-occupied')
        self.assertTrue((src.parent / 'collide_WACKAWACKA_1.jpg').exists())

    def test_05_protected_open_failure_fails_closed_without_unsafe_fallback(self):
        src = self.work_dir / 'sym_target.jpg'
        make_fixture(src, width=40, height=30)
        age_file(src)
        before = signature(src)
        link = self.work_dir / 'sym_link.jpg'
        link.symlink_to(src)

        for mode in ('is-psd', 'has-apng'):
            proc = subprocess.run(
                [sys.executable, str(ROOT / 'src/bin/kim_process.py'), mode, str(link)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 125)
        proc = subprocess.run(
            [sys.executable, str(ROOT / 'src/bin/kim_process.py'), 'run-stdin', str(link), '--', 'cat'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 125)
        self.assertEqual(signature(src), before)


if __name__ == '__main__':
    unittest.main()
