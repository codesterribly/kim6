#!/usr/bin/env python3
"""Focused creation-dialog smoke check; never renders HTML, PDF or TIFF output.

QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 tests/qt_creation_workflows_smoke.py
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QModelIndex, QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QAbstractItemView

import kim_create_dialog as ui
from kim_contactsheet_dialog import ContactSheetDialog
import kim_collage_dialog
from kim_photo_selection import ImagePicker


def pump_until(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
    raise AssertionError('Dialog/worker did not settle')


def inspected(dialog):
    pump_until(lambda: not dialog.ordered.counts()[2] and dialog.ordered.worker is None)


def read_values(path):
    data = path.read_bytes()
    assert data.endswith(b'\0')
    return [os.fsdecode(value) for value in data[:-1].split(b'\0')]


def no_workers(dialog):
    assert dialog.ordered.worker is None
    assert dialog.ordered.thumbnail_worker is None
    assert not dialog.ordered.thumbnail_timer.isActive()
    assert not dialog.isVisible()


def add_with_picker(dialog, path, *, cancel=False):
    """Drive the actual shared ImagePicker modal, including its close lifecycle."""
    errors = []
    pickers = []

    def select():
        try:
            picker = QApplication.activeModalWidget()
            assert isinstance(picker, ImagePicker)
            pickers.append(picker)
            assert 'Photo Collage' not in picker.windowTitle()
            picker.image_items[path].setSelected(True)
            if cancel:
                picker.reject()
            else:
                picker.add_button.click()
        except BaseException as exc:
            errors.append(exc)
            QApplication.activeModalWidget().reject()

    QTimer.singleShot(0, select)
    dialog.ordered.add_button.click()
    assert not errors, errors
    assert pickers and pickers[0].worker is None
    inspected(dialog)


def approve(dialog, settings):
    inspected(dialog)
    assert dialog.create.isEnabled(), dialog.status.text()
    QTimer.singleShot(0, dialog.create.click)
    assert dialog.exec() == QDialog.Accepted
    no_workers(dialog)
    return read_values(settings)


def bash_handoff(root, kind, fixture, initial, expected, *, cli=False, invalid=False, cancel=False):
    """Run real action handoff/target checks, intercepting all render commands."""
    source = (ROOT / 'src/bin/kim_all').read_text()

    def function(name):
        start = source.index(name + '() {')
        return source[start:source.index('\n}\n', start) + 3]

    capture = root / ('bash-' + kind + ('-cli' if cli else '') + ('-bad' if invalid else '')
                      + ('-cancel' if cancel else ''))
    script = '\n'.join(function(name) for name in (
        'collect_publication_inputs', 'prepare_derived_target', 'publication_input_frames', 'action_' + kind))
    script += r'''
set -euo pipefail
KIMDIR="$1"; DISPATCHER_DIR="$2"; fixture="$3"; capture="$4"; kind="$5"; cli="$6"; cancel="$7"; shift 7
require_action_tools() { :; }
enable_psd_sources() { :; }
gettext() { printf '%s' "$1"; }
progress_error() { printf '%s\n' "$*" >&2; }
kdialog() {
  local arg
  for arg in "$@"; do [ "$arg" != --error ] || return 0; done
  printf 'Unexpected kdialog\n' >&2; exit 88
}
python3() {
  [ "$cli" != 1 ] || exit 89
  [ "$cancel" != 1 ] || return 130
  printf '%s\0' "$@" > "$capture.dialog"
  if [ "$kind" = contactsheet ]; then cp -- "$fixture" "$2";
  else cp -- "$fixture" "$3"; fi
}
progress_open() {
  printf '%s\0' "${files[@]}" > "$capture.sources"
  printf '%s\0' "${target_dir:-${outpdf:-${output:-${target:-}}}}" > "$capture.target"
  printf ref
}
progress_cancelled() { [ "$kind" = gallery ]; }
progress_close() { :; }
publication_prepare_source() {
  printf '%s\0' "$2" >> "$capture.prepared"
  printf 'PNG|32|24|1\n' > "$KIMDIR/publication-records"
}
tmp_for_target() { [ "$kind" != contactsheet ] || return 1; printf '%s/stage' "$KIMDIR"; }
publication_fail() { return 1; }
publication_render_stage() { shift 2; printf '%s\0' "$@" > "$capture.command"; return 1; }
if action_"$kind" "$@"; then exit 77; fi
'''
    if cli:
        values = read_values(fixture)
        args = (['--grid', '3x4'] if kind == 'contactsheet' else [])
        args += ['--output', values[8] if kind == 'contactsheet' else values[0], '--', *initial]
    else:
        args = ['--', *initial]
    script_path = root / 'handoff.sh'
    script_path.write_text(script)
    helper = root / 'kim_create_dialog.py'
    if not helper.exists():
        helper.symlink_to(ROOT / 'src/bin/kim_create_dialog.py')
    result = subprocess.run(['bash', str(script_path), str(root), str(ROOT / 'src/bin'),
                             str(fixture), str(capture), kind, str(int(cli)), str(int(cancel)), *args],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    if invalid or cancel:
        assert not Path(str(capture) + '.sources').exists(), result.stderr
        return
    assert read_values(Path(str(capture) + '.sources')) == expected
    target = Path(read_values(Path(str(capture) + '.target'))[0])
    assert target.parent == root and not target.exists()
    if kind != 'gallery':
        assert read_values(Path(str(capture) + '.prepared')) == expected
    if kind in ('print', 'tiffjoin'):
        command = read_values(Path(str(capture) + '.command'))
        marker = command.index('--')
        assert command[marker + 1:marker + 1 + len(expected)] == expected
        assert command[0] == 'magick'
        if kind == 'tiffjoin':
            assert command[1] == '--' and command[-2] == '-adjoin'
    if cli:
        assert not Path(str(capture) + '.dialog').exists()


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='kim6-creation-') as directory:
        root = Path(directory)
        paths = []
        for name in ('first image.png', 'é 第二 image.png', 'third.png'):
            path = root / name
            image = QImage(32, 24, QImage.Format_RGB32)
            image.fill(0xff9988)
            assert image.save(str(path))
            paths.append(str(path))
        # Two-frame GIF fixture, written directly; no output renderer is invoked.
        gif = root / 'multi frame.gif'
        frame = b'\x21\xf9\x04\x00\x0a\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00'
        gif.write_bytes(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff' + frame * 2 + b';')
        originals = {p: hashlib.sha256(Path(p).read_bytes()).digest() for p in [*paths, str(gif)]}
        for kind, cls in (('gallery', ui.GalleryDialog), ('contactsheet', ContactSheetDialog),
                          ('print', ui.PrintLayoutDialog), ('tiffjoin', ui.TiffJoinDialog)):
            settings = root / (kind + '.approved')
            dialog = cls(settings, paths[:1]) if kind == 'contactsheet' else cls(settings, directory, paths[:1])
            dialog.show()
            inspected(dialog)
            one_height = dialog.height()
            assert one_height < 650, (kind, one_height)
            add_with_picker(dialog, paths[1], cancel=True)
            assert dialog.ordered.ordered_paths() == paths[:1]
            add_with_picker(dialog, paths[1])
            assert dialog.ordered.ordered_paths() == paths[:2]
            assert dialog.height() <= one_height + 100, (kind, dialog.height())
            assert dialog.height() < 750
            dialog.ordered.images.setCurrentRow(0)
            dialog.ordered.remove_button.click()
            assert dialog.ordered.ordered_paths() == paths[1:2]
            add_with_picker(dialog, paths[0])
            assert '2 selected' in dialog.count.text()
            # Button reorder and internal Qt model move (drag/drop's order path).
            dialog.ordered.images.setCurrentRow(1)
            dialog.ordered.up_button.click()
            assert dialog.ordered.ordered_paths() == paths[:2]
            model = dialog.ordered.images.model()
            assert model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 2)
            expected = [paths[1], paths[0]]
            assert dialog.ordered.ordered_paths() == expected
            if kind == 'gallery':
                assert dialog.parent_directory.text() == directory
                dialog.title.setText('A / Gallery!')
                assert dialog.folder_name.text() == 'A - Gallery'
                dialog.folder_name.setText('My Gallery')
                dialog.folder_name.textEdited.emit('My Gallery')
                dialog.title.setText('Independent title')
                assert dialog.folder_name.text() == 'My Gallery'
                (root / 'My Gallery').mkdir()
                (root / 'My Gallery' / 'sentinel').write_text('existing gallery')
                (root / 'My Gallery_1').symlink_to(root / 'missing')
                dialog.update_controls()
                assert dialog.target_label.text() == str(root / 'My Gallery_2')
                assert 'numbered' in dialog.status.text()
                # A name taken since the last preview must be reviewed again.
                (root / 'My Gallery_2').mkdir()
                dialog.accept()
                assert not settings.exists()
                assert dialog.target_label.text() == str(root / 'My Gallery_3')
                assert (root / 'My Gallery' / 'sentinel').read_text() == 'existing gallery'
            elif kind == 'contactsheet':
                choices = {
                    'paper': ['letter', 'a4'], 'orientation': ['portrait', 'landscape'],
                    'grid': ['auto', '4x5', '3x4', '5x7'],
                    'labels': ['both', 'number', 'filename', 'none', 'capture', 'camera', 'embedded'],
                    'font_size': ['auto', 'small', 'medium', 'large'],
                    'label_placement': ['below', 'above'], 'fit': ['fit', 'fill'],
                    'background': ['white', 'black'], 'dpi': ['300', '150'],
                }
                for name, values in choices.items():
                    control = getattr(dialog, name)
                    assert [control.itemData(i) for i in range(control.count())] == values
                dialog.grid.setCurrentIndex(2)  # Fixed grid simplifies the no-render Bash intercept.
                assert dialog.heading.maxLength() == 150 and dialog.heading.text() == 'Contact Sheet'
            elif kind == 'print':
                assert [dialog.preset.itemData(i) for i in range(7)] == list('1234567')
                assert dialog.preset.currentData() == '3'
            else:
                add_with_picker(dialog, str(gif))
                assert dialog.ordered.states[str(gif)][2]['frames'] == 2
                expected.append(str(gif))
                assert dialog.ordered.images.dragDropMode() == QAbstractItemView.InternalMove
            if kind != 'gallery':
                dialog.output.setText(str(root / 'missing' / 'bad'))
                dialog.accept()
                assert not settings.exists() and not dialog.create.isEnabled()
                suffix = '.tiff' if kind == 'tiffjoin' else '.pdf'
                dialog.output.setText(str(root / (kind + suffix)))
            values = approve(dialog, settings)
            offset = {'gallery': 7, 'contactsheet': 11, 'print': 2, 'tiffjoin': 1}[kind]
            assert values[offset:] == expected
            bash_handoff(root, kind, settings, paths[:1], expected)
            bash_handoff(root, kind, settings, paths[:1], expected, cancel=True)
            if kind in ('contactsheet', 'tiffjoin'):
                bash_handoff(root, kind, settings, expected, expected, cli=True)
            bad = root / (kind + '.invalid')
            bad_values = list(values)
            if kind == 'gallery':
                bad_values[6] = 'My Gallery'  # Occupied after approval: no silent renumber.
            else:
                bad_values[8 if kind == 'contactsheet' else 1 if kind == 'print' else 0] = str(root / 'missing' / 'invalid')
            bad.write_bytes(b''.join(os.fsencode(v) + b'\0' for v in bad_values))
            bash_handoff(root, kind, bad, paths[:1], expected, invalid=True)
            # Closing while header/thumbnail workers may still be active reaps them.
            cancelled = root / (kind + '.cancelled')
            original_argv = sys.argv
            closed = []
            def cancel_entry_point():
                dialog = QApplication.activeModalWidget()
                closed.append(dialog)
                dialog.reject()
            if kind == 'contactsheet':
                sys.argv = ['kim_contactsheet_dialog.py', str(cancelled), *paths]
                entry = __import__('kim_contactsheet_dialog').main
            else:
                sys.argv = ['kim_create_dialog.py', kind, str(cancelled), directory, str(len(paths)), *paths]
                entry = ui.main
            QTimer.singleShot(0, cancel_entry_point)
            try:
                assert entry() == 130
            finally:
                sys.argv = original_argv
            assert len(closed) == 1
            no_workers(closed[0])
            assert not cancelled.exists()
            print('PASS', kind, 'selection, approval, NUL handoff, cancellation and lifecycle')

        # Exercise Collage's unchanged entry point with its actual settings window.
        original_argv = sys.argv
        errors = []
        def close_collage():
            dialog = QApplication.activeModalWidget()
            try:
                assert dialog.windowTitle() == 'KIM6 — Create Collage'
            except BaseException as exc:
                errors.append(exc)
            dialog.reject()
        sys.argv = ['kim_collage_dialog.py', str(root / 'collage.approved'), paths[0]]
        QTimer.singleShot(0, close_collage)
        try:
            assert kim_collage_dialog.main() != 0
        finally:
            sys.argv = original_argv
        assert not errors and not (root / 'collage.approved').exists()
        assert not list(root.glob('*.pdf')) and not list(root.glob('*.tiff'))
        assert not list(root.rglob('index.html'))
        for path, digest in originals.items():
            assert hashlib.sha256(Path(path).read_bytes()).digest() == digest
        print('PASS collage terminology; originals unchanged; no rendered output')
    return 0


if __name__ == '__main__':
    sys.exit(main())
