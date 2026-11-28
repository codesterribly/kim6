#!/usr/bin/env python3
"""Native Review Changes gate and asynchronous browser-site preparation."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from PySide6.QtCore import Qt, QSize, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QProgressDialog,
    QPushButton, QScrollArea, QTableWidget, QStyle, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

from PySide6.QtWidgets import QSizePolicy, QHeaderView

from kim_dialog_buttons import style_button, style_button_box
from kim_story_publication import (
    DERIVATIVE_MAX_SIZE, DERIVATIVE_QUALITY, THUMBNAIL_MAX_SIZE, THUMBNAIL_QUALITY,
    PreparedPublication, StoryDocument, image_quality_summary, prepare_publication,
    output_pages, publication_collections, publication_slug, publish_prepared, publish_prepared_zip,
    resolve_image_quality, validate_prepared,
)


def private_preview_workspace() -> str:
    """Return one bounded, per-user local preview directory.

    It is intentionally retained after KIMng closes because the browser may
    still be reading it. Repeated sessions reuse the same directory and fixed
    image names; no preview tree is automatically deleted under a browser.
    """
    uid = os.getuid()
    root = Path(tempfile.gettempdir()) / f"kimng-photo-story-preview-{uid}"
    try:
        os.mkdir(root, 0o700)
    except FileExistsError:
        pass
    info = os.lstat(root)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != uid or info.st_mode & 0o077):
        raise ValueError("The private Photo Story preview directory is unsafe")
    images = root / "images"
    images.mkdir(mode=0o700, exist_ok=True)
    if images.is_symlink() or images.stat().st_uid != uid:
        raise ValueError("The private preview image directory is unsafe")
    os.chmod(images, 0o700)
    return str(root)


class PreparationWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, document: StoryDocument, workspace: str, parent=None):
        super().__init__(parent)
        self.document = document
        self.workspace = workspace

    def run(self):
        try:
            from kim_process import inspection_context
            with inspection_context(cancelled=self.isInterruptionRequested):
                prepared = prepare_publication(
                    self.document, self.workspace,
                    cancelled=self.isInterruptionRequested,
                    progress=self.progress.emit,
                )
            if not self.isInterruptionRequested():
                self.completed.emit(prepared)
        except InterruptedError:
            self.failed.emit("Gallery preview preparation was cancelled.")
        except Exception as exc:
            self.failed.emit(str(exc))


class PublicationWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, prepared: PreparedPublication, destination: str,
                 approved_parent_identity=None, parent=None):
        super().__init__(parent)
        self.prepared = prepared
        self.destination = destination
        self.approved_parent_identity = approved_parent_identity

    def run(self):
        try:
            publisher = (publish_prepared_zip if self.prepared.document.output_format == "zip"
                         else publish_prepared)
            options = {"cancelled": self.isInterruptionRequested,
                       "progress": self.progress.emit,
                       "approved_parent_identity": self.approved_parent_identity}
            if self.prepared.document.output_format == "zip":
                options["gallery_name"] = publication_slug(self.prepared.document.title)
            output = publisher(self.prepared, self.destination, **options)
            self.completed.emit(output)
        except Exception as exc:
            self.failed.emit(str(exc))


def prepare_for_browser(parent, document: StoryDocument):
    """Prepare from the approved snapshot without blocking the editor UI."""
    workspace = private_preview_workspace()
    worker = PreparationWorker(document, workspace, parent)
    dialog = QProgressDialog(
        "Preparing a private, offline gallery preview…", "Cancel", 0, 0, parent)
    dialog.setWindowTitle("Preparing gallery preview")
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    result = {"prepared": None, "error": ""}

    def complete(value):
        result["prepared"] = value
        dialog.accept()

    def fail(error):
        result["error"] = error
        dialog.accept()

    worker.completed.connect(complete)
    worker.failed.connect(fail)
    worker.progress.connect(
        lambda current, total, name: (
            dialog.setRange(0, total), dialog.setValue(current),
            dialog.setLabelText(f"Preparing image {current + 1} of {total}: {name}")
        ) if total else dialog.setLabelText("Finishing the offline gallery preview…")
    )
    dialog.canceled.connect(worker.requestInterruption)
    worker.start()
    dialog.exec()
    if worker.isRunning():
        worker.requestInterruption()
        worker.wait()
    worker.deleteLater()
    if result["error"] and result["error"] != "Gallery preview preparation was cancelled.":
        QMessageBox.warning(parent, "Gallery preview unavailable", result["error"])
    if result["prepared"] is not None and result["prepared"].blocked:
        details = "\n".join(
            f"{Path(item.source).name}: {item.reason}"
            for item in result["prepared"].blocked[:8])
        if len(result["prepared"].blocked) > 8:
            details += f"\nAnd {len(result['prepared'].blocked) - 8} more image(s)."
        QMessageBox.warning(parent, "Some images are unavailable", details)
    return result["prepared"]


class StoryReviewDialog(QDialog):
    """Review immutable gallery contents and approve one exact destination."""

    def __init__(self, document: StoryDocument, destination: str, parent=None):
        super().__init__(parent)
        self.document = document
        self.destination = str(Path(destination).absolute())
        try:
            parent_info = Path(self.destination).parent.resolve(strict=True).stat()
            self.approved_parent_identity = (parent_info.st_dev, parent_info.st_ino)
        except OSError:
            self.approved_parent_identity = None
        self.prepared: PreparedPublication | None = None
        self.publication_path = ""
        self.cancel_requested = False
        self.worker = None
        self.publication_worker = None
        self.publication_progress = None
        self._closing = False

        self.setWindowTitle("KIMng - Create a gallery - Review Changes")
        self.resize(1000, 720)
        self.setMinimumSize(740, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(9)

        title = QLabel("Review gallery output")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self.status = QLabel("Preparing gallery output…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

        summary = QFrame()
        summary.setFrameShape(QFrame.StyledPanel)
        summary_grid = QGridLayout(summary)
        summary_grid.setHorizontalSpacing(16)
        summary_grid.setVerticalSpacing(5)

        fields = (
            ("Gallery type", 0, 0),
            ("Visual style", 0, 2),
            ("Image arrangement", 1, 0),
            ("Output format", 1, 2),
            ("Story content", 2, 0),
            ("Story title", 2, 2),
            ("Website structure", 3, 0),
            ("Sections", 3, 2),
            ("Image quality", 4, 0),
        )
        self.summary_fields = {}
        for name, row, column in fields:
            label = QLabel(name + ":")
            value = QLabel("Preparing…")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            summary_grid.addWidget(label, row, column)
            summary_grid.addWidget(value, row, column + 1)
            self.summary_fields[name] = value
        summary_grid.setColumnStretch(1, 1)
        summary_grid.setColumnStretch(3, 1)
        layout.addWidget(summary)

        heading_row = QHBoxLayout()
        content_title = QLabel("Planned gallery content")
        content_title.setStyleSheet("font-weight: 700;")
        heading_row.addWidget(content_title)
        heading_row.addStretch()
        self.content_count = QLabel()
        heading_row.addWidget(self.content_count)
        layout.addLayout(heading_row)

        self.story_scroll = QScrollArea()
        self.story_scroll.setWidgetResizable(True)
        self.story_scroll.setFrameShape(QFrame.StyledPanel)
        self.story_container = QWidget()
        self.story_layout = QVBoxLayout(self.story_container)
        self.story_layout.setContentsMargins(8, 8, 8, 8)
        self.story_layout.setSpacing(6)
        self.story_scroll.setWidget(self.story_container)
        layout.addWidget(self.story_scroll, 1)

        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        layout.addWidget(self.warnings_label)

        self.output_toggle = QToolButton()
        self.output_toggle.setText("Output details")
        self.output_toggle.setCheckable(True)
        self.output_toggle.setChecked(False)
        self.output_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.output_toggle.setArrowType(Qt.RightArrow)
        layout.addWidget(self.output_toggle)

        self.output_box = QWidget()
        output_layout = QVBoxLayout(self.output_box)
        output_layout.setContentsMargins(4, 0, 4, 0)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        output_layout.addWidget(self.details)
        self.details.hide()

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ("Story element", "Source", "Generated file", "Derivative")
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(150)
        output_layout.addWidget(self.table)
        self.table.hide()

        self.output_inventory = QTableWidget(0, 3)
        self.output_inventory.setHorizontalHeaderLabels(
            ("Generated file", "Type", "Details")
        )
        self.output_inventory.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.output_inventory.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.output_inventory.setAlternatingRowColors(True)
        self.output_inventory.horizontalHeader().setStretchLastSection(True)
        self.output_inventory.setMaximumHeight(230)
        output_layout.addWidget(self.output_inventory)

        self.output_box.setMaximumHeight(250)
        self.output_box.setVisible(False)
        layout.addWidget(self.output_box)

        def toggle_output(checked):
            self.output_toggle.setArrowType(
                Qt.DownArrow if checked else Qt.RightArrow
            )
            self.output_box.setVisible(checked)

        self.output_toggle.toggled.connect(toggle_output)

        destination_title = QLabel("Destination")
        destination_title.setStyleSheet("font-weight: 700;")
        layout.addWidget(destination_title)

        # Retain the validated QLineEdit model for compatibility
        # and signal handling. Display a wrapping full-width path
        # instead of a horizontally scrolling control.
        self.destination_edit = QLineEdit(self.destination)
        self.destination_edit.setObjectName(
            "reviewGalleryDestinationPath")
        self.destination_edit.textChanged.connect(
            self._review_destination_changed)
        self.destination_edit.hide()

        self.change_destination_button = QPushButton(
            "Change destination…")
        self.change_destination_button.setIcon(
            QIcon.fromTheme("folder-open"))
        self.change_destination_button.clicked.connect(
            self.change_review_destination)
        layout.addWidget(
            self.change_destination_button, 0, Qt.AlignLeft)

        self.destination_path = QLabel(self.destination)
        self.destination_path.setObjectName(
            "reviewGalleryDestinationDisplay")
        self.destination_path.setWordWrap(True)
        self.destination_path.setMinimumWidth(0)
        self.destination_path.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        self.destination_path.setToolTip(self.destination)
        layout.addWidget(self.destination_path)

        self.destination_feedback = QLabel()
        self.destination_feedback.setWordWrap(True)
        layout.addWidget(self.destination_feedback)

        # Compatibility for existing review tests and callers.
        self.destination_label = QLabel(self.destination)
        self.destination_label.hide()

        actions = QHBoxLayout()

        self.back_button = QPushButton("Back")
        self.back_button.setIcon(QIcon.fromTheme("go-previous"))
        self.back_button.clicked.connect(self.go_back)
        style_button(self.back_button)
        actions.addWidget(self.back_button)

        actions.addStretch(1)

        self.open_preview = QPushButton("Preview in browser")
        self.open_preview.setIcon(QIcon.fromTheme("internet-web-browser"))
        self.open_preview.setEnabled(False)
        self.open_preview.clicked.connect(self.open_browser_preview)
        self.open_preview.hide()

        self.buttons = QDialogButtonBox()
        style_button_box(self.buttons)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setIcon(QIcon.fromTheme("dialog-ok-apply"))
        self.apply_button.setEnabled(False)
        style_button(self.apply_button)
        self.buttons.addButton(self.apply_button, QDialogButtonBox.AcceptRole)
        self.apply_button.clicked.connect(self.apply)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(QIcon.fromTheme("dialog-cancel"))
        self.cancel_button.clicked.connect(self.cancel_story)
        style_button(self.cancel_button)
        self.buttons.addButton(self.cancel_button, QDialogButtonBox.RejectRole)

        actions.addWidget(self.buttons)
        layout.addLayout(actions)
        self._start_preparation()

    def _start_preparation(self):
        self.worker = PreparationWorker(self.document, private_preview_workspace(), self)
        self.worker.completed.connect(self._prepared)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finish_cancel_if_ready)
        self.worker.start()

    def _progress(self, current, total, name):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.progress.setFormat(f"Preparing image {current} of {total}: %p%")
            self.status.setText(f"Preparing {name}")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.setFormat("No images to prepare")

    def _prepared(self, prepared):
        if self._closing:
            return
        self.prepared = prepared
        self.progress.hide()
        self.open_preview.setEnabled(True)
        images = prepared.images
        elements = len(prepared.document.elements)
        total_images = sum(element.kind == "image" for element in prepared.document.elements)
        layout_labels = {
            "one-per-section": "One image per story section",
            "two-per-section": "Up to two images per story section",
            "adaptive": "Adaptive photographic layout",
            "justified": "Justified horizontal rows",
            "masonry": "Masonry columns",
        }
        type_labels = {"travelogue": "Travelogue", "photo-essay": "Photo essay",
                       "illustrated-story": "Illustrated story", "simple-gallery": "Simple gallery"}
        style_labels = {"classic": "Classic", "modern": "Modern", "dramatic": "Dramatic",
                        "cinematic": "Dramatic", "editorial": "Modern", "journal": "Classic",
                        "simple-light": "Light", "simple-dark": "Dark"}
        gallery_name = publication_slug(prepared.document.title)
        element_by_id = {item.id: item for item in prepared.document.elements}
        sections = publication_collections(prepared.document)
        ordered_elements = (tuple(element_by_id[element_id]
                                  for section in sections
                                  for element_id in section.element_ids)
                            if sections else prepared.document.elements)
        cover_names = []
        for collection in sections:
            cover_id = collection.cover_image_id or next(
                (item_id for item_id in collection.element_ids
                 if element_by_id[item_id].kind == "image" and element_by_id[item_id].output_image), "")
            cover = element_by_id.get(cover_id)
            cover_names.append(f"{collection.title}: {Path(cover.source).name if cover else 'None'}"
                               + (" (automatic)" if not collection.cover_image_id else ""))
        format_label = "ZIP archive" if prepared.document.output_format == "zip" else "Gallery folder"
        max_dim, jpeg_quality = resolve_image_quality(prepared.document)
        quality_label = image_quality_summary(prepared.document)
        planned_files = [*output_pages(prepared.document), "style.css", "gallery-viewer.css", "gallery-viewer.js",
                         *(image.relative_path for image in images),
                         *(image.thumb_relative_path for image in images if image.thumb_relative_path)]
        if prepared.document.output_format == "zip":
            planned_files = [f"{gallery_name}/{name}" for name in planned_files]
        headings = sum(element.kind == "heading" for element in prepared.document.elements)
        passages = sum(element.kind == "text" for element in prepared.document.elements)
        output_instructions = (
            f"The archive contains a {gallery_name}/ folder; extract it to view the gallery."
            if prepared.document.output_format == "zip" else
            "Open index.html in a browser or upload the gallery folder contents to a web host."
        )
        warnings = list(prepared.warnings)
        if prepared.blocked:
            warnings.append(f"{len(prepared.blocked)} image(s) are blocked and prevent Apply.")
        warnings_text = "; ".join(warnings) if warnings else "None"
        self.details.setText(
            f"Gallery type: {type_labels[prepared.document.publication_type]}. "
            f"Visual style: {style_labels[prepared.document.style]}. "
            f"Image arrangement: {layout_labels[prepared.document.layout]}. "
            f"Website structure: {'Multiple pages' if prepared.document.website_structure == 'multiple-pages' else 'Single page'}. "
            f"Sections: {', '.join(item.title for item in sections) or 'None'}. "
            f"Covers: {', '.join(cover_names) or 'None'}. "
            f"Captions: {'shown' if prepared.document.show_captions else 'hidden'}. "
            f"Filenames: {'shown' if not prepared.document.hide_filenames else 'hidden'}. "
            f"Image quality: {quality_label}. "
            f"Output format: {format_label}. "
            f"Story title: {prepared.document.title if prepared.document.title.strip() else 'Untitled story'}. "
            f"{total_images} images, {headings} headings, and {passages} text passages. "
            f"Prepared: {len(images)}. Blocked: {len(prepared.blocked)}.\n"
            f"Output path: {self.destination}\n"
            f"Planned output entries: {', '.join(planned_files)}\n"
            f"Warnings: {warnings_text}\n"
            f"{output_instructions} Gallery contents include index.html, style.css, the local image viewer assets, "
            f"{len(images)} full-view JPEG derivatives (maximum {max_dim} x {max_dim} pixels, quality {jpeg_quality}), "
            f"and {len(images)} grid thumbnails (maximum {THUMBNAIL_MAX_SIZE[0]} x {THUMBNAIL_MAX_SIZE[1]} pixels, quality {THUMBNAIL_QUALITY}). "
            "Images are freshly encoded; embedded source metadata is not copied."
        )
        if prepared.blocked:
            self.details.setText(
                self.details.text()
                + f"\nBlocked images: {len(prepared.blocked)}. Remove or replace them before Apply."
            )
        self.summary_fields["Gallery type"].setText(
            type_labels[prepared.document.publication_type])
        self.summary_fields["Visual style"].setText(
            style_labels[prepared.document.style])
        self.summary_fields["Image arrangement"].setText(
            layout_labels[prepared.document.layout])
        self.summary_fields["Website structure"].setText(
            "Multiple pages" if prepared.document.website_structure == "multiple-pages" else "Single page")
        self.summary_fields["Sections"].setText(
            ", ".join(item.title for item in sections) or "None")
        self.summary_fields["Image quality"].setText(quality_label)
        self.summary_fields["Output format"].setText(format_label)
        self.summary_fields["Story content"].setText(
            f"{total_images} images, {headings} headings, {passages} passages")
        self.summary_fields["Story title"].setText(
            prepared.document.title.strip() or "Untitled story")
        self.content_count.setText(f"{elements} elements")

        if warnings:
            self.warnings_label.setText(
                "Warnings: " + "; ".join(warnings))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setVisible(False)

        self.table.setRowCount(len(ordered_elements))
        images_by_id = {image.element_id: image for image in images}
        blocked_by_id = {image.element_id: image for image in prepared.blocked}
        for row, element in enumerate(ordered_elements):
            if element.kind == "image":
                if element.id in blocked_by_id:
                    item = blocked_by_id[element.id]
                    values = ("Image blocked", Path(item.source).name, "Not generated", item.reason)
                else:
                    item = images_by_id[element.id]
                    generated_name = (f"{gallery_name}/{item.relative_path}"
                                      if prepared.document.output_format == "zip"
                                      else item.relative_path)
                    values = ("Image", Path(item.source).name, generated_name,
                              f"{item.width} × {item.height} px · {item.byte_size:,} bytes · JPEG")
            elif element.kind == "heading":
                values = ("Section heading", element.heading or "(empty)", "No file", "Text")
            else:
                excerpt = element.text.splitlines()[0][:90] if element.text else "(empty)"
                values = ("Text passage", excerpt, "No file", "Text")
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if element.kind == "image" and column == 1:
                    cell.setToolTip((images_by_id if element.id in images_by_id
                                     else blocked_by_id)[element.id].source)
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self._render_story_rows(
            prepared, images_by_id, blocked_by_id, gallery_name)

        self._populate_output_inventory(prepared, gallery_name)
        self._validate_destination()

    def _populate_output_inventory(self, prepared, gallery_name):
        prefix = (
            gallery_name + "/"
            if prepared.document.output_format == "zip" else ""
        )

        entries = [
            *((prefix + name, "HTML", "Gallery document") for name in output_pages(prepared.document)),
            (prefix + "style.css", "CSS", "Gallery stylesheet"),
            (prefix + "gallery-viewer.css", "CSS", "Image viewer"),
            (prefix + "gallery-viewer.js", "JavaScript", "Image viewer"),
        ]

        for image in prepared.images:
            entries.append((
                prefix + image.relative_path,
                "JPEG",
                f"{image.width} × {image.height} px; "
                f"{image.byte_size:,} bytes (full view)"
            ))
            if image.thumb_relative_path:
                entries.append((
                    prefix + image.thumb_relative_path,
                    "Thumbnail JPEG",
                    f"{image.thumb_width} × {image.thumb_height} px; "
                    f"{image.thumb_byte_size:,} bytes (grid thumbnail)"
                ))

        self.output_inventory.setRowCount(len(entries))
        for row, values in enumerate(entries):
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.output_inventory.setItem(row, column, cell)

        self.output_inventory.setWordWrap(True)
        self.output_inventory.setTextElideMode(Qt.ElideNone)

        header = self.output_inventory.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QHeaderView.Interactive)
        header.setSectionResizeMode(
            1, QHeaderView.Fixed)
        header.setSectionResizeMode(
            2, QHeaderView.Stretch)

        self.output_inventory.setColumnWidth(0, 215)
        self.output_inventory.setColumnWidth(1, 80)
        self.output_inventory.resizeRowsToContents()

    def _validate_destination(self):
        self.apply_button.setEnabled(False)
        if self.prepared is None:
            return

        value = self.destination.strip()
        problem = ""
        if not value or not Path(value).is_absolute():
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
            else:
                try:
                    info = parent.resolve(strict=True).stat()
                    if self.approved_parent_identity != (
                            info.st_dev, info.st_ino):
                        problem = "The destination directory changed."
                except OSError:
                    problem = "The destination directory is unavailable."

        if not problem:
            try:
                validate_prepared(self.prepared)
            except Exception as exc:
                problem = str(exc)

        if not problem and self.prepared.blocked:
            problem = (
                f"{len(self.prepared.blocked)} source image(s) "
                "cannot be published."
            )

        self.destination_feedback.setText(problem)
        self.destination_feedback.setVisible(bool(problem))
        if self.prepared.blocked:
            self.status.setText(
                "One or more source images are unavailable. "
                "Go back to remove them or restore the missing files."
            )
        elif problem:
            self.status.setText("Choose another destination to continue.")
        else:
            self.status.setText("Ready to create gallery.")
        self.apply_button.setEnabled(not problem)

    def _review_destination_changed(self, value):
        self.destination = value.strip()
        self.destination_path.setText(
            self.destination or "Choose a destination directory.")
        self.destination_path.setToolTip(self.destination)
        self.destination_label.setText(self.destination)
        self.destination_label.setToolTip(self.destination)
        try:
            parent = Path(self.destination).parent.resolve(
                strict=True).stat()
            self.approved_parent_identity = (
                parent.st_dev, parent.st_ino)
        except (OSError, ValueError):
            self.approved_parent_identity = None
        self._validate_destination()

    def change_review_destination(self):
        if (self.publication_worker is not None
                and self.publication_worker.isRunning()):
            return

        current = self.destination_edit.text().strip()
        start = str(Path(current).parent) if current else str(Path.home())
        selected = QFileDialog.getExistingDirectory(
            self, "Choose gallery destination directory", start,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if selected:
            filename = Path(self.destination).name
            self.destination_edit.setText(str(Path(selected) / filename))

    def _render_story_rows(self, prepared, images_by_id,
                           blocked_by_id, gallery_name):
        """Show compact story-order rows using prepared derivatives only."""
        while self.story_layout.count():
            child = self.story_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        for element in prepared.document.elements:
            card = QFrame()
            card.setFrameShape(QFrame.StyledPanel)

            row = QHBoxLayout(card)
            row.setContentsMargins(6, 3, 6, 3)
            row.setSpacing(8)

            thumbnail_label = QLabel()
            thumbnail_label.setFixedSize(76, 54)
            thumbnail_label.setAlignment(Qt.AlignCenter)

            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(3)
            content.setMinimumWidth(0)
            content.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred)

            name_label = QLabel()
            name_label.setTextFormat(Qt.PlainText)
            name_label.setWordWrap(True)
            name_label.setMinimumWidth(0)
            name_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred)
            name_label.setStyleSheet("font-weight: 600;")
            name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

            detail_label = QLabel()
            detail_label.setTextFormat(Qt.PlainText)
            detail_label.setWordWrap(True)
            detail_label.setMinimumWidth(0)
            detail_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred)
            detail_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse)
            detail_font = detail_label.font()
            detail_font.setPointSize(
                max(8, detail_font.pointSize() - 1))
            detail_label.setFont(detail_font)

            if element.kind == "image":
                image = images_by_id.get(element.id)
                blocked = blocked_by_id.get(element.id)

                if image is not None:
                    reader = QImageReader(image.staged_path)
                    size = reader.size()
                    if size.isValid():
                        reader.setScaledSize(
                            size.scaled(
                                QSize(72, 50), Qt.KeepAspectRatio
                            )
                        )

                    thumbnail = reader.read()
                    if not thumbnail.isNull():
                        thumbnail_label.setPixmap(
                            QPixmap.fromImage(thumbnail)
                        )
                    else:
                        thumbnail_label.setText("No preview")

                    source_name = Path(image.source).name
                    name_label.setText(source_name)
                    name_label.setToolTip(image.source)

                    output_name = image.relative_path
                    if prepared.document.output_format == "zip":
                        output_name = f"{gallery_name}/{output_name}"

                    detail_label.setText(
                        f"{output_name}  |  "
                        f"{image.width} × {image.height} px  |  "
                        f"JPEG  |  {image.byte_size:,} bytes"
                    )
                    detail_label.setToolTip(
                        f"Source: {image.source}\n"
                        f"Planned output: {output_name}"
                    )
                else:
                    source_name = Path(element.source).name
                    reason = (
                        blocked.reason if blocked is not None
                        else "No prepared derivative"
                    )
                    thumbnail_label.setText("Blocked")
                    name_label.setText(source_name)
                    name_label.setToolTip(element.source)
                    detail_label.setText(f"Blocked: {reason}")

            elif element.kind == "heading":
                thumbnail_label.setPixmap(
                    QIcon.fromTheme(
                        "format-text-heading"
                    ).pixmap(28, 28)
                )
                name_label.setText(
                    element.heading or "(empty heading)"
                )
                detail_label.setText(
                    "Section heading  |  Included in index.html"
                )

            else:
                thumbnail_label.setPixmap(
                    QIcon.fromTheme(
                        "format-justify-left"
                    ).pixmap(28, 28)
                )
                excerpt = " ".join((element.text or "").split())
                if len(excerpt) > 140:
                    excerpt = excerpt[:137] + "…"
                name_label.setText(
                    excerpt or "(empty passage)"
                )
                name_label.setToolTip(element.text or "")
                detail_label.setText(
                    "Text in index.html"
                    if excerpt else "Empty text element"
                )

            content_layout.addWidget(name_label)
            content_layout.addWidget(detail_label)

            row.addWidget(thumbnail_label)
            row.addWidget(content, 1)
            self.story_layout.addWidget(card)

        self.story_layout.addStretch(1)

    def _failed(self, error):
        self.progress.hide()
        if self._closing:
            return
        self.status.setText("Gallery preparation failed: " + error)
        self.apply_button.setEnabled(False)

    def open_browser_preview(self):
        index = Path(self.prepared.workspace) / "index.html"
        if not index.is_file():
            QMessageBox.warning(self, "Preview unavailable", "The prepared browser preview is missing.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(index))):
            QMessageBox.warning(self, "Browser unavailable", "KDE could not open the local gallery preview.")

    def apply(self):
        if self.prepared is None or not self.apply_button.isEnabled():
            return
        self.apply_button.setEnabled(False)
        self.back_button.setEnabled(False)
        total = len(self.prepared.images) + 3 + len(output_pages(self.prepared.document))
        self.publication_progress = QProgressDialog(
            "Writing the approved gallery into private staging…",
            "Cancel", 0, total, self)
        self.publication_progress.setWindowTitle("Applying gallery output")
        self.publication_progress.setWindowModality(Qt.WindowModal)
        self.publication_progress.setMinimumDuration(0)
        self.publication_progress.setAutoClose(False)
        self.publication_progress.setAutoReset(False)
        self.publication_worker = PublicationWorker(
            self.prepared, self.destination, self.approved_parent_identity, self)
        self.publication_worker.progress.connect(self._publication_progress)
        self.publication_worker.completed.connect(self._publication_completed)
        self.publication_worker.failed.connect(self._publication_failed)
        self.publication_worker.finished.connect(
            self._finish_cancel_if_ready
        )
        self.publication_progress.canceled.connect(
            self.publication_worker.requestInterruption)
        self.publication_worker.start()
        self.publication_progress.show()

    def go_back(self):
        self.reject()

    def cancel_story(self):
        self.cancel_requested = True
        self.reject()

    def _publication_progress(self, current, total, name):
        progress = self.publication_progress
        if progress is not None:
            progress.setRange(0, total)
            progress.setValue(current)
            progress.setLabelText(f"Preparing {name}")

    def _publication_completed(self, output):
        self.publication_path = output
        if self.publication_progress is not None:
            self.publication_progress.close()
        QDialog.accept(self)

    def _publication_failed(self, error):
        if self.publication_progress is not None:
            self.publication_progress.close()
        self.back_button.setEnabled(True)
        if "cancelled" in error.casefold():
            self.status.setText("Publication cancelled. No gallery output was created.")
            self.apply_button.setEnabled(True)
            return
        self.status.setText("Publication blocked: " + error)
        # A changed source or a newly occupied destination requires a new review.
        self.apply_button.setEnabled(False)

    def _finish_cancel_if_ready(self):
        if not self._closing:
            return
        for worker in (self.worker, self.publication_worker):
            if worker is not None and worker.isRunning():
                return
        QTimer.singleShot(0, lambda: QDialog.reject(self))

    def reject(self):
        running = [
            worker for worker in (
                self.worker, self.publication_worker)
            if worker is not None and worker.isRunning()
        ]
        if running:
            self._closing = True
            self.apply_button.setEnabled(False)
            self.back_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.change_destination_button.setEnabled(False)
            self.status.setText("Stopping gallery operation…")
            for worker in running:
                worker.requestInterruption()
            return
        super().reject()

    def closeEvent(self, event):
        running = [
            worker for worker in (
                self.worker, self.publication_worker)
            if worker is not None and worker.isRunning()
        ]
        if running:
            self._closing = True
            for worker in running:
                worker.requestInterruption()
            event.ignore()
            return
        super().closeEvent(event)

    def done(self, result):
        if self.publication_worker is not None and self.publication_worker.isRunning():
            self.publication_worker.requestInterruption()
            self.publication_worker.wait()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
