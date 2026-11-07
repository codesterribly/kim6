#!/usr/bin/env python3
"""KIM6 Contact Sheet configuration dialog for Qt 6."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from PySide6.QtWidgets import QScrollArea, QWidget
from kim_ui import tr
from kim_create_dialog import (
    CreationImages, OrderedImageDialog, creation_output, write_creation_settings,
)


class ContactSheetDialog(OrderedImageDialog):
    def __init__(self, settings_file, images):
        super().__init__()
        self.settings_file = settings_file
        self.setWindowTitle('KIM6 - Contact sheet')
        self.setMinimumWidth(600)
        # KIM6_CONTACTSHEET_SCROLL_LAYOUT_V1
        # Bound the window height without shrinking its controls.
        # The existing thumbnail list remains independently scrollable.
        self.resize(720, 820)
        self.setMaximumHeight(900)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        scroll.setWidget(content)
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
            ("4 × 5 - Compact", "4x5"),
            ("3 × 4 - Spacious", "3x4"),
            ("5 × 7 - Dense", "5x7"),
        ])
        self.labels = select("Captions:", [
            ("Number and filename", "both"),
            ("Number only", "number"),
            ("Filename only", "filename"),
            ("No captions", "none"),
            (tr("Image Capture Date"), "capture"),
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
            ("300 DPI - Print", "300"),
            ("150 DPI - Draft", "150"),
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

        # KIM6_CONTACT_SHEET_PREVIEW_V1
        self.preview_heading = QLabel('Page preview')
        layout.addWidget(self.preview_heading)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(230)
        self.preview.setAccessibleName(
            'Approximate contact sheet page preview'
        )
        layout.addWidget(self.preview)

        self.preview_note = QLabel(
            'Approximate first-page preview using cached thumbnails.'
        )
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)

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
        self.ordered.resized.connect(self.compact_image_list)

        for widget in (
            self.paper, self.orientation, self.grid,
            self.labels, self.font_size, self.label_placement,
            self.fit, self.background, self.dpi,
        ):
            widget.currentIndexChanged.connect(self.update_preview)

        self.heading.textChanged.connect(self.update_preview)
        self.ordered.changed.connect(self.update_preview)
        self.ordered.thumbnail_changed.connect(self.update_preview)

        self.ordered.add_paths(images)
        self.update_controls()
        self.update_preview()


    def update_preview(self, *_):
        """Draw an approximate first PDF page from cached thumbnails.

        No file decoding, ImageMagick calls or output publication.
        Automatic page geometry is illustrative, not the PDF plan.
        """
        paths = self.ordered.ordered_paths()

        image = QImage(
            560, 220, QImage.Format_ARGB32_Premultiplied
        )

        image.fill(QColor("#dddddd"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(
            QPainter.SmoothPixmapTransform, True
        )

        paper = self.paper.currentData()
        landscape = self.orientation.currentData() == "landscape"

        if paper == "a4":
            page_w, page_h = 210.0, 297.0
        else:
            page_w, page_h = 215.9, 279.4

        if landscape:
            page_w, page_h = page_h, page_w

        scale = min(520.0 / page_w, 208.0 / page_h)

        width = page_w * scale
        height = page_h * scale

        page = QRectF(
            (560.0 - width) / 2.0,
            (220.0 - height) / 2.0,
            width,
            height,
        )

        dark = self.background.currentData() == "black"

        page_color = QColor("#171717" if dark else "white")
        ink = QColor("white" if dark else "#222222")

        painter.fillRect(page, page_color)
        painter.setPen(QPen(QColor("#999999"), 1))
        painter.drawRect(page)

        margin = max(5.0, min(width, height) * 0.045)
        heading_height = max(12.0, height * 0.075)

        title_rect = QRectF(
            page.x() + margin,
            page.y() + margin,
            page.width() - 2 * margin,
            heading_height,
        )

        painter.setPen(ink)

        title_font = painter.font()
        title_font.setPixelSize(
            max(7, min(13, int(height * 0.048)))
        )
        title_font.setBold(True)
        painter.setFont(title_font)

        heading = self.heading.text().strip() or "Contact Sheet"

        painter.drawText(
            title_rect,
            Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(
                heading,
                Qt.ElideRight,
                max(1, int(title_rect.width())),
            ),
        )

        grid = self.grid.currentData()

        if grid == "3x4":
            cols, rows = 3, 4
        elif grid == "4x5":
            cols, rows = 4, 5
        elif grid == "5x7":
            cols, rows = 5, 7
        else:
            # Automatic layout is calculated by the PDF renderer
            # using source geometry. This is a representative grid.
            cols, rows = (5, 3) if landscape else (4, 5)

        content_top = (
            page.y() + margin + heading_height + margin * 0.35
        )
        content_bottom = page.bottom() - margin

        available_width = page.width() - 2 * margin
        available_height = max(
            1.0, content_bottom - content_top
        )

        gap = max(1.5, min(width, height) * 0.012)

        cell_width = (
            available_width - gap * (cols - 1)
        ) / cols

        cell_height = (
            available_height - gap * (rows - 1)
        ) / rows

        caption_mode = self.labels.currentData()
        show_caption = caption_mode != "none"
        captions_above = (
            self.label_placement.currentData() == "above"
        )
        fill = self.fit.currentData() == "fill"

        font_size = self.font_size.currentData()

        font_pixels = {
            "small": 6,
            "medium": 8,
            "large": 10,
        }.get(font_size, 7)

        font_pixels = min(
            font_pixels,
            max(5, int(cell_height * 0.20)),
        )

        caption_font = painter.font()
        caption_font.setBold(False)
        caption_font.setPixelSize(font_pixels)
        painter.setFont(caption_font)

        capacity = cols * rows

        for index, path in enumerate(paths[:capacity]):
            col = index % cols
            row = index // cols

            cell = QRectF(
                page.x() + margin + col * (cell_width + gap),
                content_top + row * (cell_height + gap),
                max(1.0, cell_width),
                max(1.0, cell_height),
            )

            caption_height = (
                max(8.0, cell.height() * 0.22)
                if show_caption else 0.0
            )

            if show_caption and captions_above:
                caption_rect = QRectF(
                    cell.x(),
                    cell.y(),
                    cell.width(),
                    caption_height,
                )

                picture_rect = QRectF(
                    cell.x(),
                    cell.y() + caption_height,
                    cell.width(),
                    max(1.0, cell.height() - caption_height),
                )

            else:
                picture_rect = QRectF(
                    cell.x(),
                    cell.y(),
                    cell.width(),
                    max(1.0, cell.height() - caption_height),
                )

                caption_rect = QRectF(
                    cell.x(),
                    cell.bottom() - caption_height,
                    cell.width(),
                    caption_height,
                )

            painter.fillRect(
                picture_rect,
                QColor("#707070" if dark else "#cccccc"),
            )

            thumbnail = self.ordered.thumbnails.get(path)

            if thumbnail is not None and not thumbnail.isNull():
                tw = thumbnail.width()
                th = thumbnail.height()

                if tw > 0 and th > 0:
                    if fill:
                        factor = max(
                            picture_rect.width() / tw,
                            picture_rect.height() / th,
                        )

                        crop_width = picture_rect.width() / factor
                        crop_height = picture_rect.height() / factor

                        source_rect = QRectF(
                            (tw - crop_width) / 2.0,
                            (th - crop_height) / 2.0,
                            crop_width,
                            crop_height,
                        )

                        target_rect = picture_rect

                    else:
                        factor = min(
                            picture_rect.width() / tw,
                            picture_rect.height() / th,
                        )

                        target_width = tw * factor
                        target_height = th * factor

                        target_rect = QRectF(
                            picture_rect.center().x()
                            - target_width / 2.0,
                            picture_rect.center().y()
                            - target_height / 2.0,
                            target_width,
                            target_height,
                        )

                        source_rect = QRectF(0, 0, tw, th)

                    painter.drawImage(
                        target_rect,
                        thumbnail,
                        source_rect,
                    )

            if show_caption:
                name = Path(path).name

                if caption_mode == "number":
                    caption = str(index + 1)
                elif caption_mode == "filename":
                    caption = name
                elif caption_mode == "both":
                    caption = f"{index + 1}. {name}"
                elif caption_mode == "capture":
                    caption = "Image Capture Date"
                elif caption_mode == "camera":
                    caption = "Camera / lens"
                elif caption_mode == "embedded":
                    caption = "Embedded caption"
                else:
                    caption = name

                painter.setPen(ink)

                caption = painter.fontMetrics().elidedText(
                    caption,
                    Qt.ElideRight,
                    max(1, int(caption_rect.width())),
                )

                painter.drawText(
                    caption_rect,
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    caption,
                )

        painter.end()

        self.preview.setPixmap(QPixmap.fromImage(image))

        notes = [
            "Approximate first-page preview.",
            "The final PDF uses the selected paper size and DPI.",
        ]

        if grid == "auto":
            notes.append(
                "Automatic layout is illustrative; actual "
                "pagination depends on image dimensions."
            )

        if len(paths) > capacity:
            notes.append(
                "Additional images continue on later pages."
            )

        if caption_mode in ("capture", "camera", "embedded"):
            notes.append(
                "Metadata captions are represented by placeholders."
            )

        self.preview_note.setText(" ".join(notes))

    # KIM6_CONTACTSHEET_COMPACT_LIST_V1
    def compact_image_list(self):
        """Show at most three thumbnail rows; retain scrolling."""
        rows = min(
            3,
            max(1, self.ordered.images.count()),
        )
        self.ordered.images.setFixedHeight(12 + rows * 79)

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
