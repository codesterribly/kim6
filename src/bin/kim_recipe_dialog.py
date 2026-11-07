#!/usr/bin/env python3
"""Reusable recipe manager/builder widget and independent Dolphin launcher."""
import copy
import sys
import uuid
from pathlib import Path
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtCore import QTimer, Qt, QThread, Signal, Slot, QDate, QTime
from PySide6.QtGui import QIcon, QPalette, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QComboBox, QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QInputDialog,
    QProgressDialog, QHeaderView, QGroupBox, QSplitter, QSizePolicy, QToolButton, QTreeWidget, QTreeWidgetItem, QDialogButtonBox,
    QDateEdit, QTimeEdit, QDoubleSpinBox)
from kim_recipe_core import (folder_label, ROOT_FOLDER, RecipeError, builtins,
                             save_users, load_users, load_library, save_library, RecipeLibrary, library_groups, recipe_title, validate, preview, execute, handler, format_output_pattern, display_output_pattern)


from kim_recipe_run import RunRecipeDialog, RecipeWorker, PropertyView, property_fields, WarningView


from kim_ui import CaptureDateInput, CaptureDateOptions, CaptureAdjustment, RotationInput, HelpButton, with_help


class ExamplePreviewWorker(QThread):
    stage_changed = Signal(str)

    def __init__(self, recipe, sample, index, generation, parent):
        super().__init__(parent)
        self.recipe, self.sample, self.index = copy.deepcopy(recipe), sample, index
        self.generation, self.row = generation, None

    def run(self):
        from kim_process import inspection_context
        from kim_recipe_core import PreviewRow
        try:
            with inspection_context(self.stage_changed.emit,self.isInterruptionRequested):
                self.row = preview(self.recipe,[self.sample],start_index=self.index)[0]
        except Exception as exc:
            self.row = PreviewRow(str(self.sample),problems=[str(exc)])


class OperationPicker(QDialog):
    """One view of the handler's definitions; IDs and parameter data stay shared."""
    def __init__(self, definitions, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Operation'); self.resize(570, 480)
        self.definitions = definitions; self.operation_id = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search operations…')
        self.search.setAccessibleName('Search operations by name or keyword'); layout.addWidget(self.search)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Operations grouped by category'); layout.addWidget(self.tree, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.add = buttons.button(QDialogButtonBox.Ok); self.add.setText('Add'); self.add.setEnabled(False)
        buttons.accepted.connect(self.choose); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.choose())
        self.refresh(); self.search.setFocus()

    def refresh(self):
        from kim_recipe_image import CATEGORIES
        query = self.search.text().casefold().split(); self.tree.clear()
        first = None
        for category in CATEGORIES:
            operations = [(op,d) for op,d in self.definitions.items() if d.get('category', CATEGORIES[3]) == category and
                          all(word in (category+' '+d['label']+' '+d.get('keywords','')+' '+d.get('description','')).casefold() for word in query)]
            if not operations: continue
            group = QTreeWidgetItem([category]); group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for op, definition in sorted(operations, key=lambda item:item[1]['label'].casefold()):
                item = QTreeWidgetItem([definition['label']]); item.setData(0,Qt.UserRole,op)
                item.setToolTip(0,definition.get('description',definition['label'])); group.addChild(item)
                if first is None: first = item
            group.setExpanded(True)
        self.tree.setCurrentItem(first); self.selection_changed()

    def selection_changed(self,*_):
        item = self.tree.currentItem()
        self.operation_id = item.data(0,Qt.UserRole) if item else None
        self.add.setEnabled(bool(self.operation_id))

    def choose(self):
        if self.operation_id: self.accept()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Down and self.search.hasFocus():
            self.tree.setFocus(); event.accept(); return
        super().keyPressEvent(event)


class RecipeWidget(QWidget):
    """Embeddable manager; files are optional and preview is always text-only."""
    def __init__(self, files=(), parent=None, from_run=False):
        super().__init__(parent)
        self.files = list(files)
        self.from_run = from_run
        self.draft_ids = set()
        self.saved_new_recipe_id = None
        self.saved_recipe_id = None
        self.example_files = None
        self.run_dialog = None
        self.repair_inputs = None
        self.active_index = -1
        self.baseline = None
        self.shipped = builtins()
        library = load_library()
        self.users, self.folders = library.recipes, library.folders
        self.recipe = None
        self.preview_worker = None; self.preview_generation = 0; self.preview_pending = False; self.preview_closing = False
        self.loading = False
        root = QVBoxLayout(self)
        self.editor = QWidget(self)
        root.addWidget(self.editor)
        layout = QVBoxLayout(self.editor)
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        left = QWidget(); right = QGroupBox('Preview')
        left.setMinimumWidth(0); right.setMinimumWidth(0)
        self.splitter.addWidget(left); self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3); self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([660, 440])
        controls = QVBoxLayout(left)
        self.selector = QComboBox()
        controls.addWidget(self.selector)
        bar = QHBoxLayout()
        self.management_buttons = {}
        for label, icon, callback in [('New', 'document-new', self.new),
            ('Duplicate to Edit', 'edit-copy', self.duplicate), ('Rename', 'edit-rename', self.rename),
            ('Delete', 'edit-delete', self.remove), ('Save', 'document-save', self.save)]:
            button = QPushButton(QIcon.fromTheme(icon), label)
            button.clicked.connect(callback); bar.addWidget(button)
            self.management_buttons[label] = button
        controls.addLayout(bar)
        name_form = QFormLayout()
        self.name = QLineEdit(); self.name.textEdited.connect(self.changed)
        name_row = QWidget(); name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0); name_layout.addWidget(self.name, 1)
        self.reset_builtin = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Defaults')
        self.reset_builtin.clicked.connect(self.reset_builtin_defaults)
        name_layout.addWidget(self.reset_builtin)
        name_form.addRow('Recipe name', name_row)
        self.library_folder = QComboBox()
        self.library_folder.currentIndexChanged.connect(self.folder_changed)
        name_form.addRow('Recipe folder', self.library_folder)
        controls.addLayout(name_form)
        folder_bar = QHBoxLayout()
        for text, callback in [('Create Folder…', self.create_folder), ('Rename Folder…', self.rename_folder), ('Delete Folder…', self.delete_folder)]:
            button = QPushButton(text); button.clicked.connect(callback); folder_bar.addWidget(button)
        controls.addLayout(folder_bar)
        controls.addWidget(QLabel('Recipe Steps'))
        self.steps = QListWidget()
        self.steps.setAccessibleName('Ordered recipe steps; check to enable')
        self.steps.currentRowChanged.connect(self.edit_step)
        self.steps.itemChanged.connect(self.toggle_step)
        bar = QHBoxLayout()
        self.operation = QPushButton(QIcon.fromTheme('list-add'), 'Add Operation…')
        self.operation.clicked.connect(self.add_step); bar.addWidget(self.operation, 1)
        self.step_buttons = []
        button = QPushButton(QIcon.fromTheme('list-remove'), 'Remove')
        button.clicked.connect(self.remove_step); bar.addWidget(button); self.step_buttons.append(button)
        self.operation_bar = bar
        controls.addLayout(bar)
        self.steps_row = QHBoxLayout()
        self.steps_row.addWidget(self.steps, 1)
        self.move_controls = QWidget()
        moves = QVBoxLayout(self.move_controls); moves.setContentsMargins(0, 0, 0, 0)
        self.move_up = QToolButton(); self.move_down = QToolButton()
        for button, icon_name, arrow, delta, shortcut in (
            (self.move_up, 'go-up', Qt.UpArrow, -1, 'Alt+Up'),
            (self.move_down, 'go-down', Qt.DownArrow, 1, 'Alt+Down')):
            icon = QIcon.fromTheme(icon_name)
            if icon.isNull():
                button.setArrowType(arrow)
            else:
                button.setIcon(icon)
            button.setToolTip(('Move step up' if delta < 0 else 'Move step down') + ' (' + shortcut + ')')
            button.setAccessibleName('Move step up' if delta < 0 else 'Move step down')
            button.setShortcut(QKeySequence(shortcut))
            button.clicked.connect(lambda checked=False, d=delta: self.move(d))
            moves.addWidget(button)
        moves.addStretch(1)
        self.steps_row.addWidget(self.move_controls)
        controls.addLayout(self.steps_row, 2)
        self.parameters = QGroupBox('Step Parameters')
        self.form = QFormLayout(self.parameters)
        controls.addWidget(self.parameters)
        self.destination_group = QGroupBox('Destination')
        self.destinations = QFormLayout(self.destination_group)
        self.mode = QComboBox()
        for label, mode in [('Beside each original', 'beside'), ('Subfolder beside each original', 'subfolder'), ('One directory', 'directory')]:
            self.mode.addItem(label, mode)
        self.folder = QLineEdit(); self.path = QLineEdit()
        self.ask = QCheckBox('Ask for directory on every run')
        self.directory_row = QWidget()
        directory_layout = QHBoxLayout(self.directory_row); directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self.path)
        browse = QPushButton(QIcon.fromTheme('folder-open'), 'Choose…')
        browse.clicked.connect(self.browse); directory_layout.addWidget(browse)
        self.destinations.addRow('Location', with_help(self.mode, 'output'))
        self.destinations.addRow('Subfolder', self.folder)
        self.destinations.addRow('', self.ask)
        self.destinations.addRow('Directory', self.directory_row)
        controls.addWidget(self.destination_group)
        self.mode.currentIndexChanged.connect(self.changed)
        for widget in (self.folder, self.path):
            widget.textEdited.connect(self.changed)
        self.ask.toggled.connect(self.changed)
        preview_layout = QVBoxLayout(right)
        self.example_selector = QComboBox()
        self.example_selector.setMinimumWidth(0)
        self.example_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.example_selector.currentIndexChanged.connect(self.update_preview)
        self.example_label = QLabel('Example image (preview only)')
        self.example_label.setBuddy(self.example_selector)
        preview_layout.addWidget(self.example_label)
        preview_layout.addWidget(with_help(self.example_selector, 'psd'))
        self.choose_example_button = QPushButton(QIcon.fromTheme('document-open'), 'Choose Example Image…')
        self.choose_example_button.clicked.connect(self.choose_examples)
        preview_layout.addWidget(self.choose_example_button)
        self.reset_examples = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Selected Images')
        self.reset_examples.clicked.connect(lambda: self.set_examples(None))
        self.reset_examples.setVisible(False)
        preview_layout.addWidget(self.reset_examples)
        self.status = QLabel(); self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_layout.addWidget(self.status)
        self.cancel_preview = QPushButton('Cancel preview'); self.cancel_preview.setVisible(False)
        self.cancel_preview.clicked.connect(self.stop_preview); preview_layout.addWidget(self.cancel_preview)
        self.table = PropertyView()
        preview_layout.addWidget(self.table, 1)
        self.warning_view=WarningView(); self.warning_view.hide(); preview_layout.addWidget(self.warning_view)
        safety = QLabel('Originals are never changed. Outputs are always new files.')
        safety.setWordWrap(True); safety.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_layout.addWidget(safety)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(300)
        self.timer.timeout.connect(self.update_preview)
        self.selector.currentIndexChanged.connect(lambda i: self.select_id(self.selector.itemData(i)))
        self.selector.activated.connect(lambda i: self.reselect_builtin(self.active_index))
        self.refresh_examples()
        self.refresh()

    def refresh(self, selected=0):
        self.selector.blockSignals(True); self.selector.clear()
        recipes = self.shipped + self.users
        for folder_id, name, grouped in library_groups(RecipeLibrary(self.users, self.folders), self.shipped):
            for r in grouped:
                self.selector.addItem(name + ' / ' + r['name'], r['id'])
        self.selector.setCurrentIndex(self.selector.findData(recipes[selected]['id'])); self.selector.blockSignals(False)
        self.select(selected, force=True)

    def select_id(self, recipe_id):
        index = next((i for i, r in enumerate(self.shipped + self.users) if r['id'] == recipe_id), -1)
        if index >= 0: self.select(index)

    def select(self, index, force=False):
        recipes = self.shipped + self.users
        if not 0 <= index < len(recipes):
            return
        if not force and index != self.active_index and not self.protect_unsaved():
            self.selector.blockSignals(True)
            self.selector.setCurrentIndex(self.selector.findData(self.recipe['id']))
            self.selector.blockSignals(False)
            return
        self.loading = True
        self.active_index = index
        self.recipe = copy.deepcopy(recipes[index])
        self.baseline = copy.deepcopy(self.recipe)
        self.media_handler = handler(self.recipe['media'])
        self.definitions = self.media_handler.operation_definitions()
        self.immutable = index < len(self.shipped)
        self.name.setText(self.recipe['name']); self.name.setReadOnly(self.immutable)
        self.library_folder.blockSignals(True); self.library_folder.clear(); self.library_folder.addItem('Unfiled', None)
        self.library_folder.addItem('Root', ROOT_FOLDER)
        for folder in sorted(self.folders, key=lambda f: f['name'].casefold()):
            self.library_folder.addItem(folder_label(folder), folder['id'])
        self.library_folder.setCurrentIndex(self.library_folder.findData(self.recipe.get('folder')))
        self.library_folder.setEnabled(not self.immutable); self.library_folder.blockSignals(False)
        dest = self.recipe['destination']
        self.mode.setCurrentIndex(self.mode.findData(dest['mode'])); self.folder.setText(dest.get('folder', 'Recipes'))
        self.path.setText(dest.get('path', '')); self.ask.setChecked(dest.get('ask', False))
        self.destination_group.setEnabled(not self.immutable)
        self.operation.setEnabled(not self.immutable)
        for button in self.step_buttons:
            button.setEnabled(not self.immutable)
        for label in ('Rename', 'Delete', 'Save'):
            self.management_buttons[label].setEnabled(not self.immutable)
        self.update_destination_controls()
        self.reload_steps()
        self.loading = False
        self.update_modified()
        self.update_preview()

    def reselect_builtin(self, index):
        if self.immutable and index == self.active_index and self.is_dirty():
            self.select(index, force=True)

    def comparable(self, recipe):
        state = copy.deepcopy(recipe)
        for step in state['steps']:
            step.setdefault('enabled', True)
            for key, spec in self.definitions[step['op']]['parameters'].items():
                step.setdefault(key, copy.deepcopy(spec['default']))
        return state

    def is_dirty(self):
        return self.recipe is not None and (self.recipe['id'] in self.draft_ids or self.comparable(self.recipe) != self.comparable(self.baseline))

    def update_modified(self):
        dirty = self.is_dirty()
        label = recipe_title(self.recipe, self.folders)
        if self.immutable:
            label += ' [modified for this run]' if dirty else ' [built-in]'
        elif dirty:
            label += ' *'
        self.selector.setItemText(self.selector.findData(self.recipe['id']), label)
        self.management_buttons['Save'].setEnabled(not self.immutable and dirty)
        self.reset_builtin.setVisible(self.immutable)
        self.reset_builtin.setEnabled(self.immutable and dirty)
        self.update_move_buttons()

    def update_move_buttons(self):
        row = self.steps.currentRow()
        self.move_up.setEnabled(not self.immutable and row > 0)
        self.move_down.setEnabled(not self.immutable and 0 <= row < self.steps.count() - 1)

    def reset_builtin_defaults(self):
        if self.immutable:
            self.select(self.active_index, force=True)

    def style_step_item(self, item, enabled):
        # Unchecked steps remain selectable, and must be readable.
        item.setForeground(self.palette().brush(QPalette.Active, QPalette.Text))
        font = item.font()
        font.setItalic(not enabled)
        item.setFont(font)
        item.setToolTip('Enabled in recipe' if enabled else 'Disabled: check this step to include it in the recipe')

    def reload_steps(self, row=0):
        self.steps.blockSignals(True)
        self.steps.clear()
        for step in self.recipe['steps']:
            item = QListWidgetItem(self.media_handler.step_label(step))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if step.get('enabled', True) else Qt.Unchecked)
            self.style_step_item(item, step.get('enabled', True))
            self.steps.addItem(item)
        self.steps.blockSignals(False)
        self.steps.setCurrentRow(min(row, len(self.recipe['steps']) - 1))
        if not self.recipe['steps']:
            self.edit_step(-1)

    def toggle_step(self, item):
        row = self.steps.row(item)
        enabled = item.checkState() == Qt.Checked
        self.recipe['steps'][row]['enabled'] = enabled
        self.steps.blockSignals(True)
        self.style_step_item(item, enabled)
        self.steps.blockSignals(False)
        self.update_modified()
        self.timer.start()

    def edit_step(self, row):
        self.update_move_buttons()
        self.parameter_widgets = {}
        self.filename_example = None
        self.parameter_resets = {}
        self.parameter_modes = {}
        self.step_defaults_button = None
        while self.form.rowCount():
            self.form.removeRow(0)
        if self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        definition = self.definitions[step['op']]
        self.parameters.setTitle(definition.get('label', 'Step Parameters'))
        if definition.get('description'):
            hint = QLabel(definition['description']); hint.setWordWrap(True)
            self.form.addRow(hint)
        definitions = definition['parameters']
        if definition.get('editor') == 'image_ops':
            from kim_image_ops import step_details
            for title, value in step_details(step):
                label = QLabel(value); label.setTextFormat(Qt.PlainText); label.setWordWrap(True)
                self.form.addRow(title, label)
            configure = QPushButton('Configure with image preview…')
            configure.clicked.connect(lambda checked=False, r=row: self.configure_image_operation(r))
            self.form.addRow(configure)
            reset = QPushButton('Reset step defaults'); reset.clicked.connect(self.reset_step_defaults)
            self.form.addRow(reset)
            return
        if step['op'] == 'image.resize':
            sizes = (300,600,800,1024,1280,1400,1600,1920,2048,2560,3440,3840)
            presets = QComboBox(); presets.addItem('Custom bounds',None)
            for size in sizes: presets.addItem(f'{size} × {size}',size)
            presets.setCurrentIndex(presets.findData(step['max_width']) if step['max_width'] == step['max_height'] and step['max_width'] in sizes else 0)
            presets.currentIndexChanged.connect(lambda i,r=row,w=presets:self.resize_preset(r,w.itemData(i)))
            self.form.addRow('Common sizes',presets)
        for key, spec in definitions.items():
            if step['op'] == 'metadata.set_capture' and key in ('timezone','fields'): continue
            try:
                value = self.media_handler.parameter_value(step, key)
            except (OSError, RecipeError) as exc:
                value = spec['default'] if spec['type'] in ('integer','number') else ''
                self.status.setText(str(exc))
            if step['op']=='file.rename_output' and key=='pattern': value=display_output_pattern(value)
            if key == 'degrees' and step['op'] == 'image.rotate':
                widget = RotationInput(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif spec['type'] == 'capture_datetime':
                widget = CaptureDateInput(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif key == 'seconds' and step['op'] == 'metadata.shift_capture':
                widget = CaptureAdjustment(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif 'choices' in spec:
                widget = QComboBox()
                for choice in spec['choices']:
                    labels = {'specific':'Enter a specific date/time','embedded':'Use embedded image capture date if available' if key == 'mode' else 'Keep embedded timezone (or unknown)',
                              'file_mtime':'Use source file modification time', 'unknown':'Unknown camera timezone (no offset)',
                              '':'Choose timezone…','UTC':'UTC (+00:00)','custom':'Enter ±HH:MM offset',
                              'capture':'Image capture date only','all':'Image capture, creation and modification dates'} if step['op'] == 'metadata.set_capture' or key == 'fields' else {}
                    widget.addItem(labels.get(choice,str(choice).replace('_',' ').capitalize()), choice)
                if key == 'timezone':
                    widget.setEditable(True)
                    if widget.findData(value) < 0: widget.addItem(value,value)
                widget.setCurrentIndex(widget.findData(value))
                if key == 'timezone':
                    widget.currentTextChanged.connect(lambda v,k=key,r=row,w=widget:self.parameter(r,k,w.itemData(w.findText(v)) if w.findText(v) >= 0 else v))
                else: widget.currentIndexChanged.connect(lambda i, k=key, r=row, w=widget: self.parameter(r, k, w.itemData(i)))
            elif spec['type'] == 'boolean':
                widget = QCheckBox(); widget.setChecked(value)
                widget.toggled.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            elif spec['type'] == 'integer':
                widget = QSpinBox(); widget.setRange(spec['minimum'], spec['maximum'])
                widget.setValue(value)
                widget.valueChanged.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            elif spec['type'] == 'number':
                widget = QDoubleSpinBox(); widget.setRange(spec['minimum'],spec['maximum']); widget.setDecimals(3); widget.setValue(value)
                widget.valueChanged.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            else:
                widget = QLineEdit(value)
                widget.textEdited.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            self.parameter_widgets[key] = widget
            if spec.get('settings_key'):
                field_row = QWidget(); field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0); field_layout.addWidget(widget, 1)
                reset = QPushButton('Reset from Settings')
                reset.clicked.connect(lambda checked=False, r=row, k=key: self.reset_to_settings(r, k))
                field_layout.addWidget(reset); field_layout.addWidget(HelpButton('settings')); self.parameter_resets[key] = reset
                self.form.addRow(spec.get('label', key), field_row)
                mode = QLabel('')
                self.parameter_modes[key] = mode
                self.form.addRow('', mode)
            else:
                if spec['type'] == 'capture_datetime': self.form.addRow(widget)
                else: self.form.addRow(spec.get('label', key.replace('_', ' ')), widget)
            if step['op']=='file.rename_output' and key=='pattern':
                self.filename_example=QLabel(); self.filename_example.setTextFormat(Qt.PlainText); self.filename_example.setWordWrap(True)
                self.form.addRow('',self.filename_example)
                widget.textChanged.connect(self.update_filename_example)
                self.update_filename_example()
        if step['op'] == 'metadata.set_capture':
            # Blank was the old 'choose timezone' UI state. Unknown is now the
            # explicit, safe default for manual clocks; no local zone is used.
            if not step['timezone']: step['timezone'] = 'unknown'
            self.capture_options = CaptureDateOptions(step['timezone'],step['fields'],embedded=True)
            self.parameter_widgets['timezone'] = self.capture_options.zone
            self.parameter_widgets['fields'] = self.capture_options.fields
            self.capture_options.zone_changed.connect(lambda v,r=row:self.parameter(r,'timezone',v))
            self.capture_options.fields_changed.connect(lambda v,r=row:self.parameter(r,'fields',v))
            self.form.addRow(self.capture_options)
        topics = {'metadata.set_capture':(), 'metadata.shift_capture':('capture','dates'),
                  'image.convert':('quality','color'), 'image.compress':('quality',), 'image.color':('color',),
                  'image.resize':('resize',), 'image.resize_exact':('resize',), 'image.resize_geometry':('resize',),
                  'metadata.strip_all':('strip',), 'file.rename_output':('output',), 'file.name_transform':('output',)}
        for topic in topics.get(step['op'],()):
            from kim_ui import HELP
            self.form.addRow(HELP[topic][0], HelpButton(topic))
        if definitions:
            self.step_defaults_button = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset step defaults')
            self.step_defaults_button.clicked.connect(self.reset_step_defaults)
            self.form.addRow(self.step_defaults_button)
        self.update_parameter_modes(row)
        self.update_conversion_controls(row)

    def configure_image_operation(self, row):
        from kim_image_ops_dialog import ImageOperationDialog
        # The same modal controls configure standalone operations. The Recipe
        # destination and all preceding/succeeding steps remain authoritative.
        files = self.files if self.example_files is None else self.example_files
        dialog = ImageOperationDialog(self.recipe['steps'][row], files, self,
                                      recipe=self.recipe, row=row)
        sample = self.example_selector.currentData()
        if sample and dialog.images.findData(sample) >= 0:
            dialog.images.setCurrentIndex(dialog.images.findData(sample))
        if dialog.exec() != QDialog.Accepted: return
        replacement = copy.deepcopy(dialog.step)
        if 'enabled' in self.recipe['steps'][row]:
            replacement['enabled'] = self.recipe['steps'][row]['enabled']
        self.recipe['steps'][row] = replacement
        self.reload_steps(row); self.update_modified(); self.update_preview()

    def update_filename_example(self,*_):
        if self.filename_example is None: return
        from kim_recipe_image import FORMATS
        sample=self.example_selector.currentData()
        source=Path(sample) if sample else Path('vacation.jpg')
        suffix=source.suffix.lower().lstrip('.')
        fmt={'jpg':'jpeg','jpe':'jpeg','jfif':'jpeg','tif':'tiff','heif':'heic'}.get(suffix,suffix)
        for step in self.recipe['steps']:
            if step['op']=='image.convert' and step.get('enabled',True): fmt=step['format']
        if fmt not in FORMATS:
            self.filename_example.setText('Example output: choose Convert Format for this image.'); return
        try:
            value=self.parameter_widgets['pattern'].text()
            name=format_output_pattern(value,source.stem,'[image capture date]',1)
            self.filename_example.setText('Example output: '+name+'.'+FORMATS[fmt])
        except (KeyError,ValueError): self.filename_example.setText('Example output: enter a valid filename pattern.')

    def resize_preset(self,row,size):
        if size is None: return
        for key in ('max_width','max_height'):
            self.parameter_widgets[key].setValue(size)

    def update_conversion_controls(self, row):
        step = self.recipe['steps'][row]
        if row != self.steps.currentRow(): return
        if step['op'] == 'metadata.set_capture':
            self.form.setRowVisible(self.parameter_widgets['datetime'],step['mode'] == 'specific')
            embedded = self.capture_options.zone.findData('embedded')
            self.capture_options.zone.model().item(embedded).setEnabled(step['mode'] == 'embedded')
            if step['mode'] == 'file_mtime': self.capture_options.toggle.setChecked(True)
        if step['op'] == 'image.compress':
            for key in ('quality','png_level'):
                self.parameter_widgets[key].setEnabled(step['preset'] == 'custom')
        if step['op'] != 'image.convert' or row != self.steps.currentRow(): return
        fmt = step['format']
        for key, formats in {'jpeg_progressive':('jpeg',), 'jpeg_optimize':('jpeg',), 'jp2_mode':('jp2',), 'tiff_compression':('tiff',), 'depth':('png','jp2','tiff')}.items():
            if key in self.parameter_widgets: self.form.setRowVisible(self.parameter_widgets[key], fmt in formats)
        self.parameter_widgets['quality'].setEnabled(fmt in ('jpeg','webp','avif','heic','heif','jxl') or (fmt=='jp2' and step.get('jp2_mode','lossless')=='lossy'))
        self.parameter_resets['quality'].setVisible(fmt in ('jpeg','webp','avif'))

    def update_parameter_modes(self, row):
        if row < 0: return
        step = self.recipe['steps'][row]
        for key, label in self.parameter_modes.items():
            inherited = step.get(key) is None
            self.parameter_resets[key].setEnabled(not inherited)
            if inherited:
                try: value = self.media_handler.parameter_value(step,key)
                except (OSError,RecipeError) as exc:
                    value = self.definitions[step['op']]['parameters'][key]['default'] or ''
                    self.status.setText(str(exc))
                widget = self.parameter_widgets[key]
                widget.blockSignals(True)
                if isinstance(widget,QSpinBox): widget.setValue(value)
                else: widget.setText(value)
                widget.blockSignals(False)
                source = ''
                if step['op'] == 'image.convert':
                    from kim_recipe_image import quality_setting
                    source = ': ' + (quality_setting(step['format']) or 'quality not inherited for this format')
                label.setText('Inherited from KIM6 Settings' + source + (': not set' if not value else ''))
            else:
                label.setText('Custom override' if step[key] and key != 'quality' else '' if step[key] else 'Blank override: leave this field unchanged')
            label.setWordWrap(True)
            label.setVisible(bool(label.text()))


    def parameter(self, row, key, value):
        self.recipe['steps'][row][key] = value
        self.steps.blockSignals(True)
        self.steps.item(row).setText(self.media_handler.step_label(self.recipe['steps'][row]))
        self.steps.blockSignals(False)
        self.update_parameter_modes(row)
        self.update_conversion_controls(row)
        self.update_modified()
        self.timer.start()

    def reset_to_settings(self, row, key):
        if self.recipe['steps'][row]['op'] == 'image.convert' and key == 'quality':
            self.recipe['steps'][row][key] = None
        else: self.recipe['steps'][row].pop(key, None)
        self.edit_step(row)
        self.update_modified()
        self.update_preview()

    def reset_step_defaults(self):
        row = self.steps.currentRow()
        if row < 0:
            return
        step = self.recipe['steps'][row]
        defaults = self.definitions[step['op']]['parameters']
        replacement = {'op': step['op'], **{key: copy.deepcopy(spec['default']) for key, spec in defaults.items()}}
        if 'enabled' in step:
            replacement['enabled'] = step['enabled']
        self.recipe['steps'][row] = replacement
        self.reload_steps(row)
        self.update_modified()
        self.update_preview()

    def changed(self, *args):
        if not self.loading and self.recipe and not self.immutable:
            self.recipe['name'] = self.name.text()
            mode = self.mode.currentData()
            dest = {'mode': mode}
            if mode == 'subfolder': dest['folder'] = self.folder.text()
            if mode == 'directory':
                dest['ask'] = self.ask.isChecked()
                if self.path.text(): dest['path'] = self.path.text()
            self.recipe['destination'] = dest
            self.update_destination_controls()
            self.update_modified()
            self.timer.start()

    def update_destination_controls(self):
        mode = self.mode.currentData()
        self.destinations.setRowVisible(self.folder, mode == 'subfolder')
        self.destinations.setRowVisible(self.ask, mode == 'directory')
        self.destinations.setRowVisible(self.directory_row, mode == 'directory' and not self.ask.isChecked())

    def browse(self):
        if self.immutable: return
        directory = QFileDialog.getExistingDirectory(self, 'Recipe destination')
        if directory:
            self.path.setText(directory); self.changed()

    def writable(self):
        if self.immutable:
            self.status.setText('Duplicate to save a user recipe or change step order and destination. Built-in parameter edits and checkboxes apply only to this run.')
            return False
        return True

    def protect_unsaved(self):
        if self.recipe is None or self.immutable or not self.is_dirty():
            return True
        answer = QMessageBox.question(self, 'Unsaved recipe', 'Save changes to this recipe?',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    def append_recipe(self, recipe):
        # Drafts live only in this widget until Save succeeds.
        self.draft_ids.add(recipe['id'])
        self.users.append(recipe)
        self.refresh(len(self.shipped) + len(self.users) - 1)

    def store_users(self, users):
        warning = save_library(RecipeLibrary([r for r in users if r['id'] not in self.draft_ids], self.folders))
        if warning: self.error(warning)

    def folder_changed(self):
        if self.loading or self.immutable:
            return
        folder_id = self.library_folder.currentData()
        if folder_id is None:
            self.recipe.pop('folder', None)
        else:
            self.recipe['folder'] = folder_id
        self.update_modified()

    def change_folders(self, change):
        if not self.protect_unsaved(): return
        if not self.immutable and self.is_dirty():
            self.select(self.active_index, force=True)
        snapshot = copy.deepcopy(self.recipe) if self.immutable else None
        selected_id = self.recipe['id']
        library = RecipeLibrary(copy.deepcopy([r for r in self.users if r['id'] not in self.draft_ids]), copy.deepcopy(self.folders))
        try:
            change(library)
            warning = save_library(library)
            if warning: self.error(warning)
            self.users, self.folders = library.recipes, library.folders
            index = next((i for i, r in enumerate(self.shipped + self.users) if r['id'] == selected_id), 0)
            self.refresh(index)
            if snapshot is not None:
                self.recipe = snapshot; self.reload_steps(); self.update_modified(); self.update_preview()
        except (OSError, RecipeError) as exc:
            self.error(exc)

    def create_folder(self):
        name, ok = QInputDialog.getText(self, 'Create Recipe Folder', 'Folder name (one level)')
        if ok: self.change_folders(lambda library: library.create_folder(name))

    def choose_folder(self, title):
        if not self.folders:
            self.status.setText('There are no user recipe folders.'); return None
        folders = sorted(self.folders, key=lambda f: f['name'].casefold())
        name, ok = QInputDialog.getItem(self, title, 'Recipe folder', [f['name'] for f in folders], editable=False)
        return next((f for f in folders if f['name'] == name), None) if ok else None

    def rename_folder(self):
        folder = self.choose_folder('Rename Recipe Folder')
        if folder is None: return
        name, ok = QInputDialog.getText(self, 'Rename Recipe Folder', 'New name', text=folder['name'])
        if ok: self.change_folders(lambda library: library.rename_folder(folder['id'], name))

    def delete_folder(self):
        folder = self.choose_folder('Delete recipe folder')
        if folder is None: return
        message = QMessageBox(self); message.setWindowTitle('Delete recipe folder'); message.setTextFormat(Qt.PlainText)
        message.setText('Delete folder “' + folder['name'] + '”? Its recipes will move to Unfiled; no recipes or images are deleted.')
        message.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel); message.setDefaultButton(QMessageBox.Cancel)
        if message.exec() == QMessageBox.Yes:
            self.change_folders(lambda library: library.delete_folder(folder['id']))

    def new(self):
        if not self.protect_unsaved(): return
        self.append_recipe({'schema': 1, 'id': 'user-' + uuid.uuid4().hex, 'name': 'New Recipe',
            'media': 'image', 'steps': [{'op': 'file.rename_output', 'pattern': '{filename}_recipe'}],
            'destination': {'mode': 'beside'}})

    def duplicate(self):
        if not self.protect_unsaved(): return
        recipe = copy.deepcopy(self.recipe if self.immutable or not self.is_dirty() else self.baseline)
        recipe['id'] = 'user-' + uuid.uuid4().hex; recipe['name'] += ' copy'
        self.append_recipe(recipe)

    def rename(self):
        if not self.writable(): return
        name, ok = QInputDialog.getText(self, 'Rename recipe', 'Name', text=self.name.text())
        if ok: self.name.setText(name); self.changed()

    def remove(self):
        if not self.writable(): return
        index = self.active_index - len(self.shipped)
        answer = QMessageBox.question(self, 'Delete recipe',
            'Delete saved recipe “' + self.users[index]['name'] + '”?',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes or not self.protect_unsaved():
            return
        users = self.users[:]; del users[index]
        try:
            self.store_users(users); self.users = users; self.refresh()
        except (OSError, RecipeError) as exc: self.error(exc)

    def save(self):
        if not self.writable(): return False
        if not self.is_dirty():
            self.status.setText('No unsaved changes.')
            return True
        try:
            recipe = validate(self.recipe)
            index = self.active_index - len(self.shipped)
            users = self.users[:]; users[index] = recipe
            is_new = recipe['id'] in self.draft_ids
            self.draft_ids.discard(recipe['id'])
            try:
                self.store_users(users)
            except Exception:
                if is_new: self.draft_ids.add(recipe['id'])
                raise
            self.users = users
            if is_new: self.saved_new_recipe_id = recipe['id']
            self.saved_recipe_id = recipe['id']
            self.baseline = copy.deepcopy(recipe)
            self.update_modified()
            self.status.setText('Recipe saved.')
            return True
        except (OSError, RecipeError) as exc:
            self.error(exc)
            return False

    def add_step(self, op=None):
        if not self.writable(): return
        if not isinstance(op, str):
            dialog = OperationPicker(self.definitions, self)
            if dialog.exec() != QDialog.Accepted: return
            op = dialog.operation_id
        if op not in self.definitions: return
        self.recipe['steps'].append({'op': op, **{key: copy.deepcopy(spec['default'])
            for key, spec in self.definitions[op]['parameters'].items()}})
        self.reload_steps(len(self.recipe['steps']) - 1); self.update_modified(); self.timer.start()

    def remove_step(self):
        if not self.writable(): return
        row = self.steps.currentRow()
        if row >= 0:
            del self.recipe['steps'][row]; self.reload_steps(row); self.update_modified(); self.timer.start()

    def move(self, delta):
        if not self.writable(): return
        row = self.steps.currentRow(); target = row + delta
        if 0 <= target < len(self.recipe['steps']):
            steps = self.recipe['steps']; steps[row], steps[target] = steps[target], steps[row]
            self.reload_steps(target); self.update_modified(); self.timer.start()

    def refresh_examples(self):
        previous = self.example_selector.currentData()
        samples = self.files if self.example_files is None else self.example_files
        self.example_selector.blockSignals(True)
        self.example_selector.clear()
        for sample in samples:
            self.example_selector.addItem(Path(sample).name, sample)
        if previous in samples:
            self.example_selector.setCurrentIndex(samples.index(previous))
        self.example_selector.blockSignals(False)
        self.reset_examples.setVisible(self.example_files is not None)

    def set_examples(self, files):
        self.example_files = None if files is None else list(files)
        self.refresh_examples()
        self.update_preview()

    def choose_examples(self):
        files = choose_images(self, title='Choose Example Images',
                               extensions=RECIPE_IMAGE_EXTENSIONS, accept_label='Use Example Images')
        if files:
            self.set_examples(files)

    def show_preview_fields(self, fields):
        self.table.set_fields(fields)

    def refresh_inherited_parameters(self):
        row = self.steps.currentRow()
        if row < 0:
            return
        step = self.recipe['steps'][row]
        for key, spec in self.definitions[step['op']]['parameters'].items():
            if spec.get('settings_key') and step.get(key) is None:
                widget = self.parameter_widgets[key]
                widget.blockSignals(True)
                value = self.media_handler.parameter_value(step,key)
                if isinstance(widget,QSpinBox): widget.setValue(value)
                else: widget.setText(value)
                widget.blockSignals(False)
        self.update_parameter_modes(row)

    def update_preview(self, *args):
        self.update_filename_example()
        if self.recipe is None:
            return
        self.preview_generation += 1
        if self.preview_worker is not None:
            self.preview_pending = True
            self.preview_worker.requestInterruption()
            return
        sample = self.example_selector.currentData()
        self.warning_view.set_rows([])
        fields = [('Source image', str(sample) if sample else 'Choose an example image')]
        try:
            if not sample:
                validate(self.recipe)
                self.refresh_inherited_parameters()
                self.media_handler.validate_context(self.recipe['steps'])
                self.status.setText('Choose an example image to inspect this recipe.')
                self.show_preview_fields(fields + [('Originals', 'Always unchanged')])
                return
            index = self.files.index(sample) + 1 if sample in self.files else 1
            self.refresh_inherited_parameters()
            worker = ExamplePreviewWorker(self.recipe,sample,index,self.preview_generation,self)
            self.preview_worker = worker
            self.status.setText('Validating recipe…'); self.show_preview_fields(fields)
            self.cancel_preview.setVisible(True)
            worker.stage_changed.connect(self.preview_stage)
            worker.finished.connect(self.preview_finished)
            worker.start()
        except (OSError, RecipeError, UnicodeError) as exc:
            self.status.setText(str(exc))
            self.show_preview_fields(fields + [('Validation problem', str(exc)), ('Originals', 'Always unchanged')])

    def preview_stage(self, message):
        worker = self.sender()
        if worker.generation == self.preview_generation and worker.recipe == self.recipe:
            self.status.setText(message + '…')

    def preview_finished(self):
        worker = self.preview_worker; self.preview_worker = None
        self.cancel_preview.setVisible(False)
        current = (worker.generation == self.preview_generation and worker.recipe == self.recipe
                   and worker.sample == self.example_selector.currentData())
        if current and worker.row is not None:
            self.show_preview_fields(property_fields(worker.recipe,worker.row))
            self.warning_view.set_rows([worker.row])
            self.status.setText(worker.row.problems[0] if worker.row.problems else '')
        worker.deleteLater()
        if self.preview_closing:
            QTimer.singleShot(0,self.window().close)
        elif self.preview_pending:
            self.preview_pending = False; self.update_preview()

    def stop_preview(self):
        self.preview_generation += 1; self.preview_pending = False
        if self.preview_worker is not None: self.preview_worker.requestInterruption()
        self.status.setText('Preview cancelled. Change a step or example image to retry.')

    def error(self, exc):
        QMessageBox.warning(self, 'Recipes', str(exc))

    def load_photos_and_run(self):
        if self.from_run: return
        if not self.protect_unsaved(): return
        if not self.immutable and self.is_dirty():
            # Save clears dirty state; reaching here means Discard was selected.
            if self.recipe['id'] in self.draft_ids:
                draft_id = self.recipe['id']
                self.users = [r for r in self.users if r['id'] != draft_id]
                self.draft_ids.discard(draft_id)
                self.refresh()
            else:
                self.select(self.active_index, force=True)
        snapshot = copy.deepcopy(self.recipe)
        files = choose_images(self, title='Load Images for Recipe Execution',
                               extensions=RECIPE_IMAGE_EXTENSIONS, accept_label='Load Images')
        if not files: return
        try:
            self.run_dialog = RunRecipeDialog(snapshot, files, self.folders, self)
            self.run_dialog.exec()
            self.run_dialog = None
        except (OSError, RecipeError) as exc:
            self.error(exc)

    def offer_recipe_repair(self, files, chosen):
        self.repair_inputs=(list(files),chosen)
        if not hasattr(self,'repair_return'):
            self.repair_explanation=QLabel('Photoshop files need Convert Format. Add it and choose an output format. '
                'For a built-in recipe, choose Duplicate to Edit first.')
            self.repair_explanation.setWordWrap(True)
            self.repair_return=QPushButton('Return to recipe runner')
            self.repair_return.clicked.connect(self.resume_recipe_repair)
            self.layout().insertWidget(0,self.repair_return); self.layout().insertWidget(0,self.repair_explanation)
        self.repair_return.show(); self.repair_explanation.show()

    def resume_recipe_repair(self):
        if self.repair_inputs is None or not self.protect_unsaved(): return
        if not self.immutable and self.is_dirty():
            # Discard must restore the stored recipe, just as Load Photos does.
            if self.recipe['id'] in self.draft_ids:
                self.users=[r for r in self.users if r['id']!=self.recipe['id']]
                self.draft_ids.discard(self.recipe['id']); self.refresh()
            else: self.select(self.active_index,force=True)
        files,chosen=self.repair_inputs; self.repair_inputs=None
        self.repair_return.hide(); self.repair_explanation.hide()
        self.run_dialog=RunRecipeDialog(copy.deepcopy(self.recipe),files,self.folders,self,chosen=chosen)
        self.run_dialog.exec(); self.run_dialog=None

    def prepare_close(self):
        if self.run_dialog is not None and (self.run_dialog.worker is not None or self.run_dialog.preflight_worker is not None):
            self.run_dialog.reject(); return False
        if not self.preview_closing and not self.protect_unsaved(): return False
        if self.preview_worker is not None:
            self.stop_preview(); self.preview_closing = True
            return False
        return True


class RecipeDialog(QDialog):
    def accept(self):
        if self.widget.prepare_close():
            super().accept()

    def reject(self):
        if self.widget.prepare_close():
            super().reject()

    def closeEvent(self, event):
        if self.widget.prepare_close():
            event.accept()
        else:
            event.ignore()


def make_editor_dialog(parent=None, from_run=False, files=(), recipe=None, repair=False):
    dialog = RecipeDialog(parent); dialog.setWindowTitle('Recipe Editor'); dialog.resize(1150, 850)
    layout = QVBoxLayout(dialog)
    if repair:
        hint=QLabel('Photoshop files need Convert Format. Add it and choose an output format. '
                    'For a built-in recipe, choose Duplicate to Edit first. Original PSDs stay unchanged.')
        hint.setWordWrap(True); layout.addWidget(hint); dialog.repair_hint=hint
    widget = RecipeWidget(files, dialog, from_run=from_run); dialog.widget = widget; layout.addWidget(widget)
    if recipe is not None:
        recipes=widget.shipped+widget.users
        index=next((i for i,r in enumerate(recipes) if r['id']==recipe['id']),None)
        if index is None:
            widget.append_recipe(copy.deepcopy(recipe))
        elif index < len(widget.shipped):
            widget.select(index)
        else:
            # A Run opened from an editor can contain an unsaved snapshot.
            # Load it as dirty against the stored baseline; Save/Discard remains
            # the existing editor's responsibility, never this launch hook's.
            baseline=copy.deepcopy(recipes[index])
            widget.users[index-len(widget.shipped)]=copy.deepcopy(recipe)
            widget.refresh(index); widget.baseline=baseline; widget.update_modified()
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    if not from_run:
        run = QPushButton('Load images && run…'); run.clicked.connect(widget.load_photos_and_run); buttons.addWidget(run)
    close = QPushButton('Return to recipe runner' if from_run else 'Close')
    close.clicked.connect(dialog.accept); buttons.addWidget(close)
    layout.addLayout(buttons)
    return dialog


def launch(files=()):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        dialog = make_editor_dialog(files=files)
    except (OSError, RecipeError) as exc:
        QMessageBox.critical(None, 'Recipes', str(exc)); return 1
    dialog.exec()
    return 0


if __name__ == '__main__':
    raise SystemExit(launch(sys.argv[1:]))
