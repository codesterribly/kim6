#!/usr/bin/env python3
"""Focused PSD notice/approval/report checks; no publication outputs are rendered.

QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 tests/qt_psd_advisories_smoke.py
"""
import contextlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

import kim_album_dialog as album
import kim_collage_dialog as collage
import kim_create_dialog as ui
from kim_contactsheet_dialog import ContactSheetDialog
import kim_job as job
from kim_photo_selection import ImagePicker
from kim_psd_source import WARNING
from kim_process import DIGEST_WARNING, record_warnings
import kim_source_advisories as advisory


def pump(predicate):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
    raise AssertionError('Qt did not settle')


def close(dialog):
    dialog.reject()
    pump(lambda: dialog.ordered.worker is None and dialog.ordered.thumbnail_worker is None)
    assert not dialog.isVisible()


def psd(path):
    # A real tiny raw RGB composite, with no resources or layer data.
    path.write_bytes(b'8BPS' + struct.pack('>H', 1) + b'\0' * 6
                     + struct.pack('>HIIHH', 3, 2, 2, 8, 3)
                     + b'\0' * 12 + struct.pack('>H', 0) + bytes(range(12)))


def values(path):
    data = path.read_bytes()
    assert data.endswith(b'\0')
    return [os.fsdecode(value) for value in data[:-1].split(b'\0')]


def warnings(cache, records):
    (cache / 'warnings.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in records))


def result(cache, status='success', outputs=None):
    capture = io.StringIO()
    with contextlib.redirect_stderr(capture):
        job.publication_result(cache, 'Gallery', ['/tmp/result'] if outputs is None else outputs,
                               status, graphical=False)
    return capture.getvalue()


def filtering(root, sources):
    cache = root / 'filter-job'; cache.mkdir()
    with patch.dict(os.environ, KIM_SOURCE_ADVISORY_DIR=str(cache), KIM_PSD_CACHE=str(cache)):
        records = advisory.source_advisories(sources)
        assert len(records) == 2
        advisory.acknowledge_advisories(records[:1])
        # Actual collector retains the complete processing-time fingerprint.
        record_warnings(cache, sources[0], records[0]['identity'], [WARNING])
        saved = (cache / 'warnings.jsonl').read_bytes()
        assert job.shell_warning_rows(cache)[0].identity == records[0]['identity']
        assert result(cache) == ''
        with patch.object(job, 'completion_dialog') as completion:
            job.publication_result(cache, 'Gallery', ['/tmp/result'], 'success', graphical=True)
            completion.assert_not_called()
        assert (cache / 'warnings.jsonl').read_bytes() == saved
        new = [DIGEST_WARNING, 'IPTCDigest staging diagnostic: new metadata notice',
               'ICC profile could not be interpreted', 'Unexpected metadata notice',
               'Unknown warning', 'PSD compatibility: unexpected reconstruction diagnostic']
        for diagnostic in new:
            warnings(cache, [records[0], dict(records[0], warning=diagnostic)])
            report = result(cache)
            assert diagnostic in report and str(sources[0]) in report
            assert WARNING not in report
        # Keep the existing compact graphical report for genuinely new diagnostics.
        with patch.object(QApplication, 'exec', return_value=0):
            dialog = job.publication_result(cache, 'Gallery', ['/tmp/result'], 'success', graphical=True)
        assert 'unexpected reconstruction' in dialog.details.toPlainText()
        assert not dialog.details.isVisible()
        assert '/tmp/result' in dialog.saved_label.text()
        dialog.close()
        warnings(cache, records)
        report = result(cache)
        assert str(sources[1]) in report and str(sources[0]) not in report
        for status in ('failed', 'cancelled'):
            with patch.object(job, 'completion_dialog') as completion:
                report = result(cache, status)
                completion.assert_not_called()
            assert WARNING in report and str(sources[0]) in report
            assert 'Saved results retained' in report
        assert WARNING in result(cache, outputs=[])
        advisory.acknowledge_advisories(records)
        assert result(cache) == ''
        # Same path, inode and size, even with mtime restored: ctime invalidates approval.
        before = sources[0].stat()
        data = sources[0].read_bytes()
        sources[0].write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        os.utime(sources[0], ns=(before.st_atime_ns, before.st_mtime_ns))
        assert advisory.source_identity(sources[0]) != records[0]['identity']
        report = result(cache)
        assert str(sources[0]) in report and str(sources[1]) not in report
        # Even a fresh processing fingerprint cannot match an older approval.
        fresh = advisory.source_advisories(sources)[0]
        warnings(cache, [fresh])
        assert WARNING in result(cache)
        for text in ('{broken', '{}', '[{"identity":[]}]'):
            (cache / advisory.ACKNOWLEDGMENTS).write_text(text)
            assert WARNING in result(cache)
        (cache / advisory.ACKNOWLEDGMENTS).unlink()
        assert WARNING in result(cache)
        advisory.acknowledge_advisories([fresh])
        warnings(cache, [dict(fresh, identity=fresh['identity'][:2])])
        assert WARNING in result(cache)  # Older/partial diagnostic records fail open.
        sources[0].write_bytes(data)
    print('PASS J–O: exact warning filtering, current identity, independent sources, failures/cancellation')


def preflight(root, jpg, png, first, second):
    renamed = root / 'renamed.jpeg'; renamed.write_bytes(first.read_bytes())
    fake = root / 'ordinary.psd'; fake.write_bytes(jpg.read_bytes())
    malformed = root / 'malformed.psd'; malformed.write_bytes(b'8BPS')
    cache = {}
    with patch('subprocess.Popen', side_effect=AssertionError('Preflight must not run tools')):
        with patch.object(advisory, 'header', wraps=advisory.header) as header:
            assert advisory.source_advisories([jpg, png, fake, malformed], cache) == []
            records = advisory.source_advisories([jpg, png, first, renamed], cache)
            assert [r['source'] for r in records] == list(map(str, [first, renamed]))
            count = header.call_count
            assert advisory.source_advisories([jpg, png, first, renamed], cache) == records
            assert header.call_count == count
    notice = ui.SourceAdvisoryNotice()
    notice.set_sources([jpg]); assert notice.isHidden()
    notice.set_sources([jpg, png, first]); assert not notice.isHidden()
    assert 'Photoshop image (PSD)' in notice.text() and first.name in notice.toolTip()
    notice.set_sources([first, second]); assert '2 Photoshop files' in notice.text()
    assert first.name in notice.accessibleDescription() and second.name in notice.toolTip()
    notice.set_sources([jpg, png]); assert notice.isHidden()
    notice.set_sources([renamed]); assert not notice.isHidden()
    notice.set_sources([fake]); assert notice.isHidden()
    # A newly added identity cannot be approved before its notice is displayed.
    assert not notice.approve([first])
    assert 'Photoshop image' in notice.text()
    print('PASS A–G: header detection, mixed inputs, count/removal, renamed PSD, false suffix, cached preflight')


def shell_staging(root, selected):
    source = (ROOT / 'src/bin/kim_all').read_text()
    def function(name):
        start = source.index(name + '() {')
        return source[start:source.index('\n}\n', start) + 3]
    harness = '\n'.join(function(name) for name in
                        ('is_psd_source', 'enable_psd_sources', 'collect_publication_inputs'))
    harness += '''
set -euo pipefail
KIMDIR="$1"; DISPATCHER_DIR="$2"; shift 2
require_action_tools() { :; }
for cmd in gallery contactsheet print tiffjoin animate slideshow album collage; do
  unset KIM_PSD_CACHE
  files=()
  collect_publication_inputs files "$@"
  [ "$KIM_PSD_CACHE" = "$KIMDIR/psd" ]
  [ "${files[0]}" = "$1" ]
done
'''
    subprocess.run(['bash', '-c', harness, 'check', str(root), str(ROOT / 'src/bin'), *selected],
                   check=True, capture_output=True)


def ordered_dialogs(root, jpg, png, first, second):
    factories = [
        ('Gallery', lambda settings: ui.GalleryDialog(settings, str(root), [str(jpg)]), 7),
        ('Contact Sheet', lambda settings: ContactSheetDialog(settings, [str(jpg)]), 11),
        ('Print', lambda settings: ui.PrintLayoutDialog(settings, str(root), [str(jpg)]), 2),
        ('TIFF', lambda settings: ui.TiffJoinDialog(settings, str(root), [str(jpg)]), 1),
        ('Animation', lambda settings: ui.AnimatedImageDialog(settings, str(root), [str(jpg)]), 4),
    ]
    for index, (name, factory, offset) in enumerate(factories):
        cache = root / ('ordered-job-' + str(index))
        settings = root / ('settings-' + str(index))
        with patch.dict(os.environ, KIM_SOURCE_ADVISORY_DIR=str(cache)):
            cancelled = factory(settings)
            cancelled.show()
            assert cancelled.source_notice.isHidden()
            cancelled.ordered.add_paths([str(first)])
            assert not cancelled.source_notice.isHidden()
            close(cancelled)
            assert not (cache / advisory.ACKNOWLEDGMENTS).exists()
            dialog = factory(settings); dialog.show()
            pump(lambda: dialog.ordered.worker is None and not dialog.ordered.counts()[2])
            errors = []
            def pick():
                try:
                    picker = QApplication.activeModalWidget()
                    assert isinstance(picker, ImagePicker)
                    assert str(first) in picker.image_items
                    picker.image_items[str(first)].setSelected(True)
                    picker.add_button.click()
                except BaseException as exc:
                    errors.append(exc)
                    QApplication.activeModalWidget().reject()
            QTimer.singleShot(0, pick)
            dialog.ordered.add_button.click()
            assert not errors, errors
            assert first.name in dialog.source_notice.toolTip()
            dialog.ordered.add_paths([str(png), str(second)])
            assert '2 Photoshop files' in dialog.source_notice.text()
            dialog.ordered.images.clearSelection()
            dialog.ordered.items[str(first)].setSelected(True)
            dialog.ordered.remove_button.click()
            assert second.name in dialog.source_notice.toolTip()
            assert first.name not in dialog.source_notice.toolTip()
            pump(lambda: dialog.ordered.worker is None and not dialog.ordered.counts()[2])
            assert dialog.create.isEnabled(), getattr(dialog, 'status', dialog.summary if hasattr(dialog, 'summary') else None).text()
            dialog.layout().activate()
            assert dialog.source_notice.y() < dialog.create.parentWidget().y()
            assert dialog.width() <= 1000 and dialog.height() <= 1000, (name, dialog.size())
            approved = dialog.ordered.ordered_paths()
            dialog.create.click()
            pump(lambda: dialog.ordered.worker is None and dialog.ordered.thumbnail_worker is None
                 and not dialog.isVisible())
            records = json.loads((cache / advisory.ACKNOWLEDGMENTS).read_text())
            assert records == advisory.source_advisories([second])
            assert values(settings)[offset:] == approved
            shell_staging(root, values(settings)[offset:])
        print('PASS H/I/P/Q:', name, 'notice, real picker, final order/approval, staging, compact geometry')
    # Slideshow retains its existing source eligibility; the shared notice still works.
    cache = root / 'slideshow-job'
    with patch.dict(os.environ, KIM_SOURCE_ADVISORY_DIR=str(cache)):
        d = ui.SlideshowDialog(root / 'slideshow-settings', 3, '1920x1080', 25, 'black', '', [str(jpg)])
        d.show()
        d.ordered.add_paths([str(first)])
        assert first.name in d.source_notice.toolTip()
        close(d)
        assert not (cache / advisory.ACKNOWLEDGMENTS).exists()
    print('PASS: Slideshow shared notice and cancellation; existing eligibility preserved')


def fixed_dialogs(root, jpg, first, app):
    for module in (album, collage):
        for cancel in (True, False):
            cache = root / (module.__name__ + str(cancel)); settings = root / (cache.name + '-settings')
            errors = []
            def click():
                try:
                    dialog = QApplication.activeModalWidget()
                    notice = dialog.findChild(ui.SourceAdvisoryNotice)
                    assert notice is not None and first.name in notice.toolTip()
                    assert not notice.isHidden()
                    buttons = dialog.findChild(QDialogButtonBox)
                    assert notice.y() < buttons.y()
                    if cancel:
                        dialog.reject()
                    else:
                        buttons.button(QDialogButtonBox.Ok).click()
                except BaseException as exc:
                    errors.append(exc)
                    QApplication.activeModalWidget().reject()
            with patch.dict(os.environ, KIM_SOURCE_ADVISORY_DIR=str(cache)), \
                 patch.object(sys, 'argv', ['dialog', str(settings), str(jpg), str(first)]), \
                 patch.object(module, 'QApplication', return_value=app) if module is album else contextlib.nullcontext():
                QTimer.singleShot(0, click)
                code = module.main()
            assert not errors, errors
            if cancel:
                assert code != 0 and not (cache / advisory.ACKNOWLEDGMENTS).exists()
            else:
                assert code == 0 and settings.exists()
                assert json.loads((cache / advisory.ACKNOWLEDGMENTS).read_text()) == advisory.source_advisories([first])
        print('PASS H/I/Q:', module.__name__, 'shared notice, Create and cancellation')


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='kim6-advisories-') as directory:
        root = Path(directory)
        jpg, png = root / 'photo.jpg', root / 'photo.png'
        image = QImage(4, 3, QImage.Format_RGB32); image.fill(0x123456)
        assert image.save(str(jpg)) and image.save(str(png))
        first, second = root / 'first source.psd', root / 'second source.psd'
        psd(first); psd(second)
        originals = {p: p.read_bytes() for p in (jpg, png, first, second)}
        preflight(root, jpg, png, first, second)
        filtering(root, [first, second])
        ordered_dialogs(root, jpg, png, first, second)
        fixed_dialogs(root, jpg, first, app)
        assert all(p.read_bytes() == content for p, content in originals.items())
    print('PASS: focused PSD advisory checks; no HTML/PDF/TIFF/video/animation publication rendering')


if __name__ == '__main__':
    main()
