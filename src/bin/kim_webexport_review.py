#!/usr/bin/env python3
"""Explicit pre-processing review for KIMng Web Export."""

import os
import sys
import json
from pathlib import Path

from kim_psd_source import WARNING as PSD_WARNING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHeaderView,
    QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QPlainTextEdit, QLineEdit,
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

        self.setWindowTitle("KIMng - Web Export - Review Changes")
        visible_rows = min(len(records), 8)
        self.resize(
            1050,
            min(760, 325 + 34 * visible_rows)
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
            "Source metadata is stripped. KIMng may retain or install "
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

        destination_input_row = QHBoxLayout()

        self.destination_entry = QLineEdit()
        self.destination_entry.setPlaceholderText(
            "Beside each source (leave empty)"
        )
        self.destination_entry.setAccessibleName(
            "Shared destination directory"
        )
        self.destination_entry.setText(destination)
        self.destination_entry.textChanged.connect(
            lambda _: self.apply.setEnabled(False)
        )
        self.destination_entry.editingFinished.connect(
            self.submit_destination
        )
        destination_input_row.addWidget(self.destination_entry, 1)

        change_button = QPushButton("Change destination…")
        change_button.clicked.connect(self.change_destination)
        destination_input_row.addWidget(change_button)

        self.table = QTableWidget(len(records), 6)
        self.table.setHorizontalHeaderLabels((
            "Source image", "Original", "Planned",
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
                    "Unprofiled RGB/grayscale source: KIMng assumed "
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

        layout.addLayout(destination_row)
        layout.addLayout(destination_input_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.apply = buttons.button(QDialogButtonBox.Ok)
        self.apply.setText("Apply changes")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.refresh_status()

    def submit_destination(self):
        proposed = self.destination_entry.text().strip()

        if proposed == self.destination:
            self.refresh_status()
            return

        if proposed:
            if (
                not os.path.isabs(proposed)
                or os.path.islink(proposed)
                or not os.path.isdir(proposed)
                or not os.access(proposed, os.W_OK | os.X_OK)
            ):
                self.status.setText(
                    "Invalid shared destination. Choose an existing "
                    "writable directory."
                )
                self.apply.setEnabled(False)
                return

            proposed = os.path.realpath(proposed)

        try:
            Path(self.destination_request).write_bytes(
                os.fsencode(proposed) + bytes([0])
            )
        except OSError as exc:
            self.status.setText(
                f"Could not save destination request: {exc}"
            )
            self.apply.setEnabled(False)
            return

        # The caller rebuilds the exact filenames and destinations
        # before allowing approval. Never apply a stale plan.
        self.reject()

    def change_destination(self):
        initial = (
            self.destination_entry.text().strip()
            if os.path.isdir(self.destination_entry.text().strip())
            else (
                self.destination
                if os.path.isdir(self.destination)
                else os.path.dirname(self.records[0][0])
            )
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose Web Export destination",
            initial,
        )

        if selected:
            self.destination_entry.setText(selected)
            self.submit_destination()

    def refresh_source_notices(self):
        selection = self.table.selectionModel().selectedRows()

        if not selection:
            self.before_summary.hide()
            self.notice_details.hide()
            return

        index = selection[0].row()
        source = self.records[index][0]
        notices = self.source_notices.get(source, [])

        if notices:
            self.before_summary.setText(
                f"Source warnings ({len(notices)})"
            )
            self.before_summary.show()
            self.notice_details.setPlainText(
                "\n\n".join(notices)
            )
            self.notice_details.show()
        else:
            self.before_summary.clear()
            self.before_summary.hide()
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
