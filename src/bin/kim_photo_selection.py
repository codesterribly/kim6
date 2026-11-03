"""Local image selection and bounded, orientation-aware read-only previews."""
from pathlib import Path

from PySide6.QtCore import QFile, QIODevice, QSize, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QBrush, QImage, QImageIOHandler, QImageReader, QPalette, QPixmap
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget
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
OTHER_PHOTOS = {'bmp', 'gif', 'jp2', 'j2k', 'jxl', 'ppm', 'pgm', 'pbm',
                'dng', 'cr2', 'cr3', 'nef', 'arw', 'raf', 'orf', 'rw2', 'pef', 'srw', 'psd'}


def photo_filters():
    readable = {bytes(fmt).decode('ascii', errors='ignore').lower() for fmt in QImageReader.supportedImageFormats()}
    other = sorted(OTHER_PHOTOS & (readable | {'dng', 'cr2', 'cr3', 'nef', 'arw', 'raf', 'orf', 'rw2', 'pef', 'srw', 'psd'}))
    groups = PHOTO_GROUPS + ([('Other readable images', tuple(other))] if other else [])
    def patterns(exts):
        return ' '.join(pattern for ext in exts for pattern in ('*.' + ext, '*.' + ext.upper()))
    supported = sorted({ext for _, exts in groups for ext in exts})
    return ['Supported images (' + patterns(supported) + ')',
            *[label + ' (' + patterns(exts) + ')' for label, exts in groups], 'All Files (*)']


def read_thumbnail(path, size):
    """Use descriptor-backed no-atime reads; never modify an image.

    Large images require decoder-native downscaling. Other decoders get a
    placeholder instead of a full-resolution allocation. QImageReader's own
    allocation bound additionally covers malformed input / plugin behavior.
    """
    before = identity(path)
    with inspection_path(path) as (_, fd):
        if descriptor_identity(fd) != before: raise ValueError('Image changed while opening preview')
        device = QFile()
        if not device.open(fd, QIODevice.ReadOnly): raise ValueError('Preview unavailable')
        try:
            reader = QImageReader(device)
            reader.setDecideFormatFromContent(True)
            reader.setAutoTransform(True)
            dimensions = reader.size()
            if not dimensions.isValid() or dimensions.width() * dimensions.height() > 1_000_000_000:
                raise ValueError('Preview dimensions unavailable or too large')
            native_scale = reader.supportsOption(QImageIOHandler.ScaledSize)
            if not native_scale and dimensions.width() * dimensions.height() > 1_000_000:
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


class PhotoChooser(QFileDialog):
    """Non-native Qt file chooser with a real highlighted-photo preview."""
    def __init__(self, parent=None, directory=''):
        super().__init__(parent, 'Choose a GPS source image', directory)
        self.setFileMode(QFileDialog.ExistingFile)
        self.setSupportedSchemes(['file'])
        self.setOption(QFileDialog.DontUseNativeDialog, True)
        self.setNameFilters(photo_filters())
        self.preview = QLabel('Highlight an image to preview it')
        self.preview.setAlignment(Qt.AlignCenter); self.preview.setWordWrap(True)
        self.preview.setMinimumSize(180, 160)
        self.caption = QLabel(); self.caption.setWordWrap(True); self.caption.setTextFormat(Qt.PlainText)
        panel = QWidget(); bar = QVBoxLayout(panel); bar.addWidget(self.preview, 1); bar.addWidget(self.caption)
        grid = self.layout()
        grid.addWidget(panel, 0, grid.columnCount(), grid.rowCount(), 1)
        self.resize(950, 600)
        self.preview_worker = None; self.requested = ''; self.finish_result = None
        self.preview_timer = QTimer(self); self.preview_timer.setSingleShot(True); self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.start_preview)
        self.currentChanged.connect(self.queue_preview)

    def queue_preview(self, path):
        self.requested = path
        self.preview.setText('Preview unavailable' if not Path(path).is_file() else 'Loading preview…')
        self.caption.setText(Path(path).name)
        if self.preview_worker: self.preview_worker.requestInterruption()
        self.preview_timer.start()

    def start_preview(self):
        if self.preview_worker or self.finish_result is not None: return
        if not Path(self.requested).is_file(): return
        self.preview_worker = ThumbnailWorker([self.requested], QSize(280, 220), self)
        self.preview_worker.thumbnail_ready.connect(self.receive_preview)
        self.preview_worker.finished.connect(self.preview_finished)
        self.preview_worker.start()

    def receive_preview(self, path, image, stamp):
        if path != self.requested: return
        try: valid = stamp is not None and identity(path) == stamp
        except (OSError, ValueError): valid = False
        if image.isNull() or not valid:
            self.preview.setText('Preview unavailable\nYou can still select this image.')
        else: self.preview.setPixmap(QPixmap.fromImage(image))

    def preview_finished(self):
        worker, self.preview_worker = self.preview_worker, None
        last = worker.paths[0]; worker.deleteLater()
        if self.finish_result is not None: super().done(self.finish_result)
        elif last != self.requested: self.start_preview()

    def done(self, result):
        self.preview_timer.stop()
        if self.preview_worker:
            self.finish_result = result; self.preview_worker.requestInterruption(); return
        super().done(result)


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
