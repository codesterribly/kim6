#!/usr/bin/env python3
"""KIMng PDF embedded-image extraction, reviewed and create-only."""

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy,
)

from kim_dialog_buttons import style_button
from kim_pdf_pages import (
    PDFError, identity, inspect_pdf, open_source,
    validate_pdf_selection,
    KDialogBatchProgress,
)


ACTION = "Extract embedded images from PDF"

# The listing is produced by Poppler. Keep parsing fail-closed.
IMAGE_LINE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+"
    r"(image|mask|smask|stencil)\s+"
    r"(\d+)\s+(\d+)\s+"
    r"(\S+)\s+(\d+)\s+(\d+)\s+(\S+)\b"
)

# JPEG/JP2 are retained in their native encoded form.
# Other raster images use PNG, except CMYK uses TIFF.
EXTRACTION_OPTIONS = (
    "-png", "-tiff", "-j", "-jp2"
)


def extension_for(record):
    encoding = record["encoding"].lower()
    color = record["color"].lower()

    if encoding == "jpeg":
        return "jpg"
    if encoding == "jp2":
        return "jp2"
    if color == "cmyk":
        return "tif"
    return "png"


def run_poppler(source, args, progress=None):
    """Read via O_NOATIME stdin; stop owned processes on cancellation."""
    fd = open_source(source["path"])

    try:
        with tempfile.TemporaryFile() as stdout:
            with tempfile.TemporaryFile() as stderr:
                process = subprocess.Popen(
                    args,
                    stdin=fd,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=True,
                )

                try:
                    while process.poll() is None:
                        QApplication.processEvents()

                        if progress and progress.cancelled():
                            raise PDFError("Operation cancelled.")

                        time.sleep(0.08)

                    stdout.seek(0)
                    stderr.seek(0)

                    output = stdout.read()
                    errors = stderr.read(1200)

                    if process.returncode:
                        raise PDFError(
                            errors.decode(
                                "utf-8", "replace"
                            ).strip()
                            or "PDF extraction failed."
                        )

                    return output.decode(
                        "utf-8", "replace"
                    )

                except BaseException:
                    if process.poll() is None:
                        try:
                            os.killpg(
                                process.pid, signal.SIGTERM
                            )
                        except ProcessLookupError:
                            pass

                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            try:
                                os.killpg(
                                    process.pid, signal.SIGKILL
                                )
                            except ProcessLookupError:
                                pass

                    process.wait()
                    raise

    finally:
        os.close(fd)


def image_listing(source, page):
    data = run_poppler(
        source,
        [
            "pdfimages",
            "-f", str(page),
            "-l", str(page),
            "-list", "-",
        ],
    )

    records = []

    for line in data.splitlines():
        match = IMAGE_LINE.match(line)

        if not match:
            if line.strip() and line.lstrip()[0:1].isdigit():
                raise PDFError(
                    "Unrecognized PDF image listing: "
                    + line[:180]
                )
            continue

        (
            page_number, number, kind,
            width, height, color,
            components, bpc, encoding,
        ) = match.groups()

        if int(page_number) != page:
            raise PDFError(
                "Unexpected page in PDF image listing."
            )

        records.append({
            "page": page,
            "number": int(number),
            "kind": kind,
            "width": int(width),
            "height": int(height),
            "color": color,
            "components": int(components),
            "bpc": int(bpc),
            "encoding": encoding,
        })

    return records


class ExtractDialog(QDialog):
    def __init__(self, paths):
        super().__init__()

        self.sources = [inspect_pdf(p) for p in paths]
        self.plan = []
        self.signature = None
        self.listing_cache = {}

        self.setWindowTitle(
            f"KIMng - {ACTION} - Settings"
        )
        self.resize(850, 340)
        self.setMinimumWidth(740)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Ignored,
        )
        outer.addWidget(self.stack)

        self.build_settings()
        self.build_review()

        buttons = QHBoxLayout()

        self.back = QPushButton("Back")
        style_button(self.back, "back")
        self.back.clicked.connect(self.show_settings)

        buttons.addWidget(self.back)
        buttons.addStretch(1)

        self.actions = QDialogButtonBox()

        self.primary = self.actions.addButton(
            "Review Changes",
            QDialogButtonBox.AcceptRole,
        )
        style_button(self.primary, "review")
        self.primary.clicked.connect(self.advance)

        cancel = self.actions.addButton(
            QDialogButtonBox.Cancel
        )
        style_button(cancel, "cancel")
        cancel.clicked.connect(self.reject)

        buttons.addWidget(self.actions)
        outer.addLayout(buttons)

        self.show_settings()

    def destination_controls(self, layout, review=False):
        label = QLabel("Destination: Beside each source")
        layout.addWidget(label)

        row = QHBoxLayout()
        entry = QLineEdit()
        entry.setPlaceholderText(
            "Beside each source (leave empty)"
        )
        entry.setAccessibleName(
            "Output directory for all selected documents"
        )
        row.addWidget(entry, 1)

        browse = QPushButton("Change destination…")
        browse.clicked.connect(
            lambda: self.browse(entry, review)
        )
        row.addWidget(browse)

        layout.addLayout(row)
        return label, entry

    def build_settings(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(
            f"Selected PDF documents: {len(self.sources)}"
        ))

        form = QFormLayout()

        self.all_pages = QCheckBox("All pages")
        self.all_pages.setChecked(True)
        form.addRow("Pages:", self.all_pages)

        self.first = QSpinBox()
        self.first.setRange(1, 100000)

        self.last = QSpinBox()
        self.last.setRange(1, 100000)
        self.last.setValue(
            min(item["pages"] for item in self.sources)
        )

        form.addRow("First page:", self.first)
        form.addRow("Last page:", self.last)

        def range_visibility(all_selected):
            self.first.setEnabled(not all_selected)
            self.last.setEnabled(not all_selected)

        self.all_pages.toggled.connect(range_visibility)
        range_visibility(True)

        self.include_masks = QCheckBox(
            "Include image masks and transparency components"
        )
        self.include_masks.setChecked(True)
        form.addRow("", self.include_masks)

        layout.addLayout(form)

        note = QLabel(
            "Extract raster images stored inside PDF documents. "
            "JPEG and JPEG 2000 data are preserved where supported. "
            "Other encodings are written as PNG or TIFF. "
            "Masks may be separate images, not combined transparency."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        # Keep destination separated from settings without
        # creating an oversized empty area.
        layout.addSpacing(14)

        self.destination_label, self.destination = (
            self.destination_controls(layout)
        )

        self.stack.addWidget(widget)

    def build_review(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Input", "Pages", "Output",
            "Destination", "Action", "Status",
        ])

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        for column in range(6):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )

        header.setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        header.setSectionResizeMode(
            2, QHeaderView.Stretch
        )

        self.table.setColumnWidth(1, 75)
        self.table.setColumnWidth(3, 170)
        self.table.setColumnWidth(4, 115)
        self.table.setColumnWidth(5, 125)

        self.table.currentCellChanged.connect(
            lambda row, *_: self.update_details(row)
        )
        layout.addWidget(self.table, 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(95)
        self.details.setMaximumHeight(120)
        layout.addWidget(self.details)

        layout.addSpacing(14)

        self.review_label, self.review_destination = (
            self.destination_controls(layout, review=True)
        )

        self.review_destination.editingFinished.connect(
            self.destination_edited
        )

        self.stack.addWidget(widget)

    def browse(self, entry, review):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose output directory",
            entry.text().strip() or str(Path.home()),
        )
        if directory:
            entry.setText(directory)
            if review:
                self.destination_edited()

    def destination_edited(self):
        if self.stack.currentIndex() != 1:
            return

        value = self.review_destination.text().strip()
        self.destination.setText(value)
        self.populate_review()

    def settings_signature(self):
        return (
            self.all_pages.isChecked(),
            self.first.value(),
            self.last.value(),
            self.include_masks.isChecked(),
            self.destination.text().strip(),
        )

    def show_settings(self):
        self.setWindowTitle(
            f"KIMng - {ACTION} - Settings"
        )
        self.stack.setCurrentIndex(0)
        self.back.hide()
        self.primary.setText("Review Changes")
        style_button(self.primary, "review")
        self.primary.setEnabled(True)
        self.resize(850, 340)

    def create_plan(self):
        destination = self.destination.text().strip()

        if destination and not Path(destination).is_absolute():
            raise PDFError(
                "Destination must be an absolute directory."
            )

        plan = []
        reserved = set()
        self.listing_cache = {}
        self.naming_warnings = {}

        for source in self.sources:
            path = source["path"]

            if identity(path) != source["identity"]:
                raise PDFError(
                    "Source changed during review: " + path
                )

            start, end = (
                (1, source["pages"])
                if self.all_pages.isChecked()
                else (self.first.value(), self.last.value())
            )

            if start > end or end > source["pages"]:
                raise PDFError(
                    f"Invalid page range for {Path(path).name}. "
                    f"PDF has {source['pages']} pages."
                )

            folder = (
                Path(destination)
                if destination else Path(path).parent
            )

            if (
                folder.is_symlink()
                or not folder.is_dir()
                or not os.access(
                    folder, os.W_OK | os.X_OK
                )
            ):
                raise PDFError(
                    f"Destination unavailable: {folder}"
                )

            info = folder.stat()
            parent_id = (info.st_dev, info.st_ino)

            for page in range(start, end + 1):
                records = image_listing(source, page)
                self.listing_cache[(path, page)] = records

                for ordinal, record in enumerate(records):
                    if (
                        not self.include_masks.isChecked()
                        and record["kind"] != "image"
                    ):
                        continue

                    extension = extension_for(record)
                    filename = (
                        f"{Path(path).stem}-page-"
                        f"{page:03d}-image-"
                        f"{ordinal + 1:03d}.{extension}"
                    )

                    preferred = folder / filename
                    target = preferred

                    # Resolve known collisions during review,
                    # never during publication after approval.
                    suffix_number = 1

                    while (
                        str(target) in reserved
                        or os.path.lexists(target)
                    ):
                        if suffix_number > 9999:
                            raise PDFError(
                                "Cannot find an available output "
                                "filename for " + str(preferred)
                            )

                        target = folder / (
                            f"{preferred.stem}_{suffix_number}"
                            f"{preferred.suffix}"
                        )
                        suffix_number += 1

                    if target != preferred:
                        self.naming_warnings[str(target)] = (
                            "Existing filename: "
                            + preferred.name
                            + "\nProposed unique filename: "
                            + target.name
                            + "\nThe existing file will not be changed."
                        )

                    reserved.add(str(target))

                    plan.append((
                        source, page, ordinal, record,
                        target, parent_id,
                    ))

                    if len(plan) > 2000:
                        raise PDFError(
                            "More than 2,000 extracted outputs. "
                            "Choose a smaller page range."
                        )

        return plan

    def update_details(self, row):
        if row < 0 or row >= len(self.plan):
            self.details.clear()
            return

        source, page, ordinal, image, target, _ = (
            self.plan[row]
        )

        details = [
            f"PDF page: {page} of {source['pages']}",
            f"Embedded image: {ordinal + 1}",
            f"Dimensions: {image['width']} × {image['height']}",
            f"Encoding: {image['encoding']}",
            f"Color space: {image['color']}",
            f"Type: {image['kind']}",
        ]

        if image["kind"] != "image":
            details.append(
                "Mask or stencil extracted separately. "
                "Transparency is not recomposited."
            )

        naming_note = self.naming_warnings.get(
            str(target)
        )

        if naming_note:
            details.extend([
                "",
                "Filename collision:",
                naming_note,
            ])

        self.details.setPlainText("\n".join(details))

    def populate_review(self):
        try:
            plan = self.create_plan()
        except (PDFError, OSError) as exc:
            self.plan = []
            self.signature = None
            self.table.setRowCount(0)
            self.primary.setEnabled(False)
            self.summary.setText(
                "Review blocked: " + str(exc)
            )
            self.details.clear()
            return

        self.plan = plan
        self.signature = self.settings_signature()

        self.table.setRowCount(len(plan))

        for index, row in enumerate(plan):
            source, page, ordinal, image, target, _ = row

            values = (
                Path(source["path"]).name,
                str(page),
                target.name,
                str(target.parent),
                "Extract image",
                (
                    "Ready (renamed)"
                    if str(target) in self.naming_warnings
                    else "Ready"
                ),
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)

        self.summary.setText(
            f"Selected: {len(self.sources)} PDF documents  |  "
            f"Ready: {len(plan)}  |  "
            "Skipped: 0  |  "
            f"Warnings: {len(self.naming_warnings)}  |  "
            "Blocked: 0"
        )

        current = self.destination.text().strip()

        self.review_label.setText(
            "Destination: " + (
                current or "Beside each source"
            )
        )

        self.review_destination.blockSignals(True)
        self.review_destination.setText(current)
        self.review_destination.blockSignals(False)

        self.primary.setEnabled(bool(plan))

        if plan:
            self.table.selectRow(0)
            self.update_details(0)
        else:
            self.details.setPlainText(
                "No embedded raster images matched "
                "the selected pages and options."
            )

    def advance(self):
        if self.stack.currentIndex() == 1:
            self.apply_changes()
            return

        self.setWindowTitle(
            f"KIMng - {ACTION} - Review Changes"
        )
        self.stack.setCurrentIndex(1)
        self.back.show()

        self.primary.setText("Apply Changes")
        style_button(self.primary, "apply")

        self.resize(1080, 530)
        self.populate_review()

    def apply_changes(self):
        progress = None
        published = 0

        try:
            if (
                self.settings_signature() != self.signature
                or self.create_plan() != self.plan
            ):
                raise PDFError(
                    "Review plan changed. Review again."
                )

            # Group one PDF page into one extraction invocation.
            groups = defaultdict(list)

            for row in self.plan:
                groups[(row[0]["path"], row[1])].append(row)

            progress = KDialogBatchProgress(
                len(self.plan), ACTION
            )

            for (path, page), rows in groups.items():
                source = rows[0][0]

                if identity(path) != source["identity"]:
                    raise PDFError(
                        "Source changed after review: " + path
                    )

                parent = rows[0][4].parent
                current = parent.stat()

                if (
                    current.st_dev,
                    current.st_ino,
                ) != rows[0][5]:
                    raise PDFError(
                        "Destination directory changed."
                    )

                stage = Path(tempfile.mkdtemp(
                    prefix=".kimng-pdf-extract-",
                    dir=parent,
                ))

                try:
                    root = stage / "asset"

                    first_target = rows[0][4]

                    progress.status.start(
                        path, published + 1
                    )
                    progress.stage(
                        source, page, first_target,
                        "Extracting embedded images"
                    )

                    run_poppler(
                        source,
                        [
                            "pdfimages",
                            "-f", str(page),
                            "-l", str(page),
                            *EXTRACTION_OPTIONS,
                            "-", str(root),
                        ],
                        progress,
                    )

                    extracted = []

                    for candidate in stage.iterdir():
                        match = re.fullmatch(
                            r"asset-(\d+)\."
                            r"(png|tif|jpg|jp2)",
                            candidate.name,
                        )
                        if not match:
                            raise PDFError(
                                "Unexpected extracted artifact: "
                                + candidate.name
                            )

                        extracted.append((
                            int(match.group(1)),
                            candidate,
                        ))

                    extracted.sort(key=lambda item: item[0])

                    expected_records = self.listing_cache[
                        (path, page)
                    ]

                    if len(extracted) != len(expected_records):
                        raise PDFError(
                            "PDF image listing and extracted "
                            "image count disagree."
                        )

                    for ordinal, (_, candidate) in enumerate(extracted):
                        expected_ext = extension_for(
                            expected_records[ordinal]
                        )

                        if candidate.suffix.lower() != (
                            "." + expected_ext
                        ):
                            raise PDFError(
                                "PDF image encoding differed "
                                "from the approved review."
                            )

                    for row in rows:
                        source, page, ordinal, image, target, parent_id = row

                        if progress.cancelled():
                            raise PDFError(
                                "Operation cancelled."
                            )

                        candidate = extracted[ordinal][1]

                        progress.status.start(
                            path, published + 1
                        )
                        progress.stage(
                            source, page, target,
                            "Validating extracted image"
                        )

                        if (
                            not candidate.is_file()
                            or candidate.is_symlink()
                            or candidate.stat().st_size == 0
                        ):
                            raise PDFError(
                                "Extracted image missing or empty."
                            )

                        # Fail closed on unrecognized output.
                        result = subprocess.run(
                            [
                                "identify", "-ping",
                                "-format", "%m %w %h",
                                str(candidate),
                            ],
                            capture_output=True,
                            text=True,
                        )

                        if result.returncode:
                            raise PDFError(
                                "Extracted image validation failed: "
                                + candidate.name
                            )

                        if identity(path) != source["identity"]:
                            raise PDFError(
                                "Source changed during extraction."
                            )

                        current = target.parent.stat()

                        if (
                            (current.st_dev, current.st_ino) != parent_id
                            or os.path.lexists(target)
                        ):
                            raise PDFError(
                                "Destination changed or "
                                "output filename occupied: "
                                + str(target)
                            )

                        if progress.cancelled():
                            raise PDFError(
                                "Operation cancelled."
                            )

                        progress.stage(
                            source, page, target,
                            "Publishing extracted image"
                        )

                        # Create-only, atomic visibility.
                        os.link(candidate, target)

                        published += 1
                        progress.status.finish({
                            "ok": True,
                            "output": str(target),
                        })
                        progress.value(published)

                finally:
                    shutil.rmtree(stage)

            # Successful completion needs no additional
            # confirmation. Close progress and return to Dolphin.
            progress.close()
            progress = None
            self.accept()

        except (
            PDFError, OSError, subprocess.TimeoutExpired
        ) as exc:
            cancelled = bool(
                progress and progress.status.cancelling
            )

            remaining = max(
                0, len(self.plan) - published
            )

            QMessageBox.warning(
                self,
                f"KIMng - {ACTION}",
                f"{exc}\n\n"
                f"Succeeded: {published}\n"
                f"Failed: {0 if cancelled else 1}\n"
                f"Cancelled: {1 if cancelled else 0}\n"
                f"Not completed: {remaining}\n\n"
                "Previously published outputs remain.\n"
                "Original PDF documents are unchanged.",
            )

        finally:
            if progress:
                progress.close()


def main():
    app = QApplication(sys.argv)

    missing = [
        command for command in (
            "pdfinfo", "pdfimages", "identify",
        )
        if not shutil.which(command)
    ]

    if missing:
        QMessageBox.critical(
            None,
            f"KIMng - {ACTION}",
            "Missing utilities: "
            + ", ".join(missing)
            + "\nInstall poppler-utils.",
        )
        return 1

    paths = [
        value for value in sys.argv[1:]
        if value != "--"
    ]

    if not paths:
        QMessageBox.warning(
            None,
            f"KIMng - {ACTION}",
            "Select one or more PDF documents.",
        )
        return 1

    try:
        from kim_pdf_pages import (
            inspect_pdf_selection,
            build_pdf_selection_settings,
        )

        inspected = inspect_pdf_selection(paths)

        if any(reason for _, _, reason in inspected):
            dialog = build_pdf_selection_settings(
                inspected,
                ACTION,
                ExtractDialog,
            )
            dialog.exec()
            return 1

        dialog = ExtractDialog(paths)
        return (
            0 if dialog.exec() == QDialog.Accepted
            else 1
        )
    except (PDFError, OSError) as exc:
        QMessageBox.critical(
            None, f"KIMng - {ACTION}", str(exc)
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
