#!/usr/bin/env python3
"""Shared visual controls for standalone and Recipe crop / visible overlays."""
import copy
from collections import OrderedDict
import html
import json
import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QAbstractItemView, QFileSystemModel, QListView, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QToolTip, QTreeView)

from kim_image_ops import (ANCHORS, ASPECTS, CROP_DEFAULTS, KINDS, OVERLAY_DEFAULTS,
    PLACEMENTS, TEXT_FIELDS, CAMERA_FIELDS, camera_fields, crop_plan, crop_ratio, watermark_fields)
from kim_recipe_core import RecipeError, validate


def paint_checkerboard(painter, rect):
    painter.fillRect(rect, QColor('#eeeeee'))
    for y in range(int(rect.top()), int(rect.bottom()) + 1, 12):
        for x in range(int(rect.left()), int(rect.right()) + 1, 12):
            if ((x - int(rect.left())) // 12 + (y - int(rect.top())) // 12) % 2:
                painter.fillRect(QRectF(x, y, min(12, rect.right() - x), min(12, rect.bottom() - y)), QColor('#bcbcbc'))


class WatermarkPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage(); self.message = 'Select an image to preview.'
        self.setMinimumSize(280, 250); self.setAccessibleName('Selected watermark image against a transparency checkerboard')

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_checkerboard(painter, self.rect())
        if self.image.isNull():
            painter.fillRect(self.rect(), self.palette().window())
            painter.setPen(self.palette().windowText().color())
            painter.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.AlignCenter | Qt.TextWordWrap, self.message)
        else:
            size = self.image.size().scaled(self.size() - QSize(12, 12), Qt.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                            size.width(), size.height())
            painter.setRenderHint(QPainter.SmoothPixmapTransform); painter.drawImage(target, self.image)
        painter.end()


class WatermarkPreviewWorker(QThread):
    """Only a bounded, generated PNG is decoded in Qt; tools run out of process."""
    def __init__(self, key, edge, parent):
        super().__init__(parent)
        self.key, self.edge = key, edge
        self.image = QImage(); self.metadata = {}; self.error = ''; self.cancelled = False
        self.state = 'loading'

    def cancel(self):
        self.cancelled = True; self.requestInterruption()

    def run(self):
        from kim_process import inspection_context, run_process
        try:
            with tempfile.TemporaryDirectory(prefix='kim6-picker-') as workspace:
                env = dict(os.environ, TMPDIR=workspace, MAGICK_TEMPORARY_PATH=workspace,
                           MAGICK_MEMORY_LIMIT='256MiB', MAGICK_MAP_LIMIT='512MiB',
                           MAGICK_DISK_LIMIT='1GiB', MAGICK_THREAD_LIMIT='2', MAGICK_TIME_LIMIT='12',
                           MAGICK_WIDTH_LIMIT='100000', MAGICK_HEIGHT_LIMIT='100000')
                # All child temporary work, including PSD adapters, stays inside
                # this tree even when timeout/cancellation kills the child.
                try:
                    with inspection_context(cancelled=lambda: self.cancelled or self.isInterruptionRequested()):
                        result = run_process([sys.executable, str(Path(__file__).with_name('kim_image_ops.py')),
                                              '--watermark-preview', self.key[0], str(self.edge), workspace],
                                             timeout=15 if self.edge > 144 else 8, env=env, text=True)
                    if result.returncode:
                        self.error = result.stderr.strip()[-600:] or 'The preview reader could not render this image.'
                    else:
                        self.image = QImage(str(Path(workspace, 'preview.png')))
                        if self.image.isNull(): self.error = 'The preview reader did not produce an image.'
                finally:
                    info = Path(workspace, 'info.json')
                    if info.is_file(): self.metadata = json.loads(info.read_text())
        except Exception as exc:
            self.error = str(exc)
        if not self.image.isNull(): self.state = 'ready'
        elif self.error.startswith('Unsupported input image format: ') and not self.error.endswith(('None', 'unknown')):
            self.state = 'unsupported'
        elif any(reason in self.error.lower() for reason in ('no decode delegate', 'no decoding delegate',
                'security policy', 'not authorized', 'unavailable in recipes', 'image sequences are unavailable',
                'only single-frame images', 'safe preview dimensions', 'missing dependency')):
            self.state = 'unavailable'
        else: self.state = 'failed'


THUMBNAIL_STATES = {'loading': 'Waiting for thumbnail…', 'ready': 'Preview ready',
                    'unsupported': 'Unsupported file', 'unavailable': 'Format cannot be previewed',
                    'failed': 'Image preview failed'}


def thumbnail_icon(image=None, state='loading'):
    tile = QImage(144, 108, QImage.Format_ARGB32_Premultiplied); painter = QPainter(tile)
    paint_checkerboard(painter, tile.rect())
    if image is None or image.isNull():
        painter.setPen(QColor('#222222'))
        painter.drawText(tile.rect().adjusted(5, 5, -5, -5), Qt.AlignCenter | Qt.TextWordWrap, THUMBNAIL_STATES[state])
    else:
        size = image.size().scaled(tile.size(), Qt.KeepAspectRatio)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(QRectF((144 - size.width()) / 2, (108 - size.height()) / 2,
                                size.width(), size.height()), image)
    painter.end()
    return QIcon(QPixmap.fromImage(tile))


def watermark_file_key(index):
    model, source = index.model(), index
    while hasattr(model, 'mapToSource'):
        source = model.mapToSource(source); model = model.sourceModel()
    if not isinstance(model, QFileSystemModel): return None
    info = model.fileInfo(source)
    if not info.isFile() or info.isSymLink(): return None
    return (info.absoluteFilePath(), info.size(), info.lastModified().toMSecsSinceEpoch())


class WatermarkThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, picker):
        super().__init__(picker); self.picker = picker

    def paint(self, painter, option, index):
        # Schedule from an explicit Python paint path. Do not rely on the Qt
        # base delegate calling our initStyleOption virtual while painting.
        decorated = QStyleOptionViewItem(option)
        self.initStyleOption(decorated, index)
        self.decorate(decorated, index, request=True)
        style = decorated.widget.style() if decorated.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, decorated, painter, decorated.widget)

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        self.decorate(option, index)

    def decorate(self, option, index, request=False):
        if index.column() != 0: return
        key = watermark_file_key(index)
        if key is None: return
        # Offscreen size hints never enqueue decoder work.
        option.icon = self.picker.thumbnail(key, request=request)
        option.features |= QStyleOptionViewItem.HasDecoration

    def helpEvent(self, event, view, option, index):
        key = watermark_file_key(index)
        if key is None: return super().helpEvent(event, view, option, index)
        record = self.picker.cache.get(key, dict(state='loading', error=''))
        text = key[0] + '\n' + THUMBNAIL_STATES[record['state']]
        if record['error']: text += '\n' + record['error']
        QToolTip.showText(event.globalPos(), '<qt>' + html.escape(text).replace('\n', '<br>') + '</qt>', view)
        return True


class WatermarkImagePicker(QFileDialog):
    """Keep Qt's file navigation/entry/filtering, adding real lazy thumbnails."""
    def __init__(self, parent, current=''):
        super().__init__(parent, 'Choose Watermark Image')
        self.setOption(QFileDialog.DontUseNativeDialog, True)
        self.setOption(QFileDialog.DontUseCustomDirectoryIcons, True)
        self.setFileMode(QFileDialog.ExistingFile); self.setAcceptMode(QFileDialog.AcceptOpen)
        # Match the engine's accepted inputs, regardless of Qt's decoder plugins.
        self.setNameFilters([
            'Watermark images (*.jpg *.jpeg *.jpe *.jfif *.png *.webp *.avif *.tif *.tiff *.bmp *.ppm *.pnm *.heic *.heif *.psd *.gif *.jp2 *.jxl)',
            'JPEG (*.jpg *.jpeg *.jpe *.jfif)', 'PNG (*.png)', 'WebP (*.webp)', 'AVIF (*.avif)',
            'TIFF (*.tif *.tiff)', 'HEIC / HEIF (*.heic *.heif)', 'Photoshop (*.psd)',
            'Other watermark images (*.bmp *.ppm *.pnm *.gif *.jp2 *.jxl)', 'All Files (*)'])
        self.cache = OrderedDict(); self.queue = OrderedDict()
        self.state_icons = {state: thumbnail_icon(state=state) for state in THUMBNAIL_STATES if state != 'ready'}
        self.thumb_worker = None; self.preview_worker = None; self.preview_key = None
        self.closing = False; self.close_result = QDialog.Rejected
        self.thumb_timer = QTimer(self); self.thumb_timer.setSingleShot(True); self.thumb_timer.timeout.connect(self.load_thumbnail)
        self.preview_timer = QTimer(self); self.preview_timer.setSingleShot(True); self.preview_timer.setInterval(120)
        self.preview_timer.timeout.connect(self.load_selected)
        self.visible_timer = QTimer(self); self.visible_timer.setSingleShot(True)
        self.visible_timer.setInterval(30); self.visible_timer.timeout.connect(self.schedule_visible_thumbnails)
        self.setViewMode(QFileDialog.List)
        self.views = [v for name, cls in (('listView', QListView), ('treeView', QTreeView))
                      if (v := self.findChild(cls, name)) is not None]
        self.thumbnail_delegates = []
        for view in self.views:
            delegate = WatermarkThumbnailDelegate(self); self.thumbnail_delegates.append(delegate)
            view.setItemDelegate(delegate)
            view.setMinimumWidth(300); view.viewport().installEventFilter(self)
            view.verticalScrollBar().valueChanged.connect(self.refresh_thumbnail_requests)
            view.horizontalScrollBar().valueChanged.connect(self.refresh_thumbnail_requests)
            if isinstance(view, QListView):
                view.setViewMode(QListView.IconMode); view.setFlow(QListView.LeftToRight)
                view.setWrapping(True); view.setResizeMode(QListView.Adjust); view.setMovement(QListView.Static)
                view.setIconSize(QSize(144, 108)); view.setGridSize(QSize(170, 144)); view.setWordWrap(True)
                view.setUniformItemSizes(True); view.setLayoutMode(QListView.Batched); view.setBatchSize(128)
            else:
                view.setIconSize(QSize(64, 48)); view.setUniformRowHeights(True)
            model = view.model()
            model.rowsInserted.connect(self.refresh_thumbnail_requests)
            model.modelReset.connect(self.refresh_thumbnail_requests)
            while hasattr(model, 'sourceModel'): model = model.sourceModel()
            if isinstance(model, QFileSystemModel):
                model.directoryLoaded.connect(self.refresh_thumbnail_requests)
        panel = QWidget(self); panel_layout = QVBoxLayout(panel)
        self.selected_preview = WatermarkPreview(); panel_layout.addWidget(self.selected_preview, 1)
        self.preview_info = QLabel('Dimensions and detected format appear here.'); self.preview_info.setWordWrap(True)
        self.preview_info.setTextFormat(Qt.PlainText); panel_layout.addWidget(self.preview_info)
        note = QLabel('Transparency is shown against a checkerboard. Preview availability does not determine whether a file is valid.'); note.setWordWrap(True)
        panel_layout.addWidget(note)
        # Qt's file dialog already has a sidebar/browser splitter. Nest that
        # browser region with our preview; retain navigation, entry and buttons.
        layout = self.layout(); browser_split = self.findChild(QSplitter, 'splitter')
        if browser_split is None:
            browser_split = self.views[0].parentWidget()
            while browser_split.parentWidget() is not self and layout.indexOf(browser_split) < 0:
                browser_split = browser_split.parentWidget()
        self.preview_split = QSplitter(Qt.Horizontal, self)
        layout.replaceWidget(browser_split, self.preview_split)
        self.preview_split.addWidget(browser_split); self.preview_split.addWidget(panel)
        self.preview_split.setChildrenCollapsible(False); self.preview_split.setHandleWidth(8)
        self.preview_split.handle(1).setToolTip('Drag to resize the thumbnail browser and image preview')
        self.preview_split.setStretchFactor(0, 2); self.preview_split.setStretchFactor(1, 1)
        self.preview_split.setSizes([700, 360]); panel.setMinimumWidth(280)
        self.resize(1100, 650)
        self.currentChanged.connect(self.select_preview); self.directoryEntered.connect(self.directory_changed)
        self.filterSelected.connect(self.refresh_thumbnail_requests)
        self.refresh_thumbnail_requests()
        entry = self.findChild(QLineEdit, 'fileNameEdit')
        if entry: entry.textEdited.connect(self.filename_edited)
        if current:
            self.setDirectory(str(Path(current).parent)); self.selectFile(current); self.select_preview(current)

    def filename_edited(self, text):
        paths = self.selectedFiles()
        self.select_preview(paths[0] if paths else '')

    def thumbnail(self, key, request=False):
        if key in self.cache:
            self.cache.move_to_end(key); return self.cache[key]['icon']
        if request and not self.closing and (self.thumb_worker is None or self.thumb_worker.key != key):
            self.queue[key] = None
            while len(self.queue) > 64: self.queue.popitem(last=False)
            if not self.thumb_timer.isActive(): self.thumb_timer.start(0)
        return self.state_icons['loading']

    def load_thumbnail(self):
        if self.closing or self.thumb_worker or not self.queue: return
        key, _ = self.queue.popitem(last=False)
        self.thumb_worker = WatermarkPreviewWorker(key, 144, self)
        self.thumb_worker.finished.connect(self.thumbnail_finished); self.thumb_worker.start()

    @Slot()
    def thumbnail_finished(self):
        worker, self.thumb_worker = self.thumb_worker, None
        if not worker.cancelled and not self.closing:
            self.cache[worker.key] = dict(icon=thumbnail_icon(worker.image) if worker.state == 'ready' else self.state_icons[worker.state],
                                          state=worker.state, error=worker.error)
            while len(self.cache) > 128: self.cache.popitem(last=False)
            for view in self.views: view.viewport().update()
        worker.deleteLater()
        if self.closing: self.finish_close()
        else:
            self.thumb_timer.start(0)
            self.visible_timer.start()

    def select_preview(self, path):
        if self.closing: return
        self.preview_key = (path,) if path and not os.path.isdir(path) else None
        if self.preview_worker: self.preview_worker.cancel()
        self.selected_preview.image = QImage()
        self.selected_preview.message = 'Loading preview…' if self.preview_key else 'Select an image to preview.'
        self.selected_preview.update(); self.preview_info.setText(Path(path).name if path else '')
        self.preview_timer.start()

    def load_selected(self):
        if self.closing or not self.preview_key or self.preview_worker: return
        self.preview_worker = WatermarkPreviewWorker(self.preview_key, 720, self)
        self.preview_worker.finished.connect(self.selected_finished); self.preview_worker.start()

    @Slot()
    def selected_finished(self):
        worker, self.preview_worker = self.preview_worker, None
        if not self.closing and worker.key == self.preview_key and not worker.cancelled:
            self.selected_preview.image = worker.image
            self.selected_preview.message = THUMBNAIL_STATES[worker.state] + '.\nYou can still select this file; KIM6 validates it before execution.'
            info = worker.metadata
            details = f"{info['width']} × {info['height']} pixels · {info['format']}" if info else 'Dimensions / format unavailable'
            self.preview_info.setText(details + ('\n' + THUMBNAIL_STATES[worker.state] + ': ' + worker.error if worker.error else ''))
            self.selected_preview.update()
        worker.deleteLater()
        if self.closing: self.finish_close()
        elif worker.cancelled or worker.key != self.preview_key: self.preview_timer.start()

    def directory_changed(self, directory):
        if self.thumb_worker: self.thumb_worker.cancel()
        self.refresh_thumbnail_requests()
        self.select_preview('')

    def refresh_thumbnail_requests(self, *_):
        if self.closing: return
        self.queue.clear()
        # Scrolling must not repeatedly cancel a supported image's decode.
        self.visible_timer.start()
        for view in self.views: view.viewport().update()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Resize) and hasattr(self, 'visible_timer') and not self.closing:
            self.visible_timer.start()
        return super().eventFilter(watched, event)

    def schedule_visible_thumbnails(self):
        """Replenish bounded work after model loads, resizing and completion.

        Scan viewport positions, never enumerate/decode an entire directory.
        This also covers rows Qt painted before its filesystem model populated.
        """
        if self.closing: return
        for view in self.views:
            if not view.isVisible(): continue
            seen = set(); viewport = view.viewport()
            for y in range(0, viewport.height(), 20):
                for x in range(0, viewport.width(), 40):
                    index = view.indexAt(QPoint(x, y))
                    if not index.isValid(): continue
                    index = index.siblingAtColumn(0)
                    if index in seen: continue
                    seen.add(index)
                    key = watermark_file_key(index)
                    if key is not None: self.thumbnail(key, request=True)

    def done(self, result):
        if self.closing: return
        self.closing = True; self.close_result = result
        self.queue.clear(); self.thumb_timer.stop(); self.preview_timer.stop(); self.visible_timer.stop()
        for worker in (self.thumb_worker, self.preview_worker):
            if worker: worker.cancel()
        self.finish_close()

    def finish_close(self):
        if not self.thumb_worker and not self.preview_worker: super().done(self.close_result)


class CropCanvas(QWidget):
    """Image-space selection with bounded edge, corner and whole-rectangle drags."""
    selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage(); self.selection = QRectF(0, 0, 1, 1)
        self.ratio = None; self.drag = None; self.editable = False
        self.setMinimumSize(340, 300); self.setMouseTracking(True)
        self.setAccessibleName('Image preview; drag crop edges, corners or the selection interior')
        self.setToolTip('Drag an edge or corner to resize; drag inside to move. Exact pixel controls are available beside the image.')

    def image_box(self):
        if self.image.isNull(): return QRectF()
        box = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        scale = min(box.width() / self.image.width(), box.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def selection_box(self):
        b = self.image_box(); r = self.selection
        return QRectF(b.x() + r.x() * b.width(), b.y() + r.y() * b.height(), r.width() * b.width(), r.height() * b.height())

    def paintEvent(self, _event):
        painter = QPainter(self); painter.fillRect(self.rect(), self.palette().window())
        if self.image.isNull():
            painter.drawText(self.rect(), Qt.AlignCenter, 'Choose an image to display a real preview.'); return
        box = self.image_box(); painter.drawImage(box, self.image)
        if not self.editable: return
        r = self.selection_box()
        painter.fillRect(QRectF(box.left(), box.top(), box.width(), r.top() - box.top()), QColor(0, 0, 0, 135))
        painter.fillRect(QRectF(box.left(), r.bottom(), box.width(), box.bottom() - r.bottom()), QColor(0, 0, 0, 135))
        painter.fillRect(QRectF(box.left(), r.top(), r.left() - box.left(), r.height()), QColor(0, 0, 0, 135))
        painter.fillRect(QRectF(r.right(), r.top(), box.right() - r.right(), r.height()), QColor(0, 0, 0, 135))
        painter.setPen(QPen(Qt.white, 2)); painter.drawRect(r)
        painter.setPen(QPen(Qt.black, 1, Qt.DashLine)); painter.drawRect(r)
        painter.setPen(QPen(Qt.white, 1, Qt.DotLine))
        for fraction in (1 / 3, 2 / 3):
            painter.drawLine(QPointF(r.x() + r.width() * fraction, r.top()), QPointF(r.x() + r.width() * fraction, r.bottom()))
            painter.drawLine(QPointF(r.left(), r.y() + r.height() * fraction), QPointF(r.right(), r.y() + r.height() * fraction))
        painter.setBrush(Qt.white); painter.setPen(Qt.black)
        for x, y in ((r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()), (r.right(), r.bottom()),
                     (r.center().x(), r.top()), (r.center().x(), r.bottom()), (r.left(), r.center().y()), (r.right(), r.center().y())):
            painter.drawRect(QRectF(x - 4, y - 4, 8, 8))

    def hit(self, point):
        r = self.selection_box()
        if not r.adjusted(-9, -9, 9, 9).contains(point): return ''
        horizontal = 'l' if abs(point.x() - r.left()) <= 9 else 'r' if abs(point.x() - r.right()) <= 9 else ''
        vertical = 't' if abs(point.y() - r.top()) <= 9 else 'b' if abs(point.y() - r.bottom()) <= 9 else ''
        return horizontal + vertical or ('move' if r.contains(point) else '')

    def mousePressEvent(self, event):
        if not self.editable or self.image.isNull() or event.button() != Qt.LeftButton: return
        mode = self.hit(event.position())
        if mode: self.drag = (mode, event.position(), QRectF(self.selection)); event.accept()

    def mouseMoveEvent(self, event):
        if not self.editable or self.image.isNull(): return
        if not self.drag:
            mode = self.hit(event.position())
            self.setCursor({'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor, 't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
                            'lt': Qt.SizeFDiagCursor, 'rb': Qt.SizeFDiagCursor, 'rt': Qt.SizeBDiagCursor,
                            'lb': Qt.SizeBDiagCursor, 'move': Qt.SizeAllCursor}.get(mode, Qt.ArrowCursor)); return
        mode, start, original = self.drag; box = self.image_box()
        dx, dy = (event.position().x() - start.x()) / box.width(), (event.position().y() - start.y()) / box.height()
        if mode == 'move':
            result = QRectF(min(1 - original.width(), max(0, original.x() + dx)),
                            min(1 - original.height(), max(0, original.y() + dy)), original.width(), original.height())
        else:
            left, right, top, bottom = original.left(), original.right(), original.top(), original.bottom()
            min_w, min_h = min(.01, 2 / box.width()), min(.01, 2 / box.height())
            if 'l' in mode: left = max(0, min(right - min_w, left + dx))
            if 'r' in mode: right = min(1, max(left + min_w, right + dx))
            if 't' in mode: top = max(0, min(bottom - min_h, top + dy))
            if 'b' in mode: bottom = min(1, max(top + min_h, bottom + dy))
            if self.ratio:
                # Convert physical aspect to normalized image coordinates.
                ratio = self.ratio * box.height() / box.width()
                w, h = right - left, bottom - top
                if mode in ('t', 'b'): w = h * ratio
                else: h = w / ratio
                ax = original.right() if 'l' in mode else original.left() if 'r' in mode else original.center().x()
                ay = original.bottom() if 't' in mode else original.top() if 'b' in mode else original.center().y()
                max_w = ax if 'l' in mode else 1 - ax if 'r' in mode else 2 * min(ax, 1 - ax)
                max_h = ay if 't' in mode else 1 - ay if 'b' in mode else 2 * min(ay, 1 - ay)
                scale = min(1, max_w / w, max_h / h); w *= scale; h *= scale
                left = ax - w if 'l' in mode else ax if 'r' in mode else ax - w / 2
                top = ay - h if 't' in mode else ay if 'b' in mode else ay - h / 2
                right, bottom = left + w, top + h
            result = QRectF(left, top, right - left, bottom - top)
        self.selection = result; self.update(); self.selected.emit(result)

    def mouseReleaseEvent(self, event):
        if self.drag: self.drag = None; event.accept()


class VisualWorker(QThread):
    stage_changed = Signal(str)

    def __init__(self, recipe, files, sample, prefix, step, generation, parent):
        super().__init__(parent)
        self.recipe, self.files, self.sample = copy.deepcopy(recipe), list(files), sample
        self.prefix, self.step, self.generation = copy.deepcopy(prefix), copy.deepcopy(step), generation
        self.rows = []; self.image = QImage(); self.dimensions = None; self.error = None; self.rendered_overlay = False

    def run(self):
        from kim_psd_source import source_session
        from kim_process import inspection_context, checkpoint
        from kim_recipe_core import preview
        from kim_recipe_image import ImageHandler, run, srgb_profile
        from kim_image_ops import overlay_arguments
        try:
            with inspection_context(self.stage_changed.emit, self.isInterruptionRequested):
                self.rows = preview(self.recipe, self.files)
                checkpoint()
                if not self.sample: return
                with source_session(), tempfile.TemporaryDirectory(prefix='kim6-visual-') as workspace:
                    source = Path(self.sample)
                    before = source.stat()
                    if source.is_symlink() or not source.is_file(): raise RecipeError('Preview source must be a regular image')
                    media = ImageHandler()
                    state = None
                    if self.step['op'] == 'image.overlay':
                        try:
                            # Plan the complete recipe: later format declarations
                            # and metadata policies can affect the final ICC and
                            # opaque output background even without later geometry.
                            state = media.plan(source, self.recipe['steps'], 1)
                            self.rendered_overlay = True
                        except (RecipeError, OSError) as exc:
                            self.error = str(exc)
                    if state is None:
                        # Show the real oriented input even while an overlay is
                        # incomplete. This preview-only PNG declaration never
                        # changes a recipe or its output format.
                        steps = [copy.deepcopy(s) for s in self.prefix if s['op'].startswith('image.') and
                                 s['op'] not in ('image.convert', 'image.compress', 'image.overlay')]
                        steps.insert(0, {'op': 'image.convert', 'format': 'png', 'quality': 90})
                        steps.append({'op': 'image.auto_orient'})
                        for step in steps: media.validate_step(step)
                        media.validate_order(steps)
                        state = media.plan(source, steps, 1)
                    self.dimensions = state['properties']['width'], state['properties']['height']
                    overlay_args = overlay_arguments(source, state, workspace)
                    output = Path(workspace) / 'preview.png'
                    background = ['-background', 'white', '-alpha', 'remove', '-alpha', 'off'] if self.rendered_overlay and state['format'] in ('jpeg', 'bmp', 'pdf', 'heic', 'heif') else []
                    run(['magick', str(source), *state['pixel_args'], *overlay_args, *background,
                         '-profile', srgb_profile(), '-thumbnail', '1000x750>', '-strip', 'PNG:' + str(output)])
                    after = source.stat()
                    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise RecipeError('Preview source changed; select it again')
                    self.image = QImage(str(output))
                    if self.image.isNull(): raise RecipeError('Cannot display the rendered preview')
        except Exception as exc:
            self.error = str(exc)


class ImageOperationDialog(QDialog):
    def __init__(self, step, files=(), parent=None, recipe=None, row=None):
        super().__init__(parent)
        self.step = copy.deepcopy(step); self.files = list(files); self.recipe = copy.deepcopy(recipe); self.row = row
        self.standalone = recipe is None; self.crop = step['op'] == 'image.crop'
        self.loading = True; self.worker = None; self.generation = 0; self.pending = False; self.closing = False
        self.dimensions = None; self.checked_generation = None
        self.fields = {}
        self.setWindowTitle('Crop Image' if self.crop else 'Add Watermark / Overlay'); self.resize(1160, 870)
        layout = QVBoxLayout(self)
        note = QLabel('One configuration applies to every selected image. Manual crop areas use relative coordinates; exact crop pixels are checked individually. The table shows each image’s coordinates and output size.' if self.crop else
                      'Visible overlays change image pixels independently of embedded rights metadata. Size and margins are percentages of each final image’s shorter edge; relative placement applies to every selected image.')
        note.setWordWrap(True); layout.addWidget(note)
        selection = QHBoxLayout(); selection.addWidget(QLabel('Preview image:'))
        self.images = QComboBox()
        for path in self.files: self.images.addItem(Path(path).name, str(path))
        selection.addWidget(self.images, 1); choose = QPushButton('Choose Image…'); choose.clicked.connect(self.choose_image); selection.addWidget(choose)
        layout.addLayout(selection); self.images.currentIndexChanged.connect(self.schedule)
        split = QSplitter(Qt.Horizontal); split.setChildrenCollapsible(False); split.setHandleWidth(8); layout.addWidget(split, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); controls = QWidget(); self.form = QFormLayout(controls)
        scroll.setWidget(controls); scroll.setMinimumWidth(380); split.addWidget(scroll)
        self.canvas = CropCanvas(); self.canvas.editable = self.crop; self.canvas.selected.connect(self.manual_selection); split.addWidget(self.canvas)
        split.handle(1).setToolTip('Drag to resize the controls and image preview')
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        split.setSizes([420, 700])
        if self.crop: self.crop_controls()
        else: self.overlay_controls()
        if self.standalone: self.output_controls()
        self.geometry = QLabel(); self.geometry.setTextFormat(Qt.PlainText); self.geometry.setWordWrap(True); layout.addWidget(self.geometry)
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(['Image', 'Original dimensions', 'Crop / overlay plan', 'Planned output / issues'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setResizeContentsPrecision(40)

        header.setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(
            2, QHeaderView.Interactive
        )
        header.setSectionResizeMode(
            3, QHeaderView.Interactive
        )

        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 260)
        self.table.setMinimumHeight(145)
        layout.addWidget(self.table)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        safety = QLabel('Original images stay unchanged. Outputs use the existing verified, create-only publication path; occupied filenames receive a number.')
        safety.setWordWrap(True); layout.addWidget(safety)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.apply = self.buttons.button(QDialogButtonBox.Ok); self.apply.setText('Review Outputs…' if self.standalone else 'Use Settings')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(250); self.timer.timeout.connect(self.refresh)
        self.loading = False; self.sync_visibility(); self.schedule()

    def combo(self, key, title, values):
        widget = QComboBox()
        for label, value in values: widget.addItem(label, value)
        widget.setCurrentIndex(widget.findData(self.step.get(key))); widget.setAccessibleName(title)
        self.fields[key] = widget; self.form.addRow(title, widget)
        widget.currentIndexChanged.connect(lambda *_: self.control_changed(key))
        return widget

    def spin(self, key, title, low, high, decimals=0):
        widget = QDoubleSpinBox() if decimals else QSpinBox(); widget.setRange(low, high)
        if decimals: widget.setDecimals(decimals)
        widget.setValue(self.step[key]); widget.setAccessibleName(title)
        self.fields[key] = widget; self.form.addRow(title, widget)
        widget.valueChanged.connect(lambda *_: self.control_changed(key)); return widget

    def check(self, key, title):
        widget = QCheckBox(title); widget.setChecked(self.step[key]); self.fields[key] = widget
        self.form.addRow(widget); widget.toggled.connect(lambda *_: self.control_changed(key)); return widget

    def crop_controls(self):
        self.combo('aspect', 'Aspect ratio', ASPECTS)
        self.spin('ratio_width', 'Custom ratio width', 1, 100000); self.spin('ratio_height', 'Custom ratio height', 1, 100000)
        self.combo('area', 'Crop area', [('Largest area at ratio', 'aspect'), ('Exact crop pixels', 'pixels'), ('Manual relative area', 'manual')])
        self.spin('crop_width', 'Crop width (pixels)', 1, 100000); self.spin('crop_height', 'Crop height (pixels)', 1, 100000)
        self.combo('placement', 'Crop position', PLACEMENTS)
        hint = QLabel('Drag the rectangle edges or corners to select a manual area. Drag inside to move it. Pixel controls provide a keyboard alternative.')
        hint.setWordWrap(True); self.form.addRow(hint)
        for key, title in [('x', 'Manual left (%)'), ('y', 'Manual top (%)'), ('w', 'Manual width (%)'), ('h', 'Manual height (%)')]:
            widget = QDoubleSpinBox(); widget.setRange(0 if key in ('x', 'y') else .001, 100); widget.setDecimals(3)
            widget.setValue(self.step[key] * 100); widget.setAccessibleName(title); self.fields[key] = widget; self.form.addRow(title, widget)
            widget.valueChanged.connect(lambda *_, k=key: self.control_changed(k))
        resize_note = QLabel('Output resizing is separate from the crop area and always preserves proportions.')
        resize_note.setWordWrap(True); self.form.addRow(resize_note)
        self.check('resize', 'Resize cropped output to target pixels')
        self.spin('target_width', 'Target width (pixels)', 1, 100000); self.spin('target_height', 'Target height (pixels)', 1, 100000)
        self.check('upscale', 'Allow enlargement of cropped output')

    def overlay_controls(self):
        self.combo('kind', 'Overlay type', KINDS)
        self.step['camera_fields'] = camera_fields(self.step)
        self.camera_grid = QWidget(); grid = QGridLayout(self.camera_grid); grid.setContentsMargins(0, 0, 0, 0)
        for index, (label, key) in enumerate(CAMERA_FIELDS):
            checkbox = QCheckBox(label); checkbox.setChecked(self.step['camera_fields'][key])
            checkbox.toggled.connect(lambda checked, k=key: self.camera_field_changed(k, checked))
            grid.addWidget(checkbox, index // 2, index % 2)
        self.form.addRow('Camera & EXIF details', self.camera_grid)
        self.step['text_fields'] = watermark_fields(self.step)
        self.watermark_widgets = {}
        for label, key in TEXT_FIELDS:
            container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0)
            selected = QCheckBox(label); selected.setChecked(self.step['text_fields'][key]['selected']); layout.addWidget(selected)
            editor = QPlainTextEdit(); editor.setMaximumHeight(70); editor.setAccessibleName(label + ' watermark text'); layout.addWidget(editor)
            mode = QLabel(); mode.setWordWrap(True); mode.setTextFormat(Qt.PlainText); layout.addWidget(mode)
            reset = None
            if key != 'custom':
                reset = QPushButton('Reset from Settings'); reset.setAccessibleName('Reset ' + label + ' from Settings')
                reset.clicked.connect(lambda checked=False, k=key: self.reset_watermark_field(k)); layout.addWidget(reset)
            self.watermark_widgets[key] = (container, selected, editor, mode, reset)
            self.form.addRow(container); self.show_watermark_field(key)
            selected.toggled.connect(lambda checked, k=key: self.watermark_field_changed(k, selection=checked))
            editor.textChanged.connect(lambda k=key: self.watermark_field_changed(k))
        self.combo('source', 'Caption source', [('Custom caption', 'custom'), ('Embedded image caption', 'embedded')])
        self.fields['value'] = QPlainTextEdit(); self.fields['value'].setMaximumHeight(95); self.fields['value'].setAccessibleName('Custom caption text')
        self.form.addRow('Caption', self.fields['value'])
        self.show_text_value(); self.fields['value'].textChanged.connect(lambda: self.control_changed('value'))
        self.fields['logo'] = QLineEdit(self.step['logo']); self.fields['logo'].setAccessibleName('Local watermark image filename')
        self.form.addRow('Watermark image', self.fields['logo']); self.fields['logo'].textChanged.connect(lambda: self.control_changed('logo'))
        self.logo_button = QPushButton('Choose Watermark Image…'); self.logo_button.clicked.connect(self.choose_logo); self.form.addRow(self.logo_button)
        self.combo('anchor', 'Position', ANCHORS)
        self.spin('margin', 'Margin (% of shorter edge)', 0, 40, 2)
        self.spin('size', 'Size (% of shorter edge)', .1, 100, 2)
        self.size_note = QLabel('Text size is font height; logo size is its bounding box.'); self.size_note.setWordWrap(True); self.form.addRow(self.size_note)
        self.spin('opacity', 'Opacity (%)', 0, 100)
        self.fields['font'] = QFontComboBox(); self.fields['font'].setCurrentFont(QFont(self.step['font']))
        self.fields['font'].setAccessibleName('Text overlay font'); self.form.addRow('Font', self.fields['font'])
        self.fields['font'].currentFontChanged.connect(lambda *_: self.control_changed('font'))
        self.fields['color'] = QLineEdit(self.step['color']); self.fields['color'].setAccessibleName('Text color, hexadecimal RGB')
        self.form.addRow('Text color', self.fields['color']); self.fields['color'].textChanged.connect(lambda: self.control_changed('color'))
        self.color_button = QPushButton('Choose Color…'); self.color_button.clicked.connect(self.choose_color); self.form.addRow(self.color_button)
        self.check('bold', 'Bold'); self.check('italic', 'Italic')
        self.combo('assistance', 'Readability', [('Outline', 'outline'), ('Shadow', 'shadow'), ('None', 'none')])

    def output_controls(self):
        self.form.addRow(QLabel('Output'))
        self.output_format = QComboBox(); self.output_format.addItem('Keep source format', None)
        from kim_recipe_image import FORMATS
        for fmt in FORMATS: self.output_format.addItem(fmt.upper(), fmt)
        self.output_format.setAccessibleName('Output image format'); self.form.addRow('Format', self.output_format)
        self.output_format.currentIndexChanged.connect(self.schedule)
        self.destination = QComboBox()
        for label, value in [('Beside each original', 'beside'), ('Subfolder beside each original', 'subfolder'), ('One directory', 'directory')]: self.destination.addItem(label, value)
        self.form.addRow('Destination', self.destination); self.destination.currentIndexChanged.connect(self.schedule)
        self.folder = QLineEdit('cropped' if self.crop else 'watermarked'); self.form.addRow('Subfolder', self.folder); self.folder.textChanged.connect(self.schedule)
        self.directory = QLineEdit(); self.form.addRow('Directory', self.directory); self.directory.textChanged.connect(self.schedule)
        self.directory_button = QPushButton('Choose Output Directory…'); self.directory_button.clicked.connect(self.choose_directory); self.form.addRow(self.directory_button)

    def show_text_value(self):
        value = self.step['value'] or ''
        self.fields['value'].blockSignals(True); self.fields['value'].setPlainText(value); self.fields['value'].blockSignals(False)

    def show_watermark_field(self, key):
        _, selected, editor, mode, reset = self.watermark_widgets[key]
        value = self.step['text_fields'][key]['value']
        message = 'Custom text' if key == 'custom' else 'Watermark override'
        if value is None:
            from kim_recipe_image import copyright_settings
            try:
                value = copyright_settings()[key]
                message = 'Inherited from KIM6 Settings' + ('' if value.strip() else ' — not set')
            except (OSError, RecipeError) as exc:
                value = ''; message = 'Settings unavailable: ' + str(exc)
        editor.blockSignals(True); editor.setPlainText(value); editor.blockSignals(False)
        mode.setText(message); editor.setEnabled(selected.isChecked())
        if reset: reset.setEnabled(selected.isChecked())

    def watermark_field_changed(self, key, selection=None):
        if self.loading: return
        _, selected, editor, mode, reset = self.watermark_widgets[key]
        field = self.step['text_fields'][key]
        if selection is None:
            field['value'] = editor.toPlainText()
            mode.setText('Custom text' if key == 'custom' else 'Watermark override')
        else:
            field['selected'] = selection
            self.show_watermark_field(key)
        self.schedule()

    def camera_field_changed(self, key, checked):
        if self.loading: return
        self.step['camera_fields'][key] = checked
        self.schedule()

    def reset_watermark_field(self, key):
        self.step['text_fields'][key]['value'] = None
        self.show_watermark_field(key); self.schedule()

    def control_changed(self, key):
        if self.loading: return
        w = self.fields[key]
        value = (w.currentFont().family() if isinstance(w, QFontComboBox) else w.currentData() if isinstance(w, QComboBox) else
                 w.isChecked() if isinstance(w, QCheckBox) else w.toPlainText() if isinstance(w, QPlainTextEdit) else
                 w.text() if isinstance(w, QLineEdit) else w.value())
        if key in ('x', 'y', 'w', 'h'): value /= 100
        self.step[key] = value
        self.loading = True
        if self.crop:
            if (key == 'placement' and value == 'manual') or (key == 'area' and value == 'manual'):
                r = self.canvas.selection
                for k, v in zip(('x', 'y', 'w', 'h'), (r.x(), r.y(), r.width(), r.height())): self.set_field(k, v)
                self.set_field('area', 'manual'); self.set_field('placement', 'manual')
            if key == 'placement' and value != 'manual' and self.step['area'] == 'manual': self.set_field('area', 'pixels')
            if key in ('x', 'y', 'w', 'h'): self.set_field('area', 'manual'); self.set_field('placement', 'manual')
            if key in ('crop_width', 'crop_height'):
                self.set_field('area', 'pixels')
            if self.dimensions and key in ('aspect', 'ratio_width', 'ratio_height', 'crop_width', 'crop_height') and self.step['area'] == 'pixels':
                ratio = crop_ratio(self.step, *self.dimensions)
                if ratio:
                    other = 'crop_width' if key == 'crop_height' else 'crop_height'
                    adjusted = round(self.step['crop_height'] * ratio) if other == 'crop_width' else round(self.step['crop_width'] / ratio)
                    self.set_field(other, max(1, min(100000, adjusted)))
        elif key == 'kind':
            source = 'custom' if value in ('text', 'caption') else self.step['source']
            self.set_field('source', source)
            if self.step['value'] is None: self.step['value'] = ''; self.show_text_value()
            self.set_field('size', 20.0 if value == 'image' else 3.0)
        elif key == 'source':
            self.step['value'] = self.fields['value'].toPlainText()
            self.show_text_value()
        self.loading = False; self.sync_visibility(); self.update_crop_boundary(); self.schedule()

    def set_field(self, key, value):
        self.step[key] = value; w = self.fields[key]; w.blockSignals(True)
        if isinstance(w, QComboBox): w.setCurrentIndex(w.findData(value))
        else: w.setValue(value * 100 if key in ('x', 'y', 'w', 'h') else value)
        w.blockSignals(False)

    def sync_visibility(self):
        if self.crop:
            for key in ('ratio_width', 'ratio_height'): self.form.setRowVisible(self.fields[key], self.step['aspect'] == 'custom')
            for key in ('crop_width', 'crop_height'): self.form.setRowVisible(self.fields[key], True)
            for key in ('x', 'y', 'w', 'h'): self.form.setRowVisible(self.fields[key], self.step['area'] == 'manual')
            for key in ('target_width', 'target_height', 'upscale'): self.form.setRowVisible(self.fields[key], self.step['resize'])
        else:
            kind = self.step['kind']; text = kind != 'image'
            self.form.setRowVisible(self.camera_grid, kind == 'camera')
            for container, *_ in self.watermark_widgets.values(): self.form.setRowVisible(container, kind == 'text')
            self.form.setRowVisible(self.fields['source'], kind == 'caption')
            self.form.setRowVisible(self.fields['value'], kind == 'caption' and self.step['source'] == 'custom')
            for key in ('font', 'color', 'bold', 'italic', 'assistance'): self.form.setRowVisible(self.fields[key], text)
            self.color_button.setVisible(text); self.form.setRowVisible(self.fields['logo'], kind == 'image'); self.logo_button.setVisible(kind == 'image')
        if self.standalone:
            mode = self.destination.currentData()
            self.form.setRowVisible(self.folder, mode == 'subfolder'); self.form.setRowVisible(self.directory, mode == 'directory'); self.directory_button.setVisible(mode == 'directory')

    def manual_selection(self, rect):
        if self.loading: return
        self.loading = True
        self.set_field('area', 'manual'); self.set_field('placement', 'manual')
        for key, value in zip(('x', 'y', 'w', 'h'), (rect.x(), rect.y(), rect.width(), rect.height())): self.set_field(key, value)
        self.loading = False; self.sync_visibility(); self.update_crop_boundary(keep_drag=True); self.schedule()

    def update_crop_boundary(self, keep_drag=False):
        if not self.crop or not self.dimensions: return
        try:
            step = dict(self.step, resize=False); result = crop_plan(*self.dimensions, step)
            width, height = self.dimensions
            if not keep_drag: self.canvas.selection = QRectF(result['x'] / width, result['y'] / height, result['width'] / width, result['height'] / height)
            self.canvas.ratio = crop_ratio(step, width, height); self.canvas.update()
            self.geometry.setText(f"Image before this crop: {width} × {height}; crop: {result['width']} × {result['height']} at ({result['x']}, {result['y']}). Output resizing is shown in the plan below.")
            if self.step['area'] != 'pixels':
                for key, v in (('crop_width', result['width']), ('crop_height', result['height'])):
                    self.step[key] = v
                    self.fields[key].blockSignals(True); self.fields[key].setValue(v); self.fields[key].blockSignals(False)
        except RecipeError as exc: self.geometry.setText(str(exc))

    def build_recipe(self):
        step = copy.deepcopy(self.step); step['enabled'] = True
        if not self.standalone:
            recipe = copy.deepcopy(self.recipe); recipe['steps'][self.row] = step
            return validate(recipe)
        steps = []
        fmt = self.output_format.currentData()
        if fmt: steps.append({'op': 'image.convert', 'format': fmt, 'quality': 90})
        steps += [step, {'op': 'file.rename_output', 'pattern': '{filename}_cropped' if self.crop else '{filename}_watermarked'}]
        mode = self.destination.currentData(); dest = dict(mode=mode)
        if mode == 'subfolder': dest['folder'] = self.folder.text()
        elif mode == 'directory': dest.update(path=self.directory.text(), ask=False)
        return validate(dict(schema=1, id='standalone-crop' if self.crop else 'standalone-overlay',
                             name=self.windowTitle(), media='image', steps=steps, destination=dest))

    def schedule(self, *_):
        if self.loading or self.closing: return
        self.generation += 1; self.checked_generation = None; self.apply.setEnabled(False)
        self.sync_visibility()
        if self.worker: self.worker.requestInterruption(); self.pending = True
        self.timer.start()

    def refresh(self):
        if self.closing: return
        if self.worker: self.pending = True; return
        self.pending = False
        try:
            recipe = self.build_recipe()
            sample = self.images.currentData()
            files = self.files if self.files else ([sample] if sample else [])
            prefix = recipe['steps'][:self.row] if not self.standalone else [s for s in recipe['steps'] if s['op'] == 'image.convert']
            prefix = [s for s in prefix if s.get('enabled', True)]
            if not files:
                if not self.crop and self.step['kind'] == 'text':
                    from kim_image_ops import watermark_text
                    watermark_text(self.step)
                if not self.crop and self.step['kind'] == 'camera':
                    from kim_image_ops import validate_camera_selection
                    validate_camera_selection(self.step)
                self.status.setText('Choose an example image for a visual preview. Recipe execution will check every selected image.')
                self.apply.setEnabled(not self.standalone); self.checked_generation = self.generation
                return
            self.worker = VisualWorker(recipe, files, sample, prefix, dict(self.step, enabled=True), self.generation, self)
            self.worker.stage_changed.connect(self.stage); self.worker.finished.connect(self.finished_preview); self.worker.start()
            self.status.setText('Checking each selected image and rendering the preview…')
        except (RecipeError, OSError) as exc:
            self.status.setText(str(exc)); self.apply.setEnabled(False)

    def stage(self, value):
        if self.worker and self.sender() == self.worker and self.worker.generation == self.generation: self.status.setText(value)

    def finished_preview(self):
        worker, self.worker = self.worker, None
        if self.closing: worker.deleteLater(); super().reject(); return
        if worker.generation != self.generation:
            worker.deleteLater(); self.refresh(); return
        self.table.setRowCount(len(worker.rows)); problems = []; warnings = []
        for index, row in enumerate(worker.rows):
            p = row.properties
            original = f"{p.get('original_display_width', '?')} × {p.get('original_display_height', '?')}"
            plan = '\n'.join(p.get('crops' if self.crop else 'overlays', []))
            result = '; '.join(row.problems) if row.problems else f"{p.get('display_width', '?')} × {p.get('display_height', '?')} → {row.output}"
            for column, value in enumerate(
                (Path(row.source).name, original, plan, result)
            ):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    row.source if column == 0 else value
                )
                self.table.setItem(index, column, item)
            problems += [row.source + ': ' + p for p in row.problems]; warnings += [row.source + ': ' + w for w in row.warnings]
        self.table.resizeRowsToContents()
        if not worker.image.isNull():
            self.canvas.image = worker.image; self.dimensions = worker.dimensions; self.canvas.update()
            if self.crop: self.update_crop_boundary()
            else: self.geometry.setText(f"Final overlay geometry: {worker.dimensions[0]} × {worker.dimensions[1]} pixels. Preview uses the production overlay renderer." if worker.rendered_overlay else 'Source image only — resolve the overlay problem below to see the visible result.')
        elif worker.error:
            self.canvas.image = QImage(); self.canvas.update()
        if worker.error: problems.append(worker.error)
        self.status.setText('\n'.join(problems + warnings) or 'Every image has a valid output plan. The visual preview is scaled to fit.')
        self.checked_generation = self.generation
        self.apply.setEnabled(not problems and not worker.image.isNull())
        worker.deleteLater()
        if self.pending: self.refresh()

    def choose_image(self):
        current = self.images.currentData()
        paths = choose_images(self, str(Path(current).parent) if current else '',
                              title='Choose Preview Image', multiple=False,
                              extensions=RECIPE_IMAGE_EXTENSIONS, accept_label='Use Preview Image')
        for path in paths:
            if self.images.findData(path) < 0: self.images.addItem(Path(path).name, path)
        if paths: self.images.setCurrentIndex(self.images.findData(paths[0])); self.schedule()

    def choose_logo(self):
        picker = WatermarkImagePicker(self, self.step['logo'])
        if picker.exec() == QDialog.Accepted and picker.selectedFiles():
            self.fields['logo'].setText(picker.selectedFiles()[0])
        picker.deleteLater()

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.step['color']), self, 'Text Color')
        if color.isValid(): self.fields['color'].setText(color.name())

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, 'Choose Output Directory')
        if path: self.directory.setText(path)

    def accept(self):
        if self.worker or self.checked_generation != self.generation or not self.apply.isEnabled(): return
        try: self.result_recipe = self.build_recipe()
        except (RecipeError, OSError) as exc: self.status.setText(str(exc)); return
        self.timer.stop(); self.closing = True
        super().accept()

    def reject(self):
        self.timer.stop(); self.closing = True
        if self.worker: self.worker.requestInterruption(); self.apply.setEnabled(False); self.status.setText('Cancelling preview; waiting for cleanup…')
        else: super().reject()

    def closeEvent(self, event):
        if self.worker: self.reject(); event.ignore()
        else: self.timer.stop(); self.closing = True; event.accept()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='KIM6 crop and visible overlays (new derivatives only)')
    parser.add_argument('operation', choices=('crop', 'overlay')); parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    defaults = CROP_DEFAULTS if args.operation == 'crop' else OVERLAY_DEFAULTS
    try:
        files = [os.path.abspath(path) for path in args.files]
        dialog = ImageOperationDialog(dict(op='image.' + args.operation, **defaults), files)
        if dialog.exec() != QDialog.Accepted: return 1
        from kim_recipe_run import RunRecipeDialog
        run = RunRecipeDialog(dialog.result_recipe, files, operation_title=dialog.windowTitle())
        run.exec()
        return int(not run.execution_succeeded)
    except (OSError, RecipeError) as exc:
        QMessageBox.critical(None, 'KIM6', str(exc)); return 1


if __name__ == '__main__':
    raise SystemExit(main())
