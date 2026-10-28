"""Regression checks for batch preflight, duplicate sources and metadata isolation.

Only disposable files are modified. The Bash helper definitions are taken
verbatim from the dispatcher; the Dolphin/KDialog progress interface is stubbed.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/bin/kim_all"
ENTRYPOINT = '\nmain "$@"\n'


class FunctionalAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kim6-functional-audit-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        script = SOURCE.read_text(encoding="utf-8")
        self.assertEqual(script.count(ENTRYPOINT), 1)
        self.library = self.root / "kim-library.sh"
        self.library.write_text(script.replace(ENTRYPOINT, "\n"), encoding="utf-8")

    def run_action(self, action, *inputs, extra='', policy='create', extra_env=None):
        harness = r'''
source "$1"
set +e
shift
KIM_POLICY="${KIM_TEST_POLICY:-create}"
KIM_NAME_AFFIX_POSITION=suffix
gettext(){ printf '%s' "$1"; }
kdialog(){ case " $* " in *--radiolist*) printf 'review\n' ;; esac; return 0; }
progress_error(){ printf 'ERROR:%s\n' "$1"; }
progress_open(){ printf 'fake'; }
progress_begin_item(){ return 0; }
progress_cancelled(){ return 1; }
progress_value(){ return 0; }
progress_close(){ return 0; }
report_finish_dialog(){ printf 'summary ok=%s fail=%s\n' "$REPORT_OK" "$REPORT_FAIL"; }
mk_workdir
'''
        result = subprocess.run(
            ["bash", "-c", harness + extra + "\n" + action + "\nexit $?\n",
             "bash", str(self.library), *map(str, inputs)],
            cwd=self.root, env={**os.environ, "KIM_TEST_POLICY": policy, **(extra_env or {})},
            capture_output=True, text=True, timeout=30,
        )
        return result

    def test_newline_selection_rejected_before_any_batch_progress(self):
        good = self.root / 'ordinary.jpg'
        bad = self.root / 'bad\nfilename.jpg'
        good.write_bytes(b'not a picture')
        bad.write_bytes(b'not a picture')
        invocations = (
            'action_compress --quality 70 -- "$1" "$2"',
            'action_convert --format png -- "$1" "$2"',
            'action_resize --percent 50 -- "$1" "$2"',
            'action_rotate --angle 90 -- "$1" "$2"',
            'action_flipflop flip -- "$1" "$2"',
            'action_stripmeta --mode all -- "$1" "$2"',
            'action_stripmeta --mode gps -- "$1" "$2"',
            'action_copyright --creator Photographer -- "$1" "$2"',
            'action_timeshift --offset +01:00:00 -- "$1" "$2"',
        )
        for invocation in invocations:
            with self.subTest(action=invocation):
                result = self.run_action(invocation, good, bad)
                self.assertNotEqual(result.returncode, 0, (invocation, result.stdout, result.stderr))
                self.assertNotIn('summary ok=', result.stdout,
                                 'An invalid selection must not enter the batch loop')
                self.assertEqual(good.read_bytes(), b'not a picture')

    def test_duplicate_preflight_policy_is_action_specific(self):
        source = self.root / 'ordinary.jpg'
        source.write_bytes(b'unchanged input')
        repeated = self.run_action(
            'files=(); collect_valid_files_with_repeats files "$1" "$1"; '
            'rc=$?; printf "count=%d\n" "${#files[@]}"; exit "$rc"',
            source)
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertIn('count=2', repeated.stdout)
        rejected = self.run_action(
            'files=(); collect_valid_files files "$1" "$1"; '
            'rc=$?; printf "count=%d\n" "${#files[@]}"; exit "$rc"',
            source)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('count=0', rejected.stdout)
        self.assertEqual(source.read_bytes(), b'unchanged input')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('identify'),
                         'ImageMagick 7 is required for the resize fixture')
    def test_duplicate_overwrite_percent_resize_is_rejected_without_changes(self):
        source = self.root / 'photo.png'
        subprocess.run([shutil.which('magick'), '-size', '100x100', 'xc:skyblue', str(source)],
                       check=True, capture_output=True)
        result = self.run_action('action_resize --percent 50 -- "$1" "$1"', source,
                                 policy='overwrite')
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn('summary ok=', result.stdout)
        output = subprocess.run([shutil.which('identify'), '-format', '%wx%h', str(source)],
                                check=True, capture_output=True, text=True).stdout
        self.assertEqual(output, '100x100')

    def test_failed_items_return_nonzero_from_image_actions(self):
        corrupt = self.root / 'corrupt.jpg'
        corrupt.write_bytes(b'not an actual image')
        invocations = (
            'action_compress --quality 70 -- "$1"',
            'action_convert --format png -- "$1"',
            'action_resize --percent 50 -- "$1"',
            'action_rotate --angle 90 -- "$1"',
            'action_flipflop flip -- "$1"',
            'action_stripmeta --mode all -- "$1"',
        )
        for invocation in invocations:
            with self.subTest(action=invocation):
                result = self.run_action(invocation, corrupt)
                self.assertNotEqual(result.returncode, 0, (invocation, result.stdout, result.stderr))
                if invocation.startswith(('action_rotate', 'action_flipflop')):
                    # Create policy refuses in-place work before progress starts.
                    self.assertNotIn('summary ok=', result.stdout)
                else:
                    self.assertIn('summary ok=0 fail=1', result.stdout)
                self.assertEqual(corrupt.read_bytes(), b'not an actual image')

    @unittest.skipUnless(shutil.which('magick') and shutil.which('identify'),
                         'ImageMagick 7 is required for the mixed-batch fixture')
    def test_mixed_batch_keeps_successful_output_but_returns_failure(self):
        corrupt = self.root / 'bad.png'
        correct = self.root / 'good.png'
        corrupt.write_bytes(b'not a picture')
        subprocess.run([shutil.which('magick'), '-size', '100x100', 'xc:skyblue',
                        str(correct)], check=True, capture_output=True)
        before = correct.read_bytes()
        result = self.run_action('action_resize --percent 50 -- "$1" "$2"',
                                 corrupt, correct)
        self.assertNotEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('summary ok=1 fail=1', result.stdout)
        output = self.root / 'good_resized.png'
        self.assertTrue(output.is_file(), result.stderr)
        self.assertEqual(correct.read_bytes(), before)
        dimensions = subprocess.run([shutil.which('identify'), '-format', '%wx%h',
                                     str(output)], check=True, capture_output=True,
                                    text=True).stdout
        self.assertEqual(dimensions, '50x50')

    def test_gps_ai_batch_does_not_delete_non_ai_digital_source_type(self):
        first = self.root / 'first.jpg'
        second = self.root / 'second.jpg'
        first.touch()
        second.touch()
        fake_tool = self.root / 'exiftool'
        fake_tool.write_text('#!/bin/sh\nexit 0\n')
        fake_tool.chmod(0o700)
        extra = r'''
PATH="${KIM_TEST_TOOL_DIR:-$PWD}:$PATH"
metadata_query(){
  local file="$1"; shift
  case "$*" in
    *-XMP-iptcExt:DigitalSourceType*)
      case "$file" in *first.jpg) printf trainedAlgorithmicMedia ;; *) printf negativeFilm ;; esac ;;
    *-GPS:all*) printf 'gps-data' ;;
  esac
}
metadata_publish_one(){
  local file="$1" arg matched=false
  shift 5
  for arg in "$@"; do
    [ "$arg" != '-XMP-iptcExt:DigitalSourceType=' ] || matched=true
  done
  printf '%s deleted_digital_source_type=%s\n' "${file##*/}" "$matched"
  return 0
}
'''
        # Fake ExifTool is only a presence probe; publishing is instrumented.
        result = self.run_action('action_stripmeta_selective gps true "$1" "$2"',
                                 first, second, extra=extra, policy='prompt',
                                 extra_env={'KIM_TEST_TOOL_DIR': str(self.root)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('first.jpg deleted_digital_source_type=true', result.stdout)
        self.assertIn('second.jpg deleted_digital_source_type=false', result.stdout)
