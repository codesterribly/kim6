#!/usr/bin/env python3
"""Native Review Changes gate and asynchronous browser-site preparation."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QProgressDialog, QPushButton, QTableWidget,
    QStyle, QTableWidgetItem, QVBoxLayout,
)

from kim_dialog_buttons import style_button, style_button_box
from kim_story_publication import (
    DERIVATIVE_MAX_SIZE, DERIVATIVE_QUALITY,
    PreparedPublication, StoryDocument, prepare_publication,
    publication_slug, publish_prepared, publish_prepared_zip, validate_prepared,
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
        self.resize(920, 680)
        self.setMinimumSize(720, 480)
        layout = QVBoxLayout(self)
        title = QLabel("Review gallery output")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)
        self.status = QLabel("Preparing the exact gallery output shown in browser preview…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Story element", "Source", "Generated file", "Derivative"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        action_row = QHBoxLayout()
        self.open_preview = QPushButton("Preview in browser")
        self.open_preview.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.open_preview.setEnabled(False)
        self.open_preview.clicked.connect(self.open_browser_preview)
        action_row.addWidget(self.open_preview)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self.buttons = QDialogButtonBox()
        style_button_box(self.buttons)
        self.back_button = QPushButton("Back")
        self.cancel_button = QPushButton("Cancel")
        self.back_button.clicked.connect(self.go_back)
        self.cancel_button.clicked.connect(self.cancel_story)
        style_button(self.back_button)
        style_button(self.cancel_button)
        self.buttons.addButton(self.back_button, QDialogButtonBox.RejectRole)
        self.buttons.addButton(self.cancel_button, QDialogButtonBox.RejectRole)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setEnabled(False)
        style_button(self.apply_button)
        self.buttons.addButton(self.apply_button, QDialogButtonBox.AcceptRole)
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.buttons)
        self._start_preparation()

    def _start_preparation(self):
        self.worker = PreparationWorker(self.document, private_preview_workspace(), self)
        self.worker.completed.connect(self._prepared)
        self.worker.failed.connect(self._failed)
        self.worker.progress.connect(self._progress)
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
        }
        type_labels = {"travelogue": "Travelogue", "photo-essay": "Photo essay",
                       "illustrated-story": "Illustrated story"}
        style_labels = {"classic": "Classic", "modern": "Modern", "dramatic": "Dramatic",
                        "cinematic": "Dramatic", "editorial": "Modern", "journal": "Classic"}
        gallery_name = publication_slug(prepared.document.title)
        format_label = "ZIP archive" if prepared.document.output_format == "zip" else "Gallery folder"
        planned_files = ["index.html", "style.css", "gallery-viewer.css", "gallery-viewer.js",
                         *(image.relative_path for image in images)]
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
            f"Captions: {'shown' if prepared.document.show_captions else 'hidden'}. "
            f"Filenames: {'shown' if not prepared.document.hide_filenames else 'hidden'}. "
            f"Output format: {format_label}. "
            f"Story title: {prepared.document.title if prepared.document.title.strip() else 'Untitled story'}. "
            f"{total_images} images, {headings} headings, and {passages} text passages. "
            f"Prepared: {len(images)}. Blocked: {len(prepared.blocked)}.\n"
            f"Output path: {self.destination}\n"
            f"Planned output entries: {', '.join(planned_files)}\n"
            f"Warnings: {warnings_text}\n"
            f"{output_instructions} Gallery contents include index.html, style.css, the local image viewer assets, "
            f"and {len(images)} local JPEG derivatives "
            f"(maximum {DERIVATIVE_MAX_SIZE[0]} x {DERIVATIVE_MAX_SIZE[1]} pixels, quality {DERIVATIVE_QUALITY}). "
            "Images are freshly encoded; embedded source metadata is not copied."
        )
        if prepared.blocked:
            self.details.setText(
                self.details.text()
                + f"\nBlocked images: {len(prepared.blocked)}. Remove or replace them before Apply."
            )
        self.table.setRowCount(len(prepared.document.elements))
        images_by_id = {image.element_id: image for image in images}
        blocked_by_id = {image.element_id: image for image in prepared.blocked}
        for row, element in enumerate(prepared.document.elements):
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
        collision = os.path.lexists(self.destination)
        parent = Path(self.destination).parent
        parent_ready = parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)
        try:
            current_parent = parent.resolve(strict=True).stat()
            parent_matches = self.approved_parent_identity == (
                current_parent.st_dev, current_parent.st_ino)
        except OSError:
            parent_matches = False
        try:
            validate_prepared(prepared)
            validation_error = ""
        except Exception as exc:
            validation_error = str(exc)
        if collision:
            self.status.setText("Blocked: the reviewed output path already exists. Go back and choose another destination.")
        elif not parent_ready or not parent_matches:
            self.status.setText("Blocked: the destination parent directory is unavailable or not writable.")
        elif validation_error:
            self.status.setText("Blocked: " + validation_error)
        else:
            self.status.setText("Ready. Review the exact output plan, then choose Apply to create the gallery.")
            self.apply_button.setEnabled(True)

    def _failed(self, error):
        self.progress.hide()
        if self._closing:
            QTimer.singleShot(0, lambda: QDialog.reject(self))
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
        total = len(self.prepared.images) + 4
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
            if self._closing:
                QTimer.singleShot(0, lambda: QDialog.reject(self))
            return
        self.status.setText("Publication blocked: " + error)
        # A changed source or a newly occupied destination requires a new review.
        self.apply_button.setEnabled(False)

    def reject(self):
        if self.publication_worker is not None and self.publication_worker.isRunning():
            self._closing = True
            self.publication_worker.requestInterruption()
            self.status.setText("Stopping before gallery output is created…")
            self.back_button.setEnabled(False)
            return
        if self.worker is not None and self.worker.isRunning():
            self._closing = True
            self.worker.requestInterruption()
            self.status.setText("Stopping gallery preparation…")
            self.back_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self.publication_worker is not None and self.publication_worker.isRunning():
            self._closing = True
            self.publication_worker.requestInterruption()
            event.ignore()
            return
        if self.worker is not None and self.worker.isRunning():
            self._closing = True
            self.worker.requestInterruption()
            event.ignore()
            return
        event.accept()

    def done(self, result):
        if self.publication_worker is not None and self.publication_worker.isRunning():
            self.publication_worker.requestInterruption()
            self.publication_worker.wait()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait()
        super().done(result)
