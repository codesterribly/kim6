"""Read-only confirmation, responsive batch inspection, and shared recipe property view."""
import copy
import os
import re
import stat
import sys
import time
from pathlib import Path
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtCore import QThread, Signal, Slot, Qt, QTimer, QStandardPaths, QSettings, QUrl
from PySide6.QtGui import QPalette, QIcon, QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QSplitter, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QPlainTextEdit, QFileDialog, QProgressDialog, QMessageBox, QProgressBar, QScrollArea, QSizePolicy)
from kim_job import JobStatus, grouped_warnings, WarningGroups
from kim_recipe_core import (CONCRETE_SCHEMA, AUTHORED_SCHEMA, RecipeError, PreviewRow, builtins, load_library, lookup_recipe,
                             recipe_title, RecipeLibrary, library_groups, handler, preview, execute, validate,
                             approve_rows, block_output_collisions, number_review_outputs, output_key,
                             load_remembered_values, save_remembered_values, clear_remembered_values)

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
        super().__init__(parent); self.finished_job=False; self.resize(520, 165)
        self.setWindowTitle('KIMng - Job progress')
        layout=QVBoxLayout(self)
        layout.setSpacing(8)
        self.label=QLabel(text); self.label.setWordWrap(True); self.label.setTextFormat(Qt.PlainText)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard); layout.addWidget(self.label)
        self.bar=QProgressBar(); self.bar.setRange(minimum,maximum); layout.addWidget(self.bar)
        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.hide()
        layout.addWidget(self.status_label)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.addStretch(1)
        stop_icon = QIcon.fromTheme('process-stop')
        self.cancel_button = QPushButton(stop_icon, cancel_text) if not stop_icon.isNull() else QPushButton(cancel_text)
        self.cancel_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cancel_button.clicked.connect(self.cancel)
        btn_row.addWidget(self.cancel_button)
        layout.addLayout(btn_row)

    def setMinimumDuration(self,_): self.show()
    def setAutoClose(self,_): pass
    def setAutoReset(self,_): pass
    def setLabelText(self,text): self.label.setText(text)
    def setStatusText(self, text):
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
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
        from kim_psd_source import source_session, protected_header as psd_header
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
        inspected_rows = []

        for index, source in enumerate(self.files, 1):
            if self.isInterruptionRequested():
                self.cancelled = True
                break

            self.file_started.emit(
                str(source), index, len(self.files)
            )

            try:
                from kim_process import inspection_context
                from kim_recipe_image import checked_input_headers

                with (
                    inspection_context(
                        self.stage_changed.emit,
                        self.isInterruptionRequested
                    ),
                    checked_input_headers(self.checked_inputs)
                ):
                    row = preview(
                        self.recipe,
                        [source],
                        self.chosen,
                        start_index=index
                    )[0]

                if self.binding_error:
                    row.problems.append(self.binding_error)

                if (
                    self.recipe['destination'].get('ask')
                    and not self.chosen
                ):
                    row.problems.append(
                        'Choose an output directory before running.'
                    )

            except Exception as exc:
                row = PreviewRow(
                    str(source), problems=[str(exc)]
                )

            if self.isInterruptionRequested():
                self.cancelled = True
                row = PreviewRow(
                    str(source),
                    properties={'_cancelled': True}
                )

            inspected_rows.append(row)

            # Show inspection progress normally.
            # The completed batch will replace these provisional
            # rows with its final, collision-resolved output plan.
            self.inspected.emit(
                copy.deepcopy(row), index - 1
            )

            if self.cancelled:
                break

        if (
            not self.cancelled
            and not self.isInterruptionRequested()
            and len(inspected_rows) == len(self.files)
        ):
            # Block intra-batch duplicate output targets fail-closed before
            # resolving pre-existing filenames on disk. Conflicting selected
            # sources must never be silently renumbered into separate outputs.
            block_output_collisions(inspected_rows)
            non_duplicate = [
                row for row in inspected_rows
                if not any(
                    'multiple selected sources target ' in p
                    for p in row.problems
                )
            ]
            if non_duplicate:
                number_review_outputs(non_duplicate)
            # Re-verify across the entire batch in case numbering touched
            # another selected source's target or an aliased destination.
            block_output_collisions(inspected_rows)

            for index, row in enumerate(inspected_rows):
                if self.isInterruptionRequested():
                    self.cancelled = True
                    break

                self.inspected.emit(
                    copy.deepcopy(row), index
                )


def confirmation_snapshot(recipe, values=None):
    """Resolve parameters and bind inherited Settings for this confirmation only.

    Saved references and authored definitions remain untouched. Parameterized
    definitions resolve strictly via kim_recipe_params.resolve_recipe(); ordinary
    concrete definitions keep the established best-effort (snapshot, error) return.
    """
    from kim_recipe_params import (
        is_parameterized,
        materialize_settings,
        resolve_recipe,
    )
    if is_parameterized(recipe) or values is not None:
        try:
            return resolve_recipe(recipe, values), None
        except (OSError, RecipeError) as exc:
            return None, str(exc)

    snapshot = copy.deepcopy(recipe)
    if snapshot.get('schema') == AUTHORED_SCHEMA:
        snapshot['schema'] = CONCRETE_SCHEMA
        snapshot.pop('parameters', None)
    media = handler(recipe['media'])
    error = None
    try:
        media.validate_context(recipe['steps'])
    except (OSError, RecipeError) as exc:
        error = str(exc)
    settings_error = materialize_settings(
        snapshot, media, strict=False, include_disabled=True
    )
    if error is None and settings_error is not None:
        error = settings_error
    return snapshot, error


def selection_title(recipe, folders):
    try:
        return recipe_title(recipe, folders)
    except RecipeError:
        return recipe.get('name', '')


def verify_editor_handoff(recipe, baseline):
    """Verify the stored definition without discarding temporary edits."""
    if not isinstance(recipe, dict) or not isinstance(baseline, dict):
        raise RecipeError('Missing saved Recipe definition.')

    if recipe.get('id') != baseline.get('id'):
        raise RecipeError('The selected Recipe identity has changed.')

    saved = lookup_recipe(recipe['id'])

    if saved != baseline:
        raise RecipeError(
            'The selected recipe has changed. '
            'Open the editor and review it again.'
        )

    if recipe != saved:
        if 'dolphin_shortcut' in saved:
            raise RecipeError(
                'Save the User Recipe before running it.'
            )

        # Built-ins permit temporary step settings, not
        # changes to their identity, structure or destination.
        requested_header = {
            key: value for key, value in recipe.items()
            if key != 'steps'
        }
        saved_header = {
            key: value for key, value in saved.items()
            if key != 'steps'
        }

        if requested_header != saved_header:
            raise RecipeError(
                'A built-in Recipe must be duplicated '
                'before changing its definition.'
            )

        if (
            [step['op'] for step in recipe['steps']]
            != [step['op'] for step in saved['steps']]
        ):
            raise RecipeError(
                'A built-in Recipe must be duplicated '
                'before changing its operations.'
            )

    return copy.deepcopy(saved)


class RunRecipeDialog(QDialog):
    def __init__(
        self, recipe, files, folders=(), parent=None,
        chosen=None, operation_title=None, *, saved_baseline=None
    ):
        super().__init__(parent)
        self.recipe = copy.deepcopy(recipe)
        self.operation_title = operation_title
        self.omit_overlay_metadata = False
        self.files = list(files)
        self.authored_recipe = None
        self._session_param_values = {}
        self._approved_run_remember = None
        if recipe is None:
            self.runner_phase = 'empty'
            self.execution_recipe, self.binding_error = None, None
        elif not operation_title:
            from kim_recipe_params import is_parameterized, validate_authored
            if is_parameterized(recipe):
                self.authored_recipe = validate_authored(recipe)
                self.runner_phase = 'settings'
                self.execution_recipe, self.binding_error = None, None
            else:
                self.runner_phase = 'review'
                self.execution_recipe, self.binding_error = confirmation_snapshot(recipe)
        else:
            self.runner_phase = 'review'
            self.execution_recipe, self.binding_error = confirmation_snapshot(recipe)
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
            if saved_baseline is not None:
                self.saved_definition = verify_editor_handoff(
                    recipe, saved_baseline
                )
            else:
                try:
                    saved = lookup_recipe(recipe['id'])
                    if saved == recipe:
                        self.saved_definition = copy.deepcopy(saved)
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
        self._scroll_review_to_top = self.runner_phase == 'review'
        self.preflight_active = None
        self.preflight_clock = QTimer(self); self.preflight_clock.setInterval(1000)
        self.preflight_clock.timeout.connect(self.refresh_preflight_status)
        self.results = []
        self.execution_succeeded = False
        self.editor_dialog = None; self._close_after_editor = False
        self._update_window_title()
        self.resize(
            1010 if operation_title else 1100,
            635 if operation_title else 780
        )
        self.settings = QSettings('KIMng', 'RecipeReview' if operation_title else 'RecipeRunner')
        layout = QVBoxLayout(self)
        selection = QHBoxLayout()
        label = QLabel('&Recipe:')
        self.search = QLineEdit(); self.search.setPlaceholderText('Search recipes…')
        self.search.setAccessibleName('Search recipes or folders')
        self.selector = QComboBox(); self.selector.setPlaceholderText('Choose a recipe…')
        self.selector.setMinimumContentsLength(24)
        self.selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        label.setBuddy(self.selector)
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(210)
        self.search.setMaximumWidth(300)
        selection.addWidget(label)
        selection.addWidget(self.search)
        selection.addWidget(self.selector, 1)
        self.create_button = QPushButton('New Recipe…')
        self.create_button.clicked.connect(self.create_recipe)
        self.edit_button = QPushButton()
        self.edit_button.clicked.connect(self.edit_recipe)
        selection.addWidget(self.edit_button)
        selection.addWidget(self.create_button)
        layout.addLayout(selection)

        self.search_results = QTreeWidget()
        self.search_results.setAccessibleName(
            'Matching recipes'
        )
        self.search_results.setHeaderHidden(True)
        self.search_results.setRootIsDecorated(False)
        self.search_results.setUniformRowHeights(True)
        self.search_results.setMaximumHeight(130)
        self.search_results.itemClicked.connect(
            self.choose_search_result
        )
        self.search_results.itemActivated.connect(
            self.choose_search_result
        )
        self.search_results.hide()

        layout.addWidget(self.search_results)
        self.selection_hint=QLabel('Select a recipe to preview its planned outputs.')
        self.selection_hint.setWordWrap(True); self.selection_hint.setVisible(recipe is None); layout.addWidget(self.selection_hint)
        self.search.textChanged.connect(self.search_recipes)
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

        self.recipe_description_group = QWidget()
        description_layout = QVBoxLayout(
            self.recipe_description_group
        )
        description_layout.setContentsMargins(0, 0, 0, 0)
        from PySide6.QtWidgets import QSizePolicy

        self.recipe_description = QLabel()
        self.recipe_description.setTextFormat(Qt.RichText)
        self.recipe_description.setWordWrap(True)
        self.recipe_description.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.recipe_description.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.recipe_description.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Maximum
        )
        self.recipe_description.setAccessibleName(
            'Selected Recipe description'
        )
        description_layout.addWidget(self.recipe_description)
        layout.addWidget(self.recipe_description_group)

        description = (
            recipe.get('description', '').strip()
            if recipe and not operation_title else ''
        )
        self.set_recipe_description(description)
        self.recipe_description_group.setVisible(bool(description))

        self.count = QLabel('Inputs: ' + file_count(len(self.files)))
        if operation_title:
            layout.addWidget(self.count)
        else:
            self.count.hide()
        split = self.splitter = QSplitter(Qt.Horizontal); layout.addWidget(split, 1)
        split.setChildrenCollapsible(False)
        left = QWidget(); left.setMinimumWidth(0); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0,0,0,0); split.addWidget(left)
        inputs = QGroupBox(
            'Selected images: choose one to review'
            if operation_title
            else 'Selected images'
        )
        inp_layout = QVBoxLayout(inputs)
        self.inputs = InputFilesView(); self.inputs.setHeaderLabels(['Filename', 'Status'])
        self.inputs.setAccessibleName('Selected images and review status')
        self.inputs.header().setStretchLastSection(False)
        self.inputs.header().setSectionResizeMode(0, QHeaderView.Stretch)
        if operation_title:
            self.inputs.header().setSectionResizeMode(1, QHeaderView.Fixed)
            self.inputs.setColumnWidth(1, 175)
        else:
            self.inputs.header().setMinimumSectionSize(80)
            self.inputs.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.inputs.setRootIsDecorated(False)
        initial_status = self._initial_queue_status()
        for source in self.files:
            item = QTreeWidgetItem([Path(source).name, initial_status]); item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.inputs.currentItemChanged.connect(self.show_selected)
        inp_layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.add_photos = QPushButton('Add images…'); self.add_photos.clicked.connect(self.pick_files)
        self.remove_selected = QPushButton(
            'Remove selected' if operation_title else 'Remove'
        )
        self.remove_selected.clicked.connect(self.remove_files)
        self.remove_selected.setToolTip('Remove selected images')

        self.clear_list = QPushButton(
            'Clear list' if operation_title else 'Clear'
        )
        self.clear_list.clicked.connect(self.clear_files)
        self.clear_list.setToolTip('Clear the selected image list')
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
            operations.setMinimumHeight(130)
        self.operations_panel = operations

        if not operation_title:
            operation_tools = QHBoxLayout()
            operation_tools.addStretch(1)

            self.expand_operations = QPushButton(
                'Expand all'
            )
            self.collapse_operations = QPushButton(
                'Collapse all'
            )

            self.expand_operations.clicked.connect(
                self.operations.expandAll
            )
            self.collapse_operations.clicked.connect(
                self.operations.collapseAll
            )

            operation_tools.addWidget(self.expand_operations)
            operation_tools.addWidget(self.collapse_operations)
            op_layout.insertLayout(0, operation_tools)

        # Internal Recipe steps remain available to the engine,
        # but standalone image operations do not show the tree.
        if operation_title:
            operations.hide()
        right = QGroupBox(
            'Planned output'
        )
        right_layout = QVBoxLayout(right)
        right.setMinimumWidth(0)
        if operation_title:
            self.output_filename = exact_field(right_layout, 'Filename')
            self.output_directory = exact_field(right_layout, 'Output Directory')
        else:
            from PySide6.QtWidgets import QFormLayout

            self.output_fields = output_fields = QFormLayout()
            output_fields.setSpacing(5)
            right_layout.addLayout(output_fields)

            for caption, attribute in (
                ('Filename', 'output_filename'),
                ('Output directory', 'output_directory'),
            ):
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
                output_fields.addRow(caption, value)
        self.properties_button = QPushButton('Show output properties')
        self.properties_button.setCheckable(True)
        right_layout.addWidget(self.properties_button)
        if operation_title:
            self.properties = PropertyView()
        else:
            from kim_recipe_dialog import RecipePreviewTree
            self.properties = RecipePreviewTree()

        self.properties.setMinimumHeight(140)
        right_layout.addWidget(
            self.properties, 0 if operation_title else 2
        )
        self.properties_button.toggled.connect(self.properties.setVisible)
        self.properties_button.toggled.connect(lambda expanded: self.properties_button.setText(
            'Hide output properties' if expanded else 'Show output properties'))
        self.properties_button.setChecked(
            self.settings.value(
                'properties_expanded', True, type=bool
            )
        )
        self.properties.setVisible(self.properties_button.isChecked())
        self.operations_button = QPushButton()
        self.operations_button.setCheckable(True)
        right_layout.addWidget(self.operations_button)
        right_layout.addWidget(operations, 1 if not operation_title else 0)
        self.operations_button.toggled.connect(operations.setVisible)
        self.operations_button.toggled.connect(self.update_operation_summary)
        self.operations_button.setChecked(
            not operation_title and self.settings.value(
                'operations_expanded', False, type=bool
            )
        )
        operations.setVisible(self.operations_button.isChecked() and not operation_title and self.recipe is not None)
        self.operations_button.setVisible(not operation_title and self.recipe is not None)
        self.update_operation_summary()
        if operation_title:
            right_layout.addStretch(1)
        preview_scroll = self.preview_scroll = QScrollArea(); preview_scroll.setWidgetResizable(True)
        preview_scroll.setMinimumWidth(220)

        if operation_title:
            preview_scroll.setWidget(right)
        else:
            from PySide6.QtWidgets import QStackedWidget

            self.review_stack = QStackedWidget()
            self.review_stack.setMinimumSize(0, 0)

            welcome = QWidget()
            welcome_layout = QVBoxLayout(welcome)
            welcome_layout.setContentsMargins(24, 24, 24, 24)
            welcome_layout.addStretch(1)

            welcome_title = QLabel('Choose a Recipe to start')
            font = welcome_title.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 3)
            welcome_title.setFont(font)
            welcome_title.setAlignment(Qt.AlignCenter)

            welcome_description = QLabel(
                'Choose from the list above or search for a recipe.\n\n'
                'Review the planned changes before running.'
            )
            welcome_description.setWordWrap(True)
            welcome_description.setAlignment(Qt.AlignCenter)

            arrow = QLabel()
            arrow.setAlignment(Qt.AlignCenter)

            arrow_icon = QIcon.fromTheme('go-up')
            if not arrow_icon.isNull():
                arrow.setPixmap(arrow_icon.pixmap(48, 48))
            else:
                arrow.setText('↑')
                arrow_font = arrow.font()
                arrow_font.setPointSize(32)
                arrow.setFont(arrow_font)

            welcome_layout.addWidget(arrow)
            welcome_layout.addSpacing(6)
            welcome_layout.addWidget(welcome_title)
            welcome_layout.addSpacing(10)
            welcome_layout.addWidget(welcome_description)
            welcome_layout.addStretch(1)

            self.review_stack.addWidget(welcome)
            self.review_stack.addWidget(right)

            from kim_recipe_param_ui import RecipeSettingsPage
            self.settings_page = RecipeSettingsPage(self.review_stack)
            self.settings_page.changed.connect(self.settings_changed)
            self.settings_page.clear_remembered_requested.connect(
                self._clear_remembered_for_current_recipe
            )
            self.review_stack.addWidget(self.settings_page)
            if self.authored_recipe is not None:
                self._load_settings_for_authored(self.authored_recipe, self.selected_id)

            self.properties_button.hide()
            self.operations_button.hide()

            self.properties_button.setChecked(True)
            self.operations_button.setChecked(True)

            self.properties.setMinimumHeight(100)
            self.operations_panel.setMinimumHeight(100)

            self.planned_output_group = right
            self.output_properties_group = properties_group = QGroupBox(
                'Output properties'
            )
            properties_layout = QVBoxLayout(properties_group)
            self.property_tools = QWidget()
            property_tools_layout = QHBoxLayout(self.property_tools)
            property_tools_layout.setContentsMargins(0, 0, 0, 0)
            property_tools_layout.addStretch(1)

            self.expand_properties = QPushButton('Expand all')
            self.collapse_properties = QPushButton('Collapse all')

            self.expand_properties.clicked.connect(
                self.properties.expandAll
            )
            self.collapse_properties.clicked.connect(
                self.properties.collapseAll
            )

            property_tools_layout.addWidget(self.expand_properties)
            property_tools_layout.addWidget(self.collapse_properties)

            properties_layout.addWidget(self.property_tools)
            properties_layout.addWidget(self.properties)

            self.no_images_message = QWidget()
            empty_layout = QVBoxLayout(self.no_images_message)
            empty_layout.addStretch(1)

            from PySide6.QtCore import QSize
            from PySide6.QtWidgets import QStyle

            add_icon = QIcon.fromTheme('image-x-generic')

            if add_icon.isNull():
                add_icon = QIcon.fromTheme('document-open')

            if add_icon.isNull():
                add_icon = self.style().standardIcon(
                    QStyle.StandardPixmap.SP_DialogOpenButton
                )

            self.empty_add_images_button = QPushButton(
                add_icon,
                'Add Images to start'
            )

            self.empty_add_images_button.setIconSize(
                QSize(32, 32)
            )

            self.empty_add_images_button.setMinimumSize(
                220, 58
            )

            self.empty_add_images_button.setCursor(
                Qt.PointingHandCursor
            )

            self.empty_add_images_button.setToolTip(
                'Choose images to run this recipe on'
            )
            self.empty_add_images_button.clicked.connect(
                self.pick_files
            )

            font = self.empty_add_images_button.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 2)
            self.empty_add_images_button.setFont(font)

            empty_layout.addWidget(
                self.empty_add_images_button,
                0, Qt.AlignCenter
            )

            empty_layout.addSpacing(6)

            hint = QLabel('Or drag images into the list on the left.')
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)

            empty_layout.addWidget(hint)
            empty_layout.addStretch(1)

            properties_layout.addWidget(
                self.no_images_message, 1
            )
            self.no_images_message.hide()

            self.review_sections = QSplitter(Qt.Vertical)
            self.review_sections.setChildrenCollapsible(False)
            self.review_sections.addWidget(properties_group)
            self.review_sections.addWidget(self.operations_panel)
            self.review_sections.setStretchFactor(0, 3)
            self.review_sections.setStretchFactor(1, 2)
            self.review_sections.setSizes([260, 180])

            right_layout.addWidget(self.review_sections, 1)

            preview_scroll.setWidget(self.review_stack)
            preview_scroll.setFrameShape(QScrollArea.NoFrame)
            preview_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff
            )
            preview_scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarAlwaysOff
            )

            self.update_recipe_review_presentation()
        split.addWidget(preview_scroll)
        preview_scroll.setVisible(
            recipe is not None or not operation_title
        )
        split.setSizes(
            [390, 730] if operation_title else [380, 680]
        )
        dest = QHBoxLayout()
        self.destination_caption = QLabel(
            'Output location:' if operation_title else 'Destination:'
        )
        dest.addWidget(self.destination_caption)
        self.destination_label = QLabel(); self.destination_label.setTextFormat(Qt.PlainText)
        self.destination_label.setWordWrap(True)
        self.choose_destination = QPushButton(QIcon.fromTheme('folder-open'), 'Choose output directory…')
        self.choose_destination.clicked.connect(self.select_destination)
        self.choose_destination.setVisible(
            self.runner_phase == 'review'
            and bool(recipe and recipe['destination'].get('ask'))
        )
        self.destination_label.setText(
            (
                ('Destination: ' if operation_title else '')
                + self.destination_description()
            ) if recipe and self.runner_phase == 'review' else ''
        )
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
        # Destination appears below the review workspace.
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
        self.open_output_button = QPushButton(
            QIcon.fromTheme('folder-open'),
            'Open output directory',
        )
        self.open_output_button.clicked.connect(self.open_selected_output_directory)
        self.open_output_button.hide()
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
            self.completion_tools = QHBoxLayout()
            self.completion_tools.setContentsMargins(0, 0, 0, 0)
            self.completion_tools.setSpacing(8)
            self.completion_tools.addWidget(self.open_output_button)
            self.completion_tools.addWidget(self.technical_details_button)
            self.completion_tools.addStretch(1)
            layout.insertLayout(layout.indexOf(self.diagnostics), self.completion_tools)
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

        layout.addSpacing(6)
        layout.addLayout(dest)
        safety = QLabel(
            'Originals are not being changed. KIMng saves only the '
            'exact reviewed filenames. A collision blocks publication '
            'and requires a new review. Finished results stay put '
            'if you cancel or something fails.'
            if operation_title else
            'Originals remain unchanged. Outputs are saved exactly '
            'as reviewed. Filename conflicts require a new review.'
        )
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
        else:
            self.settings_back_button = QPushButton('Back')
            style_button(self.settings_back_button, 'back')
            self.settings_back_button.clicked.connect(
                self.open_settings_page
            )
            self.settings_back_button.hide()
            buttons.addWidget(self.settings_back_button)
        buttons.addStretch(1)
        if not operation_title:
            self.review_button = QPushButton('Review Changes')
            style_button(self.review_button, 'review')
            self.review_button.setEnabled(False)
            self.review_button.clicked.connect(
                self.enter_review_from_settings
            )
            self.review_button.hide()
            buttons.addWidget(self.review_button)
        self.run_button = QPushButton(
            ('Apply Changes to ' + file_count(len(self.files)).title()
             if operation_title else
             f'Run Recipe on {len(self.files)} '
             + ('image' if len(self.files) == 1 else 'images'))
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
            self.technical_details_button.setChecked(False)
        default_size = (1010, 635) if operation_title else (1060, 700)
        if not operation_title and self.runner_phase == 'settings':
            param_count = len((self.authored_recipe or {}).get('parameters', ()))
            if param_count <= 2:
                default_size = (1060, 540)
        restore_review_geometry(
            self, self.settings, default_size
        )
        restore_splitter(
            self.splitter, self.settings, 'splitter',
            [650, 430] if operation_title else [380, 680]
        )
        self.finished.connect(self.save_display_preferences)
        self._sync_settings_example_source()
        self.update_recipe_review_presentation()
        self.update_summary()
        self.start_preflight()
        if not operation_title and self.runner_phase == 'settings':
            QTimer.singleShot(0, self._focus_initial_settings)

    def _update_window_title(self):
        if self.operation_title:
            self.setWindowTitle(self.operation_title + ' - Review Changes')
        elif self.runner_phase == 'settings':
            self.setWindowTitle('KIMng - Run a Recipe - Settings')
        elif getattr(self, '_execution_completed', False):
            self.setWindowTitle('KIMng - Run a Recipe - Results')
        elif self.recipe is not None:
            self.setWindowTitle('KIMng - Run a Recipe - Review Changes')
        else:
            self.setWindowTitle('KIMng - Run a Recipe')

    def _initial_queue_status(self):
        if self.runner_phase == 'settings':
            return ''
        return 'Queued' if self.recipe else 'Select recipe'

    def _sync_settings_example_source(self):
        if self.operation_title or not hasattr(self, 'settings_page'):
            return
        source = None
        item = self.inputs.currentItem()
        if item is not None:
            index = self.inputs.indexOfTopLevelItem(item)
            if 0 <= index < len(self.files):
                source = self.files[index]
        if source is None and self.files:
            source = self.files[0]
        self.settings_page.set_example_source(source)

    def _focus_initial_settings(self):
        if (
            self.operation_title
            or self._closing
            or self.runner_phase != 'settings'
            or self.authored_recipe is None
            or not hasattr(self, 'settings_page')
        ):
            return
        self.settings_page.focus_first_required()

    def set_recipe_description(self, description):
        from html import escape

        safe = escape(description).replace(chr(10), '<br>')
        self.recipe_description.setText(
            '<b>Description:</b> ' + safe if safe else ''
        )

    def normalize_destination_caption(self):
        if self.operation_title:
            return

        label = self.destination_label.text()

        if label.startswith('Destination: '):
            self.destination_label.setText(
                label.removeprefix('Destination: ')
            )

        elif label.startswith('Output directory: '):
            self.destination_label.setText(
                label.removeprefix('Output directory: ')
            )

    def update_recipe_review_presentation(self):
        if self.operation_title or not hasattr(self, 'review_stack'):
            return

        selected = self.recipe is not None
        in_settings = selected and self.runner_phase == 'settings'
        in_review = selected and self.runner_phase == 'review'
        has_images = bool(self.files)
        show_output = in_review and has_images

        self.review_stack.setCurrentIndex(
            2 if in_settings else 1 if in_review else 0
        )
        self._update_window_title()

        self.properties_button.hide()
        self.operations_button.hide()
        self.selection_hint.hide()
        self.heading.hide()

        self.planned_output_group.setTitle(
            'Planned output' if show_output else ''
        )

        self.output_properties_group.setTitle(
            'Output properties' if show_output else ''
        )

        for index in range(self.output_fields.count()):
            item = self.output_fields.itemAt(index)
            widget = item.widget()
            if widget is not None:
                widget.setVisible(show_output)

        self.properties.setVisible(show_output)
        self.property_tools.setVisible(show_output)
        self.no_images_message.setVisible(
            in_review and not has_images
        )

        self.operations_panel.setVisible(in_review)

        effective_steps = (
            self.execution_recipe['steps']
            if self.execution_recipe is not None
            else (self.recipe['steps'] if selected else [])
        )
        enabled = sum(
            step.get('enabled', True) for step in effective_steps
        )

        self.operations_panel.setTitle(
            f'Recipe operations ({enabled} enabled, {len(effective_steps)} total)'
        )

        # During construction, destination and action buttons are created
        # after the review workspace.
        if hasattr(self, 'destination_caption'):
            self.destination_caption.setVisible(in_review)
            self.destination_choice.setVisible(in_review)
            self.destination_label.setVisible(in_review)
            self.normalize_destination_caption()

            if not in_review:
                self.choose_destination.hide()

        if hasattr(self, 'review_button'):
            self.review_button.setVisible(in_settings)
        if hasattr(self, 'run_button'):
            self.run_button.setVisible(not in_settings)
        if hasattr(self, 'settings_back_button'):
            self.settings_back_button.setVisible(
                in_review and self.authored_recipe is not None
            )

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
        present = bool(self.diagnostics.toPlainText())
        expanded = self.technical_details_button.isChecked()

        self.technical_details_button.setText(
            'Hide technical details' if expanded
            else 'Show technical details'
        )

        self.technical_details_button.setVisible(present)
        self.diagnostics.setVisible(present and expanded)

    def update_operation_summary(self):
        steps = (
            self.execution_recipe['steps']
            if self.execution_recipe is not None
            else (self.recipe['steps'] if self.recipe else [])
        )
        enabled = sum(step.get('enabled', True) for step in steps)
        action = 'Hide' if self.operations_button.isChecked() else 'Show'
        self.operations_button.setText(f'{action} operations ({enabled} enabled, {len(steps)} total)')

    def update_edit_button(self):
        self.edit_button.setText('Edit Recipe…')
        is_dev_draft = bool(
            self.selected_id and self.selected_id.startswith('dev-draft-')
        )
        self.edit_button.setEnabled(
            bool(self.recipe)
            and not is_dev_draft
            and self.editor_dialog is None
            and self.worker is None
        )
        self.edit_button.setToolTip(
            'Temporary development drafts are edited in the development Editor.'
            if is_dev_draft else ''
        )

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

        if hasattr(self, 'empty_add_images_button'):
            self.empty_add_images_button.setEnabled(
                self.add_photos.isEnabled()
            )
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
        self.update_recipe_review_presentation()
        selected={os.path.abspath(p) for p in self.files}
        self.checked_inputs={key:value for key,value in self.checked_inputs.items() if key in selected}
        self.inputs.clear()
        status_text = self._initial_queue_status()
        for source in self.files:
            item = QTreeWidgetItem([Path(source).name, status_text])
            item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.count.setText('Inputs: ' + file_count(len(self.files)))
        self.run_button.setText(
            ('Apply Changes to ' + file_count(len(self.files)).title()
             if self.operation_title else
             f'Run Recipe on {len(self.files)} '
             + ('image' if len(self.files) == 1 else 'images'))
        )
        self.update_file_actions()
        if preflight: self.start_preflight()
        if self.files: self.inputs.setCurrentItem(self.inputs.topLevelItem(0))
        self._sync_settings_example_source()

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
        source = self.base_execution_recipe or self.recipe
        d = source['destination']
        if d['mode'] == 'beside': return 'Beside each source'
        if d['mode'] == 'subfolder':
            if self.authored_recipe is not None:
                from kim_recipe_params import has_parameter_references
                authored_folder = (self.authored_recipe.get('destination') or {}).get('folder', '')
                if has_parameter_references(authored_folder):
                    return 'Subfolder beside each source: ' + d['folder']
            return d['folder'] + ' subfolder beside each source'
        return d.get('path', '')

    def fill_operations(self):
        self.operations.clear()
        if self.recipe is None or self.execution_recipe is None:
            return
        from kim_recipe_params import has_parameter_references

        format_display = {
            'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WebP', 'avif': 'AVIF',
            'bmp': 'BMP', 'gif': 'GIF', 'heic': 'HEIC', 'heif': 'HEIF',
            'jp2': 'JP2', 'jxl': 'JXL', 'pdf': 'PDF', 'tiff': 'TIFF',
        }
        pixel_fields = {
            ('image.resize', 'max_width'),
            ('image.resize', 'max_height'),
            ('image.resize_exact', 'width'),
            ('image.resize_exact', 'height'),
            ('image.resize_long_edge', 'pixels'),
        }

        media = handler(self.execution_recipe['media'])
        for index, (original, effective) in enumerate(zip(self.recipe['steps'], self.execution_recipe['steps']), 1):
            label, details = media.operation_details(effective)
            if original['op'] == 'image.auto_orient' and label == 'Auto-Orient':
                label = 'Auto-orient'
            enabled = effective.get('enabled', True)
            item = QTreeWidgetItem([
                f'{index}. {label}'
                + ('' if enabled else ' (Disabled)')
            ])
            definitions = media.operation_definitions()[original['op']]['parameters']
            bound_fields = original.get('bindings') or {}
            for (key, spec), (name, value) in zip(definitions.items(), details):
                if original['op'] == 'image.convert':
                    fmt = effective.get('format')

                    relevant_formats = {
                        'jpeg_progressive': ('jpeg',),
                        'jpeg_optimize': ('jpeg',),
                        'jp2_mode': ('jp2',),
                        'tiff_compression': ('tiff',),
                        'depth': ('png', 'jp2', 'tiff'),
                        'quality': (
                            'jpeg', 'webp', 'avif',
                            'heic', 'heif', 'jxl', 'jp2'
                        ),
                    }

                    if (
                        key in relevant_formats
                        and fmt not in relevant_formats[key]
                    ):
                        continue

                    if (
                        key == 'quality'
                        and fmt == 'jp2'
                        and effective.get('jp2_mode') != 'lossy'
                    ):
                        continue

                    if key == 'format':
                        value = format_display.get(str(value).casefold(), str(value).upper())

                elif original['op'] == 'image.color' and key == 'mode':
                    name = 'Color profile'
                    value = {'srgb': 'sRGB', 'preserve': 'Preserve'}.get(
                        str(value).casefold(), value
                    )

                if (original['op'], key) in pixel_fields and value.isdigit():
                    value = value + ' px'

                from_settings = (
                    key in bound_fields
                    or (
                        original['op'] == 'file.rename_output'
                        and key == 'pattern'
                        and has_parameter_references(original.get('pattern', ''))
                    )
                )

                if spec.get('settings_key'):
                    if from_settings:
                        value = value.rsplit(' (', 1)[0] + ' (from run settings)'
                    else:
                        value = value.rsplit(' (', 1)[0] + (' (inherited from Settings)' if original.get(key) is None else ' (recipe override)')
                elif from_settings:
                    value = value + ' (from run settings)'
                child = QTreeWidgetItem([name + ': ' + value]); child.setToolTip(0, child.text(0)); item.addChild(child)
            if not enabled:
                font = item.font(0)
                font.setItalic(True)
                item.setFont(0, font)

            self.operations.addTopLevelItem(item)

        self.operations.collapseAll()

    def search_recipes(self, *_):
        if self.operation_title:
            return

        self.refresh_selector()
        self.search_results.clear()

        if not self.search.text().strip():
            self.search_results.hide()
            return

        if self._search_matches:
            for title, recipe_id in self._search_matches:
                item = QTreeWidgetItem([title])
                item.setData(0, Qt.UserRole, recipe_id)
                item.setToolTip(0, title)
                self.search_results.addTopLevelItem(item)
        else:
            item = QTreeWidgetItem(['No matching recipes'])
            item.setFlags(Qt.NoItemFlags)
            self.search_results.addTopLevelItem(item)

        row_height = max(
            self.search_results.sizeHintForRow(0),
            self.search_results.fontMetrics().height() + 4
        )

        visible_rows = min(
            self.search_results.topLevelItemCount(), 7
        )

        frame = self.search_results.frameWidth() * 2

        self.search_results.setFixedHeight(
            row_height * visible_rows + frame + 4
        )

        self.search_results.show()

    def choose_search_result(self, item, column=0):
        if not self.search_results.isVisible():
            return

        recipe_id = item.data(0, Qt.UserRole)

        if not recipe_id:
            return

        index = self.selector.findData(recipe_id)

        if index < 0:
            return

        self.search_results.hide()

        # Use the existing selection workflow. Searching itself
        # never changes the selected Recipe or image queue.
        if index != self.selector.currentIndex():
            self.selector.setCurrentIndex(index)

        self.selector.setFocus(Qt.OtherFocusReason)

    def refresh_selector(self, *args):
        if self.operation_title: return
        query = self.search.text().casefold().strip()
        self.selector.blockSignals(True); self.selector.clear()
        match_count = 0
        self._search_matches = []

        for folder_id, name, recipes in library_groups(self.library):
            matches = [
                r for r in recipes
                if all(
                    word in (
                        name + ' ' + r['name'] + ' '
                        + r.get('description', '')
                    ).casefold()
                    for word in query.split()
                )
            ]
            if not matches:
                continue

            match_count += len(matches)

            self.selector.addItem(name, None)
            self.selector.model().item(self.selector.count() - 1).setEnabled(False)
            from kim_recipe_params import is_parameterized
            param_icon = QIcon.fromTheme('configure')
            for recipe in matches:
                self._search_matches.append((
                    name + ' / ' + recipe['name'],
                    recipe['id']
                ))

                parameterized = is_parameterized(recipe)
                if parameterized and not param_icon.isNull():
                    self.selector.addItem(
                        param_icon,
                        name + ' / ' + recipe['name'],
                        recipe['id']
                    )
                else:
                    self.selector.addItem(
                        name + ' / ' + recipe['name'],
                        recipe['id']
                    )
                tip = name + ' / ' + recipe['name']
                if parameterized:
                    tip += '\nAsks for settings when running.'
                self.selector.setItemData(self.selector.count() - 1, tip, Qt.ToolTipRole)
        if not match_count:
            self.selector.addItem('No matching recipes', None)
            self.selector.model().item(
                self.selector.count() - 1
            ).setEnabled(False)

        index=self.selector.findData(self.selected_id) if self.selected_id else -1
        if self.selected_id and index < 0 and self.recipe:
            # Filtering choices must not display 'Choose a recipe' while a
            # current (possibly unsaved) recipe is still being inspected.
            self.selector.addItem(
                selection_title(self.recipe, self.library.folders)
                + ' (current recipe)',
                self.selected_id
            )
            index=self.selector.count()-1
        self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)

    def select_recipe(self, index):
        self.search_results.hide()
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

    def _load_settings_for_authored(self, authored, recipe_id):
        from kim_recipe_params import initial_remembered_values
        raw_rem = {}
        if recipe_id and not recipe_id.startswith('dev-draft-'):
            try:
                raw_rem = load_remembered_values(recipe_id)
            except (OSError, RecipeError):
                raw_rem = {}
        valid_rem = initial_remembered_values(authored, raw_rem, validated=True)
        session_vals = self._session_param_values.get(recipe_id) or {}
        if session_vals:
            all_remember = {
                **authored,
                'parameters': [
                    {**p, 'remember': True}
                    for p in authored.get('parameters', ())
                ],
            }
            valid_session = initial_remembered_values(
                all_remember, session_vals, validated=True
            )
            if valid_session:
                self._session_param_values[recipe_id] = dict(valid_session)
            else:
                self._session_param_values.pop(recipe_id, None)
            initial = {**valid_rem, **valid_session}
        else:
            initial = valid_rem
        self.settings_page.set_recipe(
            authored, entered_values=initial or None
        )
        self.settings_page.set_has_remembered(bool(raw_rem))

    def _clear_remembered_for_current_recipe(self):
        if self.operation_title or self.authored_recipe is None or not self.selected_id:
            return
        if not self.selected_id.startswith('dev-draft-'):
            try:
                clear_remembered_values(self.selected_id)
            except (OSError, RecipeError):
                pass
        self._session_param_values.pop(self.selected_id, None)
        self.settings_page.form.reset_to_defaults()
        self.settings_page.set_has_remembered(False)

    def apply_recipe(self, recipe):
        self.invalidate_preflight()
        self._approved_run_remember = None
        self.results = []
        self._execution_completed = False
        if hasattr(self, 'open_output_button'):
            self.open_output_button.hide()
        self.recipe = copy.deepcopy(recipe)
        self.selected_id = recipe['id'] if recipe else None
        self.authored_recipe = None
        self.selection_hint.setVisible(recipe is None)
        self.preview_scroll.setVisible(
            recipe is not None or not self.operation_title
        )
        self.destination_choice.setEnabled(recipe is not None)
        self.operations_button.setVisible(recipe is not None and not self.operation_title)
        self.operations_panel.setVisible(
            recipe is not None and not self.operation_title
            and self.operations_button.isChecked()
        )
        if recipe is None:
            self.runner_phase = 'empty'
            self.execution_recipe, self.binding_error = None, None
            if hasattr(self, 'settings_page'):
                self.settings_page.set_has_remembered(False)
        elif not self.operation_title:
            from kim_recipe_params import is_parameterized, validate_authored
            if is_parameterized(recipe):
                self.authored_recipe = validate_authored(recipe)
                self.runner_phase = 'settings'
                self.execution_recipe, self.binding_error = None, None
                self._load_settings_for_authored(self.authored_recipe, self.selected_id)
            else:
                self.runner_phase = 'review'
                self.execution_recipe, self.binding_error = confirmation_snapshot(recipe)
                if hasattr(self, 'settings_page'):
                    self.settings_page.set_has_remembered(False)
        else:
            self.runner_phase = 'review'
            self.execution_recipe, self.binding_error = confirmation_snapshot(recipe)
        self.base_execution_recipe = copy.deepcopy(self.execution_recipe)
        self.refresh_selector()
        if self.selected_id and self.selector.findData(self.selected_id) < 0 and self.search.text():
            self.search.clear()
        self.heading.setText('Recipe: ' + selection_title(recipe, self.library.folders) if recipe else 'Choose a recipe…')

        description = (
            recipe.get('description', '').strip()
            if recipe and not self.operation_title else ''
        )
        self.set_recipe_description(description)
        self.recipe_description_group.setVisible(bool(description))

        self.fill_operations()
        if self.runner_phase == 'review':
            effective_dest = (self.base_execution_recipe or recipe)['destination']
            ask = bool(effective_dest.get('ask'))
            self.choose_destination.setVisible(ask)
            self.destination_label.setText(
                ('Output directory: ' + (self.chosen or 'choose before running')) if ask
                else ('Destination: ' + self.destination_description())
            )
            self.apply_destination_override()
        else:
            self.choose_destination.hide()
            self.destination_label.setText('Choose a recipe.' if recipe is None else '')
        self.update_edit_button()
        self.update_operation_summary()
        self._scroll_review_to_top = self.runner_phase == 'review'
        self._sync_settings_example_source()
        self.update_recipe_review_presentation()
        self.update_summary()
        self.start_preflight()
        if not self.operation_title and self.runner_phase == 'settings':
            QTimer.singleShot(0, self._focus_initial_settings)

    def settings_changed(self):
        if self.operation_title or self.authored_recipe is None:
            return
        if self.selected_id:
            self._session_param_values[self.selected_id] = self.settings_page.entered_values()
        self.execution_recipe = None
        self.base_execution_recipe = None
        self.binding_error = None
        self.runner_phase = 'settings'
        self.invalidate_preflight()
        self.update_recipe_review_presentation()
        self.update_summary()

    def enter_review_from_settings(self):
        if (
            self.operation_title
            or self.runner_phase != 'settings'
            or self.authored_recipe is None
            or self.worker is not None
            or self.add_worker is not None
            or self._addition_queue
            or self.editor_dialog is not None
            or not self.files
        ):
            return
        if self.settings_page.has_errors():
            self.update_summary()
            return
        if self.selected_id:
            self._session_param_values[self.selected_id] = self.settings_page.entered_values()
        snapshot, error = confirmation_snapshot(
            self.recipe,
            self.settings_page.active_values(),
        )
        if error or snapshot is None:
            self.execution_recipe = None
            self.base_execution_recipe = None
            self.binding_error = error
            self.settings_page.set_diagnostic(
                error or 'Cannot resolve recipe settings.'
            )
            self.update_summary()
            return
        self.settings_page.set_diagnostic('')
        ev = self.settings_page.form.evaluation()
        self._approved_run_remember = (
            self.selected_id,
            {p['id'] for p in ev['active']},
            copy.deepcopy(ev['values']),
        )
        self.base_execution_recipe = copy.deepcopy(snapshot)
        self.execution_recipe = copy.deepcopy(snapshot)
        self.binding_error = None
        self.runner_phase = 'review'
        self._scroll_review_to_top = True
        self.apply_destination_override()
        self.fill_operations()
        self.update_operation_summary()
        self.update_recipe_review_presentation()
        self.start_preflight()

    def open_settings_page(self):
        if (
            self.operation_title
            or self.authored_recipe is None
            or self.worker is not None
            or self.editor_dialog is not None
        ):
            return
        self.runner_phase = 'settings'
        self.execution_recipe = None
        self.base_execution_recipe = None
        self.binding_error = None
        self.invalidate_preflight()
        self.settings_page.set_diagnostic('')
        self._sync_settings_example_source()
        self.update_recipe_review_presentation()
        self.update_summary()
        focused = self.focusWidget()
        if focused is None or not focused.isVisible():
            self.settings_page.focus_first_required() or self.settings_page.focus_first_control()

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
            dialog = make_editor_dialog(
                self,
                from_run=True,
                files=list(self.files),
                recipe=self.recipe if repair or edit else None,
                repair=repair,
            )

            selected = self.inputs.currentItem()

            if selected is not None:
                index = self.inputs.indexOfTopLevelItem(selected)

                if 0 <= index < len(self.files):
                    sample = dialog.widget.example_selector.findData(
                        self.files[index]
                    )

                    if sample >= 0:
                        dialog.widget.example_selector.setCurrentIndex(
                            sample
                        )
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
        if self.editor_dialog is None:
            return
        dialog,self.editor_dialog=self.editor_dialog,None
        saved_id=dialog.widget.saved_recipe_id
        run_request = (
            getattr(dialog, 'run_request', None)
            if result == QDialog.Accepted else None
        )
        previous,previous_definition=self._editor_previous
        self.create_button.setEnabled(True)
        for control in (self.selector, self.search, self.destination_choice, self.choose_destination): control.setEnabled(True)
        error=None
        try:
            self.library=load_library()
            if run_request is not None:
                requested_recipe, requested_files, baseline = run_request

                self.saved_definition = verify_editor_handoff(
                    requested_recipe, baseline
                )
                recipe = copy.deepcopy(requested_recipe)
            else:
                recipe = lookup_recipe(saved_id) if saved_id else previous
                self.saved_definition = (
                    copy.deepcopy(recipe)
                    if saved_id else previous_definition
                )
        except (OSError,RecipeError) as exc:
            recipe=None; self.saved_definition=None; error=str(exc)
        dialog.deleteLater()
        self.update_edit_button()
        if self._close_after_editor:
            self._close_after_editor=False; self.reject(); return
        if error is None and run_request is not None:
            self.invalidate_preflight()

            if list(self.files) != list(requested_files):
                self.replace_files(
                    requested_files,
                    preflight=False
                )

            self.apply_recipe(recipe)
            self.selector.setFocus()
            return

        if error is None and recipe == previous:
            # No change to the active recipe: preserve its reviewed plan
            # and any inspection still running.
            self.refresh_selector()
            self.heading.setText(
                'Recipe: ' + selection_title(recipe, self.library.folders)
                if recipe else 'Choose a recipe…'
            )
            self.update_summary()
            if (
                self.runner_phase == 'review'
                and self.validated_snapshot is None
                and self.preflight_worker is None
            ):
                self.start_preflight()
        else:
            # New or changed recipe: existing validation cannot be reused.
            self.apply_recipe(recipe)
        if error: self.diagnostics.setPlainText(error)
        (self.fix_recipe_button if self.fix_recipe_button.isVisible() else self.selector).setFocus()

    def invalidate_preflight(self):
        self.generation += 1
        self._restart = False
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
        if not self.operation_title:
            self.technical_details_button.setChecked(False)
            self.sync_diagnostics()
        self.fix_recipe_button.hide()
        status_text = self._initial_queue_status()
        for index in range(len(self.files)):
            self.inputs.topLevelItem(index).setText(1, status_text)
            self.inputs.topLevelItem(index).setToolTip(1, '')
        if self.preflight_worker is not None:
            self.preflight_worker.requestInterruption()

    def start_preflight(self):
        if self.worker is not None: return
        self.invalidate_preflight()
        if self.recipe is None:
            self.summary.setText('Waiting for recipe selection' if self.operation_title else '')
            return
        if self.runner_phase != 'review' or self.execution_recipe is None:
            self.update_summary()
            return
        if self.preflight_worker is not None:
            self._restart = True
            return
        self._restart = False
        if self.editor_dialog is not None or self.add_worker is not None or self._addition_queue: return
        self.summary.setText(file_count(len(self.files)) + ' selected; inspecting…')
        if not self.files:
            self.summary.setText(
                '0 files selected; use Add images or drop images here.'
                if self.operation_title else 'No images selected.'
            ); return
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
            self._restart = False
            if self.runner_phase == 'review' and self.execution_recipe is not None:
                self.start_preflight()
                return
        if (
            self.runner_phase == 'review'
            and self.execution_recipe is not None
            and worker.generation == self.generation
            and not worker.cancelled
        ):
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
            self.summary.setText('Waiting for recipe selection' if self.operation_title else '')
            self.run_button.setEnabled(False)
            if hasattr(self, 'review_button'):
                self.review_button.setEnabled(False)
            return
        if not self.operation_title and self.runner_phase == 'settings':
            self.blocking_summary.clear()
            self.blocking_summary.hide()
            self.fix_recipe_button.hide()
            self.run_button.setEnabled(False)
            can_review = (
                bool(self.files)
                and not self.settings_page.has_errors()
                and self.worker is None
                and not self._closing
                and self.add_worker is None
                and not self._addition_queue
                and self.editor_dialog is None
                and not self._pending_picker
            )
            self.review_button.setEnabled(can_review)
            if not self.files:
                self.summary.setText('Add images to review changes.')
            elif self.settings_page.has_errors():
                self.summary.setText('Complete the required recipe settings to review changes.')
            else:
                self.summary.setText(
                    file_count(len(self.files)) + ' selected; ready to review changes.'
                )
            return
        if hasattr(self, 'review_button'):
            self.review_button.setEnabled(False)
        self.update_blocking_summary()
        ready, problems = self.ready_count, self.problem_count
        pending = len(self.files) - len(self.rows)
        if self.operation_title:
            self.summary.setText(
                file_count(len(self.files))
                + f' selected; {ready} ready; {problems} '
                + ('problem' if problems == 1 else 'problems')
                + (f'; {pending} pending' if pending else '')
            )
        else:
            parts = [f'{ready} ready']

            if problems:
                parts.append(f'{problems} blocked')

            if pending:
                parts.append(f'{pending} pending')

            self.summary.setText('; '.join(parts))
        self.fix_recipe_button.setVisible(not self.operation_title and self.repair_count > 0 and self.editor_dialog is None and not self._pending_picker)
        self.run_button.setEnabled(
            self.recipe is not None
            and self.runner_phase == 'review'
            and self.execution_recipe is not None
            and self.reviewed_generation == self.generation
            and bool(getattr(self, 'approved_plan', None))
            and bool(self.files)
            and ready == len(self.files)
            and not pending
            and not problems
            and self.preflight_worker is None
            and self.worker is None
            and not self._closing
            and self.add_worker is None
            and not self._addition_queue
            and self.editor_dialog is None
            and not self._pending_picker
        )

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
            lines.append(caption + other[0].problems[0])
        if duplicates or occupied:
            lines.append("Change the recipe's filename pattern or destination, or select different images, then review again.")
        if self.approval_error:
            lines.append('Review could not be approved. See technical details, then review again.')
        self.blocking_summary.setText('\n'.join(lines))
        self.blocking_summary.setToolTip('\n'.join(dict.fromkeys(row.output for row in blocked if row.output)))
        self.blocking_summary.setVisible(bool(lines))

    def show_selected(self, *args):
        if not self.operation_title and self.runner_phase == 'settings':
            self._sync_settings_example_source()
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
                else [
                    (key, value)
                    for key, value in property_fields(
                        self.execution_recipe, row
                    )
                    if key not in (
                        'Output filename',
                        'Output folder',
                        'Output directory',
                    )
                ]
            ) if row else []
        )
        if row is not None and self._scroll_review_to_top:
            self._scroll_review_to_top = False
            self.properties.scrollToTop()
        self._update_open_output_button()

    def _selected_output_directory(self):
        results = getattr(self, 'results', None) or []
        if not results:
            return None
        item = self.inputs.currentItem()
        index = self.inputs.indexOfTopLevelItem(item) if item else -1
        if 0 <= index < len(results):
            res = results[index]
            if res.get('ok') and res.get('output'):
                return Path(res['output']).parent
        for res in results:
            if res.get('ok') and res.get('output'):
                return Path(res['output']).parent
        return None

    def _update_open_output_button(self):
        if self.operation_title or not hasattr(self, 'open_output_button'):
            return
        out_dir = self._selected_output_directory()
        self.open_output_button.setVisible(out_dir is not None)
        if out_dir is not None:
            self.open_output_button.setToolTip(f'Open output directory: {out_dir}')

    def open_selected_output_directory(self):
        out_dir = self._selected_output_directory()
        if out_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))
            vbar = self.properties.verticalScrollBar()
            if vbar is not None:
                vbar.setValue(vbar.minimum())

    def apply_destination_override(self):
        if self.recipe is None or self.base_execution_recipe is None:
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
        self.choose_destination.setVisible(
            self.destination_mode == 'directory'
            or (
                self.destination_mode == 'default'
                and bool(self.base_execution_recipe['destination'].get('ask'))
            )
        )

        self.normalize_destination_caption()

    def change_destination_mode(self, *_):
        if self.runner_phase != 'review':
            return
        previous_mode = self.destination_mode
        if previous_mode == 'default': self.default_chosen = self.chosen
        self.destination_mode = self.destination_choice.currentData()
        if self.destination_mode == 'default': self.chosen = self.default_chosen
        self.apply_destination_override()
        self.start_preflight()
        if self.destination_mode == 'directory' and not self.override_directory:
            self.select_destination()

    def select_destination(self):
        if self.runner_phase != 'review':
            return
        directory = QFileDialog.getExistingDirectory(self, 'Choose output directory')
        if directory:
            self.chosen = directory
            if self.destination_mode == 'directory': self.override_directory = directory
            self.apply_destination_override()
            self.start_preflight()

    def start_execution(self):
        if (
            self.runner_phase != 'review'
            or self.execution_recipe is None
            or not self.run_button.isEnabled()
            or self.worker is not None
        ):
            return
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
        elif hasattr(self, 'settings_back_button'):
            self.settings_back_button.setEnabled(False)
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
        self._execution_completed = False
        self.results = []
        self._execution_started_at = time.monotonic()
        if hasattr(self, 'open_output_button'):
            self.open_output_button.hide()
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

    def _update_progress_dialog(self):
        if self.progress is None or self.job_status is None:
            return
        ok, failed, cancelled, skipped, _remaining = self.job_status.counts()
        stage = 'Cancelling current operation…' if self.job_status.cancelling else self.job_status.stage
        source = self.job_status.source
        name = Path(source).name if source else ''
        if self.job_status.index > 0 and name:
            headline = f'Image {self.job_status.index} of {self.job_status.total}: {name}'
        else:
            headline = f'{self.job_status.action}…'
        self.progress.setLabelText(f'{headline}\n{stage}')
        self.progress.label.setToolTip(source)
        parts = [f'Completed: {ok} of {self.job_status.total}']
        if failed:
            parts.append(f'{failed} failed')
        if cancelled:
            parts.append(f'{cancelled} cancelled')
        if skipped:
            parts.append(f'{skipped} skipped')
        self.progress.setStatusText(', '.join(parts))

    @Slot(str, int)
    def execution_started(self, source, index):
        self.job_status.start(source,index)
        self._update_progress_dialog(); self.progress.setValue(index - 1)

    @Slot(dict, int)
    def execution_item(self, result, index):
        self.job_status.finish(result)
        self._update_progress_dialog(); self.progress.setValue(index)

    def execution_stage(self, message):
        if self.worker is not None and self.sender() == self.worker:
            self.job_status.stage = message; self._update_progress_dialog()

    def cancel_execution(self):
        if self.worker is not None:
            self.worker.requestInterruption(); self.job_status.cancelling=True
            self._update_progress_dialog()

    @Slot()
    def execution_finished(self):
        worker = self.worker; self.results = worker.results; self.worker = None
        self.execution_succeeded = (bool(self.files) and not worker.cancelled and not worker.error
                                    and len(worker.results) == len(self.files)
                                    and all(result['ok'] for result in worker.results))
        if (
            self.execution_succeeded
            and not self.operation_title
            and self.authored_recipe is not None
            and self._approved_run_remember is not None
        ):
            rem_rid, active_ids, resolved_vals = self._approved_run_remember
            if rem_rid and rem_rid == self.selected_id and not rem_rid.startswith('dev-draft-'):
                remember_ids = {
                    p['id'] for p in self.authored_recipe.get('parameters', ())
                    if p.get('remember', False)
                }
                if remember_ids:
                    try:
                        updated = {
                            pid: val
                            for pid, val in load_remembered_values(rem_rid).items()
                            if pid in remember_ids
                        }
                        for pid in remember_ids:
                            if pid in active_ids and pid in resolved_vals:
                                updated[pid] = resolved_vals[pid]
                        save_remembered_values(rem_rid, updated)
                        if hasattr(self, 'settings_page'):
                            self.settings_page.set_has_remembered(bool(updated))
                    except (OSError, RecipeError):
                        pass
        self.progress.complete(); self.progress.deleteLater()
        skipped=[]
        for index,result in enumerate(worker.results):
            self.inputs.topLevelItem(index).setText(1,'Succeeded' if result['ok'] else 'Cancelled' if result.get('cancelled') else 'Failed')
        if worker.cancelled or worker.error:
            for index in range(len(worker.results),len(self.files)):
                result={'source':str(self.files[index]),'ok':False,'skipped':True,'error':'Not scheduled after cancellation' if worker.cancelled else 'Not scheduled after job error'}
                skipped.append(result); self.job_status.finish(result)
                self.inputs.topLevelItem(index).setText(1,'Skipped')
        elapsed = max(0.0, time.monotonic() - getattr(self, '_execution_started_at', time.monotonic()))
        ok, failed, cancelled, skipped_count, _remaining = self.job_status.counts()
        metadata_warnings = [
            result.get('warning', '')
            for result in worker.results
            if result.get('ok')
            and result.get('warning')
        ]
        if not self.operation_title:
            self._execution_completed = True
            self._update_window_title()
            if self.execution_succeeded:
                noun = 'image' if ok == 1 else 'images'
                self.summary.setText(f'{ok} {noun} successfully processed.')
            else:
                parts = []
                if ok:
                    parts.append(f'{ok} succeeded')
                if failed:
                    parts.append(f'{failed} failed')
                if cancelled:
                    parts.append(f'{cancelled} cancelled')
                if skipped_count:
                    parts.append(f'{skipped_count} skipped')
                summary_text = (', '.join(parts) + '.') if parts else 'No images were processed.'
                if failed:
                    summary_text += ' Failed outputs were not published.'
                elif worker.error:
                    summary_text += ' Execution error.'
                self.summary.setText(summary_text)
            detail_lines = [f'Elapsed time: {elapsed:.2f} s']
            for r in worker.results + skipped:
                if r.get('ok'):
                    detail_lines.append(f"Created: {r['output']} (from {r['source']})")
                    if r.get('warning'):
                        detail_lines.append(f"Warning: {r['warning']}")
                else:
                    detail_lines.append(f"{r['source']}: {r.get('error', 'Failed')}")
            if worker.error:
                detail_lines.append(f'Error: {worker.error}')
            self.diagnostics.setPlainText('\n'.join(detail_lines))
            self.diagnostics.setMaximumHeight(160)
            has_issues = bool(worker.error or not self.execution_succeeded or metadata_warnings)
            self.technical_details_button.setChecked(has_issues)
            self.sync_diagnostics()
            self._update_open_output_button()
        else:
            self.summary.setText(self.job_status.label().split('\n')[-1] + ('; cancelled before remaining files' if worker.cancelled else '') + ('; execution error' if worker.error else ''))
            report = [r['output'] if r['ok'] else r['source'] + ': ' + r['error'] for r in worker.results+skipped]
            if worker.error: report.append(worker.error)
            self.diagnostics.setPlainText('\n'.join(report))
            self.diagnostics.setMaximumHeight(200)
            if worker.error or not self.execution_succeeded:
                self.diagnostics.show()
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
                failed_n = len(failures)
                self.summary.setText(
                    f"{succeeded} succeeded, "
                    f"{failed_n} failed. "
                    "Failed outputs were not published."
                )

        if self.operation_title and metadata_warnings:
            self.summary.setText(metadata_warnings[0])

            created = [
                result['output']
                for result in worker.results
                if result.get('ok') and result.get('output')
            ]

            self.diagnostics.setPlainText(
                'Created: ' + '\n'.join(created)
            )
            self.diagnostics.setMaximumHeight(72)
            self.diagnostics.show()

            if hasattr(self, 'problem_explanation'):
                self.problem_explanation.hide()
            if hasattr(self, 'technical_details_button'):
                self.technical_details_button.hide()

        self.cancel_button.setText('Close')

        if not self._closing:
            self.inputs.setEnabled(True)
            for control in (self.selector,self.search,self.create_button,self.choose_destination,self.destination_choice): control.setEnabled(True)
            if hasattr(self, 'settings_back_button'):
                self.settings_back_button.setEnabled(True)
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
