#!/usr/bin/env python3
"""Standalone Crop review and execution interface."""

import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
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

        self.setWindowTitle("KIMng - Review changes")
        self.resize(880, 520)

        layout = QVBoxLayout(self)

        heading = QLabel(
            f"Crop {len(files)} selected images"
        )
        layout.addWidget(heading)

        destination_row = QHBoxLayout()

        self.destination = QLabel()
        self.destination.setTextFormat(Qt.PlainText)
        self.destination.setWordWrap(True)
        destination_row.addWidget(self.destination, 1)

        self.destination_button = QPushButton(
            "Change destination…"
        )
        self.destination_button.clicked.connect(
            self.change_destination
        )
        destination_row.addWidget(
            self.destination_button
        )
        layout.addLayout(destination_row)

        self.table = QTableWidget(len(files), 3)
        self.table.setHorizontalHeaderLabels([
            "Image",
            "Planned output",
            "Dimensions",
        ])
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )

        layout.addWidget(self.table, 1)

        self.status = QLabel(
            "Checking selected images…"
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Cancel
        )
        self.apply_button = self.buttons.addButton(
            "Apply changes",
            QDialogButtonBox.AcceptRole,
        )
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(
            self.approve
        )
        self.buttons.rejected.connect(
            self.reject
        )
        layout.addWidget(self.buttons)

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

        self.refresh_destination()
        self.recheck()

    def recheck(self):
        if self.worker is not None or self.closing:
            return

        self.apply_button.setEnabled(False)
        self.destination_button.setEnabled(False)

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

            for column, value in enumerate((
                Path(source).name,
                planned,
                dimensions,
            )):
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
            self.status.setText(
                f"All {len(self.files)} images are ready. "
                "Original images will not be overwritten."
            )

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

    if (
        review.exec() != QDialog.Accepted
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
