#!/usr/bin/env python3
"""KIM6 PDF Album configuration dialog.

One window configures the album layout and output filename.
The existing kim_all publication pipeline creates and validates the PDF.
"""

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
    QCheckBox, QTableWidget, QTableWidgetItem, QPlainTextEdit, QHeaderView, QGroupBox,
)

from kim_ui import tr
from kim_annotations import clean_text

LAYOUTS = [
    ("1 × 1, Portrait", "1"),
    ("1 × 1, Landscape", "2"),
    ("1 × 2, Landscape", "3"),
    ("2 × 1, Portrait", "4"),
    ("2 × 2, Landscape", "5"),
    ("3 × 2, Portrait", "6"),
    ("3 × 4, Landscape", "7"),
    ("4 × 4, Landscape", "8"),
]


def main():
    if len(sys.argv) < 3:
        return 2

    settings_file = sys.argv[1]
    images = sys.argv[2:]

    app = QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Create a PDF Album")
    dialog.setMinimumWidth(490)

    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel(f"{len(images)} selected image(s) will be included.")
    )

    form = QFormLayout()
    layout.addLayout(form)

    album_layout = QComboBox()
    for label, value in LAYOUTS:
        album_layout.addItem(label, value)
    album_layout.setCurrentIndex(4)
    form.addRow("Layout:", album_layout)

    annotation_group = QGroupBox(tr("Captions beneath each image"))
    annotation_layout = QVBoxLayout(annotation_group)
    annotation_note = QLabel(tr("Selected information appears beneath each image. "
                               "Nothing is printed over the image."))
    annotation_note.setWordWrap(True)
    annotation_layout.addWidget(annotation_note)
    annotation_form = QFormLayout()
    annotation_layout.addLayout(annotation_form)
    layout.addWidget(annotation_group)

    caption_source = QComboBox()
    caption_source.setAccessibleName(tr("Caption source"))
    for label, value in ((tr("None"), "none"), (tr("Embedded caption"), "embedded"),
                         (tr("Filename"), "filename"), (tr("Custom per-image captions"), "custom")):
        caption_source.addItem(label, value)
    annotation_form.addRow(tr("Caption source:"), caption_source)
    capture_date = QCheckBox(tr("Include capture date"))
    camera_lens = QCheckBox(tr("Include camera and lens"))
    annotation_form.addRow(capture_date)
    annotation_form.addRow(camera_lens)
    captions = QTableWidget(len(images), 2)
    captions.setHorizontalHeaderLabels([tr("Source filename"), tr("Caption")])
    captions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    editors = []
    for row, image in enumerate(images):
        item = QTableWidgetItem(os.path.basename(image))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setToolTip(image)
        captions.setItem(row, 0, item)
        editor = QPlainTextEdit()
        editor.setPlaceholderText(tr("Blank captions are allowed"))
        captions.setCellWidget(row, 1, editor)
        captions.setRowHeight(row, 76)
        editors.append(editor)
    captions.setMinimumHeight(180)
    captions.hide()
    annotation_layout.addWidget(captions)
    caption_source.currentIndexChanged.connect(
        lambda: captions.setVisible(caption_source.currentData() == "custom"))

    output_row = QWidget()
    output_layout = QHBoxLayout(output_row)
    output_layout.setContentsMargins(0, 0, 0, 0)

    source_dir = os.path.dirname(os.path.abspath(images[0]))
    output = QLineEdit(os.path.join(source_dir, "album.pdf"))
    browse = QPushButton("Browse…")

    output_layout.addWidget(output)
    output_layout.addWidget(browse)
    form.addRow("Save PDF:", output_row)

    def browse_output():
        filename, _ = QFileDialog.getSaveFileName(
            dialog,
            "Save PDF Album",
            output.text(),
            "PDF documents (*.pdf)",
        )
        if filename:
            output.setText(filename)

    browse.clicked.connect(browse_output)

    note = QLabel(
        "Existing files will not be overwritten. "
        "KIM6 will choose a numbered filename if necessary."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    layout.addWidget(buttons)

    def save():
        filename = output.text().strip()
        if not filename:
            QMessageBox.warning(
                dialog, "Missing destination",
                "Enter an output PDF filename.",
            )
            return

        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

        filename = os.path.abspath(filename)

        if not os.path.isdir(os.path.dirname(filename)):
            QMessageBox.warning(
                dialog, "Invalid destination",
                "The output directory does not exist.",
            )
            return

        # NUL-delimited values preserve whitespace and Unicode.
        with open(settings_file, "wb") as stream:
            values = [album_layout.currentData(), filename, caption_source.currentData(),
                      str(capture_date.isChecked()).lower(), str(camera_lens.isChecked()).lower()]
            values.extend(clean_text(editor.toPlainText()) for editor in editors)
            for value in values:
                stream.write(value.encode("utf-8") + b"\0")

        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
