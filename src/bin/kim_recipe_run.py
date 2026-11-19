"""Read-only confirmation, responsive batch inspection, and shared recipe property view."""
import copy
import os
import re
import stat
import sys
import time
from pathlib import Path
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtCore import QThread, Signal, Slot, Qt, QTimer, QStandardPaths, QSettings
from PySide6.QtGui import QPalette, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QSplitter, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QPlainTextEdit, QFileDialog, QProgressDialog, QMessageBox, QProgressBar, QScrollArea, QSizePolicy)
from kim_job import JobStatus, grouped_warnings, WarningGroups
from kim_recipe_core import (RecipeError, PreviewRow, builtins, load_library, lookup_recipe,
                             recipe_title, RecipeLibrary, library_groups, handler, preview, execute, validate,
                             approve_rows, block_output_collisions, output_key)

from kim_review_ui import (exact_field, set_exact, restore_review_geometry,
                           clamp_review_geometry, restore_splitter)


def set_recipe_output_text(field, value):
    # Standalone Review Changes still uses its existing exact fields.
    if isinstance(field, QLabel):
        field.setText(value)
        field.setToolTip(value)
    else:
        set_exact(field, value)



class JobProgressDialog(QDialog):
    canceled = Signal()

    def __init__(self, text, cancel_text, minimum, maximum, parent=None):
        super().__init__(parent); self.finished_job=False; self.resize(640,200)
        self.setWindowTitle('KIMng - Job progress')
        layout=QVBoxLayout(self); self.label=QLabel(text); self.label.setWordWrap(True); self.label.setTextFormat(Qt.PlainText)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard); layout.addWidget(self.label)
        self.bar=QProgressBar(); self.bar.setRange(minimum,maximum); layout.addWidget(self.bar)
        self.cancel_button=QPushButton(cancel_text); self.cancel_button.clicked.connect(self.cancel); layout.addWidget(self.cancel_button)

    def setMinimumDuration(self,_): self.show()
    def setAutoClose(self,_): pass
    def setAutoReset(self,_): pass
    def setLabelText(self,text): self.label.setText(text)
    def setValue(self,value): self.bar.setValue(value)

    def cancel(self):
        self.cancel_button.setEnabled(False); self.canceled.emit()

    def complete(self):
        self.finished_job=True; self.accept()

    def closeEvent(self,event):
        if self.finished_job: event.accept()
        else: self.cancel(); event.ignore()

    def reject(self):
        if self.finished_job: super().reject()
        else: self.cancel()


class WarningView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.summary=QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.expand=QPushButton('Show affected files and technical details'); self.expand.setCheckable(True); layout.addWidget(self.expand)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.details.hide(); self.details.setMaximumHeight(100); layout.addWidget(self.details)
        self.copy=QPushButton('Copy details'); self.copy.hide(); layout.addWidget(self.copy)
        self.expand.toggled.connect(self.refresh_details); self.expand.toggled.connect(self.details.setVisible); self.expand.toggled.connect(self.copy.setVisible)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.details.toPlainText()))

    def set_rows(self, rows):
        self.groups = WarningGroups()
        for row in rows: self.groups.add(row)
        self.refresh_summary()

    def add_row(self, row):
        if not row.warnings: return
        self.groups.add(row)
        self.refresh_summary()

    def refresh_summary(self):
        self.setVisible(bool(self.groups.categories))
        captions = list(self.groups.captions())
        self.summary.setText('\n'.join(captions[:2]) + (f'\n{len(captions)-2} more notice categories; expand for details.' if len(captions)>2 else ''))
        self.summary.setToolTip('\n'.join(captions))
        self.details_dirty = True
        if self.expand.isChecked(): self.refresh_details()

    def refresh_details(self, *args):
        self.expand.setText(('Hide' if self.expand.isChecked() else 'Show') + ' affected files and technical details')
        if getattr(self, 'details_dirty', False):
            self.details.setPlainText('\n\n'.join(caption+'\n'+details for caption, details in self.groups.groups()))
            self.details_dirty = False


class InputFilesView(QTreeWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)

    def dragEnterEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls():
            self.files_dropped.emit([url.toLocalFile() if url.isLocalFile() and url.host() in ('', 'localhost') else url.toString()
                                     for url in event.mimeData().urls()])
            event.acceptProposedAction()
        else: event.ignore()


def explain_review_failure(error):
    """Explain known failures without weakening validation."""
    message = str(error)

    if (
        "Incomplete extended XMP" in message
        and "[minor]" in message
    ):
        return (
            "ExifTool found incomplete extended XMP metadata. "
            "KIMng could not verify that the metadata would be "
            "preserved safely, so this output was blocked. "
            "The original image remains unchanged."
        )

    return (
        "KIMng could not safely complete this operation. "
        "The affected output was not published. "
        "See technical details for the reported error."
    )


def file_count(n):
    return f"{n} {'file' if n == 1 else 'files'}"


class PropertyView(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(['Property', 'Planned Value'])
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setWordWrap(True); self.setMinimumWidth(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.setColumnWidth(0, 155)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().sectionResized.connect(lambda *_: self.resizeRowsToContents())

    def set_fields(self, fields):
        self.setRowCount(len(fields))
        for row, (key, value) in enumerate(fields):
            for column, text in enumerate((key, str(value))):
                item = QTableWidgetItem(text); item.setToolTip(text)
                if column == 1 and text.casefold().startswith(('removed', 'not included', 'none detected', 'when exported', 'not set')):
                    font = item.font(); font.setItalic(True); item.setFont(font)
                    item.setForeground(self.palette().brush(QPalette.Active, QPalette.Text))
                self.setItem(row, column, item)
        self.resizeRowsToContents()


def property_fields(recipe, row):
    fields = [('Source filename', Path(row.source).name), ('Source folder', str(Path(row.source).parent))]
    if row.output and not row.problems:
        fields += [('Output filename', Path(row.output).name), ('Output folder', str(Path(row.output).parent))]
    fields += handler(recipe['media']).preview_fields(row)
    if row.problems:
        fields.append(('Output plan', 'Unavailable: resolve validation problems'))
    fields += [('Validation problem', problem) for problem in row.problems]
    # Category notices belong to the batch disclosure, not every property row.
    if not row.problems:
        fields += [('Publication', row.certainty)]
    return fields + [('Originals', 'Always unchanged')]

def operation_review_fields(recipe, row):
    """Concise Crop/Overlay review without unrelated metadata."""
    fields = property_fields(recipe, row)

    names = {
        'source filename',
        'output filename',
        'output folder',
        'original dimensions',
        'output dimensions',
        'final format',
        'crop geometry',
        'output plan',
        'validation problem',
        'publication',
        'originals',
    }

    return [
        (name, value)
        for name, value in fields
        if name.casefold() in names
        or name.casefold().startswith(('crop ', 'overlay '))
    ]


class RecipeWorker(QThread):
    """The existing serial execution loop, shared by every confirmation launch."""
    item_started = Signal(str, int)
    item_finished = Signal(dict, int)
    stage_changed = Signal(str)

    def __init__(
        self, recipe, files, chosen=None, parent=None,
        omit_overlay_metadata=False,
        auto_metadata_fallback=False,
        approved_plan=None,
    ):
        super().__init__(parent)
        self.recipe, self.files, self.chosen = (
            copy.deepcopy(recipe), list(files), chosen
        )
        self.results, self.error, self.cancelled = [], None, False
        self.omit_overlay_metadata = bool(omit_overlay_metadata)
        self.auto_metadata_fallback = bool(auto_metadata_fallback)
        self.approved_plan = approved_plan

    def run(self):
        from kim_image_ops import logo_inspections
        from kim_recipe_image import (
            standalone_overlay_metadata_policy,
            automatic_watermark_metadata_fallback,
        )
        with (
            standalone_overlay_metadata_policy(
                self.omit_overlay_metadata
            ),
            automatic_watermark_metadata_fallback(
                self.auto_metadata_fallback
            ),
            logo_inspections(),
        ):
            self.execute_files()

    def execute_files(self):
        from kim_process import inspection_context
        try:
            if self.approved_plan is None:
                raise RecipeError('Missing approved publication plan; review again')
            def completed(result, index, total):
                self.results.append(result)
                self.item_finished.emit(result, index)
            with inspection_context(self.stage_changed.emit, self.isInterruptionRequested):
                execute(self.recipe, self.files, self.chosen, progress=completed,
                        approved_plan=self.approved_plan, started=self.item_started.emit)
            self.cancelled = self.isInterruptionRequested() or any(r.get('cancelled') for r in self.results)
        except Exception as exc:
            if self.isInterruptionRequested(): self.cancelled = True
            else: self.error = str(exc)


class InputFiltersWorker(QThread):
    def __init__(self,parent=None):
        super().__init__(parent); self.filters=None

    def run(self):
        from kim_recipe_image import input_name_filters
        from kim_process import inspection_context
        try:
            with inspection_context(cancelled=self.isInterruptionRequested): self.filters=input_name_filters()
        except (OSError,ValueError):
            if not self.isInterruptionRequested(): self.filters=['All Files (*)']


class AddFilesWorker(QThread):
    """Decode outside Qt's GUI thread; accepted paths belong to one revision."""
    item_started = Signal(int)
    def __init__(self, paths, current, revision, parent=None):
        super().__init__(parent)
        self.paths, self.current, self.revision = list(paths), list(current), revision
        self.accepted, self.rejected = [], []
        self.checked_inputs = {}

    def run(self):
        from kim_recipe_image import inspect, checked_input_headers
        from kim_psd_source import source_session, header as psd_header
        from kim_process import inspection_context
        identities = {os.path.normcase(os.path.abspath(p)) for p in self.current}
        file_identities = set()
        for existing in self.current:
            try:
                info = os.stat(existing)
            except OSError:
                continue
            file_identities.add((info.st_dev, info.st_ino))

        for index,raw in enumerate(self.paths):
            if self.isInterruptionRequested(): break
            self.item_started.emit(index)
            path = os.path.abspath(os.path.normpath(raw)); key = os.path.normcase(path)
            try:
                if key in identities:
                    raise RecipeError('Already in the list')
                info = os.stat(path, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise RecipeError('Choose an existing local image file, not a directory or symlink')
                file_identity = (info.st_dev, info.st_ino)
                if file_identity in file_identities:
                    raise RecipeError('Already in the list')
                # Admission checks the PSD header/resource bounds. Recipe
                # preflight owns composite/ICC validation; decoding here too
                # doubled large-document work before the user could press Run.
                if psd_header(path) is None:
                    with inspection_context(cancelled=self.isInterruptionRequested), source_session(), checked_input_headers(self.checked_inputs): inspect(Path(path))
                self.accepted.append(path)
                identities.add(key)
                file_identities.add(file_identity)
            except (OSError, ValueError) as exc:
                self.rejected.append(str(raw) + ': ' + str(exc))
            except Exception as exc:
                # Unexpected decoder errors must reach the UI, not silently
                # abandon pending inputs at the QThread boundary.
                self.rejected.append(str(raw) + ': Image inspection failed: ' + str(exc))


class PreflightWorker(QThread):
    file_started = Signal(str, int, int)
    inspected = Signal(object, int)
    stage_changed = Signal(str)

    def __init__(
        self, recipe, files, chosen=None, binding_error=None,
        parent=None, checked_inputs=None,
        omit_overlay_metadata=False,
    ):
        super().__init__(parent)
        self.recipe, self.files, self.chosen = (
            copy.deepcopy(recipe), list(files), chosen
        )
        self.binding_error = binding_error
        self.checked_inputs = copy.deepcopy(checked_inputs or {})
        self.cancelled = False
        self.omit_overlay_metadata = bool(omit_overlay_metadata)

    def run(self):
        from kim_image_ops import logo_inspections
        from kim_recipe_image import standalone_overlay_metadata_policy
        with (
            standalone_overlay_metadata_policy(
                self.omit_overlay_metadata
            ),
            logo_inspections(),
        ):
            self.inspect_files()

    def inspect_files(self):
        outputs = {}
        for index, source in enumerate(self.files, 1):
            if self.isInterruptionRequested():
                self.cancelled = True; break
            self.file_started.emit(str(source),index,len(self.files))
            try:
                from kim_process import inspection_context
                from kim_recipe_image import checked_input_headers
                with inspection_context(self.stage_changed.emit,self.isInterruptionRequested), checked_input_headers(self.checked_inputs):
                    row = preview(self.recipe, [source], self.chosen, start_index=index)[0]
                if self.binding_error:
                    row.problems.append(self.binding_error)
                if self.recipe['destination'].get('ask') and not self.chosen:
                    row.problems.append('Choose an output directory before running.')
                if row.approved is not None:
                    duplicates = outputs.setdefault(output_key(row.approved), [])
                    previous_problems = [len(previous.problems) for _, previous in duplicates]
                    duplicates.append((index - 1, row))
                    block_output_collisions([previous for _, previous in duplicates])
                    for (previous_index, previous), count in zip(duplicates, previous_problems):
                        if len(previous.problems) != count:
                            self.inspected.emit(copy.deepcopy(previous), previous_index)
            except Exception as exc:
                row = PreviewRow(str(source), problems=[str(exc)])
            if self.isInterruptionRequested():
                self.cancelled=True
                row=PreviewRow(str(source),properties={'_cancelled':True})
            self.inspected.emit(copy.deepcopy(row), index - 1)
            if self.cancelled: break


def confirmation_snapshot(recipe):
    """Bind inherited text for this confirmation only; saved references remain untouched."""
    snapshot = copy.deepcopy(recipe)
    media = handler(recipe['media'])
    definitions = media.operation_definitions()
    error = None
    try:
        media.validate_context(recipe['steps'])
    except (OSError, RecipeError) as exc:
        error = str(exc)
    for step in snapshot['steps']:
        if step['op'] == 'image.overlay' and step['kind'] == 'text':
            try:
                from kim_image_ops import resolved_watermark_fields
                step['text_fields'] = resolved_watermark_fields(step)
            except (OSError, RecipeError) as exc:
                if step.get('enabled', True): error = str(exc)
        for key, spec in definitions[step['op']]['parameters'].items():
            if key=='quality' and step['op']=='image.convert' and any(s['op']=='image.compress' and s.get('enabled',True) for s in snapshot['steps']):
                continue  # Disabled compression restores this saved reference.
            if spec.get('settings_key') and step.get(key) is None:
                try:
                    step[key] = media.parameter_value(step, key)
                except (OSError, RecipeError) as exc:
                    if step.get('enabled', True): error = str(exc)
    return snapshot, error


def selection_title(recipe, folders):
    if recipe.get('folder'):
        return recipe_title(recipe, folders)
    group = 'Built-In' if recipe['id'] in {r['id'] for r in builtins()} else 'Unfiled'
    return group + ' / ' + recipe['name']


class RunRecipeDialog(QDialog):
    def __init__(self, recipe, files, folders=(), parent=None, chosen=None, operation_title=None):
        super().__init__(parent)
        self.recipe = copy.deepcopy(recipe)
        self.operation_title = operation_title
        self.omit_overlay_metadata = False
        self.files = list(files)
        self.execution_recipe, self.binding_error = confirmation_snapshot(recipe) if recipe else (None, None)
        self.base_execution_recipe = copy.deepcopy(self.execution_recipe)
        self.add_worker = None; self._addition_queue = []; self._addition_items = []; self.input_revision = 0
        self.checked_inputs = {}
        self.filters_worker = None; self._input_filters = None; self._pending_picker = False
        self.generation = 0
        self.reviewed_generation = None
        self.validated_snapshot = None
        self.approved_plan = None
        self.approval_error = ''
        self.library = RecipeLibrary() if operation_title else load_library()
        self.selected_id = recipe['id'] if recipe else None
        self.saved_definition = None
        if recipe and not operation_title:
            try:
                saved = lookup_recipe(recipe['id'])
                if saved == recipe: self.saved_definition = saved
            except RecipeError:
                pass
        self.chosen = chosen
        self.default_chosen = chosen
        self.destination_mode = 'default'
        self.override_directory = ''
        self.preflight_worker = None; self.worker = None
        self.ready_count = self.problem_count = self.repair_count = 0
        self.problem_messages = {}; self._last_problem_index = -1; self._selected_presentation = None
        self.rows = {}; self._restart = False; self._closing = False
        self.preflight_active = None
        self.preflight_clock = QTimer(self); self.preflight_clock.setInterval(1000)
        self.preflight_clock.timeout.connect(self.refresh_preflight_status)
        self.results = []
        self.execution_succeeded = False
        self.editor_dialog = None; self._close_after_editor = False
        self.setWindowTitle(
            operation_title + ' - Review Changes'
            if operation_title else 'Run a Recipe'
        )
        self.resize(
            1010 if operation_title else 1120,
            635 if operation_title else 820
        )
        self.settings = QSettings('KIMng', 'RecipeReview' if operation_title else 'RecipeRun')
        layout = QVBoxLayout(self)
        selection = QHBoxLayout()
        label = QLabel('&Recipe:')
        self.search = QLineEdit(); self.search.setPlaceholderText('Search recipes or folders…')
        self.search.setAccessibleName('Search recipes or folders')
        self.selector = QComboBox(); self.selector.setPlaceholderText('Choose a recipe…')
        self.selector.setMinimumContentsLength(24)
        self.selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        label.setBuddy(self.selector)
        selection.addWidget(label); selection.addWidget(self.search, 1); selection.addWidget(self.selector, 2)
        self.create_button = QPushButton('Create new recipe…')
        self.create_button.clicked.connect(self.create_recipe)
        self.edit_button = QPushButton()
        self.edit_button.clicked.connect(self.edit_recipe)
        selection.addWidget(self.edit_button)
        selection.addWidget(self.create_button); layout.addLayout(selection)
        self.selection_hint=QLabel('Select a recipe to preview its outputs and operations. Choose the output location below before running.')
        self.selection_hint.setWordWrap(True); self.selection_hint.setVisible(recipe is None); layout.addWidget(self.selection_hint)
        self.search.textChanged.connect(self.refresh_selector)
        self.selector.currentIndexChanged.connect(self.select_recipe)
        self.refresh_selector()
        if operation_title:
            for control in (label, self.search, self.selector, self.create_button, self.edit_button): control.hide()
        self.heading = QLabel(operation_title or ('Recipe: ' + selection_title(recipe, folders) if recipe else 'Choose a recipe…'))
        self.heading.setTextFormat(Qt.PlainText); self.heading.setWordWrap(True)
        if operation_title:
            self.heading.setText(
                'Review the exact planned outputs before applying.'
            )
        layout.addWidget(self.heading)
        self.count = QLabel('Inputs: ' + file_count(len(self.files))); layout.addWidget(self.count)
        split = self.splitter = QSplitter(Qt.Horizontal); layout.addWidget(split, 1)
        split.setChildrenCollapsible(False)
        left = QWidget(); left.setMinimumWidth(0); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0,0,0,0); split.addWidget(left)
        inputs = QGroupBox(
            'Selected images: choose one to review'
            if operation_title
            else 'Selected files: select one for detailed preview'
        )
        inp_layout = QVBoxLayout(inputs)
        self.inputs = InputFilesView(); self.inputs.setHeaderLabels(['Filename', 'Status'])
        self.inputs.setAccessibleName('Selected images and review status')
        self.inputs.header().setStretchLastSection(False)
        self.inputs.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.inputs.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.inputs.setColumnWidth(1, 175)
        self.inputs.setRootIsDecorated(False)
        for source in self.files:
            item = QTreeWidgetItem([Path(source).name, 'Queued' if self.recipe else 'Select recipe']); item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.inputs.currentItemChanged.connect(self.show_selected)
        inp_layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.add_photos = QPushButton('Add images…'); self.add_photos.clicked.connect(self.pick_files)
        self.remove_selected = QPushButton('Remove selected'); self.remove_selected.clicked.connect(self.remove_files)
        self.clear_list = QPushButton('Clear list'); self.clear_list.clicked.connect(self.clear_files)
        for button in (self.add_photos, self.remove_selected, self.clear_list): actions.addWidget(button)
        inp_layout.addLayout(actions); left_layout.addWidget(inputs, 1)
        self.blocking_summary = QLabel(); self.blocking_summary.setWordWrap(True)
        self.blocking_summary.setTextFormat(Qt.PlainText)
        self.blocking_summary.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.blocking_summary.hide(); left_layout.addWidget(self.blocking_summary)
        self.inputs.files_dropped.connect(self.add_files)
        self.inputs.itemSelectionChanged.connect(self.update_file_actions)
        operations = QGroupBox('Recipe operations in execution order'); op_layout = QVBoxLayout(operations)
        self.operations = QTreeWidget(); self.operations.setHeaderHidden(True); self.operations.setWordWrap(True)
        self.fill_operations()
        op_layout.addWidget(self.operations)
        if not operation_title:
            operations.setMinimumHeight(260)
        self.operations_panel = operations

        # Internal Recipe steps remain available to the engine,
        # but standalone image operations do not show the tree.
        if operation_title:
            operations.hide()
        right = QGroupBox(
            'Planned output' if operation_title else 'Output preview'
        )
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(0)
        if operation_title:
            self.output_filename = exact_field(right_layout, 'Filename')
            self.output_directory = exact_field(right_layout, 'Output Directory')
        else:
            # Display planned information as text, not input controls.
            for caption, attribute in (
                ('Filename', 'output_filename'),
                ('Output Directory', 'output_directory'),
            ):
                right_layout.addWidget(QLabel(caption))
                value = QLabel()
                value.setTextFormat(Qt.PlainText)
                value.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
                )
                value.setSizePolicy(
                    QSizePolicy.Ignored, QSizePolicy.Preferred
                )
                value.setAccessibleName(caption)
                setattr(self, attribute, value)
                right_layout.addWidget(value)
        self.properties_button = QPushButton('Show output properties')
        self.properties_button.setCheckable(True)
        right_layout.addWidget(self.properties_button)
        self.properties = PropertyView(); self.properties.setMinimumHeight(140)
        if not operation_title:
            self.properties.setMaximumHeight(220)
        right_layout.addWidget(self.properties)
        self.properties_button.toggled.connect(self.properties.setVisible)
        self.properties_button.toggled.connect(lambda expanded: self.properties_button.setText(
            'Hide output properties' if expanded else 'Show output properties'))
        self.properties_button.setChecked(self.settings.value('properties_expanded', bool(operation_title), type=bool))
        self.properties.setVisible(self.properties_button.isChecked())
        self.operations_button = QPushButton()
        self.operations_button.setCheckable(True)
        right_layout.addWidget(self.operations_button)
        right_layout.addWidget(operations, 1 if not operation_title else 0)
        self.operations_button.toggled.connect(operations.setVisible)
        self.operations_button.toggled.connect(self.update_operation_summary)
        self.operations_button.setChecked(not operation_title)
        operations.setVisible(self.operations_button.isChecked() and not operation_title and self.recipe is not None)
        self.operations_button.setVisible(not operation_title and self.recipe is not None)
        self.update_operation_summary()
        if operation_title:
            right_layout.addStretch(1)
        preview_scroll = self.preview_scroll = QScrollArea(); preview_scroll.setWidgetResizable(True)
        preview_scroll.setMinimumWidth(220); preview_scroll.setWidget(right)
        split.addWidget(preview_scroll)
        preview_scroll.setVisible(recipe is not None)
        split.setSizes(
            [390, 730] if operation_title else [460, 640]
        )
        dest = QHBoxLayout()
        dest.addWidget(QLabel('Output location:'))
        self.destination_label = QLabel(); self.destination_label.setTextFormat(Qt.PlainText)
        self.destination_label.setWordWrap(True)
        self.choose_destination = QPushButton(QIcon.fromTheme('folder-open'), 'Choose output directory…')
        self.choose_destination.clicked.connect(self.select_destination)
        self.choose_destination.setVisible(bool(recipe and recipe['destination'].get('ask')))
        self.destination_label.setText('Destination: ' + self.destination_description() if recipe else 'Choose a recipe to inspect its destination.')
        self.destination_choice = QComboBox()
        self.destination_choice.setAccessibleName('Destination for this run')
        self.destination_choice.addItem('Use recipe default', 'default')
        self.destination_choice.addItem('Beside each source', 'beside')
        self.destination_choice.addItem('Choose another directory…', 'directory')
        self.destination_choice.currentIndexChanged.connect(self.change_destination_mode)
        self.destination_choice.setVisible(not operation_title)
        self.destination_choice.setEnabled(bool(recipe))
        dest.addWidget(self.destination_choice)
        dest.addWidget(self.destination_label, 1)
        dest.addWidget(self.choose_destination)
        if not operation_title:
            layout.insertLayout(layout.indexOf(split), dest)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.PlainText)
        layout.addWidget(self.summary)

        self.metadata_policy_note = QLabel(
            "Source metadata will be omitted from this "
            "watermarked derivative. The original is unchanged."
        )
        self.metadata_policy_note.setWordWrap(True)
        self.metadata_policy_note.hide()
        layout.addWidget(self.metadata_policy_note)
        self.preflight_busy=QProgressBar(); self.preflight_busy.setRange(0,0)
        self.preflight_busy.setAccessibleName('Inspecting selected images'); self.preflight_busy.hide()
        layout.addWidget(self.preflight_busy)
        self.problem_explanation = QLabel()
        self.problem_explanation.setWordWrap(True)
        self.problem_explanation.setTextFormat(Qt.PlainText)
        self.problem_explanation.hide()
        if operation_title:
            layout.addWidget(self.problem_explanation)

        self.technical_details_button = QPushButton(
            "Show technical details"
        )
        self.technical_details_button.setCheckable(True)
        self.technical_details_button.hide()
        if operation_title:
            layout.addWidget(self.technical_details_button)

        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(150)
        layout.addWidget(self.diagnostics)

        self.diagnostics.hide()
        if operation_title:
            self.technical_details_button.toggled.connect(self.diagnostics.setVisible)
        else:
            layout.insertWidget(layout.indexOf(self.diagnostics), self.technical_details_button)
            self.technical_details_button.toggled.connect(self.sync_diagnostics)
            self.diagnostics.textChanged.connect(self.sync_diagnostics)
        self.fix_recipe_button=QPushButton('Fix recipe…'); self.fix_recipe_button.setAccessibleName('Fix recipe: choose a Photoshop output format')
        self.fix_recipe_button.clicked.connect(self.fix_recipe); self.fix_recipe_button.hide(); layout.addWidget(self.fix_recipe_button)
        self.warning_view = WarningView()
        layout.addWidget(self.warning_view)
        if operation_title:
            self.warning_view.expand.hide()
            self.warning_view.details.hide()
            self.warning_view.copy.hide()
            if hasattr(self, 'technical_details_button'):
                self.technical_details_button.hide()

        if operation_title:
            layout.addLayout(dest)
        safety = QLabel('Originals are not being changed. KIMng saves only the exact reviewed filenames. A collision blocks publication and requires a new review. Finished results stay put if you cancel or something fails.')
        safety.setWordWrap(True); layout.addWidget(safety)
        from kim_dialog_buttons import style_button

        buttons = QHBoxLayout()
        if operation_title:
            self.back_button = QPushButton('Back')
            style_button(self.back_button, 'back')
            self.back_button.clicked.connect(
                self.return_to_settings
            )
            buttons.addWidget(self.back_button)
        buttons.addStretch(1)
        self.run_button = QPushButton(
            ('Apply Changes to ' if operation_title
             else 'Run Recipe on ')
            + file_count(len(self.files)).title()
        )
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_execution)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)

        style_button(self.run_button, 'apply')
        style_button(self.cancel_button, 'cancel')

        buttons.addWidget(self.run_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        if self.files: self.inputs.setCurrentItem(self.inputs.topLevelItem(0))
        self.update_file_actions()
        self.update_edit_button()
        if not operation_title:
            self.technical_details_button.setChecked(self.settings.value('technical_expanded', False, type=bool))
        restore_review_geometry(self, self.settings, (1120, 680) if not operation_title else (1010, 635))
        restore_splitter(self.splitter, self.settings, 'splitter', [650, 430])
        self.finished.connect(self.save_display_preferences)
        self.start_preflight()

    def showEvent(self, event):
        super().showEvent(event)
        clamp_review_geometry(self)

    def save_display_preferences(self, *_):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('splitter', self.splitter.sizes())
        self.settings.setValue('operations_expanded', self.operations_button.isChecked())
        self.settings.setValue('properties_expanded', self.properties_button.isChecked())
        self.settings.setValue('technical_expanded', self.technical_details_button.isChecked())

    def sync_diagnostics(self, *_):
        self.technical_details_button.setText('Hide technical details' if self.technical_details_button.isChecked() else 'Show technical details')
        present = bool(self.diagnostics.toPlainText())
        self.technical_details_button.setVisible(present)
        self.diagnostics.setVisible(present and self.technical_details_button.isChecked())

    def update_operation_summary(self):
        steps = self.recipe['steps'] if self.recipe else []
        enabled = sum(step.get('enabled', True) for step in steps)
        action = 'Hide' if self.operations_button.isChecked() else 'Show'
        self.operations_button.setText(f'{action} operations ({enabled} enabled, {len(steps)} total)')

    def update_edit_button(self):
        immutable = bool(self.recipe and any(r['id'] == self.recipe['id'] for r in builtins()))
        self.edit_button.setText('Customize built-in…' if immutable else 'Edit recipe…')
        self.edit_button.setEnabled(bool(self.recipe) and self.editor_dialog is None and self.worker is None)

    def edit_recipe(self):
        if self.recipe is not None:
            self.open_editor(edit=True)

    def return_to_settings(self):
        if not self.operation_title:
            return
        if (
            self.worker is not None
            or self.preflight_worker is not None
            or self.add_worker is not None
            or self.filters_worker is not None
            or self._addition_queue
        ):
            self.summary.setText(
                'Inspection or execution is still in progress.'
            )
            return
        if self.results:
            return
        self.done(131)

    def show_operation_problems(self, problems):
        if not self.operation_title:
            return

        problems = [
            str(problem)
            for problem in problems
            if str(problem).strip()
        ]

        if not problems:
            self.problem_explanation.hide()
            self.technical_details_button.hide()
            self.diagnostics.hide()
            return

        self.problem_explanation.setText(
            explain_review_failure(problems[0])
        )
        self.problem_explanation.show()

        self.technical_details_button.show()
        self.diagnostics.setVisible(
            self.technical_details_button.isChecked()
        )

    def update_file_actions(self):
        idle = self.worker is None and not self._closing
        self.add_photos.setEnabled(idle and self.filters_worker is None)
        self.remove_selected.setEnabled(idle and self.add_worker is None and bool(self.inputs.selectedItems()))
        self.clear_list.setEnabled(idle and (bool(self.files) or self.add_worker is not None))
        self.inputs.setEnabled(idle)

    def pick_files(self):
        if self.worker is not None or self._closing or self.editor_dialog is not None: return
        from kim_recipe_image import cached_input_name_filters
        if self._input_filters is None: self._input_filters=cached_input_name_filters()
        if self._input_filters is None:
            self._pending_picker=True; self.run_button.setEnabled(False)
            self.add_photos.setText('Loading image formats…'); self.add_photos.setEnabled(False)
            if self.filters_worker is None:
                self.filters_worker=InputFiltersWorker(self)
                self.filters_worker.finished.connect(self.input_filters_finished); self.filters_worker.start()
            return
        start = str(Path(self.files[0]).parent) if self.files else ''
        if not start or not Path(start).is_dir():
            preferred = Path.home() / 'Pictures'
            start = str(preferred) if preferred.is_dir() else (QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or str(Path.home()))
        if not Path(start).is_dir(): start = str(Path.home())
        extensions = set(re.findall(r'\*\.([a-zA-Z0-9]+)', self._input_filters[0]))
        paths = choose_images(self, start, title='Add images',
                              extensions=extensions or RECIPE_IMAGE_EXTENSIONS,
                              accept_label='Add images')
        self.add_files(paths)
        self.update_summary()

    def input_filters_finished(self):
        worker,self.filters_worker=self.filters_worker,None
        self._input_filters=worker.filters; worker.deleteLater()
        self.add_photos.setText('Add images…'); self.update_file_actions()
        if self._closing: self.finish_close_if_idle(); return
        pending,self._pending_picker=self._pending_picker,False
        if pending and self.worker is None and self.editor_dialog is None: self.pick_files()
        else: self.update_summary()

    def add_files(self, paths):
        if self.worker is not None or self._closing or not paths: return
        self._addition_queue.extend(paths)
        self.invalidate_preflight()
        # Paint selected names before any admission delegate completes. These
        # rows are provisional; rejected files never become runnable inputs.
        for path in paths:
            item=QTreeWidgetItem([Path(path).name,'Checking image…']); item.setToolTip(0,str(path))
            self.inputs.addTopLevelItem(item); self._addition_items.append(item)
        self.count.setText('Inputs: '+file_count(self.inputs.topLevelItemCount()))
        self.summary.setText('Checking added images…')
        self.start_additions()

    def start_additions(self):
        if self.add_worker is not None or not self._addition_queue or self._closing: return
        paths, self._addition_queue = self._addition_queue, []
        self.add_worker = AddFilesWorker(paths, self.files, self.input_revision, self)
        self.add_worker.display_items,self._addition_items=self._addition_items,[]
        self.add_worker.item_started.connect(self.admission_started)
        self.add_worker.finished.connect(self.additions_finished)
        self.update_file_actions()
        self.add_worker.start()

    @Slot(int)
    def admission_started(self,index):
        worker=self.sender()
        if worker.revision==self.input_revision and not self._closing:
            worker.display_items[index].setText(1,'Inspecting')

    def additions_finished(self):
        worker, self.add_worker = self.add_worker, None
        worker.deleteLater()
        if self._closing:
            self.finish_close_if_idle(); return
        if worker.revision == self.input_revision:
            self.checked_inputs.update(worker.checked_inputs)
            queued=self._addition_queue[:]
            self.replace_files(self.files+worker.accepted,preflight=False)
            if queued: self.add_files(queued)
            else: self.start_preflight()
            if worker.rejected: QMessageBox.warning(self, 'Some files were not added', '\n'.join(worker.rejected))
        elif not self._addition_queue:
            self.start_preflight()
        self.start_additions()
        self.update_file_actions(); self.update_summary()

    def finish_close_if_idle(self):
        if self._closing and self.worker is None and self.preflight_worker is None and self.add_worker is None and self.filters_worker is None:
            super().reject()

    def replace_files(self, files, preflight=True):
        if self.worker is not None or self._closing: return
        self.input_revision += 1
        if self.add_worker is not None: self.add_worker.requestInterruption()
        self._addition_queue.clear(); self._addition_items.clear()
        self.files = list(files)
        selected={os.path.abspath(p) for p in self.files}
        self.checked_inputs={key:value for key,value in self.checked_inputs.items() if key in selected}
        self.inputs.clear()
        for source in self.files:
            item = QTreeWidgetItem([Path(source).name, 'Queued' if self.recipe else 'Select recipe'])
            item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.count.setText('Inputs: ' + file_count(len(self.files)))
        self.run_button.setText(
            ('Apply Changes to ' if self.operation_title
             else 'Run Recipe on ')
            + file_count(len(self.files)).title()
        )
        self.update_file_actions()
        if preflight: self.start_preflight()
        if self.files: self.inputs.setCurrentItem(self.inputs.topLevelItem(0))

    def remove_files(self):
        if self.add_worker is not None: return
        selected = {self.inputs.indexOfTopLevelItem(item) for item in self.inputs.selectedItems()}
        if selected: self.replace_files([path for i, path in enumerate(self.files) if i not in selected])

    def clear_files(self):
        if self.worker is not None or (not self.files and self.add_worker is None): return
        if QMessageBox.question(self, 'Clear list', 'Remove all pending files from this job?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.replace_files([])

    def destination_description(self):
        d = self.recipe['destination']
        if d['mode'] == 'beside': return 'Beside each source'
        if d['mode'] == 'subfolder': return d['folder'] + ' subfolder beside each source'
        return d.get('path', '')

    def fill_operations(self):
        self.operations.clear()
        if self.recipe is None: return
        media = handler(self.recipe['media'])
        for index, (original, effective) in enumerate(zip(self.recipe['steps'], self.execution_recipe['steps']), 1):
            label, details = media.operation_details(effective)
            enabled = original.get('enabled', True)
            item = QTreeWidgetItem([f'{index}. {label}: ' + ('Enabled' if enabled else 'Disabled')])
            definitions = media.operation_definitions()[original['op']]['parameters']
            for (key, spec), (name, value) in zip(definitions.items(), details):
                if spec.get('settings_key'):
                    value = value.rsplit(' (', 1)[0] + (' (inherited from Settings)' if original.get(key) is None else ' (recipe override)')
                child = QTreeWidgetItem([name + ': ' + value]); child.setToolTip(0, child.text(0)); item.addChild(child)
            if not enabled:
                item.setForeground(0, self.palette().brush(QPalette.Disabled, QPalette.Text))
            self.operations.addTopLevelItem(item)
        self.operations.expandAll()

    def refresh_selector(self, *args):
        if self.operation_title: return
        query = self.search.text().casefold().strip()
        self.selector.blockSignals(True); self.selector.clear()
        for folder_id, name, recipes in library_groups(self.library):
            matches = [r for r in recipes if not query or query in (name + ' ' + r['name']).casefold()]
            if query and not matches: continue
            self.selector.addItem(name, None)
            self.selector.model().item(self.selector.count() - 1).setEnabled(False)
            for recipe in matches:
                self.selector.addItem('    ' + recipe['name'], recipe['id'])
                self.selector.setItemData(self.selector.count() - 1, name + ' / ' + recipe['name'], Qt.ToolTipRole)
        index=self.selector.findData(self.selected_id) if self.selected_id else -1
        if self.selected_id and index < 0 and self.recipe:
            # Filtering choices must not display 'Choose a recipe' while a
            # current (possibly unsaved) recipe is still being inspected.
            self.selector.addItem('    '+self.recipe['name']+' (current recipe)',self.selected_id)
            index=self.selector.count()-1
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)

    def select_recipe(self, index):
        recipe_id = self.selector.itemData(index)
        if self.worker is not None: return
        if not recipe_id:
            self.saved_definition=None; self.apply_recipe(None); return
        self.invalidate_preflight()
        try:
            self.library = load_library()
            recipe = lookup_recipe(recipe_id)
            self.saved_definition = copy.deepcopy(recipe)
            self.apply_recipe(recipe)
        except (OSError, RecipeError) as exc:
            self.saved_definition=None; self.apply_recipe(None)
            self.diagnostics.setPlainText(str(exc))

    def apply_recipe(self, recipe):
        self.recipe = copy.deepcopy(recipe)
        self.selected_id = recipe['id'] if recipe else None
        self.selection_hint.setVisible(recipe is None)
        self.preview_scroll.setVisible(recipe is not None)
        self.destination_choice.setEnabled(recipe is not None)
        self.operations_button.setVisible(recipe is not None and not self.operation_title)
        self.operations_panel.setVisible(
            recipe is not None and not self.operation_title
            and self.operations_button.isChecked()
        )
        self.execution_recipe, self.binding_error = confirmation_snapshot(recipe) if recipe else (None, None)
        self.base_execution_recipe = copy.deepcopy(self.execution_recipe)
        self.refresh_selector()
        if self.selected_id and self.selector.findData(self.selected_id) < 0 and self.search.text():
            self.search.clear()
        self.heading.setText('Recipe: ' + selection_title(recipe, self.library.folders) if recipe else 'Choose a recipe…')
        self.fill_operations()
        ask = bool(recipe and recipe['destination'].get('ask'))
        self.choose_destination.setVisible(ask)
        self.destination_label.setText(('Output directory: ' + (self.chosen or 'choose before running')) if ask else
                                       ('Destination: ' + self.destination_description() if recipe else 'Choose a recipe.'))
        self.apply_destination_override()
        self.update_edit_button()
        self.update_operation_summary()
        self.start_preflight()

    def create_recipe(self):
        self.open_editor()

    def fix_recipe(self):
        if self.recipe is None or not any(row.properties.get('_repair')=='add_convert_format' for row in self.rows.values()): return
        self.open_editor(repair=True)

    def open_editor(self, repair=False, edit=False):
        from kim_recipe_dialog import make_editor_dialog, RecipeWidget
        owner=self.parent()
        if repair and isinstance(owner,RecipeWidget) and owner.run_dialog is self:
            # Return to the editor that launched this Run instead of opening a
            # second manager over its unsaved state. It retains this file set.
            owner.offer_recipe_repair(self.files,self.chosen)
            self.reject(); return
        if self.editor_dialog is not None:
            self.editor_dialog.raise_(); self.editor_dialog.activateWindow(); return
        self._editor_previous=(copy.deepcopy(self.recipe),copy.deepcopy(self.saved_definition))
        # Opening the editor does not change the selected recipe or inputs.
        # Retain completed inspection and let an active preflight finish.
        try:
            dialog=make_editor_dialog(self,from_run=True,recipe=self.recipe if repair or edit else None,repair=repair)
        except (OSError,RecipeError) as exc:
            self.saved_definition=None; self.apply_recipe(None)
            self.diagnostics.setPlainText('Cannot open Recipe Editor: '+str(exc)); return
        self.editor_dialog=dialog; self.create_button.setEnabled(False)
        self.edit_button.setEnabled(False)
        for control in (self.selector, self.search, self.destination_choice, self.choose_destination): control.setEnabled(False)
        if edit and dialog.widget.immutable:
            dialog.widget.status.setText('Choose Duplicate to Edit to create an editable User copy, then Save when ready.')
            dialog.widget.management_buttons['Duplicate to Edit'].setFocus()
        self.update_summary()
        dialog.finished.connect(self.editor_finished)
        # open() uses Qt's normal completion signal, without another nested
        # exec() loop while retired inspection workers are still cleaning up.
        dialog.open()

    @Slot(int)
    def editor_finished(self, result):
        dialog,self.editor_dialog=self.editor_dialog,None
        saved_id=dialog.widget.saved_recipe_id
        previous,previous_definition=self._editor_previous
        self.create_button.setEnabled(True)
        for control in (self.selector, self.search, self.destination_choice, self.choose_destination): control.setEnabled(True)
        error=None
        try:
            self.library=load_library()
            recipe=lookup_recipe(saved_id) if saved_id else previous
            self.saved_definition=copy.deepcopy(recipe) if saved_id else previous_definition
        except (OSError,RecipeError) as exc:
            recipe=None; self.saved_definition=None; error=str(exc)
        dialog.deleteLater()
        self.update_edit_button()
        if self._close_after_editor:
            self._close_after_editor=False; self.reject(); return
        if error is None and recipe == previous:
            # No change to the active recipe: preserve its reviewed plan
            # and any inspection still running.
            self.refresh_selector()
            self.heading.setText(
                'Recipe: ' + selection_title(recipe, self.library.folders)
                if recipe else 'Choose a recipe…'
            )
            self.update_summary()
            if self.validated_snapshot is None and self.preflight_worker is None: self.start_preflight()
        else:
            # New or changed recipe: existing validation cannot be reused.
            self.apply_recipe(recipe)
        if error: self.diagnostics.setPlainText(error)
        (self.fix_recipe_button if self.fix_recipe_button.isVisible() else self.selector).setFocus()

    def invalidate_preflight(self):
        self.generation += 1
        self.reviewed_generation = None
        self.validated_snapshot = None
        self.approved_plan = None
        self.approval_error = ''
        self.run_button.setEnabled(False)
        self.preflight_active=None; self.preflight_clock.stop(); self.preflight_busy.hide(); self.cancel_button.setText('Cancel')
        self.ready_count = self.problem_count = self.repair_count = 0
        self.problem_messages.clear(); self._last_problem_index = -1; self._selected_presentation = None
        self.rows.clear(); self.properties.set_fields([]); self.diagnostics.clear(); self.warning_view.set_rows([])
        self.blocking_summary.clear(); self.blocking_summary.hide()
        for field in (self.output_filename, self.output_directory): set_recipe_output_text(field, '')
        if not self.operation_title: self.sync_diagnostics()
        self.fix_recipe_button.hide()
        for index in range(len(self.files)):
            self.inputs.topLevelItem(index).setText(1, 'Queued' if self.recipe else 'Select recipe')
            self.inputs.topLevelItem(index).setToolTip(1, '')
        if self.preflight_worker is not None:
            self.preflight_worker.requestInterruption()

    def start_preflight(self):
        if self.worker is not None: return
        self.invalidate_preflight()
        if self.recipe is None: self.summary.setText('Waiting for recipe selection')
        if self.preflight_worker is not None:
            self._restart = self.recipe is not None; return
        self._restart = False
        if self.editor_dialog is not None or self.add_worker is not None or self._addition_queue: return
        if self.recipe is None:
            self.summary.setText('Waiting for recipe selection'); return
        self.summary.setText(file_count(len(self.files)) + ' selected; inspecting…')
        if not self.files:
            self.summary.setText('0 files selected; use Add images or drop images here.'); return
        worker = PreflightWorker(
            self.execution_recipe,
            self.files,
            self.chosen,
            self.binding_error,
            self,
            checked_inputs=self.checked_inputs,
            omit_overlay_metadata=self.omit_overlay_metadata,
        )
        worker.generation = self.generation
        self.preflight_worker = worker
        worker.file_started.connect(self.preflight_started)
        worker.inspected.connect(self.inspected)
        worker.stage_changed.connect(self.preflight_stage)
        worker.finished.connect(self.preflight_finished)
        self.preflight_busy.show(); self.preflight_clock.start(); self.cancel_button.setText('Cancel all')
        worker.start()

    @Slot(str,int,int)
    def preflight_started(self,source,index,total):
        if self.sender().generation != self.generation or self._closing: return
        self.preflight_active=(source,index,total,'Inspecting source',time.monotonic())
        self.inputs.topLevelItem(index-1).setText(1,'Inspecting')
        self.refresh_preflight_status()

    def preflight_stage(self, message):
        if self.sender().generation != self.generation or self._closing or not self.preflight_active: return
        source,index,total,_,started=self.preflight_active
        self.preflight_active=(source,index,total,message,started)
        self.inputs.topLevelItem(index-1).setText(1,'Inspecting: '+message)
        self.inputs.topLevelItem(index-1).setToolTip(1, message)
        self.refresh_preflight_status()

    def refresh_preflight_status(self):
        if not self.preflight_active: return
        source,index,total,stage,started=self.preflight_active
        if self._closing: stage='Cancelling current operation; waiting for cleanup'
        self.summary.setText(f'Inspecting {index} of {total}: {Path(source).name}\n'
            f'{stage}…  Elapsed: {int(time.monotonic()-started)} s; '
            f'{len(self.rows)} completed; {max(0,total-index)} queued.')
        self.summary.setToolTip('')

    @Slot(object, int)
    def inspected(self, row, index):
        if self.sender().generation != self.generation: return
        previous = self.rows.get(index)
        for item, change in ((previous, -1), (row, 1)):
            if item is None: continue
            self.ready_count += change * (not item.problems and not item.properties.get('_cancelled'))
            self.problem_count += change * bool(item.problems)
            self.repair_count += change * (item.properties.get('_repair') == 'add_convert_format')
        self.rows[index] = row
        self.inputs.topLevelItem(index).setToolTip(1, '\n'.join(row.problems))
        self.inputs.topLevelItem(index).setText(1, 'Cancelled' if row.properties.get('_cancelled') else 'Blocked' if row.problems else 'Ready')
        if row.problems or (previous is not None and previous.problems):
            ordered = previous is None and index > self._last_problem_index
            self._last_problem_index = max(index, self._last_problem_index)
            self.problem_messages[index] = [str(self.files[index]) + ': ' + issue for issue in row.problems]
            if ordered: self.diagnostics.appendPlainText('\n'.join(self.problem_messages[index]))
            else: self.diagnostics.setPlainText('\n'.join(message for i in sorted(self.problem_messages) for message in self.problem_messages[i]))
            if self.operation_title: self.diagnostics.show()
            else: self.sync_diagnostics()
        if previous is not None and previous.warnings:
            self.warning_view.set_rows(self.rows.values())
        else: self.warning_view.add_row(row)
        self.preflight_active=None

        if self.operation_title:
            problems = [
                message
                for index in sorted(self.problem_messages)
                for message in self.problem_messages[index]
            ]
            self.show_operation_problems(problems)

        if not self._closing:
            self.update_summary()
            selected = self.inputs.currentItem()
            if selected is not None and self.inputs.indexOfTopLevelItem(selected) == index: self.show_selected()

    @Slot()
    def preflight_finished(self):
        worker = self.preflight_worker; self.preflight_worker = None; worker.deleteLater()
        self.preflight_active=None; self.preflight_clock.stop(); self.preflight_busy.hide(); self.cancel_button.setText('Cancel')
        if self._closing:
            for index in range(len(self.files)):
                if index not in self.rows: self.inputs.topLevelItem(index).setText(1,'Skipped')
            self.finish_close_if_idle(); return
        if self._restart:
            self._restart = False; self.start_preflight(); return
        if worker.generation == self.generation and not worker.cancelled:
            self.checked_inputs.update(worker.checked_inputs)
            self.reviewed_generation = self.generation
            self.validated_snapshot = (copy.deepcopy(worker.recipe), list(worker.files), worker.chosen)
            self.approved_plan = None
            if len(self.rows) == len(worker.files) and not any(row.problems for row in self.rows.values()):
                try:
                    self.approved_plan = approve_rows(worker.recipe, worker.files,
                        [self.rows[index] for index in range(len(worker.files))], worker.chosen)
                except (OSError, RecipeError) as exc:
                    self.approval_error = str(exc)
                    self.diagnostics.setPlainText(str(exc))
                    if self.operation_title: self.diagnostics.show()
        self.update_summary()

    def update_summary(self):
        if self.recipe is None:
            self.summary.setText('Waiting for recipe selection'); self.run_button.setEnabled(False); return
        self.update_blocking_summary()
        ready, problems = self.ready_count, self.problem_count
        pending = len(self.files) - len(self.rows)
        self.summary.setText(file_count(len(self.files)) + f' selected; {ready} ready; {problems} ' + ('problem' if problems == 1 else 'problems') + (f'; {pending} pending' if pending else ''))
        self.fix_recipe_button.setVisible(not self.operation_title and self.repair_count > 0 and self.editor_dialog is None and not self._pending_picker)
        self.run_button.setEnabled(self.recipe is not None and self.reviewed_generation == self.generation and bool(getattr(self, 'approved_plan', None)) and bool(self.files) and ready == len(self.files) and not pending and not problems and self.preflight_worker is None and self.worker is None and not self._closing and self.add_worker is None and not self._addition_queue and self.editor_dialog is None and not self._pending_picker)

    def update_blocking_summary(self):
        blocked = [row for row in self.rows.values() if row.problems]
        duplicates = [row for row in blocked if any('multiple selected sources target ' in p for p in row.problems)]
        occupied = [row for row in blocked if any('approved filename already exists:' in p for p in row.problems)]
        lines = []
        if duplicates:
            targets = list(dict.fromkeys(row.output for row in duplicates))
            lines.append(f'{len(duplicates)} images have conflicting output filenames.')
            filename = self.fontMetrics().elidedText(Path(targets[0]).name, Qt.ElideMiddle, 420)
            lines.append('Multiple selected sources would create ' + filename +
                         (f' (and {len(targets)-1} other targets).' if len(targets) > 1 else '.'))
        if occupied:
            lines.append('1 image would use an output filename that already exists on disk.' if len(occupied) == 1 else
                         f'{len(occupied)} images would use output filenames that already exist on disk.')
        other = [row for row in blocked if row not in duplicates and row not in occupied]
        if other:
            caption = '1 image is blocked: ' if len(other) == 1 else f'{len(other)} images are blocked: '
            lines.append(caption +
                         self.fontMetrics().elidedText(other[0].problems[0], Qt.ElideMiddle, 500))
        if duplicates or occupied:
            lines.append("Change the recipe's filename pattern or destination, or select different images, then review again.")
        if self.approval_error:
            lines.append('Review could not be approved. See technical details, then review again.')
        self.blocking_summary.setText('\n'.join(lines))
        self.blocking_summary.setToolTip('\n'.join(dict.fromkeys(row.output for row in blocked if row.output)))
        self.blocking_summary.setVisible(bool(lines))

    def show_selected(self, *args):
        item = self.inputs.currentItem()
        index = self.inputs.indexOfTopLevelItem(item) if item else -1
        row = self.rows.get(index)
        previous = self._selected_presentation
        if previous is not None and previous[0] == (self.generation, index) and previous[1] is row and previous[2] is self.execution_recipe: return
        self._selected_presentation = ((self.generation, index), row, self.execution_recipe)
        output = Path(row.output) if row and row.output else None
        set_recipe_output_text(self.output_filename, output.name if output else '')
        set_recipe_output_text(self.output_directory, str(output.parent) if output else '')
        self.properties.set_fields(
            (
                operation_review_fields(
                    self.execution_recipe, row
                )
                if self.operation_title
                else property_fields(
                    self.execution_recipe, row
                )
            ) if row else []
        )

    def apply_destination_override(self):
        if self.recipe is None:
            return
        # Change only the private resolved snapshot. Both review and execution
        # consume this definition and the same chosen directory.
        self.execution_recipe = copy.deepcopy(self.base_execution_recipe)
        if self.destination_mode == 'beside':
            self.execution_recipe['destination'] = {'mode': 'beside'}
        elif self.destination_mode == 'directory':
            self.execution_recipe['destination'] = {
                'mode': 'directory', 'ask': True,
            }
            self.chosen = self.override_directory or None
        if self.destination_mode == 'beside':
            description = 'Beside each source'
        elif self.destination_mode == 'directory':
            description = self.override_directory or 'Choose a directory before running'
        else:
            description = self.chosen or self.destination_description()
        self.destination_label.setText('Destination: ' + description)
        self.destination_label.setToolTip(description)
        self.choose_destination.setVisible(self.destination_mode == 'directory' or
                                          (self.destination_mode == 'default' and bool(self.recipe['destination'].get('ask'))))

    def change_destination_mode(self, *_):
        previous_mode = self.destination_mode
        if previous_mode == 'default': self.default_chosen = self.chosen
        self.destination_mode = self.destination_choice.currentData()
        if self.destination_mode == 'default': self.chosen = self.default_chosen
        self.apply_destination_override()
        self.start_preflight()
        if self.destination_mode == 'directory' and not self.override_directory:
            self.select_destination()

    def select_destination(self):
        directory = QFileDialog.getExistingDirectory(self, 'Choose output directory')
        if directory:
            self.chosen = directory
            if self.destination_mode == 'directory': self.override_directory = directory
            self.apply_destination_override()
            self.start_preflight()

    def start_execution(self):
        if not self.run_button.isEnabled() or self.worker is not None: return
        if self.validated_snapshot != (self.execution_recipe, self.files, self.chosen):
            self.start_preflight(); return
        if self.saved_definition is not None:
            try:
                if lookup_recipe(self.selected_id) != self.saved_definition:
                    raise RecipeError('Selected recipe changed. Select it again to review the current definition.')
            except (OSError, RecipeError) as exc:
                self.invalidate_preflight()
                self.selector.blockSignals(True); self.selector.setCurrentIndex(-1); self.selector.blockSignals(False)
                self.summary.setText(str(exc)); return
        self.run_button.setEnabled(False); self.choose_destination.setEnabled(False)
        if self.operation_title:
            self.back_button.setEnabled(False)
        self.selector.setEnabled(False); self.search.setEnabled(False); self.create_button.setEnabled(False)
        self.edit_button.setEnabled(False); self.destination_choice.setEnabled(False)
        self.add_photos.setEnabled(False); self.remove_selected.setEnabled(False); self.clear_list.setEnabled(False); self.inputs.setEnabled(False)
        recipe, files, chosen = self.validated_snapshot
        self.job_status = JobStatus(self.operation_title or 'Run recipe',len(self.files))
        self.progress = JobProgressDialog(
            ('Applying ' + self.operation_title + '…')
            if self.operation_title else 'Running recipe…',
            'Cancel all', 0, len(self.files), self
        )
        if not self.operation_title:
            self.progress.setWindowTitle(
                'KIMng - ' + recipe['name'] + ' - Progress'
            )
        self.progress.setWindowModality(Qt.WindowModal); self.progress.setMinimumDuration(0)
        self.progress.setAutoClose(False); self.progress.setAutoReset(False)
        self.execution_succeeded = False
        self.worker = RecipeWorker(
            recipe, files, chosen, self,
            approved_plan=self.approved_plan,
            omit_overlay_metadata=self.omit_overlay_metadata,
            auto_metadata_fallback=(
                bool(self.operation_title)
                and 'watermark / overlay'
                    in self.operation_title.casefold()
                and len(files) == 1
                and not self.omit_overlay_metadata
            ),
        )
        self.progress.canceled.connect(self.cancel_execution)
        self.worker.item_started.connect(self.execution_started)
        self.worker.item_finished.connect(self.execution_item)
        self.worker.stage_changed.connect(self.execution_stage)
        self.worker.finished.connect(self.execution_finished)
        self.cancel_button.setText('Cancel all')
        self.worker.start()

    @Slot(str, int)
    def execution_started(self, source, index):
        self.job_status.start(source,index)
        self.progress.setLabelText(self.job_status.label()); self.progress.setValue(index - 1)

    @Slot(dict, int)
    def execution_item(self, result, index):
        self.job_status.finish(result)
        self.progress.setLabelText(self.job_status.label()); self.progress.setValue(index)

    def execution_stage(self, message):
        if self.worker is not None and self.sender() == self.worker:
            self.job_status.stage = message; self.progress.setLabelText(self.job_status.label())

    def cancel_execution(self):
        if self.worker is not None:
            self.worker.requestInterruption(); self.job_status.cancelling=True
            self.progress.setLabelText(self.job_status.label())

    @Slot()
    def execution_finished(self):
        worker = self.worker; self.results = worker.results; self.worker = None
        self.execution_succeeded = (bool(self.files) and not worker.cancelled and not worker.error
                                    and len(worker.results) == len(self.files)
                                    and all(result['ok'] for result in worker.results))
        self.progress.complete(); self.progress.deleteLater()
        skipped=[]
        for index,result in enumerate(worker.results):
            self.inputs.topLevelItem(index).setText(1,'Succeeded' if result['ok'] else 'Cancelled' if result.get('cancelled') else 'Failed')
        if worker.cancelled or worker.error:
            for index in range(len(worker.results),len(self.files)):
                result={'source':str(self.files[index]),'ok':False,'skipped':True,'error':'Not scheduled after cancellation' if worker.cancelled else 'Not scheduled after job error'}
                skipped.append(result); self.job_status.finish(result)
                self.inputs.topLevelItem(index).setText(1,'Skipped')
        self.summary.setText(self.job_status.label().split('\n')[-1] + ('; cancelled before remaining files' if worker.cancelled else '') + ('; execution error' if worker.error else ''))
        report = [r['output'] if r['ok'] else r['source'] + ': ' + r['error'] for r in worker.results+skipped]
        if worker.error: report.append(worker.error)
        self.diagnostics.setPlainText('\n'.join(report))
        self.diagnostics.setMaximumHeight(200)
        # The existing bottom panel becomes the completion report.
        # No popup or additional report window.
        if not self.operation_title:
            self.technical_details_button.setChecked(True)
            self.sync_diagnostics()
        if worker.error or not self.execution_succeeded:
            if self.operation_title: self.diagnostics.show()
            else: self.sync_diagnostics()
        if self.operation_title:
            failures = [
                result.get('error', '')
                for result in worker.results
                if not result.get('ok')
            ]
            if worker.error:
                failures.append(worker.error)

            self.show_operation_problems(failures)

            if failures:
                succeeded = sum(
                    bool(result.get('ok'))
                    for result in worker.results
                )
                failed = len(failures)
                self.summary.setText(
                    f"{succeeded} succeeded, "
                    f"{failed} failed. "
                    "Failed outputs were not published."
                )

        metadata_warnings = [
            result.get('warning', '')
            for result in worker.results
            if result.get('ok')
            and result.get('warning')
        ]

        if self.operation_title and metadata_warnings:
            self.summary.setText(metadata_warnings[0])

            created = [
                result['output']
                for result in worker.results
                if result.get('ok') and result.get('output')
            ]

            self.diagnostics.setPlainText(
                'Created: ' + '\\n'.join(created)
            )
            self.diagnostics.setMaximumHeight(72)
            self.diagnostics.show()

            if hasattr(self, 'problem_explanation'):
                self.problem_explanation.hide()
            if hasattr(self, 'technical_details_button'):
                self.technical_details_button.hide()

        self.cancel_button.setText('Close')

        failures = [
            item.get("error", "")
            for item in worker.results
            if not item.get("ok")
        ]
        if worker.error:
            failures.append(worker.error)


        if not self._closing:
            for control in (self.selector,self.search,self.create_button,self.choose_destination,self.destination_choice): control.setEnabled(True)
            self.update_edit_button()
            self.update_file_actions()
        worker.deleteLater()
        if self._closing: super().reject()

    def reject(self):
        if self.filters_worker is not None:
            self._closing=True; self._pending_picker=False; self.filters_worker.requestInterruption()
            if self.add_worker is not None: self.add_worker.requestInterruption()
            if self.preflight_worker is not None: self.preflight_worker.requestInterruption()
            if self.worker is not None: self.cancel_execution()
            self.run_button.setEnabled(False); return
        if self.editor_dialog is not None:
            self._close_after_editor=True; self.editor_dialog.reject(); return
        if self.add_worker is not None:
            self._closing = True; self._addition_queue.clear()
            self.add_worker.requestInterruption()
            if self.preflight_worker is not None: self.preflight_worker.requestInterruption()
            self.run_button.setEnabled(False)
            self.summary.setText('Cancelling current operation; waiting for cleanup…')
            return
        if self.worker is not None:
            self.cancel_execution(); self._closing = True; return
        if self.preflight_worker is not None:
            self._closing = True; self.preflight_worker.requestInterruption()
            self.summary.setText('Cancelling current operation; waiting for cleanup…'); return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None or self.preflight_worker is not None or self.add_worker is not None or self.editor_dialog is not None or self.filters_worker is not None:
            self.reject(); event.ignore()
        else:
            self.save_display_preferences()
            event.accept()


def launch_run(recipe_id, files):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        recipe = lookup_recipe(recipe_id) if recipe_id else None
        dialog = RunRecipeDialog(recipe, files, load_library().folders)
        dialog.exec()
        return 0
    except (OSError, RecipeError, UnicodeError) as exc:
        QMessageBox.critical(None, 'Run recipe', str(exc))
        return 1
