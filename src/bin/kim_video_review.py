#!/usr/bin/env python3
"""Explicit review for KIM6 video transcode presets and output destination."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def source_identity(path):
    info = os.stat(path, follow_symlinks=False)
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError("Source is not a regular, independent file")
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
    )


class VideoReview(QDialog):
    def __init__(self, plan, codec, limit, quality, mode, request_path, destination):
        super().__init__()

        self.setWindowTitle("KIM6 - Review video conversion")
        self.resize(1060, min(760, 300 + 52 * len(plan)))
        self.setMinimumWidth(850)

        self.plan = plan
        self.request_path = Path(request_path)
        self.identities = {}
        self.errors = {}

        outer = QVBoxLayout(self)

        codec_name = {
            "libx264": "H.264",
            "libx265": "H.265",
            "av1": "AV1",
        }.get(codec, codec)

        heading = QLabel(
            f"{len(plan)} selected video(s) | "
            f"{codec_name} | Maximum {limit} | {quality}"
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        audio_note = QLabel(
            "KIM6 transcodes the first video stream and copies "
            "available audio streams without re-encoding them. "
            "Aspect ratio is preserved. Smaller videos are not enlarged."
        )
        audio_note.setWordWrap(True)
        outer.addWidget(audio_note)

        if mode == "overwrite":
            policy = (
                "Output policy: Replace originals. "
                "The selected source files will be replaced only after "
                "successful encoding and output validation."
            )
        else:
            policy = (
                "Output policy: Create new files. "
                "Original videos will remain unchanged."
            )

        policy_label = QLabel(policy)
        policy_label.setWordWrap(True)
        outer.addWidget(policy_label)

        destination_row = QHBoxLayout()
        destination_label = QLabel(
            "Destination: Replace each original in place" if mode == "overwrite"
            else "Destination: " + (destination or "Beside each source")
        )
        destination_label.setWordWrap(True)
        destination_row.addWidget(destination_label, 1)
        if mode != "overwrite":
            choose_button = QPushButton("Change destination…")
            choose_button.clicked.connect(lambda: self.choose_destination(destination))
            destination_row.addWidget(choose_button)
            if destination:
                reset_button = QPushButton("Beside each source")
                reset_button.clicked.connect(lambda: self.request_destination(""))
                destination_row.addWidget(reset_button)
        outer.addLayout(destination_row)

        self.table = QTableWidget(len(plan), 6)
        self.table.setHorizontalHeaderLabels((
            "Source video",
            "Original size",
            "Duration",
            "Audio",
            "Planned filename",
            "Destination",
        ))
        self.table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        for column in range(6):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )

        for column in (0, 4, 5):
            header.setSectionResizeMode(
                column, QHeaderView.Stretch
            )

        for column in (1, 2, 3):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )

        for number, record in enumerate(plan):
            source, dimensions, duration, audio, target, muxer = record

            filename = os.path.basename(source)
            destination = os.path.dirname(target)
            output_name = os.path.basename(target)

            try:
                self.identities[source] = source_identity(source)
            except Exception as exc:
                self.errors[source] = str(exc)

            try:
                seconds = float(duration)
                duration_text = (
                    f"{int(seconds // 3600):02d}:"
                    f"{int(seconds // 60) % 60:02d}:"
                    f"{seconds % 60:05.2f}"
                )
            except ValueError:
                duration_text = duration

            try:
                audio_count = int(audio)
            except ValueError:
                audio_count = 0

            audio_text = (
                f"{audio_count} copied"
                if audio_count
                else "No audio"
            )

            values = (
                filename,
                dimensions,
                duration_text,
                audio_text,
                output_name,
                destination,
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    source if column == 0
                    else target if column in (4, 5)
                    else value
                )
                self.table.setItem(number, column, item)

            self.table.setRowHeight(number, 34)

        outer.addWidget(self.table, 1)

        note = QLabel(
            "Planned output names reflect current settings and "
            "filesystem state. If a new filename collision occurs, "
            "KIM6 may add a number during safe publication. "
            "No video has been modified."
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        self.status = QLabel()
        outer.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.apply = buttons.button(QDialogButtonBox.Ok)
        self.apply.setText("Apply changes")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer.addWidget(buttons)

        self.refresh_status()

    def request_destination(self, directory):
        try:
            self.request_path.write_bytes(os.fsencode(directory) + b"\0")
        except OSError as exc:
            QMessageBox.critical(self, "Cannot change destination", str(exc))
            return
        self.reject()  # Exit 130 with a request file to trigger a fresh preflight.

    def choose_destination(self, current_directory):
        start = current_directory or os.path.dirname(self.plan[0][0])
        selected = QFileDialog.getExistingDirectory(
            self, "Choose output directory", start
        )
        if selected:
            self.request_destination(selected)

    def refresh_status(self):
        blocked = len(self.errors)
        ready = len(self.plan) - blocked

        self.status.setText(
            f"{ready} ready, {blocked} blocked. "
            "Review the planned conversion before applying."
        )

        if blocked:
            details = "\n".join(
                f"{os.path.basename(path)}: {reason}"
                for path, reason in self.errors.items()
            )
            self.status.setToolTip(details)

        self.apply.setEnabled(
            bool(self.plan) and not blocked
        )

    def accept(self):
        for record in self.plan:
            source = record[0]

            if source in self.errors:
                continue

            try:
                current = source_identity(source)

                if current != self.identities[source]:
                    raise ValueError(
                        "Source changed since review opened"
                    )

            except Exception as exc:
                self.errors[source] = str(exc)

        self.refresh_status()

        if self.apply.isEnabled():
            super().accept()


def main():
    if len(sys.argv) != 8:
        return 125

    _, plan_file, codec, limit, quality, mode, request_file, destination = sys.argv

    if mode not in ("create", "overwrite"):
        return 125

    try:
        raw = Path(plan_file).read_bytes()

        if not raw.endswith(b"\0"):
            return 125

        parts = [
            os.fsdecode(part)
            for part in raw[:-1].split(b"\0")
        ]

        if not parts or len(parts) % 6:
            return 125

        records = [
            tuple(parts[index:index + 6])
            for index in range(0, len(parts), 6)
        ]

        if any(not row[0] or not row[4] for row in records):
            return 125

    except (OSError, ValueError):
        return 125

    app = QApplication(sys.argv[:1])

    review = VideoReview(
        records, codec, limit, quality, mode, request_file, destination
    )

    return (
        0 if review.exec() == QDialog.Accepted
        else 130
    )


if __name__ == "__main__":
    sys.exit(main())
