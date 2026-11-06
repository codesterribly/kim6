#!/usr/bin/env python3
"""Explicit pre-processing review for KIM6 Web Export."""

import os
import sys
import json
from pathlib import Path

from kim_psd_source import WARNING as PSD_WARNING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QPlainTextEdit,
    QFileDialog, QPushButton, QHBoxLayout,
)


def source_identity(path):
    info = os.stat(path, follow_symlinks=False)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError("Source is not a regular file")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


class WebExportReview(QDialog):
    def __init__(self, records, fmt, size, quality, color,
                 destination_request, destination):
        super().__init__()
        self.records = records
        self.destination_request = destination_request
        self.destination = destination
        self.identities = {}
        self.errors = {}
        self.source_notices = {}

        self.setWindowTitle("KIM6 — Review Web Export")
        visible_rows = min(len(records), 8)
        self.resize(
            1050,
            min(760, 370 + 34 * visible_rows)
        )
        self.setMinimumWidth(820)

        layout = QVBoxLayout(self)

        heading = QLabel(
            f"{len(records)} selected image(s)  |  "
            f"{fmt.upper()}  |  Maximum {size} px  |  Quality {quality}"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        color_text = (
            "Convert to sRGB" if color == "srgb"
            else "Preserve existing color interpretation"
        )
        policy = QLabel(
            f"Color policy: {color_text}. "
            "Source metadata is stripped. KIM6 may retain or install "
            "an ICC profile in the finished export. "
            "Original images are never modified."
        )
        policy.setWordWrap(True)
        layout.addWidget(policy)

        destination_row = QHBoxLayout()
        destination_text = (
            "Destination: " + destination
            if destination
            else "Destination: Beside each source"
        )

        if destination and not os.path.isdir(destination):
            destination_text += " (created after approval)"

        destination_label = QLabel(destination_text)
        destination_label.setWordWrap(True)
        destination_row.addWidget(destination_label, 1)

        change_button = QPushButton("Change Destination…")
        change_button.clicked.connect(self.change_destination)
        destination_row.addWidget(change_button)

        layout.addLayout(destination_row)

        self.table = QTableWidget(len(records), 6)
        self.table.setHorizontalHeaderLabels((
            "Before: Source image", "Original", "Planned size",
            "Output filename", "Destination", "Status"
        ))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        for col in (0, 3, 4):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(5, 64)

        for index, record in enumerate(records):
            source, source_fmt, original, planned, frames, target, issue, icc, notice_tags = record

            notices = []
            tags = set(filter(None, notice_tags.split(",")))

            if "psd" in tags:
                notices.append(PSD_WARNING)

            if "unprofiled" in tags:
                notices.append(
                    "Unprofiled RGB/grayscale source: KIM6 assumed "
                    "sRGB for color interpretation."
                )

            self.source_notices[source] = notices

            if not issue:
                try:
                    self.identities[source] = source_identity(source)
                except Exception as exc:
                    issue = str(exc)

            if issue:
                self.errors[source] = issue

            values = (
                Path(source).name,
                original,
                planned,
                Path(target).name if target else "Unavailable",
                str(Path(target).parent) if target else "",
                "Blocked" if issue else "Ready",
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    issue if issue else
                    source if column == 0 else
                    target if column in (3, 4) else
                    f"Input: {source_fmt}; ICC: {icc}"
                )
                self.table.setItem(index, column, item)

            self.table.setRowHeight(index, 32)

        # Include row headers, column header, frame and scrollbars.
        self.table.setFixedHeight(
            50 + 34 * visible_rows
        )
        layout.addWidget(self.table)

        # Display selected-source warnings immediately, without
        # another disclosure step or a second dialog.
        self.before_summary = QLabel()
        self.before_summary.setWordWrap(True)
        layout.addWidget(self.before_summary)

        self.notice_details = QPlainTextEdit()
        self.notice_details.setReadOnly(True)
        self.notice_details.setMaximumHeight(92)
        self.notice_details.setMinimumHeight(56)
        self.notice_details.setLineWrapMode(
            QPlainTextEdit.WidgetWidth
        )
        self.notice_details.hide()
        layout.addWidget(self.notice_details)

        self.table.itemSelectionChanged.connect(
            self.refresh_source_notices
        )

        if self.records:
            self.table.selectRow(0)

        self.refresh_source_notices()

        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        note = QLabel(
            "Dimensions are calculated without enlargement. "
            "Output names may be renumbered if a collision occurs."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.apply = buttons.button(QDialogButtonBox.Ok)
        self.apply.setText("Apply Changes")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_status()

    def change_destination(self):
        initial = (
            self.destination
            if os.path.isdir(self.destination)
            else os.path.dirname(self.records[0][0])
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose Web Export Destination",
            initial,
        )

        if not selected:
            return

        selected = os.path.realpath(selected)

        if not (
            os.path.isdir(selected)
            and os.access(selected, os.W_OK | os.X_OK)
        ):
            self.status.setText(
                "Selected destination is not accessible."
            )
            return

        try:
            Path(self.destination_request).write_bytes(
                os.fsencode(selected) + bytes([0])
            )
        except OSError as exc:
            self.status.setText(
                f"Could not save destination request: {exc}"
            )
            return

        # Return control to kim_all to rebuild the filename plan.
        self.reject()

    def refresh_source_notices(self):
        selection = self.table.selectionModel().selectedRows()

        if not selection:
            self.before_summary.setText(
                "Before: Select an image to inspect its source."
            )
            self.notice_details.hide()
            return

        index = selection[0].row()
        source = self.records[index][0]
        notices = self.source_notices.get(source, [])

        if notices:
            self.before_summary.setText(
                f"Before: {Path(source).name} | "
                f"{len(notices)} source warning(s)"
            )
            self.notice_details.setPlainText(
                source + "\n\n" + "\n\n".join(notices)
            )
            self.notice_details.show()
        else:
            self.before_summary.setText(
                f"Before: {Path(source).name} | "
                "No source warnings"
            )
            self.notice_details.clear()
            self.notice_details.hide()

    def refresh_status(self):
        blocked = len(self.errors)
        ready = len(self.records) - blocked
        self.apply.setEnabled(bool(self.records) and blocked == 0)
        self.status.setText(
            f"{ready} ready, {blocked} blocked. "
            "Select a row to inspect its details."
        )
        if blocked:
            self.status.setToolTip("\n".join(
                f"{Path(path).name}: {message}"
                for path, message in self.errors.items()
            ))

    def accept(self):
        for record in self.records:
            source = record[0]
            if source in self.errors:
                continue
            try:
                if source_identity(source) != self.identities[source]:
                    raise ValueError("Source changed since review opened")
            except Exception as exc:
                self.errors[source] = str(exc)

        self.refresh_status()
        if self.apply.isEnabled():
            super().accept()


def main():
    if len(sys.argv) != 9:
        return 125

    _, plan_file, fmt, size, quality, color, destination_request, destination, disclosed_path = sys.argv

    try:
        raw = Path(plan_file).read_bytes()
        if not raw or not raw.endswith(b"\0"):
            return 125

        parts = [
            os.fsdecode(part)
            for part in raw[:-1].split(b"\0")
        ]
        if len(parts) % 9:
            return 125

        records = [
            tuple(parts[index:index + 9])
            for index in range(0, len(parts), 9)
        ]
        if not records or any(not row[0] for row in records):
            return 125
    except (OSError, ValueError):
        return 125

    app = QApplication(sys.argv[:1])
    dialog = WebExportReview(
        records, fmt, size, quality, color,
        destination_request, destination
    )
    if dialog.exec() != QDialog.Accepted:
        return 130

    # Only approved, source-specific notices may be suppressed
    # from the later job-exit dialog. Never hide unknown categories.
    entries = []
    for record in records:
        source, *_, tags = record
        for category in filter(None, tags.split(",")):
            if category in ("psd", "unprofiled"):
                entries.append({
                    "source": os.path.realpath(source),
                    "category": category,
                })

    try:
        Path(disclosed_path).write_text(
            "".join(json.dumps(entry) + "\n"
                    for entry in entries)
        )
    except OSError:
        return 125

    return 0


if __name__ == "__main__":
    sys.exit(main())
