#!/usr/bin/env python3
"""KIM6 Contact Sheet configuration dialog for Qt 6."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from kim_ui import tr
from kim_create_dialog import (
    CreationImages, OrderedImageDialog, creation_output, write_creation_settings,
)


class ContactSheetDialog(OrderedImageDialog):
    def __init__(self, settings_file, images):
        super().__init__()
        self.settings_file = settings_file
        self.setWindowTitle('KIM6 — Contact Sheet')
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        self.ordered = CreationImages(self, 'PDF Contact Sheet', single_frame=True)
        layout.addWidget(self.ordered)
        self.count = QLabel()
        layout.addWidget(self.count)
        form = QFormLayout()
        layout.addLayout(form)

        def select(label, choices):
            widget = QComboBox()
            for text, value in choices:
                widget.addItem(text, value)
            widget.setAccessibleName(label.rstrip(':'))
            form.addRow(label, widget)
            return widget

        self.paper = select("Paper:", [
            ("US Letter", "letter"), ("A4", "a4")
        ])
        self.orientation = select("Orientation:", [
            ("Portrait", "portrait"), ("Landscape", "landscape")
        ])
        self.grid = select("Layout:", [
            ("Automatic (recommended)", "auto"),
            ("4 × 5 — Compact", "4x5"),
            ("3 × 4 — Spacious", "3x4"),
            ("5 × 7 — Dense", "5x7"),
        ])
        self.labels = select("Captions:", [
            ("Number and filename", "both"),
            ("Number only", "number"),
            ("Filename only", "filename"),
            ("No captions", "none"),
            (tr("Capture date"), "capture"),
            (tr("Camera and lens"), "camera"),
            (tr("Embedded caption"), "embedded"),
        ])
        self.font_size = select(tr("Caption font size:"), [
            (tr("Auto (recommended)"), "auto"), (tr("Small"), "small"),
            (tr("Medium"), "medium"), (tr("Large"), "large"),
        ])
        self.label_placement = select(tr("Caption position:"), [
            (tr("Below image"), "below"), (tr("Above image"), "above"),
        ])
        self.fit = select("Placement:", [
            ("Fit without cropping", "fit"),
            ("Fill with center crop", "fill"),
        ])
        self.background = select("Background:", [
            ("White", "white"), ("Black", "black")
        ])
        self.dpi = select("Resolution:", [
            ("300 DPI — Print", "300"),
            ("150 DPI — Draft", "150"),
        ])

        self.heading = QLineEdit("Contact Sheet")
        self.heading.setMaxLength(150)
        form.addRow("Heading:", self.heading)

        source_dir = str(Path(images[0]).absolute().parent) if images else str(Path.home())
        self.output = QLineEdit(os.path.join(source_dir, 'contact-sheet.pdf'))
        browse = QPushButton('Browse…')
        row = QHBoxLayout()
        row.addWidget(self.output, 1)
        row.addWidget(browse)
        form.addRow('Save PDF:', row)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.create = buttons.button(QDialogButtonBox.Ok)
        self.create.setText('Create')
        self.add_source_notice(layout)
        layout.addWidget(buttons)
        browse.clicked.connect(self.choose_output)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.output.textChanged.connect(self.update_controls)
        self.heading.textChanged.connect(self.update_controls)
        self.ordered.changed.connect(self.update_controls)
        self.ordered.resized.connect(self.fit_images)
        self.ordered.add_paths(images)
        self.update_controls()
        self.fit_images()

    def choose_output(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Save Contact Sheet', self.output.text(), 'PDF (*.pdf)',
            options=QFileDialog.DontConfirmOverwrite)
        if filename:
            self.output.setText(filename)

    def update_controls(self, *_):
        ready, blocked, pending = self.ordered.counts()
        paths = self.ordered.ordered_paths()
        self.count.setText(f'{len(paths)} selected image(s)')
        problem = ''
        valid = True
        try:
            requested, candidate = creation_output(self.output.text(), ('pdf',), paths)
            if requested != candidate:
                problem = f'Output exists. Proposed filename: {candidate}'
            if any(char in self.heading.text() for char in ('\0', '\n', '\r')):
                raise ValueError('Heading cannot contain line breaks or NUL.')
        except (OSError, ValueError) as exc:
            problem = str(exc)
            valid = False
        if blocked:
            problem = 'Remove or replace blocked images.'
        elif pending:
            problem = 'Inspecting selected images…'
        elif not ready:
            problem = 'Add at least one image.'
        self.status.setText(problem)
        self.create.setEnabled(valid and bool(ready) and not blocked and not pending)

    def accept(self):
        if self.finish_result is not None:
            return
        self.update_controls()
        if not self.create.isEnabled() or not self.ordered.validate_sources():
            return
        requested, _ = creation_output(self.output.text(), ('pdf',), self.ordered.ordered_paths())
        values = [
            self.paper.currentData(), self.orientation.currentData(),
            self.grid.currentData(), self.labels.currentData(),
            self.fit.currentData(), self.background.currentData(),
            self.dpi.currentData(), self.heading.text(), str(requested),
            self.font_size.currentData(), self.label_placement.currentData(),
            *self.ordered.ordered_paths(),
        ]
        if write_creation_settings(self, self.settings_file, values):
            self.done(QDialog.Accepted)


def main():
    if len(sys.argv) < 3:
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = ContactSheetDialog(sys.argv[1], sys.argv[2:])
    return 0 if dialog.exec() == QDialog.Accepted else 130


if __name__ == '__main__':
    sys.exit(main())
