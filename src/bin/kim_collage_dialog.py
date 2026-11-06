#!/usr/bin/env python3
"""Single-window Qt 6 configuration for KIM6's existing collage renderer."""

import os
import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QColorDialog, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPen
from PySide6.QtCore import Qt, QRectF

from kim_create_dialog import CreationImages, OrderedImageDialog


def collision_message(filename):
    """Advisory only: the renderer rechecks using create-only publication."""
    name = filename.strip()
    if not name: return ''
    if not name.lower().endswith('.png'): name += '.png'
    path = Path(os.path.abspath(name))
    if not os.path.lexists(path): return ''
    number = 1
    while number < 10000:
        candidate = path.with_name(f'{path.stem}_{number}{path.suffix}')
        if not os.path.lexists(candidate):
            return f'{path.name} already exists. KIM6 plans to save this as {candidate.name}. The name is checked again when saving.'
        number += 1
    return 'Many matching names already exist. Choose a different filename.'


def main():
    if len(sys.argv) < 3:
        return 2

    destination = Path(sys.argv[1])
    pictures = sys.argv[2:]

    app = QApplication.instance() or QApplication(sys.argv)
    # KIM6_COLLAGE_ORDERED_SELECTION_V1
    dialog = OrderedImageDialog()
    dialog.setWindowTitle("KIM6 — Create Collage")
    dialog.setMinimumWidth(680)
    dialog.resize(780, 760)

    layout = QVBoxLayout(dialog)

    instruction = QLabel(
        "Images appear in composition order. "
        "Drag rows or use Move Up / Move Down to reorder."
    )
    instruction.setWordWrap(True)
    layout.addWidget(instruction)

    dialog.ordered = CreationImages(dialog, "Collage")
    layout.addWidget(dialog.ordered)

    selection_status = QLabel()
    selection_status.setWordWrap(True)
    layout.addWidget(selection_status)

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

    custom_color_row = QWidget()
    color_layout = QHBoxLayout(custom_color_row)
    color_layout.setContentsMargins(0, 0, 0, 0)

    custom_color = QLineEdit("#808080")
    custom_color.setPlaceholderText("#RRGGBB")
    custom_color.setToolTip(
        "Enter a hexadecimal color or choose a color."
    )

    color_swatch = QLabel()
    color_swatch.setFixedSize(26, 22)
    color_swatch.setAccessibleName(
        "Selected background color preview"
    )

    choose_color = QPushButton("Choose Color…")

    color_layout.addWidget(custom_color, 1)
    color_layout.addWidget(color_swatch)
    color_layout.addWidget(choose_color)

    form.addRow("Custom color:", custom_color_row)

    def update_color_swatch(text):
        color = QColor(text.strip())
        fill = (
            color.name()
            if color.isValid()
            else "transparent"
        )
        color_swatch.setStyleSheet(
            "QLabel { background-color: " + fill + "; "
            "border: 1px solid palette(mid); }"
        )
        color_swatch.setToolTip(
            color.name()
            if color.isValid()
            else "Invalid color"
        )

    def choose_background_color():
        initial = QColor(custom_color.text().strip())
        if not initial.isValid():
            initial = QColor("#808080")

        selected = QColorDialog.getColor(
            initial,
            dialog,
            "Choose Collage Background Color"
        )

        if selected.isValid():
            custom_color.setText(selected.name())

    def sync_color():
        custom_color_row.setEnabled(
            background.currentData() == "custom"
        )

    custom_color.textChanged.connect(update_color_swatch)
    choose_color.clicked.connect(choose_background_color)
    background.currentIndexChanged.connect(sync_color)

    update_color_swatch(custom_color.text())
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
    collision = QLabel(); collision.setWordWrap(True)
    collision.setAccessibleName('Planned collage filename collision')
    form.addRow('', collision)

    def update_collision():
        message = collision_message(output.text())
        collision.setText(message); collision.setVisible(bool(message))

    output.textChanged.connect(update_collision)
    update_collision()

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


    # KIM6_COLLAGE_LAYOUT_PREVIEW_V1
    preview_heading = QLabel("Layout preview")
    preview_heading.setAccessibleName("Collage layout preview heading")
    layout.addWidget(preview_heading)

    preview_image = QLabel()
    preview_image.setAlignment(Qt.AlignCenter)
    preview_image.setFixedHeight(184)
    preview_image.setAccessibleName("Approximate collage composition")
    layout.addWidget(preview_image)

    preview_note = QLabel(
        "Approximate layout using available thumbnails. "
        "Final rendering may differ."
    )
    preview_note.setWordWrap(True)
    layout.addWidget(preview_note)

    def refresh_preview(*_):
        paths = dialog.ordered.ordered_paths()
        count = len(paths)

        image = QImage(
            560, 180, QImage.Format_ARGB32_Premultiplied
        )
        image.fill(QColor("#e5e5e5"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        dimensions = (
            custom_canvas.text().strip()
            if canvas.currentData() == "custom"
            else canvas.currentData()
        )

        match = re.fullmatch(
            r"([1-9][0-9]{0,5})x([1-9][0-9]{0,5})",
            dimensions,
        )

        if match:
            cw, ch = map(int, match.groups())
        else:
            cw, ch = 3840, 2560

        ratio = cw / ch
        if ratio > 0:
            display_width = min(540.0, 170.0 * ratio)
            display_height = display_width / ratio
            if display_height > 170.0:
                display_height = 170.0
                display_width = display_height * ratio
        else:
            display_width, display_height = 260.0, 170.0

        area = QRectF(
            (560.0 - display_width) / 2,
            (180.0 - display_height) / 2,
            display_width,
            display_height,
        )

        background_value = (
            custom_color.text().strip()
            if background.currentData() == "custom"
            else background.currentData()
        )

        if background_value == "none":
            painter.fillRect(area, QColor("#f3f3f3"))
            step = 12
            for yy in range(int(area.top()), int(area.bottom()), step):
                for xx in range(int(area.left()), int(area.right()), step):
                    if ((xx // step) + (yy // step)) % 2 == 0:
                        square = QRectF(xx, yy, step, step)
                        painter.fillRect(
                            square.intersected(area),
                            QColor("#d0d0d0"),
                        )
        else:
            backdrop = QColor(background_value)
            painter.fillRect(
                area,
                backdrop if backdrop.isValid() else QColor("white"),
            )

        if not count:
            painter.setPen(QColor("#444444"))
            painter.drawText(
                area, Qt.AlignCenter, "Add images to preview"
            )
            painter.end()
            preview_image.setPixmap(QPixmap.fromImage(image))
            return

        selected_layout = design.currentData()
        gap = max(
            1.5,
            min(12.0, spacing.value() / 20.0),
        )

        # Slots are relative coordinates on the preview canvas.
        # The actual composition is still owned by kim_all.
        slots = []

        if selected_layout in ("grid", "filmstrip"):
            if selected_layout == "filmstrip":
                cols = min(4, count)
            else:
                cols = 1
                while cols * cols * 2 < count * 3:
                    cols += 1
                cols = min(cols, count)

            rows = (count + cols - 1) // cols

            for index in range(count):
                col = index % cols
                row = index // cols
                slots.append((
                    col / cols,
                    row / rows,
                    1 / cols,
                    1 / rows,
                ))

        elif selected_layout == "hero":
            if count == 1:
                slots = [(0, 0, 1, 1)]
            else:
                slots.append((0, 0, 0.56, 1))
                remaining = count - 1
                cols = 1 if remaining <= 2 else 2
                rows = (remaining + cols - 1) // cols

                for index in range(remaining):
                    col = index % cols
                    row = index // cols
                    slots.append((
                        0.56 + col * 0.44 / cols,
                        row / rows,
                        0.44 / cols,
                        1 / rows,
                    ))

        elif selected_layout == "mosaic":
            rows = (count + 2) // 3

            for index in range(count):
                group = index // 3
                within = index % 3

                if within == 0:
                    slots.append((
                        0,
                        group / rows,
                        0.66,
                        1 / rows,
                    ))
                else:
                    slots.append((
                        0.66,
                        group / rows
                        + (within - 1) / (2 * rows),
                        0.34,
                        1 / (2 * rows),
                    ))

        else:
            # Scattered placement uses random geometry in the
            # renderer. This preview is deliberately schematic.
            columns = max(1, min(4, count))
            rows = (count + columns - 1) // columns

            for index in range(count):
                col = index % columns
                row = index // columns

                slots.append((
                    0.04 + col * 0.87 / columns,
                    0.05 + row * 0.87 / rows,
                    0.94 / columns,
                    0.94 / rows,
                ))

        def draw_tile(index, slot):
            sx, sy, sw, sh = slot

            tile = QRectF(
                area.x() + sx * area.width() + gap / 2,
                area.y() + sy * area.height() + gap / 2,
                max(1.0, sw * area.width() - gap),
                max(1.0, sh * area.height() - gap),
            )

            if shadow.isChecked():
                painter.fillRect(
                    tile.translated(2, 3),
                    QColor(0, 0, 0, 70),
                )

            frame_style = borders.currentData()

            if frame_style == "polaroid":
                painter.fillRect(tile, QColor("white"))
                content = tile.adjusted(
                    3, 3, -3, -max(6.0, tile.height() * 0.16)
                )
            elif frame_style == "thin":
                painter.fillRect(tile, QColor("white"))
                content = tile.adjusted(2, 2, -2, -2)
            else:
                content = tile

            painter.fillRect(content, QColor("#999999"))

            thumbnail = dialog.ordered.thumbnails.get(paths[index])

            if thumbnail is not None and not thumbnail.isNull():
                iw = thumbnail.width()
                ih = thumbnail.height()

                if iw > 0 and ih > 0:
                    source_rect = QRectF(0, 0, iw, ih)

                    if placement.currentData() == "fill":
                        scale = max(
                            content.width() / iw,
                            content.height() / ih,
                        )
                        crop_width = content.width() / scale
                        crop_height = content.height() / scale

                        source_rect = QRectF(
                            (iw - crop_width) / 2,
                            (ih - crop_height) / 2,
                            crop_width,
                            crop_height,
                        )
                        target = content
                    else:
                        scale = min(
                            content.width() / iw,
                            content.height() / ih,
                        )
                        target_width = iw * scale
                        target_height = ih * scale

                        target = QRectF(
                            content.center().x() - target_width / 2,
                            content.center().y() - target_height / 2,
                            target_width,
                            target_height,
                        )

                    painter.drawImage(
                        target, thumbnail, source_rect
                    )
            else:
                painter.setPen(QColor("#ffffff"))
                painter.drawText(
                    content, Qt.AlignCenter,
                    str(index + 1),
                )

            painter.setPen(QPen(QColor("#555555"), 0.6))
            painter.drawRect(tile)

        for index, slot in enumerate(slots):
            draw_tile(index, slot)

        painter.end()
        preview_image.setPixmap(QPixmap.fromImage(image))

        if selected_layout == "scattered":
            note = (
                "Illustrative preview. Scattered/Polaroid uses "
                "randomized positions during final rendering."
            )
        else:
            note = (
                "Approximate composition using cached thumbnails. "
                "Final rendering may differ."
            )

        if shuffle.isChecked():
            note += (
                " Shuffle is enabled, so final image order "
                "will be randomized."
            )

        preview_note.setText(note)

    # All updates are GUI-thread-only and use existing cached
    # thumbnails. No additional decoding or rendering workers.
    for widget in (
        design, canvas, placement, borders, background,
    ):
        widget.currentIndexChanged.connect(refresh_preview)

    for widget in (spacing,):
        widget.valueChanged.connect(refresh_preview)

    for widget in (custom_canvas, custom_color):
        widget.textChanged.connect(refresh_preview)

    for widget in (shadow, shuffle):
        widget.toggled.connect(refresh_preview)

    dialog.ordered.changed.connect(refresh_preview)
    dialog.ordered.thumbnail_changed.connect(refresh_preview)

    refresh_preview()

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )

    dialog.create = buttons.button(QDialogButtonBox.Ok)
    dialog.create.setText("Create")

    dialog.add_source_notice(layout)
    layout.addWidget(buttons)

    def update_selection(*_):
        paths = dialog.ordered.ordered_paths()
        ready, blocked, pending = dialog.ordered.counts()
        count = len(paths)

        selection_status.setText(
            f"{count} selected images · "
            f"{ready} ready · "
            f"{blocked} blocked · "
            f"{pending} inspecting"
            + (
                "\nRemove or replace blocked images."
                if blocked else ""
            )
        )

        dialog.create.setEnabled(
            count > 0
            and ready == count
            and blocked == 0
            and pending == 0
            and dialog.ordered.worker is None
            and dialog.finish_result is None
        )

    dialog.ordered.changed.connect(update_selection)
    dialog.ordered.add_paths(pictures)
    update_selection()

    def accept():
        update_selection()

        if not dialog.create.isEnabled():
            return

        if not dialog.ordered.validate_sources():
            update_selection()
            return

        selected_images = dialog.ordered.ordered_paths()

        if not selected_images:
            return
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
            *selected_images,
        ]

        # Final source advisories and identities are checked before
        # returning approved, ordered paths to the renderer.
        try:
            if not dialog.source_notice.approve(selected_images):
                return

            destination.write_bytes(
                b"".join(
                    os.fsencode(value) + b"\0"
                    for value in values
                )
            )

        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                dialog,
                "Cannot approve collage settings",
                str(exc),
            )
            return

        # OrderedImageDialog owns worker shutdown and cancellation.
        dialog.done(QDialog.Accepted)

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
