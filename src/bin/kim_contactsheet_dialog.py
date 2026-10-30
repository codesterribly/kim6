#!/usr/bin/env python3
"""KIM6 Contact Sheet configuration dialog for Qt 6."""

import os
import sys

from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)


def main():
    if len(sys.argv) < 3:
        return 2

    settings_file = sys.argv[1]
    images = sys.argv[2:]
    app = QApplication(sys.argv)

    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Contact Sheet")
    dialog.setMinimumWidth(470)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(
        f"Images selected in Dolphin: {len(images)}"
    ))

    form = QFormLayout()
    layout.addLayout(form)

    def select(label, choices):
        widget = QComboBox()
        for text, value in choices:
            widget.addItem(text, value)
        form.addRow(label, widget)
        return widget

    paper = select("Paper:", [
        ("US Letter", "letter"), ("A4", "a4")
    ])
    orientation = select("Orientation:", [
        ("Portrait", "portrait"), ("Landscape", "landscape")
    ])
    grid = select("Layout:", [
        ("4 × 5 — Compact", "4x5"),
        ("3 × 4 — Spacious", "3x4"),
        ("5 × 7 — Dense", "5x7"),
    ])
    labels = select("Labels:", [
        ("Number and filename", "both"),
        ("Number only", "number"),
        ("Filename only", "filename"),
        ("None", "none"),
    ])
    fit = select("Placement:", [
        ("Fit without cropping", "fit"),
        ("Fill with center crop", "fill"),
    ])
    background = select("Background:", [
        ("White", "white"), ("Black", "black")
    ])
    dpi = select("Resolution:", [
        ("300 DPI — Print", "300"),
        ("150 DPI — Draft", "150"),
    ])

    heading = QLineEdit("Contact Sheet")
    heading.setMaxLength(150)
    form.addRow("Heading:", heading)

    output_row = QWidget()
    output_layout = QHBoxLayout(output_row)
    output_layout.setContentsMargins(0, 0, 0, 0)

    source_dir = os.path.dirname(os.path.abspath(images[0]))
    output = QLineEdit(
        os.path.join(source_dir, "contact-sheet.pdf")
    )
    browse = QPushButton("Browse…")

    output_layout.addWidget(output)
    output_layout.addWidget(browse)
    form.addRow("Save PDF:", output_row)

    def browse_output():
        filename, _ = QFileDialog.getSaveFileName(
            dialog, "Save Contact Sheet",
            output.text(), "PDF (*.pdf)"
        )
        if filename:
            output.setText(filename)

    browse.clicked.connect(browse_output)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    layout.addWidget(buttons)

    def save():
        filename = output.text().strip()

        if not filename:
            QMessageBox.warning(
                dialog, "Missing output",
                "Choose an output filename."
            )
            return

        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        filename = os.path.abspath(filename)

        if not os.path.isdir(os.path.dirname(filename)):
            QMessageBox.warning(
                dialog, "Invalid destination",
                "The output directory does not exist."
            )
            return

        values = [
            paper.currentData(),
            orientation.currentData(),
            grid.currentData(),
            labels.currentData(),
            fit.currentData(),
            background.currentData(),
            dpi.currentData(),
            heading.text(),
            filename,
        ]

        # NUL-delimited fields preserve spaces and Unicode.
        with open(settings_file, "wb") as stream:
            for value in values:
                stream.write(value.encode("utf-8") + b"\0")

        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
