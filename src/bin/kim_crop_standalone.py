#!/usr/bin/env python3
"""Standalone Crop review and execution interface."""
from kim_dialog_buttons import style_button, style_button_box

import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kim_recipe_core import preview, execute


class CropPreflight(QThread):
    """Inspect every selected image without publishing outputs."""

    def __init__(self, recipe, files, parent=None):
        super().__init__(parent)
        self.recipe = copy.deepcopy(recipe)
        self.files = list(files)
        self.rows = []
        self.error = ""

    def run(self):
        try:
            from kim_process import inspection_context

            with inspection_context(
                cancelled=self.isInterruptionRequested
            ):
                self.rows = preview(self.recipe, self.files)

        except Exception as exc:
            self.error = str(exc)


class CropReview(QDialog):
    """Standalone Crop review, separate from RunRecipeDialog."""

    def __init__(self, recipe, files):
        super().__init__()

        self.recipe = copy.deepcopy(recipe)
        self.files = list(files)
        self.worker = None
        self.closing = False
        self.approved = None

        self.setWindowTitle("KIMng - Crop - Review Changes")
        self.resize(
            970,
            min(590, 305 + 34 * max(1, len(files)))
        )

        layout = QVBoxLayout(self)

        heading = QLabel(
            f"Crop {len(files)} selected images"
        )
        layout.addWidget(heading)

        output_policy = QLabel(
            "Save cropped images: Create new files "
            "(originals untouched)"
        )
        layout.addWidget(output_policy)

        self.destination = QLabel()
        self.destination.setTextFormat(Qt.PlainText)
        self.destination.setWordWrap(True)

        destination_row = QHBoxLayout()
        self.destination_entry = QLineEdit(self)
        self.destination_entry.setPlaceholderText(
            "Beside each source (leave empty)"
        )
        self.destination_entry.setAccessibleName(
            "Shared destination directory"
        )
        self.destination_entry.setText(
            self.recipe["destination"].get("path", "")
            if self.recipe["destination"]["mode"] == "directory"
            else ""
        )
        destination_row.addWidget(self.destination_entry, 1)

        self.destination_button = QPushButton(
            "Change destination…"
        )
        self.destination_button.clicked.connect(
            self.change_destination
        )
        destination_row.addWidget(self.destination_button)

        self.table = QTableWidget(len(files), 6)
        self.table.setHorizontalHeaderLabels([
            "Image", "Original", "Planned",
            "Output filename", "Destination", "Status",
        ])
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        for column, width in enumerate(
            (165, 105, 105, 215, 205, 90)
        ):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )
            self.table.setColumnWidth(column, width)

        layout.addWidget(self.table, 1)

        self.status = QLabel(
            "Checking selected images…"
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)

        layout.addWidget(self.destination)
        layout.addLayout(destination_row)

        button_row = QHBoxLayout()
        self.back_button = QPushButton("Back")
        style_button(self.back_button)
        self.back_button.setIcon(
            self.back_button.style().standardIcon(
                QStyle.SP_ArrowLeft
            )
        )
        self.back_button.clicked.connect(
            lambda: self.done(131)
        )
        button_row.addWidget(self.back_button)
        button_row.addStretch(1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel
        )
        style_button_box(self.buttons)
        self.apply_button = self.buttons.addButton(
            "Apply changes",
            QDialogButtonBox.AcceptRole,
        )
        style_button(self.apply_button)
        self.apply_button.setIcon(
            self.apply_button.style().standardIcon(
                QStyle.SP_DialogApplyButton
            )
        )
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.approve)
        crop_cancel = self.buttons.button(
            QDialogButtonBox.Cancel
        )
        crop_cancel.setIcon(
            crop_cancel.style().standardIcon(
                QStyle.SP_DialogCancelButton
            )
        )
        self.buttons.rejected.connect(self.reject)
        button_row.addWidget(self.buttons)
        layout.addLayout(button_row)

        self.destination_entry.textChanged.connect(
            lambda _: self.apply_button.setEnabled(False)
        )
        self.destination_entry.editingFinished.connect(
            self.submit_destination
        )

        self.refresh_destination()

        QTimer.singleShot(0, self.recheck)

    def refresh_destination(self):
        dest = self.recipe["destination"]

        if dest["mode"] == "beside":
            label = "Beside each source"

        elif dest["mode"] == "subfolder":
            label = (
                "Subfolder beside each source: "
                + dest["folder"]
            )

        else:
            label = dest.get(
                "path", "No directory selected"
            )

        self.destination.setText(
            "Destination: " + label
        )

    def change_destination(self):
        if self.worker is not None:
            return

        root = (
            self.files[0]
            if self.files
            else str(Path.home())
        )

        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output directory",
            str(Path(root).parent),
        )

        if not folder:
            return

        self.recipe["destination"] = {
            "mode": "directory",
            "path": folder,
            "ask": False,
        }

        self.destination_entry.setText(folder)
        self.refresh_destination()
        self.recheck()

    def submit_destination(self):
        if self.worker is not None:
            return

        directory = self.destination_entry.text().strip()
        if directory:
            folder = Path(directory)
            if (
                not folder.is_absolute()
                or folder.is_symlink()
                or not folder.is_dir()
            ):
                self.status.setText(
                    "Choose an existing absolute destination directory."
                )
                self.apply_button.setEnabled(False)
                return
            self.recipe["destination"] = {
                "mode": "directory",
                "path": str(folder.resolve(strict=True)),
                "ask": False,
            }
        else:
            self.recipe["destination"] = {
                "mode": "beside"
            }

        self.refresh_destination()
        self.recheck()

    def recheck(self):
        if self.worker is not None or self.closing:
            return

        self.apply_button.setEnabled(False)
        self.destination_button.setEnabled(False)
        self.destination_entry.setEnabled(False)
        self.back_button.setEnabled(False)

        self.status.setText(
            "Checking each image and output destination…"
        )

        self.table.setRowCount(len(self.files))

        self.worker = CropPreflight(
            self.recipe,
            self.files,
            self,
        )

        self.worker.finished.connect(
            self.checked
        )
        self.worker.start()

    def checked(self):
        worker = self.worker
        self.worker = None

        if self.closing:
            worker.deleteLater()
            super().reject()
            return

        self.destination_button.setEnabled(True)
        self.destination_entry.setEnabled(True)
        self.back_button.setEnabled(True)

        if worker.error:
            self.status.setText(worker.error)
            worker.deleteLater()
            return

        seen = set()
        problems = []

        for index, (source, row) in enumerate(
            zip(self.files, worker.rows)
        ):
            errors = list(row.problems)

            if not errors and not row.output:
                errors.append(
                    "No planned output"
                )

            if errors:
                planned = "Blocked"
                problems.extend(
                    f"{Path(source).name}: {issue}"
                    for issue in errors
                )

            else:
                output = Path(
                    row.properties.get(
                        "_proposed_output",
                        row.output,
                    )
                )

                candidate = output
                number = 0

                while (
                    str(candidate) in seen
                    or candidate.exists()
                    or candidate.is_symlink()
                ):
                    number += 1
                    candidate = output.with_name(
                        f"{output.stem}_{number}"
                        f"{output.suffix}"
                    )

                seen.add(str(candidate))
                planned = str(candidate)

            properties = row.properties

            dimensions = (
                f"{properties.get('original_display_width', '?')}"
                " × "
                f"{properties.get('original_display_height', '?')}"
                " → "
                f"{properties.get('display_width', '?')}"
                " × "
                f"{properties.get('display_height', '?')}"
            )

            original_size, planned_size = (
                dimensions.split(" → ", 1)
                if " → " in dimensions
                else (dimensions, "Unavailable")
            )
            output_path = (
                Path(planned)
                if planned != "Blocked" else None
            )
            values = (
                Path(source).name,
                original_size,
                planned_size,
                output_path.name if output_path else "No output",
                str(output_path.parent) if output_path else "No output",
                "Blocked" if errors else "Ready",
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    source if column == 0 else value
                )
                self.table.setItem(
                    index, column, item
                )

        if len(worker.rows) != len(self.files):
            problems.append(
                "Not all selected images were inspected."
            )

        if problems:
            self.status.setText(
                "\n".join(problems)
            )

        else:
            self.status.setText("")

        self.apply_button.setEnabled(
            not problems and bool(self.files)
        )

        worker.deleteLater()

    def approve(self):
        if (
            self.worker is not None
            or not self.apply_button.isEnabled()
        ):
            return

        self.approved = copy.deepcopy(
            self.recipe
        )
        super().accept()

    def reject(self):
        if self.worker is not None:
            self.closing = True
            self.worker.requestInterruption()
            self.status.setText(
                "Cancelling review…"
            )
            self.apply_button.setEnabled(False)
            return

        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            event.accept()


class CropExecution(QThread):
    """Process the approved batch without a Recipe UI."""

    started_file = Signal(str, int)
    finished_file = Signal(dict, int)

    def __init__(self, recipe, files):
        super().__init__()

        self.recipe = copy.deepcopy(recipe)
        self.files = list(files)
        self.results = []
        self.error = ""
        self.cancelled = False

    def run(self):
        try:
            from kim_process import inspection_context
            from kim_image_ops import preflight_batch

            # Repeat validation immediately before
            # the first output is published.
            with inspection_context(
                cancelled=self.isInterruptionRequested
            ):
                preflight_batch(
                    self.recipe,
                    self.files,
                )

            for index, source in enumerate(
                self.files, 1
            ):
                if self.isInterruptionRequested():
                    self.cancelled = True
                    break

                self.started_file.emit(
                    str(source), index
                )

                with inspection_context(
                    cancelled=self.isInterruptionRequested
                ):
                    result = execute(
                        self.recipe,
                        [source],
                        start_index=index,
                    )[0]

                self.results.append(result)
                self.finished_file.emit(
                    result, index
                )

                if (
                    not result.get("ok")
                    or result.get("cancelled")
                    or self.isInterruptionRequested()
                ):
                    self.cancelled = bool(
                        result.get("cancelled")
                        or self.isInterruptionRequested()
                    )
                    break

        except Exception as exc:
            self.cancelled = (
                self.isInterruptionRequested()
            )
            if not self.cancelled:
                self.error = str(exc)


class CropProgress(QDialog):
    """Progress only. No persistent review or results window."""

    def __init__(self, total, worker):
        super().__init__()

        self.worker = worker
        self.completed = False

        self.setWindowTitle(
            "KIMng - Job progress"
        )
        self.resize(640, 175)

        layout = QVBoxLayout(self)

        self.label = QLabel(
            f"Cropping {total} images…"
        )
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.label)

        self.bar = QProgressBar()
        self.bar.setRange(0, total)
        layout.addWidget(self.bar)

        self.cancel_button = QPushButton(
            "Cancel all"
        )
        self.cancel_button.clicked.connect(
            self.cancel
        )
        layout.addWidget(
            self.cancel_button
        )

        worker.started_file.connect(
            self.file_started
        )
        worker.finished_file.connect(
            self.file_finished
        )
        worker.finished.connect(
            self.execution_finished
        )

        QTimer.singleShot(
            0, worker.start
        )

    def file_started(self, source, index):
        self.label.setText(
            f"Cropping {index} of "
            f"{self.bar.maximum()}: "
            f"{Path(source).name}"
        )
        self.bar.setValue(index - 1)

    def file_finished(self, result, index):
        self.bar.setValue(index)

        if not result.get("ok"):
            self.label.setText(
                result.get(
                    "error", "Crop failed"
                )
            )

    def cancel(self):
        self.cancel_button.setEnabled(False)
        self.label.setText(
            "Cancelling after the current operation…"
        )
        self.worker.requestInterruption()

    def execution_finished(self):
        self.completed = True
        self.accept()

    def closeEvent(self, event):
        if not self.completed:
            self.cancel()
            event.ignore()
        else:
            event.accept()

    def reject(self):
        if self.completed:
            super().reject()
        else:
            self.cancel()


def run_standalone_crop(recipe, files):
    review = CropReview(recipe, files)

    review_result = review.exec()
    if review_result == 131:
        return 131
    if (
        review_result != QDialog.Accepted
        or review.approved is None
    ):
        return 1

    # Review has closed before progress begins.
    worker = CropExecution(
        review.approved,
        files,
    )

    progress = CropProgress(
        len(files),
        worker,
    )

    progress.exec()
    worker.wait()

    success = (
        not worker.cancelled
        and not worker.error
        and len(worker.results) == len(files)
        and all(
            result.get("ok")
            for result in worker.results
        )
    )

    if not success:
        if worker.error:
            print(
                "Crop failed: " + worker.error,
                file=sys.stderr,
            )

        for result in worker.results:
            if not result.get("ok"):
                print(
                    "Crop failed: "
                    + str(result.get("source"))
                    + ": "
                    + str(result.get("error")),
                    file=sys.stderr,
                )

    return 0 if success else 1
