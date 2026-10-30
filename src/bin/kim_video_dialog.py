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


def main():
    if len(sys.argv) < 4:
        return 2

    mode = sys.argv[1]
    destination = Path(sys.argv[2])
    defaults = sys.argv[3:]

    if mode not in ("contact", "gif"):
        return 2

    if len(defaults) != (2 if mode == "contact" else 5):
        return 2

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

        layout.addWidget(QLabel(
            "Maximum duration: 15 seconds. "
            "Maximum frames: 360."
        ))

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    buttons.button(QDialogButtonBox.Ok).setText("Create")
    layout.addWidget(buttons)

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
