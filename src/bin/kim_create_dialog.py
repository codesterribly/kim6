#!/usr/bin/env python3
"""KIM6 graphical creation settings and shared ordered image selection.

The dialogs collect approved source order and creation settings. The Bash
dispatcher retains responsibility for source validation, rendering, safe staging,
collision handling and publication.
"""

import os
import sys
from pathlib import Path
import re
import struct
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QRectF, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPalette, QBrush, QImage, QPainter
from kim_photo_selection import (
    choose_images, CREATE_IMAGE_EXTENSIONS, ThumbnailWorker, ImageCanvas,
)
from kim_preview import identity, inspection_path
from kim_location import descriptor_identity

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)



SLIDESHOW_EXTENSIONS = {
    'jpg', 'jpeg', 'jpe', 'png', 'webp', 'avif',
    'heic', 'heif', 'hif', 'tif', 'tiff',
    'bmp', 'gif', 'jp2', 'j2k', 'jpf', 'jxl',
}

SLIDESHOW_CODERS = {
    'JPEG', 'PNG', 'WEBP', 'AVIF', 'HEIC',
    'HEIF', 'TIFF', 'BMP', 'GIF', 'JP2', 'JXL',
}


class ImageSourceInspector(QThread):
    """Read source headers off the GUI thread; publication revalidates them."""

    inspected = Signal(str, str, str, object)

    def __init__(self, paths, parent, mode):
        super().__init__(parent)
        self.paths = list(paths)
        self.mode = mode

    def run(self):
        from kim_process import inspection_context, run_process, checkpoint

        with inspection_context(cancelled=self.isInterruptionRequested):
            for path in self.paths:
                if self.isInterruptionRequested():
                    break
                try:
                    if '\n' in path or '\r' in path:
                        raise ValueError('KIM6 publication does not support paths containing line breaks')
                    if (self.mode == 'slideshow'
                            and Path(path).suffix.lower().lstrip('.') not in SLIDESHOW_EXTENSIONS):
                        raise ValueError('Unsupported format; remove this image')
                    before = identity(path)
                    animated_png = False
                    with inspection_path(path) as (_, fd):
                        if descriptor_identity(fd) != before:
                            raise ValueError('Source changed while opening inspection')
                        # The child inherits this descriptor: seek must reset its
                        # OS offset, rather than just a Python input buffer.
                        with os.fdopen(os.dup(fd), 'rb', buffering=0) as stream:
                            # Some ImageMagick PNG readers report only the default
                            # APNG image. Match Bash's pre-IDAT acTL safeguard.
                            signature = stream.read(8)
                            psd_composite = self.mode == 'animation' and signature.startswith(b'8BPS')
                            if signature == b'\x89PNG\r\n\x1a\n':
                                length = os.fstat(fd).st_size
                                while stream.tell() + 12 <= length:
                                    checkpoint()
                                    size, tag = struct.unpack('>I4s', stream.read(8))
                                    if size + 4 > length - stream.tell():
                                        break
                                    if tag == b'acTL' and size == 8:
                                        animated_png = True
                                        break
                                    if tag in (b'IDAT', b'IEND'):
                                        break
                                    stream.seek(size + 4, 1)
                            stream.seek(0)
                            result = run_process(
                                ['identify', *(['-regard-warnings', '+ping']
                                              if self.mode == 'slideshow' else ['-ping']),
                                 '-format', '%m|%w|%h|%n|%[orientation]\n',
                                 # The existing Bash PSD adapter uses its saved composite.
                                 'psd:-[0]' if psd_composite else '-'],
                                text=True, stdin=stream, timeout=30,
                            )
                    if result.returncode:
                        raise ValueError('ImageMagick could not inspect this image')
                    records = [line.split('|') for line in result.stdout.splitlines()]
                    if not records or any(
                        len(row) != 5 or not re.fullmatch(r'[A-Za-z0-9]+', row[0])
                        or any(not value.isdigit() or int(value) < 1 for value in row[1:4])
                        for row in records
                    ):
                        raise ValueError('Invalid image dimensions or frame headers')
                    if self.mode == 'slideshow' and (
                        len(records) != 1 or records[0][3] != '1'
                        or records[0][0] not in SLIDESHOW_CODERS
                    ):
                        raise ValueError('Unsupported encoding or multiple frames')
                    if identity(path) != before:
                        raise ValueError('Source changed during inspection')
                    geometry = [(int(row[2]), int(row[1]))
                                if row[4] in ('LeftTop', 'RightTop', 'RightBottom', 'LeftBottom')
                                else (int(row[1]), int(row[2])) for row in records]
                    details = dict(stamp=before, frames=len(records),
                                   width=max(w for w, _ in geometry),
                                   height=max(h for _, h in geometry),
                                   animated_png=animated_png)
                    note = 'Ready for rendering validation'
                    if len(records) > 1 or animated_png:
                        note += '; multi-frame source — preview unavailable'
                    if not self.isInterruptionRequested():
                        self.inspected.emit(path, 'Ready', note, details)
                except Exception as exc:
                    if not self.isInterruptionRequested():
                        self.inspected.emit(path, 'Blocked', str(exc), None)


class SourceAdvisoryNotice(QLabel):
    """Compact shared preflight notice; filenames are available by hover or focus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []
        self.cache = {}
        self.setWordWrap(True)
        self.setTextFormat(Qt.PlainText)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Source compatibility notice')
        self.hide()

    def set_sources(self, paths):
        from kim_source_advisories import source_advisories
        self.records = source_advisories(paths, self.cache)
        count = len(self.records)
        if count == 1:
            text = ('Photoshop image (PSD): KIM6 uses the saved composite or a best-effort '
                    'reconstruction. Layers, masks, text, effects and adjustments may look '
                    'different in the output.')
        elif count:
            text = (f'{count} Photoshop files: saved composites or best-effort reconstruction '
                    'will be used. Layers, masks, text, effects and adjustments may look different.')
        else:
            text = ''
        names = '\n'.join(Path(record['source']).name for record in self.records)
        self.setText(text)
        self.setToolTip(names)
        self.setAccessibleDescription(names)
        self.setVisible(bool(count))

    def approve(self, paths):
        from kim_source_advisories import acknowledge_advisories
        disclosed = self.records
        self.set_sources(paths)
        if self.records != disclosed:
            # A new identity must be shown before it can be approved.
            return False
        acknowledge_advisories(self.records)
        return True


class OrderedImages(QWidget):
    """One ordered selection with inspection and bounded asynchronous thumbnails.

    ordered_paths() is always display order. Pixel storage is capped at 64 small
    images; only visible rows and the requested preview source are decoded.
    """

    changed = Signal()
    resized = Signal()
    idle = Signal()
    thumbnail_changed = Signal(str)

    def __init__(self, parent=None, *, mode='slideshow'):
        super().__init__(parent)
        self.mode = mode
        self.max_images = 200 if mode == 'slideshow' else None
        self.states = {}
        self.items = {}
        self.thumbnails = OrderedDict()
        self.unavailable = set()
        self.worker = None
        self.thumbnail_worker = None
        self.stopped = False
        self.preview_path = ''
        self.animation_format = 'gif'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        self.add_button = QPushButton('Add Images…')
        self.remove_button = QPushButton('Remove Selected')
        self.up_button = QPushButton('Move Up')
        self.down_button = QPushButton('Move Down')
        for button in (self.add_button, self.remove_button, self.up_button, self.down_button):
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.images = QListWidget()
        self.images.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.images.setDragDropMode(QAbstractItemView.InternalMove)
        self.images.setDefaultDropAction(Qt.MoveAction)
        self.images.setIconSize(QSize(96, 70))
        self.images.setAlternatingRowColors(True)
        self.images.setUniformItemSizes(True)
        self.images.setAccessibleName('Images in playback order')
        layout.addWidget(self.images)
        self.add_button.clicked.connect(self.choose_images)
        self.remove_button.clicked.connect(self.remove_images)
        self.up_button.clicked.connect(lambda: self.move_image(-1))
        self.down_button.clicked.connect(lambda: self.move_image(1))
        self.images.itemSelectionChanged.connect(self.update_controls)
        self.images.model().rowsMoved.connect(self.refresh_items)
        self.images.verticalScrollBar().valueChanged.connect(self.queue_thumbnails)
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.setInterval(30)
        self.thumbnail_timer.timeout.connect(self.load_thumbnails)
        self.resize_image_list()
        self.update_controls()

    def ordered_paths(self):
        return [self.images.item(i).data(Qt.UserRole) for i in range(self.images.count())]

    def add_paths(self, paths):
        for input_path in paths:
            # Resolve parent aliases, leaving the final entry for no-follow checks.
            path = Path(os.path.abspath(os.fspath(input_path)))
            path = str(path.parent.resolve() / path.name)
            if path in self.items:
                continue
            if self.max_images is not None and self.images.count() >= self.max_images:
                break
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setSizeHint(QSize(100, 77))
            self.images.addItem(item)
            self.items[path] = item
            self.states[path] = ('Inspecting', 'Checking image format', None)
        self.resize_image_list()
        self.refresh_items()
        self.start_inspection()

    def choose_images(self):
        paths = self.ordered_paths()
        initial = str(Path(paths[0]).parent) if paths else str(Path.home())
        paths = choose_images(
            self, initial,
            title='Add Images for ' + ('Video Slideshow' if self.mode == 'slideshow' else 'Animated Image'),
            extensions=SLIDESHOW_EXTENSIONS if self.mode == 'slideshow' else CREATE_IMAGE_EXTENSIONS,
        )
        if paths:
            self.add_paths(paths)

    def remove_images(self):
        for item in self.images.selectedItems():
            path = item.data(Qt.UserRole)
            self.images.takeItem(self.images.row(item))
            self.items.pop(path, None)
            self.states.pop(path, None)
            self.thumbnails.pop(path, None)
            self.unavailable.discard(path)
        self.resize_image_list()
        self.refresh_items()

    def move_image(self, direction):
        selected = self.images.selectedItems()
        if len(selected) != 1:
            return
        row = self.images.row(selected[0])
        destination = row + direction
        if 0 <= destination < self.images.count():
            item = self.images.takeItem(row)
            self.images.insertItem(destination, item)
            self.images.setCurrentRow(destination)
            self.refresh_items()

    def resize_image_list(self):
        self.images.setFixedHeight(12 + min(4, max(1, self.images.count())) * 79)
        self.resized.emit()

    def state(self, path):
        status, reason, details = self.states[path]
        if status == 'Ready' and self.mode == 'animation' and self.animation_format == 'apng':
            if details['frames'] != 1 or details['animated_png']:
                return 'Blocked', 'APNG needs single-frame sources', details
        return status, reason, details

    def counts(self):
        statuses = [self.state(path)[0] for path in self.ordered_paths()]
        return statuses.count('Ready'), statuses.count('Blocked'), statuses.count('Inspecting')

    def refresh_item(self, path):
        item = self.items[path]
        status, reason, _ = self.state(path)
        item.setText(f'{self.images.row(item) + 1}. {Path(path).name}\n{status}')
        item.setToolTip(path + '\n' + reason)
        item.setForeground(QBrush(self.palette().color(
            QPalette.Disabled if status == 'Blocked' else QPalette.Active, QPalette.Text)))

    def refresh_items(self, *_):
        for path in self.items:
            self.refresh_item(path)
        self.update_controls()
        self.queue_thumbnails()
        self.changed.emit()

    def update_controls(self):
        selected = self.images.selectedItems()
        count = self.images.count()
        self.remove_button.setEnabled(bool(selected))
        self.up_button.setEnabled(len(selected) == 1 and self.images.row(selected[0]) > 0)
        self.down_button.setEnabled(len(selected) == 1 and self.images.row(selected[0]) < count - 1)
        self.add_button.setEnabled(self.max_images is None or count < self.max_images)

    def start_inspection(self):
        if self.stopped or self.worker is not None:
            return
        paths = [p for p in self.ordered_paths() if self.states[p][0] == 'Inspecting']
        if not paths:
            return
        self.inspection_items = {path: self.items[path] for path in paths}
        self.worker = ImageSourceInspector(paths, self, self.mode)
        self.worker.inspected.connect(self.inspection_result)
        self.worker.finished.connect(self.inspection_finished)
        self.worker.start()

    def inspection_result(self, path, status, reason, details):
        if (self.stopped or path not in self.states or self.states[path][0] != 'Inspecting'
                or self.items[path] is not self.inspection_items.get(path)):
            return
        self.states[path] = (status, reason, details)
        self.refresh_item(path)
        self.changed.emit()
        self.queue_thumbnails()

    def inspection_finished(self):
        worker, self.worker = self.worker, None
        worker.wait()
        worker.deleteLater()
        if self.stopped:
            self.notify_idle()
        else:
            self.start_inspection()
            self.changed.emit()

    def validate_sources(self):
        # Approval never trusts an inspection of an older source identity.
        for path in self.ordered_paths():
            details = self.states[path][2]
            try:
                if details is None or identity(path) != details['stamp']:
                    raise ValueError('Source changed; remove and add it again')
            except (OSError, ValueError) as exc:
                self.states[path] = ('Blocked', str(exc), None)
        self.refresh_items()
        ready, blocked, pending = self.counts()
        return bool(ready) and not blocked and not pending

    def queue_thumbnails(self, *_):
        if not self.stopped:
            self.thumbnail_timer.start()

    def request_preview(self, path):
        self.preview_path = path
        self.queue_thumbnails()

    def load_thumbnails(self):
        if self.stopped or self.thumbnail_worker is not None:
            return
        viewport = self.images.viewport().rect()
        visible = [p for p, item in self.items.items()
                   if self.images.visualItemRect(item).intersects(viewport)]
        paths = []
        for path in dict.fromkeys([self.preview_path, *visible]):
            if path not in self.items or path in self.unavailable or path in self.thumbnails:
                continue
            if self.states[path][0] == 'Ready':
                paths.append(path)
        if paths:
            self.thumbnail_items = {path: self.items[path] for path in paths[:8]}
            self.thumbnail_worker = ThumbnailWorker(paths[:8], QSize(192, 140), self)
            self.thumbnail_worker.thumbnail_ready.connect(self.receive_thumbnail)
            self.thumbnail_worker.finished.connect(self.thumbnails_finished)
            self.thumbnail_worker.start()

    def receive_thumbnail(self, path, image, stamp):
        if (self.stopped or path not in self.items or self.states[path][0] != 'Ready'
                or self.items[path] is not self.thumbnail_items.get(path)):
            return
        details = self.states[path][2]
        try:
            unchanged = details is not None and identity(path) == details['stamp']
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            self.states[path] = ('Blocked', 'Source changed; remove and add it again', None)
            self.unavailable.add(path)
            self.refresh_item(path)
            self.changed.emit()
        elif image.isNull() or stamp != details['stamp']:
            self.unavailable.add(path)
            self.items[path].setToolTip(self.items[path].toolTip() + '; thumbnail unavailable')
        else:
            self.thumbnails[path] = image
            self.thumbnails.move_to_end(path)
            self.items[path].setIcon(QIcon(QPixmap.fromImage(image)))
            while len(self.thumbnails) > 64:
                old_path, _ = self.thumbnails.popitem(last=False)
                if old_path in self.items:
                    self.items[old_path].setIcon(QIcon())
        self.thumbnail_changed.emit(path)

    def thumbnails_finished(self):
        worker, self.thumbnail_worker = self.thumbnail_worker, None
        worker.wait()
        worker.deleteLater()
        if self.stopped:
            self.notify_idle()
        else:
            self.queue_thumbnails()

    def stop(self):
        self.stopped = True
        self.thumbnail_timer.stop()
        for worker in (self.worker, self.thumbnail_worker):
            if worker is not None:
                worker.requestInterruption()
        self.notify_idle()

    def notify_idle(self):
        if self.worker is None and self.thumbnail_worker is None:
            self.idle.emit()


class OrderedImageDialog(QDialog):
    """Delay closing until the owned inspection/thumbnail threads have stopped."""

    finish_result = None

    def add_source_notice(self, layout):
        self.source_notice = SourceAdvisoryNotice(self)
        layout.addWidget(self.source_notice)
        self.ordered.changed.connect(
            lambda: self.source_notice.set_sources(self.ordered.ordered_paths()))

    def fit_images(self):
        self.layout().activate()
        self.resize(self.width(), self.sizeHint().height())

    def done(self, result):
        if self.finish_result is not None:
            return
        if result == QDialog.Accepted:
            try:
                if not self.source_notice.approve(self.ordered.ordered_paths()):
                    return
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Cannot approve source advisories', str(exc))
                return
        self.finish_result = result
        self.create.setEnabled(False)
        self.ordered.setEnabled(False)
        self.ordered.idle.connect(self.finish_close)
        self.ordered.stop()

    def finish_close(self):
        QDialog.done(self, self.finish_result)

    def reject(self):
        self.done(QDialog.Rejected)

    def closeEvent(self, event):
        self.reject()
        if self.ordered.worker is not None or self.ordered.thumbnail_worker is not None:
            event.ignore()
        else:
            event.accept()


class SlideshowDialog(OrderedImageDialog):
    """Ordered image selection for the existing MP4 renderer."""

    def __init__(
        self, destination, seconds, frame_size,
        fps, background, output, paths
    ):
        super().__init__()

        self.destination = Path(destination)
        self.max_images = 200

        self.setWindowTitle('KIM6 — Create Video Slideshow')
        self.resize(760, 400)
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)

        instruction = QLabel(
            'Images play from top to bottom. '
            'Drag rows or use Up/Down to change the order.'
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.ordered = OrderedImages(self)
        layout.addWidget(self.ordered)

        form = QFormLayout()

        self.seconds = QSpinBox()
        self.seconds.setRange(1, 30)
        self.seconds.setValue(int(seconds))
        self.seconds.setSuffix(' seconds')
        form.addRow('Seconds per image', self.seconds)

        self.size = QComboBox()

        for label, value in (
            ('854 × 480 (SD)', '854x480'),
            ('1280 × 720 (HD)', '1280x720'),
            ('1920 × 1080 (Full HD)', '1920x1080'),
        ):
            self.size.addItem(label, value)

        size_index = self.size.findData(frame_size)
        self.size.setCurrentIndex(max(0, size_index))
        form.addRow('Video size', self.size)

        self.fps = QSpinBox()
        self.fps.setRange(1, 30)
        self.fps.setValue(int(fps))
        self.fps.setSuffix(' FPS')
        form.addRow('Frame rate', self.fps)

        self.background = QComboBox()

        for color in (
            'black', 'white', 'gray', 'grey',
            'navy', 'red', 'green', 'blue',
            'yellow', 'orange', 'purple',
        ):
            self.background.addItem(
                color.capitalize(),
                color,
            )

        self.background.addItem(
            'Custom color (#RRGGBB)',
            'custom',
        )

        bg_index = self.background.findData(
            'custom'
            if background.startswith('#')
            else background
        )

        self.background.setCurrentIndex(
            max(0, bg_index)
        )

        form.addRow('Background', self.background)

        self.custom_color = QLineEdit(
            background
            if background.startswith('#')
            else '#202020'
        )

        form.addRow(
            'Custom color',
            self.custom_color,
        )

        def show_custom_color():
            form.setRowVisible(
                self.custom_color,
                self.background.currentData() == 'custom'
            )
            self.update_controls()

        self.background.currentIndexChanged.connect(
            show_custom_color
        )
        self.custom_color.textChanged.connect(
            self.update_controls
        )

        form.setRowVisible(
            self.custom_color,
            self.background.currentData() == 'custom',
        )

        output_row = QHBoxLayout()
        self.output = QLineEdit()
        self.output.setPlaceholderText(
            'Choose a new MP4 filename'
        )

        self.browse_button = QPushButton('Browse…')
        output_row.addWidget(self.output, 1)
        output_row.addWidget(self.browse_button)

        form.addRow('Save video as', output_row)
        layout.addLayout(form)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )

        self.create = buttons.button(
            QDialogButtonBox.Ok
        )
        self.create.setText('Create Slideshow')
        self.create.setEnabled(False)

        self.add_source_notice(layout)
        layout.addWidget(buttons)

        self.browse_button.clicked.connect(
            self.choose_output
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self.ordered.changed.connect(self.update_controls)
        self.ordered.resized.connect(self.fit_images)

        for control in (
            self.seconds,
            self.fps,
        ):
            control.valueChanged.connect(
                self.update_controls
            )

        self.output.textChanged.connect(
            self.update_controls
        )

        def natural(path):
            return [
                (
                    0, int(part)
                )
                if part.isdigit()
                else (
                    1, part.casefold()
                )
                for part in re.split(
                    r'(\d+)',
                    Path(path).name,
                )
            ]

        self.ordered.add_paths(sorted(paths, key=natural))

        if output:
            self.output.setText(output)

        elif paths:
            initial = (
                Path(paths[0]).parent
                / 'slideshow.mp4'
            )

            number = 1

            while (
                initial.exists()
                or initial.is_symlink()
            ):
                initial = (
                    Path(paths[0]).parent
                    / f'slideshow_{number}.mp4'
                )
                number += 1

            self.output.setText(str(initial))

        self.update_controls()

    def ordered_paths(self):
        return self.ordered.ordered_paths()

    def choose_output(self):
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            'Save MP4 Slideshow',
            self.output.text(),
            'MP4 video (*.mp4)',
        )

        if filename:
            self.output.setText(filename)

    def update_controls(self, *_):
        paths = self.ordered_paths()
        count = len(paths)
        ready, blocked, pending = self.ordered.counts()

        duration = (
            count * self.seconds.value()
        )

        frames = (
            duration * self.fps.value()
        )

        target = self.output.text().strip()
        problem = ''

        if count < 1:
            problem = 'Add at least one image.'

        elif count > self.max_images:
            problem = (
                'A slideshow can contain at most 200 images.'
            )

        elif (
            duration > 600
            or frames > 18000
        ):
            problem = (
                'Limit: 600 seconds or 18,000 frames. '
                'Reduce the duration or frame rate.'
            )

        elif blocked:
            problem = (
                'Remove or replace blocked images '
                'before creating the slideshow.'
            )

        elif (
            pending
            or self.ordered.worker is not None
        ):
            problem = 'Inspecting selected images…'

        elif (
            not target
            or not Path(target).is_absolute()
            or Path(target).suffix.lower() != '.mp4'
        ):
            problem = (
                'Choose an absolute MP4 output filename.'
            )

        elif (
            '\n' in target
            or '\r' in target
        ):
            problem = (
                'Output filenames cannot contain line breaks.'
            )

        elif (
            Path(target).exists()
            or Path(target).is_symlink()
        ):
            problem = (
                'Output exists. Choose a different filename.'
            )

        elif not Path(target).parent.is_dir():
            problem = (
                'The output directory does not exist.'
            )

        elif target in paths:
            problem = (
                'Output cannot replace a selected image.'
            )

        elif (
            self.background.currentData() == 'custom'
            and not re.fullmatch(
                r'#[0-9A-Fa-f]{6}',
                self.custom_color.text().strip(),
            )
        ):
            problem = (
                'Custom background color must be #RRGGBB.'
            )

        self.create.setEnabled(
            not problem and ready == count
        )

        self.summary.setText(
            f'{count} selected · '
            f'{ready} ready · '
            f'{blocked} blocked · '
            f'{pending} inspecting · '
            f'Duration: {duration} seconds'
            + (
                '\n' + problem
                if problem
                else ''
            )
        )

    def accept(self):
        self.update_controls()
        if not self.create.isEnabled() or not self.ordered.validate_sources():
            return
        self.update_controls()

        if not self.create.isEnabled():
            return

        color = (
            self.custom_color.text().strip()
            if self.background.currentData() == 'custom'
            else self.background.currentData()
        )

        values = [
            str(self.seconds.value()),
            self.size.currentData(),
            str(self.fps.value()),
            color,
            self.output.text().strip(),
            *self.ordered_paths(),
        ]

        try:
            self.destination.write_bytes(
                b''.join(
                    os.fsencode(value) + b'\0'
                    for value in values
                )
            )

        except OSError as exc:
            QMessageBox.critical(
                self,
                'Cannot save slideshow settings',
                str(exc),
            )
            return

        self.done(QDialog.Accepted)


class AnimatedImageDialog(OrderedImageDialog):
    """Approve source order and settings; preview never encodes or publishes."""

    def __init__(self, destination, starting_dir, paths, *, output='', delay=100,
                 loops=0, animation_format='gif', canvas_mode='fit'):
        super().__init__()
        self.destination = Path(destination)
        self.frame_index = 0
        self.completed_cycles = 0
        self.sequence = ()
        self.setWindowTitle('KIM6 — Create Animated Image')
        self.setMinimumWidth(640)
        self.resize(720, 400)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addWidget(QLabel('Images play in the order shown. Drag to rearrange.'))
        self.ordered = OrderedImages(self, mode='animation')
        layout.addWidget(self.ordered)

        form = QFormLayout()
        self.format = QComboBox()
        self.format.addItem('Animated GIF', 'gif')
        self.format.addItem('Animated PNG (APNG)', 'apng')
        self.format.setCurrentIndex(max(0, self.format.findData(animation_format)))
        form.addRow('Output format:', self.format)
        self.canvas_mode = QComboBox()
        self.canvas_mode.addItem('Fit entire image', 'fit')
        self.canvas_mode.addItem('Fill canvas (center crop)', 'fill')
        self.canvas_mode.addItem('Preserve original pixels (pad)', 'preserve')
        self.canvas_mode.setCurrentIndex(max(0, self.canvas_mode.findData(canvas_mode)))
        self.canvas_mode.setToolTip('Fit and Fill use the first image’s oriented size. '
                                   'Preserve uses the largest required canvas without resizing.')
        self.canvas_mode_label = QLabel('APNG canvas:')
        form.addRow(self.canvas_mode_label, self.canvas_mode)
        self.canvas_mode_label.setVisible(animation_format == 'apng')
        self.canvas_mode.setVisible(animation_format == 'apng')
        self.delay = QSpinBox()
        self.delay.setRange(0, 65535)
        self.delay.setValue(int(delay))
        self.delay.setToolTip(
            'Exact encoded frame delay in 1/100-second units.'
        )
        self.timing_units = QComboBox()
        self.timing_units.addItem(
            'Seconds per frame', 'seconds'
        )
        self.timing_units.addItem(
            'Centiseconds per frame', 'centiseconds'
        )
        self.timing_units.addItem(
            'Frames per second (FPS)', 'fps'
        )
        form.addRow('Timing units:', self.timing_units)

        self.timing_inputs = QStackedWidget()

        self.seconds_per_frame = QDoubleSpinBox()
        self.seconds_per_frame.setRange(0, 655.35)
        self.seconds_per_frame.setDecimals(2)
        self.seconds_per_frame.setSingleStep(0.1)
        self.seconds_per_frame.setSuffix(' s')

        self.frames_per_second = QDoubleSpinBox()
        self.frames_per_second.setRange(0, 100)
        self.frames_per_second.setDecimals(2)
        self.frames_per_second.setSingleStep(1)
        self.frames_per_second.setSuffix(' FPS')

        for field in (
            self.seconds_per_frame,
            self.delay,
            self.frames_per_second,
        ):
            self.timing_inputs.addWidget(field)

        form.addRow('Frame timing:', self.timing_inputs)

        self.timing_summary = QLabel()
        self.timing_summary.setWordWrap(True)
        form.addRow(self.timing_summary)
        self.loops = QSpinBox()
        self.loops.setRange(0, 65535)
        self.loops.setValue(int(loops))
        form.addRow('Loop count (0 = infinite):', self.loops)
        self.output = QLineEdit(output or str(Path(starting_dir) / (
            'my_animation.gif' if animation_format == 'gif' else 'my_animation.png')))
        self.browse = QPushButton('Browse…')
        output_row = QHBoxLayout()
        output_row.addWidget(self.output, 1)
        output_row.addWidget(self.browse)
        form.addRow('Save animation as:', output_row)
        layout.addLayout(form)
        explanation = QLabel('GIF uses indexed color; APNG supports full-color RGBA. '
                             'Existing outputs are numbered when needed.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        preview_row = QHBoxLayout()
        self.canvas = ImageCanvas(self)
        self.canvas.setAccessibleName('Animated Image sequence preview')
        self.canvas.setFixedSize(192, 140)
        preview_row.addWidget(self.canvas)
        preview_controls = QVBoxLayout()
        note = QLabel('Sequence and timing preview. Final encoding may differ.')
        note.setWordWrap(True)
        preview_controls.addWidget(note)
        self.frame_position = QLabel()
        preview_controls.addWidget(self.frame_position)
        playback = QHBoxLayout()
        self.play = QPushButton('Play')
        self.pause = QPushButton('Pause')
        self.restart = QPushButton('Restart')
        for button in (self.play, self.pause, self.restart):
            playback.addWidget(button)
        preview_controls.addLayout(playback)
        preview_controls.addStretch(1)
        preview_row.addLayout(preview_controls, 1)
        layout.addLayout(preview_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create = buttons.button(QDialogButtonBox.Ok)
        self.create.setText('Create Animated Image')
        self.add_source_notice(layout)
        layout.addWidget(buttons)

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.advance_preview)
        self.delay.valueChanged.connect(self.update_interval)
        self.delay.valueChanged.connect(self.sync_timing)

        self.seconds_per_frame.valueChanged.connect(
            lambda seconds: self.delay.setValue(
                round(seconds * 100)
            )
        )
        self.frames_per_second.valueChanged.connect(
            lambda fps: self.delay.setValue(
                round(100 / fps) if fps else 0
            )
        )
        self.timing_units.currentIndexChanged.connect(
            self.change_timing_units
        )

        self.loops.valueChanged.connect(self.reset_cycles)
        self.play.clicked.connect(self.play_preview)
        self.pause.clicked.connect(self.pause_preview)
        self.restart.clicked.connect(self.restart_preview)
        self.browse.clicked.connect(self.choose_output)
        self.format.currentIndexChanged.connect(self.change_format)
        self.canvas_mode.currentIndexChanged.connect(self.change_canvas_mode)
        self.output.textChanged.connect(self.update_controls)
        self.ordered.changed.connect(self.sequence_changed)
        self.ordered.resized.connect(self.fit_images)
        self.ordered.thumbnail_changed.connect(self.thumbnail_ready)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ordered.animation_format = self.format.currentData()
        self.change_timing_units()
        self.update_interval()
        self.ordered.add_paths(paths)
        self.sequence_changed()
        self.fit_images()

    def ordered_paths(self):
        return self.ordered.ordered_paths()

    def change_timing_units(self, *_):
        self.timing_inputs.setCurrentIndex(
            self.timing_units.currentIndex()
        )
        self.sync_timing()

    def sync_timing(self, *_):
        delay = self.delay.value()

        for widget, value in (
            (self.seconds_per_frame, delay / 100),
            (
                self.frames_per_second,
                100 / delay if delay else 0
            ),
        ):
            blocked = widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(blocked)

        if delay:
            self.timing_summary.setText(
                f'Actual frame delay: {delay / 100:.2f} s '
                f'({delay} centiseconds, '
                f'{100 / delay:.2f} FPS). '
                'GIF timing is quantized to centiseconds.'
            )
        else:
            self.timing_summary.setText(
                'Zero-delay frames have no specified playback '
                'rate. Players may apply their own minimum delay.'
            )

    def update_interval(self, *_):
        # A zero-delay GIF is legal. Limit preview to 50 FPS to avoid a busy loop.
        self.preview_timer.setInterval(max(20, self.delay.value() * 10))
        self.update_controls()

    def reset_cycles(self, *_):
        self.completed_cycles = 0

    def sequence_changed(self):
        paths = tuple(self.ordered_paths())
        if paths != self.sequence:
            self.sequence = paths
            self.frame_index = 0
            self.completed_cycles = 0
            if self.preview_timer.isActive():
                self.preview_timer.start()
        if not paths:
            self.preview_timer.stop()
        self.show_frame()
        self.update_controls()

    def thumbnail_ready(self, path):
        if self.sequence and path == self.sequence[self.frame_index]:
            self.show_frame()

    def show_frame(self):
        self.canvas.image = QImage()
        if not self.sequence:
            self.frame_position.setText('Frame 0 of 0')
            self.canvas.message = 'Add images to preview'
        else:
            path = self.sequence[self.frame_index]
            status, reason, details = self.ordered.state(path)
            multi = details and (details['frames'] > 1 or details['animated_png'])
            any_multi = any(d and (d['frames'] > 1 or d['animated_png'])
                            for _, _, d in self.ordered.states.values())
            unit = 'Source' if any_multi else 'Frame'
            self.frame_position.setText(f'{unit} {self.frame_index + 1} of {len(self.sequence)}')
            self.canvas.setToolTip(path)
            if multi:
                count = str(details['frames']) if not details['animated_png'] else 'multiple'
                self.canvas.message = f'Multi-frame source ({count} frames).\nSequence preview unavailable for this source.'
            elif status == 'Blocked':
                self.canvas.message = reason
            elif path in self.ordered.thumbnails:
                self.canvas.image = self.ordered.thumbnails[path]
                if self.format.currentData() == 'apng':
                    self.canvas.image = self.apng_preview(self.canvas.image, details)
                self.ordered.thumbnails.move_to_end(path)
            elif path in self.ordered.unavailable:
                self.canvas.message = 'Preview unavailable.\nNo safe thumbnail decoder; export validation is independent.'
            else:
                self.canvas.message = 'Loading frame preview…'
            self.ordered.request_preview(path)
        self.canvas.update()

    def apng_canvas_size(self):
        """One oriented output canvas, shared by preview and approval limits."""
        details = [self.ordered.states[p][2] for p in self.sequence]
        if not details or any(d is None for d in details):
            return QSize()
        if self.canvas_mode.currentData() == 'preserve':
            return QSize(max(d['width'] for d in details), max(d['height'] for d in details))
        return QSize(details[0]['width'], details[0]['height'])

    def apng_preview(self, thumbnail, details):
        # Only transform the cached, asynchronously decoded thumbnail. Header
        # geometry avoids accumulating rounding errors from thumbnail dimensions.
        canvas = self.apng_canvas_size()
        if not canvas.isValid() or details is None:
            return QImage()
        size = canvas.scaled(self.canvas.size(), Qt.KeepAspectRatio)
        image = QImage(size, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        width, height = details['width'], details['height']
        mode = self.canvas_mode.currentData()
        scale = (max if mode == 'fill' else min)(canvas.width() / width, canvas.height() / height)
        if mode == 'preserve':
            scale = 1
        # Painting clips Fill at the canvas edges; Fit/Preserve leave alpha padding.
        xscale, yscale = size.width() / canvas.width(), size.height() / canvas.height()
        rect = QRectF((canvas.width() - width * scale) / 2 * xscale,
                      (canvas.height() - height * scale) / 2 * yscale,
                      width * scale * xscale, height * scale * yscale)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(rect, thumbnail)
        painter.end()
        return image

    def change_canvas_mode(self, *_):
        self.show_frame()
        self.update_controls()

    def play_preview(self):
        if not self.sequence or self.finish_result is not None:
            return
        if self.loops.value() and self.completed_cycles >= self.loops.value():
            self.frame_index = 0
            self.completed_cycles = 0
        self.show_frame()
        self.preview_timer.start()
        self.update_controls()

    def pause_preview(self):
        self.preview_timer.stop()
        self.update_controls()

    def restart_preview(self):
        self.frame_index = 0
        self.completed_cycles = 0
        self.play_preview()

    def advance_preview(self):
        if not self.sequence or not self.preview_timer.isActive():
            return
        if self.frame_index == len(self.sequence) - 1:
            self.completed_cycles += 1
            if self.loops.value() and self.completed_cycles >= self.loops.value():
                self.pause_preview()
                return
            self.frame_index = 0
        else:
            self.frame_index += 1
        self.show_frame()

    def change_format(self):
        is_apng = self.format.currentData() == 'apng'
        self.canvas_mode_label.setVisible(is_apng)
        self.canvas_mode.setVisible(is_apng)
        name, extension = os.path.splitext(self.output.text())
        if extension.lower() in ('.gif', '.png'):
            self.output.setText(name + ('.gif' if self.format.currentData() == 'gif' else '.png'))
        self.ordered.animation_format = self.format.currentData()
        self.ordered.refresh_items()

    def choose_output(self):
        is_gif = self.format.currentData() == 'gif'
        value, _ = QFileDialog.getSaveFileName(
            self, 'Save Animated GIF' if is_gif else 'Save Animated PNG',
            self.output.text(), 'Animated GIF (*.gif)' if is_gif else 'Animated PNG (*.png)',
        )
        if value:
            self.output.setText(value)

    def approved_target(self):
        target = os.path.abspath(os.path.expanduser(self.output.text().strip()))
        name, extension = os.path.splitext(target)
        suffix = '.gif' if self.format.currentData() == 'gif' else '.png'
        if extension.lower() not in ('', '.gif', '.png'):
            return '', 'Choose a ' + suffix + ' output filename.'
        target = name + suffix if extension else target + suffix
        if not self.output.text().strip() or '\n' in target or '\r' in target:
            return '', 'Choose an output filename without line breaks.'
        if not Path(target).parent.is_dir():
            return '', 'The destination directory does not exist.'
        if target in self.sequence:
            return '', 'Output cannot replace a selected image.'
        return target, ''

    def update_controls(self, *_):
        if not hasattr(self, 'preview_timer'):
            return
        count = len(self.sequence)
        ready, blocked, pending = self.ordered.counts()
        _, problem = self.approved_target()
        if count < 1:
            problem = 'Add at least one image.'
        elif blocked:
            problem = 'Remove or replace blocked images before creating the Animated Image.'
        elif pending or self.ordered.worker is not None:
            problem = 'Inspecting selected images…'
        elif self.format.currentData() == 'apng':
            if not 2 <= count <= 360 or self.delay.value() < 1:
                problem = 'APNG needs 2–360 single-frame images and a nonzero frame delay.'
            else:
                canvas = self.apng_canvas_size()
                if max(canvas.width(), canvas.height()) > 4096:
                    problem = 'APNG canvas dimensions cannot exceed 4096 pixels.'
                elif canvas.width() * canvas.height() * count > 200000000:
                    problem = 'APNG exceeds the 200-million pixel-frame limit.'
        self.create.setEnabled(not problem and ready == count and self.finish_result is None)
        duration = count * self.delay.value() / 100
        self.summary.setText(
            f'{count} frames · {duration:.2f} s per loop · '
            f'{ready} ready · {blocked} blocked · '
            f'{pending} inspecting'
            + ('\n' + problem if problem else '')
        )
        playing = self.preview_timer.isActive()
        self.play.setEnabled(bool(count) and not playing)
        self.pause.setEnabled(playing)
        self.restart.setEnabled(bool(count))

    def accept(self):
        self.update_controls()
        if not self.create.isEnabled() or not self.ordered.validate_sources():
            return
        self.update_controls()
        if not self.create.isEnabled():
            return
        target, _ = self.approved_target()
        values = [self.format.currentData(), str(self.delay.value()),
                  str(self.loops.value()), target]
        if self.format.currentData() == 'apng':
            values.append(self.canvas_mode.currentData())
        values.extend(self.ordered_paths())
        try:
            self.destination.write_bytes(b''.join(os.fsencode(value) + b'\0' for value in values))
        except OSError as exc:
            QMessageBox.critical(self, 'Cannot save Animated Image settings', str(exc))
            return
        self.done(QDialog.Accepted)

    def done(self, result):
        self.preview_timer.stop()
        super().done(result)


def animation_dialog(arguments):
    if len(arguments) < 8:
        return 2
    destination, starting_dir, count_text, animation_format, delay, loops, output, *paths = arguments
    canvas_mode = 'fit'
    if paths[:1] == ['--canvas-mode']:
        if len(paths) < 3 or paths[1] not in ('fit', 'fill', 'preserve'):
            return 2
        _, canvas_mode, *paths = paths
    try:
        if (int(count_text) != len(paths) or not paths or animation_format not in ('gif', 'apng')
                or not 0 <= int(delay) <= 65535 or not 0 <= int(loops) <= 65535):
            return 2
    except ValueError:
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = AnimatedImageDialog(destination, starting_dir, paths, output=output,
                                 delay=delay, loops=loops, animation_format=animation_format,
                                 canvas_mode=canvas_mode)
    return 0 if dialog.exec() == QDialog.Accepted else 130


def slideshow_dialog(arguments):
    if len(arguments) < 9:
        return 2

    destination, starting_dir, count_text, seconds, size, fps, background, output, *files = arguments

    try:
        count = int(count_text)

        if (
            count != len(files)
            or not 1 <= count <= 200
        ):
            return 2

    except ValueError:
        return 2

    app = QApplication.instance() or QApplication(sys.argv)

    dialog = SlideshowDialog(
        destination,
        seconds,
        size,
        fps,
        background,
        output,
        files,
    )

    return (
        0
        if dialog.exec() == QDialog.Accepted
        else 130
    )


class CreationImages(OrderedImages):
    """Small action adapter; selection, ordering and worker ownership stay shared."""

    def __init__(self, parent, title, *, single_frame=False):
        # Animation inspection supports the existing PSD composite adapter and
        # multi-frame sources without imposing slideshow eligibility or limits.
        super().__init__(parent, mode='animation')
        self.action_title = title
        self.single_frame = single_frame
        self.images.setAccessibleName('Images in output order')

    def choose_images(self):
        paths = self.ordered_paths()
        additions = choose_images(
            self, str(Path(paths[0]).parent) if paths else str(Path.home()),
            title='Add Images for ' + self.action_title,
            extensions=CREATE_IMAGE_EXTENSIONS,
        )
        if additions:
            self.add_paths(additions)

    def state(self, path):
        status, reason, details = super().state(path)
        if status == 'Ready' and self.single_frame and details['frames'] != 1:
            return 'Blocked', 'Contact Sheet requires single-frame images', details
        return status, reason, details


def creation_output(text, extensions, paths):
    """Validate a requested derivative like Bash prepare_derived_target.

    Numbering and exclusive publication remain with the action. Return both the
    requested path and an advisory numbered path for display before approval.
    """
    if not text.strip():
        raise ValueError('Choose an output filename.')
    if any(char in text for char in ('\0', '\n', '\r')):
        raise ValueError('Output filenames cannot contain line breaks or NUL.')
    requested = Path(os.path.abspath(os.path.expanduser(text.strip())))
    if not text.strip().endswith('/') and requested.name not in ('', '.', '..'):
        if requested.suffix.lower().lstrip('.') not in extensions:
            requested = requested.with_name(requested.name + '.' + extensions[0])
    else:
        raise ValueError('Choose an output filename.')
    parent = requested.parent.resolve()
    if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
        raise ValueError('Choose an existing, writable output directory.')
    requested = parent / requested.name
    if any(char in str(requested) for char in ('\n', '\r', '\0')):
        raise ValueError('Output filenames cannot contain line breaks or NUL.')
    if requested.exists():
        stamp = requested.stat()
        for path in paths:
            source = os.stat(path, follow_symlinks=False)
            if (source.st_dev, source.st_ino) == (stamp.st_dev, stamp.st_ino):
                raise ValueError('Output cannot replace a selected image.')
    candidate = requested
    number = 1
    while os.path.lexists(candidate):
        candidate = requested.with_name(f'{requested.stem}_{number}{requested.suffix.lower()}')
        number += 1
    return requested, candidate


def write_creation_settings(dialog, destination, values):
    try:
        if any('\0' in value for value in values):
            raise ValueError('Settings cannot contain NUL.')
        Path(destination).write_bytes(b''.join(os.fsencode(value) + b'\0' for value in values))
    except (OSError, ValueError) as exc:
        QMessageBox.warning(dialog, 'Cannot approve creation settings', str(exc))
        return False
    return True


class GalleryDialog(OrderedImageDialog):
    def __init__(self, destination, starting_dir, paths):
        super().__init__()
        self.destination = destination
        self.setWindowTitle('KIM6 — Create an HTML Gallery')
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        self.ordered = CreationImages(self, 'HTML Gallery')
        layout.addWidget(self.ordered)
        self.count = QLabel()
        layout.addWidget(self.count)
        form = QFormLayout()
        layout.addLayout(form)
        self.title = QLineEdit('My Gallery')
        self.author = QLineEdit(os.environ.get('USER', ''))
        self.columns = QSpinBox()
        self.columns.setRange(1, 100)
        self.columns.setValue(4)
        self.theme = QComboBox()
        self.theme.addItem('Dark Portfolio', 'dark')
        self.theme.addItem('Clean Light', 'light')
        self.resolution = QComboBox()
        self.resolution.addItem('Standard (up to 1920 px)', '1920')
        self.resolution.addItem('High (up to 3840 px)', '3840')
        for caption, widget in (('Gallery title:', self.title), ('Author:', self.author),
                                ('Columns:', self.columns), ('Appearance:', self.theme),
                                ('Image resolution:', self.resolution)):
            form.addRow(caption, widget)
        self.parent_directory = QLineEdit(starting_dir)
        browse = QPushButton('Browse…')
        row = QHBoxLayout()
        row.addWidget(self.parent_directory, 1)
        row.addWidget(browse)
        form.addRow('Parent directory:', row)
        self.folder_name = QLineEdit(self.safe_folder_name(self.title.text()))
        form.addRow('Gallery folder name:', self.folder_name)
        self.target_label = QLabel()
        self.target_label.setTextFormat(Qt.PlainText)
        self.target_label.setWordWrap(True)
        self.target_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow('Destination:', self.target_label)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create = buttons.button(QDialogButtonBox.Ok)
        self.create.setText('Create')
        self.add_source_notice(layout)
        layout.addWidget(buttons)
        self.folder_edited = False
        self.folder_name.textEdited.connect(self.folder_was_edited)
        self.title.textChanged.connect(self.title_changed)
        self.parent_directory.textChanged.connect(self.update_controls)
        self.folder_name.textChanged.connect(self.update_controls)
        browse.clicked.connect(self.choose_parent)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ordered.changed.connect(self.update_controls)
        self.ordered.resized.connect(self.fit_images)
        self.ordered.add_paths(paths)
        self.update_controls()
        self.fit_images()

    @staticmethod
    def safe_folder_name(title):
        name = re.sub(r'[^\w .-]+', '-', title, flags=re.UNICODE).strip(' .-')
        while len(os.fsencode(name)) > 120:
            name = name[:-1]
        return name.rstrip(' .') or 'Gallery'

    def folder_was_edited(self):
        self.folder_edited = True

    def title_changed(self):
        if not self.folder_edited:
            self.folder_name.setText(self.safe_folder_name(self.title.text()))

    def choose_parent(self):
        parent = QFileDialog.getExistingDirectory(self, 'Choose Parent Directory for HTML Gallery',
                                                   self.parent_directory.text())
        if parent:
            self.parent_directory.setText(parent)

    def gallery_target(self):
        raw_parent = self.parent_directory.text()
        name = self.folder_name.text()
        if (not raw_parent.strip() or any(c in raw_parent + name for c in ('\0', '\n', '\r'))
                or not name.strip() or name in ('.', '..') or '/' in name):
            raise ValueError('Choose a parent directory and a single gallery folder name.')
        parent = Path(os.path.abspath(os.path.expanduser(raw_parent.strip()))).resolve()
        if any(c in str(parent) for c in ('\0', '\n', '\r')):
            raise ValueError('Directory paths cannot contain line breaks or NUL.')
        if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
            raise ValueError('Choose an existing, writable parent directory.')
        candidate = parent / name
        number = 1
        while os.path.lexists(candidate):
            candidate = parent / f'{name}_{number}'
            number += 1
        return candidate, number > 1

    def update_controls(self, *_):
        ready, blocked, pending = self.ordered.counts()
        self.count.setText(f'{len(self.ordered.ordered_paths())} selected image(s)')
        problem = ''
        try:
            target, collision = self.gallery_target()
            self.target_label.setText(str(target))
            if collision:
                problem = 'Folder name already exists. Proposed numbered destination shown above.'
        except (OSError, ValueError) as exc:
            self.target_label.clear()
            self.status.setText(str(exc))
            self.create.setEnabled(False)
            return
        if blocked:
            problem = 'Remove or replace blocked images.'
        elif pending:
            problem = 'Inspecting selected images…'
        elif not ready:
            problem = 'Add at least one image.'
        self.status.setText(problem)
        self.create.setEnabled(bool(ready) and not blocked and not pending)

    def accept(self):
        if self.finish_result is not None:
            return
        previous = self.target_label.text()
        self.update_controls()
        if not self.create.isEnabled() or not self.ordered.validate_sources():
            return
        if self.target_label.text() != previous:
            self.status.setText('Destination changed. Review the numbered destination, then Create.')
            return
        # Freeze the displayed approval; Bash rejects a name taken afterward.
        target = Path(self.target_label.text())
        values = [self.title.text(), self.author.text(), str(self.columns.value()),
                  self.theme.currentData(), self.resolution.currentData(),
                  str(target.parent), target.name, *self.ordered.ordered_paths()]
        if write_creation_settings(self, self.destination, values):
            self.done(QDialog.Accepted)


PRINT_LAYOUT_PRESETS = (
    ('9x13 cm: 2x2 images, landscape', '1'),
    ('10x15 cm: 1x2 images, portrait', '2'),
    ('11.5x15 cm: 1x2 images, portrait', '3'),
    ('13x18 cm: 1x2 images, portrait', '4'),
    ('20x25 cm: 1 image, landscape', '5'),
    ('3x2 portrait album', '6'),
    ('Thumbnails: 4x5 images, portrait', '7'),
)


class PrintLayoutDialog(OrderedImageDialog):
    """Output approval for the existing print and multi-page TIFF renderers."""

    def __init__(self, destination, starting_dir, paths, *, tiff=False):
        super().__init__()
        self.destination = destination
        self.tiff = tiff
        self.extensions = ('tiff', 'tif') if tiff else ('pdf',)
        title = 'Multi-page TIFF' if tiff else 'Print Layout PDF'
        self.setWindowTitle('KIM6 — Create ' + title)
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        self.ordered = CreationImages(self, title)
        layout.addWidget(self.ordered)
        self.count = QLabel()
        layout.addWidget(self.count)
        form = QFormLayout()
        layout.addLayout(form)
        if not tiff:
            self.preset = QComboBox()
            for caption, value in PRINT_LAYOUT_PRESETS:
                self.preset.addItem(caption, value)
            self.preset.setCurrentIndex(2)
            form.addRow('Print layout:', self.preset)
        self.output = QLineEdit(str(Path(starting_dir) / ('my_images.tiff' if tiff else 'print.pdf')))
        browse = QPushButton('Browse…')
        row = QHBoxLayout()
        row.addWidget(self.output, 1)
        row.addWidget(browse)
        form.addRow('Save TIFF as:' if tiff else 'Save PDF as:', row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create = buttons.button(QDialogButtonBox.Ok)
        self.create.setText('Create')
        self.add_source_notice(layout)
        layout.addWidget(buttons)
        browse.clicked.connect(self.choose_output)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.output.textChanged.connect(self.update_controls)
        self.ordered.changed.connect(self.update_controls)
        self.ordered.resized.connect(self.fit_images)
        self.ordered.add_paths(paths)
        self.update_controls()
        self.fit_images()

    def choose_output(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Save Multi-page TIFF' if self.tiff else 'Save Print Layout PDF',
            self.output.text(), 'TIFF (*.tiff *.tif)' if self.tiff else 'PDF (*.pdf)',
            options=QFileDialog.DontConfirmOverwrite)
        if filename:
            self.output.setText(filename)

    def update_controls(self, *_):
        ready, blocked, pending = self.ordered.counts()
        paths = self.ordered.ordered_paths()
        self.count.setText(f'{len(paths)} selected image(s)')
        problem = ''
        valid = True
        try:
            requested, candidate = creation_output(self.output.text(), self.extensions, paths)
            if requested != candidate:
                problem = f'Output exists. Proposed filename: {candidate}'
        except (OSError, ValueError) as exc:
            problem = str(exc)
            valid = False
        if blocked:
            problem = 'Remove or replace blocked images.'
        elif pending:
            problem = 'Inspecting selected images…'
        elif not ready:
            problem = 'Add at least one image.'
        self.status.setText(problem)
        self.create.setEnabled(valid and bool(ready) and not blocked and not pending)

    def accept(self):
        if self.finish_result is not None:
            return
        self.update_controls()
        if not self.create.isEnabled() or not self.ordered.validate_sources():
            return
        requested, _ = creation_output(self.output.text(), self.extensions, self.ordered.ordered_paths())
        values = ([] if self.tiff else [self.preset.currentData()])
        values += [str(requested), *self.ordered.ordered_paths()]
        if write_creation_settings(self, self.destination, values):
            self.done(QDialog.Accepted)


class TiffJoinDialog(PrintLayoutDialog):
    def __init__(self, destination, starting_dir, paths):
        super().__init__(destination, starting_dir, paths, tiff=True)


def main():
    if len(sys.argv) >= 10 and sys.argv[1] == 'animate':
        return animation_dialog(sys.argv[2:])
    if len(sys.argv) >= 11 and sys.argv[1] == 'slideshow':
        return slideshow_dialog(sys.argv[2:])
    if len(sys.argv) < 6:
        return 2
    kind, result_path, starting_dir, count_text, *paths = sys.argv[1:]
    try:
        if int(count_text) != len(paths):
            return 2
    except ValueError:
        return 2
    dialog_type = {'gallery': GalleryDialog, 'print': PrintLayoutDialog, 'tiffjoin': TiffJoinDialog}.get(kind)
    if dialog_type is None:
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = dialog_type(result_path, starting_dir, paths)
    return 0 if dialog.exec() == QDialog.Accepted else 130


if __name__ == '__main__':
    sys.exit(main())
