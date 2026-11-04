#!/usr/bin/env python3
"""Focused offscreen UI/approval smoke check. Does not encode animations/video.

Run: QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 tests/qt_ordered_animation_smoke.py
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt, QModelIndex, QEvent, QEventLoop, QTimer
from PySide6.QtGui import QColor, QImage, QKeyEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QDialog

import kim_create_dialog as ui


def pump_until(predicate, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
    raise AssertionError(message)


def inspected(dialog):
    pump_until(lambda: dialog.ordered.worker is None and not dialog.ordered.counts()[2],
               'Source inspection did not settle')


def close(dialog):
    dialog.close()
    pump_until(lambda: dialog.ordered.worker is None and dialog.ordered.thumbnail_worker is None
               and not dialog.isVisible(), 'Dialog did not close cleanly')
    assert not dialog.ordered.thumbnail_timer.isActive()
    if isinstance(dialog, ui.AnimatedImageDialog):
        assert not dialog.preview_timer.isActive()


def read_values(path):
    data = path.read_bytes()
    assert data.endswith(b'\0')
    return [os.fsdecode(value) for value in data[:-1].split(b'\0')]


def bash_handoff(root, initial, approved, kind):
    """Exercise the real action's NUL read/revalidation, with rendering intercepted."""
    source = (ROOT / 'src/bin/kim_all').read_text()

    def function(name):
        start = source.index(name + '() {')
        return source[start:source.index('\n}\n', start) + 3]

    capture = root / ('bash-' + kind)
    harness = '\n'.join(function(name) for name in (
        'collect_publication_inputs', 'prepare_derived_target', 'action_animate'))
    harness += r'''
set -euo pipefail
KIMDIR="$1"; DISPATCHER_DIR="$2"; fixture="$3"; capture="$4"; shift 4
require_action_tools() { :; }
enable_psd_sources() { :; }
progress_error() { printf '%s\n' "$*" >&2; }
progress_open() { printf ref; }
progress_cancelled() { return 1; }
progress_close() { :; }
progress_begin_item() { :; }
publication_fail() { return 1; }
# Only the settings dialog is intercepted; collect_publication_inputs is real.
python3() { [ "$2" = animate ]; cp -- "$fixture" "$3"; }
publication_prepare_source() {
  printf '%s\0' "$2" >> "$capture.sources"
  printf 'PNG|32|24|1\n' > "$KIMDIR/publication-records"
}
tmp_for_target() { printf '%s/stage' "$KIMDIR"; }
image_has_apng_control_chunk() { return 1; }
identify() { printf '32|24|1'; }
publication_render_stage() {
  shift 2
  printf '%s\0' "$@" >> "$capture.commands"
  # Stop before GIF rendering or APNG encoding. APNG frame commands are recorded
  # without writing pixels, so the complete decoding order can be checked.
  if [ "$1" = ffmpeg ]; then return 1; fi
  local arg
  for arg in "$@"; do if [ "$arg" = -loop ]; then return 1; fi; done
  return 0
}
if action_animate -- "$@"; then exit 77; fi
'''
    result = subprocess.run(['bash', '-c', harness, 'smoke', str(root),
                             str(ROOT / 'src/bin'), str(approved), str(capture), *initial],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    expected = read_values(approved)[4:]
    assert read_values(Path(str(capture) + '.sources')) == expected
    commands = read_values(Path(str(capture) + '.commands'))
    if kind == 'gif':
        assert commands[:2] == ['magick', '--']
        assert commands[2:2 + len(expected)] == expected
    else:
        decoded = [commands[i + 2] for i, value in enumerate(commands)
                   if value == 'magick' and commands[i + 1] == '--'
                   and commands[i + 3] == '-auto-orient']
        assert decoded == expected
        assert 'ffmpeg' in commands


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='.kim6-ui-smoke-', dir=ROOT) as directory:
        root = Path(directory)
        paths = []
        for name, color in [('frame 10.png', 'red'), ('frame 2.jpg', 'green'), ('frame 1.png', 'blue')]:
            path = root / name
            image = QImage(32, 24, QImage.Format_RGB32)
            image.fill(QColor(color))
            assert image.save(str(path))
            paths.append(str(path))
        originals = {path: Path(path).read_bytes() for path in paths}
        animation_result = root / 'animation-settings'
        a = ui.AnimatedImageDialog(animation_result, directory, paths[:2])
        s = ui.SlideshowDialog(root / 'slideshow-settings', 3, '1280x720', 25, 'black', '', paths[:2])
        for dialog in (a, s):
            dialog.show()
            inspected(dialog)
            assert dialog.ordered.counts() == (2, 0, 0), dialog.ordered.states
            assert isinstance(dialog.ordered, ui.OrderedImages)
            widget = dialog.ordered
            assert widget.images.dragDropMode() == QAbstractItemView.InternalMove
            initial = widget.ordered_paths()
            widget.images.setCurrentRow(0)
            for event_type in (QEvent.KeyPress, QEvent.KeyRelease):
                app.sendEvent(widget.images, QKeyEvent(event_type, Qt.Key_Down, Qt.NoModifier))
            assert widget.images.currentRow() == 1  # keyboard selection
            widget.up_button.click()
            assert widget.ordered_paths() == initial[::-1]
            widget.down_button.click()
            assert widget.ordered_paths() == initial
            # Use the actual shared-picker caller; bypass only its modal user interaction.
            original_picker = ui.choose_images
            picker_calls = []
            def pick(*args, **kwargs):
                picker_calls.append(kwargs['title'])
                return [paths[2]]
            ui.choose_images = pick
            try:
                widget.add_button.click()
            finally:
                ui.choose_images = original_picker
            inspected(dialog)
            assert picker_calls and widget.ordered_paths() == [*initial, paths[2]]
            widget.images.setCurrentRow(1)
            widget.remove_button.click()
            assert widget.ordered_paths() == [initial[0], paths[2]]
            # The view's internal drag/drop uses this model move and rowsMoved.
            model = widget.images.model()
            assert model.moveRows(QModelIndex(), 1, 1, QModelIndex(), 0)
            assert widget.ordered_paths() == [paths[2], initial[0]]
            assert all(widget.images.item(i).toolTip().startswith(widget.ordered_paths()[i])
                       for i in range(widget.images.count()))

        # Sequence, decoded pixels, interval changes and controls.
        a.delay.setValue(600)  # deterministic manual ticks below, no wall-clock races
        pump_until(lambda: a.sequence[0] in a.ordered.thumbnails, 'First preview did not decode')
        assert not a.canvas.image.isNull()
        assert a.sequence == tuple(a.ordered_paths())
        a.play.click()
        assert a.preview_timer.isActive() and a.frame_index == 0
        a.advance_preview()
        assert a.frame_index == 1 and a.frame_position.text() == 'Frame 2 of 2'
        pump_until(lambda: a.sequence[1] in a.ordered.thumbnails, 'Second preview did not decode')
        a.show_frame()
        assert a.canvas.image == a.ordered.thumbnails[a.sequence[1]]
        a.pause.click()
        assert not a.preview_timer.isActive() and a.frame_index == 1
        a.play.click()
        assert a.frame_index == 1
        a.restart.click()
        assert a.frame_index == 0 and a.preview_timer.isActive()
        a.delay.setValue(7)
        assert a.preview_timer.interval() == 70
        a.delay.setValue(0)
        assert a.preview_timer.interval() == 20 and a.delay.value() == 0
        a.delay.setValue(600)
        a.loops.setValue(0)
        for _ in range(6):
            a.advance_preview()
        assert a.preview_timer.isActive() and a.completed_cycles == 3
        a.loops.setValue(2)
        a.restart.click()
        for _ in range(4):
            a.advance_preview()
        assert not a.preview_timer.isActive() and a.completed_cycles == 2 and a.frame_index == 1
        a.play.click()
        assert a.frame_index == 0 and a.completed_cycles == 0
        a.pause.click()
        a.loops.setValue(0)
        a.restart.click()
        index = a.frame_index
        a.format.setCurrentIndex(1)
        assert a.preview_timer.isActive() and a.frame_index == index
        assert a.format.currentData() == 'apng' and a.output.text().endswith('.png')
        a.delay.setValue(0)
        assert not a.create.isEnabled()
        a.accept()
        assert not animation_result.exists()
        a.delay.setValue(10)
        assert a.create.isEnabled()
        a.pause.click()
        # Approve APNG, then exercise the real Bash order handoff without encoders.
        approved_order = a.ordered_paths()
        a.create.click()
        pump_until(lambda: not a.isVisible(), 'Approval did not close dialog')
        assert a.result() == QDialog.Accepted
        assert read_values(animation_result) == ['apng', '10', '0', str(root / 'my_animation.png'), *approved_order]
        assert not a.preview_timer.isActive() and a.ordered.worker is None and a.ordered.thumbnail_worker is None
        bash_handoff(root, paths[:2], animation_result, 'apng')

        gif_result = root / 'gif-settings'
        gif = ui.AnimatedImageDialog(gif_result, directory, approved_order)
        gif.show()
        inspected(gif)
        gif.delay.setValue(0)
        assert gif.create.isEnabled()
        gif.create.click()
        pump_until(lambda: gif.ordered.thumbnail_worker is None and not gif.isVisible(), 'GIF approval close failed')
        assert read_values(gif_result)[4:] == approved_order
        bash_handoff(root, paths[:2], gif_result, 'gif')

        expected_slideshow = s.ordered_paths()
        assert s.create.isEnabled()
        s.create.click()
        pump_until(lambda: not s.isVisible(), 'Slideshow approval did not close')
        assert read_values(root / 'slideshow-settings')[5:] == expected_slideshow

        # One-image size, APNG count validation, and closing with active workers.
        one = ui.AnimatedImageDialog(root / 'cancelled', directory, paths[:1])
        one.show()
        inspected(one)
        assert one.ordered.images.height() == 91 and one.height() < 650, one.height()
        one.format.setCurrentIndex(1)
        assert not one.create.isEnabled()
        one.accept()
        assert not (root / 'cancelled').exists()
        one.play.click()
        close(one)
        small_slideshow = ui.SlideshowDialog(root / 'cancelled-slideshow', 3, '1280x720', 25, 'black', '', paths[:1])
        small_slideshow.show()
        assert small_slideshow.ordered.images.height() == 91 and small_slideshow.height() < 650
        close(small_slideshow)  # deliberately while inspection is active
        assert not (root / 'cancelled-slideshow').exists()

        # Removed/re-added paths must not receive results belonging to old rows.
        race = ui.AnimatedImageDialog(root / 'race-cancelled', directory, paths[:1])
        race.show()
        race.ordered.images.setCurrentRow(0)
        race.ordered.remove_button.click()
        race.ordered.add_paths(paths[:1])
        inspected(race)
        assert race.ordered.counts() == (1, 0, 0) and race.create.isEnabled()
        close(race)

        # A concatenated PPM is a real two-frame source, without an animation encoder.
        multi_path = root / 'two-frame.ppm'
        multi_path.write_bytes(b'P6\n1 1\n255\n\xff\x00\x00P6\n1 1\n255\n\x00\x00\xff')
        multi = ui.AnimatedImageDialog(root / 'multi-settings', directory, [str(multi_path)])
        multi.show()
        inspected(multi)
        assert multi.create.isEnabled() and multi.ordered.states[str(multi_path)][2]['frames'] == 2
        assert 'Multi-frame source' in multi.canvas.message and multi.frame_position.text() == 'Source 1 of 1'
        multi.format.setCurrentIndex(1)
        assert not multi.create.isEnabled() and multi.ordered.counts()[1] == 1
        multi.format.setCurrentIndex(0)
        assert multi.create.isEnabled()
        close(multi)

        # Publication safeguards: line breaks, links, decoder failure, source changes.
        newline_path = root / 'line\nbreak.png'
        newline_path.write_bytes(Path(paths[0]).read_bytes())
        invalid = ui.AnimatedImageDialog(root / 'invalid', directory, [str(newline_path)])
        invalid.show()
        inspected(invalid)
        assert invalid.ordered.counts() == (0, 1, 0) and not invalid.create.isEnabled()
        close(invalid)
        changed = ui.AnimatedImageDialog(root / 'changed', directory, paths[:1])
        changed.show()
        inspected(changed)
        changed.ordered.unavailable.add(paths[0])
        changed.ordered.thumbnails.clear()
        changed.show_frame()
        assert 'unavailable' in changed.canvas.message and changed.create.isEnabled()
        # Simulate a mismatched inspection identity without touching a source.
        changed.ordered.states[paths[0]][2]['stamp'] = []
        changed.accept()
        assert not changed.create.isEnabled() and not (root / 'changed').exists()
        close(changed)
        assert all(Path(path).read_bytes() == data for path, data in originals.items())
        assert not list(root.glob('*.gif')) and not list(root.glob('*.mp4'))
        assert not list(root.glob('my_animation*.png'))
        print('PASS: A–L shared ordering, preview, settings, safe ordered approval, APNG validation, clean shutdown and compact size.')
        print('PASS: actual Bash GIF/APNG approval handoff and source order; rendering intercepted, no GIF/APNG/MP4 encoded.')
    app.processEvents()


if __name__ == '__main__':
    main()
