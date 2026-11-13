#!/usr/bin/env python3
"""Standalone, read-only KIM6 Metadata Browser."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import re
import signal
import sys

try:
    from PySide6.QtCore import QSettings, Qt, QThread, Signal, QSortFilterProxyModel, QSize, QModelIndex, QTimer
    from PySide6.QtGui import QIcon, QImage, QPalette, QStandardItem, QStandardItemModel, QPixmap
    from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QHBoxLayout,
        QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QScrollArea,
        QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QTableView, QVBoxLayout,
        QWidget, QHeaderView, QAbstractItemView, QFrame, QGridLayout, QTreeWidget,
        QTreeWidgetItem, QStackedWidget, QComboBox, QToolButton, QStyle)
except ModuleNotFoundError as exc:
    if exc.name and exc.name.startswith("PySide6"):
        print("KIM6 Metadata Browser requires PySide6. Install the KIM6 Qt runtime and try again.", file=sys.stderr)
        raise SystemExit(2) from exc
    raise

from kim_metadata_reader import MetadataEntry, MetadataRecord, read_metadata, value_text
from kim_photo_selection import read_thumbnail
from kim_process import inspection_context


DISPLAY_LIMIT = 240


class PreviewLabel(QLabel):
    """Keep the bounded decoded preview crisp and fitted after window resizing."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(220, 150)
        self.setWordWrap(True)

    def set_image(self, image):
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


def _text(value):
    return value_text(value)


def _compact(value):
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    else:
        text = _text(value).replace("\r\n", "\n")
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


class MetadataFilterProxy(QSortFilterProxyModel):
    """Filter against complete values, even when the table cell is shortened."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.needle = ""

    def set_needle(self, value):
        self.needle = value.casefold().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.needle:
            return True
        model = self.sourceModel()
        return any(self.needle in str(model.index(source_row, column, source_parent).data(Qt.UserRole + 2)
                                       or model.index(source_row, column, source_parent).data(Qt.UserRole + 1)
                                       or "").casefold()
                   for column in range(model.columnCount()))


class MetadataWorker(QThread):
    completed = Signal(object, object, object)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = list(paths)

    def run(self):
        try:
            with inspection_context(cancelled=self.isInterruptionRequested):
                records = read_metadata(self.paths)
        except Exception as exc:
            records = {str(Path(path).resolve(strict=False)): MetadataRecord(
                path=str(Path(path).resolve(strict=False)), error=str(exc)) for path in self.paths}
        previews = {}
        for path in self.paths:
            if self.isInterruptionRequested():
                break
            key = str(Path(path).resolve(strict=False))
            try:
                image, _stamp = read_thumbnail(path, QSize(640, 480))
                previews[key] = (image, "")
            except Exception as exc:
                previews[key] = (QImage(), str(exc))
        self.completed.emit(records, previews, None)


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
]
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


class MetadataBrowser(QMainWindow):
    def __init__(self, paths):
        super().__init__()
        initial_paths = [str(Path(path).expanduser().resolve(strict=False)) for path in paths]
        self.paths = []
        self.records = {}
        self.previews = {}
        self.worker = None
        self.close_after_worker = False
        self.add_button = None
        self.setWindowTitle("KIM6 Metadata Browser")
        available = QApplication.primaryScreen().availableGeometry()
        minimum_width = min(900, max(620, available.width() - 24))
        minimum_height = min(560, max(480, available.height() - 48))
        self.setMinimumSize(minimum_width, minimum_height)
        self.resize(min(1160, max(minimum_width, available.width() - 24)),
                    min(740, max(minimum_height, available.height() - 60)))
        self.settings = QSettings("KIM6", "MetadataBrowser")
        self.section_expanded = {
            name: self.settings.value(f"overview/expanded/{name}", True, type=bool)
            for name in ("Description", "Creator & rights", "Camera & capture")
        }
        self.group_expanded = {
            family: self.settings.value(f"tags/expanded/{family}", True, type=bool)
            for family in METADATA_FAMILY_ORDER
        }
        self._applying_group_filter = False
        self._group_filter_active = False
        self.selected_entry = None

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
        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self.select_image)
        self.image_list.setMinimumHeight(120)
        self.image_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.image_list.setIconSize(QSize(48, 36))
        self.image_list.setUniformItemSizes(True)
        self.preview = PreviewLabel()
        self.preview.setText("Choose one or more images to inspect")
        self.preview.setFrameShape(QFrame.StyledPanel)
        self.preview.setFrameShadow(QFrame.Sunken)
        self.preview.setAutoFillBackground(True)
        palette = self.preview.palette()
        palette.setColor(self.preview.backgroundRole(), self.palette().color(self.backgroundRole()))
        self.preview.setPalette(palette)
        layout.addWidget(self.preview, 3)
        self.filename = QLabel("")
        self.filename.setStyleSheet("font-weight: 600")
        self.filename.setTextFormat(Qt.PlainText)
        self.filename.setWordWrap(False)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename.setToolTip("")
        self.filename.setMinimumWidth(0)
        self.filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.filename.setFixedHeight(self.filename.sizeHint().height())
        self.format_label = QLabel("")
        self.format_label.setTextFormat(Qt.PlainText)
        self.format_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.format_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.format_label.setFixedHeight(self.format_label.sizeHint().height())
        self.position_label = QLabel("0 of 0")
        self.position_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.position_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details = QHBoxLayout()
        details.setSpacing(8)
        details.addWidget(self.filename, 1)
        details.addWidget(self.format_label)
        details.addWidget(self.position_label)
        layout.addLayout(details)
        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.previous_button.clicked.connect(lambda: self.image_list.setCurrentRow(max(0, self.image_list.currentRow() - 1)))
        self.next_button.clicked.connect(lambda: self.image_list.setCurrentRow(min(self.image_list.count() - 1, self.image_list.currentRow() + 1)))
        navigation.addWidget(self.previous_button, 1)
        navigation.addWidget(self.next_button, 1)
        layout.addLayout(navigation)
        selection_row = QHBoxLayout()
        selection_heading = QLabel("Selected images")
        selection_heading.setStyleSheet("font-weight: 600")
        selection_row.addWidget(selection_heading)
        self.selection_count = QLabel("0 images")
        self.selection_count.setStyleSheet("color: palette(placeholder-text)")
        selection_row.addWidget(self.selection_count)
        selection_row.addStretch(1)
        self.add_button = QPushButton("Add images…")
        self.add_button.clicked.connect(self.choose_files)
        selection_row.addWidget(self.add_button)
        layout.addLayout(selection_row)
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
        self.show_empty.toggled.connect(self.update_overview)
        overview_layout.addWidget(self.show_empty)
        self.overview_scroll = QScrollArea()
        self.overview_scroll.setWidgetResizable(True)
        self.overview_body = QWidget()
        self.overview_body.setMaximumWidth(860)
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
        self.model = QStandardItemModel(0, 4, self)
        self.model.setHorizontalHeaderLabels(["Tag", "Value", "Group", "Identifier"])
        self.proxy = MetadataFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
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
        self.grouped_tree = QTreeWidget()
        self.grouped_tree.setColumnCount(2)
        self.grouped_tree.setHeaderLabels(["Field", "Value"])
        self.grouped_tree.setRootIsDecorated(True)
        self.grouped_tree.setAlternatingRowColors(True)
        self.grouped_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.grouped_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grouped_tree.setUniformRowHeights(True)
        self.grouped_tree.setWordWrap(False)
        self.grouped_tree.setTextElideMode(Qt.ElideRight)
        self.grouped_tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.grouped_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.grouped_tree.setColumnWidth(0, 235)
        self.grouped_tree.currentItemChanged.connect(self.show_grouped_entry)
        self.grouped_tree.itemExpanded.connect(self._group_expanded)
        self.grouped_tree.itemCollapsed.connect(self._group_collapsed)
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
        self.copy_button = QPushButton("Copy value")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_value)
        copy_row.addWidget(self.copy_button)
        copy_row.addStretch(1)
        tags_layout.addLayout(copy_row)
        self.tabs.addTab(tags, "All tags")
        self.search.textChanged.connect(self._filter_tags)
        self.tag_view_mode.currentTextChanged.connect(self._set_tag_view_mode)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Open images", str(Path.home()), "Images and XMP sidecars (*)")
        if files:
            self.set_images([*self.paths, *files])

    def set_images(self, paths):
        old = set(self.paths)
        self.paths = list(dict.fromkeys(str(Path(path).expanduser().resolve(strict=False)) for path in paths))
        for path in self.paths:
            if path not in old:
                item = QListWidgetItem(Path(path).name)
                item.setToolTip(path)
                self.image_list.addItem(item)
        self.selection_count.setText(f"{len(self.paths)} image" + ("s" if len(self.paths) != 1 else ""))
        self.records.clear()
        self.previews.clear()
        self._set_loading()
        if self.paths:
            self.image_list.setCurrentRow(0)
            self.worker = MetadataWorker(self.paths, self)
            self.add_button.setEnabled(False)
            self.worker.completed.connect(self.receive_results)
            self.worker.finished.connect(self.worker_finished)
            self.worker.start()

    def _set_loading(self):
        self.model.removeRows(0, self.model.rowCount())
        self.grouped_tree.clear()
        self.value_detail.clear()
        self.selected_entry = None
        self.preview.set_image(QImage())
        self.preview.setText("Reading image preview…")
        self.filename.setText("Metadata inspection is running…")
        self.format_label.clear()
        self.status_summary.setText("Reading metadata…")
        self.notice.clear()
        self.notice.hide()
        self.copy_button.setEnabled(False)

    def receive_results(self, records, previews, _error):
        self.records.update(records)
        self.previews.update(previews)
        for row, path in enumerate(self.paths):
            preview = self.previews.get(path)
            if preview and not preview[0].isNull():
                pixmap = QPixmap.fromImage(preview[0]).scaled(
                    QSize(48, 36), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_list.item(row).setIcon(QIcon(pixmap))
        self.update_current()

    def worker_finished(self):
        worker = self.worker
        if worker and not worker.wait(1000):
            QTimer.singleShot(50, self.worker_finished)
            return
        self.worker = None
        if self.close_after_worker:
            self.close()
        else:
            self.add_button.setEnabled(True)

    def select_image(self, _row):
        self.update_current()

    def update_current(self):
        row = self.image_list.currentRow()
        if row < 0 or row >= len(self.paths):
            return
        path = self.paths[row]
        self.filename.setText(Path(path).name)
        self.filename.setToolTip(path)
        self.previous_button.setEnabled(row > 0)
        self.next_button.setEnabled(row + 1 < len(self.paths))
        self.position_label.setText(f"{row + 1} of {len(self.paths)}")
        preview = self.previews.get(path)
        if preview:
            image, error = preview
            if not image.isNull():
                self.preview.set_image(image)
                self.preview.setToolTip("")
            else:
                self.preview.set_image(QImage())
                record = self.records.get(path)
                message = (record.error if record and record.error else error) or "This image format is not supported by the preview decoder."
                self.preview.setText(message)
                self.preview.setToolTip(message)
        else:
            self.preview.set_image(QImage())
            self.preview.setText("Reading image preview…" if self.worker else "Preview unavailable")
        record = self.records.get(path)
        fmt = next((entry.value for entry in (record.entries if record else []) if entry.name.casefold() == "filetype"), "Unknown format")
        dimensions = f"{preview[0].width()} × {preview[0].height()} px" if preview and not preview[0].isNull() else "Dimensions unavailable"
        self.format_label.setText(f"{fmt}  ·  {dimensions}")
        messages = ([record.error] if record and record.error else []) + (record.warnings if record else [])
        self.notice.setText("\n".join(messages))
        self.notice.setVisible(bool(messages))
        self._update_status_summary(record)
        self._populate_tags(record)
        self.update_overview()

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

    @staticmethod
    def _entry_columns(entry, record):
        raw = _text(entry.value)
        display_name = f"{entry.name} [{entry.language}]" if entry.language else entry.name
        identifier = f"ID {entry.tag_id}" if entry.tag_id is not None else ""
        if entry.language:
            identifier = f"{identifier}; language {entry.language}".strip("; ")
        if entry.source and Path(entry.source).resolve(strict=False) != Path(record.path).resolve(strict=False):
            identifier = f"{identifier}; {Path(entry.source).name}".strip("; ")
        search_text = " ".join((entry.name, entry.qualified_name, entry.group, identifier,
                                raw, " ".join(entry.groups or ()), entry.source,
                                str(entry.tag_id or ""), entry.language or ""))
        return display_name, _compact(entry.value), entry.group, identifier, raw, search_text

    def _populate_grouped_tree(self, record):
        self.grouped_tree.clear()
        if not record:
            return
        families = {}
        for entry in record.entries:
            families.setdefault(self._metadata_family(entry), []).append(entry)
        order = METADATA_FAMILY_ORDER
        for family in order:
            entries = families.get(family)
            if not entries:
                continue
            parent = QTreeWidgetItem(self.grouped_tree, [f"{family} ({len(entries)})", ""])
            parent.setData(0, Qt.UserRole, None)
            parent.setData(0, Qt.UserRole + 1, family)
            parent.setToolTip(0, f"{family}: {len(entries)} metadata entries")
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFont(1, font)
            for entry in entries:
                name, value, _group, _identifier, raw, search_text = self._entry_columns(entry, record)
                field_name = self._grouped_field_name(entry)
                row_value = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
                if len(row_value) > DISPLAY_LIMIT:
                    row_value = row_value[:DISPLAY_LIMIT - 1] + "…"
                child = QTreeWidgetItem(parent, [field_name, row_value])
                child.setData(0, Qt.UserRole, entry)
                child.setData(0, Qt.UserRole + 1, f"{family} {search_text}")
                child.setToolTip(0, f"{field_name}\n{entry.qualified_name}\n{entry.group}")
                child.setToolTip(1, raw)
            parent.setExpanded(self.group_expanded.get(family, True))
        self._filter_grouped_tree(self.search.text())

    def _group_expanded(self, item):
        if self._applying_group_filter:
            return
        family = item.data(0, Qt.UserRole + 1)
        if family in self.group_expanded:
            self.group_expanded[family] = True
            self.settings.setValue(f"tags/expanded/{family}", True)

    def _group_collapsed(self, item):
        if self._applying_group_filter:
            return
        family = item.data(0, Qt.UserRole + 1)
        if family in self.group_expanded:
            self.group_expanded[family] = False
            self.settings.setValue(f"tags/expanded/{family}", False)

    def _filter_grouped_tree(self, text):
        needle = text.casefold().strip()
        if needle and not self._group_filter_active:
            for index in range(self.grouped_tree.topLevelItemCount()):
                parent = self.grouped_tree.topLevelItem(index)
                family = parent.data(0, Qt.UserRole + 1)
                self.group_expanded[family] = parent.isExpanded()
            self._group_filter_active = True
        for index in range(self.grouped_tree.topLevelItemCount()):
            parent = self.grouped_tree.topLevelItem(index)
            matched = 0
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                blob = str(child.data(0, Qt.UserRole + 1) or "").casefold()
                visible = not needle or needle in blob
                child.setHidden(not visible)
                matched += int(visible)
            parent.setHidden(matched == 0)
            if needle and matched:
                self._applying_group_filter = True
                parent.setExpanded(True)
                self._applying_group_filter = False
            elif not needle:
                self._applying_group_filter = True
                family = parent.data(0, Qt.UserRole + 1)
                parent.setExpanded(self.group_expanded.get(family, True))
                self._applying_group_filter = False
        if not needle:
            self._group_filter_active = False
        current = self.grouped_tree.currentItem()
        if current and (current.isHidden() or (current.parent() and current.parent().isHidden())):
            self.grouped_tree.setCurrentItem(None)
            self._show_entry(None)

    def _filter_tags(self, text):
        self.proxy.set_needle(text)
        self._filter_grouped_tree(text)
        if self.tag_view_mode.currentText() == "Flat" and not self.table.currentIndex().isValid():
            self._show_entry(None)

    def _set_tag_view_mode(self, mode):
        self.tags_stack.setCurrentIndex(0 if mode == "Grouped" else 1)
        self.grouped_tree.setCurrentItem(None)
        self.grouped_tree.clearSelection()
        self.table.setCurrentIndex(QModelIndex())
        self.table.clearSelection()
        self._show_entry(None)

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
        parts = [f"{len(record.entries)} metadata entries"]
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
        self.model.removeRows(0, self.model.rowCount())
        self.grouped_tree.clear()
        self.value_detail.clear()
        self.selected_entry = None
        self.copy_button.setEnabled(False)
        self._show_entry(None)
        if not record:
            return
        for entry in record.entries:
            name, value, group, identifier, raw, search_text = self._entry_columns(entry, record)
            columns = [name, value, group, identifier]
            items = []
            for index, value in enumerate(columns):
                item = QStandardItem(value)
                item.setEditable(False)
                item.setData(entry, Qt.UserRole)
                item.setData(raw if index == 1 else value, Qt.UserRole + 1)
                item.setData(search_text, Qt.UserRole + 2)
                item.setToolTip(search_text)
                items.append(item)
            self.model.appendRow(items)
        self._populate_grouped_tree(record)

    def _entries(self, record, names):
        if not record:
            return []
        wanted = {name.casefold() for name in names}
        return [entry for entry in record.entries if entry.name.casefold() in wanted]

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

    @staticmethod
    def _subdued_label(text, parent=None):
        label = QLabel(text, parent)
        label.setTextFormat(Qt.PlainText)
        palette = label.palette()
        palette.setColor(QPalette.WindowText, palette.color(QPalette.PlaceholderText))
        label.setPalette(palette)
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
        expanded = self.section_expanded.get(title, True)
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
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 2, 0, 8)
        body_layout.setSpacing(2)
        body.setVisible(expanded)
        heading.toggled.connect(lambda value, name=title, content=body, button=heading:
                                self._set_section_expanded(name, value, content, button))
        self.overview_layout.addWidget(heading, 0, Qt.AlignLeft)
        self.overview_layout.addWidget(body)
        self.section_layout = body_layout

    def _set_section_expanded(self, section, expanded, body, button):
        self.section_expanded[section] = expanded
        body.setVisible(expanded)
        button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.settings.setValue(f"overview/expanded/{section}", expanded)

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

    def _add_missing_field(self, label):
        row = QHBoxLayout()
        row.setSpacing(8)
        name = self._subdued_label(label)
        value = self._subdued_label("Not present")
        row.addWidget(name)
        row.addWidget(value)
        row.addStretch(1)
        self.section_layout.addLayout(row)
        self.section_layout.addSpacing(4)

    def _add_description_field(self, label, entries, record):
        if not entries:
            self._add_missing_field(label)
            return
        grouped = self._overview_groups(entries, record, title=label in {"Title", "Caption / Description"})
        by_language = {}
        for language, shown, sources in grouped:
            by_language.setdefault(language, []).append((shown, sources))
        has_conflict = any(len(values) > 1 for values in by_language.values())

        self.section_layout.addWidget(self._subdued_label(label))
        self.section_layout.addSpacing(3)
        if has_conflict:
            self._add_conflict_indicator()
            for language, values in by_language.items():
                for shown, sources in values:
                    source = " · ".join(sorted(sources))
                    language_label = f"{language}: " if language and language != "x-default" else ""
                    line = f"{source}: {language_label}{shown}" if source else f"{language_label}{shown}"
                    self.section_layout.addWidget(self._content_label(line, prominent=label == "Title"))
                    self.section_layout.addSpacing(2)
        else:
            default = next((value for value in grouped if value[0] == "x-default"), None)
            primary = default or next((value for value in grouped if not value[0]), grouped[0])
            language, shown, _sources = primary
            primary_text = (f"{language}: {shown}" if language and language != "x-default" else shown)
            self.section_layout.addWidget(self._content_label(primary_text, prominent=label == "Title"))

            alternatives = [value for value in grouped if value is not primary]
            if alternatives:
                alt_text = " · ".join(
                    f"{lang or 'Other'}: {value}"
                    for lang, value, _sources in alternatives)
                alt_label = self._subdued_label(alt_text)
                alt_label.setWordWrap(True)
                self.section_layout.addWidget(alt_label)

            sources = set().union(*(source_set for _lang, _value, source_set in grouped))
            if sources:
                self.section_layout.addWidget(self._subdued_label(" · ".join(sorted(sources))))
        self.section_layout.addSpacing(7)

    def _add_rights_field(self, label, entries, record):
        if not entries:
            self._add_missing_field(label)
            return
        grouped = self._overview_groups(entries, record)
        by_language = {}
        for language, shown, sources in grouped:
            by_language.setdefault(language, []).append((shown, sources))
        has_conflict = any(len(values) > 1 for values in by_language.values())
        self.section_layout.addWidget(self._subdued_label(label))
        self.section_layout.addSpacing(3)
        if has_conflict:
            self._add_conflict_indicator()
            for language, values in by_language.items():
                for shown, sources in values:
                    source = " · ".join(sorted(sources))
                    language_prefix = f"{language}: " if language and language != "x-default" else ""
                    text = f"{source}: {language_prefix}{shown}" if source else f"{language_prefix}{shown}"
                    self.section_layout.addWidget(self._content_label(text))
        else:
            primary = next((value for value in grouped if value[0] == "x-default"), None)
            primary = primary or next((value for value in grouped if not value[0]), grouped[0])
            _language, shown, _sources = primary
            self.section_layout.addWidget(self._content_label(shown))
            alternatives = [value for value in grouped if value is not primary]
            if alternatives:
                text = " · ".join(f"{lang}: {value}" for lang, value, _sources in alternatives)
                self.section_layout.addWidget(self._subdued_label(text))
            sources = set().union(*(source_set for _lang, _value, source_set in grouped))
            if sources:
                self.section_layout.addWidget(self._subdued_label(" · ".join(sorted(sources))))
        self.section_layout.addSpacing(7)

    def _camera_values(self, label, aliases, record):
        if label == "Camera":
            makes = self._entries(record, ("Make",))
            models = self._entries(record, ("Model",))
            make = next((_overview_value(entry.value) for entry in makes if _overview_value(entry.value)), "")
            model = next((_overview_value(entry.value) for entry in models if _overview_value(entry.value)), "")
            value = " ".join(part for part in (make, model) if part)
            return [value] if value else []
        if label == "Image dimensions":
            entries = self._entries(record, ("ImageSize",))
            if entries:
                return list(dict.fromkeys(_format_camera_value(label, entry.value) for entry in entries))
            width = self._entries(record, ("ImageWidth",))
            height = self._entries(record, ("ImageHeight",))
            if width and height:
                return [f"{_overview_value(width[0].value)} × {_overview_value(height[0].value)} pixels"]
        entries = self._entries(record, aliases)
        values = []
        for entry in entries:
            shown = _format_camera_value(label, entry.value)
            if shown and shown not in values:
                values.append(shown)
        return values

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

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                MetadataBrowser._clear_layout(item.layout())
                item.layout().deleteLater()

    def update_overview(self):
        self._clear_layout(self.overview_layout)
        row = self.image_list.currentRow()
        record = self.records.get(self.paths[row]) if 0 <= row < len(self.paths) else None
        self._section_heading("Description", first=True)
        for label, aliases in DESCRIPTION_FIELDS:
            self._add_description_field(label, self._entries(record, aliases), record)

        self._section_heading("Creator & rights")
        for label, aliases in RIGHTS_FIELDS:
            self._add_rights_field(label, self._entries(record, aliases), record)

        self._section_heading("Camera & capture")
        self._add_camera_section(record)
        self.overview_layout.addStretch(1)

    def show_entry_value(self, current, _previous):
        index = self.proxy.index(current.row(), 0, current.parent()) if current.isValid() else None
        entry = index.data(Qt.UserRole) if index and index.isValid() else None
        self._show_entry(entry)

    def show_grouped_entry(self, current, _previous):
        entry = current.data(0, Qt.UserRole) if current and current.parent() else None
        self._show_entry(entry)

    def _show_entry(self, entry):
        had_entry = isinstance(self.selected_entry, MetadataEntry)
        if not isinstance(entry, MetadataEntry):
            self.selected_entry = None
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
        self.value_detail.setPlainText(_text(entry.value))
        self.copy_button.setEnabled(True)
        if not had_entry:
            details_size = min(190, max(145, int(self.tags_splitter.height() * 0.28)))
            self.tags_splitter.setSizes([max(1, self.tags_splitter.height() - details_size), details_size])

    def copy_value(self):
        if isinstance(self.selected_entry, MetadataEntry):
            QApplication.clipboard().setText(_text(self.selected_entry.value))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.close_after_worker = True
            self.worker.requestInterruption()
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.sizes())
        for section, expanded in self.section_expanded.items():
            self.settings.setValue(f"overview/expanded/{section}", expanded)
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
    app.setApplicationName("KIM6 Metadata Browser")
    app.setOrganizationName("KIM6")
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
