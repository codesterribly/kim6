#!/usr/bin/env python3
"""Standalone Crop review and execution interface."""
from kim_dialog_buttons import style_button, style_button_box

import copy
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QSettings
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
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kim_recipe_core import preview, execute, approve_rows, RecipeError
from kim_review_ui import restore_review_geometry, clamp_review_geometry


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
            import contextvars
            from concurrent.futures import ThreadPoolExecutor

            from kim_process import inspection_context, checkpoint
            from kim_recipe_core import (
                number_review_outputs,
                block_output_collisions,
            )

            with inspection_context(
                cancelled=self.isInterruptionRequested
            ):
                # One-image reviews retain the established code path.
                if len(self.files) <= 1:
                    self.rows = preview(
                        self.recipe,
                        self.files,
                        number_collisions=True,
                    )
                    return

                rows = [None] * len(self.files)

                def inspect_one(position, source):
                    checkpoint()
                    result = preview(
                        self.recipe,
                        [source],
                        start_index=position + 1,
                    )
                    checkpoint()

                    if len(result) != 1:
                        raise RecipeError(
                            "Crop inspection returned an invalid row count"
                        )

                    return position, result[0]

                # Each task receives its own contextvars context.
                # No mutable inspection context is shared between tasks.
                with ThreadPoolExecutor(
                    max_workers=min(3, len(self.files)),
                    thread_name_prefix="kimng-crop-review",
                ) as pool:
                    futures = []

                    for position, source in enumerate(self.files):
                        checkpoint()
                        context = contextvars.copy_context()
                        futures.append(
                            pool.submit(
                                context.run,
                                inspect_one,
                                position,
                                source,
                            )
                        )

                    for future in futures:
                        checkpoint()
                        position, row = future.result()
                        rows[position] = row

                checkpoint()

                if any(row is None for row in rows):
                    raise RecipeError(
                        "Crop review did not inspect every selected image"
                    )

                # Resolve numbering in original selection order.
                # The displayed filename becomes the approved filename.
                number_review_outputs(rows)

                # Retain existing duplicate-target safety checks.
                block_output_collisions(rows)

                self.rows = rows

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
        self.approved_plan = None
        self.review_rows = []

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

        self.table = QTableWidget(len(files), 5)
        self.table.setHorizontalHeaderLabels([
            "Image", "Original", "Planned", "Output", "Status",
        ])
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.settings = QSettings('KIMng', 'CropReview')
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(56)
        for column in range(5):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )

        self._setting_columns = False
        self._custom_columns = False
        widths = self.settings.value('column_widths')
        if isinstance(widths, list) and len(widths) == 5:
            try:
                widths = [max(56, min(1200, int(width))) for width in widths]
                self._custom_columns = True
                for column, width in enumerate(widths):
                    self.table.setColumnWidth(column, width)
            except (TypeError, ValueError):
                pass

        header.sectionResized.connect(self.column_resized)
        layout.addWidget(self.table, 1)
        self.output_label = QLabel("Output: ")
        self.output_label.setTextFormat(Qt.PlainText)
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.output_label.setWordWrap(True)
        self.output_label.setAccessibleName("Selected output filename")
        layout.addWidget(self.output_label)
        self.table.currentCellChanged.connect(self.show_selected_output)

        self.status = QLabel(
            "Checking selected images…"
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)

        self.details_button = QPushButton("Show details")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self.toggle_details)
        layout.addWidget(self.details_button)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(125)
        self.details.setVisible(False)
        layout.addWidget(self.details)

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
        restore_review_geometry(self, self.settings, (1050, min(650, 480 + 24 * max(1, len(files)))))
        self.finished.connect(self.save_display_preferences)

        QTimer.singleShot(0, self.recheck)

    def showEvent(self, event):
        super().showEvent(event)
        clamp_review_geometry(self)
        self.fit_default_columns()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_custom_columns'):
            QTimer.singleShot(0, self.fit_default_columns)

    def column_resized(self, *_):
        if not self._setting_columns:
            self._custom_columns = True

    def fit_default_columns(self):
        available = self.table.viewport().width()
        if available <= 0:
            return
        if not self._custom_columns:
            # Give the source and output names equal room, with compact
            # dimensions and status columns. The proportions use the actual
            # viewport so the default never needs horizontal scrolling.
            widths = [int(available * ratio) for ratio in (.30, .15, .15, .30, .10)]
            widths[0] += available - sum(widths)
        else:
            widths = [self.table.columnWidth(i) for i in range(5)]
            total = sum(widths)
            if total > available:
                scale = available / total
                widths = [max(56, int(width * scale)) for width in widths]
                widths[0] += max(0, available - sum(widths))
        self._setting_columns = True
        try:
            for column, width in enumerate(widths):
                self.table.setColumnWidth(column, width)
        finally:
            self._setting_columns = False

    def save_display_preferences(self, *_):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('column_widths', [self.table.columnWidth(i) for i in range(5)])

    def show_selected_output(self, *_):
        index = self.table.currentRow()
        row = self.review_rows[index] if 0 <= index < len(self.review_rows) else None
        output = Path(row.output) if row and row.output else None
        filename = output.name if output else ""
        self.output_label.setText("Output: " + filename)
        self.output_label.setToolTip(filename)
        self.refresh_destination()

    def toggle_details(self):
        visible = not self.details.isVisible()
        self.details.setVisible(visible)
        self.details_button.setText("Hide details" if visible else "Show details")

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

        text = "Destination: " + label
        index = self.table.currentRow() if hasattr(self, "table") else -1
        row = self.review_rows[index] if 0 <= index < len(self.review_rows) else None
        if row and row.output and dest["mode"] != "directory":
            text += "\nSelected image destination: " + str(Path(row.output).parent)
        self.destination.setText(text)

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
                or (folder.exists() and not folder.is_dir())
                or (not folder.exists() and not folder.parent.is_dir())
            ):
                self.status.setText(
                    "Choose an absolute destination directory whose parent exists."
                )
                self.apply_button.setEnabled(False)
                return
            self.recipe["destination"] = {
                "mode": "directory",
                "path": str(folder.resolve(strict=False)),
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
        self.approved_plan = None
        self.review_rows = []
        self.show_selected_output()
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

        self.review_rows = worker.rows
        diagnostic_lines = []
        existing_count = 0
        duplicate_count = 0
        validation_count = 0
        ready_count = 0

        for index, (source, row) in enumerate(
            zip(self.files, worker.rows)
        ):
            errors = list(row.problems)

            if not errors and not row.output:
                errors.append(
                    "No planned output"
                )

            if errors:
                planned = row.output or "Blocked"
                text = "; ".join(errors)
                diagnostic_lines.append(f"{Path(source).name}: {text}")
                if any("already exists" in issue.lower() for issue in errors):
                    existing_count += 1
                if any("multiple selected sources" in issue.lower() for issue in errors):
                    duplicate_count += 1
                if not any("output collision:" in issue.lower() for issue in errors):
                    validation_count += 1

            else:
                planned = row.output
                ready_count += 1

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

        if self.files and self.table.currentRow() < 0:
            self.table.setCurrentCell(0, 3)
        self.show_selected_output()

        if len(worker.rows) != len(self.files):
            diagnostic_lines.append("Review: Not all selected images were inspected.")

        blocked_count = len(self.files) - ready_count
        selected_count = len(self.files)
        summary = (
            f"{selected_count} image{'s' if selected_count != 1 else ''} selected, "
            f"{ready_count} ready, {blocked_count} blocked."
        )
        explanations = []
        if existing_count:
            explanations.append(
                f"{existing_count} planned output{'s' if existing_count != 1 else ''} "
                f"already {'exist' if existing_count != 1 else 'exists'}."
            )
        if duplicate_count:
            explanations.append(
                f"{duplicate_count} image{'s' if duplicate_count != 1 else ''} "
                f"{'share' if duplicate_count != 1 else 'shares'} a planned output path."
            )
        if validation_count:
            explanations.append(
                f"{validation_count} image{'s' if validation_count != 1 else ''} "
                f"{'have' if validation_count != 1 else 'has'} other validation problems."
            )
        if explanations:
            summary += "\n" + "\n".join(explanations)
            summary += "\nChoose a different destination or change the selected images, then review again."
        if any(
            Path(source).suffix.lower() in (".jpg", ".jpeg")
            for source in self.files
        ):
            summary += (
                "\nMetadata notice: JPEG metadata will be preserved "
                "where possible. If source metadata is malformed, "
                "KIMng may omit it from a cropped copy. "
                "Original images remain unchanged."
            )

        self.status.setText(summary)
        self.details.setPlainText("\n".join(diagnostic_lines))
        self.details_button.setVisible(bool(diagnostic_lines))
        self.details_button.setText(f"Show details ({len(diagnostic_lines)})")
        self.details.setVisible(False)

        self.apply_button.setEnabled(
            not diagnostic_lines and bool(self.files)
        )

        worker.deleteLater()

    def approve(self):
        if (
            self.worker is not None
            or not self.apply_button.isEnabled()
        ):
            return

        try:
            self.approved_plan = approve_rows(self.recipe, self.files, self.review_rows)
        except (OSError, RecipeError) as exc:
            self.status.setText(str(exc))
            self.apply_button.setEnabled(False)
            return
        self.approved = copy.deepcopy(self.recipe)
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
            self.save_display_preferences()
            event.accept()


class CropExecution(QThread):
    """Process the approved batch without a Recipe UI."""

    started_file = Signal(str, int)
    finished_file = Signal(dict, int)
    stage_changed = Signal(str)

    def __init__(self, recipe, files, approved_plan=None):
        super().__init__()

        self.recipe = copy.deepcopy(recipe)
        self.approved_plan = approved_plan
        self.files = list(files)
        self.results = []
        self.error = ""
        self.cancelled = False

    def run(self):
        try:
            from kim_process import inspection_context
            from kim_recipe_image import standalone_crop_metadata_fallback
            if self.approved_plan is None:
                raise RecipeError('Missing approved publication plan; review again')
            def completed(result, index, total):
                self.results.append(result)
                self.finished_file.emit(result, index)
            with inspection_context(
                progress=self.stage_changed.emit,
                cancelled=self.isInterruptionRequested
            ), standalone_crop_metadata_fallback():
                execute(self.recipe, self.files, progress=completed,
                        approved_plan=self.approved_plan,
                        started=self.started_file.emit, stop_on_error=True)
            self.cancelled = self.isInterruptionRequested() or any(r.get('cancelled') for r in self.results)

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
            "KIMng - Crop - Progress"
        )
        self.resize(640, 175)

        layout = QVBoxLayout(self)

        self.label = QLabel(
            f"Cropping {total} images…"
        )
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.label)

        self.stage_label = QLabel("Preparing image…")
        self.stage_label.setWordWrap(True)
        self.stage_label.setTextFormat(Qt.PlainText)
        self.stage_label.setAccessibleName("Current processing stage")
        layout.addWidget(self.stage_label)

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
        worker.stage_changed.connect(self.stage_changed)
        worker.finished.connect(
            self.execution_finished
        )

        QTimer.singleShot(
            0, worker.start
        )

    def stage_changed(self, message):
        if not self.completed:
            self.stage_label.setText(str(message))

    def file_started(self, source, index):
        self.stage_label.setText("Preparing image…")
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
        self.stage_label.setText("Cancellation requested")
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
        approved_plan=review.approved_plan,
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

    from PySide6.QtWidgets import QMessageBox

    succeeded = [
        result for result in worker.results
        if result.get("ok")
    ]
    failures = [
        result for result in worker.results
        if not result.get("ok")
    ]
    if not success and not worker.cancelled:
        details = [
            Path(str(result.get("source", ""))).name + ": "
            + str(result.get("error", "Unknown error"))
            for result in failures
        ]

        if worker.error:
            details.insert(0, worker.error)

        QMessageBox.critical(
            None,
            "KIMng - Crop - Failed",
            f"{len(succeeded)} of {len(files)} images created.\\n"
            "Original images were not overwritten.\\n\\n"
            + "\\n\\n".join(
                details or ["Processing stopped unexpectedly."]
            )
        )

    return 0 if success else 1
