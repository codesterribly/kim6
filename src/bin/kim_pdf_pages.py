#!/usr/bin/env python3
"""KIMng PDF page conversion. Sources remain unchanged."""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QAbstractItemView, QPlainTextEdit
from kim_dialog_buttons import style_button
from kim_job import JobStatus
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout,
    QLabel, QMessageBox, QProgressDialog, QPushButton,
    QSpinBox, QStackedWidget, QTableWidget, QHBoxLayout,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)


class PDFError(Exception):
    pass


def identity(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PDFError(f"Not an independent regular file: {path}")
    return (
        info.st_dev, info.st_ino, info.st_size,
        info.st_atime_ns, info.st_mtime_ns,
        info.st_ctime_ns, info.st_mode,
    )


def open_source(path):
    try:
        return os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NOATIME
        )
    except OSError as exc:
        raise PDFError(
            f"Cannot safely open PDF without changing atime: "
            f"{path}: {exc}"
        ) from exc


def execute_pdf(source, arguments, progress=None):
    fd = open_source(source)
    try:
        # Feed the O_NOATIME descriptor directly to Poppler.
        # Reopening /proc/self/fd can update source atime.
        command = [*arguments, "-"]
        process = subprocess.Popen(
            command,
            stdin=fd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        while process.poll() is None:
            QApplication.processEvents()
            if progress and progress.wasCanceled():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                process.communicate()
                raise PDFError("Operation cancelled.")
            time.sleep(0.05)

        output, errors = process.communicate()
        if process.returncode:
            raise PDFError(
                errors.decode("utf-8", "replace")[:700]
                or "PDF processing failed."
            )
        return output.decode("utf-8", "replace")
    finally:
        os.close(fd)


def validate_pdf_source(path):
    """Reject non-PDF inputs before launching any PDF utility."""
    path = str(Path(path).absolute())

    if "\\n" in path or "\\r" in path:
        raise PDFError(
            "Filenames containing line breaks are unsupported."
        )

    if Path(path).suffix.lower() != ".pdf":
        raise PDFError(
            f"{Path(path).name}: Not a PDF document "
            "(requires a .pdf file)."
        )

    before = identity(path)

    fd = open_source(path)
    try:
        header = os.read(fd, 8)
    finally:
        os.close(fd)

    if identity(path) != before:
        raise PDFError(
            f"{Path(path).name}: Source changed during validation."
        )

    if not (
        len(header) == 8
        and header.startswith(b"%PDF-")
        and header[5:6] in (b"1", b"2")
        and header[6:7] == b"."
        and header[7:8] in tuple(
            bytes((digit,)) for digit in range(48, 58)
        )
    ):
        raise PDFError(
            f"{Path(path).name}: Not a valid PDF file header. "
            "The file may be incorrectly named or damaged."
        )

    return before


def validate_pdf_selection(paths):
    """Reject an invalid batch before opening Settings."""
    problems = []

    for path in paths:
        try:
            validate_pdf_source(path)
        except (PDFError, OSError) as exc:
            problems.append(str(exc))

    if problems:
        display = problems[:10]

        if len(problems) > len(display):
            display.append(
                f"...and {len(problems) - len(display)} more."
            )

        raise PDFError(
            "PDF documents only.\\n\\n"
            "Unsupported selections:\\n"
            + "\\n".join(display)
            + "\\n\\nNo files were processed."
        )


def inspect_pdf(path):
    path = str(Path(path).absolute())
    if "\n" in path or "\r" in path:
        raise PDFError("Filenames containing line breaks are unsupported.")

    before = validate_pdf_source(path)
    information = execute_pdf(path, ["pdfinfo"])
    match = re.search(
        r"^Pages:\s+(\d+)\s*$", information, re.MULTILINE
    )
    if not match or int(match.group(1)) < 1:
        raise PDFError(f"Cannot determine page count: {path}")

    if re.search(
        r"^Encrypted:\s+yes", information, re.MULTILINE
    ):
        raise PDFError(
            f"Encrypted PDFs are not supported: {path}"
        )

    if identity(path) != before:
        raise PDFError(f"Source changed during inspection: {path}")

    return {
        "path": path,
        "identity": before,
        "pages": int(match.group(1)),
    }



class KDialogBatchProgress:
    """KIMng KDialog progress using the existing job status model."""

    SERVICE_PATTERN = re.compile(
        r"(?::[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+"
        r"|[A-Za-z_-][A-Za-z0-9_-]*"
        r"(?:\.[A-Za-z_-][A-Za-z0-9_-]*)+)\Z"
    )

    OBJECT_PATTERN = re.compile(
        r"/(?:[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)?\Z"
    )

    def __init__(self, total, action="Convert PDF pages to images"):
        self.ref = None
        self.status = JobStatus(action, total)

        self.bus = (
            shutil.which("qdbus")
            or shutil.which("qdbus6")
            or (
                "/usr/lib/qt6/bin/qdbus"
                if Path("/usr/lib/qt6/bin/qdbus").is_file()
                else None
            )
        )

        if not self.bus or not shutil.which("kdialog"):
            raise PDFError(
                "KDialog or QtDBus is unavailable."
            )

        result = subprocess.run(
            [
                "kdialog",
                "--title",
                f"KIMng - {action} - Progress",
                "--cancel-label", "Cancel All",
                "--progressbar",
                "Preparing PDF conversion…",
                str(total),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )

        parts = result.stdout.strip().split()

        if len(parts) != 2:
            raise PDFError(
                "KDialog returned an unexpected progress reference: "
                + repr(result.stdout.strip()[:200])
            )

        service, object_path = parts

        # Match the same named and unique D-Bus service forms
        # accepted by kim_all's progress_parse_ref().
        valid = (
            self.SERVICE_PATTERN.fullmatch(service)
            and self.OBJECT_PATTERN.fullmatch(object_path)
        )

        if not valid:
            # Best-effort cleanup of the window just opened.
            # Never use killall or close unrelated KDialog jobs.
            try:
                subprocess.run(
                    [self.bus, service, object_path, "close"],
                    capture_output=True,
                    timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

            raise PDFError(
                "KDialog returned an unsupported progress reference: "
                + repr(result.stdout.strip()[:200])
            )

        # Register ownership before any further initialization.
        # Every subsequent failure closes this exact window.
        self.ref = [service, object_path]

        try:
            if result.returncode:
                raise PDFError(
                    "KDialog could not initialize its progress window."
                )

            self.call("showCancelButton", "true")

            self.call(
                "org.freedesktop.DBus.Properties.Set",
                "org.kde.kdialog.ProgressDialog",
                "autoClose", "false",
            )

            self.value(0)

        except Exception:
            self.close()
            raise

    def call(self, *arguments):
        if not self.ref:
            raise PDFError("Progress dialog is closed.")

        try:
            result = subprocess.run(
                [self.bus, *self.ref, *arguments],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PDFError(
                "KIMng progress communication failed."
            ) from exc

        if result.returncode:
            raise PDFError(
                "KIMng progress communication failed: "
                + result.stderr.strip()[:300]
            )

        return result.stdout.strip()

    def cancelled(self):
        QApplication.processEvents()

        state = self.call("wasCancelled")

        if state == "true":
            self.status.cancelling = True
            return True

        if state == "false":
            return False

        raise PDFError(
            "Unexpected KDialog cancellation response."
        )

    def value(self, completed):
        self.call(
            "org.freedesktop.DBus.Properties.Set",
            "org.kde.kdialog.ProgressDialog",
            "value", str(completed),
        )

    def stage(self, source, page, output, stage):
        self.status.stage = stage

        label = (
            self.status.label()
            + f"\nPDF page: {page} of {source['pages']}"
            + f"\nOutput: {output.name}"
        )

        self.call("setLabelText", label)

    def close(self):
        reference = self.ref
        self.ref = None

        if reference:
            try:
                subprocess.run(
                    [self.bus, *reference, "close"],
                    capture_output=True,
                    timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass


class PDFPagesDialog(QDialog):
    ACTION = "Convert PDF pages to images"

    def __init__(self, paths):
        super().__init__()
        self.sources = [inspect_pdf(p) for p in paths]
        self.plan = []
        self.review_signature = None
        self.shared_directory = ""

        self.setWindowTitle(f"KIMng - {self.ACTION} - Settings")
        self.resize(860, 380)
        self.setMinimumWidth(750)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.create_settings()
        self.create_review()

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

    def create_settings(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(
            f"Selected PDF documents: {len(self.sources)}"
        ))

        form = QFormLayout()

        self.output_format = QComboBox()
        self.output_format.addItems([
            "PNG (lossless)", "JPEG", "TIFF (lossless)"
        ])
        form.addRow("Output format:", self.output_format)

        self.dpi_presets = QComboBox()

        for label, value in (
            ("72 DPI", 72),
            ("96 DPI", 96),
            ("150 DPI", 150),
            ("200 DPI", 200),
            ("300 DPI", 300),
            ("600 DPI", 600),
        ):
            self.dpi_presets.addItem(label, value)

        self.dpi_presets.addItem("Custom…", None)
        self.dpi_presets.setCurrentIndex(4)

        self.dpi = QSpinBox()
        self.dpi.setRange(36, 1200)
        self.dpi.setValue(300)
        self.dpi.setSuffix(" DPI")
        self.dpi.hide()

        resolution_row = QHBoxLayout()
        resolution_row.addWidget(self.dpi_presets, 1)
        resolution_row.addWidget(self.dpi)

        def resolution_changed(index):
            selected = self.dpi_presets.itemData(index)
            custom = selected is None

            if not custom:
                self.dpi.setValue(int(selected))

            self.dpi.setVisible(custom)
            self.dpi.setEnabled(custom)

        self.dpi_presets.currentIndexChanged.connect(
            resolution_changed
        )

        resolution_changed(self.dpi_presets.currentIndex())
        form.addRow("Resolution:", resolution_row)

        self.all_pages = QCheckBox("All pages")
        self.all_pages.setChecked(True)
        form.addRow("Pages:", self.all_pages)

        self.first = QSpinBox()
        self.first.setRange(1, 100000)
        self.last = QSpinBox()
        self.last.setRange(1, 100000)
        self.last.setValue(
            min(s["pages"] for s in self.sources)
        )

        form.addRow("First page:", self.first)
        form.addRow("Last page:", self.last)

        self.first.setEnabled(False)
        self.last.setEnabled(False)

        def toggle_range(checked):
            self.first.setEnabled(not checked)
            self.last.setEnabled(not checked)

        self.all_pages.toggled.connect(toggle_range)

        layout.addLayout(form)
        layout.addStretch(1)
        layout.addSpacing(14)

        layout.addWidget(QLabel("Destination: Beside each source"))

        self.destination_entry = QLineEdit()
        self.destination_entry.setPlaceholderText(
            "Beside each source (leave empty)"
        )
        self.destination_entry.setAccessibleName(
            "Shared destination directory"
        )

        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination_entry, 1)

        browse = QPushButton("Change destination…")
        browse.clicked.connect(
            lambda: self.choose_destination(self.destination_entry)
        )
        destination_row.addWidget(browse)

        layout.addLayout(destination_row)
        self.stack.addWidget(widget)

    def create_review(self):
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
        header.setMinimumSectionSize(60)

        for index in range(6):
            header.setSectionResizeMode(
                index, QHeaderView.Interactive
            )

        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )

        self.table.setColumnWidth(3, 180)
        self.table.setColumnWidth(4, 105)

        self.table.currentCellChanged.connect(
            lambda row, *_: self.update_details(row)
        )

        layout.addWidget(self.table, 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(100)
        self.details.setMinimumHeight(78)
        layout.addWidget(self.details)

        layout.addSpacing(12)

        self.review_destination_label = QLabel()
        layout.addWidget(self.review_destination_label)

        destination_row = QHBoxLayout()

        self.review_entry = QLineEdit()
        self.review_entry.setPlaceholderText(
            "Beside each source (leave empty)"
        )
        self.review_entry.setAccessibleName(
            "Shared destination directory"
        )
        self.review_entry.textChanged.connect(
            lambda _: self.primary.setEnabled(False)
            if self.stack.currentIndex() == 1 else None
        )
        self.review_entry.editingFinished.connect(
            self.update_review_destination
        )
        destination_row.addWidget(self.review_entry, 1)

        choose = QPushButton("Change destination…")
        choose.clicked.connect(self.choose_review_destination)
        destination_row.addWidget(choose)

        layout.addLayout(destination_row)
        self.stack.addWidget(widget)

    def choose_destination(self, entry):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output directory",
            entry.text().strip() or str(Path.home()),
        )
        if folder:
            entry.setText(folder)

    def choose_review_destination(self):
        self.choose_destination(self.review_entry)
        self.update_review_destination()

    def settings_signature(self):
        return (
            self.output_format.currentIndex(),
            self.dpi_presets.currentIndex(),
            self.dpi.value(),
            self.all_pages.isChecked(),
            self.first.value(),
            self.last.value(),
            self.destination_entry.text().strip(),
        )

    def show_settings(self):
        self.setWindowTitle(f"KIMng - {self.ACTION} - Settings")
        self.stack.setCurrentIndex(0)
        self.back.hide()
        self.primary.setText("Review Changes")
        style_button(self.primary, "review")
        self.primary.setEnabled(True)
        self.resize(860, 380)

    def create_plan(self):
        destination = self.destination_entry.text().strip()

        if destination and not Path(destination).is_absolute():
            raise PDFError(
                "Destination must be an absolute directory path."
            )

        extension = ["png", "jpg", "tif"][
            self.output_format.currentIndex()
        ]

        rows = []
        reserved = set()
        self.naming_warnings = {}

        for source in self.sources:
            path = source["path"]

            if identity(path) != source["identity"]:
                raise PDFError(f"Source changed: {path}")

            if self.all_pages.isChecked():
                start, end = 1, source["pages"]
            else:
                start, end = self.first.value(), self.last.value()

            if start > end or end > source["pages"]:
                raise PDFError(
                    f"Invalid page range for {Path(path).name}. "
                    f"Document has {source['pages']} pages."
                )

            folder = Path(destination) if destination else Path(path).parent

            if (
                folder.is_symlink()
                or not folder.is_dir()
                or not os.access(folder, os.W_OK | os.X_OK)
            ):
                raise PDFError(
                    f"Output directory unavailable: {folder}"
                )

            directory = folder.stat()
            parent_id = (directory.st_dev, directory.st_ino)
            digits = max(3, len(str(source["pages"])))

            for page in range(start, end + 1):
                filename = (
                    f"{Path(path).stem}-page-"
                    f"{page:0{digits}d}.{extension}"
                )
                preferred = folder / filename
                output = preferred
                number = 1

                while (
                    str(output) in reserved
                    or os.path.lexists(output)
                ):
                    if number > 9999:
                        raise PDFError(
                            "No available output filename for: "
                            + str(preferred)
                        )

                    output = folder / (
                        f"{preferred.stem}_{number}"
                        f"{preferred.suffix}"
                    )
                    number += 1

                if output != preferred:
                    self.naming_warnings[str(output)] = (
                        "Existing filename: "
                        + preferred.name
                        + "\nPlanned unique filename: "
                        + output.name
                        + "\nThe existing file will not be changed."
                    )

                reserved.add(str(output))
                rows.append(
                    (source, page, output, parent_id, extension)
                )

                if len(rows) > 2000:
                    raise PDFError(
                        "More than 2,000 outputs requested. "
                        "Choose a smaller page range."
                    )

        return rows

    def update_review_destination(self):
        if self.stack.currentIndex() != 1:
            return

        self.destination_entry.setText(
            self.review_entry.text().strip()
        )
        self.populate_review()

    def update_details(self, index):
        if index < 0 or index >= len(self.plan):
            self.details.clear()
            return

        source, page, output, _, extension = self.plan[index]
        format_name = {
            "png": "PNG, lossless",
            "jpg": "JPEG, lossy",
            "tif": "TIFF, lossless",
        }[extension]

        details = [
            f"PDF page: {page} of {source['pages']}",
            f"Rendering: {self.dpi.value()} DPI",
            f"Output format: {format_name}",
        ]

        if extension == "jpg":
            details.append(
                "JPEG encoding is lossy and may discard detail."
            )

        details.append(
            "Output dimensions and file size are verified after rendering."
        )

        self.details.setPlainText("\n".join(details))

    def populate_review(self):
        try:
            plan = self.create_plan()
        except (PDFError, OSError) as exc:
            self.plan = []
            self.review_signature = None
            self.primary.setEnabled(False)
            self.summary.setText("Review blocked: " + str(exc))
            self.table.setRowCount(0)
            self.details.clear()
            return False

        self.plan = plan
        self.review_signature = self.settings_signature()
        self.table.setRowCount(len(plan))

        names = {
            "png": "PNG",
            "jpg": "JPEG",
            "tif": "TIFF",
        }

        for index, (source, page, output, _, extension) in enumerate(plan):
            values = [
                Path(source["path"]).name,
                f"{page} / {source['pages']}",
                output.name,
                str(output.parent),
                "PDF → " + names[extension],
                "Ready",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)

        self.summary.setText(
            f"Selected: {len(self.sources)} PDF documents  |  "
            f"Ready: {len(plan)}  |  "
            "Skipped: 0  |  Warnings: 0  |  Blocked: 0"
        )

        description = (
            self.destination_entry.text().strip()
            or "Beside each source"
        )
        self.review_destination_label.setText(
            "Destination: " + description
        )

        self.review_entry.blockSignals(True)
        self.review_entry.setText(
            self.destination_entry.text().strip()
        )
        self.review_entry.blockSignals(False)

        self.primary.setEnabled(True)
        self.table.selectRow(0)
        self.update_details(0)
        return True

    def advance(self):
        if self.stack.currentIndex() == 1:
            self.apply_changes()
            return

        self.stack.setCurrentIndex(1)
        self.setWindowTitle(
            f"KIMng - {self.ACTION} - Review Changes"
        )
        self.back.show()
        self.primary.setText("Apply Changes")
        style_button(self.primary, "apply")
        self.resize(1080, min(720, max(430, 280 + 28 * len(self.sources))))

        self.populate_review()

    def apply_changes(self):
        progress = None
        published = 0

        try:
            if (
                self.settings_signature() != self.review_signature
                or self.create_plan() != self.plan
            ):
                raise PDFError(
                    "The output plan changed. Review again before applying."
                )

            progress = KDialogBatchProgress(len(self.plan))

            for index, row in enumerate(self.plan):
                source, page, output, parent_id, fmt = row

                progress.status.start(source["path"], index + 1)

                if progress.cancelled():
                    raise PDFError("Operation cancelled.")

                if identity(source["path"]) != source["identity"]:
                    raise PDFError(
                        "Source changed after review: " + source["path"]
                    )

                parent = output.parent
                current = parent.stat()

                if (
                    (current.st_dev, current.st_ino) != parent_id
                    or os.path.lexists(output)
                ):
                    raise PDFError(
                        "Destination changed or filename occupied: "
                        + str(output)
                    )

                stage = Path(tempfile.mkdtemp(
                    prefix=".kimng-pdf-", dir=parent
                ))

                try:
                    prefix = stage / "render"
                    option = {
                        "png": "-png",
                        "jpg": "-jpeg",
                        "tif": "-tiff",
                    }[fmt]

                    progress.stage(
                        source, page, output, "Rendering PDF page"
                    )

                    fd = open_source(source["path"])
                    try:
                        command = [
                            "pdftoppm",
                            "-f", str(page),
                            "-l", str(page),
                            "-singlefile",
                            "-r", str(self.dpi.value()),
                            option,
                            "-",
                            str(prefix),
                        ]

                        with tempfile.TemporaryFile() as errors:
                            process = subprocess.Popen(
                                command,
                                stdin=fd,
                                stdout=subprocess.DEVNULL,
                                stderr=errors,
                                start_new_session=True,
                            )

                            try:
                                while process.poll() is None:
                                    QApplication.processEvents()
                                    if progress.cancelled():
                                        process.terminate()
                                        try:
                                            process.wait(timeout=2)
                                        except subprocess.TimeoutExpired:
                                            process.kill()
                                        raise PDFError("Operation cancelled.")
                                    time.sleep(0.15)

                                if process.returncode:
                                    errors.seek(0)
                                    raise PDFError(
                                        errors.read(700).decode(
                                            "utf-8", "replace"
                                        ) or "PDF rendering failed."
                                    )
                            finally:
                                if process.poll() is None:
                                    process.kill()
                                process.wait()
                    finally:
                        os.close(fd)

                    if progress.cancelled():
                        raise PDFError("Operation cancelled.")

                    rendered = Path(str(prefix) + "." + fmt)
                    if (
                        not rendered.is_file()
                        or rendered.stat().st_size == 0
                    ):
                        raise PDFError(
                            "Rendered output missing or empty."
                        )

                    progress.stage(
                        source, page, output, "Validating output image"
                    )

                    check = subprocess.run(
                        [
                            "identify", "-ping",
                            "-format", "%m %w %h",
                            str(rendered),
                        ],
                        capture_output=True,
                        text=True,
                    )

                    expected = {
                        "png": "PNG",
                        "jpg": "JPEG",
                        "tif": "TIFF",
                    }[fmt]

                    fields = check.stdout.strip().split()
                    if (
                        check.returncode != 0
                        or len(fields) != 3
                        or fields[0] != expected
                        or not all(
                            re.fullmatch(r"[1-9]\d*", part)
                            for part in fields[1:]
                        )
                    ):
                        raise PDFError(
                            "Rendered image validation failed."
                        )

                    if identity(source["path"]) != source["identity"]:
                        raise PDFError(
                            "Source changed during rendering."
                        )

                    current = parent.stat()
                    if (
                        (current.st_dev, current.st_ino) != parent_id
                        or os.path.lexists(output)
                    ):
                        raise PDFError(
                            "Destination changed before publication."
                        )

                    if progress.cancelled():
                        raise PDFError("Operation cancelled.")

                    progress.stage(
                        source, page, output, "Publishing output image"
                    )

                    # Atomic create-only publication. Never replace an
                    # existing destination, including a late collision.
                    os.link(rendered, output)
                    published += 1

                    progress.status.finish({
                        "ok": True, "output": str(output)
                    })
                    progress.value(published)

                finally:
                    shutil.rmtree(stage)

            progress.close()
            progress = None

            self.accept()

        except (PDFError, OSError, subprocess.TimeoutExpired) as exc:
            cancelled = bool(
                progress and progress.status.cancelling
            )
            remaining = max(0, len(self.plan) - published - 1)

            QMessageBox.warning(
                self,
                f"KIMng - {self.ACTION}",
                f"{exc}\n\n"
                f"Succeeded: {published}\n"
                f"Failed: {0 if cancelled else 1}\n"
                f"Cancelled: {1 if cancelled else 0}\n"
                f"Skipped: {remaining}\n\n"
                "Successfully published outputs are retained.\n"
                "Original PDF files remain unchanged.",
            )
        finally:
            if progress:
                progress.close()


def inspect_pdf_selection(paths):
    """Inspect every selection and collect user-facing block reasons.

    A blocked batch is never submitted for processing.
    """
    results = []

    for value in paths:
        path = str(Path(value).absolute())
        name = Path(path).name

        try:
            validate_pdf_source(path)
        except (PDFError, OSError) as exc:
            message = str(exc)

            if "Not a PDF document" in message:
                reason = "Not a PDF document"
            elif "Not a valid PDF file header" in message:
                reason = "Invalid PDF file header"
            elif "Source changed" in message:
                reason = "Source changed during validation"
            else:
                reason = "Cannot safely inspect this file"

            results.append((path, None, reason))
            continue

        try:
            information = inspect_pdf(path)
        except (PDFError, OSError):
            # Do not expose raw Poppler parser diagnostics.
            results.append((
                path, None,
                "PDF document is unreadable, damaged, or unsupported"
            ))
        else:
            results.append((path, information, ""))

    return results


class PDFBlockedSelectionDialog(QDialog):
    """Standard review surface for an invalid PDF selection.

    No processing is possible while any input is blocked.
    """

    def __init__(self, results, action):
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QDialogButtonBox,
            QHeaderView,
            QHBoxLayout,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        super().__init__()

        self.results = list(results)
        self.setWindowTitle(
            f"KIMng - {action} - Review Changes"
        )
        self.resize(1020, 530)
        self.setMinimumWidth(760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        blocked = sum(
            1 for _, information, reason in self.results
            if reason
        )
        ready = len(self.results) - blocked

        summary = QLabel(
            f"Selected: {len(self.results)}  |  "
            f"Ready: {ready}  |  "
            "Skipped: 0  |  "
            f"Blocked: {blocked}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QTableWidget(
            len(self.results), 6
        )
        self.table.setHorizontalHeaderLabels([
            "Input", "Pages", "Output",
            "Destination", "Action", "Status"
        ])
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        for index in range(6):
            header.setSectionResizeMode(
                index, QHeaderView.Interactive
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
        self.table.setColumnWidth(5, 100)

        operation = (
            "Extract images"
            if action.startswith("Extract ")
            else "Convert pages"
        )

        for row, (path, information, reason) in enumerate(
            self.results
        ):
            folder = str(Path(path).parent)

            values = [
                Path(path).name,
                (
                    str(information["pages"])
                    if information else ""
                ),
                "Not planned",
                folder,
                operation,
                "Blocked" if reason else "Ready",
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(
                    reason or path
                )
                self.table.setItem(
                    row, column, item
                )

        layout.addWidget(self.table, 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(100)
        self.details.setMaximumHeight(125)
        layout.addWidget(self.details)

        notice = QLabel(
            "Apply Changes is unavailable because this "
            "selection contains blocked files. "
            "No files will be processed."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        buttons = QHBoxLayout()

        back = QPushButton("Back")
        style_button(back, "back")
        back.clicked.connect(self.reject)
        back.setToolTip(
            "Return to Settings"
        )
        buttons.addWidget(back)

        buttons.addStretch(1)

        actions = QDialogButtonBox()

        apply_button = actions.addButton(
            "Apply Changes",
            QDialogButtonBox.AcceptRole,
        )
        style_button(apply_button, "apply")
        apply_button.setEnabled(False)

        cancel = actions.addButton(
            QDialogButtonBox.Cancel
        )
        style_button(cancel, "cancel")
        cancel.clicked.connect(self.reject)

        buttons.addWidget(actions)
        layout.addLayout(buttons)

        self.table.currentCellChanged.connect(
            lambda row, *_: self.update_details(row)
        )

        if self.results:
            first_blocked = next(
                (
                    index
                    for index, item in enumerate(self.results)
                    if item[2]
                ),
                0,
            )
            self.table.selectRow(first_blocked)
            self.update_details(first_blocked)

    def update_details(self, row):
        if not (0 <= row < len(self.results)):
            self.details.clear()
            return

        path, information, reason = self.results[row]

        lines = [
            "Input: " + Path(path).name,
            "Source: " + path,
        ]

        if reason:
            lines.extend([
                "Status: Blocked",
                "Reason: " + reason,
            ])
        else:
            lines.extend([
                "Status: Ready",
                "PDF pages: " + str(information["pages"]),
                "This is a valid PDF input.",
            ])

        lines.extend([
            "",
            "No output has been planned or created.",
        ])

        self.details.setPlainText(
            "\n".join(lines)
        )




def build_pdf_selection_settings(results, action, valid_factory):
    """Use the normal Settings and Review workflow for valid files.

    Unsupported inputs are visible in review but never enter
    the execution plan. Ready outputs remain applicable.
    """
    from PySide6.QtWidgets import (
        QDialogButtonBox,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QTableWidgetItem,
        QVBoxLayout,
    )

    valid = [
        path for path, information, reason in results
        if information is not None and not reason
    ]
    blocked = [
        (path, reason)
        for path, information, reason in results
        if reason
    ]

    if not blocked:
        raise ValueError(
            "Blocked-input Settings requires blocked selections."
        )

    if valid:
        # Reuse the existing accepted Settings and Review
        # implementation. Only valid PDFs enter create_plan()
        # and apply_changes().
        dialog = valid_factory(valid)
        dialog.setWindowTitle(
            f"KIMng - {action} - Settings"
        )

        settings_page = dialog.stack.widget(0)
        layout = settings_page.layout()

        for label in settings_page.findChildren(QLabel):
            if label.text().startswith(
                "Selected PDF documents:"
            ):
                label.setText(
                    f"Selected: {len(results)} files  |  "
                    f"Valid PDFs: {len(valid)}  |  "
                    f"Blocked: {len(blocked)}"
                )
                break

        warning = QLabel(
            f"{len(blocked)} selected "
            f"{'file is' if len(blocked) == 1 else 'files are'} "
            "not a usable PDF. "
            "Valid PDFs can be processed; blocked files "
            "will be skipped. Review Changes shows both."
        )
        warning.setWordWrap(True)
        warning.setObjectName(
            "pdfBlockedSelectionNotice"
        )
        layout.insertWidget(1, warning)

        original_populate = dialog.populate_review
        original_details = dialog.update_details

        dialog._pdf_blocked_results = list(results)
        dialog._pdf_blocked_inputs = list(blocked)
        dialog._pdf_ready_rows = 0
        dialog._pdf_blocked_notice = warning

        def update_mixed_details(row):
            ready_rows = dialog._pdf_ready_rows

            if row < ready_rows:
                return original_details(row)

            index = row - ready_rows

            if 0 <= index < len(blocked):
                path, reason = blocked[index]

                dialog.details.setPlainText(
                    "Input: " + Path(path).name
                    + "\nSource: " + path
                    + "\nStatus: Blocked"
                    + "\nReason: " + reason
                    + "\n\nThis file will be skipped."
                    + "\nValid PDF outputs may still be applied."
                )
                return

            dialog.details.clear()

        def populate_mixed_review(*args, **kwargs):
            result = original_populate(*args, **kwargs)

            # The accepted planner owns the real output rows.
            # It also handles existing-file collisions and
            # disables Apply if planning itself fails.
            ready_rows = dialog.table.rowCount()

            if ready_rows != len(dialog.plan):
                # Do not turn a blocked planning operation into
                # an apparently executable plan.
                dialog._pdf_ready_rows = ready_rows
                return result

            dialog._pdf_ready_rows = ready_rows

            renamed = getattr(
                dialog, "naming_warnings", {}
            )

            for index in range(ready_rows):
                if index >= len(dialog.plan):
                    break

                output = dialog.plan[index][2]
                warning = renamed.get(str(output))

                if warning:
                    status_item = dialog.table.item(index, 5)
                    if status_item is not None:
                        status_item.setText(
                            "Ready (renamed)"
                        )
                        status_item.setToolTip(warning)

                    output_item = dialog.table.item(index, 2)
                    if output_item is not None:
                        output_item.setToolTip(warning)

            for offset, (path, reason) in enumerate(blocked):
                row = ready_rows + offset
                dialog.table.insertRow(row)

                values = [
                    Path(path).name,
                    "",
                    "Not planned",
                    str(Path(path).parent),
                    "Skip",
                    "Blocked",
                ]

                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(reason)
                    dialog.table.setItem(
                        row, column, item
                    )

            dialog.summary.setText(
                f"Selected: {len(results)} files  |  "
                f"Ready: {ready_rows}  |  "
                f"Skipped: {len(blocked)}  |  "
                f"Warnings: {len(renamed)}  |  "
                f"Blocked: {len(blocked)}"
            )

            # Existing Apply handling remains wired to
            # apply_changes(), which uses only dialog.plan.
            # Never enable an otherwise blocked plan.
            if ready_rows == 0:
                dialog.primary.setEnabled(False)

            current_row = dialog.table.currentRow()
            if current_row >= 0:
                update_mixed_details(current_row)

            return result

        dialog.update_details = update_mixed_details
        dialog.populate_review = populate_mixed_review

        # Keep the original Review Changes signal connected.
        # Do not disconnect or replace the accepted workflow.
        return dialog

    # When every input is invalid, the existing compact
    # blocked-selection Settings view remains appropriate.
    dialog = QDialog()
    dialog.setWindowTitle(
        f"KIMng - {action} - Settings"
    )
    dialog.resize(850, 280)
    dialog.setMinimumWidth(680)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    layout.addWidget(QLabel(
        f"Selected: {len(results)} files  |  "
        "Valid PDFs: 0  |  "
        f"Blocked: {len(blocked)}"
    ))

    notice = QLabel(
        "None of the selected files can be processed "
        "as PDF documents."
    )
    notice.setWordWrap(True)
    layout.addWidget(notice)

    details = QPlainTextEdit()
    details.setReadOnly(True)
    details.setPlainText(
        "\\n".join(
            f"{Path(path).name}: {reason}"
            for path, reason in blocked
        )
    )
    details.setMaximumHeight(105)
    layout.addWidget(details)

    layout.addWidget(QLabel(
        "Review Changes lists the blocked files. "
        "Apply Changes will be unavailable."
    ))

    layout.addStretch(1)

    buttons = QHBoxLayout()
    buttons.addStretch(1)

    actions = QDialogButtonBox()

    review_button = actions.addButton(
        "Review Changes",
        QDialogButtonBox.AcceptRole,
    )
    style_button(review_button, "review")

    def show_blocked_review():
        review = PDFBlockedSelectionDialog(
            results, action
        )
        review.exec()

    review_button.clicked.connect(
        lambda _checked=False: show_blocked_review()
    )

    cancel = actions.addButton(
        QDialogButtonBox.Cancel
    )
    style_button(cancel, "cancel")
    cancel.clicked.connect(dialog.reject)

    buttons.addWidget(actions)
    layout.addLayout(buttons)

    return dialog





def main():
    app = QApplication(sys.argv)
    selected = [
        value for value in sys.argv[1:]
        if value != "--"
    ]

    missing = [
        name for name in ("pdfinfo", "pdftoppm", "identify")
        if not shutil.which(name)
    ]
    if missing:
        QMessageBox.critical(
            None, "KIMng - PDF conversion",
            "Missing dependencies: "
            + ", ".join(missing)
            + "\nInstall poppler-utils."
        )
        return 1

    if not selected:
        QMessageBox.warning(
            None, "KIMng - PDF conversion",
            "Select one or more PDF documents."
        )
        return 1

    try:
        inspected = inspect_pdf_selection(selected)

        if any(reason for _, _, reason in inspected):
            dialog = build_pdf_selection_settings(
                inspected,
                "Convert PDF pages to images",
                PDFPagesDialog,
            )
            dialog.exec()
            return 1

        dialog = PDFPagesDialog(selected)
        return (
            0 if dialog.exec() == QDialog.Accepted else 1
        )
    except (PDFError, OSError) as exc:
        QMessageBox.critical(
            None, "KIMng - PDF conversion", str(exc)
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
