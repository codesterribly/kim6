#!/usr/bin/env python3
"""KIM6 single-window settings for video contact sheets and GIFs."""

import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)


def mute_review(plan_path, request_path, destination):
    """Mandatory Remove Audio review with shared destination selection."""
    import os

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )

    payload = plan_path.read_bytes()

    if not payload.endswith(b"\0"):
        raise ValueError("Incomplete mute review plan")

    parts = payload[:-1].split(b"\0")

    if not parts or len(parts) % 6:
        raise ValueError("Invalid mute review plan")

    records = [
        [os.fsdecode(value) for value in parts[i:i + 6]]
        for i in range(0, len(parts), 6)
    ]

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Review Remove Audio")

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    layout.addWidget(QLabel(
        f"{len(records)} selected video(s) | "
        "Remove all audio streams | Copy video without re-encoding"
    ))

    destination_row = QHBoxLayout()
    destination_row.setSpacing(8)

    destination_row.addWidget(QLabel(
        "Destination: " + (
            destination if destination else "Beside each source"
        )
    ), 1)

    choose_button = QPushButton("Change Destination…")
    destination_row.addWidget(choose_button)

    reset_button = QPushButton("Beside each source")
    reset_button.setVisible(bool(destination))
    destination_row.addWidget(reset_button)

    layout.addLayout(destination_row)

    table = QTableWidget(len(records), 6)
    table.setHorizontalHeaderLabels([
        "Before: Source video",
        "Video codec",
        "Audio streams",
        "Output filename",
        "Destination",
        "Status",
    ])
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.Interactive
    )

    for col, width in enumerate(
        (235, 105, 105, 220, 265, 80)
    ):
        table.setColumnWidth(col, width)

    for row, record in enumerate(records):
        source, codec, audio, target, status, detail = record
        values = (
            os.path.basename(source),
            codec or "Unknown",
            audio,
            os.path.basename(target) if target else "None",
            os.path.dirname(target) if target else "None",
            status,
        )

        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(
                source if col == 0
                else target if col in (3, 4)
                else detail
            )
            if col == 2:
                item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, col, item)

    visible_rows = min(len(records), 8)
    table.setFixedHeight(48 + 31 * visible_rows)
    layout.addWidget(table)

    details = QLabel()
    details.setWordWrap(True)
    details.setMinimumHeight(38)
    layout.addWidget(details)

    def update_details():
        row = table.currentRow()
        if row >= 0:
            source, _, _, _, status, message = records[row]
            details.setText(f"{source}\n{status}: {message}")

    table.itemSelectionChanged.connect(update_details)
    table.selectRow(0)
    update_details()

    ready = sum(row[4] == "Ready" for row in records)
    blocked = sum(row[4] == "Blocked" for row in records)
    skipped = len(records) - ready - blocked

    summary = QLabel(
        f"{ready} ready, {blocked} blocked, {skipped} skipped. "
        "Original videos are never modified. "
        "Output filenames may be renumbered if collisions occur."
    )
    summary.setWordWrap(True)
    layout.addWidget(summary)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )

    apply_button = buttons.button(QDialogButtonBox.Ok)
    apply_button.setText("Apply Changes")
    apply_button.setEnabled(ready > 0 and blocked == 0)

    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def request_change(new_directory):
        try:
            request_path.write_bytes(
                os.fsencode(new_directory) + b"\0"
            )
        except OSError as error:
            QMessageBox.critical(
                dialog, "Cannot change destination", str(error)
            )
            return
        dialog.reject()

    def choose_directory():
        initial = destination or os.path.dirname(records[0][0])
        selected = QFileDialog.getExistingDirectory(
            dialog, "Choose output directory", initial
        )
        if selected:
            request_change(selected)

    choose_button.clicked.connect(choose_directory)
    reset_button.clicked.connect(lambda: request_change(""))

    dialog.resize(
        1080,
        min(720, 240 + 31 * visible_rows)
    )

    return 0 if dialog.exec() == QDialog.Accepted else 130



def frame_review(plan_path, request_path, destination):
    """Mandatory review for frame, thumbnail and contact-sheet extraction."""
    import os

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )

    payload = plan_path.read_bytes()

    if not payload.endswith(b"\0"):
        raise ValueError("Incomplete video frame review plan")

    parts = payload[:-1].split(b"\0")

    if not parts or len(parts) % 8:
        raise ValueError("Invalid video frame review plan")

    records = [
        [os.fsdecode(v) for v in parts[i:i + 8]]
        for i in range(0, len(parts), 8)
    ]

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Review Video Frames")

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    mode = records[0][7]
    names = {
        "single": "Extract frame at timestamp",
        "thumbnail": "Extract automatic thumbnail",
        "contact": "Create video contact sheet",
    }

    layout.addWidget(QLabel(
        f"{len(records)} selected video(s) | "
        f"{names.get(mode, 'Extract video frames')}"
    ))

    destination_row = QHBoxLayout()
    destination_row.setSpacing(8)

    destination_row.addWidget(QLabel(
        "Destination: " + (
            destination if destination else "Beside each source"
        )
    ), 1)

    choose_button = QPushButton("Change Destination…")
    destination_row.addWidget(choose_button)

    reset_button = QPushButton("Beside each source")
    reset_button.setVisible(bool(destination))
    destination_row.addWidget(reset_button)

    layout.addLayout(destination_row)

    table = QTableWidget(len(records), 7)
    table.setHorizontalHeaderLabels([
        "Before: Source video",
        "Frame time",
        "Planned size",
        "Format",
        "Output filename",
        "Destination",
        "Status",
    ])
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)

    for col, width in enumerate(
        (215, 125, 115, 70, 225, 225, 85)
    ):
        table.setColumnWidth(col, width)

    for row, record in enumerate(records):
        source, when, size, fmt, target, status, detail, _ = record

        values = (
            os.path.basename(source),
            when or "Unavailable",
            size or "Unknown",
            fmt.upper(),
            os.path.basename(target) if target else "None",
            os.path.dirname(target) if target else "None",
            status,
        )

        for col, value in enumerate(values):
            item = QTableWidgetItem(value)

            item.setToolTip(
                source if col == 0
                else target if col in (4, 5)
                else detail
            )

            table.setItem(row, col, item)

    visible_rows = min(len(records), 8)
    table.setFixedHeight(48 + 31 * visible_rows)
    layout.addWidget(table)

    details = QLabel()
    details.setWordWrap(True)
    details.setMinimumHeight(38)
    layout.addWidget(details)

    def update_details():
        row = table.currentRow()
        if row >= 0:
            source, when, _, _, _, status, detail, _ = records[row]
            details.setText(
                f"{source}\n{status}: {detail} "
                f"Frame selection: {when}."
            )

    table.itemSelectionChanged.connect(update_details)
    table.selectRow(0)
    update_details()

    ready = sum(r[5] == "Ready" for r in records)
    blocked = len(records) - ready

    summary = QLabel(
        f"{ready} ready, {blocked} blocked. "
        "Original videos are never modified. "
        "Output filenames may be renumbered if collisions occur."
    )
    summary.setWordWrap(True)
    layout.addWidget(summary)

    if mode == "single":
        note = QLabel(
            "Frame seeking uses the requested timestamp; "
            "the decoded frame may fall slightly after that point."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )

    apply_button = buttons.button(QDialogButtonBox.Ok)
    apply_button.setText("Apply Changes")
    apply_button.setEnabled(ready > 0 and blocked == 0)

    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def request_change(new_directory):
        try:
            request_path.write_bytes(
                os.fsencode(new_directory) + b"\0"
            )
        except OSError as error:
            QMessageBox.critical(
                dialog, "Cannot change destination", str(error)
            )
            return
        dialog.reject()

    def choose_directory():
        initial = destination or os.path.dirname(records[0][0])
        selected = QFileDialog.getExistingDirectory(
            dialog, "Choose output directory", initial
        )
        if selected:
            request_change(selected)

    choose_button.clicked.connect(choose_directory)
    reset_button.clicked.connect(lambda: request_change(""))

    dialog.resize(
        1130,
        min(750, 260 + 31 * visible_rows)
    )

    return 0 if dialog.exec() == QDialog.Accepted else 130


def frame_options(output_path, mode, initial_at, initial_format, sources):
    """Per-video timestamps with a shared output format."""
    import os
    import re

    from PySide6.QtWidgets import (
        QApplication,
        QAbstractItemView,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    if mode not in ("single", "thumbnail") or not sources:
        raise ValueError("Invalid frame options")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle(
        "KIM6 — Extract Frame Options"
        if mode == "single"
        else "KIM6 — Thumbnail Options"
    )

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)

    count = len(sources)

    heading = QLabel(
        f"{count} selected video(s) | "
        + (
            "Extract frame at timestamp"
            if mode == "single"
            else "Extract automatic thumbnail"
        )
    )
    layout.addWidget(heading)

    editors = []

    if mode == "single":
        bulk_row = QHBoxLayout()
        bulk_row.setSpacing(8)

        bulk_row.addWidget(QLabel("Set all timestamps to:"))

        bulk_time = QLineEdit(initial_at or "00:00:01")
        bulk_time.setPlaceholderText("HH:MM:SS[.sss]")
        bulk_row.addWidget(bulk_time, 1)

        apply_all = QPushButton("Apply to All")
        bulk_row.addWidget(apply_all)

        layout.addLayout(bulk_row)

        table = QTableWidget(count, 2)
        table.setHorizontalHeaderLabels([
            "Source video",
            "Extract at",
        ])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setColumnWidth(0, 330)
        table.setColumnWidth(1, 180)

        for index, source in enumerate(sources):
            item = QTableWidgetItem(os.path.basename(source))
            item.setToolTip(source)
            table.setItem(index, 0, item)

            editor = QLineEdit(initial_at or "00:00:01")
            editor.setPlaceholderText("HH:MM:SS[.sss]")
            table.setCellWidget(index, 1, editor)
            editors.append(editor)

        table.setFixedHeight(
            48 + 33 * min(count, 8)
        )
        layout.addWidget(table)

        def apply_timestamp_to_all():
            value = bulk_time.text().strip()
            for editor in editors:
                editor.setText(value)

        apply_all.clicked.connect(apply_timestamp_to_all)

    else:
        note = QLabel(
            "KIM6 automatically selects the midpoint "
            "of each video."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

    format_row = QHBoxLayout()
    format_row.addWidget(QLabel("Output format:"))

    output_format = QComboBox()
    output_format.addItem("PNG (lossless)", "png")
    output_format.addItem("JPEG", "jpg")
    index = output_format.findData(initial_format)
    output_format.setCurrentIndex(index if index >= 0 else 0)

    format_row.addWidget(output_format, 1)
    layout.addLayout(format_row)

    note = QLabel(
        "Original videos are never modified. "
        "Each timestamp and output destination "
        "will be checked before extraction."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    buttons.button(
        QDialogButtonBox.Ok
    ).setText("Continue to Review")

    pattern = (
        r"[0-9]{2,}:[0-5][0-9]:"
        r"[0-5][0-9](?:\.[0-9]{1,3})?"
    )

    def accept_options():
        times = []

        if mode == "single":
            for row, editor in enumerate(editors):
                value = editor.text().strip()

                if re.fullmatch(pattern, value) is None:
                    QMessageBox.warning(
                        dialog,
                        "Invalid timestamp",
                        "Enter HH:MM:SS or HH:MM:SS.sss "
                        f"for {os.path.basename(sources[row])}."
                    )
                    editor.setFocus()
                    editor.selectAll()
                    return

                times.append(value)

        selected_format = output_format.currentData()

        if selected_format not in ("png", "jpg"):
            return

        # Shared format, followed by one timestamp per source.
        fields = [
            initial_at if mode == "thumbnail" else (
                times[0] if times else initial_at
            ),
            selected_format,
        ] + times

        payload = b"".join(
            os.fsencode(value) + b"\0"
            for value in fields
        )

        try:
            output_path.write_bytes(payload)
        except OSError as error:
            QMessageBox.critical(
                dialog,
                "Cannot save frame options",
                str(error)
            )
            return

        dialog.accept()

    buttons.accepted.connect(accept_options)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.resize(
        570 if mode == "single" else 480,
        min(740, 225 + (33 * min(count, 8) if mode == "single" else 0))
    )

    return 0 if dialog.exec() == QDialog.Accepted else 130



def main():
    if (
        len(sys.argv) >= 8
        and sys.argv[1] == "frame-options"
        and sys.argv[6] == "--"
    ):
        return frame_options(
            Path(sys.argv[2]),
            sys.argv[3],
            sys.argv[4],
            sys.argv[5],
            sys.argv[7:],
        )
    if len(sys.argv) == 5 and sys.argv[1] == "frame-review":
        return frame_review(
            Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
        )
    if len(sys.argv) == 5 and sys.argv[1] == "mute-review":
        return mute_review(
            Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
        )
    if len(sys.argv) < 4:
        return 2

    mode = sys.argv[1]
    destination = Path(sys.argv[2])
    defaults = sys.argv[3:]

    if mode not in ("contact", "gif"):
        return 2

    if mode == 'contact' and len(defaults) != 2:
        return 2
    if mode == 'gif' and len(defaults) < 5:
        return 2
    selected_videos = defaults[5:] if mode == 'gif' else []

    app = QApplication(sys.argv)
    dialog = QDialog()
    dialog.setMinimumWidth(440)

    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    layout.addLayout(form)

    def choice(label, options, default):
        widget = QComboBox()

        for caption, value in options:
            widget.addItem(caption, value)

        index = widget.findData(default)
        if index < 0:
            raise ValueError(f"Unsupported default for {label}")

        widget.setCurrentIndex(index)
        form.addRow(label, widget)
        return widget

    if mode == "contact":
        dialog.setWindowTitle("KIM6 — Video Contact Sheet")

        grid = choice("Grid:", [
            ("3 × 3 (9 frames)", "3x3"),
            ("4 × 4 (16 frames)", "4x4"),
            ("5 × 5 (25 frames)", "5x5"),
        ], defaults[0])

        image_format = choice("Image format:", [
            ("JPEG", "jpg"),
            ("PNG", "png"),
        ], defaults[1])

        layout.addWidget(QLabel(
            "Frames are sampled evenly across each selected video."
        ))

    else:
        dialog.setWindowTitle("KIM6 — Animated GIF")

        start = QLineEdit(defaults[0])
        start.setPlaceholderText("00:00:00")
        form.addRow("Start time:", start)

        duration = QDoubleSpinBox()
        duration.setRange(0.001, 15.0)
        duration.setDecimals(3)
        duration.setSingleStep(0.5)
        duration.setValue(float(defaults[1]))
        duration.setSuffix(" seconds")
        form.addRow("Duration:", duration)

        fps = choice("Frame rate:", [
            ("10 FPS", "10"),
            ("12 FPS", "12"),
            ("15 FPS", "15"),
            ("24 FPS", "24"),
        ], defaults[2])

        width = choice("Maximum width:", [
            ("320 px", "320"),
            ("480 px", "480"),
            ("640 px", "640"),
            ("800 px", "800"),
        ], defaults[3])

        loop = choice("Loop:", [
            ("Repeat forever", "infinite"),
            ("Play once", "once"),
        ], defaults[4])

        selection = QLabel(
            f'{len(selected_videos)} selected video(s): '
            + ', '.join(
                Path(path).name
                for path in selected_videos[:3]
            )
            + (' …' if len(selected_videos) > 3 else '')
            if selected_videos else 'Selected video(s)'
        )
        selection.setWordWrap(True)
        layout.addWidget(selection)

        estimate = QLabel()
        estimate.setWordWrap(True)
        layout.addWidget(estimate)

        layout.addWidget(QLabel(
            'Maximum duration: 15 seconds. '
            'Maximum frames: 360.'
        ))

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    buttons.button(QDialogButtonBox.Ok).setText("Create")
    layout.addWidget(buttons)

    if mode == 'gif':
        def update_estimate(*_):
            count = int(
                duration.value() * int(fps.currentData())
            )
            estimate.setText(
                f'Estimated output: about {count} frames '
                f'per video, maximum width '
                f'{width.currentData()} px. '
                'Actual frame count depends on source '
                'timestamps.'
                + (
                    ' Reduce duration or FPS '
                    '(360-frame limit).'
                    if count > 360 else ''
                )
            )
            buttons.button(
                QDialogButtonBox.Ok
            ).setEnabled(count <= 360)

        duration.valueChanged.connect(update_estimate)
        fps.currentIndexChanged.connect(update_estimate)
        width.currentIndexChanged.connect(update_estimate)
        update_estimate()

    def accept():
        if mode == "contact":
            values = [
                grid.currentData(),
                image_format.currentData(),
            ]

        else:
            timestamp = start.text().strip()

            if not re.fullmatch(
                r"[0-9]{2,}:[0-5][0-9]:[0-5][0-9]"
                r"([.][0-9]{1,3})?",
                timestamp,
            ):
                QMessageBox.warning(
                    dialog,
                    "Invalid start time",
                    "Use HH:MM:SS or HH:MM:SS.sss.",
                )
                return

            seconds = duration.value()
            rate = int(fps.currentData())

            if seconds * rate > 360:
                QMessageBox.warning(
                    dialog,
                    "Too many frames",
                    "Shorten the duration or lower the frame rate.",
                )
                return

            values = [
                timestamp,
                f"{seconds:g}",
                fps.currentData(),
                width.currentData(),
                loop.currentData(),
            ]

        try:
            destination.write_bytes(
                b"".join(
                    value.encode("utf-8") + b"\0"
                    for value in values
                )
            )
        except OSError as error:
            QMessageBox.critical(
                dialog,
                "Cannot save settings",
                str(error),
            )
            return

        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
