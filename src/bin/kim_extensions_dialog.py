"""Content-based extension inspection. Bash owns planning, staging and publication."""
import os
from pathlib import Path
import stat
import sys

from kim_annotations import identity, read_tags
from kim_psd_source import inspection_context
from kim_ui import tr

# Deliberately distinguish JPEG 2000 containers from raw codestreams. Generic
# HEIF content is accepted under either established HEIF/HEIC image suffix.
FORMATS = {
    'JPEG': ('JPEG', ('jpg', 'jpeg', 'jpe', 'jfif')),
    'PNG': ('PNG', ('png', 'apng')),
    'WEBP': ('WebP', ('webp',)), 'Extended WEBP': ('WebP', ('webp',)),
    'AVIF': ('AVIF', ('avif',)),
    'HEIC': ('HEIC/HEIF', ('heic', 'heif')), 'HEIF': ('HEIC/HEIF', ('heif', 'heic')),
    'GIF': ('GIF', ('gif',)), 'TIFF': ('TIFF', ('tif', 'tiff')),
    'BMP': ('BMP', ('bmp', 'dib')), 'PSD': ('PSD', ('psd',)),
    'JP2': ('JPEG 2000', ('jp2',)), 'JPC': ('JPEG 2000 codestream', ('j2k', 'j2c', 'jpc')),
    'J2C': ('JPEG 2000 codestream', ('j2k', 'j2c', 'jpc')),
    'J2K': ('JPEG 2000 codestream', ('j2k', 'j2c', 'jpc')),
    'JXL': ('JPEG XL', ('jxl',)),
}
IMAGE_SUFFIXES = {ext for _, extensions in FORMATS.values() for ext in extensions}


def source_stamp(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError(tr('Select an ordinary file with no symlinks or hardlink aliases'))
    return ':'.join(map(str, identity(info)))


def inspect_file(path):
    suffix = Path(path).suffix.lstrip('.').lower()
    row = dict(path=path, format='', extension=suffix, suggested='', status='', stamp='')
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode): raise ValueError(tr('Select a regular file without a symlink'))
        stamp = ':'.join(map(str, identity(info)))
        data, inspected, rc = read_tags(path, ('FileType', 'MajorBrand', 'CompatibleBrands'), numeric=True)
        if stamp != ':'.join(map(str, inspected)): raise ValueError(tr('Source changed during inspection'))
        kind = data.get('File:FileType', '')
        brands = {str(data.get('QuickTime:MajorBrand', ''))}
        compatible = data.get('QuickTime:CompatibleBrands', [])
        brands.update(compatible if isinstance(compatible, list) else str(compatible).split())
        if kind in ('HEIF', 'HEIC') and brands.intersection(('avif', 'avis')): kind = 'AVIF'
        recognized = FORMATS.get(kind)
        # Generic HEIF brands establish the container, but not its codec. Do
        # not recommend HEVC suffixes for an ambiguous AV1/generic container.
        if kind == 'HEIF' and not brands.intersection(('heic', 'heix', 'hevc', 'hevx')):
            recognized = None
        error = str(data.get('ExifTool:Error', ''))
        if rc and not kind and error and 'Unknown file type' not in error and 'File is empty' not in error:
            raise ValueError(error)
        if recognized:
            row['format'], extensions = recognized
            row['suggested'] = extensions[0] if suffix not in extensions else suffix
            row['status'] = tr('Correct') if suffix in extensions else tr('Extension mismatch')
            row['stamp'] = stamp
            row['mismatch'] = suffix not in extensions
        elif rc and not kind:
            # ExifTool uses an error for unrecognized content too. That is an
            # unknown format, not proof that an image is damaged.
            row['status'] = tr('Unknown or unsupported format')
        else:
            row['format'] = str(kind)
            row['status'] = tr('Unknown or unsupported format')
    except Exception as exc:
        row['status'] = tr('Inspection failure')
        row['detail'] = str(exc)
    return row


def verify_copy(source, stage, expected):
    """Check both byte streams using descriptors, retaining source identity."""
    if source_stamp(source) != expected: raise ValueError(tr('Selected source changed'))
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stage_fd = None
    try:
        stage_fd = os.open(stage, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(source_fd); output = os.fstat(stage_fd)
        if ':'.join(map(str, identity(before))) != expected: raise ValueError(tr('Selected source changed'))
        if not stat.S_ISREG(output.st_mode) or output.st_nlink != 1:
            raise ValueError(tr('Unsafe staged copy'))
        if (before.st_dev, before.st_ino) == (output.st_dev, output.st_ino): raise ValueError(tr('Copy aliases source'))
        while True:
            from kim_psd_source import checkpoint
            checkpoint()
            block = os.read(source_fd, 1024 * 1024)
            if block != os.read(stage_fd, 1024 * 1024): raise ValueError(tr('Copied bytes differ'))
            if not block: break
        if identity(before) != identity(os.fstat(source_fd)) or source_stamp(source) != expected:
            raise ValueError(tr('Selected source changed'))
        if identity(output) != identity(os.fstat(stage_fd)) or identity(output) != identity(os.lstat(stage)):
            raise ValueError(tr('Staged copy changed'))
        os.chmod(stage_fd, stat.S_IMODE(before.st_mode))
        # cp already preserved the pre-copy access/modify timestamps. Byte
        # verification may advance atime, so restore those staged timestamps.
        os.utime(stage_fd, ns=(output.st_atime_ns, output.st_mtime_ns))
    finally:
        if stage_fd is not None: os.close(stage_fd)
        os.close(source_fd)


def run_dialog(result_file, inputs):
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
        QAbstractItemView, QFileDialog)

    class Scan(QThread):
        found = Signal(object)
        notice = Signal(str)

        def __init__(self, paths, parent):
            super().__init__(parent); self.paths = paths; self.error = None

        def run(self):
            seen = set()
            try:
                with inspection_context(cancelled=self.isInterruptionRequested):
                    for raw in self.paths:
                        if self.isInterruptionRequested(): break
                        raw = os.path.abspath(raw)
                        if os.path.isdir(raw) and not os.path.islink(raw):
                            with os.scandir(raw) as entries:
                                for entry in entries:
                                    if self.isInterruptionRequested(): break
                                    # Never traverse a directory or a directory symlink.
                                    if entry.is_dir(follow_symlinks=False) or entry.is_symlink(): continue
                                    if not entry.is_file(follow_symlinks=False): continue
                                    self.examine(entry.path, True, seen)
                        else:
                            self.examine(raw, False, seen)
            except Exception as exc:
                self.error = tr('Inspection failure') + ': ' + str(exc)
                self.notice.emit(self.error)

        def examine(self, path, folder, seen):
            if path in seen: return
            seen.add(path)
            row = inspect_file(path)
            if self.isInterruptionRequested(): return
            if not folder or row['stamp'] or row['extension'] in IMAGE_SUFFIXES:
                self.found.emit(row)

    class Inspector(QDialog):
        def __init__(self):
            super().__init__(); self.worker = None; self.rows = []; self.closing = False
            self.setWindowTitle(tr('KIM6 — Check & Correct Extensions')); self.resize(960, 540)
            layout = QVBoxLayout(self)
            self.note = QLabel(tr('Read-only inspection. Unknown format does not mean corrupt. Folder scans are nonrecursive.'))
            self.note.setWordWrap(True); layout.addWidget(self.note)
            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels([tr('Filename'), tr('Detected Format'), tr('Current Extension'),
                                                  tr('Suggested Extension'), tr('Status')])
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self.table)
            actions = QHBoxLayout(); layout.addLayout(actions)
            self.folder = QPushButton(tr('Choose Folder…')); self.folder.clicked.connect(self.choose_folder)
            self.stop = QPushButton(tr('Cancel Scan')); self.stop.setEnabled(False)
            self.stop.clicked.connect(self.cancel_scan)
            self.copy = QPushButton(tr('Create Correctly Named Copies')); self.copy.setEnabled(False)
            self.copy.clicked.connect(self.create)
            close = QPushButton(tr('Close')); close.clicked.connect(self.reject)
            for button in (self.folder, self.stop, self.copy, close): actions.addWidget(button)
            if inputs: self.start(inputs)
            else: self.note.setText(tr('Select a folder to inspect. No originals will be changed.'))

        def choose_folder(self):
            path = QFileDialog.getExistingDirectory(self, tr('Choose Folder'), options=
                                                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
            if path: self.start([path])

        def start(self, paths):
            self.table.setRowCount(0); self.rows = []
            self.folder.setEnabled(False); self.copy.setEnabled(False); self.stop.setEnabled(True)
            self.note.setText(tr('Inspecting file content…'))
            self.worker = Scan(paths, self)
            self.worker.found.connect(self.add_row); self.worker.notice.connect(self.note.setText)
            self.worker.finished.connect(self.scan_finished); self.worker.start()

        def add_row(self, row):
            self.rows.append(row); index = self.table.rowCount(); self.table.insertRow(index)
            values = [Path(row['path']).name, row['format'],
                      '.' + row['extension'] if row['extension'] else '',
                      '.' + row['suggested'] if row['suggested'] else '', row['status']]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value); item.setToolTip(row['path'] + '\n' + row.get('detail', ''))
                self.table.setItem(index, column, item)

        def cancel_scan(self):
            if self.worker: self.worker.requestInterruption(); self.stop.setEnabled(False)

        def scan_finished(self):
            worker, self.worker = self.worker, None
            stopped = worker.isInterruptionRequested(); worker.deleteLater()
            if self.closing: super().reject(); return
            self.note.setText(tr('Scan cancelled. Showing inspected files only.') if stopped else
                              worker.error or tr('Inspection finished. Originals are unchanged.'))
            self.folder.setEnabled(True); self.stop.setEnabled(False)
            self.copy.setEnabled(any(row.get('mismatch') for row in self.rows))

        def create(self):
            # Private NUL protocol, not a report or executable command stream.
            with open(result_file, 'wb') as stream:
                for row in self.rows:
                    if row.get('mismatch'):
                        for field in ('path', 'suggested', 'stamp'):
                            stream.write(os.fsencode(row[field]) + b'\0')
            self.accept()

        def reject(self):
            if self.worker:
                self.closing = True; self.worker.requestInterruption(); self.copy.setEnabled(False)
            else: super().reject()

        def closeEvent(self, event):
            if self.worker: self.reject(); event.ignore()
            else: event.accept()

    app = QApplication(sys.argv[:1]); dialog = Inspector()
    return 0 if dialog.exec() == QDialog.Accepted else 1


def confirm_plan(path):
    from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QLabel,
        QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox, QAbstractItemView)
    fields = [os.fsdecode(field) for field in Path(path).read_bytes().split(b'\0')[:-1]]
    app = QApplication(sys.argv[:1]); dialog = QDialog(); dialog.resize(900, 440)
    dialog.setWindowTitle(tr('Create Correctly Named Copies'))
    layout = QVBoxLayout(dialog)
    note = QLabel(tr('Review every destination. Originals will be kept. Existing destinations will never be replaced; a changed or occupied destination will fail safely.'))
    note.setWordWrap(True); layout.addWidget(note)
    table = QTableWidget(len(fields)//3, 2)
    table.setHorizontalHeaderLabels([tr('Source'), tr('Planned destination')])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for row in range(len(fields)//3):
        for column in range(2): table.setItem(row, column, QTableWidgetItem(fields[row*3+column]))
    layout.addWidget(table)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText(tr('Create Copies'))
    buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    return 0 if dialog.exec() == QDialog.Accepted else 1


def main():
    if sys.argv[1:2] == ['--stamp']:
        print(source_stamp(sys.argv[2])); return 0
    if sys.argv[1:2] == ['--verify']:
        verify_copy(*sys.argv[2:]); return 0
    if sys.argv[1:2] == ['--confirm']: return confirm_plan(sys.argv[2])
    return run_dialog(sys.argv[1], sys.argv[2:])


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr); raise SystemExit(1)
