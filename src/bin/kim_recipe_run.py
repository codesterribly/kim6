"""Read-only confirmation, responsive batch inspection, and shared recipe property view."""
import copy
import os
import re
import sys
import time
from pathlib import Path
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtCore import QThread, Signal, Slot, Qt, QTimer, QStandardPaths
from PySide6.QtGui import QPalette, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QSplitter, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QPlainTextEdit, QFileDialog, QProgressDialog, QMessageBox, QProgressBar)
from kim_job import JobStatus, grouped_warnings, WarningGroups
from kim_recipe_core import (RecipeError, PreviewRow, builtins, load_library, lookup_recipe,
                             recipe_title, RecipeLibrary, library_groups, handler, preview, execute, validate)


class JobProgressDialog(QDialog):
    canceled = Signal()

    def __init__(self, text, cancel_text, minimum, maximum, parent=None):
        super().__init__(parent); self.finished_job=False; self.resize(640,200)
        self.setWindowTitle('KIM6 — Job Progress')
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
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); self.details.hide(); layout.addWidget(self.details)
        self.copy=QPushButton('Copy Details'); self.copy.hide(); layout.addWidget(self.copy)
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
        self.summary.setText('\n'.join(self.groups.captions()))
        self.details_dirty = True
        if self.expand.isChecked(): self.refresh_details()

    def refresh_details(self, *args):
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
                    item.setForeground(self.palette().brush(QPalette.Disabled, QPalette.Text))
                self.setItem(row, column, item)
        self.resizeRowsToContents()


def property_fields(recipe, row):
    fields = [('Source filename', Path(row.source).name), ('Source folder', str(Path(row.source).parent))]
    if row.output and not row.problems:
        fields += [('Output filename', Path(row.output).name), ('Output folder', str(Path(row.output).parent))]
    fields += handler(recipe['media']).preview_fields(row)
    if row.problems:
        fields.append(('Output plan', 'Unavailable — resolve validation problems'))
    fields += [('Validation problem', problem) for problem in row.problems]
    # Category notices belong to the batch disclosure, not every property row.
    if not row.problems:
        fields += [('Publication', row.certainty)]
    return fields + [('Originals', 'Always unchanged')]


class RecipeWorker(QThread):
    """The existing serial execution loop, shared by every confirmation launch."""
    item_started = Signal(str, int)
    item_finished = Signal(dict, int)
    stage_changed = Signal(str)

    def __init__(self, recipe, files, chosen=None, parent=None):
        super().__init__(parent)
        self.recipe, self.files, self.chosen = copy.deepcopy(recipe), list(files), chosen
        self.results, self.error, self.cancelled = [], None, False

    def run(self):
        from kim_image_ops import logo_inspections
        with logo_inspections(): self.execute_files()

    def execute_files(self):
        from kim_psd_source import inspection_context
        try:
            from kim_image_ops import has_image_operations, preflight_batch
            if has_image_operations(self.recipe):
                with inspection_context(self.stage_changed.emit, self.isInterruptionRequested):
                    preflight_batch(self.recipe, self.files, self.chosen)
            for index, source in enumerate(self.files, 1):
                if self.isInterruptionRequested():
                    self.cancelled = True; break
                self.item_started.emit(str(source), index)
                # Execution retains the established stop-between-files contract.
                with inspection_context(self.stage_changed.emit,self.isInterruptionRequested):
                    result = execute(self.recipe, [source], self.chosen, start_index=index)[0]
                self.results.append(result); self.item_finished.emit(result, index)
                if result.get('cancelled') or self.isInterruptionRequested():
                    self.cancelled = True; break
        except Exception as exc:
            if self.isInterruptionRequested(): self.cancelled = True
            else: self.error = str(exc)


class InputFiltersWorker(QThread):
    def __init__(self,parent=None):
        super().__init__(parent); self.filters=None

    def run(self):
        from kim_recipe_image import input_name_filters
        from kim_psd_source import inspection_context
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
        from kim_psd_source import source_session, inspection_context, header as psd_header
        identities = {os.path.normcase(os.path.abspath(p)) for p in self.current}
        for index,raw in enumerate(self.paths):
            if self.isInterruptionRequested(): break
            self.item_started.emit(index)
            path = os.path.abspath(os.path.normpath(raw)); key = os.path.normcase(path)
            try:
                if key in identities or any(os.path.exists(path) and os.path.exists(p) and os.path.samefile(path,p) for p in self.current + self.accepted):
                    raise RecipeError('Already in the list')
                if not Path(path).is_file() or Path(path).is_symlink():
                    raise RecipeError('Choose an existing local image file, not a directory or symlink')
                # Admission checks the PSD header/resource bounds. Recipe
                # preflight owns composite/ICC validation; decoding here too
                # doubled large-document work before the user could press Run.
                if psd_header(path) is None:
                    with inspection_context(cancelled=self.isInterruptionRequested), source_session(), checked_input_headers(self.checked_inputs): inspect(Path(path))
                self.accepted.append(path); identities.add(key)
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

    def __init__(self, recipe, files, chosen=None, binding_error=None, parent=None, checked_inputs=None):
        super().__init__(parent)
        self.recipe, self.files, self.chosen = copy.deepcopy(recipe), list(files), chosen
        self.binding_error = binding_error
        self.checked_inputs = copy.deepcopy(checked_inputs or {})
        self.cancelled = False

    def run(self):
        from kim_image_ops import logo_inspections
        with logo_inspections(): self.inspect_files()

    def inspect_files(self):
        outputs = set()
        for index, source in enumerate(self.files, 1):
            if self.isInterruptionRequested():
                self.cancelled = True; break
            self.file_started.emit(str(source),index,len(self.files))
            try:
                from kim_psd_source import inspection_context
                from kim_recipe_image import checked_input_headers
                with inspection_context(self.stage_changed.emit,self.isInterruptionRequested), checked_input_headers(self.checked_inputs):
                    row = preview(self.recipe, [source], self.chosen, start_index=index)[0]
                if self.binding_error:
                    row.problems.append(self.binding_error)
                if self.recipe['destination'].get('ask') and not self.chosen:
                    row.problems.append('Choose an output directory before running.')
                if row.output and not row.problems and not (self.recipe['destination'].get('ask') and not self.chosen):
                    proposed = Path(row.properties.get('_proposed_output', row.output))
                    number = 0
                    candidate = proposed
                    while str(candidate) in outputs or candidate.exists() or candidate.is_symlink():
                        number += 1
                        candidate = proposed.with_name(f'{proposed.stem}_{number}{proposed.suffix}')
                    if candidate != proposed:
                        row.certainty = 'That filename already exists. KIM6 plans to save this file as ' + candidate.name + '. The name is checked again when saving.'
                    row.output = str(candidate)
                    outputs.add(row.output)
            except Exception as exc:
                row = PreviewRow(str(source), problems=[str(exc)])
            if self.isInterruptionRequested():
                self.cancelled=True
                row=PreviewRow(str(source),properties={'_cancelled':True})
            self.inspected.emit(row, index - 1)
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
        self.files = list(files)
        self.execution_recipe, self.binding_error = confirmation_snapshot(recipe) if recipe else (None, None)
        self.add_worker = None; self._addition_queue = []; self._addition_items = []; self.input_revision = 0
        self.checked_inputs = {}
        self.filters_worker = None; self._input_filters = None; self._pending_picker = False
        self.generation = 0
        self.reviewed_generation = None
        self.validated_snapshot = None
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
        self.setWindowTitle(operation_title or 'Run a Recipe'); self.resize(1120, 820)
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
        self.create_button = QPushButton('Create New Recipe…')
        self.create_button.clicked.connect(self.create_recipe)
        selection.addWidget(self.create_button); layout.addLayout(selection)
        self.selection_hint=QLabel('Choose a recipe to check these photos and preview the results.')
        self.selection_hint.setWordWrap(True); self.selection_hint.setVisible(recipe is None); layout.addWidget(self.selection_hint)
        self.search.textChanged.connect(self.refresh_selector)
        self.selector.currentIndexChanged.connect(self.select_recipe)
        self.refresh_selector()
        if operation_title:
            for control in (label, self.search, self.selector, self.create_button): control.hide()
        self.heading = QLabel(operation_title or ('Recipe: ' + selection_title(recipe, folders) if recipe else 'Choose a recipe…'))
        self.heading.setTextFormat(Qt.PlainText); self.heading.setWordWrap(True)
        if operation_title: self.heading.setText(operation_title + ' — review all output plans')
        layout.addWidget(self.heading)
        self.count = QLabel('Inputs: ' + file_count(len(self.files))); layout.addWidget(self.count)
        split = QSplitter(Qt.Horizontal); layout.addWidget(split, 1)
        left = QWidget(); left_layout = QVBoxLayout(left); split.addWidget(left)
        inputs = QGroupBox('Selected files — select one for detailed preview'); inp_layout = QVBoxLayout(inputs)
        self.inputs = InputFilesView(); self.inputs.setHeaderLabels(['Filename', 'Preflight'])
        self.inputs.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.inputs.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.inputs.setRootIsDecorated(False)
        for source in self.files:
            item = QTreeWidgetItem([Path(source).name, 'Queued' if self.recipe else 'Waiting for recipe']); item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.inputs.currentItemChanged.connect(self.show_selected)
        inp_layout.addWidget(self.inputs)
        actions = QHBoxLayout()
        self.add_photos = QPushButton('Add Photos…'); self.add_photos.clicked.connect(self.pick_files)
        self.remove_selected = QPushButton('Remove Selected'); self.remove_selected.clicked.connect(self.remove_files)
        self.clear_list = QPushButton('Clear List'); self.clear_list.clicked.connect(self.clear_files)
        for button in (self.add_photos, self.remove_selected, self.clear_list): actions.addWidget(button)
        inp_layout.addLayout(actions); left_layout.addWidget(inputs, 2)
        self.inputs.files_dropped.connect(self.add_files)
        self.inputs.itemSelectionChanged.connect(self.update_file_actions)
        operations = QGroupBox('Recipe operations — configured order'); op_layout = QVBoxLayout(operations)
        self.operations = QTreeWidget(); self.operations.setHeaderHidden(True); self.operations.setWordWrap(True)
        self.fill_operations(); op_layout.addWidget(self.operations); left_layout.addWidget(operations, 3)
        right = QGroupBox('Output preview'); right_layout = QVBoxLayout(right)
        self.properties = PropertyView(); right_layout.addWidget(self.properties)
        split.addWidget(right); split.setSizes([460, 640])
        dest = QHBoxLayout()
        self.destination_label = QLabel(); self.destination_label.setTextFormat(Qt.PlainText)
        self.destination_label.setWordWrap(True)
        self.choose_destination = QPushButton(QIcon.fromTheme('folder-open'), 'Choose Output Directory…')
        self.choose_destination.clicked.connect(self.select_destination)
        self.choose_destination.setVisible(bool(recipe and recipe['destination'].get('ask')))
        self.destination_label.setText('Destination: ' + self.destination_description() if recipe else 'Choose a recipe to inspect its destination.')
        dest.addWidget(self.destination_label, 1); dest.addWidget(self.choose_destination); layout.addLayout(dest)
        self.summary = QLabel(); self.summary.setTextFormat(Qt.PlainText); layout.addWidget(self.summary)
        self.preflight_busy=QProgressBar(); self.preflight_busy.setRange(0,0)
        self.preflight_busy.setAccessibleName('Inspecting selected photos'); self.preflight_busy.hide()
        layout.addWidget(self.preflight_busy)
        self.diagnostics = QPlainTextEdit(); self.diagnostics.setReadOnly(True); self.diagnostics.setMaximumHeight(100)
        layout.addWidget(self.diagnostics)
        self.fix_recipe_button=QPushButton('Fix Recipe…'); self.fix_recipe_button.setAccessibleName('Fix recipe: choose a Photoshop output format')
        self.fix_recipe_button.clicked.connect(self.fix_recipe); self.fix_recipe_button.hide(); layout.addWidget(self.fix_recipe_button)
        self.warning_view = WarningView(); layout.addWidget(self.warning_view)
        safety = QLabel('Originals are never overwritten. KIM6 saves new files and adds a number when names collide, so nothing gets clobbered. Finished results stay put if you cancel or something fails.')
        safety.setWordWrap(True); layout.addWidget(safety)
        buttons = QHBoxLayout(); buttons.addStretch(1)
        self.run_button = QPushButton(('Apply to ' if operation_title else 'Run Recipe on ') + file_count(len(self.files)).title()); self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_execution)
        self.cancel_button = QPushButton('Cancel'); self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.run_button); buttons.addWidget(self.cancel_button); layout.addLayout(buttons)
        if self.files: self.inputs.setCurrentItem(self.inputs.topLevelItem(0))
        self.update_file_actions()
        self.start_preflight()

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
        paths = choose_images(self, start, title='Add Photos',
                              extensions=extensions or RECIPE_IMAGE_EXTENSIONS,
                              accept_label='Add Photos')
        self.add_files(paths)
        self.update_summary()

    def input_filters_finished(self):
        worker,self.filters_worker=self.filters_worker,None
        self._input_filters=worker.filters; worker.deleteLater()
        self.add_photos.setText('Add Photos…'); self.update_file_actions()
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
            item=QTreeWidgetItem([Path(path).name,'Checking photo…']); item.setToolTip(0,str(path))
            self.inputs.addTopLevelItem(item); self._addition_items.append(item)
        self.count.setText('Inputs: '+file_count(self.inputs.topLevelItemCount()))
        self.summary.setText('Checking added photos…')
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
            item = QTreeWidgetItem([Path(source).name, 'Queued' if self.recipe else 'Waiting for recipe'])
            item.setToolTip(0, str(source)); self.inputs.addTopLevelItem(item)
        self.count.setText('Inputs: ' + file_count(len(self.files)))
        self.run_button.setText(('Apply to ' if self.operation_title else 'Run Recipe on ') + file_count(len(self.files)).title())
        self.update_file_actions()
        if preflight: self.start_preflight()
        if self.files: self.inputs.setCurrentItem(self.inputs.topLevelItem(0))

    def remove_files(self):
        if self.add_worker is not None: return
        selected = {self.inputs.indexOfTopLevelItem(item) for item in self.inputs.selectedItems()}
        if selected: self.replace_files([path for i, path in enumerate(self.files) if i not in selected])

    def clear_files(self):
        if self.worker is not None or (not self.files and self.add_worker is None): return
        if QMessageBox.question(self, 'Clear List', 'Remove all pending files from this job?',
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
            item = QTreeWidgetItem([f'{index}. {label} — ' + ('Enabled' if enabled else 'Disabled')])
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
        self.execution_recipe, self.binding_error = confirmation_snapshot(recipe) if recipe else (None, None)
        self.refresh_selector()
        if self.selected_id and self.selector.findData(self.selected_id) < 0 and self.search.text():
            self.search.clear()
        self.heading.setText('Recipe: ' + selection_title(recipe, self.library.folders) if recipe else 'Choose a recipe…')
        self.fill_operations()
        ask = bool(recipe and recipe['destination'].get('ask'))
        self.choose_destination.setVisible(ask)
        self.destination_label.setText(('Output directory: ' + (self.chosen or 'choose before running')) if ask else
                                       ('Destination: ' + self.destination_description() if recipe else 'Choose a recipe.'))
        self.start_preflight()

    def create_recipe(self):
        self.open_editor()

    def fix_recipe(self):
        if self.recipe is None or not any(row.properties.get('_repair')=='add_convert_format' for row in self.rows.values()): return
        self.open_editor(repair=True)

    def open_editor(self, repair=False):
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
        self.invalidate_preflight()
        try:
            dialog=make_editor_dialog(self,from_run=True,recipe=self.recipe if repair else None,repair=repair)
        except (OSError,RecipeError) as exc:
            self.saved_definition=None; self.apply_recipe(None)
            self.diagnostics.setPlainText('Cannot open Recipe Editor: '+str(exc)); return
        self.editor_dialog=dialog; self.create_button.setEnabled(False)
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
        error=None
        try:
            self.library=load_library()
            recipe=lookup_recipe(saved_id) if saved_id else previous
            self.saved_definition=copy.deepcopy(recipe) if saved_id else previous_definition
        except (OSError,RecipeError) as exc:
            recipe=None; self.saved_definition=None; error=str(exc)
        dialog.deleteLater()
        if self._close_after_editor:
            self._close_after_editor=False; self.reject(); return
        self.apply_recipe(recipe)
        if error: self.diagnostics.setPlainText(error)
        (self.fix_recipe_button if self.fix_recipe_button.isVisible() else self.selector).setFocus()

    def invalidate_preflight(self):
        self.generation += 1
        self.reviewed_generation = None
        self.validated_snapshot = None
        self.run_button.setEnabled(False)
        self.preflight_active=None; self.preflight_clock.stop(); self.preflight_busy.hide(); self.cancel_button.setText('Cancel')
        self.ready_count = self.problem_count = self.repair_count = 0
        self.problem_messages.clear(); self._last_problem_index = -1; self._selected_presentation = None
        self.rows.clear(); self.properties.set_fields([]); self.diagnostics.clear(); self.warning_view.set_rows([])
        self.fix_recipe_button.hide()
        for index in range(len(self.files)): self.inputs.topLevelItem(index).setText(1, 'Queued' if self.recipe else 'Waiting for recipe')
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
            self.summary.setText('0 files selected; use Add Photos or drop images here.'); return
        worker = PreflightWorker(self.execution_recipe, self.files, self.chosen, self.binding_error, self,checked_inputs=self.checked_inputs)
        worker.generation = self.generation
        self.preflight_worker = worker
        worker.file_started.connect(self.preflight_started)
        worker.inspected.connect(self.inspected)
        worker.stage_changed.connect(self.preflight_stage)
        worker.finished.connect(self.preflight_finished)
        self.preflight_busy.show(); self.preflight_clock.start(); self.cancel_button.setText('Cancel All')
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
        self.inputs.topLevelItem(index-1).setText(1,'Inspecting — '+message)
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
        self.inputs.topLevelItem(index).setText(1, 'Cancelled' if row.properties.get('_cancelled') else 'Problem' if row.problems else 'Ready')
        if row.problems or (previous is not None and previous.problems):
            ordered = previous is None and index > self._last_problem_index
            self._last_problem_index = max(index, self._last_problem_index)
            self.problem_messages[index] = [str(self.files[index]) + ': ' + issue for issue in row.problems]
            if ordered: self.diagnostics.appendPlainText('\n'.join(self.problem_messages[index]))
            else: self.diagnostics.setPlainText('\n'.join(message for i in sorted(self.problem_messages) for message in self.problem_messages[i]))
        if previous is not None and previous.warnings:
            self.warning_view.set_rows(self.rows.values())
        else: self.warning_view.add_row(row)
        self.preflight_active=None
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
        self.update_summary()

    def update_summary(self):
        if self.recipe is None:
            self.summary.setText('Waiting for recipe selection'); self.run_button.setEnabled(False); return
        ready, problems = self.ready_count, self.problem_count
        pending = len(self.files) - len(self.rows)
        self.summary.setText(file_count(len(self.files)) + f' selected; {ready} ready; {problems} ' + ('problem' if problems == 1 else 'problems') + (f'; {pending} pending' if pending else ''))
        self.fix_recipe_button.setVisible(not self.operation_title and self.repair_count > 0 and self.editor_dialog is None and not self._pending_picker)
        self.run_button.setEnabled(self.recipe is not None and self.reviewed_generation == self.generation and bool(self.files) and ready == len(self.files) and not pending and not problems and self.preflight_worker is None and self.worker is None and not self._closing and self.add_worker is None and not self._addition_queue and self.editor_dialog is None and not self._pending_picker)

    def show_selected(self, *args):
        item = self.inputs.currentItem()
        index = self.inputs.indexOfTopLevelItem(item) if item else -1
        row = self.rows.get(index)
        previous = self._selected_presentation
        if previous is not None and previous[0] == (self.generation, index) and previous[1] is row and previous[2] is self.execution_recipe: return
        self._selected_presentation = ((self.generation, index), row, self.execution_recipe)
        self.properties.set_fields(property_fields(self.execution_recipe, row) if row else [])

    def select_destination(self):
        directory = QFileDialog.getExistingDirectory(self, 'Choose output directory')
        if directory:
            self.chosen = directory; self.destination_label.setText('Output directory: ' + directory); self.start_preflight()

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
        self.selector.setEnabled(False); self.search.setEnabled(False); self.create_button.setEnabled(False)
        self.add_photos.setEnabled(False); self.remove_selected.setEnabled(False); self.clear_list.setEnabled(False); self.inputs.setEnabled(False)
        self.job_status = JobStatus(self.operation_title or 'Run Recipe',len(self.files))
        self.progress = JobProgressDialog(('Applying ' + self.operation_title + '…') if self.operation_title else 'Running recipe…', 'Cancel All', 0, len(self.files), self)
        self.progress.setWindowModality(Qt.WindowModal); self.progress.setMinimumDuration(0)
        self.progress.setAutoClose(False); self.progress.setAutoReset(False)
        recipe, files, chosen = self.validated_snapshot
        self.execution_succeeded = False
        self.worker = RecipeWorker(recipe, files, chosen, self)
        self.progress.canceled.connect(self.cancel_execution)
        self.worker.item_started.connect(self.execution_started)
        self.worker.item_finished.connect(self.execution_item)
        self.worker.stage_changed.connect(self.execution_stage)
        self.worker.finished.connect(self.execution_finished)
        self.cancel_button.setText('Cancel All')
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
        self.diagnostics.setPlainText('\n'.join(report)); self.diagnostics.setMaximumHeight(200)
        self.cancel_button.setText('Close')
        if not self._closing:
            for control in (self.selector,self.search,self.create_button,self.choose_destination): control.setEnabled(True)
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
            event.accept()


def launch_run(recipe_id, files):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        recipe = lookup_recipe(recipe_id) if recipe_id else None
        dialog = RunRecipeDialog(recipe, files, load_library().folders)
        dialog.exec()
        return 0
    except (OSError, RecipeError, UnicodeError) as exc:
        QMessageBox.critical(None, 'Run Recipe', str(exc))
        return 1
