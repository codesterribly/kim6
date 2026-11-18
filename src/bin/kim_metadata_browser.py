#!/usr/bin/env python3
"""Standalone, read-only KIMng Metadata Browser."""
from __future__ import annotations
from kim_dialog_buttons import style_button, style_button_box

import json
import os
from collections import OrderedDict
from collections.abc import MutableMapping
from datetime import datetime
from dataclasses import dataclass, is_dataclass
from collections import Counter
import time
from pathlib import Path
import re
import signal
import sys

try:
    from PySide6.QtCore import QSettings, Qt, QThread, Signal, QAbstractItemModel, QAbstractTableModel, QSize, QRect, QModelIndex, QTimer, QItemSelectionModel, QLocale, QMimeData, QUrl, QEvent, QPersistentModelIndex
    from PySide6.QtGui import QIcon, QImage, QPalette, QPixmap, QFont, QDrag, QColor, QAction, QPainter, QPen
    from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QScrollArea,
        QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QTableView, QVBoxLayout,
        QWidget, QHeaderView, QAbstractItemView, QFrame, QGridLayout,
        QTreeView, QProgressBar, QStackedWidget, QComboBox, QToolButton, QStyle,
        QDialog, QDialogButtonBox, QMessageBox, QSizePolicy, QFormLayout,
        QTableWidget, QTableWidgetItem,
        QStyledItemDelegate, QStyleOptionViewItem, QToolTip, QMenu)
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        print("KIMng Metadata Browser requires PySide6. Install the KIMng Qt runtime and try again.", file=sys.stderr)
        raise SystemExit(2) from exc
    raise

from kim_metadata_reader import MetadataEntry, MetadataRecord, read_metadata, value_text, associated_xmp_sidecars, _source_path, _select_fields
from kim_metadata_sources import (MetadataSourcePreferences, preferred_entry, source_name,
    OverviewPreferences, OverviewField, OVERVIEW_DEFAULTS, PINNED_DEFAULTS, OVERVIEW_CATALOG)
from kim_metadata_compare import compare_records, compare_overview_records, _entry_display, is_difference
from kim_photo_selection import read_thumbnail
from kim_preview import identity
from kim_process import inspection_context
from kim_metadata_gps_actions import (gps_field, is_gps_entry, entry_key, action_owner,
    add_field_controls, GPSActionDelegate, GPSField)


DISPLAY_LIMIT = 240
TAG_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsSelectable
CURRENT_RECORD = object()



def kimng_simple_field_label(label):
    """Friendly display name without storage hierarchy."""
    name = str(label).split(" · ", 1)[0].strip()
    aliases = {
        "ExposureTime": "Shutter Speed",
        "ShutterSpeedValue": "Shutter Speed",
        "FNumber": "Aperture",
        "ApertureValue": "Aperture",
        "PhotographicSensitivity": "ISO",
        "ISOSpeedRatings": "ISO",
        "FocalLength": "Focal Length",
        "DateTimeOriginal": "Capture Date",
        "CreateDate": "Creation Date",
        "ImageWidth": "Image Width",
        "ImageHeight": "Image Height",
        "ExposureBiasValue": "Exposure Compensation",
        "ExposureCompensation": "Exposure Compensation",
        "ExposureProgram": "Exposure Program",
        "ExposureMode": "Exposure Mode",
        "WhiteBalance": "White Balance",
    }
    return aliases.get(name, name)


def metadata_alternatives(entry, record):
    names = next((field.selectors for field in OVERVIEW_DEFAULTS
                  if entry.name.casefold() in {name.casefold() for name in field.selectors}), (entry.name,))
    names = {name.casefold() for name in names}
    return [entry] + [other for other in record.entries if other is not entry and other.name.casefold() in names]


def raw_metadata_value(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


class OverviewSection(QWidget):
    """A native grid whose columns follow the available width and font size."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fields = []
        self.columns = 0
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 4, 0, 8)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def add_field(self, widget, wide=False):
        self.fields.append((widget, wide))
        self.columns = 0
        self._reflow(self.width())

    def _reflow(self, width):
        minimum = self.fontMetrics().horizontalAdvance('Camera capture information') + 24
        columns = max(1, min(3, (width + 18) // (minimum + 18)))
        if columns == self.columns:
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        row = column = 0
        for widget, wide in self.fields:
            span = columns if wide else 1
            if column + span > columns:
                row += 1
                column = 0
            self.grid.addWidget(widget, row, column, 1, span, Qt.AlignTop)
            column += span
            if column == columns:
                row += 1
                column = 0
        self.grid.invalidate()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        self._reflow(width)
        return self.grid.totalHeightForWidth(width)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def resizeEvent(self, event):
        self._reflow(event.size().width())
        self.updateGeometry()
        super().resizeEvent(event)


@dataclass(eq=False)
class ValueNode:
    name: str
    value: object
    parent: object = None
    children: object = None
    iterator: object = None


class StructureModel(QAbstractItemModel):
    """Inspect original typed values, fetching only expanded children."""
    def __init__(self, value, parent=None):
        super().__init__(parent)
        self.root = ValueNode('Value', value, children=[])

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return len(parent.internalPointer().children) if parent.isValid() and parent.column() == 0 else 0 if parent.isValid() else 1

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        node = parent.internalPointer().children[row] if parent.isValid() else self.root
        return self.createIndex(row, column, node)

    def parent(self, index):
        if not index.isValid() or index.internalPointer().parent is None:
            return QModelIndex()
        parent = index.internalPointer().parent
        row = parent.parent.children.index(parent) if parent.parent else 0
        return self.createIndex(row, 0, parent)

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        return parent.column() == 0 and isinstance(parent.internalPointer().value, (dict, list)) and bool(parent.internalPointer().value)

    def canFetchMore(self, parent):
        return parent.isValid() and parent.column() == 0 and self.hasChildren(parent) and len(parent.internalPointer().children) < len(parent.internalPointer().value)

    def fetchMore(self, parent):
        if not self.canFetchMore(parent):
            return
        from itertools import islice
        node = parent.internalPointer()
        if node.iterator is None:
            node.iterator = iter(node.value.items()) if isinstance(node.value, dict) else enumerate(node.value)
        children = [ValueNode(str(key), value, node, []) for key, value in islice(node.iterator, 128)]
        first = len(node.children)
        self.beginInsertRows(parent, first, first + len(children) - 1)
        node.children.extend(children)
        self.endInsertRows()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ('Member', 'Value', 'Type')[section]

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            node = index.internalPointer()
            value = node.value
            summary = f'{len(value)} elements' if isinstance(value, (dict, list)) else 'Explicitly empty' if value in ('', None) else _compact(value)
            return (node.name, summary, type(value).__name__)[index.column()]


class MetadataDetailsDialog(QDialog):
    """Readable provenance and lazy typed inspection shared by metadata views."""
    def __init__(self, entries, parent=None, field_name=None):
        super().__init__(parent)
        self.entries = list(entries) or [None]
        self.setWindowTitle('Metadata details')
        self.resize(740, 540)
        layout = QVBoxLayout(self)
        self.alternatives = QComboBox()
        for index, entry in enumerate(self.entries):
            text = f'{entry.name} · {entry.group} · {Path(entry.source).name}' + (f' · {entry.language}' if entry.language else '') if entry else 'Not present'
            self.alternatives.addItem(f'{index + 1}: {text}')
        self.alternatives.setAccessibleName('Available representations')
        layout.addWidget(QLabel('Available representations'))
        layout.addWidget(self.alternatives)
        form = QFormLayout()
        self.properties = {}
        for name in ('Name', 'State', 'Metadata family', 'Group', 'Qualified identifier', 'Source', 'Language'):
            label = QLabel()
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            self.properties[name] = label
            form.addRow(name, label)
        layout.addLayout(form)
        self.scalar = QPlainTextEdit()
        self.scalar.setReadOnly(True)
        layout.addWidget(self.scalar, 1)
        self.structure = QTreeView()
        self.structure.setUniformRowHeights(True)
        self.structure.header().setSectionResizeMode(QHeaderView.Stretch)
        self.expanded_structures = set()
        self.structure.expanded.connect(lambda index: self.expanded_structures.add(QPersistentModelIndex(index)))
        self.structure.collapsed.connect(lambda index: self.expanded_structures.discard(QPersistentModelIndex(index)))
        self.structure_timer = QTimer(self)
        self.structure_timer.setSingleShot(True)
        self.structure_timer.timeout.connect(self.fetch_structure_rows)
        self.structure.verticalScrollBar().valueChanged.connect(lambda value:
            self.structure_timer.start(0) if value >= self.structure.verticalScrollBar().maximum() > 0 else None)
        layout.addWidget(self.structure, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        style_button_box(buttons)
        buttons.rejected.connect(self.reject)
        self.raw_copy = buttons.addButton('Copy raw value', QDialogButtonBox.ActionRole)
        self.raw_copy.setIcon(QIcon.fromTheme('edit-copy'))
        self.raw_copy.clicked.connect(self.copy_raw)
        layout.addWidget(buttons)
        self.field_name = field_name
        self.alternatives.currentIndexChanged.connect(self.show_representation)
        self.show_representation(0)

    def show_representation(self, index):
        entry = self.entries[index]
        values = (entry.name if entry else self.field_name or 'Field',
                  'Not present' if entry is None else 'Explicitly empty' if entry.value in ('', None, [], {}) else 'Present',
                  MetadataBrowser._metadata_family(entry) if entry else '', entry.group if entry else '',
                  entry.qualified_name if entry else '', entry.source if entry else '', entry.language or 'Not specified' if entry else '')
        for label, value in zip(self.properties.values(), values):
            label.setText(value)
        structured = entry is not None and isinstance(entry.value, (dict, list))
        self.scalar.setVisible(not structured)
        self.structure.setVisible(structured)
        self.raw_copy.setEnabled(entry is not None)
        if structured:
            self.expanded_structures.clear()
            old = self.structure.model()
            self.structure.setModel(StructureModel(entry.value, self.structure))
            if old:
                old.deleteLater()
        else:
            self.scalar.setPlainText(value_text(entry.value) if entry else 'Not present')

    def fetch_structure_rows(self):
        scroll = self.structure.verticalScrollBar()
        if not self.isVisible() or scroll.value() < scroll.maximum():
            return
        model = self.structure.model()
        for parent in tuple(self.expanded_structures):
            if parent.isValid() and self.structure.isExpanded(parent) and model.canFetchMore(parent):
                model.fetchMore(parent)

    def copy_raw(self):
        entry = self.entries[self.alternatives.currentIndex()]
        if entry is not None:
            QApplication.clipboard().setText(raw_metadata_value(entry.value))


class PinDelegate(QStyledItemDelegate):
    """One delegate per view, with no button widgets allocated for rows."""
    toggled = Signal(object)

    def __init__(self, view, preferences, destination='overview'):
        super().__init__(view)
        self.view, self.preferences, self.destination = view, preferences, destination
        self.pressed = None
        view.setItemDelegateForColumn(0, self)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self.context_menu)

    def pin_rect(self, rect):
        extent = self.view.style().pixelMetric(QStyle.PM_SmallIconSize)
        return QRect(rect.left() + 4, rect.center().y() - extent // 2, extent, extent)

    def pinned(self, index):
        entry = index.data(Qt.UserRole)
        return isinstance(entry, MetadataEntry) and self.preferences.is_pinned(entry, index.model().record)

    def action_text(self, index):
        return ('Remove from ' if self.pinned(index) else 'Show in ') + self.destination

    def paint(self, painter, option, index):
        if not isinstance(index.data(Qt.UserRole), MetadataEntry):
            return super().paint(painter, option, index)
        cell = QStyleOptionViewItem(option)
        cell.rect.setLeft(self.pin_rect(option.rect).right() + 6)
        super().paint(painter, cell, index)
        pinned = self.pinned(index)
        icon = QIcon.fromTheme('pin' if pinned else 'list-add', self.view.style().standardIcon(
            QStyle.SP_DialogApplyButton if pinned else QStyle.SP_FileDialogNewFolder))
        icon.paint(painter, self.pin_rect(option.rect))

    def helpEvent(self, event, view, option, index):
        if isinstance(index.data(Qt.UserRole), MetadataEntry) and self.pin_rect(option.rect).contains(event.pos()):
            QToolTip.showText(event.globalPos(), self.action_text(index), view)
            return True
        return super().helpEvent(event, view, option, index)

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space:
            index = self.view.currentIndex().siblingAtColumn(0)
            if isinstance(index.data(Qt.UserRole), MetadataEntry):
                self.toggled.emit(index)
                return True
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) and watched is self.view.viewport():
            index = self.view.indexAt(event.position().toPoint())
            hit = index.column() == 0 and isinstance(index.data(Qt.UserRole), MetadataEntry) and self.pin_rect(self.view.visualRect(index)).contains(event.position().toPoint())
            if event.button() == Qt.LeftButton and event.type() == QEvent.MouseButtonPress:
                self.pressed = QPersistentModelIndex(index) if hit else None
                return bool(hit)
            if self.pressed is not None:
                pressed, self.pressed = self.pressed, None
                if hit and pressed == index:
                    self.toggled.emit(index)
                return True
        return super().eventFilter(watched, event)

    def context_menu(self, point):
        index = self.view.indexAt(point)
        if not index.isValid():
            index = self.view.currentIndex()
        index = index.siblingAtColumn(0)
        if not isinstance(index.data(Qt.UserRole), MetadataEntry):
            return
        menu = QMenu(self.view)
        action = menu.addAction(self.action_text(index))
        target = QPersistentModelIndex(index)
        action.triggered.connect(lambda: self.toggled.emit(QModelIndex(target)) if target.isValid() else None)
        menu.exec(self.view.viewport().mapToGlobal(point if point.x() >= 0 else self.view.visualRect(index).center()))


class PreviewLabel(QLabel):
    """Keep the bounded decoded preview crisp and fitted after window resizing."""
    painted = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(220, 150)
        self.setWordWrap(True)

    def set_image(self, image):
        if self.image.cacheKey() == image.cacheKey() and not image.isNull():
            return
        self.image = image
        if image.isNull():
            self.setPixmap(QPixmap())
        else:
            self._fit_image()

    def _fit_image(self):
        if self.image.isNull():
            return
        self.setPixmap(QPixmap.fromImage(self.image).scaled(
            self.contentsRect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the preview area close to its content's natural aspect ratio so
        # a wide landscape preview does not leave a tall empty frame around it.
        self.setMaximumHeight(max(180, int(self.width() * 0.8)))
        self._fit_image()

    def paintEvent(self, event):
        super().paintEvent(event)
        self.painted.emit()


class LoadedImageList(QListWidget):
    def startDrag(self, _actions):
        if self.currentItem() is None:
            return
        drag = QDrag(self)
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(self.currentItem().data(Qt.UserRole))])
        drag.setMimeData(data)
        drag.exec(Qt.CopyAction)


class ComparisonPreview(PreviewLabel):
    assigned = Signal(str)
    swapped = Signal()

    def __init__(self, side, parent):
        super().__init__(parent)
        self.side = side
        self.path = None
        self.setAcceptDrops(True)
        self.setAccessibleName('Left image' if side == 0 else 'Right image')
        self.setMinimumSize(100, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def resizeEvent(self, event):
        QLabel.resizeEvent(self, event)
        self._fit_image()

    def dragEnterEvent(self, event):
        data = event.mimeData()
        if data.hasFormat('application/x-kimng-slot') or (data.hasUrls() and len(data.urls()) == 1 and data.urls()[0].isLocalFile()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        data = event.mimeData()
        if data.hasFormat('application/x-kimng-slot'):
            if bytes(data.data('application/x-kimng-slot')) != str(self.side).encode():
                self.swapped.emit()
        elif data.hasUrls() and len(data.urls()) == 1 and data.urls()[0].isLocalFile():
            self.assigned.emit(data.urls()[0].toLocalFile())
        else:
            return
        event.acceptProposedAction()

    def mouseMoveEvent(self, event):
        if self.path and event.buttons() & Qt.LeftButton:
            drag = QDrag(self)
            data = QMimeData()
            data.setData('application/x-kimng-slot', str(self.side).encode())
            data.setUrls([QUrl.fromLocalFile(self.path)])
            drag.setMimeData(data)
            drag.exec(Qt.MoveAction)
        else:
            super().mouseMoveEvent(event)


class _DraggablePins(QListWidget):
    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dropEvent(self, event):
        super().dropEvent(event)
        if event.isAccepted():
            self.reordered.emit()


class OverviewFieldsDialog(QDialog):
    """Edit the shared, ordered selection without extracting metadata."""
    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences = preferences
        self.fields = list(preferences.fields)
        self.setWindowTitle('Configure pinned fields')
        self.resize(680, 540)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search fields or enter a technical tag name')
        layout.addWidget(self.search)
        explanation = QLabel(
            "Pin a field to show it in the Browser and Editor. "
            "Drag to reorder, or use Move up and Move down. "
            "Pinning does not change image metadata."
        )
        explanation.setTextFormat(Qt.PlainText)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.catalog = QListWidget()
        layout.addWidget(self.catalog)
        add = QPushButton('Add field')
        add.setIcon(QIcon.fromTheme('list-add'))
        layout.addWidget(add)
        self.selected = _DraggablePins()
        self.selected.reordered.connect(self._sync_drag_order)
        layout.addWidget(QLabel('Pinned in Browser and Editor, in this order:'))
        layout.addWidget(self.selected)
        actions = QHBoxLayout()
        for text, icon, action in (
                ('Move up', 'go-up', lambda: self.move(-1)),
                ('Move down', 'go-down', lambda: self.move(1)),
                ('Unpin field', 'list-remove', self.remove),
                ('Restore defaults', 'edit-undo', self.defaults)):
            button = QPushButton(text)
            button.setIcon(QIcon.fromTheme(icon))
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        style_button_box(buttons)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.refresh_catalog)
        add.clicked.connect(self.add)
        self.catalog.itemDoubleClicked.connect(lambda _item: self.add())
        self.refresh()

    def refresh_catalog(self):
        self.catalog.clear()
        needle = self.search.text().casefold()
        for field in OVERVIEW_CATALOG:
            if needle not in ' '.join((field.label, field.selector, *field.aliases)).casefold():
                continue
            pinned = any(item.key == field.key for item in self.fields)
            item = QListWidgetItem(f'{field.label} ({field.selector})' + (' · Already shown' if pinned else ''))
            item.setData(Qt.UserRole, field)
            self.catalog.addItem(item)

    def refresh(self):
        row = self.selected.currentRow()
        self.selected.clear()
        for field in self.fields:
            item = QListWidgetItem("⋮⋮  " + field.label)
            item.setData(Qt.UserRole, field)
            item.setToolTip(
                "Drag to reorder. "
                + field.selector
                + (f" · {field.source}" if field.source else "")
                + (f" · {field.language}" if field.language else "")
            )
            self.selected.addItem(item)
        self.selected.setCurrentRow(min(max(row, 0), len(self.fields) - 1))
        self.refresh_catalog()

    def _sync_drag_order(self):
        ordered = [
            self.selected.item(i).data(Qt.UserRole)
            for i in range(self.selected.count())
        ]
        if len(ordered) == len(self.fields) and {
                field.key for field in ordered
        } == {field.key for field in self.fields}:
            self.fields = ordered
            self.refresh_catalog()

    def add(self):
        item = self.catalog.currentItem()
        text = self.search.text().strip()
        field = item.data(Qt.UserRole) if item else next((field for field in OVERVIEW_CATALOG
            if text.casefold() in (field.selector.casefold(), field.label.casefold())), OverviewField(text, text))
        try:
            if any(existing.key == field.key for existing in self.fields):
                return
            self.preferences.validate([*self.fields, field])
            self.fields.append(field)
            self.refresh()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot add field', str(exc))

    def remove(self):
        row = self.selected.currentRow()
        if row >= 0:
            self.fields.pop(row)
            self.refresh()

    def move(self, delta):
        row = self.selected.currentRow()
        if 0 <= row + delta < len(self.fields):
            self.fields.insert(row + delta, self.fields.pop(row))
            self.refresh()
            self.selected.setCurrentRow(row + delta)

    def defaults(self):
        self.fields = list(PINNED_DEFAULTS)
        self.refresh()

    def save(self):
        try:
            self._sync_drag_order()
            self.preferences.save(self.fields)
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot save fields', str(exc))


def _text(value):
    return value_text(value)


def _compact(value):
    if isinstance(value, (dict, list)):
        parts = []
        remaining = DISPLAY_LIMIT
        for chunk in json.JSONEncoder(ensure_ascii=False).iterencode(value):
            parts.append(chunk[:remaining])
            remaining -= len(chunk)
            if remaining <= 0:
                return ''.join(parts)[:DISPLAY_LIMIT - 1] + '…'
        text = ''.join(parts)
    else:
        text = _text(value)[:DISPLAY_LIMIT + 1].replace("\r\n", "\n")
    text = text.replace("\n", " ↵ ")
    if len(text) <= DISPLAY_LIMIT:
        return text
    return text[:DISPLAY_LIMIT - 1] + "…"


def _overview_value(value):
    if isinstance(value, dict) and "x-default" in value:
        value = value["x-default"]
    if isinstance(value, list):
        return " · ".join(_text(item) for item in value)
    return _text(value)


def _entry_sources(entry, record):
    """Return concise, readable provenance labels for an overview value."""
    source_path = Path(entry.source).resolve(strict=False)
    image_path = Path(record.path).resolve(strict=False)
    if source_path != image_path:
        return [f"XMP sidecar ({source_path.name})"]
    groups = [entry.group, *(entry.groups or [])]
    labels = []
    for group in groups:
        folded = str(group).casefold()
        if folded.startswith("iptc"):
            label = "IPTC-IIM"
        elif folded.startswith("xmp"):
            label = "XMP"
        elif folded.startswith("exif"):
            label = "EXIF"
        else:
            continue
        if label not in labels:
            labels.append(label)
    return labels or ["Metadata"]


def _format_camera_value(label, value):
    """Format common camera values for people while leaving raw tags untouched."""
    text = _overview_value(value).strip()
    if label == "Capture date":
        try:
            captured = datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
            return f"{captured.strftime('%b %d, %Y').replace(' 0', ' ')} · {captured.strftime('%H:%M:%S')}"
        except ValueError:
            return text
    if label == "Image dimensions":
        match = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*(?:pixels?)?\s*", text, re.I)
        if match:
            return f"{match.group(1)} × {match.group(2)} pixels"
    elif label == "ISO" and not text.casefold().startswith("iso "):
        return f"ISO {text}"
    elif label == "Exposure" and not any(text.endswith(unit) for unit in (" s", " sec", " seconds")):
        return f"{text} s"
    elif label == "Aperture" and not text.casefold().startswith("f/"):
        return f"f/{text}"
    elif label == "Focal length":
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", text, re.I)
        if match:
            number = float(match.group(1))
            text = str(int(number)) if number.is_integer() else str(number)
            return f"{text} mm"
    return text


def _file_stamp(path):
    try:
        info = os.lstat(path)
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_atime_ns, info.st_mtime_ns, info.st_ctime_ns)
    except OSError:
        return None


def _record_stamp(path, sidecars):
    image = _file_stamp(path)
    if image is None:
        return None
    try:
        folder = os.stat(Path(path).parent)
    except OSError:
        return None
    return (image, (folder.st_dev, folder.st_ino, folder.st_mtime_ns, folder.st_ctime_ns),
            tuple((str(sidecar), _file_stamp(sidecar)) for sidecar in sidecars))


def _record_bytes(record):
    """Measure owned Python data outside the GUI thread, without serializing it."""
    pending = [record]
    seen = set()
    total = 0
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        total += sys.getsizeof(value)
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif is_dataclass(value) and not isinstance(value, type):
            pending.append(vars(value))
    return total


class InspectionCache(MutableMapping):
    """LRU with byte and entry limits; every lookup validates its source stamp."""
    def __init__(self, entries, budget, preview=False):
        self.limit = entries
        self.budget = budget
        self.preview = preview
        self.bytes = 0
        self._items = OrderedDict()

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(tuple(self._items))

    def __delitem__(self, key):
        self.bytes -= self._items.pop(key)[2]

    def clear(self):
        self._items.clear()
        self.bytes = 0

    def __getitem__(self, key):
        stamp, value, _weight = self._items[key]
        current = (_file_stamp(key) if self.preview else _record_stamp(key, value.sidecars))
        if (stamp is None and not getattr(value, 'error', False)) or current != stamp:
            del self[key]
            raise KeyError(key)
        self._items.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        stamp = _file_stamp(key) if self.preview else _record_stamp(key, value.sidecars)
        weight = value[0].sizeInBytes() if self.preview else _record_bytes(value)
        self.store(key, value, stamp, weight)

    def store(self, key, value, stamp, weight):
        if key in self._items:
            del self[key]
        if (stamp is None and not getattr(value, 'error', False)) or weight > self.budget:
            return
        self._items[key] = (stamp, value, weight)
        self.bytes += weight
        while len(self._items) > self.limit or self.bytes > self.budget:
            del self[next(iter(self._items))]


class PreviewWorker(QThread):
    completed = Signal(object, object, object)

    def __init__(self, path, parent, size=None):
        super().__init__(parent)
        self.path = path
        self.size = size or QSize(640, 480)

    def run(self):
        stamp = _file_stamp(self.path)
        try:
            with inspection_context(cancelled=self.isInterruptionRequested):
                image, _identity = read_thumbnail(self.path, self.size)
            if _file_stamp(self.path) != stamp:
                raise ValueError('Image changed while decoding its preview.')
            preview = (image, '')
        except Exception as exc:
            preview = (QImage(), str(exc))
        if not self.isInterruptionRequested():
            self.completed.emit(self.path, preview, stamp)


class MetadataWorker(QThread):
    completed = Signal(object, object, object)

    def __init__(self, paths, parent=None, fields=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.fields = fields
        self.stamps = {}
        self.weights = {}
        self.derived_fields = None
        self.derived_records = {}
        self.derived_weights = {}

    def run(self):
        for path in self.paths:
            if self.isInterruptionRequested():
                break
            try:
                identity(path)
                stamp = _record_stamp(path, associated_xmp_sidecars(path))
                with inspection_context(cancelled=self.isInterruptionRequested):
                    records = read_metadata([path], fields=self.fields)
                record = records[path]
                if not record.error and _record_stamp(path, record.sidecars) != stamp:
                    raise ValueError('Source or sidecars changed while reading metadata. Select the image again to retry.')
            except Exception as exc:
                record = MetadataRecord(path, error=str(exc))
                stamp = None
            if self.isInterruptionRequested():
                break
            self.stamps[path] = stamp
            self.weights[path] = _record_bytes(record)
            if self.isInterruptionRequested():
                break
            if self.fields is None and self.derived_fields is not None and not record.error:
                selection = _select_fields(self.derived_fields)
                derived = MetadataRecord(path, [entry for entry in record.entries if selection.includes(entry)],
                                         record.sidecars, record.error, record.warnings)
                self.derived_records[path] = derived
                self.derived_weights[path] = _record_bytes(derived)
            if not self.isInterruptionRequested():
                self.completed.emit({path: record}, {}, None)


class TagFilterWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, record, needle, column, descending, parent):
        super().__init__(parent)
        self.record = record
        self.needle = needle.casefold().strip()
        self.column = column
        self.descending = descending

    def run(self):
        matches = []
        for row, entry in enumerate(self.record.entries):
            if self.isInterruptionRequested():
                return
            if self.needle:
                text = ' '.join((entry.name, entry.qualified_name, entry.group, entry.source,
                                 str(entry.tag_id or ''), entry.language or '', _text(entry.value)))
                if self.needle not in text.casefold():
                    continue
            matches.append(row)
        if self.column is not None:
            def key(row):
                entry = self.record.entries[row]
                return (entry.name, _compact(entry.value), entry.group, str(entry.tag_id or ''))[self.column].casefold()
            matches.sort(key=key, reverse=self.descending)
        if not self.isInterruptionRequested():
            self.completed.emit(self.record, matches)


@dataclass
class ComparisonData:
    rows: tuple
    all_rows: tuple
    differences: tuple
    counts: dict
    conflicts: int
    seconds: float
    bytes: int


class ComparisonWorker(QThread):
    completed = Signal(object, object)

    def __init__(self, left, right, full, key, parent):
        super().__init__(parent)
        self.left, self.right, self.full, self.key = left, right, full, key
        self.overview_fields = OVERVIEW_DEFAULTS
        self.priority = ('Embedded XMP', 'XMP sidecar', 'IPTC-IIM', 'EXIF')
        self.locale = ''

    def run(self):
        try:
            started = time.perf_counter()
            with inspection_context(cancelled=self.isInterruptionRequested):
                rows = tuple(compare_records(self.left, self.right, include_technical=True) if self.full else
                             compare_overview_records(self.left, self.right, self.overview_fields, self.priority, self.locale))
                differences = tuple(index for index, row in enumerate(rows) if is_difference(row))
                counts = dict(Counter(row.state for row in rows))
                conflicts = MetadataBrowser._source_conflict_count(self.left, self.right)
            result = ComparisonData(rows, tuple(range(len(rows))), differences, counts, conflicts,
                                    0, 0)
            result.bytes = _record_bytes(result)
            result.seconds = time.perf_counter() - started
            if not self.isInterruptionRequested():
                self.completed.emit(result, None)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))


class ComparisonModel(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.rows = ()

    def set_result(self, result, differences=True):
        self.beginResetModel()
        self.result = result
        self.rows = (result.differences if differences else result.all_rows) if result else ()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 3

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ('Field', 'Left image', 'Right image')[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.result is None:
            return None
        row = self.result.rows[self.rows[index.row()]]
        if role == Qt.UserRole:
            return row
        if role == Qt.ToolTipRole:
            return f'{row.section}\n{row.identity}\nState: {row.state}. Open Details for complete values and provenance.'
        if role == Qt.BackgroundRole and index.column() and is_difference(row):
            base = QApplication.palette().color(QPalette.Base)
            rose = QColor.fromHslF(0.96, 0.45, 0.45 if base.lightnessF() > 0.5 else 0.65)
            return QColor.fromRgbF(*(base_component * 0.86 + rose_component * 0.14 for base_component, rose_component in
                                     zip(base.getRgbF()[:3], rose.getRgbF()[:3])))
        if role == Qt.DisplayRole:
            if index.column() == 0:
                state = 'Matching' if not is_difference(row) else {'different': 'Different', 'missing': 'Missing', 'empty': 'Empty'}.get(row.state, row.state)
                return f'{row.label} · {state}'
            return _entry_display(row.reference if index.column() == 1 else row.comparison)
        return None


DESCRIPTION_FIELDS = [
    ("Title", ("Title", "ObjectName")),
    ("Caption / Description", ("Description", "Caption-Abstract", "ImageDescription")),
    ("Keywords", ("Subject", "Keywords")),
]
RIGHTS_FIELDS = [
    ("Creator", ("Creator", "By-line", "Artist")),
    ("Copyright Notice", ("Rights", "CopyrightNotice", "Copyright")),
    ("Rights Usage Terms", ("UsageTerms", "RightsUsageTerms")),
]
CAMERA_FIELDS = [
    ("Camera", ("Make", "Model")),
    ("Lens", ("LensModel", "LensID")),
    ("Capture date", ("DateTimeOriginal", "CreateDate")),
    ("Image dimensions", ("ImageSize",)),
    ("ISO", ("ISO", "PhotographicSensitivity")),
    ("Exposure", ("ExposureTime",)),
    ("Aperture", ("FNumber", "Aperture")),
    ("Focal length", ("FocalLength",)),
    ("GPS position", ("GPSPosition", "GPSCoordinates", "GPSLatitude", "GPSLongitude")),
    ("GPS altitude", ("GPSAltitude",)),
    ("Location", ("Location", "City", "State", "Country", "CountryName")),
]
OVERVIEW_FIELDS = OverviewPreferences.validate(OVERVIEW_DEFAULTS)
ALWAYS_SHOW = {label for label, _aliases in DESCRIPTION_FIELDS + RIGHTS_FIELDS}

METADATA_FAMILY_ORDER = (
    "EXIF", "MakerNotes", "IPTC-IIM", "XMP", "File information",
    "Other", "ExifTool diagnostics",
)

# ExifTool's group 1 identifies the location or namespace of a tag. These
# values are manufacturer-specific MakerNotes groups, unlike standard EXIF
# locations such as IFD0, ExifIFD and GPS.
MAKERNOTE_GROUPS = {
    "canon", "canoncustom", "canondr4", "canonraw", "casio", "dji",
    "fujifilm", "garmin", "gopro", "htc", "infiray", "insta360",
    "kodak", "leica", "minolta", "nikon", "nikoncapture", "nikoncustom",
    "nikonscan", "nikonsettings", "olympus", "oneplus", "panasonic",
    "pentax", "phaseone", "qualcomm", "ricoh", "samsung", "sanyo",
    "sigma", "sony", "sonyiDC".casefold(), "vivo",
}


class TagModel(QAbstractItemModel):
    """Reference the complete record; format only cells requested by Qt."""
    BATCH_SIZE = 256

    def __init__(self, grouped, parent):
        super().__init__(parent)
        self.grouped = grouped
        self.record = None
        self.rows = []
        self.families = []
        self.available = []
        self.values = OrderedDict()
        self.pin_preferences = None
        self.pin_destination = 'overview'

    def set_record(self, record, rows=None):
        self.beginResetModel()
        self.record = record
        self.values.clear()
        self.rows = list(range(len(record.entries))) if record and rows is None else list(rows or ())
        self.families = []
        if self.grouped and record:
            groups = {}
            for row in self.rows:
                groups.setdefault(MetadataBrowser._metadata_family(record.entries[row]), []).append(row)
            self.families = [(family, groups[family]) for family in METADATA_FAMILY_ORDER if family in groups]
        lengths = [len(rows) for _family, rows in self.families] if self.grouped else [len(self.rows)]
        self.available = [min(self.BATCH_SIZE, length) for length in lengths]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            if not self.grouped or parent.internalId() or parent.column():
                return 0
            return self.available[parent.row()]
        return len(self.families) if self.grouped else self.available[0] if self.available else 0

    def canFetchMore(self, parent=QModelIndex()):
        if self.grouped:
            return (parent.isValid() and not parent.internalId() and parent.column() == 0 and
                    self.available[parent.row()] < len(self.families[parent.row()][1]))
        return not parent.isValid() and bool(self.available) and self.available[0] < len(self.rows)

    def fetchMore(self, parent=QModelIndex()):
        if not self.canFetchMore(parent):
            return
        group = parent.row() if self.grouped else 0
        total = len(self.families[group][1]) if self.grouped else len(self.rows)
        start = self.available[group]
        end = min(start + self.BATCH_SIZE, total)
        self.beginInsertRows(parent, start, end - 1)
        self.available[group] = end
        self.endInsertRows()

    def columnCount(self, parent=QModelIndex()):
        return 2 if self.grouped else 4

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        return self.createIndex(row, column, parent.row() + 1 if parent.isValid() else 0)

    def parent(self, index):
        if self.grouped and index.isValid() and index.internalId():
            return self.createIndex(index.internalId() - 1, 0, 0)
        return QModelIndex()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ('Field', 'Value')[section] if self.grouped else ('Tag', 'Value', 'Group', 'Identifier')[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled if self.grouped and not index.internalId() else TAG_FLAGS

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.record is None:
            return None
        if self.grouped and not index.internalId():
            family, rows = self.families[index.row()]
            if role == Qt.DisplayRole and index.column() == 0:
                return f'{family} ({len(rows)})'
            if role == Qt.UserRole + 1:
                return family
            if role == Qt.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return None
        row = (self.families[index.internalId() - 1][1][index.row()]
               if self.grouped else self.rows[index.row()])
        entry = self.record.entries[row]
        if role == Qt.UserRole:
            return entry
        if role == Qt.AccessibleDescriptionRole and self.pin_preferences is not None:
            action = 'Remove from ' if self.pin_preferences.is_pinned(entry, self.record) else 'Show in '
            return action + self.pin_destination + '. Press Space or open the context menu.'
        if role == Qt.ToolTipRole:
            return f'{entry.qualified_name}\n{entry.source}\nSelect this tag for its complete value.'
        if role != Qt.DisplayRole:
            return None
        if index.column() == 0:
            return MetadataBrowser._grouped_field_name(entry)
        if index.column() == 1:
            if row not in self.values:
                self.values[row] = _entry_display(entry) if isinstance(entry.value, (dict, list)) else _compact(entry.value)
                if len(self.values) > 512:
                    self.values.popitem(last=False)
            return self.values[row]
        if index.column() == 2:
            return entry.group
        identifier = f'ID {entry.tag_id}' if entry.tag_id is not None else ''
        if entry.language:
            identifier += f'; language {entry.language}'
        if entry.source != self.record.path:
            identifier += f'; {Path(entry.source).name}'
        return identifier.strip('; ')


class OverviewPresentation:
    """Shared read-only field presentation; extraction remains owned by each window."""

    def _entries(self, record, names):
        if not record:
            return []
        wanted = {name.casefold() for name in names}
        return [entry for entry in record.entries if entry.name.casefold() in wanted]


    @staticmethod
    def _subdued_label(text, parent=None):
        label = QLabel(text, parent)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setForegroundRole(QPalette.PlaceholderText)
        return label


    @staticmethod
    def _content_label(text, parent=None, prominent=False):
        label = QLabel(text, parent)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        if prominent:
            font = label.font()
            font.setPointSize(font.pointSize() + 2)
            font.setBold(True)
            label.setFont(font)
        return label


    def _section_heading(self, title, first=False):
        if not first:
            self.overview_layout.addSpacing(13)
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Plain)
            separator.setStyleSheet("color: palette(midlight)")
            self.overview_layout.addWidget(separator)
            self.overview_layout.addSpacing(10)
        if title not in self.section_expanded:
            self.section_expanded[title] = self.settings.value(f'overview/expanded/{title}', True, type=bool)
        expanded = self.section_expanded[title]
        heading = QToolButton()
        heading.setText(title.replace("&", "&&"))
        heading.setAccessibleName(title)
        heading.setCheckable(True)
        heading.setChecked(expanded)
        heading.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        heading.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        heading.setAutoRaise(True)
        font = heading.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        heading.setFont(font)
        body = OverviewSection()
        body.setVisible(expanded)
        heading.toggled.connect(lambda value, name=title, content=body, button=heading:
                                self._set_section_expanded(name, value, content, button))
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(heading)

        header_row.addStretch(1)
        self.overview_layout.addLayout(header_row)
        self.overview_layout.addWidget(body)
        self._overview_section = body


    def _set_section_expanded(self, section, expanded, body, button):
        self.section_expanded[section] = expanded
        body.setVisible(expanded)
        button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.settings.setValue(f"overview/expanded/{section}", expanded)
        body.updateGeometry()
        self.overview_layout.invalidate()
        self.overview_body.updateGeometry()


    def _add_missing_field(self, label):
        if not self.show_empty.isChecked():
            return
        row = QHBoxLayout()
        row.setSpacing(8)
        value = self._subdued_label("Not present")
        row.addWidget(value)
        row.addStretch(1)
        self.section_layout.addLayout(row)
        self.section_layout.addSpacing(4)


    def _preferred(self, record, aliases):
        entries = self._entries(record, aliases)
        chosen = preferred_entry(entries, record, self.metadata_preferences.priority,
                                 language_alt=True, locale=QLocale().name()) if entries else None
        if chosen is None and entries:
            priority = self.metadata_preferences.priority
            names = [name.casefold() for name in aliases]
            chosen = min(entries, key=lambda entry: (
                priority.index(source_name(entry, record)) if source_name(entry, record) in priority else len(priority),
                names.index(entry.name.casefold())))
        return chosen


    def _add_description_field(self, label, entries, record):
        if not entries:
            self._add_missing_field(label)
            return
        chosen = self._preferred(record, tuple(dict.fromkeys(entry.name for entry in entries)))
        if isinstance(chosen.value, dict) or (isinstance(chosen.value, list) and
                (len(chosen.value) > 12 or any(isinstance(item, (dict, list)) for item in chosen.value) or
                 sum(len(str(item)) for item in chosen.value) > 1000)):
            text = f'Structured value ({len(chosen.value)} elements)'
        elif isinstance(chosen.value, str) and len(chosen.value) > 2000:
            text = f'Long text ({len(chosen.value)} characters)'
        else:
            text = _overview_value(chosen.value) if chosen.value not in ('', None, [], {}) else 'Explicitly empty'
        value = self._content_label(text, prominent=label == 'Title')
        value.setToolTip('\n'.join(f'{entry.qualified_name}: {_compact(entry.value)}' for entry in entries))
        self.section_layout.addWidget(value)


    def _camera_values(self, label, aliases, record):
        def value(names):
            entry = self._preferred(record, names)
            return entry.value if entry is not None else None
        if label == 'Camera':
            text = ' '.join(_overview_value(value((name,))) for name in ('Make', 'Model') if value((name,)) is not None)
            return [text] if text else []
        if label == 'Image dimensions':
            width, height = value(('ImageWidth',)), value(('ImageHeight',))
            if width is not None and height is not None:
                return [f'{width} × {height} pixels']
            aliases = ('ImageSize',)
        if label == 'GPS position':
            from kim_location import coordinate
            from kim_location_ui import position_text
            def degrees(entry, name, latitude):
                match = re.fullmatch(r'''\s*(\d+) deg (\d+)' ([\d.]+)" ([NSEW])\s*''', str(entry.value))
                if match:
                    degree, minute, second, hemisphere = match.groups()
                    if float(minute) >= 60 or float(second) >= 60:
                        raise ValueError('Invalid coordinate')
                    return coordinate(float(degree) + float(minute) / 60 + float(second) / 3600, hemisphere, latitude)
                refs = [ref for ref in self._entries(record, (name,))
                        if ref.source == entry.source and ref.groups[:2] == entry.groups[:2]]
                ref = str(refs[0].value) if refs else None
                ref = {'North': 'N', 'South': 'S', 'East': 'E', 'West': 'W'}.get(ref, ref)
                return coordinate(entry.value, ref, latitude)
            latitudes = self._entries(record, ('GPSLatitude',))
            longitude = self._entries(record, ('GPSLongitude',))
            first = self._preferred(record, ('GPSLatitude',))
            latitudes = ([first] + [entry for entry in latitudes if entry is not first]) if first else latitudes
            for lat in latitudes:
                lon = next((entry for entry in longitude if entry.source == lat.source and entry.groups[:2] == lat.groups[:2]), None)
                if lon is not None:
                    try:
                        return [position_text((degrees(lat, 'GPSLatitudeRef', True),
                                               degrees(lon, 'GPSLongitudeRef', False)))]
                    except ValueError:
                        continue
            aliases = ('GPSPosition', 'GPSCoordinates')
        if label == 'GPS altitude':
            aliases = ('GPSAltitude',)
        selected = value(aliases)
        if selected is None:
            return []
        if label == 'GPS altitude':
            from kim_location_ui import height, preferred_units
            from kim_settings_dialog import load_settings, config_path
            match = re.match(r'^\s*([-+]?\d+(?:\.\d+)?)\s*(?:m(?:eters)?(?:\s|$)|$)', str(selected))
            if match:
                metres = float(match.group(1))
                altitude = self._preferred(record, aliases)
                references = [entry for entry in self._entries(record, ('GPSAltitudeRef',))
                              if entry.source == altitude.source and entry.groups[:2] == altitude.groups[:2]]
                reference = str(references[0].value).casefold() if references else ''
                if reference in ('1', '3', 'below sea level') or 'below sea level' in str(selected).casefold():
                    metres = -abs(metres)
                return [height(metres, preferred_units(load_settings(config_path())['KIM_LOCATION_UNITS']))]
        return [_format_camera_value(label, selected) if selected not in ('', [], {}) else 'Explicitly empty']


    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                OverviewPresentation._clear_layout(item.layout())
                item.layout().deleteLater()


    def show_metadata_details(self, entries, field_name=None):
        MetadataDetailsDialog(entries, self, field_name).exec()


    def render_overview(self, record):
        self.metadata_preferences.reload()
        self._clear_layout(self.overview_layout)
        self.overview_loading.setVisible(record is None)
        self.overview_retry.hide()
        self.overview_scroll.setVisible(record is not None)
        if record is None:
            return
        if record.error:
            self.overview_loading.setText(record.error)
            self.overview_loading.show()
            self.overview_retry.show()
            self.overview_scroll.hide()
            return
        self.overview_loading.setText('Loading metadata…')
        section = None
        fields = list(self.overview_preferences.fields)
        # The camera location stays discoverable even with no pins or values.
        gps_default = next(field for field in OVERVIEW_DEFAULTS if field.label == 'GPS position')
        if gps_default not in fields:
            fields.append(gps_default)
        camera_location_shown = False
        gps_cards = {}
        for field in fields:
            entries = field.entries(record)
            camera = field in OVERVIEW_DEFAULTS and field.section in ('Camera & capture', 'Location')
            values = self._camera_values(field.label, field.selectors, record) if camera else []
            subset = MetadataRecord(record.path, entries, record.sidecars)
            preferred = self._preferred(subset, tuple(dict.fromkeys(entry.name for entry in entries))) if entries else None
            visible_value = bool(values and values != ['Explicitly empty']) if camera else bool(
                preferred and preferred.value not in ('', None, [], {}))
            if not visible_value and not self.show_empty.isChecked() and field != gps_default:
                continue
            if field.section != section:
                self._section_heading(field.section, first=section is None)
                section = field.section
            card = QWidget()
            card.setObjectName('overviewField')
            self.section_layout = QVBoxLayout(card)
            self.section_layout.setContentsMargins(0, 0, 0, 0)
            self.section_layout.setSpacing(3)
            heading = QHBoxLayout()
            heading.setSpacing(12)
            field_heading = QLabel(kimng_simple_field_label(field.label))
            field_heading.setTextFormat(Qt.PlainText)
            field_heading.setWordWrap(True)
            heading_font = field_heading.font()
            heading_font.setBold(True)
            field_heading.setFont(heading_font)
            heading.addWidget(field_heading)
            details = QToolButton()
            details.setIcon(QIcon.fromTheme('dialog-information', self.style().standardIcon(QStyle.SP_MessageBoxInformation)))
            details.setToolTip('View field details')
            details.setAccessibleName(f'View {field.label} details')
            details.setFocusPolicy(Qt.StrongFocus)
            details.setAutoRaise(False)
            details.clicked.connect(lambda _checked=False, values=entries, name=field.label: self.show_metadata_details(values, name))
            heading.addWidget(details)
            gps_entry = preferred
            if field in OVERVIEW_DEFAULTS and field.label == 'GPS altitude':
                gps_entry = self._preferred(record, ('GPSAltitude',))
            if field == gps_default:
                gps_entry = self._preferred(record, ('GPSLatitude',)) or self._preferred(record, ('GPSPosition', 'GPSCoordinates'))
                context = gps_field(record, gps_entry)
                if gps_entry is not None and context.position is not None:
                    from kim_location_ui import position_text
                    values = [position_text(context.position)]
                elif gps_entry is not None:
                    values = [value_text(gps_entry.value)]
                else:
                    values = ['No embedded camera GPS coordinates']
            else:
                context = gps_field(record, gps_entry) if (is_gps_entry(gps_entry) or
                    field in OVERVIEW_DEFAULTS and field.label == 'GPS altitude') else None
            shared_card = False
            if context is not None:
                # Position and altitude in the same storage record share a
                # card and one action cluster. Distinct sources/records keep
                # their own controls and provenance.
                representation = (gps_entry.source, entry_key(gps_entry).rsplit(':', 1)[0],
                                  context.provenance.rsplit(' · ', 1)[-1], repr(context.position)) if gps_entry else ('missing-camera',)
                if representation in gps_cards:
                    card.deleteLater()
                    card, self.section_layout = gps_cards[representation]
                    shared_card = True
                else:
                    gps_cards[representation] = (card, self.section_layout)
                    add_field_controls(heading, action_owner(self), context)
                camera_location_shown |= context.camera
            heading.addStretch(1)
            self.section_layout.addLayout(heading)
            if camera:
                if not values:
                    self._add_missing_field(field.label)
                else:
                    for value in values:
                        self.section_layout.addWidget(self._content_label(value))
            else:
                self._add_description_field(field.label, entries, subset)
            # Keep provenance in field details, All tags,
            # and Sources & Targets, not below Overview values.
            shown = ' '.join(values) if camera else _compact(preferred.value) if preferred else ''
            wide = len(shown) > 90 or len(field.label) > 45 or '\n' in shown
            if not shared_card:
                self._overview_section.add_field(card, wide or context is not None)
        if not camera_location_shown:
            self._section_heading('Camera GPS location', first=section is None)
            card = QWidget()
            row = QHBoxLayout(card)
            context = gps_field(record)
            from kim_location_ui import position_text
            text = position_text(context.position) if context.position is not None else 'No verified embedded camera coordinates in this view.'
            row.addWidget(self._content_label('GPS location · ' + text), 1)
            add_field_controls(row, action_owner(self), context)
            self._overview_section.add_field(card, True)
        if section is None:
            self.overview_layout.addWidget(self._subdued_label('No configured metadata values are present.'))
        self.overview_layout.addStretch(1)


class MetadataOverview(QWidget, OverviewPresentation):
    """A read-only Overview using the same preferences and rendering as Browser."""
    retry = Signal()
    configuration_changed = Signal()

    def __init__(self, preferences, overview_preferences, parent=None):
        super().__init__(parent)
        self.metadata_preferences = preferences
        self.overview_preferences = overview_preferences
        self.settings = preferences.settings
        self.section_expanded = {}
        self.record = None
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.show_empty = QCheckBox("Show empty fields")
        self.show_empty.toggled.connect(lambda: self.render_overview(self.record))
        controls.addWidget(self.show_empty)
        configure = QPushButton("Configure fields…")
        configure.setIcon(QIcon.fromTheme("configure"))
        configure.clicked.connect(self.configure_fields)
        controls.addWidget(configure)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.overview_loading = QLabel("Loading metadata…")
        self.overview_loading.setTextFormat(Qt.PlainText)
        layout.addWidget(self.overview_loading)
        self.overview_retry = QPushButton("Retry metadata")
        self.overview_retry.clicked.connect(self.retry.emit)
        layout.addWidget(self.overview_retry, 0, Qt.AlignLeft)
        self.overview_scroll = QScrollArea()
        self.overview_scroll.setWidgetResizable(True)
        self.overview_body = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_body)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_layout.setSpacing(0)
        self.overview_scroll.setWidget(self.overview_body)
        layout.addWidget(self.overview_scroll, 1)
        self.set_record(None)

    def set_record(self, record):
        self.record = record
        self.render_overview(record)

    def configure_fields(self):
        if OverviewFieldsDialog(self.overview_preferences, self).exec() == QDialog.Accepted:
            self.configuration_changed.emit()


class ListThumbnails:
    """One low-priority list decode, shared by Browser and Editor."""

    def _store_thumbnail(self, path, image, stamp):
        image = image.scaled(QSize(96, 72), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if image.sizeInBytes() > self.thumbnails.budget:
            self._thumbnail_seen[path] = ('failed', stamp)
            return
        self.thumbnails.store(path, (image, ''), stamp, image.sizeInBytes())
        self._thumbnail_seen[path] = stamp
        self.image_list.item(self._path_rows[path]).setIcon(QIcon(QPixmap.fromImage(image).scaled(
            QSize(48, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        self._icon_paths.add(path)
        for old in tuple(self._icon_paths):
            if old not in self.thumbnails and old not in self.previews:
                self.image_list.item(self._path_rows[old]).setIcon(QIcon())
                self._icon_paths.discard(old)

    def _pump_thumbnails(self):
        """Fill at most four low-priority thumbnail decoder slots."""
        if (
            self._closing
            or not self.paths
            or len(self.thumbnail_workers) >= 4
        ):
            return

        # Never start background decoding ahead of selected-image
        # or comparison preview work.
        if any(
            self._preview_for(path) is None
            and not self._preview_failure(path)
            for path in self._wanted_previews()
        ):
            return

        visible = [
            self.image_list.row(
                self.image_list.itemAt(0, y)
            )
            for y in range(
                0,
                self.image_list.viewport().height(),
                max(1, self.image_list.sizeHintForRow(0)),
            )
        ]

        candidates = [
            self.paths[row]
            for row in dict.fromkeys(visible)
            if 0 <= row < len(self.paths)
        ]

        active = {
            worker.path for worker in self.thumbnail_workers
        }

        while len(self.thumbnail_workers) < 4:
            path = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate not in active
                    and self.thumbnails.get(candidate) is None
                    and self._thumbnail_seen.get(candidate)
                    != ('failed', _file_stamp(candidate))
                ),
                None,
            )

            while (
                path is None
                and self._thumbnail_cursor < len(self.paths)
            ):
                candidate = self.paths[self._thumbnail_cursor]
                self._thumbnail_cursor += 1

                if (
                    candidate in active
                    or self.thumbnails.get(candidate) is not None
                ):
                    continue

                seen = self._thumbnail_seen.get(candidate)

                if (
                    isinstance(seen, tuple)
                    and len(seen) == 2
                    and seen[0] == 'failed'
                ):
                    seen = seen[1]

                if seen != _file_stamp(candidate):
                    path = candidate

            if path is None:
                return

            cached = self._preview_for(path)

            if cached is not None:
                self._store_thumbnail(
                    path, cached[0], _file_stamp(path)
                )
                active.add(path)
                continue

            worker = PreviewWorker(
                path, self, QSize(96, 72)
            )
            self.thumbnail_workers.add(worker)
            active.add(path)

            worker.completed.connect(
                self._thumbnail_ready,
                Qt.QueuedConnection,
            )
            worker.finished.connect(
                lambda job=worker:
                self._thumbnail_finished(job),
                Qt.QueuedConnection,
            )

            worker.start(QThread.LowPriority)

    def _thumbnail_ready(self, path, value, stamp):
        if self._closing or path not in self._path_rows or stamp != _file_stamp(path):
            return
        if value[0].isNull():
            self._thumbnail_seen[path] = ('failed', stamp)
        else:
            self._store_thumbnail(path, value[0], stamp)

    def _thumbnail_finished(self, worker):
        self.thumbnail_workers.discard(worker)
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        else:
            QTimer.singleShot(0, self._pump_thumbnails)




class _ElidedMetadataPathLabel(QLabel):
    """Display one line without forcing the parent splitter to widen."""

    def __init__(self, text="", parent=None):
        super().__init__("", parent)
        self._full_text = ""
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full_text = str(text)
        self.setToolTip(self._full_text)
        self._update_elision()

    def _update_elision(self):
        width = max(0, self.contentsRect().width())
        displayed = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideMiddle, width
        )
        if displayed != self.text():
            self.setText(displayed)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(0)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elision()


class MetadataBrowser(QMainWindow, OverviewPresentation, ListThumbnails):
    def __init__(self, paths):
        super().__init__()
        initial_paths = [_source_path(Path(path).expanduser()) for path in paths]
        self.paths = []
        self.records = InspectionCache(4, 64 * 1024 * 1024)
        self.overview_records = InspectionCache(32, 16 * 1024 * 1024)
        self.previews = InspectionCache(16, 16 * 1024 * 1024, preview=True)
        self.thumbnails = InspectionCache(128, 4 * 1024 * 1024, preview=True)
        self.thumbnail_workers = set()
        self._thumbnail_seen = {}
        self._thumbnail_cursor = 0
        self.preview_workers = set()
        self._icon_paths = set()
        self.preview_generation = 0
        self._preview_error = None
        self._preview_failures = {}
        self._gif_preview_retries = set()
        self._active_preview = None
        self._active_overview = None
        self._selection_path = None
        self._selection_stamp = None
        self._pending_overview = None
        self._metadata_errors = {}
        self._active_full = None
        self._all_requested_path = None
        self._comparison_records = {}
        self._comparison_stamps = {}
        self._comparison_previews = {}
        self._comparison_overviews = {}
        self._comparison_overview_stamps = {}
        self._comparison_cache = OrderedDict()
        self.comparison_cache_budget = 64 * 1024 * 1024
        self._comparison_worker = None
        self._comparison_generation = 0
        self._comparison_cancelled = False
        self.comparison_data = None
        self._comparison_data_key = None
        self.comparison_slots = [None, None]
        self._single_splitter_sizes = None
        self._tag_record = None
        self._tag_rows = None
        self._tag_filter_worker = None
        self._tag_filter_pending = False
        self._tag_fetch_pending = False
        self._tag_sort_column = None
        self._tag_sort_descending = False
        self._closing = False
        self.worker = None
        self.worker_generation = 0
        self._activity_hide_timer = QTimer(self)
        self._activity_hide_timer.setSingleShot(True)
        self._activity_hide_timer.timeout.connect(
            self._hide_metadata_activity
        )
        self._metadata_prefetch_ready = False
        self._metadata_prefetch_attempted = set()
        self._metadata_scan_completed = set()
        self._metadata_scan_finished_announced = False
        self._metadata_prefetch_timer = QTimer(self)
        self._metadata_prefetch_timer.setSingleShot(True)
        self._metadata_prefetch_timer.setInterval(1000)
        self._metadata_prefetch_timer.timeout.connect(
            self._start_metadata_prefetch
        )
        self.close_after_worker = False
        self.add_button = None
        self.setWindowTitle("KIMng Metadata Browser")
        available = QApplication.primaryScreen().availableGeometry()
        minimum_width = min(900, max(620, available.width() - 24))
        minimum_height = min(560, max(480, available.height() - 48))
        self.setMinimumSize(minimum_width, minimum_height)
        self.resize(min(1160, max(minimum_width, available.width() - 24)),
                    min(740, max(minimum_height, available.height() - 60)))
        self.settings = QSettings("KIMng", "MetadataBrowser")
        self.metadata_preferences = MetadataSourcePreferences()
        self.overview_preferences = OverviewPreferences(self.metadata_preferences.settings)
        self.section_expanded = {
            name: self.settings.value(f"overview/expanded/{name}", True, type=bool)
            for name in ("Description", "Creator & rights", "Camera & capture")
        }
        self.group_expanded = {
            family: self.settings.value(f"tags/expanded/{family}", True, type=bool)
            for family in METADATA_FAMILY_ORDER
        }
        self.selected_entry = None
        self.compared_paths = None
        self.pending_comparison_paths = None

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.setCentralWidget(self.splitter)
        self._build_left()
        self._build_right()
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        sizes = self.settings.value("splitter", [400, 760])
        self.splitter.setSizes([int(size) for size in sizes])
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        if not initial_paths:
            self.choose_files()
        else:
            self.set_images(initial_paths)

    def _build_left(self):
        self.left_panel = QWidget()
        layout = QVBoxLayout(self.left_panel)
        layout.setContentsMargins(12, 12, 10, 12)
        layout.setSpacing(6)
        self.image_list = LoadedImageList()
        self.image_list.setMouseTracking(True)
        self.image_list.itemEntered.connect(
            self._metadata_item_hovered
        )
        self.image_list.setDragEnabled(True)
        self.image_list.currentRowChanged.connect(self.select_image)
        self.image_list.itemSelectionChanged.connect(self._selection_changed)
        self.image_list.setMinimumHeight(120)
        self.image_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.image_list.setIconSize(QSize(48, 36))
        self.image_list.setUniformItemSizes(True)
        self.image_list.verticalScrollBar().valueChanged.connect(lambda _value: self._pump_thumbnails())
        self.preview = PreviewLabel()
        self.preview.painted.connect(self._preview_painted)
        self.preview.setText("Choose one or more images to inspect")
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setFrameShadow(QFrame.Sunken)
        self.preview.setAutoFillBackground(True)
        palette = self.preview.palette()
        palette.setColor(self.preview.backgroundRole(), self.palette().color(self.backgroundRole()))
        self.preview.setPalette(palette)
        layout.addWidget(self.preview, 3)
        self.filename = _ElidedMetadataPathLabel("")
        self.filename.setStyleSheet("font-weight: 600")
        self.filename.setTextFormat(Qt.PlainText)
        self.filename.setWordWrap(False)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename.setToolTip("")
        self.filename.setMinimumWidth(0)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.format_label = QLabel("")
        self.format_label.setTextFormat(Qt.PlainText)
        self.format_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.format_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.format_label.setFixedHeight(self.format_label.sizeHint().height())
        self.position_label = QLabel("0 of 0")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.filename)

        details = QHBoxLayout()
        details.setSpacing(8)
        details.addWidget(self.format_label, 1)
        details.addWidget(self.position_label)
        layout.addLayout(details)

        directory_row = QHBoxLayout()
        directory_row.setSpacing(8)
        directory_row.addWidget(QLabel("Directory:"))
        self.directory_label = _ElidedMetadataPathLabel("")
        self.directory_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        directory_row.addWidget(self.directory_label, 1)
        layout.addLayout(directory_row)

        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.previous_button.clicked.connect(lambda: self._navigate_image(-1))
        self.next_button.clicked.connect(lambda: self._navigate_image(1))
        navigation.addWidget(self.previous_button, 1)
        navigation.addWidget(self.next_button, 1)
        layout.addLayout(navigation)
        selection_row = QHBoxLayout()
        selection_heading = QLabel("Loaded images")
        self.selection_heading = selection_heading
        selection_heading.setStyleSheet("font-weight: 600")
        selection_row.addWidget(selection_heading)
        self.selection_count = QLabel("0 images")
        self.selection_count.setStyleSheet("color: palette(placeholder-text)")
        selection_row.addWidget(self.selection_count)
        selection_row.addStretch(1)
        self.compare_images_button = QPushButton("Compare images")
        self.compare_images_button.setToolTip("Select exactly two images to compare their metadata")
        self.compare_images_button.setEnabled(False)
        self.compare_images_button.clicked.connect(self.compare_images)
        selection_row.addWidget(self.compare_images_button)
        self.add_button = QPushButton("Add images…")
        self.add_button.clicked.connect(self.choose_files)
        selection_row.addWidget(self.add_button)
        layout.addLayout(selection_row)
        self.metadata_activity = QLabel("")
        self.metadata_activity.setObjectName("metadataActivity")
        self.metadata_activity.setTextFormat(Qt.PlainText)
        self.metadata_activity.hide()
        layout.addWidget(self.metadata_activity)

        self.metadata_progress = QProgressBar()
        self.metadata_progress.setObjectName("metadataProgress")
        self.metadata_progress.setTextVisible(False)
        self.metadata_progress.setFixedHeight(7)
        self.metadata_progress.hide()
        layout.addWidget(self.metadata_progress)

        layout.addWidget(self.image_list, 2)

    def _build_right(self):
        self.right_panel = QWidget()
        layout = QVBoxLayout(self.right_panel)
        layout.setContentsMargins(10, 10, 10, 10)
        self.notice = QLabel("")
        self.notice.setTextFormat(Qt.PlainText)
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.notice.setStyleSheet("QLabel { color: palette(text); background: palette(alternate-base); padding: 6px; }")
        self.notice.hide()
        layout.addWidget(self.notice)
        self.status_summary = QLabel("Select images to inspect metadata")
        self.status_summary.setTextFormat(Qt.PlainText)
        self.status_summary.setStyleSheet("color: palette(placeholder-text)")
        self.status_summary.setWordWrap(True)
        layout.addWidget(self.status_summary)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.overview = QWidget()
        overview_layout = QVBoxLayout(self.overview)
        overview_layout.setContentsMargins(10, 10, 10, 10)
        overview_layout.setSpacing(8)
        self.show_empty = QCheckBox("Show empty fields")
        self.show_empty.toggled.connect(lambda _checked: self.update_overview())
        overview_layout.addWidget(self.show_empty)
        self.configure_overview = QPushButton('Configure fields…')
        self.configure_overview.setIcon(QIcon.fromTheme('configure'))
        self.configure_overview.clicked.connect(
            self.configure_overview_fields
        )
        overview_layout.addWidget(
            self.configure_overview, 0, Qt.AlignLeft
        )
        self.overview_loading = QLabel('Loading metadata…')
        self.overview_loading.setTextFormat(Qt.PlainText)
        overview_layout.addWidget(self.overview_loading)
        self.overview_retry = QPushButton('Retry metadata')
        self.overview_retry.setIcon(QIcon.fromTheme('view-refresh'))
        self.overview_retry.clicked.connect(self.retry_overview)
        self.overview_retry.hide()
        overview_layout.addWidget(self.overview_retry, 0, Qt.AlignLeft)
        self.overview_scroll = QScrollArea()
        self.overview_scroll.setWidgetResizable(True)
        self.overview_body = QWidget()
        self.overview_layout = QVBoxLayout(self.overview_body)
        self.overview_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_layout.setSpacing(0)
        self.overview_scroll.setWidget(self.overview_body)
        self.overview_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        overview_layout.addWidget(self.overview_scroll, 1)
        self.tabs.addTab(self.overview, "Overview")

        tags = QWidget()
        tags_layout = QVBoxLayout(tags)
        tags_layout.setContentsMargins(10, 10, 10, 10)
        tags_layout.setSpacing(8)
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search"))
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search tag names, values, groups or identifiers")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(QLabel("View:"))
        self.tag_view_mode = QComboBox()
        self.tag_view_mode.addItems(["Grouped", "Flat"])
        self.tag_view_mode.setToolTip("Choose grouped or flat metadata inspection")
        search_row.addWidget(self.tag_view_mode)
        tags_layout.addLayout(search_row)
        load_row = QHBoxLayout()
        self.all_tags_status = QLabel('Open All tags to read complete metadata.')
        self.all_tags_status.setTextFormat(Qt.PlainText)
        load_row.addWidget(self.all_tags_status, 1)
        self.all_tags_progress = QProgressBar()
        self.all_tags_progress.setRange(0, 0)
        self.all_tags_progress.setMaximumWidth(140)
        self.all_tags_progress.hide()
        load_row.addWidget(self.all_tags_progress)
        self.all_tags_cancel = QPushButton('Cancel')
        style_button(self.all_tags_cancel)
        self.all_tags_cancel.clicked.connect(self.cancel_all_tags)
        self.all_tags_cancel.hide()
        load_row.addWidget(self.all_tags_cancel)
        self.all_tags_retry = QPushButton('Load all metadata')
        self.all_tags_retry.clicked.connect(self._request_all_tags)
        self.all_tags_retry.hide()
        load_row.addWidget(self.all_tags_retry)
        tags_layout.addLayout(load_row)
        self.model = TagModel(False, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_tags)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 118)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.selectionModel().currentChanged.connect(self.show_entry_value)
        self.grouped_tree = QTreeView()
        self.grouped_model = TagModel(True, self)
        self.grouped_tree.setModel(self.grouped_model)
        self.grouped_tree.setRootIsDecorated(True)
        self.grouped_tree.setAlternatingRowColors(True)
        self.grouped_tree.setUniformRowHeights(True)
        self.grouped_tree.setWordWrap(False)
        self.grouped_tree.setTextElideMode(Qt.ElideRight)
        self.grouped_tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.grouped_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.grouped_tree.setColumnWidth(0, 235)
        self.grouped_tree.selectionModel().currentChanged.connect(self.show_grouped_entry)
        self.grouped_tree.expanded.connect(self._group_expanded)
        self.grouped_tree.collapsed.connect(self._group_collapsed)
        self.grouped_tree.verticalScrollBar().valueChanged.connect(self._tag_scroll_changed)
        self.tags_stack = QStackedWidget()
        self.tags_stack.addWidget(self.grouped_tree)
        self.tags_stack.addWidget(self.table)
        self.tag_details = QWidget()
        details_layout = QVBoxLayout(self.tag_details)
        details_layout.setContentsMargins(0, 3, 0, 0)
        details_layout.setSpacing(4)
        self.entry_identity = QLabel("")
        self.entry_identity.setTextFormat(Qt.PlainText)
        self.entry_identity.setWordWrap(True)
        self.entry_identity.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addWidget(self.entry_identity)
        self.value_detail = QPlainTextEdit()
        self.value_detail.setReadOnly(True)
        self.value_detail.setMinimumHeight(54)
        self.value_detail.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        details_layout.addWidget(self.value_detail, 1)
        self.details_placeholder = QLabel("Select a tag to inspect its details")
        self.details_placeholder.setTextFormat(Qt.PlainText)
        self.details_placeholder.setStyleSheet("color: palette(placeholder-text)")
        self.details_placeholder.setMinimumHeight(22)
        details_layout.addWidget(self.details_placeholder)
        self.entry_identity.hide()
        self.value_detail.hide()
        self.tags_splitter = QSplitter(Qt.Vertical)
        self.tags_splitter.addWidget(self.tags_stack)
        self.tags_splitter.addWidget(self.tag_details)
        self.tags_splitter.setStretchFactor(0, 4)
        self.tags_splitter.setStretchFactor(1, 1)
        self.tags_splitter.setCollapsible(0, False)
        self.tags_splitter.setCollapsible(1, False)
        self.tags_splitter.setSizes([420, 90])
        tags_layout.addWidget(self.tags_splitter, 1)
        copy_row = QHBoxLayout()
        self.copy_button = QPushButton("Copy raw value")
        self.pin_button = QAction('Show in overview', self)
        self.pin_button.setIcon(QIcon.fromTheme('list-add'))
        self.pin_button.setEnabled(False)
        self.pin_button.triggered.connect(self.toggle_overview_entry)
        for view, model in ((self.table, self.model), (self.grouped_tree, self.grouped_model)):
            model.pin_preferences = self.overview_preferences
            delegate = PinDelegate(view, self.overview_preferences)
            delegate.toggled.connect(lambda index: self.toggle_overview_entry(index.data(Qt.UserRole)))
            GPSActionDelegate(view, self, lambda index: gps_field(index.model().record, index.data(Qt.UserRole))
                              if isinstance(index.data(Qt.UserRole), MetadataEntry) else None)
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_value)
        copy_row.addWidget(self.copy_button)
        inspect = QPushButton('Details')
        inspect.setIcon(QIcon.fromTheme('dialog-information'))
        inspect.clicked.connect(lambda: self.show_metadata_details(metadata_alternatives(self.selected_entry, self._tag_record)) if self.selected_entry else None)
        copy_row.addWidget(inspect)
        copy_row.addStretch(1)
        tags_layout.addLayout(copy_row)
        self.tabs.addTab(tags, "All tags")
        self.search.textChanged.connect(self._filter_tags)
        self.tag_view_mode.currentTextChanged.connect(self._set_tag_view_mode)

        compare = QWidget()
        compare_layout = QVBoxLayout(compare)
        compare_layout.setContentsMargins(10, 8, 10, 8)
        compare_layout.setSpacing(7)
        compare_controls = QHBoxLayout()
        compare_controls.addWidget(QLabel("View:"))
        self.compare_scope = QComboBox()
        self.compare_scope.addItems(['Overview fields', 'All fields'])
        self.compare_scope.currentTextChanged.connect(self._compare_scope_changed)
        compare_controls.addWidget(self.compare_scope)
        self.compare_mode = QComboBox()
        self.compare_mode.addItems(['Differences only', 'All values'])
        self.compare_mode.currentTextChanged.connect(self._populate_comparison)
        compare_controls.addWidget(self.compare_mode)
        self.swap_button = QPushButton('Swap')
        self.swap_button.setIcon(QIcon.fromTheme('object-flip-horizontal'))
        self.swap_button.clicked.connect(self.swap_comparison)
        compare_controls.addWidget(self.swap_button)
        self.compare_progress = QProgressBar()
        self.compare_progress.setRange(0, 0)
        self.compare_progress.setMaximumWidth(100)
        self.compare_progress.hide()
        compare_controls.addWidget(self.compare_progress)
        self.compare_cancel = QPushButton('Cancel')
        style_button(self.compare_cancel)
        self.compare_cancel.clicked.connect(self.cancel_comparison)
        self.compare_cancel.hide()
        compare_controls.addWidget(self.compare_cancel)
        self.compare_retry = QPushButton('Load comparison')
        self.compare_retry.clicked.connect(self._compare_scope_changed)
        self.compare_retry.hide()
        compare_controls.addWidget(self.compare_retry)
        compare_controls.addStretch(1)
        compare_layout.addLayout(compare_controls)
        self.comparison_empty = QLabel(
            "Select two images in the list to compare their metadata. Use Ctrl+click to select the second image.")
        self.comparison_empty.setTextFormat(Qt.PlainText)
        self.comparison_empty.setWordWrap(True)
        self.comparison_empty.setAlignment(Qt.AlignCenter)
        self.comparison_empty.setStyleSheet("color: palette(placeholder-text)")
        compare_layout.addWidget(self.comparison_empty, 1)
        self.comparison_content = QWidget()
        content_layout = QVBoxLayout(self.comparison_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        preview_host = QWidget()
        image_header = QHBoxLayout(preview_host)
        image_header.setContentsMargins(0, 0, 0, 0)
        image_header.setSpacing(14)
        self.comparison_image_1_header = self._comparison_image_header("Left image", 0)
        self.comparison_image_2_header = self._comparison_image_header("Right image", 1)
        image_header.addWidget(self.comparison_image_1_header, 1)
        image_header.addWidget(self.comparison_image_2_header, 1)
        self.comparison_summary = QLabel("")
        self.comparison_summary.setTextFormat(Qt.PlainText)
        self.comparison_summary.setWordWrap(True)
        content_layout.addWidget(self.comparison_summary)
        self.comparison_model = ComparisonModel(self)
        self.comparison_tree = QTableView()
        self.comparison_tree.setModel(self.comparison_model)
        GPSActionDelegate(self.comparison_tree, self, self._comparison_gps_field, (1, 2))
        self.comparison_tree.setAlternatingRowColors(True)
        self.comparison_tree.setWordWrap(False)
        self.comparison_tree.setTextElideMode(Qt.ElideRight)
        self.comparison_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comparison_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.comparison_tree.verticalHeader().hide()
        self.comparison_tree.verticalHeader().setDefaultSectionSize(28)
        header = self.comparison_tree.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.comparison_tree.setColumnWidth(0, 190)
        self.comparison_field_space = QWidget()
        self.comparison_field_space.setFixedWidth(190)
        image_header.insertWidget(0, self.comparison_field_space)
        image_header.setSpacing(0)
        image_header.addStretch(1)
        header.sectionResized.connect(lambda *_args: self._align_comparison_columns())
        header.geometriesChanged.connect(self._align_comparison_columns)
        self.comparison_splitter = QSplitter(Qt.Vertical)
        self.comparison_splitter.setChildrenCollapsible(False)
        self.comparison_splitter.addWidget(preview_host)
        self.comparison_splitter.addWidget(self.comparison_tree)
        self.comparison_splitter.setStretchFactor(0, 3)
        self.comparison_splitter.setStretchFactor(1, 2)
        self.comparison_splitter.setSizes([340, 240])
        content_layout.addWidget(self.comparison_splitter, 1)
        details = QPushButton('Details…')
        details.setIcon(QIcon.fromTheme('dialog-information'))
        details.clicked.connect(self.show_comparison_details)
        content_layout.addWidget(details, 0, Qt.AlignRight)
        self.comparison_tree.doubleClicked.connect(lambda _index: self.show_comparison_details())
        self.comparison_content.hide()
        compare_layout.addWidget(self.comparison_content, 1)
        self.tabs.addTab(compare, "Compare")

        sources_panel = QWidget()
        sources_layout = QVBoxLayout(sources_panel)
        sources_layout.setContentsMargins(8, 8, 8, 8)

        self.sources_scroll = QScrollArea()
        self.sources_scroll.setWidgetResizable(True)
        self.sources_scroll.setFrameShape(QFrame.NoFrame)

        sources_body = QWidget()
        sources_content = QVBoxLayout(sources_body)
        sources_content.setContentsMargins(5, 5, 5, 5)
        sources_content.setSpacing(11)

        def section_heading(caption):
            label = QLabel(caption)
            label.setTextFormat(Qt.PlainText)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            sources_content.addWidget(label)

        def section_value():
            label = QLabel()
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(
                Qt.TextSelectableByMouse
            )
            sources_content.addWidget(label)
            return label

        self.sources_status = section_value()

        section_heading('Metadata reading priority')
        self.sources_priority = section_value()

        section_heading('Common metadata fields')
        self.sources_common = section_value()

        section_heading('Camera and GPS')
        self.sources_gps = section_value()

        section_heading('Associated sidecars')
        self.sources_sidecars = section_value()

        section_heading('Metadata representations')
        self.sources_representations = section_value()

        section_heading('Storage targets')
        self.sources_target_note = section_value()
        self.sources_target_note.setText(
            'Browser is read-only. No storage targets or '
            'metadata changes are proposed. Use the Editor '
            'to prepare changes and review their targets.'
        )

        sources_content.addStretch(1)

        self.sources_scroll.setWidget(sources_body)
        sources_layout.addWidget(self.sources_scroll, 1)

        self.tabs.addTab(
            sources_panel, 'Sources && Targets'
        )
        self.tabs.currentChanged.connect(self._tab_changed)

    def _comparison_image_header(self, role, side):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(role))
        panel.selector = QComboBox()
        panel.selector.setAccessibleName(role)
        panel.selector.addItem('Choose image…', None)
        panel.selector.currentIndexChanged.connect(lambda _row: self.assign_comparison(side, panel.selector.currentData()))
        layout.addWidget(panel.selector)
        panel.preview = ComparisonPreview(side, panel)
        panel.preview.assigned.connect(lambda path: self.assign_comparison(side, path))
        panel.preview.swapped.connect(self.swap_comparison)
        panel.preview.setText('Drop a loaded image here')
        layout.addWidget(panel.preview, 1)
        panel.filename = QLabel('')
        panel.filename.setTextFormat(Qt.PlainText)
        panel.filename.setWordWrap(True)
        layout.addWidget(panel.filename)
        panel.info = QLabel('')
        panel.info.setTextFormat(Qt.PlainText)
        layout.addWidget(panel.info)
        return panel

    def assign_comparison(self, side, path):
        if side not in (0, 1) or (path is not None and path not in self.paths):
            return
        opposite = 1 - side
        if path is not None and path == self.comparison_slots[opposite]:
            previous = self.comparison_slots[side]
            if previous is None or previous == path:
                self._update_slot_headers()
                self.comparison_summary.setText('Choose a different image for the other comparison slot.')
                return
            self.comparison_slots[opposite] = previous
        self._comparison_cancelled = False
        self.compare_retry.hide()
        self.comparison_model.set_result(None)
        self.comparison_slots[side] = path
        self.compared_paths = tuple(self.comparison_slots) if all(self.comparison_slots) else None
        self.pending_comparison_paths = self.compared_paths
        self._comparison_records.clear()
        self._comparison_stamps.clear()
        self._comparison_overviews.clear()
        self._comparison_overview_stamps.clear()
        self._comparison_previews = {key: value for key, value in self._comparison_previews.items() if key in self.comparison_slots}
        self._cancel_metadata()
        if self._comparison_worker is not None:
            self._comparison_worker.requestInterruption()
        self._update_slot_headers()
        self.comparison_content.show()
        self.comparison_empty.hide()
        self.comparison_summary.setText('Preparing metadata comparison…' if self.compared_paths else 'Assign a left image and a right image.')
        for worker in self.preview_workers:
            if worker.path not in self._wanted_previews():
                worker.requestInterruption()
        self._ensure_preview()
        self._comparison_ready()
        self._pump_metadata()

    def swap_comparison(self):
        if all(self.comparison_slots):
            left, right = self.comparison_slots
            self.comparison_slots[:] = [right, left]
            self.assign_comparison(0, right)

    def _update_slot_headers(self):
        for side, panel in enumerate((self.comparison_image_1_header, self.comparison_image_2_header)):
            path = self.comparison_slots[side]
            panel.selector.blockSignals(True)
            panel.selector.setCurrentIndex(max(0, panel.selector.findData(path)))
            panel.selector.blockSignals(False)
            panel.preview.path = path
            if path:
                self._update_comparison_header(panel, path)
            else:
                panel.filename.clear()
                panel.info.clear()
                panel.preview.set_image(QImage())
                panel.preview.setText('Drop a loaded image here')

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Open images", str(Path.home()), "Images and XMP sidecars (*)")
        if files:
            self.set_images([*self.paths, *files])

    def _selected_image_paths(self):
        rows = sorted(self.image_list.row(item) for item in self.image_list.selectedItems())
        return tuple(self.paths[row] for row in rows if 0 <= row < len(self.paths))

    def _update_compare_button(self):
        selected = self._selected_image_paths()
        enabled = len(selected) == 2
        self.compare_images_button.setEnabled(enabled)
        if enabled:
            self.compare_images_button.setToolTip("Compare the two selected images")
        else:
            self.compare_images_button.setToolTip("Select exactly two images to compare their metadata")

    def _selection_changed(self):
        self._update_compare_button()

    def _tab_changed(self, index):
        self.status_summary.setVisible(index != 2)
        if index != 0:
            self._metadata_prefetch_timer.stop()
            self._metadata_prefetch_ready = False
            if (
                self.worker is not None
                and getattr(self.worker, '_kim_prefetch', False)
            ):
                self._cancel_metadata()
        self._reload_overview_preferences()
        if index == 2 and self._single_splitter_sizes is None:
            self._single_splitter_sizes = self.splitter.sizes()
            self.selection_heading.hide()
            self.selection_count.hide()
            minimum = self.left_panel.minimumSizeHint().width()
            self.left_panel.setMaximumWidth(max(minimum, self.fontMetrics().horizontalAdvance('Thumbnail and image filename') + 40))
            self.splitter.setSizes([minimum, sum(self._single_splitter_sizes) - minimum])
        elif index != 2 and self._single_splitter_sizes is not None:
            self.left_panel.setMaximumWidth(16777215)
            self.selection_heading.show()
            self.selection_count.show()
            self.splitter.setSizes(self._single_splitter_sizes)
            self._single_splitter_sizes = None
        self._cancel_tag_filter()
        if index != 1:
            self._all_requested_path = None
            if self.worker is not None and self.worker.fields is None:
                self._cancel_metadata()
        for widget in (self.preview, self.filename, self.format_label, self.position_label,
                       self.previous_button, self.next_button):
            widget.setVisible(index != 2)
        self._ensure_preview()
        if index == 1:
            self._request_all_tags()
        elif index == 2:
            if self.compared_paths:
                self.pending_comparison_paths = self.compared_paths
                self._comparison_ready()
                self._pump_metadata()
            elif len(self._selected_image_paths()) == 2:
                self._begin_comparison(self._selected_image_paths())
            else:
                self.comparison_content.show()
                self.comparison_empty.hide()
                self.comparison_summary.setText('Assign a left image and a right image. You can also Ctrl+click two images and choose Compare images.')
        elif index == 3:
            self._all_requested_path = self._current_path()
            self.update_current()
        else:
            self.update_current()

    def _reload_overview_preferences(self):
        if self._closing:
            return
        previous = list(self.overview_preferences.fields)
        priority = self.metadata_preferences.priority
        self.metadata_preferences.settings.sync()
        self.metadata_preferences.reload()
        self.overview_preferences.reload()
        if previous != self.overview_preferences.fields:
            self.overview_configuration_changed()
        elif priority != self.metadata_preferences.priority:
            self._displayed_overview = None
            if self.tabs.currentIndex() == 2:
                self._populate_comparison()
            else:
                self.update_current()
        self._update_pin_button()
        self.table.viewport().update()
        self.grouped_tree.viewport().update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, 'overview_preferences'):
            QTimer.singleShot(0, self._reload_overview_preferences)

    def _navigate_image(self, offset):
        target_row = self.image_list.currentRow() + offset
        if not 0 <= target_row < self.image_list.count():
            return
        item = self.image_list.item(target_row)
        if len(self._selected_image_paths()) > 1:
            self.image_list.setCurrentItem(item, QItemSelectionModel.NoUpdate)
        else:
            self.image_list.setCurrentRow(target_row)

    def compare_images(self):
        selected = self._selected_image_paths()
        if len(selected) != 2:
            self.comparison_empty.setText(
                "Select two images in the list to compare their metadata. Use Ctrl+click to select the second image.")
            self.comparison_empty.show()
            self.comparison_content.hide()
            self.tabs.setCurrentIndex(2)
            return
        self._begin_comparison(selected)

    def _begin_comparison(self, selected):
        if len(selected) != 2:
            return
        self.comparison_slots[:] = list(selected)
        self.tabs.setCurrentIndex(2)
        self.assign_comparison(0, selected[0])

    def _compare_scope_changed(self, *_args):
        self._clear_metadata_errors(self.compared_paths or ())
        self._comparison_cancelled = False
        self.compare_retry.hide()
        self._cancel_metadata()
        self.pending_comparison_paths = self.compared_paths
        self._populate_comparison()
        self._pump_metadata()

    def cancel_comparison(self):
        self._comparison_cancelled = True
        self._cancel_metadata()
        if self._comparison_worker:
            self._comparison_worker.requestInterruption()
        self.comparison_summary.setText('Comparison loading canceled.')
        self.compare_progress.hide()
        self.compare_cancel.hide()
        self.compare_retry.show()

    def _comparison_ready(self):
        self._populate_comparison()

    def _comparison_record(self, path):
        if self.compare_scope.currentText() == 'All fields':
            return self._full_record(path)
        record = self._overview_record(path)
        return self.overview_preferences.select_record(record) if record is not None and not record.error else record

    def _comparison_key(self, records):
        return (self.compared_paths, self.compare_scope.currentText(), self.overview_preferences.selectors,
                tuple(field.key for field in self.overview_preferences.fields),
                tuple((_record_stamp(record.path, record.sidecars), id(record) if record.error else 0) for record in records),
                self.metadata_preferences.priority if self.compare_scope.currentText() != 'All fields' else ())

    def _populate_comparison(self, *_args):
        if not hasattr(self, 'comparison_model') or self.tabs.currentIndex() != 2 or self._closing or self._comparison_cancelled:
            return
        if not self.compared_paths:
            return
        self._update_slot_headers()
        self.comparison_content.show()
        self.comparison_empty.hide()
        self.pending_comparison_paths = self.compared_paths
        records = tuple(self._comparison_record(path) for path in self.compared_paths)
        self._comparison_gps_records = records
        if any(record is None for record in records):
            self.comparison_model.set_result(None)
            scope = 'full metadata' if self.compare_scope.currentText() == 'All fields' else 'overview fields'
            ready = sum(record is not None for record in records)
            names = ' and '.join(Path(path).name for path in self.compared_paths)
            self.comparison_summary.setText(f'Reading {scope}: {ready} of 2 images ready ({names})…')
            self.compare_progress.show()
            self.compare_cancel.show()
            self._pump_metadata()
            return
        key = self._comparison_key(records)
        result = self.comparison_data if self._comparison_data_key == key else self._comparison_cache.get(key)
        if result is not None:
            self.comparison_data = result
            self._comparison_data_key = key
            if key in self._comparison_cache:
                self._comparison_cache.move_to_end(key)
            self.comparison_model.set_result(result, self.compare_mode.currentText() == 'Differences only')
            counts = result.counts
            self.comparison_summary.setText(f"{counts.get('identical', 0)} matching · {len(result.differences)} differences · {self.comparison_model.rowCount()} fields shown" +
                (f' · {result.conflicts} IPTC/XMP source conflicts' if result.conflicts else '') +
                ''.join('\n' + record.error for record in records if record.error))
            self.compare_progress.hide()
            self.compare_cancel.hide()
            self.pending_comparison_paths = None
            return
        self.comparison_model.set_result(None)
        scope = 'full metadata' if self.compare_scope.currentText() == 'All fields' else 'overview fields'
        names = ' and '.join(Path(path).name for path in self.compared_paths)
        self.comparison_summary.setText(f'Comparing {scope} for {names}…')
        self.compare_progress.show()
        self.compare_cancel.show()
        if self._comparison_worker is not None:
            if self._comparison_worker.key != key:
                self._comparison_worker.requestInterruption()
            return
        worker = ComparisonWorker(*records, self.compare_scope.currentText() == 'All fields', key, self)
        worker.overview_fields = tuple(self.overview_preferences.fields)
        worker.priority = self.metadata_preferences.priority
        worker.locale = QLocale().name()
        self._comparison_worker = worker
        worker.completed.connect(lambda data, error: self._comparison_result(worker, data, error), Qt.QueuedConnection)
        worker.finished.connect(lambda: self._comparison_finished(worker), Qt.QueuedConnection)
        worker.start()

    def _comparison_result(self, worker, result, error):
        if self._closing or worker.isInterruptionRequested() or self._comparison_cancelled or not self.compared_paths:
            return
        records = tuple(self._comparison_record(path) for path in self.compared_paths)
        self._comparison_gps_records = records
        if any(record is None for record in records) or worker.key != self._comparison_key(records):
            return
        if error:
            self.comparison_summary.setText(error)
            self._comparison_cancelled = True
            self.compare_progress.hide()
            self.compare_cancel.hide()
            self.compare_retry.show()
            return
        self.comparison_data, self._comparison_data_key = result, worker.key
        if result.bytes <= self.comparison_cache_budget:
            self._comparison_cache[worker.key] = result
            while len(self._comparison_cache) > 4 or sum(value.bytes for value in self._comparison_cache.values()) > self.comparison_cache_budget:
                self._comparison_cache.popitem(last=False)
        self._populate_comparison()

    def _comparison_finished(self, worker):
        self._comparison_worker = None
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        elif not self._comparison_cancelled:
            self._populate_comparison()

    def show_comparison_details(self):
        row = self.comparison_tree.currentIndex().data(Qt.UserRole)
        if row:
            entries = [row.reference, row.comparison]
            if row.identity.startswith('Overview field '):
                selector = row.identity.removeprefix('Overview field ')
                field = next((field for field in self.overview_preferences.fields if field.selector == selector), None)
                if field:
                    for path in self.compared_paths:
                        record = self._comparison_record(path)
                        for entry in field.entries(record):
                            if not any(entry is existing for existing in entries):
                                entries.append(entry)
            self.show_metadata_details(entries, row.label)

    def _align_comparison_columns(self):
        if not hasattr(self, 'comparison_field_space'):
            return
        self.comparison_field_space.setFixedWidth(self.comparison_tree.columnWidth(0) + self.comparison_tree.frameWidth())
        self.comparison_image_1_header.setFixedWidth(self.comparison_tree.columnWidth(1))
        self.comparison_image_2_header.setFixedWidth(self.comparison_tree.columnWidth(2))

    @staticmethod
    def _source_conflict_count(reference, comparison):
        aliases = {
            "description": "description", "caption-abstract": "description",
            "imagedescription": "description", "title": "title", "objectname": "title",
            "subject": "keywords", "keywords": "keywords", "creator": "creator",
            "by-line": "creator", "rights": "rights", "copyright": "rights",
            "copyrightnotice": "rights",
        }
        conflicts = set()
        for record in (reference, comparison):
            values = {}
            for entry in record.entries:
                concept = aliases.get(entry.name.casefold())
                if not concept:
                    continue
                groups = {str(group).casefold() for group in entry.groups}
                family = ("IPTC-IIM" if any(group.startswith("iptc") for group in groups) else
                          "XMP" if any(group.startswith("xmp") for group in groups) else None)
                if family:
                    values.setdefault(concept, {}).setdefault(family, set()).add(json.dumps(
                        entry.value, ensure_ascii=False, sort_keys=True, default=str))
            for concept, families in values.items():
                if "IPTC-IIM" in families and "XMP" in families and families["IPTC-IIM"] != families["XMP"]:
                    conflicts.add(concept)
        return len(conflicts)

    def _update_comparison_header(self, panel, path, record=None):
        panel.filename.setText(Path(path).name)
        panel.filename.setToolTip(path)
        preview = self._preview_for(path) or self.thumbnails.get(path)
        panel.preview.set_image(preview[0] if preview else QImage())
        if preview is None:
            panel.preview.setText(self._preview_failure(path) or 'Loading preview…')
        record = record or self._overview_record(path)
        width = next((entry.value for entry in record.entries if entry.name == 'ImageWidth'), None) if record else None
        height = next((entry.value for entry in record.entries if entry.name == 'ImageHeight'), None) if record else None
        panel.info.setText(f'Source: {width} × {height} px' if width and height else 'Source dimensions pending')

    def set_images(self, paths):
        self._gif_preview_retries.clear()
        self._metadata_prefetch_timer.stop()
        self._metadata_prefetch_ready = False
        self._metadata_prefetch_attempted.clear()
        self._metadata_scan_completed.clear()
        self._metadata_scan_finished_announced = False
        current = self._current_path()
        self.paths = list(dict.fromkeys(_source_path(Path(path).expanduser()) for path in paths))
        self.image_list.blockSignals(True)
        self.image_list.clear()
        self._icon_paths.clear()
        self._path_rows = {path: row for row, path in enumerate(self.paths)}
        for path in self.paths:
            item = QListWidgetItem(Path(path).name)
            item.setSizeHint(QSize(0, max(self.image_list.iconSize().height() + 4, self.image_list.fontMetrics().height() + 6)))
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            self.image_list.addItem(item)
            cached = self.thumbnails.get(path) or self.previews.get(path)
            if cached is not None:
                item.setIcon(QIcon(QPixmap.fromImage(cached[0]).scaled(QSize(48, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
        self._thumbnail_cursor = 0
        self._thumbnail_seen = {path: stamp for path, stamp in self._thumbnail_seen.items() if path in self.paths}
        for worker in tuple(self.thumbnail_workers):
            if worker.path not in self.paths:
                worker.requestInterruption()
        self.selection_count.setText(f'{len(self.paths)} image' + ('s' if len(self.paths) != 1 else ''))
        if self.paths:
            self.image_list.setCurrentRow(self.paths.index(current) if current in self.paths else 0)
        self.image_list.blockSignals(False)
        for panel in (self.comparison_image_1_header, self.comparison_image_2_header):
            panel.selector.blockSignals(True)
            panel.selector.clear()
            panel.selector.addItem('Choose image…', None)
            for path in self.paths:
                panel.selector.addItem(Path(path).name, path)
                panel.selector.setItemData(panel.selector.count() - 1, path, Qt.ToolTipRole)
            panel.selector.blockSignals(False)
        self._update_slot_headers()
        self.update_current()
        self._update_compare_button()
        QTimer.singleShot(0, self._pump_thumbnails)

    def _comparison_gps_field(self, index):
        row = index.data(Qt.UserRole)
        if row is None or not self.compared_paths or index.column() not in (1, 2):
            return None
        entry = row.reference if index.column() == 1 else row.comparison
        path = self.compared_paths[index.column() - 1]
        records = getattr(self, '_comparison_gps_records', ())
        record = records[index.column() - 1] if len(records) == 2 else None
        if record is None or record.path != path:
            return None
        if entry is not None:
            return gps_field(record, entry) if is_gps_entry(entry) else None
        exemplar = row.comparison if index.column() == 1 else row.reference
        if not is_gps_entry(exemplar):
            return None
        other = records[2 - index.column()]
        origin = gps_field(other, exemplar)
        current = gps_field(record)
        if origin and origin.camera and current.camera and current.position is None:
            return current  # Missing camera GPS: Add opens this column's image.
        return GPSField(path, None, False, 'Not present · ' + exemplar.group,
                        'This representation is absent or incomplete. Inspect camera GPS in Overview; another location record will not be edited here.')

    def view_gps_on_map(self):
        """Open the existing read-only GPS report for the current image."""
        path = self._current_path()
        if not path:
            QMessageBox.information(
                self, "View on map", "Select an image first."
            )
            return

        try:
            from kim_location_dialog import LocationDialog
            dialog = LocationDialog("report", [path], "create", None)
            dialog.exec()
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(
                self, "View on map",
                "Could not open the GPS viewer: " + str(exc)
            )

    def _update_sources_targets(self):
        """Read-only summary using existing inspected metadata."""
        if self.tabs.currentIndex() != 3:
            return

        path = self._current_path()

        for widget in (
            self.sources_status,
            self.sources_priority,
            self.sources_common,
            self.sources_gps,
            self.sources_sidecars,
            self.sources_representations,
        ):
            widget.clear()

        if not path:
            self.sources_status.setText(
                'Select an image to inspect its metadata.'
            )
            return

        record = self._full_record(path)

        if record is None:
            self.sources_status.setText(
                'Loading metadata for ' + Path(path).name + '…'
            )
            return

        if record.error:
            self.sources_status.setText(
                'Metadata unavailable: ' + record.error
            )
            return

        from collections import Counter

        self.sources_status.setText(
            Path(path).name + '\n' +
            str(len(record.entries)) +
            ' metadata entries'
        )

        priority = self.metadata_preferences.priority

        self.sources_priority.setText(
            ' > '.join(str(item) for item in priority)
            if isinstance(priority, (tuple, list))
            else str(priority)
        )

        common_fields = (
            ('Title', ('Title', 'ObjectName')),
            ('Description', (
                'Description', 'Caption-Abstract',
                'ImageDescription',
            )),
            ('Keywords', ('Subject', 'Keywords')),
            ('Creator', ('Creator', 'Artist', 'By-line')),
            ('Copyright', (
                'Rights', 'Copyright', 'CopyrightNotice',
            )),
            ('Usage terms', ('UsageTerms',)),
        )

        descriptions = []

        for label, aliases in common_fields:
            entries = self._entries(record, aliases)

            chosen = (
                self._preferred(record, aliases)
                if entries else None
            )

            if chosen is None:
                descriptions.append(label + ': Not present')
                continue

            value = _overview_value(chosen.value)
            text = str(value)

            if len(text) > 180:
                text = text[:177] + '…'

            alternate_count = len(entries) - 1

            if alternate_count:
                text += (
                    ' (' + str(alternate_count) +
                    ' alternate representation' +
                    ('s' if alternate_count != 1 else '') +
                    ')'
                )

            descriptions.append(label + ': ' + text)

        self.sources_common.setText(
            '\n'.join(descriptions)
        )

        camera = self._camera_values(
            'Camera', ('Make', 'Model'), record
        )

        from kim_location_ui import position_text

        gps = gps_field(record)

        if gps is not None and gps.position is not None:
            location = position_text(gps.position)
            location_source = gps.provenance.replace(
                'Embedded image · ', ''
            ).replace('Embedded image', '').strip()
        else:
            location = 'No verified embedded camera GPS location'
            location_source = ''

        camera_text = (
            ' | '.join(camera)
            if camera
            else 'Not present'
        )

        gps_lines = [
            'Camera: ' + camera_text,
            'GPS location: ' + location,
        ]

        if location_source:
            gps_lines.append(
                'Representation: ' + location_source
            )

        gps_lines.append(
            'Additional camera and GPS metadata is available '
            'in Overview and All tags.'
        )

        self.sources_gps.setText(
            '\n'.join(gps_lines)
        )

        sidecars = record.sidecars or ()

        if sidecars:
            self.sources_sidecars.setText(
                '\n'.join(str(item) for item in sidecars)
                + '\nAssociated sidecars are not modified.'
            )
        else:
            self.sources_sidecars.setText(
                'No associated sidecars.'
            )

        by_source = {}

        for entry in record.entries:
            by_source.setdefault(
                str(entry.source), []
            ).append(entry)

        summaries = []

        for source in sorted(
            by_source, key=str.casefold
        ):
            entries = by_source[source]

            source_name = (
                'Image metadata'
                if source == record.path
                else 'Sidecar: ' + Path(source).name
            )

            summaries.append(
                source_name + ': ' +
                str(len(entries)) + ' tags'
            )

            groups = Counter(
                str(entry.group).split(':', 1)[0]
                for entry in entries
            )

            if groups:
                summaries.append(
                    'Groups: ' + ', '.join(
                        group + ' (' + str(count) + ')'
                        for group, count in sorted(
                            groups.items(),
                            key=lambda item: item[0].casefold(),
                        )
                    )
                )

            languages = Counter(
                str(entry.language)
                for entry in entries
                if entry.language
            )

            if languages:
                summaries.append(
                    'Languages: ' + ', '.join(
                        language + ' (' + str(count) + ')'
                        for language, count in sorted(
                            languages.items()
                        )
                    )
                )

            summaries.append('')

        self.sources_representations.setText(
            '\n'.join(summaries).strip()
            if summaries else
            'No metadata representations found.'
        )

    def _current_path(self):
        row = self.image_list.currentRow() if hasattr(self, 'image_list') else -1
        return self.paths[row] if 0 <= row < len(self.paths) else None

    def _full_record(self, path):
        record = self.records.get(path)
        if record is not None:
            return record
        if self._active_full and self._active_full[1].path == path:
            stamp, record = self._active_full
            if _record_stamp(path, record.sidecars) == stamp:
                return record
            self._active_full = None
        record = self._comparison_records.get(path)
        if record is not None and _record_stamp(path, record.sidecars) == self._comparison_stamps.get(path):
            return record
        return self._metadata_errors.get(('full', path))

    def _overview_record(self, path):
        record = self.overview_records.get(path)
        if record is not None:
            return record
        if self._active_overview and self._active_overview[1].path == path:
            stamp, record = self._active_overview
            if _record_stamp(path, record.sidecars) == stamp:
                return record
            self._active_overview = None
        record = self._comparison_overviews.get(path)
        if record is not None and _record_stamp(path, record.sidecars) == self._comparison_overview_stamps.get(path):
            return record
        full = self._full_record(path)
        if full is not None:
            if full.error:
                return full
            record = self.overview_preferences.select_record(full)
            if not record.error:
                # The full graph is a conservative bound when this scope was
                # configured after extraction. Never weigh large values here.
                weight = self.records._items[path][2] if isinstance(self.records, InspectionCache) and path in self.records._items else getattr(self.overview_records, 'budget', 0) + 1
                if isinstance(self.overview_records, InspectionCache):
                    self.overview_records.store(path, record, _record_stamp(path, record.sidecars), weight)
                else:
                    self.overview_records[path] = record
                if path == self._current_path():
                    self._active_overview = (_record_stamp(path, record.sidecars), record)
                if path in self.comparison_slots:
                    self._comparison_overviews[path] = record
                    self._comparison_overview_stamps[path] = _record_stamp(path, record.sidecars)
            return record
        return self._metadata_errors.get(('overview', path))

    def _preview_for(self, path):
        value = self.previews.get(path)
        if value is not None:
            return value
        if self._active_preview and self._active_preview[0] == path:
            _path, stamp, value = self._active_preview
            if stamp == _file_stamp(path):
                return value
            self._active_preview = None
        if path in self._comparison_previews:
            stamp, value = self._comparison_previews[path]
            if stamp == _file_stamp(path):
                return value
            del self._comparison_previews[path]
        return None

    def _wanted_previews(self):
        if self.tabs.currentIndex() == 2:
            return tuple(dict.fromkeys(path for path in self.comparison_slots if path))
        return (self._current_path(),) if self._current_path() else ()

    def _preview_failure(self, path):
        failure = self._preview_failures.get(path)
        if failure is not None and failure[0] == _file_stamp(path):
            return failure[1]
        self._preview_failures.pop(path, None)
        return None

    def _ensure_preview(self):
        if self._closing:
            return
        wanted = self._wanted_previews()
        self._preview_failures = {path: failure for path, failure in self._preview_failures.items() if path in wanted}
        for path in wanted:
            if self._preview_for(path) is not None or self._preview_failure(path):
                continue
            if any(worker.path == path and not worker.isInterruptionRequested() for worker in self.preview_workers):
                continue
            if len(self.preview_workers) >= 2:
                return
            generation = self.preview_generation
            worker = PreviewWorker(path, self)
            self.preview_workers.add(worker)
            worker.completed.connect(lambda p, value, stamp, token=generation: self._preview_ready(token, p, value, stamp), Qt.QueuedConnection)
            worker.finished.connect(lambda job=worker: self._preview_finished(job), Qt.QueuedConnection)
            worker.start()

    def _preview_ready(self, generation, path, value, stamp):
        if self._closing or path not in self._wanted_previews():
            return
        if stamp != _file_stamp(path):
            return
        if value[0].isNull():
            # A single transient GIF decoder error must not become a
            # permanent failure for the current image.
            retry_key = (path, stamp)
            if (
                Path(path).suffix.casefold() == '.gif'
                and value[1] == 'No thumbnail decoder for this image'
                and retry_key not in self._gif_preview_retries
            ):
                self._gif_preview_retries.add(retry_key)
                # _preview_finished will start the one permitted retry.
                return

            self._preview_failures[path] = (stamp, value[1])
            if self.thumbnails.get(path) is None:
                self._thumbnail_seen[path] = ('failed', stamp)
        else:
            self.previews.store(path, value, stamp, value[0].sizeInBytes())
            self._store_thumbnail(path, value[0], stamp)
            self._active_preview = (path, stamp, value)
            if path in self.comparison_slots:
                self._comparison_previews[path] = (stamp, value)
            self.image_list.item(self._path_rows[path]).setIcon(QIcon(QPixmap.fromImage(value[0]).scaled(
                QSize(48, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self._icon_paths.add(path)
            for old_path in tuple(self._icon_paths):
                if old_path != path and old_path not in self.previews and old_path not in self.thumbnails:
                    self.image_list.item(self._path_rows[old_path]).setIcon(QIcon())
                    self._icon_paths.remove(old_path)
        if self.tabs.currentIndex() == 2:
            self._update_slot_headers()
        else:
            self.update_current()
        self._pump_thumbnails()

    def _preview_finished(self, worker):
        self.preview_workers.discard(worker)
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        else:
            self._ensure_preview()
            self._pump_thumbnails()

    def _start_metadata_prefetch(self):
        """Begin low-priority metadata work after an idle interval."""
        if self._closing or self.tabs.currentIndex() != 0:
            return
        self._metadata_prefetch_ready = True
        self._pump_metadata()

    def _nearby_metadata_path(self):
        """Choose the next uninspected image, nearest first."""
        if self.tabs.currentIndex() != 0 or not self.paths:
            return None

        row = self.image_list.currentRow()
        if not 0 <= row < len(self.paths):
            return None

        for distance in range(1, len(self.paths)):
            for index in (row + distance, row - distance):
                if not 0 <= index < len(self.paths):
                    continue

                path = self.paths[index]

                if path in self._metadata_scan_completed:
                    continue

                if path in self._metadata_prefetch_attempted:
                    continue

                record = self._overview_record(path)

                if record is not None:
                    self._metadata_scan_completed.add(path)
                    continue

                return path

        return None

    def _activity_neighbors(self):
        row = self.image_list.currentRow()
        if row < 0 or row >= len(self.paths):
            return ()
        return tuple(
            self.paths[index]
            for offset in (1, 2, -1)
            for index in (row + offset,)
            if 0 <= index < len(self.paths)
        )

    def _metadata_item_tooltip(self, path):
        worker = self.worker
        if (
            worker is not None
            and path in worker.paths
            and not worker.isInterruptionRequested()
        ):
            status = "Reading metadata"
        else:
            record = self._overview_record(path)
            if record is None:
                status = (
                    "Previously inspected; not cached"
                    if path in self._metadata_scan_completed
                    else "Metadata not loaded"
                )
            elif record.error:
                status = "Metadata unavailable"
            else:
                status = "Metadata cached"
        return f"{path}\n{status}"

    def _metadata_item_hovered(self, item):
        path = item.data(Qt.UserRole)
        if path in self._path_rows:
            item.setToolTip(self._metadata_item_tooltip(path))

    def _hide_metadata_activity(self):
        self.metadata_activity.hide()
        self.metadata_progress.hide()

    def _update_metadata_activity(self):
        """Display actual progress for the complete image list."""
        if self._closing:
            return

        worker = self.worker
        active = (
            worker is not None
            and not worker.isInterruptionRequested()
        )

        neighbors = self._activity_neighbors()
        paths = (
            self._current_path(),
            *neighbors,
            *(worker.paths if worker else ()),
        )

        for path in dict.fromkeys(paths):
            row = self._path_rows.get(path) if path else None
            if row is None:
                continue
            item = self.image_list.item(row)
            if item is not None:
                item.setToolTip(
                    self._metadata_item_tooltip(path)
                )

        if self.tabs.currentIndex() != 0:
            self._activity_hide_timer.stop()
            self._hide_metadata_activity()
            return

        total = len(self.paths)
        completed = len(
            self._metadata_scan_completed.intersection(
                self.paths
            )
        )

        running = active
        waiting = (
            self._metadata_prefetch_timer.isActive()
        )

        finished = (
            total > 0
            and completed >= total
            and self._metadata_prefetch_ready
            and not running
        )

        if finished:
            if (
                self._metadata_scan_finished_announced
                and not self.metadata_activity.isVisible()
            ):
                return

            message = (
                f"Metadata inspected: {completed} of {total}"
            )

        elif running or waiting or (
            self._metadata_prefetch_ready
            and completed < total
        ):
            message = (
                f"Inspecting metadata: {completed} of {total}"
            )

        else:
            self._activity_hide_timer.stop()
            self._hide_metadata_activity()
            return

        self.metadata_activity.setText(message)

        if running and worker.paths:
            kind = (
                "Background"
                if getattr(worker, "_kim_prefetch", False)
                else "Selected image"
            )
            self.metadata_activity.setToolTip(
                f"{kind}: {Path(worker.paths[0]).name}"
            )
        else:
            self.metadata_activity.setToolTip("")

        self.metadata_activity.show()

        self.metadata_progress.setRange(
            0, max(1, total)
        )
        self.metadata_progress.setValue(completed)
        self.metadata_progress.show()

        if finished:
            if not self._metadata_scan_finished_announced:
                self._metadata_scan_finished_announced = True
                self._activity_hide_timer.start(2500)
        else:
            self._activity_hide_timer.stop()

    def _desired_metadata(self):
        path = self._current_path()
        if self._closing or not path:
            return None
        if self.tabs.currentIndex() == 2:
            if self._comparison_cancelled:
                return None
            for candidate in self.pending_comparison_paths or ():
                if self._comparison_record(candidate) is None:
                    return ('full' if self.compare_scope.currentText() == 'All fields' else 'overview', candidate)
            return None
        if self.tabs.currentIndex() in (1, 3) and self._all_requested_path == path and self._full_record(path) is None:
            return ('full', path)
        selected_record = self._overview_record(path)

        if selected_record is None:
            if path in self._metadata_scan_completed:
                self._metadata_scan_completed.discard(path)
                self._metadata_scan_finished_announced = False
            self._metadata_prefetch_attempted.discard(path)
            return ('overview', path)

        self._metadata_scan_completed.add(path)

        if (
            self.tabs.currentIndex() == 0
            and self._metadata_prefetch_ready
        ):
            candidate = self._nearby_metadata_path()
            if candidate is not None:
                return ('prefetch', candidate)

        return None

    def _pump_metadata(self):
        if self.worker is not None or self._closing:
            if not self._closing:
                self._update_metadata_activity()
            return
        desired = self._desired_metadata()
        if desired is None:
            if (
                self.tabs.currentIndex() == 0
                and not self._metadata_prefetch_ready
                and not self._metadata_prefetch_timer.isActive()
                and len(self._metadata_scan_completed) < len(self.paths)
            ):
                current = self._current_path()
                selected = (
                    self._overview_record(current)
                    if current else None
                )
                if selected is not None and not selected.error:
                    self._metadata_prefetch_timer.start()

            self._comparison_ready()
            self._update_metadata_activity()
            return

        mode, path = desired
        fields = self.overview_preferences.selectors if mode in ('overview', 'prefetch') else None
        self.worker_generation += 1
        generation = self.worker_generation
        worker = MetadataWorker([path], self, fields=fields)
        worker._kim_prefetch = mode == 'prefetch'
        if worker._kim_prefetch:
            self._metadata_prefetch_attempted.add(path)

        if fields is None:
            worker.derived_fields = self.overview_preferences.selectors
        self.worker = worker
        worker.completed.connect(lambda records, previews, error: self.receive_results(
            records, previews, error, generation, fields=fields,
            stamps=worker.stamps, weights=worker.weights,
            derived=worker.derived_records if worker.derived_fields == self.overview_preferences.selectors else {},
            derived_weights=worker.derived_weights), Qt.QueuedConnection)
        worker.finished.connect(lambda: self.worker_finished(worker, generation), Qt.QueuedConnection)
        if worker._kim_prefetch:
            worker.start(QThread.LowPriority)
        else:
            worker.start()
        self._update_metadata_activity()

    def _cancel_metadata(self):
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker_generation += 1

    def receive_results(self, records, previews, _error, generation=None, *, fields=None, stamps=None, weights=None,
                        derived=None, derived_weights=None):
        if self._closing or (generation is not None and generation != self.worker_generation):
            return
        mode = 'full' if fields is None else 'overview'
        cache = self.records if fields is None else self.overview_records
        for path, record in records.items():
            stamp = (stamps or {}).get(path, _record_stamp(path, record.sidecars))
            if stamps is not None and not record.error and stamp != _record_stamp(path, record.sidecars):
                continue
            if path in self._path_rows:
                self._metadata_scan_completed.add(path)
            if record.error:
                self._metadata_errors[(mode, path)] = record
            else:
                self._metadata_errors.pop((mode, path), None)
                if isinstance(cache, InspectionCache):
                    weight = weights[path] if weights is not None else _record_bytes(record)
                    cache.store(path, record, stamp, weight)
                else:
                    cache[path] = record
                if fields is not None and path == self._current_path():
                    self._active_overview = (stamp, record)
                if fields is not None and path in self.comparison_slots:
                    self._comparison_overviews[path] = record
                    self._comparison_overview_stamps[path] = stamp
                if derived and path in derived:
                    subset = derived[path]
                    self.overview_records.store(path, subset, stamp, derived_weights[path])
                    if path == self._current_path():
                        self._active_overview = (stamp, subset)
                    if path in self.comparison_slots:
                        self._comparison_overviews[path] = subset
                        self._comparison_overview_stamps[path] = stamp
            if fields is None:
                if path == self._current_path() and self._all_requested_path == path:
                    self._active_full = (stamp, record)
                if self.pending_comparison_paths and path in self.pending_comparison_paths:
                    self._comparison_records[path] = record
                    self._comparison_stamps[path] = stamp
        self.update_current()
        self._update_metadata_activity()
        self._comparison_ready()

    def worker_finished(self, worker=None, generation=None):
        worker = worker or self.worker
        if worker is not self.worker:
            return

        if getattr(worker, "_kim_prefetch", False):
            for path in worker.paths:
                if path not in self._metadata_scan_completed:
                    self._metadata_prefetch_attempted.discard(path)

        self.worker = None
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        else:
            self._pump_metadata()

    def _request_all_tags(self):
        self._all_requested_path = self._current_path()
        self._clear_metadata_errors((self._all_requested_path,))
        if self.worker is not None and (self.worker.fields is not None or self.worker.paths != [self._all_requested_path]):
            self._cancel_metadata()
        self._update_all_tags()
        self._pump_metadata()

    def cancel_all_tags(self):
        self._all_requested_path = None
        if self.worker is not None and self.worker.fields is None:
            self._cancel_metadata()
        self.all_tags_status.setText('Complete metadata loading canceled.')
        self.all_tags_progress.hide()
        self.all_tags_cancel.hide()
        self.all_tags_retry.show()

    def _update_all_tags(self):
        if self.tabs.currentIndex() != 1:
            return
        path = self._current_path()
        record = self._full_record(path)
        if record is not None:
            if self._preview_for(path) is None and not self._preview_error:
                self.all_tags_status.setText('Loading preview…')
                self.all_tags_progress.hide()
                self.all_tags_cancel.hide()
                return
            self.all_tags_progress.hide()
            self.all_tags_cancel.hide()
            self.all_tags_retry.setVisible(bool(record.error))
            self.all_tags_status.setText(record.error or f'{len(record.entries)} metadata entries')
            if record is not self._tag_record:
                self._tag_record = record
                self._tag_rows = None
                self._populate_tags(record)
            return
        if self._tag_record is not None:
            self._tag_record = None
            self.model.set_record(None)
            self.grouped_model.set_record(None)
        if self._all_requested_path == path:
            self.all_tags_status.setText('Loading all metadata…')
            self.all_tags_progress.show()
            self.all_tags_cancel.show()
            self.all_tags_retry.hide()

    def select_image(self, _row):
        self.update_current()

    def update_current(self):
        path = self._current_path()
        if path is None or self._closing:
            return
        row = self.image_list.currentRow()
        stamp = _file_stamp(path)
        if path != self._selection_path or stamp != self._selection_stamp:
            self._metadata_prefetch_timer.stop()
            self._metadata_prefetch_ready = False
            self._selection_path = path
            self._selection_stamp = stamp
            self.preview_generation += 1
            self._preview_error = None
            self._active_preview = None
            self._gif_preview_retries.clear()
            self._active_overview = None
            if self.tabs.currentIndex() != 2:
                for worker in self.preview_workers:
                    worker.requestInterruption()
                self._cancel_metadata()
            self._metadata_errors.clear()
            self._active_full = None
            self._tag_record = None
            self._tag_rows = None
            self.model.set_record(None)
            self.grouped_model.set_record(None)
            self._cancel_tag_filter()
            self._all_requested_path = path if self.tabs.currentIndex() in (1, 3) else None
        self.filename.set_full_text(Path(path).name)
        self.filename.setToolTip(path)
        self.directory_label.set_full_text(str(Path(path).parent))
        self.previous_button.setEnabled(row > 0)
        self.next_button.setEnabled(row + 1 < len(self.paths))
        self.position_label.setText(f'{row + 1} of {len(self.paths)}')
        preview = self._preview_for(path)
        failure = self._preview_failure(path)
        self._preview_error = (path, failure) if failure else None
        if preview is not None:
            self.preview.set_image(preview[0])
            self.preview.setToolTip('')
        elif self._preview_error:
            thumbnail = self.thumbnails.get(path)
            if thumbnail is not None:
                self.preview.set_image(thumbnail[0])
                self.preview.setToolTip(
                    'Full preview unavailable: '
                    + self._preview_error[1]
                )
            else:
                self.preview.set_image(QImage())
                self.preview.setText(self._preview_error[1])
                self.preview.setToolTip('')
        else:
            self.preview.set_image(QImage())
            self.preview.setText('Loading preview…')
            self.preview.setToolTip('')
            thumbnail = self.thumbnails.get(path)
            if thumbnail is not None:
                self.preview.set_image(thumbnail[0])
        record = self._overview_record(path) if preview is not None or self._preview_error else None
        fmt = next(
            (
                entry.value
                for entry in (record.entries if record else [])
                if entry.name.casefold() == 'filetype'
            ),
            None,
        )
        if not fmt:
            # Filename hint only, never treated as verified metadata.
            extension = Path(path).suffix.lstrip('.').upper()
            extension = {
                'JPG': 'JPEG',
                'TIF': 'TIFF',
            }.get(extension, extension)
            fmt = (
                f'{extension} (unverified)'
                if extension else 'Reading format…'
            )
        self.format_label.setText(str(fmt))
        messages = ([record.error] if record and record.error else []) + (record.warnings if record else [])
        self.notice.setText('\n'.join(messages))
        self.notice.setVisible(bool(messages))
        if record is not None:
            self._update_status_summary(record)
        else:
            self.status_summary.setText('Loading metadata…')
        if getattr(self, '_displayed_overview', None) != (path, id(record)):
            if record is None:
                self._displayed_overview = (path, id(None))
                self._pending_overview = None
                self.update_overview(None)
            elif self.tabs.currentIndex() == 0:
                self.overview_scroll.hide()
                self.overview_loading.setText('Loading metadata…')
                self.overview_loading.show()
                self.overview_retry.hide()
                self._pending_overview = (path, record, _record_stamp(path, record.sidecars),
                                          self.overview_preferences.selectors)
                self.preview.update()
        self._update_all_tags()
        if self.tabs.currentIndex() == 3:
            self._update_sources_targets()
        self._ensure_preview()
        self._pump_metadata()

    def _preview_painted(self):
        pending = self._pending_overview
        if pending is not None:
            self._pending_overview = None
            QTimer.singleShot(0, lambda: self._show_pending_overview(pending))

    def _show_pending_overview(self, pending):
        path, record, stamp, selectors = pending
        if self._closing or self.tabs.currentIndex() != 0 or path != self._current_path():
            return
        if selectors != self.overview_preferences.selectors:
            return
        if stamp != _record_stamp(path, record.sidecars):
            self.update_current()
            return
        self._displayed_overview = (path, id(record))
        self.update_overview(record)


    @staticmethod
    def _metadata_family(entry):
        groups = [str(value).strip() for value in (entry.groups or ())]
        group0 = groups[0].casefold() if groups else ""
        group1 = groups[1].casefold() if len(groups) > 1 else ""
        if group0 == "exiftool":
            return "ExifTool diagnostics"
        if group0 == "file":
            return "File information"
        if group0 == "iptc":
            return "IPTC-IIM"
        if group0 == "xmp":
            return "XMP"
        if group0 == "makernotes" or group1 == "makernotes" or group1 in MAKERNOTE_GROUPS:
            return "MakerNotes"
        if group0 in MAKERNOTE_GROUPS:
            return "MakerNotes"
        if group0 == "exif":
            return "EXIF"
        return "Other"

    @staticmethod
    def _grouped_field_name(entry):
        name = entry.name
        if not entry.language:
            return name
        language = entry.language
        if language.casefold() == "x-default":
            label = "default"
        else:
            language_names = {
                "de": "German", "en": "English", "es": "Spanish",
                "fr": "French", "it": "Italian", "ja": "Japanese",
                "ko": "Korean", "pt": "Portuguese", "ru": "Russian",
                "zh": "Chinese",
            }
            primary_language = language.split("-", 1)[0].casefold()
            label = language_names.get(primary_language, language)
            if "-" in language and primary_language in language_names:
                label += f" ({language.split('-', 1)[1]})"
        return f"{name} ({label})"

    def _populate_grouped_tree(self, record):
        self.grouped_model.set_record(record, self._tag_rows)
        for row, (family, _indices) in enumerate(self.grouped_model.families):
            self.grouped_tree.setExpanded(self.grouped_model.index(row, 0), self.group_expanded.get(family, True))

    def _group_expanded(self, index):
        family = index.data(Qt.UserRole + 1)
        if family in self.group_expanded:
            self.group_expanded[family] = True
            self.settings.setValue(f'tags/expanded/{family}', True)

    def _group_collapsed(self, index):
        family = index.data(Qt.UserRole + 1)
        if family in self.group_expanded:
            self.group_expanded[family] = False
            self.settings.setValue(f'tags/expanded/{family}', False)

    def _tag_scroll_changed(self, value):
        scroll = self.grouped_tree.verticalScrollBar()
        if value >= scroll.maximum() > 0 and not self._tag_fetch_pending:
            self._tag_fetch_pending = True
            QTimer.singleShot(0, self._fetch_tag_rows)

    def _fetch_tag_rows(self):
        self._tag_fetch_pending = False
        if self._closing or self.tabs.currentIndex() != 1 or self.tag_view_mode.currentText() != 'Grouped':
            return
        scroll = self.grouped_tree.verticalScrollBar()
        if scroll.value() < scroll.maximum():
            return
        # Keep expanded non-root groups growing in bounded batches as the
        # user scrolls; expansion alone does not fetch every subsequent batch.
        for row in range(self.grouped_model.rowCount()):
            parent = self.grouped_model.index(row, 0)
            if self.grouped_tree.isExpanded(parent) and self.grouped_model.canFetchMore(parent):
                self.grouped_model.fetchMore(parent)

    def _cancel_tag_filter(self):
        self._tag_filter_pending = False
        if self._tag_filter_worker:
            self._tag_filter_worker.requestInterruption()

    def _filter_tags(self, _text):
        self._tag_filter_pending = True
        if self._tag_filter_worker is not None:
            self._tag_filter_worker.requestInterruption()
        else:
            self._start_tag_filter()

    def _sort_tags(self, column):
        self._tag_sort_descending = not self._tag_sort_descending if column == self._tag_sort_column else False
        self._tag_sort_column = column
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(column, Qt.DescendingOrder if self._tag_sort_descending else Qt.AscendingOrder)
        self._filter_tags(self.search.text())

    def _start_tag_filter(self):
        if self._closing or self._tag_record is None or self.tabs.currentIndex() != 1:
            return
        self._tag_filter_pending = False
        worker = TagFilterWorker(self._tag_record, self.search.text(), self._tag_sort_column,
                                 self._tag_sort_descending, self)
        self._tag_filter_worker = worker
        worker.completed.connect(lambda record, rows: self._tag_filter_ready(worker, record, rows), Qt.QueuedConnection)
        worker.finished.connect(lambda: self._tag_filter_finished(worker), Qt.QueuedConnection)
        worker.start()

    def _tag_filter_ready(self, worker, record, rows):
        if (not self._closing and not worker.isInterruptionRequested() and
                self._tag_record is record and self.tabs.currentIndex() == 1):
            self._tag_rows = rows
            self._render_tag_model()
            self.all_tags_status.setText(f'{len(rows)} of {len(record.entries)} metadata entries')

    def _tag_filter_finished(self, worker):
        self._tag_filter_worker = None
        worker.deleteLater()
        if self._closing:
            self._finish_close()
        elif self._tag_filter_pending:
            self._start_tag_filter()

    def _render_tag_model(self):
        self._show_entry(None)
        if self.tag_view_mode.currentText() == 'Grouped':
            self.model.set_record(None)
            self._populate_grouped_tree(self._tag_record)
        else:
            self.grouped_model.set_record(None)
            self.model.set_record(self._tag_record, self._tag_rows)

    def _set_tag_view_mode(self, _mode):
        self.tags_stack.setCurrentIndex(0 if self.tag_view_mode.currentText() == 'Grouped' else 1)
        self._render_tag_model()


    def _conflicting_field_count(self, record):
        if not record:
            return 0
        fields = DESCRIPTION_FIELDS + RIGHTS_FIELDS
        count = 0
        for label, aliases in fields:
            entries = self._entries(record, aliases)
            groups = self._overview_groups(entries, record, title=label in {"Title", "Caption / Description"})
            by_language = {}
            for language, shown, _sources in groups:
                by_language.setdefault(language, set()).add(shown)
            count += int(any(len(values) > 1 for values in by_language.values()))
        return count

    def _update_status_summary(self, record):
        if not record:
            self.status_summary.setText("Metadata is not available")
            return
        parts = [f"{len(record.entries)} loaded Overview entries"]
        conflicts = self._conflicting_field_count(record)
        if conflicts:
            parts.append(f"{conflicts} conflict" + ("s" if conflicts != 1 else "") + " in Overview")
        if record.sidecars:
            parts.append("XMP sidecar present")
        if record.error:
            parts.append("Metadata read error")
        if record.warnings:
            parts.append(f"{len(record.warnings)} warnings")
        self.status_summary.setText(" · ".join(parts))

    def _populate_tags(self, record):
        self._tag_record = record
        self._render_tag_model()
        if self.search.text() or self._tag_sort_column is not None:
            self._filter_tags(self.search.text())


    def _overview_groups(self, entries, record, title=False):
        has_default = title and any(entry.language == "x-default" for entry in entries)
        grouped = {}
        for entry in entries:
            language = entry.language or ""
            if title and has_default and not language:
                language = "x-default"
            shown = _overview_value(entry.value)
            key = (language, shown)
            sources = grouped.setdefault(key, set())
            sources.update(source for source in _entry_sources(entry, record) if source != "Metadata")
        return [(language, shown, sources) for (language, shown), sources in grouped.items()]





    def _add_conflict_indicator(self):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(16, 16))
        icon.setToolTip("Different values are present in multiple metadata representations")
        row_layout.addWidget(icon)
        row_layout.addWidget(self._subdued_label("Conflicting values"))
        row_layout.addStretch(1)
        self.section_layout.addWidget(row)




    def _add_rights_field(self, label, entries, record):
        self._add_description_field(label, entries, record)


    def _add_camera_section(self, record):
        available = [(label, self._camera_values(label, aliases, record))
                     for label, aliases in CAMERA_FIELDS]
        show_all = self.show_empty.isChecked()
        visible = [(label, values) for label, values in available if values or show_all]
        if not visible:
            self.section_layout.addWidget(self._subdued_label("No camera or capture details are present."))
            return
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(14)
        for index, (label, values) in enumerate(visible):
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(2)
            item_layout.addWidget(self._subdued_label(label))
            if values:
                for value in values:
                    item_layout.addWidget(self._content_label(value))
            else:
                item_layout.addWidget(self._subdued_label("Not present"))
            grid.addWidget(item, index // 3, index % 3, Qt.AlignTop)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        self.section_layout.addWidget(grid_host)


    def update_overview(self, record=CURRENT_RECORD):
        if record is CURRENT_RECORD:
            row = self.image_list.currentRow()
            record = (self._overview_record(self.paths[row]) if 0 <= row < len(self.paths) and
                      (self._preview_for(self.paths[row]) is not None or self._preview_error) else None)
        self.render_overview(record)

    def configure_overview_fields(self):
        dialog = OverviewFieldsDialog(self.overview_preferences, self)
        if dialog.exec() == QDialog.Accepted:
            self.overview_configuration_changed()

    def _clear_metadata_errors(self, paths):
        for path in paths:
            removed = False
            for mode in ('overview', 'full'):
                removed = self._metadata_errors.pop((mode, path), None) is not None or removed
            for mapping, stamps in ((self._comparison_records, self._comparison_stamps),
                                    (self._comparison_overviews, self._comparison_overview_stamps)):
                record = mapping.get(path)
                if record is not None and record.error:
                    mapping.pop(path, None)
                    stamps.pop(path, None)
                    removed = True
            for attribute in ('_active_overview', '_active_full'):
                active = getattr(self, attribute)
                if active and active[1].path == path and active[1].error:
                    setattr(self, attribute, None)
                    removed = True
            if removed:
                self._comparison_data_key = None
                self.comparison_data = None
                self._comparison_cache.clear()

    def retry_overview(self):
        self._clear_metadata_errors((self._current_path(),))
        self._displayed_overview = None
        self._cancel_metadata()
        self.update_current()

    def show_metadata_details(self, entries, field_name=None):
        MetadataDetailsDialog(entries, self, field_name).exec()

    def overview_configuration_changed(self):
        self._metadata_prefetch_timer.stop()
        self._metadata_prefetch_ready = False
        self._metadata_prefetch_attempted.clear()
        self._metadata_scan_completed.clear()
        self._metadata_scan_finished_announced = False
        for path in self.paths:
            self._metadata_errors.pop(('overview', path), None)
        self.overview_records.clear()
        self._active_overview = None
        self._comparison_overviews.clear()
        self._comparison_overview_stamps.clear()
        self._comparison_cache.clear()
        self._comparison_data_key = None
        self._displayed_overview = None
        if self.worker is not None and self.worker.fields is not None:
            self._cancel_metadata()
        self.update_current()

    def toggle_overview_entry(self, entry=None):
        entry = entry if isinstance(entry, MetadataEntry) else self.selected_entry
        if entry is None or self._tag_record is None:
            return
        try:
            self.overview_preferences.toggle_entry(entry, self._tag_record)
            self.overview_configuration_changed()
            self._update_pin_button()
            self.table.viewport().update()
            self.grouped_tree.viewport().update()
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot change overview fields', str(exc))

    def _update_pin_button(self):
        entry = self.selected_entry
        self.pin_button.setEnabled(entry is not None)
        pinned = entry is not None and self.overview_preferences.is_pinned(entry, self._tag_record)
        self.pin_button.setText('Remove from overview' if pinned else 'Show in overview')

    def show_entry_value(self, current, _previous):
        self._show_entry(current.data(Qt.UserRole) if current.isValid() else None)

    def show_grouped_entry(self, current, _previous):
        self._show_entry(current.data(Qt.UserRole) if current.isValid() else None)

    def _show_entry(self, entry):
        had_entry = isinstance(self.selected_entry, MetadataEntry)
        if not isinstance(entry, MetadataEntry):
            self.selected_entry = None
            self._update_pin_button()
            self.entry_identity.clear()
            self.value_detail.clear()
            self.entry_identity.hide()
            self.value_detail.hide()
            self.details_placeholder.show()
            self.tag_details.setMinimumHeight(22)
            self.copy_button.setEnabled(False)
            details_size = 28
            self.tags_splitter.setSizes([max(1, self.tags_splitter.height() - details_size), details_size])
            return
        self.selected_entry = entry
        self._update_pin_button()
        family = self._metadata_family(entry)
        namespace = next((group for group in entry.groups or ()
                          if str(group).casefold().startswith("xmp-")), None)
        details = [f"Family: {family}", f"ExifTool group: {entry.group}"]
        if namespace:
            details[0] += f" · Namespace: {namespace}"
        if entry.tag_id is not None:
            details.append(f"Tag ID: {entry.tag_id}")
        if entry.language:
            details.append(f"Language: {entry.language}")
        details.append(f"Qualified tag: {entry.qualified_name}")
        details.append(f"Source: {entry.source}")
        identity_lines = [details[0]]
        technical = " · ".join(details[1:-2])
        if technical:
            identity_lines.append(technical)
        identity_lines.extend(details[-2:])
        self.entry_identity.setText("\n".join(identity_lines))
        self.entry_identity.show()
        self.value_detail.show()
        self.details_placeholder.hide()
        self.tag_details.setMinimumHeight(124)
        self.value_detail.setPlainText(_entry_display(entry))
        self.copy_button.setEnabled(True)
        if not had_entry:
            details_size = min(190, max(145, int(self.tags_splitter.height() * 0.28)))
            self.tags_splitter.setSizes([max(1, self.tags_splitter.height() - details_size), details_size])

    def copy_value(self):
        if isinstance(self.selected_entry, MetadataEntry):
            QApplication.clipboard().setText(raw_metadata_value(self.selected_entry.value))

    def _finish_close(self):
        if getattr(self, '_gps_dialog', None) is None and self.worker is None and not self.preview_workers and self._tag_filter_worker is None and self._comparison_worker is None and not self.thumbnail_workers:
            self.close()

    def closeEvent(self, event):
        self._closing = True
        if getattr(self, '_gps_dialog', None) is not None:
            self._gps_dialog.reject()
        self._activity_hide_timer.stop()
        self._metadata_prefetch_timer.stop()
        for worker in tuple(self.thumbnail_workers):
            worker.requestInterruption()
        self._cancel_tag_filter()
        if self._comparison_worker is not None:
            self._comparison_worker.requestInterruption()
        for worker in self.preview_workers:
            worker.requestInterruption()
        if self.worker is not None:
            self.worker.requestInterruption()
        if getattr(self, '_gps_dialog', None) is not None or self.worker is not None or self.preview_workers or self._tag_filter_worker is not None or self._comparison_worker is not None or self.thumbnail_workers:
            self.close_after_worker = True
            event.ignore()
            return
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.sizes())
        for section, expanded in self.section_expanded.items():
            self.settings.setValue(f'overview/expanded/{section}', expanded)
        super().closeEvent(event)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    shutdown_requested = False

    def request_shutdown(_signum, _frame):
        nonlocal shutdown_requested
        shutdown_requested = True

    # Keep SIGINT out of Qt virtual methods: Python's default handler raises
    # KeyboardInterrupt at whichever Python callback is active when Ctrl+C
    # arrives, including closeEvent. The Qt timer performs shutdown on the UI
    # thread and allows the worker's normal cancellation path to finish.
    signal.signal(signal.SIGINT, request_shutdown)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("KIMng Metadata Browser")
    app.setOrganizationName("KIMng")
    window = MetadataBrowser(argv)
    window.show()
    shutdown_timer = QTimer()
    shutdown_timer.setInterval(100)

    def process_shutdown_request():
        if shutdown_requested:
            shutdown_timer.stop()
            window.close()

    shutdown_timer.timeout.connect(process_shutdown_request)
    shutdown_timer.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
