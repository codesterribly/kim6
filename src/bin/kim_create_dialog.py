#!/usr/bin/env python3
"""KIM6 graphical creation settings for GIF/APNG animations and HTML galleries.

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


def slideshow_dialog(args):
    """Collect slideshow settings only; the shell verifies and publishes."""
    import re

    result_path, starting_dir, count_text, seconds_text, size, fps_text, color, output = args

    try:
        count, seconds, fps = int(count_text), int(seconds_text), int(fps_text)
    except ValueError:
        return 2

    if not (1 <= count <= 200 and 1 <= seconds <= 30 and 1 <= fps <= 30):
        return 2

    app = QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Create Video Slideshow")
    dialog.setMinimumWidth(560)

    outer = QVBoxLayout(dialog)
    outer.addWidget(QLabel(f"{count} selected image(s)"))

    form = QFormLayout()
    outer.addLayout(form)

    duration = QSpinBox()
    duration.setRange(1, 30)
    duration.setValue(seconds)
    form.addRow("Seconds per image:", duration)

    resolution = QComboBox()
    for label, value in (
        ("854 × 480 (SD)", "854x480"),
        ("1280 × 720 (HD)", "1280x720"),
        ("1920 × 1080 (Full HD)", "1920x1080"),
    ):
        resolution.addItem(label, value)

    index = resolution.findData(size)
    if index >= 0:
        resolution.setCurrentIndex(index)

    form.addRow("Video dimensions:", resolution)

    frame_rate = QSpinBox()
    frame_rate.setRange(1, 30)
    frame_rate.setValue(fps)
    form.addRow("Frame rate (FPS):", frame_rate)

    background = QComboBox()

    for value in (
        "black", "white", "gray", "grey", "navy", "red",
        "green", "blue", "yellow", "orange", "purple"
    ):
        background.addItem(value.title(), value)

    background.addItem("Custom color (#RRGGBB)", "custom")

    custom_color = QLineEdit(
        color if color.startswith("#") else "#202020"
    )

    form.addRow("Background:", background)
    form.addRow("Custom color:", custom_color)

    color_index = background.findData(
        "custom" if color.startswith("#") else color
    )
    if color_index >= 0:
        background.setCurrentIndex(color_index)

    def show_color():
        form.setRowVisible(
            custom_color,
            background.currentData() == "custom"
        )

    background.currentIndexChanged.connect(show_color)
    show_color()

    summary = QLabel()
    summary.setWordWrap(True)
    outer.addWidget(summary)

    def refresh():
        total = count * duration.value()
        summary.setText(
            f"{count} images × {duration.value()} seconds = "
            f"{total // 60}:{total % 60:02d} total; "
            f"approximately {total * frame_rate.value():,} frames. "
            "Images play in natural filename order."
        )

    duration.valueChanged.connect(refresh)
    frame_rate.valueChanged.connect(refresh)
    refresh()

    proposed = output or os.path.join(starting_dir, "slideshow.mp4")

    if not output and os.path.lexists(proposed):
        for number in range(1, 10001):
            candidate = os.path.join(
                starting_dir, f"slideshow_{number}.mp4"
            )
            if not os.path.lexists(candidate):
                proposed = candidate
                break
        else:
            return 2

    destination = QLineEdit(proposed)
    browse = QPushButton("Browse…")

    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.addWidget(destination)
    row_layout.addWidget(browse)

    form.addRow("Save MP4 as:", row)

    def browse_file():
        path, _ = QFileDialog.getSaveFileName(
            dialog,
            "Save MP4 Slideshow",
            destination.text(),
            "MP4 video (*.mp4)"
        )
        if path:
            destination.setText(path)

    browse.clicked.connect(browse_file)

    note = QLabel(
        "Silent H.264 video. Images retain their proportions; "
        "existing files will not be overwritten."
    )
    note.setWordWrap(True)
    outer.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    outer.addWidget(buttons)

    def accept():
        seconds = duration.value()
        total = count * seconds

        if total > 600 or total * frame_rate.value() > 18000:
            QMessageBox.warning(
                dialog,
                "Slideshow limits",
                "Maximum 600 seconds and 18,000 frames. "
                "Reduce duration or frame rate."
            )
            return

        target = destination.text().strip()

        if not target:
            QMessageBox.warning(
                dialog,
                "Destination required",
                "Choose an MP4 filename."
            )
            return

        target = os.path.abspath(os.path.expanduser(target))

        if not os.path.splitext(target)[1]:
            target += ".mp4"

        if not target.lower().endswith(".mp4"):
            QMessageBox.warning(
                dialog,
                "Invalid extension",
                "Use a .mp4 filename."
            )
            return

        if (
            not os.path.isdir(os.path.dirname(target))
            or os.path.lexists(target)
        ):
            QMessageBox.warning(
                dialog,
                "Invalid destination",
                "Choose an existing directory and an unused filename."
            )
            return

        selected_color = background.currentData()

        if selected_color == "custom":
            selected_color = custom_color.text().strip()

            if not re.fullmatch(
                r"#[0-9a-fA-F]{6}", selected_color
            ):
                QMessageBox.warning(
                    dialog,
                    "Invalid background",
                    "Enter a color like #202020."
                )
                return

        values = (
            str(seconds),
            resolution.currentData(),
            str(frame_rate.value()),
            selected_color,
            target
        )

        with open(result_path, "wb") as stream:
            for value in values:
                stream.write(value.encode("utf-8") + b"\0")

        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)

    return 0 if dialog.exec() == QDialog.Accepted else 1


def main():
    if len(sys.argv) == 10 and sys.argv[1] == "slideshow":
        return slideshow_dialog(sys.argv[2:])
    if len(sys.argv) != 5:
        return 2

    kind, result_path, starting_dir, image_count = sys.argv[1:]
    if kind not in ("gif", "gallery"):
        return 2

    app = QApplication(sys.argv)

    dialog = QDialog()
    dialog.setWindowTitle(
        "KIM6 — Create Animated GIF/APNG"
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
        choice("format", "Output format:", [
            ("Animated GIF", "gif"),
            ("Animated PNG (APNG)", "apng"),
        ])
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
        "Save animation as:" if kind == "gif" else "Create gallery in:",
        destination_row,
    )

    if kind == "gif":
        def change_format():
            name, extension = os.path.splitext(destination.text())
            if extension.lower() in (".gif", ".png"):
                ending = ".gif" if fields["format"].currentData() == "gif" else ".png"
                destination.setText(name + ending)
        fields["format"].currentIndexChanged.connect(change_format)

    def browse_destination():
        if kind == "gif":
            is_gif = fields["format"].currentData() == "gif"
            value, _ = QFileDialog.getSaveFileName(
                dialog,
                "Save Animated GIF" if is_gif else "Save Animated PNG",
                destination.text(),
                "Animated GIF (*.gif)" if is_gif else "Animated PNG (*.png)",
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
        "GIF supports indexed color. APNG supports full-color RGBA and transparency. "
        "Existing files will not be overwritten; new outputs are numbered when needed."
        if kind == "gif" else
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
            suffix = ".gif" if fields["format"].currentData() == "gif" else ".png"
            name, old_suffix = os.path.splitext(target)
            if old_suffix.lower() not in ("", ".gif", ".png"):
                QMessageBox.warning(
                    dialog, "Invalid extension",
                    "Use " + suffix + " for this format."
                )
                return
            target = (name + suffix) if old_suffix else (target + suffix)
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
            if fields["format"].currentData() == "apng":
                if fields["delay"].value() < 1 or int(image_count) < 2:
                    QMessageBox.warning(
                        dialog, "Invalid APNG settings",
                        "APNG needs at least two selected images "
                        "and a nonzero frame delay."
                    )
                    return
            values = [
                fields["format"].currentData(),
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
