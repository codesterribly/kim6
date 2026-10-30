#!/usr/bin/env python3
"""KIM6 graphical creation settings for GIF animations and HTML galleries.

The dialog collects parameters only. The Bash dispatcher retains responsibility
for source validation, rendering, safe staging, collision handling and publication.
"""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def main():
    if len(sys.argv) != 5:
        return 2

    kind, result_path, starting_dir, image_count = sys.argv[1:]
    if kind not in ("gif", "gallery"):
        return 2

    app = QApplication(sys.argv)

    dialog = QDialog()
    dialog.setWindowTitle(
        "KIM6 — Create an Animated GIF"
        if kind == "gif"
        else "KIM6 — Create an HTML Gallery"
    )
    dialog.setMinimumWidth(530)

    outer = QVBoxLayout(dialog)
    outer.addWidget(
        QLabel(f"{image_count} selected image(s) will be included.")
    )

    form = QFormLayout()
    outer.addLayout(form)

    fields = {}

    def spin(key, label, minimum, maximum, value):
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        form.addRow(label, widget)
        fields[key] = widget

    def text(key, label, value):
        widget = QLineEdit(value)
        form.addRow(label, widget)
        fields[key] = widget

    def choice(key, label, options):
        widget = QComboBox()
        for caption, value in options:
            widget.addItem(caption, value)
        form.addRow(label, widget)
        fields[key] = widget

    destination_row = QWidget()
    destination_layout = QHBoxLayout(destination_row)
    destination_layout.setContentsMargins(0, 0, 0, 0)

    if kind == "gif":
        spin(
            "delay",
            "Frame delay (centiseconds):",
            0, 65535, 100
        )
        spin(
            "loops",
            "Loop count (0 = infinite):",
            0, 65535, 0
        )

        default_destination = os.path.join(
            starting_dir, "my_animation.gif"
        )

    else:
        text("title", "Gallery title:", "My Gallery")
        text("author", "Author:", os.environ.get("USER", ""))
        spin("columns", "Columns:", 1, 100, 4)

        choice(
            "theme",
            "Appearance:",
            [
                ("Dark Portfolio", "dark"),
                ("Clean Light", "light"),
            ],
        )

        choice(
            "resolution",
            "Image resolution:",
            [
                ("Standard (up to 1920 px)", "1920"),
                ("High (up to 3840 px)", "3840"),
            ],
        )

        default_destination = starting_dir

    destination = QLineEdit(default_destination)
    browse = QPushButton("Browse…")

    destination_layout.addWidget(destination)
    destination_layout.addWidget(browse)

    form.addRow(
        "Save GIF as:" if kind == "gif" else "Create gallery in:",
        destination_row,
    )

    def browse_destination():
        if kind == "gif":
            value, _ = QFileDialog.getSaveFileName(
                dialog,
                "Save Animated GIF",
                destination.text(),
                "Animated GIF (*.gif)",
            )
        else:
            value = QFileDialog.getExistingDirectory(
                dialog,
                "Choose Parent Directory for HTML Gallery",
                destination.text() or starting_dir,
            )

        if value:
            destination.setText(value)

    browse.clicked.connect(browse_destination)

    explanation = QLabel(
        "Existing files will not be overwritten. "
        "KIM6 automatically numbers new outputs when needed."
    )
    explanation.setWordWrap(True)
    outer.addWidget(explanation)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    outer.addWidget(buttons)

    def save():
        target = destination.text().strip()

        if not target:
            QMessageBox.warning(
                dialog,
                "Destination required",
                "Choose an output destination.",
            )
            return

        target = os.path.abspath(os.path.expanduser(target))

        if kind == "gif":
            if not target.lower().endswith(".gif"):
                target += ".gif"
            parent = os.path.dirname(target)
        else:
            parent = target

        if not os.path.isdir(parent):
            QMessageBox.warning(
                dialog,
                "Invalid destination",
                "The destination directory does not exist.",
            )
            return

        values = []

        if kind == "gif":
            values = [
                str(fields["delay"].value()),
                str(fields["loops"].value()),
                target,
            ]
        else:
            values = [
                fields["title"].text(),
                fields["author"].text(),
                str(fields["columns"].value()),
                fields["theme"].currentData(),
                fields["resolution"].currentData(),
                target,
            ]

        if any("\0" in value for value in values):
            return

        with open(result_path, "wb") as stream:
            for value in values:
                stream.write(value.encode("utf-8") + b"\0")

        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
