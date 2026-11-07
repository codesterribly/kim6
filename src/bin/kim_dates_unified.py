"""Unified image-date interface, using the existing verified publisher."""

import datetime as dt
import json
import os
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from kim_ui import (
    CaptureAdjustment,
    CaptureDateInput,
    CaptureDateOptions,
)
from kim_preview import qt_classes, verify_plan, date_approval_plan


TARGETS = (
    ("capture", "Set image capture date"),
    ("file", "Set file modification date"),
    ("adjust", "Adjust image capture date"),
)

SOURCES = {
    "capture": (
        ("manual", "Enter manually"),
        ("own-file", "Each image's file modification date"),
        ("ref-capture", "Reference image's capture date"),
        ("ref-file", "Reference image's file modification date"),
    ),
    "file": (
        ("manual", "Enter manually"),
        ("own-capture", "Each image's capture date"),
        ("ref-capture", "Reference image's capture date"),
        ("ref-file", "Reference image's file modification date"),
    ),
}



def publication_rows(plan):
    """Read-only presentation of the approved planner's exact outputs."""
    from pathlib import Path

    config = plan.get('config') or {}
    reference = config.get('reference_path')

    rows = []

    for entry in plan['entries']:
        source = entry['source']
        target = entry.get('target')
        state = entry.get('status')

        if state == 'error':
            filename = ''
            directory = ''
            action = 'Blocked'

        elif state == 'skip':
            filename = ''
            directory = ''
            action = (
                'Reference'
                if source == reference
                else 'Unchanged'
            )

        elif not target:
            raise ValueError(
                'Approved date plan has no output for '
                + str(source)
            )

        else:
            filename = Path(target).name
            directory = str(Path(target).parent)

            publication = entry.get('publication')

            if publication == 'create':
                action = 'Create copy'
            elif publication == 'overwrite':
                action = (
                    'Replace original'
                    if source == target
                    else 'Replace existing output'
                )
            else:
                raise ValueError(
                    'Unknown publication action for '
                    + str(source)
                )

        rows.append((
            Path(source).name,
            filename,
            directory,
            action,
        ))

    return rows


class ReadDates(QThread):
    inspected = Signal(int, str, str, str)

    def __init__(self, files, parent):
        super().__init__(parent)
        self.files = files

    def run(self):
        from kim_date_tools import source_date
        from kim_recipe_dates import display

        for index, path in enumerate(self.files):
            if self.isInterruptionRequested():
                return

            capture = 'Not set'
            modified = 'Unavailable'
            error = ''

            try:
                info = os.stat(path, follow_symlinks=False)
                seconds, _ = divmod(info.st_mtime_ns, 10**9)

                modified = dt.datetime.fromtimestamp(
                    seconds, dt.timezone.utc
                ).astimezone().strftime('%Y-%m-%d %H:%M:%S')

                value, fraction, _, _ = source_date(
                    path,
                    ignore_invalid=True,
                    preview=True,
                    allow_animation=True,
                )

                if value is not None:
                    capture = display(value, fraction)

            except Exception as exc:
                error = str(exc)

            if not self.isInterruptionRequested():
                self.inspected.emit(
                    index, capture, modified, error
                )


class SetDatesDialog(QDialog):
    def __init__(self, files, policy, seeds, parent=None):
        super().__init__(parent)

        self.files = list(files)
        self.policy = policy
        self.seeds = list(seeds)
        self.original_seeds = list(seeds)

        self.target = 'capture'
        self.source = 'manual'
        self.reference = None
        self.reference_identity = None

        self.plan = None
        self.approved_plan = None
        self.worker = None
        self.reader = None

        self.pending = False
        self.closing = False
        self._changing = False

        self.source_info = {}
        self.cache = {}
        self._zones = {}

        self.setWindowTitle('KIM6 - Set dates')
        self.resize(1040, 650)
        self.setMinimumWidth(790)

        main = QVBoxLayout(self)
        main.setSpacing(6)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel('Change:'))

        self.targets = QButtonGroup(self)
        self.target_buttons = {}

        for index, (key, label) in enumerate(TARGETS):
            button = QRadioButton(label)
            self.targets.addButton(button, index)
            self.target_buttons[key] = button
            target_row.addWidget(button)

        main.addLayout(target_row)

        self.source_row = QFormLayout()
        self.source_box = QComboBox()

        self.source_row.addRow(
            'Use date from', self.source_box
        )
        main.addLayout(self.source_row)

        reference_row = QHBoxLayout()

        self.reference_text = QLabel(
            'No reference image selected'
        )
        self.reference_text.setWordWrap(True)

        reference_row.addWidget(self.reference_text, 1)

        self.use_reference = QPushButton(
            'Use selected as reference'
        )
        self.use_reference.clicked.connect(
            self.choose_reference
        )

        reference_row.addWidget(self.use_reference)
        main.addLayout(reference_row)

        self.date = CaptureDateInput()
        self.adjustment = CaptureAdjustment()

        self.input_form = QFormLayout()
        self.input_form.addRow(self.date)
        self.input_form.addRow(
            'Adjustment', self.adjustment
        )
        main.addLayout(self.input_form)

        self.advanced = CaptureDateOptions(
            'unknown', embedded=True
        )

        self.zone = self.advanced.zone
        self.offset = self.advanced.offset
        self.fields = self.advanced.fields

        main.addWidget(self.advanced)

        self.heading = QLabel()
        main.addWidget(self.heading)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        main.addWidget(self.summary)

        self.table = QTableWidget(len(self.files), 4)
        self.table.setHorizontalHeaderLabels(
            ['Image', 'Current', 'Proposed', 'Status']
        )

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
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        # All columns are user-resizable. Preserve their widths
        # when the dialog changes date sources or refreshes its plan.
        for column in range(4):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )

        self.table.setColumnWidth(0, 450)
        self.table.setColumnWidth(1, 225)
        self.table.setColumnWidth(2, 275)
        self.table.setColumnWidth(3, 95)

        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )

        for index, path in enumerate(self.files):
            initial = (
                Path(path).name,
                '',
                '',
                'Needs input',
            )

            for column, value in enumerate(initial):
                self.table.setItem(
                    index,
                    column,
                    QTableWidgetItem(value),
                )

        main.addWidget(self.table, 1)

        self.message = QLabel(
            'Select an image to inspect its details.'
        )
        self.message.setWordWrap(True)
        main.addWidget(self.message)

        self.more = QCheckBox(
            'Show technical metadata for selected image'
        )
        main.addWidget(self.more)

        self.technical = QPlainTextEdit()
        self.technical.setReadOnly(True)
        self.technical.setMaximumHeight(110)
        self.technical.hide()

        main.addWidget(self.technical)

        policy_note = (
            'Create copies, originals unchanged'
            if policy == 'create'
            else
            'Replace originals only under the approved overwrite policy'
        )

        main.addWidget(QLabel(policy_note))

        self.destination_mode = QComboBox()
        self.destination_mode.addItem(
            'Beside originals', 'beside'
        )
        self.destination_mode.addItem(
            'Different directory', 'directory'
        )

        self.destination_label = QLabel('Save copies:')

        destination_choice = QHBoxLayout()
        destination_choice.addWidget(self.destination_label)
        destination_choice.addWidget(
            self.destination_mode, 1
        )
        main.addLayout(destination_choice)

        self.directory_field = QLineEdit()
        self.directory_field.setPlaceholderText(
            'Enter or browse to an existing directory'
        )
        self.directory_field.setAccessibleName(
            'Output directory'
        )

        self.browse_directory = QPushButton('Browse…')
        self.browse_directory.clicked.connect(
            self.choose_output_directory
        )

        self.directory_row = QHBoxLayout()
        self.directory_row.addWidget(
            self.directory_field, 1
        )
        self.directory_row.addWidget(
            self.browse_directory
        )

        main.addLayout(self.directory_row)

        self.destination_label.setVisible(
            self.policy == 'create'
        )
        self.destination_mode.setVisible(
            self.policy == 'create'
        )
        self.directory_field.hide()
        self.browse_directory.hide()

        buttons = QHBoxLayout()
        buttons.addStretch()

        self.apply = QPushButton('Review changes…')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.review_changes)

        buttons.addWidget(self.apply)

        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)

        buttons.addWidget(cancel)
        main.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(280)
        self.timer.timeout.connect(
            self.plan_changes
        )

        self.targets.idClicked.connect(
            self.choose_target
        )
        self.source_box.currentIndexChanged.connect(
            self.choose_source
        )

        self.date.changed.connect(self.invalidate)
        self.adjustment.changed.connect(self.invalidate)
        self.zone.currentIndexChanged.connect(self.invalidate)
        self.offset.textChanged.connect(self.invalidate)
        self.fields.currentIndexChanged.connect(self.invalidate)

        self.table.itemSelectionChanged.connect(
            self.show_selected
        )
        self.more.toggled.connect(self.show_selected)

        self.destination_mode.currentIndexChanged.connect(
            self.output_destination_changed
        )
        self.directory_field.textChanged.connect(
            self.invalidate
        )

        self.target_buttons['capture'].setChecked(True)
        self.choose_target(0)

        if self.files:
            self.table.selectRow(0)

        self.reader = ReadDates(self.files, self)
        self.reader.inspected.connect(self.inspected)
        self.reader.finished.connect(self.read_done)
        self.reader.start()


    def choose_output_directory(self):
        if self.policy != 'create':
            return

        initial = self.directory_field.text().strip()

        if not initial or not Path(initial).is_dir():
            initial = (
                str(Path(self.files[0]).parent)
                if self.files
                else str(Path.home())
            )

        chosen = QFileDialog.getExistingDirectory(
            self,
            'Choose output directory',
            initial,
        )

        if chosen:
            self.directory_field.setText(chosen)

    def output_destination_changed(self, *_):
        different = (
            self.policy == 'create'
            and self.destination_mode.currentData()
            == 'directory'
        )

        self.directory_field.setVisible(different)
        self.browse_directory.setVisible(different)

        self.invalidate()

    def destination_seeds(self):
        """Build candidate paths using existing date-output names.

        The shared planner handles collision numbering, reserved names,
        source alias checks, and destination snapshots.
        """
        if self.policy != 'create':
            return list(self.original_seeds)

        if self.destination_mode.currentData() != 'directory':
            return list(self.original_seeds)

        text = self.directory_field.text().strip()

        if not text:
            raise ValueError(
                'Choose an output directory to continue.'
            )

        if (
            '\n' in text
            or '\r' in text
            or not Path(text).is_absolute()
        ):
            raise ValueError(
                'Choose an absolute directory path '
                'without line breaks.'
            )

        directory = Path(text)

        if (
            not directory.is_dir()
            or directory.is_symlink()
            or not os.access(
                directory, os.W_OK | os.X_OK
            )
        ):
            raise ValueError(
                'Output directory must exist, must not be '
                'a symbolic link, and must be writable.'
            )

        directory = directory.resolve(strict=True)

        if len(self.original_seeds) != len(self.files):
            raise ValueError(
                'Date output candidates do not match '
                'the selected images.'
            )

        return [
            str(directory / Path(seed).name)
            for seed in self.original_seeds
        ]

    def choose_target(self, index):
        self._zones[
            (self.target, self.source)
        ] = self.advanced.zone_value()

        self.target = TARGETS[index][0]
        self._changing = True

        try:
            old = self.source_box.currentData()
            self.source_box.clear()

            for code, label in SOURCES.get(
                self.target, ()
            ):
                self.source_box.addItem(label, code)

            index = self.source_box.findData(old)

            if index < 0:
                index = 0

            if index >= 0:
                self.source_box.setCurrentIndex(index)

            self.source = (
                self.source_box.currentData()
                if self.target != 'adjust'
                else None
            )

            self.source_row.setRowVisible(
                self.source_box,
                self.target != 'adjust',
            )

        finally:
            self._changing = False

        self.configure_source()

    def choose_source(self, *_):
        if self._changing:
            return

        self._zones[
            (self.target, self.source)
        ] = self.advanced.zone_value()

        self.source = self.source_box.currentData()
        self.configure_source()

    def configure_source(self):
        reference_mode = bool(
            self.source
            and self.source.startswith('ref-')
        )

        self.reference_text.setVisible(
            reference_mode
        )
        self.use_reference.setVisible(
            reference_mode
        )

        if self.reference is not None:
            self.reference_text.setText(
                'Reference: '
                + Path(
                    self.files[self.reference]
                ).name
            )
        else:
            self.reference_text.setText(
                'No reference image selected'
            )

        manual = (
            self.target != 'adjust'
            and self.source == 'manual'
        )

        self.input_form.setRowVisible(
            self.date, manual
        )
        self.input_form.setRowVisible(
            self.adjustment,
            self.target == 'adjust',
        )

        date_field = self.date.layout().itemAt(
            0, QFormLayout.LabelRole
        )

        if date_field and date_field.widget():
            date_field.widget().setText(
                'File modification date'
                if self.target == 'file'
                else 'Image capture date'
            )

        requires_timezone = (
            self.target == 'file'
            and self.source != 'ref-file'
        ) or (
            self.target == 'capture'
            and self.source in (
                'own-file', 'ref-file'
            )
        )

        zone = self._zones.get(
            (self.target, self.source)
        )

        if zone is None:
            zone = (
                'unknown'
                if manual
                else 'UTC'
                if self.source in (
                    'own-file', 'ref-file'
                )
                else 'embedded'
            )

        embedded_index = self.zone.findData(
            'embedded'
        )

        if embedded_index >= 0:
            allowed = (
                self.source in (
                    'own-capture',
                    'ref-capture',
                )
                or self.target == 'adjust'
            )

            self.zone.model().item(
                embedded_index
            ).setEnabled(allowed)

            if zone == 'embedded' and not allowed:
                zone = (
                    'unknown'
                    if manual
                    else 'UTC'
                )

        self._changing = True

        try:
            self.advanced.set_zone(zone)

            # CaptureDateOptions registers a wrapper widget,
            # not self.fields, as the Date fields form row.
            # Row 2 is Date fields in CaptureDateOptions.
            self.advanced.form.setRowVisible(
                2,
                self.target != 'file',
            )

            self.advanced.toggle.setChecked(
                requires_timezone
            )

        finally:
            self._changing = False

        heading = (
            'File modification dates'
            if self.target == 'file'
            else 'Image capture dates'
        )

        self.heading.setText(
            f'{heading} for '
            f'{len(self.files)} selected images'
        )

        self.invalidate()

    def choose_reference(self):
        selected = (
            self.table.selectionModel().selectedRows()
        )

        if not selected:
            return

        from kim_preview import identity

        index = selected[0].row()

        try:
            snapshot = identity(
                self.files[index]
            )
        except Exception as exc:
            self.reference = None
            self.reference_identity = None
            self.summary.setText(
                'Cannot use reference: ' + str(exc)
            )
            return

        self.reference = index
        self.reference_identity = snapshot

        self.reference_text.setText(
            'Reference: '
            + Path(self.files[index]).name
        )

        self.invalidate()

    def config(self):
        source = self.source

        if self.target == 'adjust':
            kind = 'shift'
        elif source == 'manual':
            kind = (
                'set'
                if self.target == 'capture'
                else 'set-file'
            )
        elif source == 'own-file':
            kind = 'file-to-exif'
        elif source == 'own-capture':
            kind = 'exif-to-file'
        else:
            kind = (
                'reference-to-exif'
                if self.target == 'capture'
                else 'reference-to-file'
            )

        result = {
            'kind': kind,
            'datetime': self.date.value(),
            'timezone': self.advanced.zone_value(),
            'seconds': self.adjustment.value(),
            'fields': self.fields.currentData(),
        }

        if (
            source
            and source.startswith('ref-')
            and self.reference is not None
        ):
            result.update({
                'reference_path': (
                    self.files[self.reference]
                ),
                'reference_type': (
                    'capture'
                    if source == 'ref-capture'
                    else 'file'
                ),
                'reference_identity': (
                    self.reference_identity
                ),
            })

        return result

    def inspected(self, index, capture, modified, error):
        self.source_info[index] = (
            capture, modified, error
        )

        if self.plan is None:
            self.render_rows()

    def read_done(self):
        worker, self.reader = self.reader, None
        worker.deleteLater()

        if self.closing:
            self.finish_close()
        else:
            self.plan_changes()

    def invalidate(self, *_):
        if self._changing or self.closing:
            return

        self.plan = None
        self.approved_plan = None
        self.apply.setEnabled(False)

        if self.worker:
            self.pending = True
            self.worker.requestInterruption()

        self.timer.start()
        self.render_rows()

    def plan_changes(self):
        self.timer.stop()

        if self.closing:
            return

        if self.worker:
            self.pending = True
            self.worker.requestInterruption()
            return

        if self.reader:
            self.summary.setText(
                'Inspecting selected image dates…'
            )
            return

        self.pending = False

        if (
            self.target != 'adjust'
            and self.source == 'manual'
            and not self.date.value()
        ):
            self.summary.setText(
                'Choose a date and time to continue.'
            )
            self.render_rows()
            return

        if (
            self.source
            and self.source.startswith('ref-')
            and self.reference is None
        ):
            self.summary.setText(
                'Select an image, then click '
                'Use selected as reference.'
            )
            self.render_rows()
            return

        try:
            config = self.config()

            if self.source == 'manual':
                from kim_recipe_dates import specific

                specific(
                    config['datetime'],
                    config['timezone'],
                )

            if (
                self.target == 'file'
                and self.source != 'ref-file'
                and config['timezone'] in (
                    'unknown', ''
                )
            ):
                raise ValueError(
                    'Choose UTC or an explicit timezone '
                    'offset to set a file date.'
                )

        except Exception as exc:
            self.summary.setText(str(exc))
            self.render_rows()
            return

        try:
            candidates = self.destination_seeds()
        except ValueError as exc:
            self.summary.setText(str(exc))
            self.render_rows()
            return

        if candidates != self.seeds:
            self.seeds = candidates
            self.cache.clear()

        key = json.dumps(
            {
                'config': config,
                'seeds': self.seeds,
            },
            sort_keys=True,
        )

        cached = self.cache.get(key)

        if cached:
            try:
                verify_plan(cached)
            except Exception:
                self.cache.pop(key, None)
            else:
                self.plan = cached
                self.present()
                return

        self.summary.setText(
            'Inspecting image dates…'
        )

        self.render_rows(inspecting=True)

        self.worker = qt_classes()[1](
            'date',
            self.policy,
            self.files,
            config,
            self.seeds,
            self,
        )

        self.worker.progress.connect(
            lambda index, total, path:
            self.summary.setText(
                f'Inspecting {index + 1} of {total}: '
                f'{Path(path).name}'
            ) if not self.pending else None
        )

        self.worker.finished.connect(
            self.plan_done
        )
        self.worker.start()

    def plan_done(self):
        worker, self.worker = self.worker, None

        try:
            if self.closing:
                return

            if self.pending:
                self.pending = False
                QTimer.singleShot(
                    0, self.plan_changes
                )
                return

            if worker.error:
                self.summary.setText(
                    'Unable to prepare preview: '
                    + str(worker.error)
                )

                self.render_rows(
                    problem=str(worker.error)
                )
                return

            self.plan = worker.plan

            if not any(
                entry['status'] == 'error'
                for entry in self.plan['entries']
            ):
                self.cache[
                    json.dumps(
                        {
                            'config': self.config(),
                            'seeds': self.seeds,
                        },
                        sort_keys=True,
                    )
                ] = self.plan

            self.present()

        finally:
            worker.deleteLater()

            if self.closing:
                self.finish_close()

    def present(self):
        entries = self.plan['entries']

        ready = sum(
            entry['status'] == 'change'
            for entry in entries
        )
        skipped = sum(
            entry['status'] == 'skip'
            for entry in entries
        )
        blocked = sum(
            entry['status'] == 'error'
            for entry in entries
        )
        warnings = sum(
            bool(entry.get('warnings'))
            for entry in entries
        )

        self.summary.setText(
            f'{ready} ready  ·  '
            f'{skipped} unchanged/reference  ·  '
            f'{warnings} warnings  ·  '
            f'{blocked} blocked'
        )

        self.render_rows()

        self.apply.setEnabled(
            self.plan is not None
            and self.worker is None
            and self.reader is None
        )

    def render_rows(self, inspecting=False, problem=''):
        entries = (
            self.plan['entries']
            if self.plan
            else [None] * len(self.files)
        )

        file_target = self.target == 'file'

        reference_mode = bool(
            self.source
            and self.source.startswith('ref-')
        )

        for index, path in enumerate(self.files):
            capture, modified, source_error = (
                self.source_info.get(
                    index,
                    ('Inspecting…', 'Inspecting…', ''),
                )
            )

            current = (
                modified if file_target else capture
            )

            entry = entries[index]

            if entry:
                result = entry.get(
                    'date_result'
                ) or {}

                proposed = str(
                    result.get('preview')
                    or 'Unavailable'
                )

                if file_target and 'epoch_ns' in result:
                    try:
                        seconds, nanos = divmod(
                            int(result['epoch_ns']),
                            10**9,
                        )

                        proposed = dt.datetime.fromtimestamp(
                            seconds,
                            dt.timezone.utc,
                        ).astimezone().strftime(
                            '%Y-%m-%d %H:%M:%S'
                        )

                        if nanos:
                            proposed += (
                                '.'
                                + f'{nanos:09d}'.rstrip('0')
                            )

                    except (
                        ValueError,
                        OverflowError,
                        OSError,
                    ):
                        proposed = 'Out of range'

                status = {
                    'change': 'Ready',
                    'skip': 'Unchanged',
                    'error': 'Blocked',
                }.get(
                    entry.get('status'),
                    'Blocked',
                )

            else:
                proposed = (
                    'Enter date'
                    if (
                        self.source == 'manual'
                        and not self.date.value()
                    )
                    else 'Select reference'
                    if (
                        reference_mode
                        and self.reference is None
                    )
                    else 'Inspecting…'
                    if (
                        inspecting
                        or self.reader
                        or self.worker
                    )
                    else 'Needs input'
                )

                status = (
                    'Blocked'
                    if source_error or problem
                    else 'Inspecting'
                    if (
                        inspecting
                        or self.reader
                        or self.worker
                    )
                    else 'Needs input'
                )

            if (
                reference_mode
                and self.reference == index
            ):
                proposed = current
                status = 'Reference'

            values = (
                Path(path).name,
                current,
                proposed,
                status,
            )

            for column, value in enumerate(values):
                item = self.table.item(
                    index, column
                )

                item.setText(str(value))
                item.setToolTip(
                    str(path)
                    if column == 0
                    else str(value)
                )

                is_reference = (
                    reference_mode
                    and self.reference == index
                )

                item.setIcon(
                    QIcon.fromTheme('emblem-favorite')
                    if column == 0 and is_reference
                    else QIcon()
                )

                item.setBackground(
                    QBrush(
                        self.palette().alternateBase().color()
                    )
                    if is_reference
                    else QBrush()
                )

        self.show_selected()

    def show_selected(self):
        selected = (
            self.table.selectionModel().selectedRows()
        )

        if not selected:
            self.message.setText(
                'Select an image to inspect its '
                'warnings or errors.'
            )
            self.technical.hide()
            return

        index = selected[0].row()

        entry = (
            self.plan['entries'][index]
            if self.plan
            else None
        )

        source_error = self.source_info.get(
            index, ('', '', '')
        )[2]

        if entry:
            messages = [
                str(message)
                for message in (
                    entry.get('error'),
                    entry.get('skip_reason'),
                    *(entry.get('warnings') or []),
                )
                if message
            ]

            self.message.setText(
                '\n'.join(messages)
                or 'No issues for the selected image.'
            )

            if self.more.isChecked():
                self.technical.setPlainText(
                    '\n'.join(
                        ' | '.join(map(str, row))
                        for row in entry.get('rows', [])
                    )
                    or 'No technical changes.'
                )
                self.technical.show()
            else:
                self.technical.hide()

        else:
            self.message.setText(
                source_error
                or 'Preview not yet available for this image.'
            )
            self.technical.hide()


    def review_changes(self):
        """Review exact destinations before accepting the date plan."""
        if (
            not self.apply.isEnabled()
            or not self.plan
            or self.worker
            or self.reader
        ):
            return

        try:
            if self.destination_seeds() != self.seeds:
                raise ValueError(
                    'Output directory changed. '
                    'Review a fresh plan.'
                )

            rows = publication_rows(self.plan)
            eligible = sum(
                entry['status'] == 'change'
                for entry in self.plan['entries']
            )
            if eligible:
                date_approval_plan(self.plan)
        except Exception as exc:
            self.apply.setEnabled(False)
            self.summary.setText(
                'Review required: ' + str(exc)
            )
            return

        review = QDialog(self)
        review.setWindowTitle(
            'KIM6 - Review date changes'
        )
        review.resize(1120, 570)
        review.setMinimumWidth(850)

        layout = QVBoxLayout(review)
        layout.setSpacing(8)

        title = QLabel(
            '<b>Review date changes and output files</b>'
        )
        layout.addWidget(title)

        action_label = {
            'capture': 'Set image capture dates',
            'file': 'Set file modification dates',
            'adjust': 'Adjust image capture dates',
        }[self.target]

        reference = (
            Path(self.files[self.reference]).name
            if self.reference is not None
            and self.source
            and self.source.startswith('ref-')
            else None
        )

        description = action_label

        if reference:
            description += (
                ' using reference: ' + reference
            )

        layout.addWidget(QLabel(description))

        if self.policy == 'create':
            location = (
                'Beside originals'
                if self.destination_mode.currentData()
                == 'beside'
                else (
                    'Different directory: '
                    + str(
                        Path(
                            self.directory_field.text()
                            .strip()
                        ).resolve()
                    )
                )
            )

            layout.addWidget(
                QLabel('Output location: ' + location)
            )

        created = sum(
            item[3] == 'Create copy'
            for item in rows
        )
        replaced = sum(
            item[3].startswith('Replace')
            for item in rows
        )
        unchanged = sum(
            item[3] in ('Reference', 'Unchanged')
            for item in rows
        )
        blocked = sum(
            item[3] == 'Blocked'
            for item in rows
        )

        summary = QLabel(
            f'{created} new copies  |  '
            f'{replaced} replacements  |  '
            f'{unchanged} unchanged/reference  |  '
            f'{blocked} blocked'
        )
        layout.addWidget(summary)

        table = QTableWidget(len(rows), 4, review)
        table.setHorizontalHeaderLabels([
            'Original image',
            'Output filename',
            'Destination directory',
            'Action',
        ])

        table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)

        table.verticalHeader().setVisible(False)
        table.setHorizontalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )

        header = table.horizontalHeader()
        header.setStretchLastSection(False)

        for column in range(4):
            header.setSectionResizeMode(
                column, QHeaderView.Interactive
            )

        for column, width in enumerate(
            (250, 310, 350, 165)
        ):
            table.setColumnWidth(column, width)

        for index, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(index, column, item)

        layout.addWidget(table, 1)

        policy = (
            'Create copies: original images will not be modified.'
            if self.policy == 'create'
            else
            'Replacement mode: review every Replace action above.'
        )

        policy_note = QLabel(policy)
        policy_note.setWordWrap(True)
        layout.addWidget(policy_note)

        layout.addWidget(QLabel(
            'Filenames and destinations come from the current '
            'KIM6 preview plan, including collision handling.'
        ))

        excluded = [
            entry for entry in self.plan['entries']
            if entry['status'] == 'error'
        ]

        for entry in excluded:
            issue = QLabel(
                'Blocked, will not be processed: '
                + Path(entry['source']).name
                + ': '
                + entry.get('error', 'Inspection failed')
            )
            issue.setWordWrap(True)
            layout.addWidget(issue)

        exclusion_confirm = QCheckBox(
            f'Exclude {len(excluded)} blocked image(s) '
            'from this operation'
        )
        exclusion_confirm.setVisible(bool(excluded))
        layout.addWidget(exclusion_confirm)

        error_label = QLabel()
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        confirm = QPushButton('Apply changes')
        confirm.setEnabled(
            (created + replaced) > 0
            and not excluded
        )
        buttons.addWidget(confirm)

        if excluded:
            exclusion_confirm.toggled.connect(
                lambda checked: confirm.setEnabled(
                    checked and (created + replaced) > 0
                )
            )

        back = QPushButton('Back')
        back.clicked.connect(review.reject)
        buttons.addWidget(back)

        def confirm_changes():
            try:
                if self.destination_seeds() != self.seeds:
                    raise ValueError(
                        'Output directory changed. '
                        'Review a fresh plan.'
                    )

                if excluded and not exclusion_confirm.isChecked():
                    raise ValueError(
                        'Confirm exclusion of blocked images.'
                    )

                approved = date_approval_plan(self.plan)

                # Reject a plan whose publication details changed
                # while the final review was open.
                if publication_rows(self.plan) != rows:
                    raise ValueError(
                        'Output destinations changed. '
                        'Review a fresh plan.'
                    )

            except Exception as exc:
                confirm.setEnabled(False)
                error_label.setText(str(exc))
                return

            self.approved_plan = approved
            review.accept()

        confirm.clicked.connect(confirm_changes)

        layout.addLayout(buttons)

        if review.exec() == QDialog.Accepted:
            # The original acceptance path verifies the plan again
            # before the launcher saves it for publication.
            self.accept()


    def accept(self):
        if (
            not self.apply.isEnabled()
            or not self.plan
            or self.worker
        ):
            return

        try:
            if self.approved_plan is None:
                raise ValueError(
                    'Complete the final output review.'
                )
            verify_plan(self.approved_plan)
        except Exception as exc:
            self.apply.setEnabled(False)
            self.summary.setText(
                str(exc)
                + '. Review the images again.'
            )
            return

        super().accept()

    def finish_close(self):
        if (
            self.closing
            and self.worker is None
            and self.reader is None
        ):
            super().reject()

    def reject(self):
        if self.worker or self.reader:
            self.closing = True
            self.timer.stop()
            self.apply.setEnabled(False)

            if self.worker:
                self.worker.requestInterruption()

            if self.reader:
                self.reader.requestInterruption()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker or self.reader:
            self.reject()
            event.ignore()
        else:
            event.accept()
