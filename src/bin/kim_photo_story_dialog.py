#!/usr/bin/env python3
"""In-memory chronological Photo Story editor."""

from collections import OrderedDict
from dataclasses import dataclass, field
from math import ceil
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import Qt, QSize, QTimer, Signal, QUrl, QEvent, QRect
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QFileDialog, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QVBoxLayout, QWidget, QToolButton,
)

from kim_dialog_buttons import style_button, style_button_box
from kim_photo_selection import CREATE_IMAGE_EXTENSIONS, ThumbnailWorker, choose_images
from kim_preview import identity


KIND_ROLE = Qt.UserRole + 1
ID_ROLE = Qt.UserRole + 2
SOURCE_ROLE = Qt.UserRole + 3


@dataclass
class StoryElement:
    """One stable entry in the chronological story."""

    kind: str
    source: str = ""
    heading: str = ""
    caption: str = ""
    text: str = ""
    description: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def title_or_text(self):
        if self.kind == "heading":
            return self.heading
        if self.kind == "text":
            return self.text
        return ""


class StorySequence:
    """Small in-memory model for ordered image, heading, and text elements."""

    KINDS = frozenset(("image", "heading", "text"))

    def __init__(self, paths=()):
        self.elements = []
        for path in paths:
            self.add_image(path)

    def get(self, element_id):
        return next(item for item in self.elements if item.id == element_id)

    def index_of(self, element_id):
        return next(i for i, item in enumerate(self.elements) if item.id == element_id)

    def insert(self, element, *, after_id=None, index=None):
        if element.kind not in self.KINDS:
            raise ValueError("Unknown story element type")
        if any(item.id == element.id for item in self.elements):
            raise ValueError("Story element IDs must be unique")
        if index is None:
            index = self.index_of(after_id) + 1 if after_id is not None else len(self.elements)
        if index < 0 or index > len(self.elements):
            raise IndexError("Story insertion position is outside the sequence")
        self.elements.insert(index, element)
        return element

    def add_image(self, path, *, index=None):
        source = os.fspath(path)
        if any(item.kind == "image" and item.source == source for item in self.elements):
            return None
        return self.insert(StoryElement("image", source=source), index=index)

    def add_heading(self, text="", *, after_id=None, index=None):
        return self.insert(StoryElement("heading", heading=text), after_id=after_id, index=index)

    def add_text(self, text="", *, after_id=None, index=None):
        return self.insert(StoryElement("text", text=text), after_id=after_id, index=index)

    def remove(self, element_id):
        return self.elements.pop(self.index_of(element_id))

    def move(self, element_id, destination):
        old = self.index_of(element_id)
        if destination < 0 or destination >= len(self.elements):
            raise IndexError("Story destination is outside the sequence")
        element = self.elements.pop(old)
        self.elements.insert(destination, element)

    def reorder(self, element_ids):
        by_id = {item.id: item for item in self.elements}
        if len(element_ids) != len(by_id) or set(element_ids) != set(by_id):
            raise ValueError("Reordering must retain every story element exactly once")
        self.elements[:] = [by_id[element_id] for element_id in element_ids]


class StoryRowDelegate(QStyledItemDelegate):
    """Paint compact editorial rows without creating one widget per element."""

    def paint(self, painter, option, index):
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, option.widget)

        rect = option.rect.adjusted(8, 4, -8, -4)
        selected = bool(option.state & QStyle.State_Selected)
        palette = option.palette
        primary = palette.color(QPalette.HighlightedText if selected else QPalette.Text)
        secondary = primary if selected else palette.color(QPalette.Text)
        if not selected:
            secondary.setAlpha(190)
        kind = index.data(KIND_ROLE)
        icon_rect = rect.adjusted(0, 4, 0, -4)
        icon_rect.setWidth(38)
        icon_rect.setHeight(min(38, icon_rect.height()))
        icon_rect.moveCenter(type(icon_rect.center())(rect.left() + 23, rect.center().y()))

        icon = index.data(Qt.DecorationRole)
        if icon and not icon.isNull():
            icon.paint(painter, icon_rect, Qt.AlignCenter)

        text_left = rect.left() + 52
        tag_font = QFont(option.font)
        tag_font.setPointSize(max(7, tag_font.pointSize() - 2))
        tag_font.setBold(True)
        painter.save()
        painter.setFont(tag_font)
        painter.setPen(secondary)
        kind_label = {"image": "IMAGE", "heading": "HEADING", "text": "TEXT"}.get(kind, "")
        painter.drawText(text_left, rect.top() + 12, kind_label)

        primary_font = QFont(option.font)
        primary_font.setBold(True)
        painter.setFont(primary_font)
        painter.setPen(primary)
        title = index.data(Qt.DisplayRole) or ""
        primary_rect = rect.adjusted(52, 15, -2, -22)
        painter.drawText(primary_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(
                             title, Qt.ElideRight, primary_rect.width()))

        secondary_font = QFont(option.font)
        secondary_font.setPointSize(max(8, secondary_font.pointSize() - 1))
        painter.setFont(secondary_font)
        painter.setPen(secondary)
        detail = index.data(Qt.UserRole) or ""
        detail_rect = rect.adjusted(52, 39, -2, -1)
        painter.drawText(detail_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(
                             detail, Qt.ElideMiddle if kind == "image" else Qt.ElideRight,
                             detail_rect.width()))
        painter.restore()


class StorySequenceView(QWidget):
    """Photo Story list adapter and bounded thumbnail owner."""

    selection_changed = Signal(str)
    sequence_changed = Signal()
    idle = Signal()

    def __init__(self, parent=None, paths=()):
        super().__init__(parent)
        self.dialog = parent
        self.sequence = StorySequence()
        self.source_stamps = {}
        self.thumbnails = OrderedDict()
        self.unavailable = set()
        self.thumbnail_worker = None
        self.thumbnail_items = {}
        self.preview_path = ""
        self.stopped = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(7)

        primary_actions = QHBoxLayout()
        self.add_images_button = QPushButton("Add images…")
        self.add_heading_button = QPushButton("Add heading")
        self.add_text_button = QPushButton("Add text")
        self.add_images_button.setIcon(QIcon.fromTheme("image-x-generic"))
        self.add_heading_button.setIcon(self._icon("format-text-bold", QStyle.SP_FileDialogDetailedView))
        self.add_text_button.setIcon(self._icon("insert-text", QStyle.SP_FileDialogContentsView))
        primary_actions.addWidget(self.add_images_button)
        outer.addLayout(primary_actions)
        narrative_actions = QHBoxLayout()
        narrative_actions.addWidget(self.add_heading_button)
        narrative_actions.addWidget(self.add_text_button)
        outer.addLayout(narrative_actions)

        edit_actions = QHBoxLayout()
        self.remove_button = QPushButton("Remove selected")
        self.up_button = QPushButton("Move up")
        self.down_button = QPushButton("Move down")
        self.remove_button.setIcon(self._icon("edit-delete", QStyle.SP_TrashIcon))
        self.up_button.setIcon(self._icon("go-up", QStyle.SP_ArrowUp))
        self.down_button.setIcon(self._icon("go-down", QStyle.SP_ArrowDown))
        for button in (self.remove_button, self.up_button, self.down_button):
            button.setMinimumWidth(0)
            edit_actions.addWidget(button, 1)
        outer.addLayout(edit_actions)

        self.list = QListWidget()
        self.list.setObjectName("storySequence")
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setDropIndicatorShown(True)
        self.list.setIconSize(QSize(54, 44))
        self.list.setItemDelegate(StoryRowDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setAccessibleName("Chronological story order")
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list.setMinimumHeight(180)
        outer.addWidget(self.list, 1)

        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.setInterval(35)
        self.thumbnail_timer.timeout.connect(self.load_thumbnails)
        self.add_images_button.clicked.connect(self.choose_images)
        self.add_heading_button.clicked.connect(self.add_heading)
        self.add_text_button.clicked.connect(self.add_text)
        self.remove_button.clicked.connect(self.remove_selected)
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.model().rowsMoved.connect(self.sync_order)
        self.list.verticalScrollBar().valueChanged.connect(self.queue_thumbnails)
        self._update_controls()
        self.add_paths(paths)

    def _icon(self, name, fallback):
        icon = QIcon.fromTheme(name)
        return icon if not icon.isNull() else self.style().standardIcon(fallback)

    def ordered_ids(self):
        return [self.list.item(i).data(ID_ROLE) for i in range(self.list.count())]

    def selected_id(self):
        item = self.list.currentItem()
        return item.data(ID_ROLE) if item is not None else ""

    def item_for_id(self, element_id):
        return next((self.list.item(i) for i in range(self.list.count())
                     if self.list.item(i).data(ID_ROLE) == element_id), None)

    def add_paths(self, paths):
        added = []
        for raw_path in paths:
            candidate = Path(os.path.abspath(os.fspath(raw_path)))
            path = str(candidate.parent.resolve() / candidate.name)
            try:
                stamp = identity(path)
            except (OSError, ValueError):
                stamp = None
            element = self.sequence.add_image(path)
            if element is None:
                continue
            self.source_stamps[path] = stamp
            self.unavailable.discard(path)
            item = QListWidgetItem()
            item.setData(ID_ROLE, element.id)
            item.setData(KIND_ROLE, "image")
            item.setData(SOURCE_ROLE, path)
            item.setData(Qt.UserRole, Path(path).name)
            item.setIcon(self._icon("image-x-generic", QStyle.SP_FileIcon))
            item.setSizeHint(QSize(100, 78))
            self.list.addItem(item)
            added.append(element.id)
        if added:
            self._refresh_all()
            self._select_id(added[0])
            self.sequence_changed.emit()
        return added

    def choose_images(self):
        paths = [item.source for item in self.sequence.elements if item.kind == "image"]
        start = str(Path(paths[-1]).parent) if paths else str(Path.home())
        additions = choose_images(self, start, title="Add images for Photo Story",
                                  extensions=CREATE_IMAGE_EXTENSIONS)
        if additions:
            self.add_paths(additions)

    def add_heading(self, after_id=None):
        after_id = self.selected_id() if after_id is None else after_id
        element = self.sequence.add_heading(after_id=after_id or None)
        item = QListWidgetItem()
        item.setData(ID_ROLE, element.id)
        item.setData(KIND_ROLE, "heading")
        item.setData(Qt.UserRole, "Use a short section title")
        item.setIcon(self._icon("format-text-bold", QStyle.SP_FileDialogDetailedView))
        item.setSizeHint(QSize(100, 78))
        row = self.sequence.index_of(element.id)
        self.list.insertItem(row, item)
        self._refresh_item(element.id)
        self._select_id(element.id)
        self._update_controls()
        self.sequence_changed.emit()
        return element

    def add_text(self, after_id=None):
        after_id = self.selected_id() if after_id is None else after_id
        element = self.sequence.add_text(after_id=after_id or None)
        item = QListWidgetItem()
        item.setData(ID_ROLE, element.id)
        item.setData(KIND_ROLE, "text")
        item.setData(Qt.UserRole, "Add a narrative passage")
        item.setIcon(self._icon("insert-text", QStyle.SP_FileDialogContentsView))
        item.setSizeHint(QSize(100, 78))
        self.list.insertItem(self.sequence.index_of(element.id), item)
        self._refresh_item(element.id)
        self._select_id(element.id)
        self._update_controls()
        self.sequence_changed.emit()
        return element

    def remove_selected(self):
        element_id = self.selected_id()
        if element_id:
            self.remove(element_id)

    def remove(self, element_id):
        row = self.sequence.index_of(element_id)
        element = self.sequence.remove(element_id)
        if element.kind == "image":
            self.source_stamps.pop(element.source, None)
            self.thumbnails.pop(element.source, None)
            self.unavailable.discard(element.source)
        self.list.takeItem(row)
        target = min(row, self.list.count() - 1)
        self._refresh_all()
        if target >= 0:
            self.list.setCurrentRow(target)
        else:
            self._selection_changed(None, None)
        self.sequence_changed.emit()
        return element

    def move_selected(self, direction):
        element_id = self.selected_id()
        if element_id:
            self.move(element_id, self.sequence.index_of(element_id) + direction)

    def move(self, element_id, destination):
        if destination < 0 or destination >= len(self.sequence.elements):
            return False
        self.sequence.move(element_id, destination)
        item = self.item_for_id(element_id)
        self.list.takeItem(self.list.row(item))
        self.list.insertItem(destination, item)
        self._select_id(element_id)
        self._refresh_all()
        self.sequence_changed.emit()
        return True

    def update_element(self, element_id, **values):
        element = self.sequence.get(element_id)
        for key, value in values.items():
            if key not in ("heading", "caption", "text", "description"):
                raise ValueError("Unsupported story content field")
            setattr(element, key, value)
        self._refresh_item(element_id)
        self.sequence_changed.emit()

    def _select_id(self, element_id, *, scroll=True):
        item = self.item_for_id(element_id)
        if item is not None:
            self.list.setCurrentItem(item)
            if scroll:
                self.list.scrollToItem(item)
        else:
            self.list.setCurrentRow(-1)

    def _selection_changed(self, current, previous):
        del previous
        self._update_controls()
        self.selection_changed.emit(current.data(ID_ROLE) if current else "")
        self.queue_thumbnails()

    def sync_order(self, *_):
        self.sequence.reorder(self.ordered_ids())
        self._refresh_all()
        self.sequence_changed.emit()
        self._update_controls()

    def _refresh_all(self):
        self.list.blockSignals(True)
        for element in self.sequence.elements:
            self._refresh_item(element.id)
        self.list.blockSignals(False)
        self._update_controls()
        self.queue_thumbnails()

    def _refresh_item(self, element_id):
        item = self.item_for_id(element_id)
        if item is None:
            return
        element = self.sequence.get(element_id)
        if element.kind == "image":
            filename = Path(element.source).name
            item.setText(element.heading or filename)
            item.setData(Qt.UserRole, filename if element.heading else "")
            cached = self.thumbnails.get(element.source)
            if cached is not None:
                item.setIcon(QIcon(QPixmap.fromImage(cached)))
            else:
                item.setIcon(self._icon("image-x-generic", QStyle.SP_FileIcon))
            item.setToolTip(element.source)
        elif element.kind == "heading":
            item.setText(element.heading or "Untitled heading")
            item.setData(Qt.UserRole, "Section heading")
            item.setIcon(self._icon("format-text-bold", QStyle.SP_FileDialogDetailedView))
            item.setToolTip("Section heading")
        else:
            excerpt = " ".join(element.text.split())[:100] or "Empty text passage"
            item.setText(excerpt)
            item.setData(Qt.UserRole, "")
            item.setIcon(self._icon("insert-text", QStyle.SP_FileDialogContentsView))
            item.setToolTip(element.text or "Empty text passage")
        item.setData(KIND_ROLE, element.kind)
        item.setSizeHint(QSize(100, 78))

    def _update_controls(self):
        count = len(self.sequence.elements)
        row = self.list.currentRow()
        self.remove_button.setEnabled(row >= 0)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < count - 1)

    def queue_thumbnails(self, *_):
        if not self.stopped:
            self.thumbnail_timer.start()

    def get_thumbnail(self, path):
        image = self.thumbnails.get(path)
        if image is not None:
            self.thumbnails.move_to_end(path)
        return image

    def request_preview(self, path):
        self.preview_path = path
        self.queue_thumbnails()

    def load_thumbnails(self):
        if self.stopped or self.thumbnail_worker is not None:
            return
        viewport = self.list.viewport().rect()
        visible = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(KIND_ROLE) == "image" and self.list.visualItemRect(item).intersects(viewport):
                visible.append(item.data(SOURCE_ROLE))
        canvas_visible = []
        dialog = self.dialog
        if dialog is not None and hasattr(dialog, "visible_canvas_image_sources"):
            canvas_visible = dialog.visible_canvas_image_sources()
        candidates = []
        for path in dict.fromkeys([*canvas_visible, self.preview_path, *visible]):
            if not path or path in self.unavailable or path in self.thumbnails:
                continue
            if any(item.kind == "image" and item.source == path for item in self.sequence.elements):
                candidates.append(path)
        if not candidates:
            return
        paths = candidates[:8]
        self.thumbnail_items = {path: self._image_element_id(path) for path in paths}
        self.thumbnail_worker = ThumbnailWorker(paths, QSize(480, 340), self)
        self.thumbnail_worker.thumbnail_ready.connect(self._receive_thumbnail)
        self.thumbnail_worker.finished.connect(self._thumbnails_finished)
        self.thumbnail_worker.start()

    def _image_element_id(self, path):
        return next((item.id for item in self.sequence.elements
                     if item.kind == "image" and item.source == path), "")

    def _receive_thumbnail(self, path, image, stamp):
        if (self.stopped or self.sender() is not self.thumbnail_worker
                or self.thumbnail_items.get(path) != self._image_element_id(path)):
            return
        expected = self.source_stamps.get(path)
        try:
            valid = stamp is not None and expected is not None and stamp == expected and identity(path) == expected
        except (OSError, ValueError):
            valid = False
        if image.isNull() or not valid:
            self.unavailable.add(path)
            dialog = self.dialog
            if dialog is not None and hasattr(dialog, "_clear_canvas_thumbnail"):
                dialog._clear_canvas_thumbnail(path)
            item_id = self.thumbnail_items.get(path)
            item = self.item_for_id(item_id)
            if item is not None:
                item.setToolTip(path + "\nPreview unavailable")
        else:
            self.thumbnails[path] = image
            self.thumbnails.move_to_end(path)
            dialog = self.dialog
            if dialog is not None and hasattr(dialog, "_update_canvas_thumbnail"):
                dialog._update_canvas_thumbnail(path)
            while len(self.thumbnails) > 64:
                expired, _ = self.thumbnails.popitem(last=False)
                item = self.item_for_id(self._image_element_id(expired))
                if item is not None:
                    item.setIcon(self._icon("image-x-generic", QStyle.SP_FileIcon))
                if dialog is not None and hasattr(dialog, "_clear_canvas_thumbnail"):
                    dialog._clear_canvas_thumbnail(expired)
            self._refresh_item(self.thumbnail_items[path])
        self.sequence_changed.emit()

    def _thumbnails_finished(self):
        worker, self.thumbnail_worker = self.thumbnail_worker, None
        worker.wait()
        worker.deleteLater()
        if self.stopped:
            self.idle.emit()
        else:
            self.queue_thumbnails()

    def stop(self):
        self.stopped = True
        self.thumbnail_timer.stop()
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.requestInterruption()


class StoryTextEdit(QPlainTextEdit):
    focus_entered = Signal()

    def __init__(self, placeholder="", *, minimum=96, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(minimum)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setTabChangesFocus(True)
        self.setStyleSheet("font-size: 14px; padding: 8px;")
        self.textChanged.connect(self.fit_content)
        self.fit_content()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focus_entered.emit()

    def fit_content(self):
        document_height = self.document().documentLayout().documentSize().height()
        metrics = self.fontMetrics()
        width = max(80, self.viewport().width() - 12)
        wrapped_lines = 0
        for paragraph in (self.toPlainText() or "").split("\n"):
            height = metrics.boundingRect(
                QRect(0, 0, width, 100000), Qt.TextWordWrap, paragraph).height()
            wrapped_lines += max(1, ceil(height / max(1, metrics.lineSpacing())))
        document_height = max(
            document_height, metrics.lineSpacing() * max(1, wrapped_lines))
        margins = self.contentsMargins()
        wanted = int(document_height + margins.top() + margins.bottom() + 36)
        self.setFixedHeight(max(self.minimumHeight(), min(560, wanted)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            QTimer.singleShot(0, self.fit_content)


class StoryCanvasBlock(QFrame):
    """Persistent editor widgets for one stable story element."""

    content_changed = Signal(str, str, str)
    focused = Signal(str)

    def __init__(self, element, parent=None, thumbnail_lookup=None):
        super().__init__(parent)
        self.element_id = element.id
        self.kind = element.kind
        self.source = element.source
        self.thumbnail_lookup = thumbnail_lookup
        self._last_preview_size = QSize()
        self.setObjectName("storyCanvasBlock")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        header = QHBoxLayout()
        kind_label = QLabel({"image": "IMAGE", "heading": "SECTION", "text": "PASSAGE"}[element.kind])
        kind_label.setStyleSheet("font-size: 10px; font-weight: 750; letter-spacing: 1px; color: palette(mid);")
        header.addWidget(kind_label)
        header.addStretch(1)
        self.source_label = None
        if element.kind == "image":
            self.source_label = QLabel(Path(element.source).name)
            self.source_label.setToolTip(element.source)
            self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.source_label.setStyleSheet("font-size: 12px; color: palette(mid);")
            header.addWidget(self.source_label)
        layout.addLayout(header)

        self.image_preview = None
        self.image_heading = None
        self.description_editor = None
        self.caption_editor = None
        self.caption_toggle = None
        self.heading_editor = None
        self.passage_editor = None
        self.caption_container = None
        if element.kind == "image":
            self.image_preview = QLabel("Image preview loads as you scroll")
            self.image_preview.setObjectName("storyCanvasImage")
            self.image_preview.setAlignment(Qt.AlignCenter)
            self.image_preview.setMinimumHeight(148)
            self.image_preview.setMaximumHeight(380)
            self.image_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.image_preview.setAccessibleName("Image in story: " + Path(element.source).name)
            self.image_preview.setStyleSheet("background: palette(alternate-base); border-radius: 5px;")
            self.image_preview.installEventFilter(self)
            # Place the photograph after the optional top caption.

            self.image_heading = QLineEdit(element.heading)
            self.image_heading.setPlaceholderText("Optional caption above image")
            self.image_heading.setAccessibleName(
                "Top caption for " + Path(element.source).name)

            # Preserve existing heading data without an extra editor control.
            self.image_heading.hide()
            self.image_heading.setFocusPolicy(Qt.NoFocus)
            layout.addWidget(self.image_preview)


            description_label = QLabel("Description")
            description_label.setStyleSheet("font-weight: 650;")
            layout.addWidget(description_label)
            self.description_editor = StoryTextEdit(
                "Write the story behind this image. Add paragraphs as needed.", minimum=96)
            self.description_editor.setAccessibleName("Description for " + Path(element.source).name)
            self.description_editor.setPlainText(element.description)
            layout.addWidget(self.description_editor)

            self.caption_toggle = QToolButton()
            self.caption_toggle.setText("Edit caption" if element.caption else "Add caption")
            self.caption_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.caption_toggle.setArrowType(Qt.DownArrow)
            self.caption_toggle.setCheckable(True)
            self.caption_toggle.setChecked(False)
            self.caption_toggle.setToolTip(element.caption or "Optional short caption, hidden in the gallery by default")
            self.caption_container = QWidget()
            caption_layout = QVBoxLayout(self.caption_container)
            caption_layout.setContentsMargins(0, 0, 0, 0)
            self.caption_editor = StoryTextEdit("Optional short caption", minimum=74)
            self.caption_editor.setMaximumHeight(190)
            self.caption_editor.setAccessibleName("Caption for " + Path(element.source).name)
            self.caption_editor.setPlainText(element.caption)
            caption_layout.addWidget(self.caption_editor)
            self.caption_container.setVisible(False)
            self.caption_toggle.toggled.connect(self.caption_container.setVisible)
            self.caption_toggle.toggled.connect(
                lambda checked: self.caption_toggle.setArrowType(Qt.UpArrow if checked else Qt.DownArrow))
            # Preserve legacy caption data without displaying a second
            # competing caption field in the editor.
            self.caption_toggle.hide()
            self.caption_container.hide()

            self.image_heading.textChanged.connect(
                lambda value: self.content_changed.emit(self.element_id, "heading", value))
            self.description_editor.textChanged.connect(
                lambda: self.content_changed.emit(
                    self.element_id, "description", self.description_editor.toPlainText()))
            self.caption_editor.textChanged.connect(
                lambda: self.content_changed.emit(
                    self.element_id, "caption", self.caption_editor.toPlainText()))
            self.caption_editor.textChanged.connect(self._update_caption_action)
            for control in (self.image_heading, self.description_editor, self.caption_editor):
                if isinstance(control, StoryTextEdit):
                    control.focus_entered.connect(lambda eid=self.element_id: self.focused.emit(eid))
                else:
                    control.installEventFilter(self)
        elif element.kind == "heading":
            self.heading_editor = QLineEdit(element.heading)
            self.heading_editor.setPlaceholderText("Untitled section heading")
            self.heading_editor.setAccessibleName("Section heading")
            self.heading_editor.setStyleSheet("font-size: 21px; font-weight: 650; padding: 8px;")
            layout.addWidget(self.heading_editor)
            self.heading_editor.textChanged.connect(
                lambda value: self.content_changed.emit(self.element_id, "heading", value))
            self.heading_editor.installEventFilter(self)
        else:
            self.passage_editor = StoryTextEdit(
                "Write a narrative passage…", minimum=136)
            self.passage_editor.setAccessibleName("Narrative passage")
            self.passage_editor.setPlainText(element.text)
            layout.addWidget(self.passage_editor)
            self.passage_editor.textChanged.connect(
                lambda: self.content_changed.emit(
                    self.element_id, "text", self.passage_editor.toPlainText()))
            self.passage_editor.focus_entered.connect(
                lambda eid=self.element_id: self.focused.emit(eid))

    def eventFilter(self, watched, event):
        if (watched is self.image_preview and event.type() == QEvent.Resize
                and self.image_preview is not None):
            QTimer.singleShot(0, self._render_image_preview)
        if event.type() == QEvent.FocusIn:
            self.focused.emit(self.element_id)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        self.focused.emit(self.element_id)
        super().mousePressEvent(event)

    def set_image(self, image):
        if image is None or image.isNull() or self.image_preview is None:
            return
        self._render_image_preview(image)

    def _render_image_preview(self, image=None):
        if self.image_preview is None:
            return
        if image is None and self.thumbnail_lookup is not None:
            image = self.thumbnail_lookup(self.source)
        if image is None or image.isNull():
            return
        width = max(0, self.image_preview.width() - 16)
        if width <= 0:
            return
        desired_height = min(380, max(180, int(width * image.height() / max(1, image.width()))))
        if self.image_preview.height() != desired_height:
            self.image_preview.setMinimumHeight(desired_height)
            self.image_preview.setMaximumHeight(desired_height)
        available = QSize(width, max(0, self.image_preview.height() - 16))
        if available.width() <= 0 or available.height() <= 0:
            return
        if available != self._last_preview_size:
            self.image_preview.setPixmap(
                QPixmap.fromImage(image).scaled(available, Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation))
            self.image_preview.setText("")
            self._last_preview_size = available

    def _update_caption_action(self):
        if self.caption_toggle is not None and self.caption_editor is not None:
            self.caption_toggle.setText(
                "Edit caption" if self.caption_editor.toPlainText() else "Add caption")

    def clear_image(self, unavailable=False):
        if self.image_preview is None:
            return
        self.image_preview.setPixmap(QPixmap())
        self._last_preview_size = QSize()
        self.image_preview.setText(
            "Image preview unavailable" if unavailable else "Image preview loads as you scroll")


class PhotoStoryDialog(QDialog):
    """Three-panel native editor for a single chronological photo story."""

    THEMES = {
        "editorial": ("#ffffff", "#20242a", "#68717a", "#b7bec6", "#f0f2f4", "Noto Serif", 24, "THE STORY", "Bright, elegant editorial presentation.", 1, 3, 8),
        "cinematic": ("#111318", "#f6f1e9", "#b8b4ad", "#d1a56a", "#090b0e", "Noto Serif", 28, "CINEMA JOURNAL", "Dramatic photographs and warm gold accents.", 1, 2, 4),
        "journal": ("#f5ead4", "#463729", "#75644e", "#b38b59", "#e3d2b3", "DejaVu Serif", 25, "FIELD NOTES", "Paper tones and a personal travel-journal feel.", 1, 4, 3),
        "essay": ("#edf1f3", "#182532", "#596874", "#527e94", "#dce3e7", "Noto Sans", 23, "PHOTO ESSAY", "Clean documentary presentation.", 1, 2, 2),
        "monochrome": ("#f3f3f1", "#171717", "#555555", "#222222", "#dadad8", "DejaVu Serif", 27, "BLACK / WHITE", "Monochrome photography and strong typography.", 2, 0, 0),
        "museum": ("#f6f4ee", "#292b2d", "#65635e", "#a68a59", "#e7e3d8", "DejaVu Serif", 27, "THE COLLECTION", "Quiet gallery walls and exhibition-style labels.", 1, 1, 0),
        "postcard": ("#f3dfc5", "#5a352c", "#89624f", "#bd6954", "#ead0ab", "DejaVu Serif", 26, "POSTCARDS", "Vintage warmth and nostalgic framing.", 3, 4, 9),
        "bold": ("#f7f6f1", "#10151e", "#424b58", "#ed613b", "#e1e4e8", "Noto Sans", 29, "THE BIG PICTURE", "Large typography and energetic contrast.", 3, 2, 2),
        "midnight": ("#101f35", "#f0f5ff", "#b2c6dd", "#6ebedb", "#0b182a", "Noto Serif", 27, "AFTER DARK", "Deep blue, luminous accents, and atmosphere.", 1, 2, 5),
        "golden": ("#fff3df", "#4a3324", "#8a6247", "#d99045", "#ead4b3", "DejaVu Serif", 26, "GOLDEN HOUR", "Soft cream, amber highlights, and warmth.", 1, 3, 7),
    }

    def __init__(self, paths=()):
        super().__init__()
        self.setWindowTitle("KIMng - Create a gallery")
        self.resize(1460, 900)
        self.setMinimumSize(980, 620)
        self._closing = False
        self._initial_canvas_selection = True
        self._layout_user_override = False
        self._setting_layout_from_type = False
        self.active_element_id = ""
        self._canvas_driving_selection = False
        self.canvas_blocks = {}
        self._full_story_preview_window = None
        self.destination_parent = self._initial_destination_parent(paths)
        self.destination_parent_explicit = False
        self._destination_sources = tuple(paths)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 12)
        outer.setSpacing(10)
        heading = QLabel("Create a gallery")
        title_font = QFont(heading.font())
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        heading.setFont(title_font)
        outer.addWidget(heading)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)
        self._build_sequence_panel(paths)
        self._build_editor_panel()
        self._build_settings_panel()
        self.splitter.setSizes([305, 785, 325])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        self.status = QLabel("Add images or story elements to begin.")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        footer = QHBoxLayout()
        self.preview_button = QPushButton("Preview in browser")
        self.preview_button.setObjectName("previewGalleryInBrowser")
        self.preview_button.setIcon(QIcon.fromTheme(
            "internet-web-browser",
            self.style().standardIcon(QStyle.SP_BrowserReload)))
        self.preview_button.clicked.connect(self.preview_in_browser)
        self.preview_button.setIconSize(QSize(16, 16))
        self.preview_button.setMaximumWidth(170)
        self.preview_button.setAutoDefault(False)
        self.preview_button.setDefault(False)
        self.preview_button.setToolTip(
            "Open a temporary gallery preview in your browser")
        self.preview_button.setSizePolicy(
            QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.full_preview_button = self.preview_button
        footer.addWidget(self.preview_button)
        footer.addStretch(1)

        self.buttons = QDialogButtonBox()
        self.review_button = QPushButton("Review Changes")
        self.review_button.setObjectName("primaryAction")
        style_button(self.review_button, "review")
        self.review_button.clicked.connect(self.review_publication)
        self.buttons.addButton(
            self.review_button, QDialogButtonBox.AcceptRole)

        self.cancel_button = QPushButton("Cancel")
        style_button(self.cancel_button, "cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.buttons.addButton(
            self.cancel_button, QDialogButtonBox.RejectRole)

        self.close_button = self.cancel_button
        footer.addWidget(self.buttons)
        outer.addLayout(footer)
        QTimer.singleShot(0, self._validate_editor_destination)

        self.sequence_view.selection_changed.connect(self._selection_changed)
        self.sequence_view.list.itemClicked.connect(
            lambda item: self._scroll_canvas_to(item.data(ID_ROLE)))
        self.sequence_view.sequence_changed.connect(self._sequence_changed)
        self.sequence_view.idle.connect(self._finish_close_if_ready)
        self.story_title.textChanged.connect(self._update_status)
        self.story_title.textChanged.connect(self._update_destination_label)
        self.introduction.textChanged.connect(self._update_status)
        self.sequence_view.list.verticalScrollBar().valueChanged.connect(
            self.sequence_view.queue_thumbnails)
        self.canvas_scroll.verticalScrollBar().valueChanged.connect(self._canvas_scrolled)
        self._scroll_debounce = QTimer(self)
        self._scroll_debounce.setSingleShot(True)
        self._scroll_debounce.setInterval(45)
        self._scroll_debounce.timeout.connect(self._update_active_from_canvas)
        self._selection_changed(self.sequence_view.selected_id())
        self._initial_canvas_selection = False
        self._update_status()

    @property
    def sequence(self):
        return self.sequence_view.sequence

    def _build_sequence_panel(self, paths):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        label = QLabel("Story order")
        label.setStyleSheet("font-weight: 700; font-size: 15px;")
        layout.addWidget(label)
        self.sequence_view = StorySequenceView(self, paths)
        layout.addWidget(self.sequence_view, 1)
        self.story_list = self.sequence_view.list
        self.splitter.addWidget(panel)

    def _build_editor_panel(self):
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(8, 0, 8, 0)
        self.canvas_scroll = QScrollArea()
        self.canvas_scroll.setObjectName("continuousStoryCanvas")
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setFrameShape(QFrame.NoFrame)
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.canvas_scroll.setAccessibleName("Continuous story editor")
        self.canvas_content = QWidget()
        self.canvas_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.editor_layout = QVBoxLayout(self.canvas_content)
        self.editor_layout.setContentsMargins(4, 4, 10, 26)
        self.editor_layout.setSpacing(18)

        self.story_header = QFrame()
        self.story_header.setObjectName("storyDetails")
        self.story_header.setFrameShape(QFrame.StyledPanel)
        header_layout = QVBoxLayout(self.story_header)
        header_layout.setContentsMargins(18, 16, 18, 18)
        header_layout.setSpacing(9)
        title_label = QLabel("Story title")
        title_label.setStyleSheet("font-weight: 650;")
        self.story_title = QLineEdit()
        self.story_title.setPlaceholderText("Give your story a title")
        self.story_title.setAccessibleName("Story title")
        intro_label = QLabel("Introduction")
        intro_label.setStyleSheet("font-weight: 650;")
        self.introduction = StoryTextEdit("Set the scene before the first image.", minimum=92)
        self.introduction.setAccessibleName("Story introduction")
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.story_title)
        header_layout.addWidget(intro_label)
        header_layout.addWidget(self.introduction)
        self.editor_layout.addWidget(self.story_header)
        for element in self.sequence.elements:
            self._create_canvas_block(element)
        self.editor_layout.addStretch(1)
        self._wire_description_tab_order()
        self.canvas_scroll.setWidget(self.canvas_content)
        self.editor_scroll = self.canvas_scroll
        layout.addWidget(self.canvas_scroll, 1)
        self.splitter.addWidget(shell)

    def _build_settings_panel(self):
        panel = QWidget()
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(12)
        heading = QLabel("Gallery settings")
        heading.setStyleSheet("font-weight: 700; font-size: 15px;")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.gallery_type_selector = QComboBox()
        self.gallery_type_selector.setAccessibleName("Gallery type")
        for label, key in (("Travelogue", "travelogue"), ("Photo essay", "photo-essay"),
                           ("Illustrated story", "illustrated-story"),
                           ("Simple gallery", "simple-gallery")):
            self.gallery_type_selector.addItem(label, key)
        self.gallery_type_selector.setCurrentIndex(1)
        form.addRow("Gallery type", self.gallery_type_selector)

        self.visual_style_selector = QComboBox()
        self.visual_style_selector.setAccessibleName("Visual style")
        for label, key in (("Classic", "classic"), ("Modern", "modern"),
                           ("Dramatic", "dramatic"),
                           ("Light", "simple-light"),
                           ("Dark", "simple-dark")):
            self.visual_style_selector.addItem(label, key)
        self.visual_style_selector.setCurrentIndex(1)
        form.addRow("Visual style", self.visual_style_selector)

        self.layout_selector = QComboBox()
        self.layout_selector.setAccessibleName("Image arrangement")
        for label, key in (("One image", "one-per-section"),
                           ("Up to two images", "two-per-section"),
                           ("Adaptive", "adaptive")):
            self.layout_selector.addItem(label, key)
        self.layout_selector.setItemData(0, "One image per story section", Qt.ToolTipRole)
        self.layout_selector.setItemData(1, "Up to two images per story section", Qt.ToolTipRole)
        self.layout_selector.setItemData(2, "Adaptive photographic layout", Qt.ToolTipRole)
        self.layout_selector.setCurrentIndex(2)
        self.layout_reset_button = QPushButton("Reset to type default")
        self.layout_reset_button.setVisible(False)
        self.layout_reset_button.clicked.connect(self._reset_layout_to_type_default)
        layout.addLayout(form)
        arrangement_label = QLabel("Image arrangement")
        arrangement_label.setStyleSheet("font-weight: 650;")
        layout.addWidget(arrangement_label)
        layout.addWidget(self.layout_selector)
        layout.addWidget(self.layout_reset_button, alignment=Qt.AlignRight)

        self.style_preview_card = QFrame()
        self.style_preview_card.setObjectName("galleryStylePreview")
        self.style_preview_card.setFrameShape(QFrame.StyledPanel)
        preview_layout = QVBoxLayout(self.style_preview_card)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(4)
        self.style_preview_title = QLabel("Photo essay · Modern")
        self.style_preview_title.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.style_preview_image = QLabel("Selected image preview")
        self.style_preview_image.setAlignment(Qt.AlignCenter)
        self.style_preview_image.setMinimumHeight(54)
        self.style_preview_image.setMaximumHeight(92)
        self.style_preview_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.style_preview_image.setAccessibleName("Compact gallery appearance preview")
        self.style_preview_image.setStyleSheet("background: palette(alternate-base); border-radius: 4px;")
        self.style_preview_note = QLabel("Photography leads the sequence")
        self.style_preview_note.setWordWrap(True)
        preview_layout.addWidget(self.style_preview_title)
        preview_layout.addWidget(self.style_preview_image)
        preview_layout.addWidget(self.style_preview_note)
        layout.addWidget(self.style_preview_card)

        self.show_captions = QCheckBox("Show captions in gallery")
        self.show_captions.setChecked(False)
        self.show_filenames = QCheckBox("Show filenames in gallery")
        self.show_filenames.setChecked(False)
        layout.addWidget(self.show_captions)
        layout.addWidget(self.show_filenames)

        self.output_format_selector = QComboBox()
        self.output_format_selector.setAccessibleName("Output format")
        self.output_format_selector.addItem("Gallery folder (recommended)", "folder")
        self.output_format_selector.addItem("ZIP archive", "zip")
        output_format_label = QLabel("Output format")
        output_format_label.setStyleSheet("font-weight: 650;")
        layout.addWidget(output_format_label)
        layout.addWidget(self.output_format_selector)
        self.output_format_explanation = QLabel()
        self.output_format_explanation.setWordWrap(True)
        self.output_format_explanation.setObjectName("outputFormatExplanation")
        layout.addWidget(self.output_format_explanation)

        self._destination_manual = False

        self.destination_label = QLabel("Destination")
        self.destination_label.setStyleSheet("font-weight: 650;")
        layout.addWidget(self.destination_label)

        # Keep the validated destination state without displaying
        # a cramped single-line path editor.
        self.destination_edit = QLineEdit()
        self.destination_edit.setObjectName("galleryDestinationPath")
        self.destination_edit.textEdited.connect(
            self._destination_edited)
        self.destination_edit.textChanged.connect(
            self._validate_editor_destination)
        self.destination_edit.hide()

        self.destination_button = QPushButton(
            "Change destination…")
        self.destination_button.setIcon(
            QIcon.fromTheme("folder-open"))
        self.destination_button.clicked.connect(
            self.change_destination)
        layout.addWidget(
            self.destination_button, 0, Qt.AlignLeft)

        self.destination_path = QLabel()
        self.destination_path.setObjectName(
            "galleryDestinationDisplay")
        self.destination_path.setWordWrap(True)
        self.destination_path.setMinimumWidth(0)
        self.destination_path.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        self.destination_path.setToolTip(
            "Complete planned gallery output path")
        layout.addWidget(self.destination_path)

        self.destination_feedback = QLabel()
        self.destination_feedback.setWordWrap(True)
        layout.addWidget(self.destination_feedback)

        # Retain the legacy Qt preview's theme data without exposing its old
        # ten-theme selector as if those were complete HTML visual styles.
        self.theme_selector = QComboBox(self)
        for name, key in (("Clean editorial", "editorial"), ("Cinematic dark", "cinematic"),
                          ("Travel journal", "journal"), ("Photo essay", "essay"),
                          ("Black and white", "monochrome"), ("Museum exhibit", "museum"),
                          ("Vintage postcard", "postcard"), ("Modern bold", "bold"),
                          ("Midnight blue", "midnight"), ("Golden hour", "golden")):
            self.theme_selector.addItem(name, key)
        self.theme_selector.hide()
        self.gallery_type_selector.currentIndexChanged.connect(self._gallery_type_changed)
        self.visual_style_selector.currentIndexChanged.connect(self._update_style_preview)
        self.layout_selector.currentIndexChanged.connect(self._layout_changed)
        self.output_format_selector.currentIndexChanged.connect(self._update_output_format)
        layout.addStretch(1)
        self._update_output_format()
        self._update_style_preview()
        self._update_destination_label()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setMinimumWidth(310)
        self.settings_scroll.setAccessibleName("Gallery settings")
        self.settings_scroll.setWidget(panel)
        self.splitter.addWidget(self.settings_scroll)

    def _gallery_type_changed(self, *_):
        if not self._layout_user_override:
            from kim_story_publication import default_layout_for_type
            self._setting_layout_from_type = True
            try:
                default = default_layout_for_type(self.gallery_type_selector.currentData())
                self.layout_selector.setCurrentIndex(self.layout_selector.findData(default))
            finally:
                self._setting_layout_from_type = False
        self.layout_reset_button.setVisible(self._layout_user_override)
        self._update_style_preview()

    def _layout_changed(self, *_):
        if not self._setting_layout_from_type:
            self._layout_user_override = True
        self.layout_reset_button.setVisible(self._layout_user_override)
        self._update_style_preview()

    def _reset_layout_to_type_default(self):
        from kim_story_publication import default_layout_for_type
        self._layout_user_override = False
        self._setting_layout_from_type = True
        try:
            default = default_layout_for_type(self.gallery_type_selector.currentData())
            self.layout_selector.setCurrentIndex(self.layout_selector.findData(default))
        finally:
            self._setting_layout_from_type = False
        self.layout_reset_button.setVisible(False)
        self._update_style_preview()

    def _update_style_preview(self, *_):
        gallery_type = self.gallery_type_selector.currentData()
        visual_style = self.visual_style_selector.currentData()
        labels = {"travelogue": "Travelogue", "photo-essay": "Photo essay",
                  "illustrated-story": "Illustrated story",
                  "simple-gallery": "Simple gallery"}
        style_names = {"classic": "Classic", "modern": "Modern", "dramatic": "Dramatic",
                       "simple-light": "Light",
                       "simple-dark": "Dark"}
        notes = {
            "travelogue": "One image at a time, with generous room for the journey.",
            "photo-essay": "Photography leads, with a deliberate mix of singles and pairs.",
            "illustrated-story": "Long-form prose leads, with images supporting the story.",
            "simple-gallery": "Images in order, with descriptions directly underneath.",
        }
        self.style_preview_title.setText(
            f"{labels[gallery_type]} · {style_names[visual_style]}")
        arrangement = self.layout_selector.currentData()
        arrangement_note = {
            "one-per-section": "Single-image sections",
            "two-per-section": "Consecutive pairs where image shapes fit",
            "adaptive": "Deterministic mix of single images and pairs",
        }[arrangement]
        self.style_preview_note.setText(f"{notes[gallery_type]}\n{arrangement_note}")
        palettes = {
            "classic": ("#edf2f7", "#152336", "#2476b3"),
            "modern": ("#f8f8f6", "#17232d", "#39718e"),
            "dramatic": ("#101114", "#f4f0e9", "#c6a979"),
            "simple-light": ("#ffffff", "#17212b", "#216c9c"),
            "simple-dark": ("#12161c", "#f1f4f7", "#7ac4f4"),
        }
        background, foreground, accent = palettes[visual_style]
        typeface = "Georgia, 'Times New Roman', serif" if visual_style != "modern" else "system-ui, sans-serif"
        ink = self.palette().windowText().color().name()
        muted = self.palette().mid().color().name()
        self.style_preview_card.setStyleSheet(
            "QFrame#galleryStylePreview { "
            "background: palette(window); "
            "border: 1px solid palette(mid); "
            "border-radius: 6px; }")
        self.style_preview_title.setStyleSheet(
            f"color: {ink}; font-size: 13px; font-weight: 700;")
        self.style_preview_note.setStyleSheet(
            f"color: {ink}; font-size: 12px;")
        self.style_preview_note.setVisible(True)
        self.style_preview_image.hide()

    def _update_style_preview_image(self):
        self.style_preview_image.hide()

    def _update_output_format(self, *_):
        if self.output_format_selector.currentData() == "zip":
            self.output_format_explanation.setText(
                "Creates one portable ZIP for transfer or archiving. Extract it to view the gallery, or upload its contents to a web host.")
        else:
            self.output_format_explanation.setText(
                "Creates a complete local gallery folder. Open index.html in a browser or upload its contents to a web host.")
        self._update_destination_label()

    def _create_canvas_block(self, element):
        block = StoryCanvasBlock(element, self.canvas_content,
                                 thumbnail_lookup=self.sequence_view.get_thumbnail)
        block.content_changed.connect(self._canvas_content_changed)
        block.focused.connect(self._canvas_field_focused)
        self.canvas_blocks[element.id] = block
        self.editor_layout.insertWidget(self.sequence.index_of(element.id) + 1, block)
        if element.kind == "image":
            block.clear_image(element.source in self.sequence_view.unavailable)
            cached = self.sequence_view.thumbnails.get(element.source)
            if cached is not None:
                block.set_image(cached)
        return block

    def _wire_description_tab_order(self):
        """Keep Tab navigation between image descriptions in story order."""
        previous = self.introduction
        for element in self.sequence.elements:
            if element.kind != "image":
                continue
            block = self.canvas_blocks.get(element.id)
            if block is None or block.description_editor is None:
                continue
            QWidget.setTabOrder(previous, block.description_editor)
            previous = block.description_editor

    def _sync_canvas_structure(self):
        wanted = [element.id for element in self.sequence.elements]
        original = set(self.canvas_blocks)
        for element_id in tuple(self.canvas_blocks):
            if element_id not in wanted:
                block = self.canvas_blocks.pop(element_id)
                self.editor_layout.removeWidget(block)
                block.deleteLater()
        for element in self.sequence.elements:
            if element.id not in self.canvas_blocks:
                self._create_canvas_block(element)
        actual = [self.editor_layout.itemAt(index).widget().element_id
                  for index in range(1, self.editor_layout.count() - 1)
                  if self.editor_layout.itemAt(index).widget() is not None
                  and hasattr(self.editor_layout.itemAt(index).widget(), "element_id")]
        if actual != wanted:
            for block in self.canvas_blocks.values():
                self.editor_layout.removeWidget(block)
            for index, element in enumerate(self.sequence.elements, 1):
                self.editor_layout.insertWidget(index, self.canvas_blocks[element.id])
        self._wire_description_tab_order()
        return any(element_id not in original for element_id in wanted)

    def canvas_element_order(self):
        return [self.editor_layout.itemAt(index).widget().element_id
                for index in range(1, self.editor_layout.count())
                if self.editor_layout.itemAt(index).widget() is not None
                and hasattr(self.editor_layout.itemAt(index).widget(), "element_id")]

    def _sequence_changed(self):
        added = self._sync_canvas_structure()
        self._update_status()
        image_sources = tuple(
            item.source for item in self.sequence.elements if item.kind == "image")
        if image_sources != self._destination_sources:
            self._destination_sources = image_sources
            self._update_destination_label()
        if added and self.active_element_id in self.canvas_blocks:
            self._selection_changed(self.active_element_id)
        self.sequence_view.queue_thumbnails()

    def refresh_canvas_element(self, element_id):
        """Refresh a persistent block after a deliberate external model edit."""
        element = self.sequence.get(element_id)
        block = self.canvas_blocks[element_id]
        if element.kind == "image":
            for widget, value in ((block.image_heading, element.heading),
                                  (block.description_editor, element.description),
                                  (block.caption_editor, element.caption)):
                widget.blockSignals(True)
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                else:
                    widget.setPlainText(value)
                widget.blockSignals(False)
            block.caption_toggle.setText("Edit caption" if element.caption else "Add caption")
            block.caption_toggle.setToolTip(element.caption or "Optional short caption")

    def _canvas_content_changed(self, element_id, field, value):
        self.sequence_view.update_element(element_id, **{field: value})

    def _canvas_field_focused(self, element_id):
        if element_id != self.active_element_id:
            self._canvas_driving_selection = True
            self.sequence_view._select_id(element_id, scroll=False)
            self._canvas_driving_selection = False

    def _selection_changed(self, element_id):
        self.active_element_id = element_id
        element = self.sequence.get(element_id) if element_id else None
        block = self.canvas_blocks.get(element_id)
        self.image_heading = block.image_heading if block and element.kind == "image" else None
        self.image_caption = block.caption_editor if block and element.kind == "image" else None
        self.heading_editor = block.heading_editor if block and element.kind == "heading" else None
        self.text_editor = block.passage_editor if block and element.kind == "text" else None
        if (not self._initial_canvas_selection and not self._canvas_driving_selection
                and element is not None):
            QTimer.singleShot(0, lambda eid=element_id: self._scroll_canvas_to(eid))
        self._update_status()

    def _scroll_canvas_to(self, element_id):
        block = self.canvas_blocks.get(element_id)
        if block is None:
            return
        top = block.mapTo(self.canvas_scroll.viewport(), block.rect().topLeft()).y()
        bar = self.canvas_scroll.verticalScrollBar()
        target = max(0, min(bar.maximum(), bar.value() + top - 14))
        bar.setValue(target)

    def _canvas_scrolled(self, *_):
        self._scroll_debounce.start()
        self.sequence_view.queue_thumbnails()

    def _update_active_from_canvas(self):
        elements = self.sequence.elements
        if not elements:
            return
        bar = self.canvas_scroll.verticalScrollBar()
        anchor = bar.value() + 42
        selected = elements[0]
        for element in elements:
            block = self.canvas_blocks.get(element.id)
            if block is None:
                continue
            top = block.mapTo(self.canvas_content, block.rect().topLeft()).y()
            if top <= anchor:
                selected = element
            else:
                break
        if selected.id != self.active_element_id:
            self._canvas_driving_selection = True
            self.sequence_view._select_id(selected.id, scroll=False)
            self._canvas_driving_selection = False

    def visible_canvas_image_sources(self):
        bar = self.canvas_scroll.verticalScrollBar()
        top = bar.value() - 420
        bottom = bar.value() + self.canvas_scroll.viewport().height() + 420
        sources = []
        for element in self.sequence.elements:
            if element.kind != "image":
                continue
            block = self.canvas_blocks.get(element.id)
            if block is None:
                continue
            block_top = block.mapTo(self.canvas_content, block.rect().topLeft()).y()
            if top <= block_top + block.height() and block_top <= bottom:
                sources.append(element.source)
        return sources

    def _update_canvas_thumbnail(self, path):
        image = self.sequence_view.thumbnails.get(path)
        if image is None:
            return
        for element in self.sequence.elements:
            if element.kind == "image" and element.source == path:
                self.canvas_blocks[element.id].set_image(image)
        self._update_style_preview_image()

    def _clear_canvas_thumbnail(self, path):
        unavailable = path in self.sequence_view.unavailable
        for element in self.sequence.elements:
            if element.kind == "image" and element.source == path:
                self.canvas_blocks[element.id].clear_image(unavailable)
        self._update_style_preview_image()

    def _update_status(self, *_):
        elements = self.sequence.elements if hasattr(self, "sequence_view") else []
        counts = {kind: sum(item.kind == kind for item in elements)
                  for kind in ("image", "heading", "text")}
        self.status.setText(
            f"{counts['image']} images, {counts['heading']} heading{'s' if counts['heading'] != 1 else ''}, "
            f"{counts['text']} text passage{'s' if counts['text'] != 1 else ''}."
            if elements else "Add images or story elements to begin.")

    def _field_label(self, value):
        label = QLabel(value)
        label.setStyleSheet("font-weight: 650;")
        return label

    def add_heading(self, after_id=None):
        element = self.sequence_view.add_heading(after_id)
        block = self.canvas_blocks.get(element.id)
        if block is not None and block.heading_editor is not None:
            block.heading_editor.setFocus(Qt.OtherFocusReason)
            block.heading_editor.selectAll()
        return element

    def add_text(self, after_id=None):
        element = self.sequence_view.add_text(after_id)
        block = self.canvas_blocks.get(element.id)
        if block is not None and block.passage_editor is not None:
            block.passage_editor.setFocus(Qt.OtherFocusReason)
        return element

    def add_paths(self, paths):
        return self.sequence_view.add_paths(paths)

    def move_element(self, element_id, destination):
        return self.sequence_view.move(element_id, destination)

    def remove_element(self, element_id):
        return self.sequence_view.remove(element_id)

    def open_full_story_preview(self):
        from kim_photo_story_preview import StoryPreviewWindow

        window = StoryPreviewWindow(
            self,
            title=self.story_title.text(),
            introduction=self.introduction.toPlainText(),
            elements=self.sequence.elements,
            theme_key=self.theme_selector.currentData(),
            hide_filenames=not self.show_filenames.isChecked(),
            source_stamps=self.sequence_view.source_stamps,
            source_aspects={
                path: image.width() / image.height()
                for path, image in self.sequence_view.thumbnails.items()
                if image.height() > 0
            },
        )
        self._full_story_preview_window = window
        try:
            return window.exec()
        finally:
            self._full_story_preview_window = None
            window.deleteLater()

    @staticmethod
    def _initial_destination_parent(paths):
        parents = set()
        for path in paths:
            try:
                parents.add(str(Path(path).resolve(strict=True).parent))
            except OSError:
                continue
        return next(iter(parents)) if len(parents) == 1 else ""

    def _update_destination_label(self):
        if not self.destination_parent_explicit and hasattr(
                self, "sequence_view"):
            parents = set()
            for element in self.sequence.elements:
                if element.kind != "image":
                    continue
                try:
                    parents.add(str(
                        Path(element.source).resolve(strict=True).parent))
                except OSError:
                    pass
            self.destination_parent = (
                next(iter(parents)) if len(parents) == 1 else "")

        from kim_story_publication import publication_slug
        if not getattr(self, "_destination_manual", False):
            if self.destination_parent:
                name = publication_slug(self.story_title.text())
                if (hasattr(self, "output_format_selector")
                        and self.output_format_selector.currentData()
                        == "zip"):
                    name += ".zip"
                value = str(Path(self.destination_parent) / name)
            else:
                value = ""
            if hasattr(self, "destination_edit"):
                self.destination_edit.setText(value)
        if hasattr(self, "destination_edit"):
            self.destination_label.setText(
                "Destination" if self.destination_parent
                else "Destination: choose a shared destination.")
            self._validate_editor_destination()

    def _destination_edited(self, value):
        self._destination_manual = True

    def _validate_editor_destination(self, *_):
        if not hasattr(self, "destination_edit"):
            return
        value = self.destination_edit.text().strip()
        self.destination_path.setText(
            value or "Choose a shared destination directory.")
        self.destination_path.setToolTip(value)
        problem = ""
        if not value:
            problem = "Choose a shared destination directory."
        elif not Path(value).is_absolute():
            problem = "Enter an absolute destination path."
        elif os.path.lexists(value):
            problem = (
                "A gallery already exists at this location. "
                "Choose another destination."
            )
        else:
            parent = Path(value).parent
            if not parent.is_dir():
                problem = "The destination directory does not exist."
            elif not os.access(parent, os.W_OK | os.X_OK):
                problem = "The destination directory is not writable."
            elif (hasattr(self, "output_format_selector")
                  and self.output_format_selector.currentData() == "zip"
                  and Path(value).suffix.casefold() != ".zip"):
                problem = "ZIP gallery output must end in .zip."

        self.destination_feedback.setText(problem)
        self.destination_feedback.setVisible(bool(problem))
        if hasattr(self, "review_button"):
            self.review_button.setEnabled(not problem)
        return not problem

    def change_destination(self):
        current = self.destination_edit.text().strip()
        start = str(Path(current).parent) if current else (
            self.destination_parent or str(Path.home()))
        selected = QFileDialog.getExistingDirectory(
            self, "Choose gallery destination directory", start,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if selected:
            self.destination_parent = str(Path(selected).resolve())
            self.destination_parent_explicit = True
            self._destination_manual = False
            self._update_destination_label()

    def _publication_document(self):
        from kim_story_publication import make_document
        return make_document(
            self.story_title.text(), self.introduction.toPlainText(),
            self.sequence.elements,
            style=self.visual_style_selector.currentData(),
            publication_type=self.gallery_type_selector.currentData(),
            hide_filenames=not self.show_filenames.isChecked(),
            source_identities=self.sequence_view.source_stamps,
            show_captions=self.show_captions.isChecked(),
            layout=self.layout_selector.currentData(),
            output_format=self.output_format_selector.currentData(),
        )

    def preview_in_browser(self):
        from kim_story_publish import prepare_for_browser
        try:
            document = self._publication_document()
            prepared = prepare_for_browser(self, document)
        except Exception as exc:
            QMessageBox.warning(self, "Gallery preview unavailable", str(exc))
            return
        if prepared is None:
            return
        index = Path(prepared.workspace) / "index.html"
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(index))):
            QMessageBox.warning(self, "Browser unavailable", "KDE could not open the local gallery preview.")

    def review_publication(self):
        from kim_story_publish import StoryReviewDialog
        if not self._validate_editor_destination():
            self.destination_edit.setFocus()
            return

        document = self._publication_document()
        destination = self.destination_edit.text().strip()

        try:
            review = StoryReviewDialog(document, destination, self)
        except Exception as exc:
            QMessageBox.warning(
                self, "Gallery plan unavailable", str(exc))
            return

        try:
            result = review.exec()
            output = (
                review.publication_path
                if result == QDialog.Accepted else "")
            cancel_story = review.cancel_requested
            reviewed_destination = review.destination
        finally:
            review.deleteLater()

        if reviewed_destination != destination:
            self._destination_manual = True
            self.destination_edit.setText(reviewed_destination)
            self._validate_editor_destination()

        if cancel_story:
            return
        if output:
            self._show_publication_complete(output)

    def _show_publication_complete(self, output):
        message = QMessageBox(self)
        is_zip = Path(output).suffix.casefold() == ".zip"
        message.setWindowTitle("Gallery created")
        message.setIcon(QMessageBox.Information)
        message.setText("Your offline gallery is ready.")
        message.setInformativeText(output)
        open_site = message.addButton("Open ZIP archive" if is_zip else "Open gallery",
                                      QMessageBox.AcceptRole)
        open_folder = message.addButton("Open containing folder" if is_zip else "Open folder",
                                        QMessageBox.ActionRole)
        message.addButton(QMessageBox.Close)
        message.exec()
        clicked = message.clickedButton()
        if clicked == open_site:
            path = output if is_zip else str(Path(output) / "index.html")
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif clicked == open_folder:
            folder = str(Path(output).parent) if is_zip else output
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _finish_close_if_ready(self):
        if self._closing and self.sequence_view.thumbnail_worker is None:
            QDialog.done(self, QDialog.Rejected)

    def closeEvent(self, event):
        if self.sequence_view.thumbnail_worker is not None:
            self._closing = True
            self.sequence_view.stop()
            event.ignore()
            return
        self.sequence_view.stop()
        event.accept()

    def reject(self):
        if self.sequence_view.thumbnail_worker is not None:
            self._closing = True
            self.sequence_view.stop()
            return
        self.sequence_view.stop()
        super().reject()


def main(argv=None):
    paths = list(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KIMng Photo Story")
    app.setOrganizationName("KIMng")
    dialog = PhotoStoryDialog(paths)
    return dialog.exec()


if __name__ == "__main__":
    raise SystemExit(main())
