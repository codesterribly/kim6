#!/usr/bin/env python3
"""Single-window Qt 6 configuration for KIM6's existing collage renderer."""

import os
import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


def main():
    if len(sys.argv) < 3:
        return 2

    destination = Path(sys.argv[1])
    pictures = sys.argv[2:]

    app = QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Create a Photo Collage")
    dialog.setMinimumWidth(460)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(
        f"{len(pictures)} selected image(s) will be included."
    ))

    form = QFormLayout()
    layout.addLayout(form)

    def choice(label, entries):
        widget = QComboBox()
        for text, value in entries:
            widget.addItem(text, value)
        form.addRow(label, widget)
        return widget

    design = choice("Layout:", [
        ("Classic Grid", "grid"),
        ("Mosaic", "mosaic"),
        ("Hero + Supporting Photos", "hero"),
        ("Scattered / Polaroid", "scattered"),
        ("Filmstrip / Storyboard", "filmstrip"),
    ])

    canvas = choice("Canvas:", [
        ("3840 × 2560 (3:2)", "3840x2560"),
        ("3840 × 2160 (16:9)", "3840x2160"),
        ("3200 × 3200 (Square)", "3200x3200"),
        ("3200 × 4000 (Portrait)", "3200x4000"),
        ("Custom dimensions", "custom"),
    ])

    custom_canvas = QLineEdit("3840x2560")
    form.addRow("Custom canvas:", custom_canvas)

    def sync_canvas():
        custom_canvas.setEnabled(canvas.currentData() == "custom")

    canvas.currentIndexChanged.connect(sync_canvas)
    sync_canvas()

    placement = choice("Image placement:", [
        ("Fit entire photograph", "fit"),
        ("Fill and crop", "fill"),
    ])

    spacing = QSpinBox()
    spacing.setRange(0, 200)
    spacing.setValue(24)
    spacing.setSuffix(" px")
    form.addRow("Spacing:", spacing)

    borders = choice("Photo borders:", [
        ("None", "none"),
        ("Thin white border", "thin"),
        ("Polaroid frame", "polaroid"),
    ])

    background = choice("Background:", [
        ("White", "white"),
        ("Black", "black"),
        ("Transparent", "none"),
        ("Custom color", "custom"),
    ])

    custom_color = QLineEdit("#808080")
    form.addRow("Custom color:", custom_color)

    def sync_color():
        custom_color.setEnabled(background.currentData() == "custom")

    background.currentIndexChanged.connect(sync_color)
    sync_color()

    shadow = QCheckBox("Enable drop shadows")
    shadow.setChecked(True)
    form.addRow("Shadows:", shadow)

    shuffle = QCheckBox("Shuffle selected photographs")
    form.addRow("Order:", shuffle)

    output_row = QWidget()
    output_layout = QHBoxLayout(output_row)
    output_layout.setContentsMargins(0, 0, 0, 0)

    initial_dir = os.path.dirname(os.path.abspath(pictures[0]))
    output = QLineEdit(os.path.join(initial_dir, "collage.png"))
    browse = QPushButton("Browse…")

    output_layout.addWidget(output)
    output_layout.addWidget(browse)
    form.addRow("Save as:", output_row)

    def browse_output():
        filename, _ = QFileDialog.getSaveFileName(
            dialog,
            "Save Collage",
            output.text(),
            "PNG Images (*.png)",
        )
        if filename:
            output.setText(filename)

    browse.clicked.connect(browse_output)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    layout.addWidget(buttons)

    def accept():
        dimensions = (
            custom_canvas.text().strip()
            if canvas.currentData() == "custom"
            else canvas.currentData()
        )

        if not re.fullmatch(r"[1-9][0-9]{0,5}x[1-9][0-9]{0,5}", dimensions):
            QMessageBox.warning(
                dialog, "Invalid canvas",
                "Enter dimensions as WIDTHxHEIGHT."
            )
            return

        name = output.text().strip()
        if not name:
            QMessageBox.warning(
                dialog, "Missing output",
                "Choose an output filename."
            )
            return

        if not name.lower().endswith(".png"):
            name += ".png"

        if not os.path.isdir(os.path.dirname(os.path.abspath(name))):
            QMessageBox.warning(
                dialog, "Invalid destination",
                "The selected output directory does not exist."
            )
            return

        color = (
            custom_color.text().strip()
            if background.currentData() == "custom"
            else background.currentData()
        )

        if not re.fullmatch(r"[A-Za-z0-9#(),._%+ -]{1,64}", color):
            QMessageBox.warning(
                dialog, "Invalid background",
                "Use a valid ImageMagick color name or hex color."
            )
            return

        values = [
            design.currentData(),
            dimensions,
            placement.currentData(),
            str(spacing.value()),
            borders.currentData(),
            color,
            "true" if shadow.isChecked() else "false",
            os.path.abspath(name),
            "true" if shuffle.isChecked() else "false",
        ]

        # NUL-delimited output preserves spaces and filenames safely.
        destination.write_bytes(
            b"".join(value.encode("utf-8") + b"\0" for value in values)
        )
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
