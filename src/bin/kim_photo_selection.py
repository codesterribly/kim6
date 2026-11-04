"""Local image selection and bounded, orientation-aware read-only previews."""
from collections import Counter, OrderedDict
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QFile, QIODevice, QRect, QSize, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QBrush, QImage, QImageIOHandler, QImageReader, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget)
from kim_preview import identity, inspection_path
from kim_location import descriptor_identity
from kim_psd_source import inspection_context

# These formats remain selectable even if Qt lacks their thumbnail plugin:
# ExifTool may still read them. Selecting one never broadens the write allowlist.
PHOTO_GROUPS = [
    ('JPEG', ('jpg', 'jpeg', 'jpe')),
    ('PNG', ('png',)), ('WebP', ('webp',)), ('TIFF', ('tif', 'tiff')),
    ('HEIC / HEIF', ('heic', 'heif', 'hif')), ('AVIF', ('avif',)),
]
IMAGE_GROUPS = PHOTO_GROUPS + [
    ('GIF / APNG', ('gif', 'apng')), ('BMP', ('bmp',)),
    ('JPEG 2000', ('jp2', 'j2k', 'jpf')), ('JPEG XL', ('jxl',)),
    ('Photoshop', ('psd',)), ('Portable images', ('ppm', 'pgm', 'pbm', 'pnm')),
    ('Camera RAW', ('dng', 'cr2', 'cr3', 'nef', 'arw', 'raf', 'orf', 'rw2', 'pef', 'srw')),
]
# Extra aliases used by creation / recipe callers, without broadening GPS browsing.
IMAGE_GROUPS = [(label, extensions + {'JPEG': ('jfif',), 'AVIF': ('avifs',)}.get(label, ()))
                for label, extensions in IMAGE_GROUPS]
CREATE_IMAGE_EXTENSIONS = frozenset({
    'jpg', 'jpeg', 'jpe', 'png', 'webp', 'avif', 'avifs', 'heic', 'heif',
    'tif', 'tiff', 'bmp', 'gif', 'jxl', 'jp2', 'j2k', 'jpf', 'apng', 'psd',
})
RECIPE_IMAGE_EXTENSIONS = frozenset({
    'jpg', 'jpeg', 'jpe', 'jfif', 'png', 'webp', 'avif', 'tif', 'tiff',
    'heic', 'heif', 'bmp', 'gif', 'jp2', 'jxl', 'psd', 'ppm', 'pnm',
})
OTHER_PHOTOS = {'bmp', 'gif', 'jp2', 'j2k', 'jxl', 'ppm', 'pgm', 'pbm',
                'dng', 'cr2', 'cr3', 'nef', 'arw', 'raf', 'orf', 'rw2', 'pef', 'srw', 'psd'}


def photo_extensions():
    """GPS browsing eligibility; metadata/write validation stays with Location."""
    readable = {bytes(fmt).decode('ascii', errors='ignore').lower() for fmt in QImageReader.supportedImageFormats()}
    other = sorted(OTHER_PHOTOS & (readable | {'dng', 'cr2', 'cr3', 'nef', 'arw', 'raf', 'orf', 'rw2', 'pef', 'srw', 'psd'}))
    groups = PHOTO_GROUPS + ([('Other readable images', tuple(other))] if other else [])
    return {ext for _, exts in groups for ext in exts}


def read_thumbnail(path, size, auto_orient=True):
    """Use descriptor-backed no-atime reads; never modify an image.

    Prefer native decoder scaling. Other decoders may decode up to 24 MP
    before Qt scales the image; larger inputs retain a placeholder.
    The existing Qt allocation limit and source identity checks remain in force.
    """
    before = identity(path)
    with inspection_path(path) as (_, fd):
        if descriptor_identity(fd) != before: raise ValueError('Image changed while opening preview')
        device = QFile()
        if not device.open(fd, QIODevice.ReadOnly): raise ValueError('Preview unavailable')
        try:
            reader = QImageReader(device)
            reader.setDecideFormatFromContent(True)
            reader.setAutoTransform(auto_orient)
            dimensions = reader.size()
            if not dimensions.isValid() or dimensions.width() * dimensions.height() > 1_000_000_000:
                raise ValueError('Preview dimensions unavailable or too large')
            native_scale = reader.supportsOption(QImageIOHandler.ScaledSize)
            if not native_scale and dimensions.width() * dimensions.height() > 24_000_000:
                raise ValueError('Safe small preview unavailable for this decoder')
            reader.setScaledSize(dimensions.scaled(size, Qt.KeepAspectRatio))
            image = reader.read()
            if image.isNull(): raise ValueError('No thumbnail decoder for this image')
            image = image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        finally:
            device.close()
    if identity(path) != before: raise ValueError('Image changed while previewing')
    return image, before


class ThumbnailWorker(QThread):
    thumbnail_ready = Signal(str, object, object)

    def __init__(self, paths, size, parent):
        super().__init__(parent)
        self.paths = paths; self.size = size

    def run(self):
        with inspection_context(cancelled=self.isInterruptionRequested):
            for path in self.paths:
                if self.isInterruptionRequested(): break
                try: image, stamp = read_thumbnail(path, self.size)
                except Exception: image, stamp = QImage(), None
                if not self.isInterruptionRequested(): self.thumbnail_ready.emit(path, image, stamp)


class ImageTileDelegate(QStyledItemDelegate):
    """Paint the slideshow's full thumbnail/caption tiles without per-file widgets."""

    def paint(self, painter, option, index):
        picker = self.parent()
        kind, path = index.data(Qt.UserRole)
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ''
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, background, painter, option.widget)
        rect = option.rect.adjusted(5, 4, -5, -4)
        preview = QRect(rect.x(), rect.y(), rect.width(), 108)
        painter.save()
        selected = bool(option.state & QStyle.State_Selected)
        painter.setPen(option.palette.color(QPalette.HighlightedText if selected else QPalette.Text))
        cached = picker.thumbnail_cache.get(path)
        if kind == 'directory':
            icon = option.widget.style().standardIcon(QStyle.SP_DirIcon)
            icon.paint(painter, preview, Qt.AlignCenter)
        elif cached is not None:
            image = cached[1]
            size = image.size().scaled(preview.size(), Qt.KeepAspectRatio)
            target = QRect(0, 0, size.width(), size.height())
            target.moveCenter(preview.center())
            painter.drawImage(target, image)
        else:
            message = 'Preview unavailable' if path in picker.unavailable else 'Loading preview…'
            painter.drawText(preview, Qt.AlignCenter | Qt.TextWordWrap, message)
        caption = QRect(rect.x(), rect.y() + 111, rect.width(), rect.height() - 111)
        painter.drawText(caption, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                         option.fontMetrics.elidedText(Path(path).name, Qt.ElideMiddle, rect.width() * 2))
        painter.restore()


class ImagePicker(QDialog):
    """Local image inputs in selection order, independent of folder and filter.

    Extensions are browsing eligibility only. Callers must retain their source
    validation. selected_paths() returns approved paths only, or [] on cancel.
    One owned ThumbnailWorker loads visible tiles through read_thumbnail().
    """

    def __init__(self, parent=None, directory='', *, title='Add Images',
                 multiple=True, extensions=None, accept_label='Add Selected Images'):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 560)
        self.setMinimumSize(480, 350)
        self.multiple = multiple
        self.extensions = frozenset(extensions if extensions is not None else photo_extensions())
        self.selection = {}  # Ordered across folders; rebuilding the view never changes it.
        self.approved_paths = []
        self.worker = None
        self.finish_result = None
        self.pending_directory = None
        self.current_directory = None
        self.image_items = {}
        self.thumbnail_cache = OrderedDict()
        self.unavailable = set()
        self.cache_limit = 192
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.load_visible_thumbnails)

        layout = QVBoxLayout(self)
        location = QHBoxLayout()
        self.up_button = QPushButton('Up')
        self.path_label = QLineEdit()
        self.path_label.setReadOnly(True)
        self.path_label.setAccessibleName('Current image folder')
        self.folder_button = QPushButton('Choose Folder…')
        location.addWidget(self.up_button)
        location.addWidget(self.path_label, 1)
        location.addWidget(self.folder_button)
        layout.addLayout(location)

        self.filter = QComboBox()
        self.filter.setAccessibleName('Image file type')
        layout.addWidget(self.filter)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setWrapping(True)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection if multiple else QAbstractItemView.SingleSelection)
        self.grid.setGridSize(QSize(170, 174))
        self.grid.setSpacing(5)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setItemDelegate(ImageTileDelegate(self))
        self.grid.setAccessibleName('Image thumbnails and folders')
        self.grid.installEventFilter(self)
        layout.addWidget(self.grid, 1)
        self.status = QLabel()
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.add_button = buttons.button(QDialogButtonBox.Ok)
        self.add_button.setText(accept_label)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.up_button.clicked.connect(self.go_up)
        self.folder_button.clicked.connect(self.choose_directory)
        self.grid.itemActivated.connect(self.open_item)
        self.grid.itemSelectionChanged.connect(self.update_selection)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        self.grid.verticalScrollBar().valueChanged.connect(self.queue_thumbnails)
        self.open_directory(directory or Path.home())

    def selected_paths(self):
        return list(self.approved_paths)

    def update_selection(self):
        visible = {path for path, item in self.image_items.items() if not item.isHidden()}
        selected = self.grid.selectedItems()
        chosen = [item.data(Qt.UserRole)[1] for item in selected
                  if item.data(Qt.UserRole)[0] == 'file' and not item.isHidden()]
        if not chosen and any(item.data(Qt.UserRole)[0] == 'directory' for item in selected):
            # Opening a folder starts with a click that clears Qt's selection.
            # Navigation must not discard images already picked in this folder.
            if self.multiple:
                self.grid.blockSignals(True)
                for path in visible:
                    self.image_items[path].setSelected(path in self.selection)
                self.grid.blockSignals(False)
            self.update_status()
            return
        if not self.multiple and chosen:
            self.selection.clear()
        else:
            for path in visible - set(chosen):
                self.selection.pop(path, None)
        for path in chosen:
            self.selection[path] = None
        self.update_status()

    def update_status(self):
        self.add_button.setEnabled(bool(self.selection) and self.finish_result is None)
        self.status.setText(f'{len(self.image_items)} images in folder · {len(self.selection)} selected')

    def go_up(self):
        if self.current_directory is not None:
            self.open_directory(self.current_directory.parent)

    def choose_directory(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose Image Folder',
            str(self.current_directory or Path.home()), QFileDialog.ShowDirsOnly)
        if folder:
            self.open_directory(folder)

    def open_item(self, item):
        kind, path = item.data(Qt.UserRole)
        if kind == 'directory':
            self.open_directory(path)
        elif not self.multiple:
            self.accept()

    def eventFilter(self, watched, event):
        if (watched is self.grid and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            item = self.grid.currentItem()
            if item is not None and item.data(Qt.UserRole)[0] == 'directory':
                # Consume Enter: QDialog's default Add button must not also fire.
                self.open_item(item)
                return True
        return super().eventFilter(watched, event)

    def open_directory(self, directory):
        if self.finish_result is not None:
            return
        try:
            folder = Path(directory).resolve(strict=True)
            if not folder.is_dir():
                raise ValueError('Not a folder')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot Open Folder', str(exc))
            return
        self.timer.stop()
        if self.worker is not None:
            self.pending_directory = folder
            self.grid.setEnabled(False)
            self.add_button.setEnabled(False)
            self.worker.requestInterruption()
        else:
            self.show_directory(folder)

    def show_directory(self, folder):
        try:
            with os.scandir(folder) as entries:
                rows = [(entry.is_dir(follow_symlinks=False), entry.name) for entry in entries
                        if entry.is_dir(follow_symlinks=False) or
                        (entry.is_file(follow_symlinks=False) and
                         Path(entry.name).suffix.lower().lstrip('.') in self.extensions)]
        except OSError as exc:
            self.grid.setEnabled(True)
            self.update_status()
            QMessageBox.warning(self, 'Cannot Read Folder', str(exc))
            return
        self.current_directory = folder
        self.path_label.setText(str(folder))
        self.up_button.setEnabled(folder.parent != folder)
        self.grid.blockSignals(True)
        self.grid.clear()
        self.image_items.clear()
        self.unavailable.clear()
        for directory, name in sorted(rows, key=lambda row: (not row[0], row[1].casefold())):
            path = str(folder / name)
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, ('directory' if directory else 'file', path))
            item.setToolTip(('Open folder: ' if directory else '') + path)
            item.setSizeHint(QSize(160, 168))
            self.grid.addItem(item)
            if not directory:
                self.image_items[path] = item
            item.setSelected(path in self.selection)
        self.grid.blockSignals(False)
        self.grid.setEnabled(True)
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem('All supported images', None)
        counts = Counter(Path(path).suffix.lower().lstrip('.') for path in self.image_items)
        grouped = set()
        for label, extensions in IMAGE_GROUPS:
            count = sum(counts[ext] for ext in extensions)
            grouped.update(extensions)
            if count:
                self.filter.addItem(f'{label} ({count})', frozenset(extensions))
        for ext in sorted(counts.keys() - grouped):
            self.filter.addItem(f'{ext.upper()} ({counts[ext]})', frozenset({ext}))
        self.filter.blockSignals(False)
        self.apply_filter()

    def apply_filter(self, *_):
        extensions = self.filter.currentData()
        self.grid.blockSignals(True)
        for path, item in self.image_items.items():
            item.setHidden(extensions is not None and Path(path).suffix.lower().lstrip('.') not in extensions)
            item.setSelected(path in self.selection)
        self.grid.blockSignals(False)
        self.grid.doItemsLayout()
        self.update_status()
        self.queue_thumbnails()

    def queue_thumbnails(self, *_):
        if self.finish_result is None and self.pending_directory is None:
            self.timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.queue_thumbnails()

    def load_visible_thumbnails(self):
        if self.worker is not None or self.finish_result is not None or self.pending_directory is not None:
            return
        viewport = self.grid.viewport().rect()
        paths = []
        for path, item in self.image_items.items():
            if item.isHidden() or not self.grid.visualItemRect(item).intersects(viewport):
                continue
            cached = self.thumbnail_cache.get(path)
            if cached is not None:
                try:
                    if identity(path) == cached[0]:
                        self.thumbnail_cache.move_to_end(path)
                        continue
                except (OSError, ValueError):
                    pass
                del self.thumbnail_cache[path]
            if path not in self.unavailable:
                paths.append(path)
        if not paths:
            return
        self.worker = ThumbnailWorker(paths[:16], QSize(140, 106), self)
        self.worker.thumbnail_ready.connect(self.receive_thumbnail)
        self.worker.finished.connect(self.thumbnails_finished)
        self.worker.start()

    def receive_thumbnail(self, path, image, stamp):
        if self.finish_result is not None or self.pending_directory is not None or path not in self.image_items:
            return
        try:
            valid = stamp is not None and identity(path) == stamp
        except (OSError, ValueError):
            valid = False
        if image.isNull() or not valid:
            self.unavailable.add(path)
        else:
            self.thumbnail_cache[path] = (stamp, image)
            self.thumbnail_cache.move_to_end(path)
            while len(self.thumbnail_cache) > self.cache_limit:
                self.thumbnail_cache.popitem(last=False)
        self.grid.viewport().update(self.grid.visualItemRect(self.image_items[path]))

    def thumbnails_finished(self):
        worker, self.worker = self.worker, None
        worker.wait()  # finished can be delivered just before native thread teardown.
        worker.deleteLater()
        if self.finish_result is not None:
            super().done(self.finish_result)
        elif self.pending_directory is not None:
            folder, self.pending_directory = self.pending_directory, None
            self.show_directory(folder)
        else:
            self.queue_thumbnails()

    def done(self, result):
        if self.finish_result is not None:
            return
        if result == QDialog.Accepted and not self.selection:
            return
        self.approved_paths = list(self.selection) if result == QDialog.Accepted else []
        self.finish_result = result
        self.timer.stop()
        self.grid.setEnabled(False)
        self.add_button.setEnabled(False)
        if self.worker is not None:
            self.worker.requestInterruption()
        else:
            super().done(result)

    def closeEvent(self, event):
        self.reject()
        if self.worker is not None:
            event.ignore()
        else:
            event.accept()


def choose_images(parent=None, directory='', *, title='Add Images', multiple=True,
                  extensions=None, accept_label='Add Selected Images'):
    """Return approved local paths; [] is a normal cancellation."""
    picker = ImagePicker(parent, directory, title=title, multiple=multiple,
                         extensions=extensions, accept_label=accept_label)
    result = picker.exec()
    paths = picker.selected_paths() if result == QDialog.Accepted else []
    picker.deleteLater()
    return paths


class ImageCanvas(QWidget):
    """Aspect-preserving software painting; decoded pixels are already bounded."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage(); self.message = 'Select an image'
        self.setMinimumSize(0, 110)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName('Selected photograph preview')

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPalette
        painter = QPainter(self); painter.fillRect(self.rect(), self.palette().brush(QPalette.Base))
        if self.image.isNull():
            painter.setPen(self.palette().color(QPalette.Text))
            painter.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.AlignCenter | Qt.TextWordWrap, self.message)
        else:
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            rect = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(rect, self.image)


class PhotoPreview(QWidget):
    """One asynchronous preview, latest selection wins; no full-size fallback."""
    idle = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = ImageCanvas(self); layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0); layout.addWidget(self.canvas)
        self.worker = None; self.requested = ''; self.stamp = None; self.stopped = False
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(150)
        self.timer.timeout.connect(self.start_preview)

    def set_path(self, path):
        if self.stopped: return
        if path == self.requested and (self.worker or self.timer.isActive()): return
        try: unchanged = path == self.requested and self.stamp is not None and identity(path) == self.stamp
        except (OSError, ValueError): unchanged = False
        if unchanged: return
        self.requested = path; self.stamp = None
        self.canvas.image = QImage(); self.canvas.message = 'Loading image preview…' if path else 'Select an image'
        self.canvas.setToolTip(path); self.canvas.update()
        if self.worker: self.worker.requestInterruption()
        self.timer.start()

    def start_preview(self):
        if self.worker or not self.requested or self.stopped: return
        ratio = self.devicePixelRatioF()
        size = QSize(min(1600, max(640, round(self.canvas.width()*ratio))),
                     min(1200, max(480, round(self.canvas.height()*ratio))))
        self.worker = ThumbnailWorker([self.requested], size, self)
        self.worker.thumbnail_ready.connect(self.receive_preview)
        self.worker.finished.connect(self.preview_finished); self.worker.start()

    def receive_preview(self, path, image, stamp):
        if path != self.requested or self.stopped: return
        try: valid = stamp is not None and identity(path) == stamp
        except (OSError, ValueError): valid = False
        if image.isNull() or not valid:
            self.canvas.image = QImage()
            self.canvas.message = 'Image preview unavailable.\nThe format may lack a safe thumbnail decoder.\nLocation metadata is inspected independently.'
        else: self.canvas.image = image; self.stamp = stamp
        self.canvas.update()

    def preview_finished(self):
        worker, self.worker = self.worker, None
        previous = worker.paths[0]; worker.deleteLater()
        if not self.stopped and previous != self.requested: self.start_preview()
        self.idle.emit()

    def stop(self):
        self.stopped = True; self.timer.stop()
        if self.worker: self.worker.requestInterruption()


class ImageList(QWidget):
    """Thumbnail, filename and status travel together, keyed by source path."""
    path_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QAbstractItemView, QComboBox, QLineEdit, QListWidget
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(); self.search.setPlaceholderText('Find an image…'); self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Find an image by filename or status'); layout.addWidget(self.search)
        self.sort = QComboBox(); self.sort.addItem('Selection order', False); self.sort.addItem('Filename order', True)
        self.sort.setAccessibleName('Image order'); layout.addWidget(self.sort)
        self.list = QListWidget(); self.list.setIconSize(QSize(72, 54))
        self.list.setWordWrap(False)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection); self.list.setTextElideMode(Qt.ElideMiddle)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.list.setMinimumWidth(0)
        self.list.setUniformItemSizes(True); self.list.setAccessibleName('Images, camera location and proposed changes')
        layout.addWidget(self.list, 1)
        self.items = {}; self.order = []
        self.search.textChanged.connect(self.filter_items)
        self.sort.currentIndexChanged.connect(self.sort_items)
        self.list.currentItemChanged.connect(self.selection_changed)

    def current_path(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ''

    def set_entries(self, rows):
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QListWidgetItem
        selected = self.current_path(); paths = {row['source'] for row in rows}
        self.list.blockSignals(True); self.list.setSortingEnabled(False)
        for path in list(self.items):
            if path not in paths:
                item = self.items.pop(path); self.list.takeItem(self.list.row(item))
        self.order = [row['source'] for row in rows]
        line_count = min(4, max([3, *[2 + row['caption'].count('\n') for row in rows]]))
        for row in rows:
            path = row['source']; item = self.items.get(path)
            if item is None:
                item = QListWidgetItem(QIcon.fromTheme('image-x-generic'), '', self.list)
                item.setData(Qt.UserRole, path); self.items[path] = item
            item.setText(Path(path).name + '\n' + row['caption'])
            # Preserve enabled/selectable flags: blocked images remain inspectable.
            item.setForeground(QBrush())
            item.setBackground(self.palette().brush(QPalette.AlternateBase) if row.get('blocked') else QBrush())
            item.setToolTip(path + '\n' + row.get('details', row['caption']))
            item.setSizeHint(QSize(0, max(62, self.fontMetrics().lineSpacing()*line_count + 10)))
        self.list.blockSignals(False)
        self.sort_items(); self.filter_items()
        item = self.items.get(selected)
        if item is None or item.isHidden(): item = next((self.list.item(i) for i in range(self.list.count()) if not self.list.item(i).isHidden()), None)
        self.list.setCurrentItem(item)
        self.path_changed.emit(self.current_path())

    def sort_items(self, *_):
        if self.sort.currentData(): self.list.sortItems(Qt.AscendingOrder)
        else:
            if [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())] == self.order: return
            current = self.current_path(); self.list.blockSignals(True)
            for path in self.order:
                item = self.items[path]; self.list.takeItem(self.list.row(item)); self.list.addItem(item)
            self.list.setCurrentItem(self.items.get(current)); self.list.blockSignals(False)

    def filter_items(self, *_):
        term = self.search.text().casefold()
        for item in self.items.values(): item.setHidden(term not in item.text().casefold())
        current = self.list.currentItem()
        if current and current.isHidden():
            self.list.setCurrentItem(next((self.list.item(i) for i in range(self.list.count()) if not self.list.item(i).isHidden()), None))

    def selection_changed(self, current, previous):
        self.path_changed.emit(current.data(Qt.UserRole) if current else '')

    def set_thumbnail(self, path, icon):
        if path in self.items: self.items[path].setIcon(icon)


def main():
    """Creation dispatcher protocol: only approved paths, separated by NUL."""
    import argparse
    import sys
    from PySide6.QtWidgets import QApplication

    parser = argparse.ArgumentParser(description='KIM6 thumbnail image picker')
    parser.add_argument('--title', default='Add Images')
    parser.add_argument('--directory', default='')
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    paths = choose_images(directory=args.directory, title=args.title,
                          extensions=CREATE_IMAGE_EXTENSIONS)
    if not paths:
        return 1
    sys.stdout.buffer.write(b''.join(os.fsencode(path) + b'\0' for path in paths))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
