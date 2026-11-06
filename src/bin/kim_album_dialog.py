#!/usr/bin/env python3
"""KIM6 PDF Album editor with ordered images, captions and page preview."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget, QCheckBox, QTableWidget,
    QTableWidgetItem, QPlainTextEdit, QHeaderView, QGroupBox,
)

from kim_ui import tr
from kim_annotations import clean_text
from kim_create_dialog import (
    CreationImages, OrderedImageDialog,
    creation_output, write_creation_settings,
)

# KIM6_ALBUM_ORDERED_PREVIEW_V1
# These capacities match the existing kim_all album renderer.
LAYOUTS = [
    ("1 × 1, Portrait", "1", 1, 1, False),
    ("1 × 1, Landscape", "2", 1, 1, True),
    ("1 × 2, Landscape", "3", 1, 2, True),
    ("2 × 1, Portrait", "4", 2, 1, False),
    ("2 × 2, Landscape", "5", 2, 2, True),
    ("3 × 2, Portrait", "6", 3, 2, False),
    ("3 × 4, Landscape", "7", 3, 4, True),
    ("4 × 4, Landscape", "8", 4, 4, True),
]


class AlbumDialog(OrderedImageDialog):
    def __init__(self, settings_file, images):
        super().__init__()
        self.settings_file = settings_file
        self.captions_by_path = {}
        self.displayed_target = None

        self.setWindowTitle("KIM6 — Create a PDF Album")
        self.setMinimumWidth(680)
        self.resize(780, 780)

        layout = QVBoxLayout(self)

        self.ordered = CreationImages(self, "PDF Album")
        layout.addWidget(self.ordered)

        self.selection_status = QLabel()
        layout.addWidget(self.selection_status)

        form = QFormLayout()
        layout.addLayout(form)

        self.album_layout = QComboBox()
        for label, key, _, _, _ in LAYOUTS:
            self.album_layout.addItem(label, key)
        self.album_layout.setCurrentIndex(4)
        form.addRow("Layout:", self.album_layout)

        annotation_group = QGroupBox(
            tr("Captions beneath each image")
        )
        annotation_layout = QVBoxLayout(annotation_group)

        note = QLabel(tr(
            "Selected information appears beneath each image. "
            "Nothing is printed over the image."
        ))
        note.setWordWrap(True)
        annotation_layout.addWidget(note)

        annotation_form = QFormLayout()
        annotation_layout.addLayout(annotation_form)
        layout.addWidget(annotation_group)

        self.caption_source = QComboBox()
        for label, key in (
            (tr("None"), "none"),
            (tr("Embedded caption"), "embedded"),
            (tr("Filename"), "filename"),
            (tr("Custom per-image captions"), "custom"),
        ):
            self.caption_source.addItem(label, key)

        annotation_form.addRow(
            tr("Caption source:"), self.caption_source
        )

        self.capture_date = QCheckBox(tr("Include capture date"))
        self.camera_lens = QCheckBox(
            tr("Include camera and lens")
        )

        annotation_form.addRow(self.capture_date)
        annotation_form.addRow(self.camera_lens)

        self.captions = QTableWidget(0, 2)
        self.captions.setHorizontalHeaderLabels([
            tr("Source filename"), tr("Caption")
        ])
        self.captions.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.captions.setFixedHeight(164)
        self.captions.hide()
        annotation_layout.addWidget(self.captions)

        source_dir = (
            str(Path(images[0]).absolute().parent)
            if images else str(Path.home())
        )

        self.output = QLineEdit(
            os.path.join(source_dir, "album.pdf")
        )
        browse = QPushButton("Browse…")

        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output, 1)
        output_layout.addWidget(browse)

        form.addRow("Save PDF:", output_row)

        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addWidget(QLabel("Page preview"))

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(180)
        self.preview.setAccessibleName(
            "Approximate PDF album first-page preview"
        )
        layout.addWidget(self.preview)

        self.preview_note = QLabel(
            "Approximate first-page preview using cached thumbnails."
        )
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.create = buttons.button(QDialogButtonBox.Ok)
        self.create.setText("Create")

        self.add_source_notice(layout)
        layout.addWidget(buttons)

        browse.clicked.connect(self.choose_output)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        self.ordered.changed.connect(self.selection_changed)
        self.ordered.thumbnail_changed.connect(self.update_preview)

        self.album_layout.currentIndexChanged.connect(
            self.update_preview
        )
        self.caption_source.currentIndexChanged.connect(
            self.caption_mode_changed
        )
        self.capture_date.toggled.connect(self.update_controls)
        self.camera_lens.toggled.connect(self.update_controls)
        self.output.textChanged.connect(self.update_controls)

        self.ordered.add_paths(images)
        self.selection_changed()

    def paths(self):
        return self.ordered.ordered_paths()

    def caption_mode_changed(self, *_):
        self.captions.setVisible(
            self.caption_source.currentData() == "custom"
        )
        self.update_controls()

    def selection_changed(self, *_):
        paths = self.paths()

        # Removing a source discards its caption. Moving a source
        # preserves the association through the absolute path.
        for path in tuple(self.captions_by_path):
            if path not in paths:
                del self.captions_by_path[path]

        self.captions.setRowCount(len(paths))

        for row, path in enumerate(paths):
            item = QTableWidgetItem(Path(path).name)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setToolTip(path)
            self.captions.setItem(row, 0, item)

            editor = QPlainTextEdit()
            editor.setPlaceholderText(
                tr("Blank captions are allowed")
            )
            editor.setPlainText(
                self.captions_by_path.get(path, "")
            )
            editor.textChanged.connect(
                lambda p=path, e=editor:
                    self.caption_changed(p, e.toPlainText())
            )
            self.captions.setCellWidget(row, 1, editor)
            self.captions.setRowHeight(row, 66)

        self.update_controls()

    def caption_changed(self, path, text):
        if path in self.paths():
            self.captions_by_path[path] = text
            self.update_preview()

    def chosen_layout(self):
        key = self.album_layout.currentData()
        return next(
            spec for spec in LAYOUTS if spec[1] == key
        )

    def update_controls(self, *_):
        paths = self.paths()
        ready, blocked, pending = self.ordered.counts()

        self.selection_status.setText(
            f"{len(paths)} selected images · "
            f"{ready} ready · {blocked} blocked · "
            f"{pending} inspecting"
        )

        reason = ""
        valid = True

        try:
            requested, candidate = creation_output(
                self.output.text(), ("pdf",), paths
            )
            self.displayed_target = str(candidate)

            if requested != candidate:
                reason = (
                    "Output exists. Proposed filename: "
                    + str(candidate)
                )

        except (OSError, ValueError) as exc:
            self.displayed_target = None
            reason = str(exc)
            valid = False

        annotated = (
            self.caption_source.currentData() != "none"
            or self.capture_date.isChecked()
            or self.camera_lens.isChecked()
        )

        if blocked:
            reason = "Remove or replace blocked images."
        elif pending or self.ordered.worker is not None:
            reason = "Inspecting selected images…"
        elif not paths:
            reason = "Add at least one image."
        elif annotated and any(
            self.ordered.states[path][2] is not None
            and (
                self.ordered.states[path][2]["frames"] != 1
                or self.ordered.states[path][2]["animated_png"]
            )
            for path in paths
        ):
            reason = (
                "Captions and camera information require "
                "single-frame images."
            )
            valid = False

        self.status.setText(reason)
        self.create.setEnabled(
            valid
            and bool(paths)
            and ready == len(paths)
            and not blocked
            and not pending
            and self.ordered.worker is None
            and self.finish_result is None
        )
        self.update_preview()

    def choose_output(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Album",
            self.output.text(),
            "PDF documents (*.pdf)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if filename:
            self.output.setText(filename)

    def update_preview(self, *_):
        paths = self.paths()
        _, _, columns, rows, landscape = self.chosen_layout()

        image = QImage(
            520, 174, QImage.Format_ARGB32_Premultiplied
        )
        image.fill(QColor("#e1e1e1"))

        painter = QPainter(image)
        painter.setRenderHint(
            QPainter.SmoothPixmapTransform, True
        )

        page_width = 250.0 if landscape else 176.8
        page_height = 176.8 if landscape else 250.0
        scale = min(
            500.0 / page_width,
            166.0 / page_height,
        )

        width = page_width * scale
        height = page_height * scale

        page = QRectF(
            (520 - width) / 2,
            (174 - height) / 2,
            width,
            height,
        )

        painter.fillRect(page, QColor("white"))
        painter.setPen(QPen(QColor("#aaaaaa"), 1))
        painter.drawRect(page)

        gap = max(2.0, page.width() * 0.018)
        margin = max(5.0, page.width() * 0.035)

        cell_width = (
            page.width() - margin * 2
            - gap * (columns - 1)
        ) / columns

        cell_height = (
            page.height() - margin * 2
            - gap * (rows - 1)
        ) / rows

        annotated = (
            self.caption_source.currentData() != "none"
            or self.capture_date.isChecked()
            or self.camera_lens.isChecked()
        )

        for index, path in enumerate(
            paths[:columns * rows]
        ):
            row = index // columns
            column = index % columns

            rect = QRectF(
                page.x() + margin
                + column * (cell_width + gap),
                page.y() + margin
                + row * (cell_height + gap),
                max(1.0, cell_width),
                max(1.0, cell_height),
            )

            caption_height = (
                rect.height() * 0.23 if annotated else 0
            )

            picture = QRectF(
                rect.x(), rect.y(),
                rect.width(),
                max(1.0, rect.height() - caption_height),
            )

            painter.fillRect(
                picture, QColor("#cccccc")
            )

            thumbnail = self.ordered.thumbnails.get(path)

            if thumbnail is not None and not thumbnail.isNull():
                factor = min(
                    picture.width() / thumbnail.width(),
                    picture.height() / thumbnail.height(),
                )

                w = thumbnail.width() * factor
                h = thumbnail.height() * factor

                target = QRectF(
                    picture.center().x() - w / 2,
                    picture.center().y() - h / 2,
                    w, h,
                )

                painter.drawImage(
                    target,
                    thumbnail,
                    QRectF(
                        0, 0,
                        thumbnail.width(),
                        thumbnail.height(),
                    ),
                )

            if annotated:
                mode = self.caption_source.currentData()

                if mode == "custom":
                    label = self.captions_by_path.get(
                        path, ""
                    )
                elif mode == "filename":
                    label = Path(path).name
                elif mode == "embedded":
                    label = "Embedded caption"
                else:
                    label = ""

                if self.capture_date.isChecked():
                    label += "  Date"
                if self.camera_lens.isChecked():
                    label += "  Camera/lens"

                font = painter.font()
                font.setPixelSize(7)
                painter.setFont(font)
                painter.setPen(QColor("#333333"))

                caption_rect = QRectF(
                    rect.x(),
                    picture.bottom(),
                    rect.width(),
                    caption_height,
                )

                painter.drawText(
                    caption_rect,
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        label.strip(),
                        Qt.ElideRight,
                        max(1, int(rect.width())),
                    ),
                )

        painter.end()

        self.preview.setPixmap(
            QPixmap.fromImage(image)
        )

        notes = [
            "Approximate first-page preview.",
            "The final PDF uses the selected layout.",
        ]

        if len(paths) > columns * rows:
            notes.append(
                "Additional images continue on later pages."
            )

        if any(
            self.ordered.states[path][2] is not None
            and self.ordered.states[path][2]["frames"] > 1
            for path in paths
        ):
            notes.append(
                "Multi-frame sources may change pagination."
            )

        if self.caption_source.currentData() == "embedded":
            notes.append(
                "Embedded captions use placeholders."
            )

        self.preview_note.setText(" ".join(notes))

    def accept(self):
        if self.finish_result is not None:
            return

        previous_target = self.displayed_target
        self.update_controls()

        if (
            not self.create.isEnabled()
            or not self.ordered.validate_sources()
        ):
            return

        if self.displayed_target != previous_target:
            self.status.setText(
                "Destination changed. Review the new "
                "numbered filename, then Create."
            )
            return

        paths = self.paths()
        requested, _ = creation_output(
            self.output.text(), ("pdf",), paths
        )

        values = [
            self.album_layout.currentData(),
            str(requested),
            self.caption_source.currentData(),
            str(self.capture_date.isChecked()).lower(),
            str(self.camera_lens.isChecked()).lower(),
            str(len(paths)),
        ]

        values.extend(
            clean_text(
                self.captions_by_path.get(path, "")
            ) for path in paths
        )

        values.extend(paths)

        if write_creation_settings(
            self, self.settings_file, values
        ):
            self.done(QDialog.Accepted)


def main():
    if len(sys.argv) < 3:
        return 2

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = AlbumDialog(sys.argv[1], sys.argv[2:])

    return (
        0 if dialog.exec() == QDialog.Accepted
        else 130
    )


if __name__ == "__main__":
    sys.exit(main())
