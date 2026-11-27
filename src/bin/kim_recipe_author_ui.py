"""Focused Recipe Editor parameter authoring UI components.

Kept separate from kim_recipe_dialog.py (library/tree/preview management) and
kim_recipe_param_ui.py (accepted Runner Settings form) so each module stays
small and focused. Delegates all validation, compatibility, dependency tracking,
and condition summarization to kim_recipe_params.
"""
import copy
import math
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kim_dialog_buttons import style_button_box
from kim_recipe_core import RecipeError
from kim_recipe_param_ui import _format_unit_suffix, _infer_unit
from kim_recipe_params import (
    MAX_CHOICES,
    MAX_CONDITION_CLAUSES,
    MAX_TEXT_LIMIT,
    SETTINGS_SOURCES,
    SETTINGS_SOURCE_LABELS,
    generate_parameter_id,
    parameter_references,
    summarize_condition,
)
from kim_ui import CaptureDateInput

PARAMETER_TYPE_LABELS = (
    ('text', 'Text'),
    ('integer', 'Whole number'),
    ('number', 'Decimal number'),
    ('boolean', 'Yes / No'),
    ('choice', 'List of choices'),
    ('capture_datetime', 'Capture date and time'),
)

PARAMETER_TYPE_DISPLAY = dict(PARAMETER_TYPE_LABELS)
PARAMETER_TYPE_DISPLAY['watermark_image'] = 'Watermark image file'

PARAMETER_TYPE_EXAMPLES = {
    'text': 'Short text such as a client or project name, subfolder or copyright text.',
    'integer': 'Whole numbers such as image pixels (1600) or JPEG quality (90).',
    'number': 'Numbers with decimals such as a scale factor or angle (e.g. 2.5).',
    'boolean': 'A checkbox to turn an option or operation on or off.',
    'choice': 'Pick one option from a predefined list (such as JPEG, WebP or PNG).',
    'capture_datetime': 'Date and time for setting or adjusting image capture dates.',
}

CONDITION_SUPPORTED_TYPES = ('boolean', 'choice', 'integer', 'text')


def _apply_muted_palette(label, *, smaller=True):
    if smaller:
        font = label.font()
        if font.pointSize() > 1:
            font.setPointSize(max(8, font.pointSize() - 1))
        label.setFont(font)
    pal = label.palette()
    color = pal.color(QPalette.Active, QPalette.WindowText)
    color.setAlphaF(0.72)
    pal.setColor(QPalette.Active, QPalette.WindowText, color)
    pal.setColor(QPalette.Inactive, QPalette.WindowText, color)
    label.setPalette(pal)


def _choice_pairs(param):
    pairs = []
    for item in param.get('choices', ()):
        if isinstance(item, dict):
            pairs.append((item['value'], item.get('label', item['value'])))
        else:
            pairs.append((str(item), str(item)))
    return pairs


def _display_op_name(op, fallback):
    if op == 'image.auto_orient':
        return 'Auto-orient'
    if op == 'metadata.strip_gps':
        return 'Remove GPS metadata'
    return fallback


_FORMAT_DISPLAY_NAMES = {
    'jpeg': 'JPEG',
    'png': 'PNG',
    'webp': 'WebP',
    'avif': 'AVIF',
    'heic': 'HEIC',
    'heif': 'HEIF',
    'tiff': 'TIFF',
    'jp2': 'JPEG 2000',
    'jxl': 'JPEG XL',
    'gif': 'GIF',
    'bmp': 'BMP',
    'pdf': 'PDF',
}


def _format_default_summary(param, *, unit=''):
    if 'default_source' in param:
        return SETTINGS_SOURCE_LABELS.get(param['default_source'], param['default_source'])
    if 'default' in param:
        val = param['default']
        if param['type'] == 'boolean':
            return 'Yes' if val else 'No'
        if param['type'] == 'choice':
            for value, label in _choice_pairs(param):
                if value == val:
                    return label
        if param['type'] in ('integer', 'number') and unit:
            return f'{val}{_format_unit_suffix(unit)}'
        return str(val)
    return 'Ask each time' if param.get('required', False) else 'Ask each time (optional)'


def _format_usage_summary(refs, *, recipe=None):
    if not refs:
        return 'Not used yet'
    steps = (recipe or {}).get('steps', ())
    labels = []
    # Group multiple field bindings on the same step under one operation prefix.
    step_bindings = {}
    ordered_items = []
    for ref in refs:
        kind = ref['kind']
        if kind == 'binding':
            step_idx = ref.get('step_index')
            op = ref.get('op', '')
            op_name = _display_op_name(op, ref.get('op_label', op))
            field = ref.get('field', '')
            field_label = ref.get('field_label', field)
            if op == 'image.convert' and field == 'quality' and isinstance(step_idx, int) and 0 <= step_idx < len(steps):
                step = steps[step_idx]
                if 'format' not in (step.get('bindings') or {}) and step.get('format'):
                    fmt = _FORMAT_DISPLAY_NAMES.get(step['format'], str(step['format']).upper())
                    field_label = f'{fmt} quality'
            key = (step_idx, op_name)
            if key not in step_bindings:
                step_bindings[key] = []
                ordered_items.append(('binding_group', key))
            if field_label not in step_bindings[key]:
                step_bindings[key].append(field_label)
        elif kind == 'filename_template':
            ordered_items.append(('text', 'Filename'))
        elif kind == 'destination_template':
            ordered_items.append(('text', 'Subfolder'))
        elif kind == 'enabled_when':
            op = ref.get('op', '')
            ordered_items.append(('text', _display_op_name(op, ref.get('op_label', op))))
        elif kind == 'visible_when':
            ordered_items.append(('text', ref.get('param_label', '')))
        else:
            ordered_items.append(('text', ref.get('description', '')))

    for item_kind, payload in ordered_items:
        if item_kind == 'binding_group':
            _, op_name = payload
            fields_text = ', '.join(step_bindings[payload])
            text = f'{op_name}: {fields_text}' if op_name else fields_text
        else:
            text = payload
        if text and text not in labels:
            labels.append(text)

    if len(labels) <= 3:
        return ', '.join(labels)
    return ', '.join(labels[:2]) + f', +{len(labels) - 2} more'


def _format_reference_lines(refs, *, recipe=None):
    """Format detailed human-readable lines for the 'This answer controls' section."""
    if not refs:
        return []
    steps = (recipe or {}).get('steps', ())
    lines = []
    step_bindings = {}
    ordered = []
    for ref in refs:
        kind = ref.get('kind')
        if kind == 'binding':
            step_idx = ref.get('step_index')
            op = ref.get('op', '')
            op_name = _display_op_name(op, ref.get('op_label', op))
            field = ref.get('field', '')
            field_label = ref.get('field_label', field)
            if op == 'image.convert' and field == 'quality' and isinstance(step_idx, int) and 0 <= step_idx < len(steps):
                step = steps[step_idx]
                if 'format' not in (step.get('bindings') or {}) and step.get('format'):
                    fmt = _FORMAT_DISPLAY_NAMES.get(step['format'], str(step['format']).upper())
                    field_label = f'{fmt} quality'
            key = (step_idx, op_name)
            if key not in step_bindings:
                step_bindings[key] = []
                ordered.append(('binding_group', key))
            if field_label not in step_bindings[key]:
                step_bindings[key].append(field_label)
        elif kind == 'filename_template':
            op = ref.get('op', '')
            op_name = _display_op_name(op, ref.get('op_label', 'Rename Output File'))
            ordered.append(('text', f'{op_name}: Filename'))
        elif kind == 'destination_template':
            ordered.append(('text', 'Destination: Subfolder'))
        elif kind == 'enabled_when':
            op = ref.get('op', '')
            op_name = _display_op_name(op, ref.get('op_label', op))
            ordered.append(('text', f'{op_name}: Whether this operation runs'))
        elif kind == 'visible_when':
            label = ref.get('param_label', '')
            ordered.append(('text', f'Question visibility: {label}' if label else 'Question visibility'))
        else:
            desc = ref.get('description', '')
            if desc:
                ordered.append(('text', desc))
    for item_kind, payload in ordered:
        if item_kind == 'binding_group':
            _, op_name = payload
            fields_text = ', '.join(step_bindings[payload])
            line = f'{op_name}: {fields_text}' if op_name else fields_text
        else:
            line = payload
        if line and line not in lines:
            lines.append(line)
    return lines


class _ConditionClauseRow(QWidget):
    """Single predicate row inside ConditionEditorWidget (param + operator + value)."""

    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, available_params, parent=None):
        super().__init__(parent)
        self._params = list(available_params)
        self._params_by_id = {p['id']: p for p in self._params}
        self._value_widget = None
        self._checkboxes = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.param_combo = QComboBox(self)
        self.param_combo.setMinimumWidth(140)
        for param in self._params:
            self.param_combo.addItem(param['label'], param['id'])
        layout.addWidget(self.param_combo)

        self.op_combo = QComboBox(self)
        self.op_combo.addItem('is', 'equals')
        self.op_combo.addItem('is one of', 'in')
        layout.addWidget(self.op_combo)

        self.value_host = QWidget(self)
        self.value_layout = QHBoxLayout(self.value_host)
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        self.value_layout.setSpacing(6)
        layout.addWidget(self.value_host, 1)

        self.remove_button = QToolButton(self)
        icon = QIcon.fromTheme('list-remove')
        if not icon.isNull():
            self.remove_button.setIcon(icon)
        else:
            self.remove_button.setText('×')
        self.remove_button.setToolTip('Remove this condition')
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_button)

        self.param_combo.currentIndexChanged.connect(self._rebuild_value_editor)
        self.op_combo.currentIndexChanged.connect(self._rebuild_value_editor)
        self._rebuild_value_editor()

    def set_removable(self, removable):
        self.remove_button.setVisible(bool(removable))

    def _clear_value_host(self):
        while self.value_layout.count():
            item = self.value_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._value_widget = None
        self._checkboxes = []

    def _current_param(self):
        pid = self.param_combo.currentData()
        return self._params_by_id.get(pid)

    def _rebuild_value_editor(self, *_):
        self._clear_value_host()
        param = self._current_param()
        if param is None:
            return
        ptype = param['type']
        op = self.op_combo.currentData()

        if ptype == 'boolean':
            if op == 'equals':
                combo = QComboBox(self.value_host)
                combo.addItem('Yes', True)
                combo.addItem('No', False)
                combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
                self.value_layout.addWidget(combo)
                self._value_widget = combo
            else:
                for text, val in (('Yes', True), ('No', False)):
                    cb = QCheckBox(text, self.value_host)
                    cb.setProperty('option_value', val)
                    cb.toggled.connect(lambda *_: self.changed.emit())
                    self.value_layout.addWidget(cb)
                    self._checkboxes.append(cb)
                self._checkboxes[0].setChecked(True)
        elif ptype == 'choice':
            pairs = _choice_pairs(param)
            if op == 'equals':
                combo = QComboBox(self.value_host)
                for val, label in pairs:
                    combo.addItem(label, val)
                combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
                self.value_layout.addWidget(combo)
                self._value_widget = combo
            else:
                for idx, (val, label) in enumerate(pairs):
                    cb = QCheckBox(label, self.value_host)
                    cb.setProperty('option_value', val)
                    if idx == 0:
                        cb.setChecked(True)
                    cb.toggled.connect(lambda *_: self.changed.emit())
                    self.value_layout.addWidget(cb)
                    self._checkboxes.append(cb)
        elif ptype == 'integer':
            if op == 'equals':
                spin = QSpinBox(self.value_host)
                low = param.get('minimum', -1_000_000)
                high = param.get('maximum', 1_000_000)
                spin.setRange(max(low, -2_000_000_000), min(high, 2_000_000_000))
                if 'default' in param and type(param['default']) is int:
                    spin.setValue(param['default'])
                spin.valueChanged.connect(lambda *_: self.changed.emit())
                self.value_layout.addWidget(spin)
                self._value_widget = spin
            else:
                edit = QLineEdit(self.value_host)
                edit.setPlaceholderText('Comma-separated whole numbers (e.g. 800, 1600)')
                edit.textChanged.connect(lambda *_: self.changed.emit())
                self.value_layout.addWidget(edit)
                self._value_widget = edit
        else:
            edit = QLineEdit(self.value_host)
            edit.setPlaceholderText(
                'Value' if op == 'equals' else 'Comma-separated values'
            )
            edit.textChanged.connect(lambda *_: self.changed.emit())
            self.value_layout.addWidget(edit)
            self._value_widget = edit

        self.changed.emit()

    def set_predicate(self, pred):
        pid = pred.get('param')
        idx = self.param_combo.findData(pid)
        if idx < 0:
            return
        self.param_combo.blockSignals(True)
        self.op_combo.blockSignals(True)
        self.param_combo.setCurrentIndex(idx)
        op = 'in' if 'in' in pred else 'equals'
        self.op_combo.setCurrentIndex(self.op_combo.findData(op))
        self.param_combo.blockSignals(False)
        self.op_combo.blockSignals(False)
        self._rebuild_value_editor()

        param = self._current_param()
        if param is None:
            return
        ptype = param['type']
        if op == 'equals':
            val = pred['equals']
            if isinstance(self._value_widget, QComboBox):
                found = self._value_widget.findData(val)
                if found >= 0:
                    self._value_widget.setCurrentIndex(found)
            elif isinstance(self._value_widget, QSpinBox) and type(val) is int:
                self._value_widget.setValue(val)
            elif isinstance(self._value_widget, QLineEdit):
                self._value_widget.setText(str(val))
        else:
            options = list(pred.get('in', ()))
            if self._checkboxes:
                for cb in self._checkboxes:
                    opt_val = cb.property('option_value')
                    cb.setChecked(any(
                        type(opt_val) is type(o) and opt_val == o
                        for o in options
                    ))
            elif isinstance(self._value_widget, QLineEdit):
                self._value_widget.setText(', '.join(str(o) for o in options))
        self.changed.emit()

    def predicate(self):
        param = self._current_param()
        if param is None:
            raise RecipeError('Choose a parameter for the condition.')
        pid = param['id']
        ptype = param['type']
        op = self.op_combo.currentData()

        if op == 'equals':
            if isinstance(self._value_widget, QComboBox):
                return {'param': pid, 'equals': self._value_widget.currentData()}
            if isinstance(self._value_widget, QSpinBox):
                return {'param': pid, 'equals': int(self._value_widget.value())}
            text_val = self._value_widget.text() if isinstance(self._value_widget, QLineEdit) else ''
            return {'param': pid, 'equals': text_val}

        if self._checkboxes:
            selected = [
                cb.property('option_value')
                for cb in self._checkboxes
                if cb.isChecked()
            ]
            if not selected:
                raise RecipeError(f"Select at least one value for '{param['label']}'.")
            return {'param': pid, 'in': selected}

        raw = self._value_widget.text() if isinstance(self._value_widget, QLineEdit) else ''
        pieces = [part.strip() for part in raw.split(',') if part.strip()]
        if not pieces:
            raise RecipeError(f"Enter at least one value for '{param['label']}'.")
        if ptype == 'integer':
            values = []
            for piece in pieces:
                try:
                    values.append(int(piece))
                except ValueError as exc:
                    raise RecipeError(f"'{piece}' is not a whole number.") from exc
            return {'param': pid, 'in': values}
        return {'param': pid, 'in': pieces}


class ConditionEditorWidget(QWidget):
    """Compact condition builder supporting equality, membership, and conjunctions."""

    changed = Signal()

    def __init__(
        self,
        available_params,
        *,
        verb='Show',
        target_label='this item',
        always_label='Always',
        conditional_label='Only when condition is met',
        parent=None,
    ):
        super().__init__(parent)
        self._available = [
            copy.deepcopy(p)
            for p in available_params
            if p.get('type') in CONDITION_SUPPORTED_TYPES
        ]
        self._params_by_id = {p['id']: p for p in self._available}
        self._verb = verb
        self._target_label = target_label
        self._rows = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        self.always_radio = QRadioButton(always_label, self)
        self.cond_radio = QRadioButton(conditional_label, self)
        self.always_radio.setChecked(True)
        mode_row.addWidget(self.always_radio)
        mode_row.addWidget(self.cond_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.no_params_note = QLabel(
            'Add an earlier Yes / No, Choice, Whole number, or Text parameter to use conditions.',
            self,
        )
        self.no_params_note.setTextFormat(Qt.PlainText)
        self.no_params_note.setWordWrap(True)
        _apply_muted_palette(self.no_params_note, smaller=True)
        layout.addWidget(self.no_params_note)

        self.clauses_panel = QWidget(self)
        clauses_outer = QVBoxLayout(self.clauses_panel)
        clauses_outer.setContentsMargins(16, 2, 0, 2)
        clauses_outer.setSpacing(4)

        self.clauses_box = QVBoxLayout()
        self.clauses_box.setContentsMargins(0, 0, 0, 0)
        self.clauses_box.setSpacing(4)
        clauses_outer.addLayout(self.clauses_box)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        self.add_clause_button = QPushButton(
            QIcon.fromTheme('list-add'),
            'Add another condition (AND)',
            self.clauses_panel,
        )
        self.add_clause_button.clicked.connect(lambda: self._add_row())
        add_row.addWidget(self.add_clause_button)
        add_row.addStretch(1)
        clauses_outer.addLayout(add_row)

        self.summary_label = QLabel('', self.clauses_panel)
        self.summary_label.setTextFormat(Qt.PlainText)
        self.summary_label.setWordWrap(True)
        _apply_muted_palette(self.summary_label, smaller=True)
        clauses_outer.addWidget(self.summary_label)

        layout.addWidget(self.clauses_panel)

        has_available = bool(self._available)
        self.cond_radio.setEnabled(has_available)
        self.no_params_note.setVisible(not has_available)
        self.clauses_panel.setVisible(False)

        self.always_radio.toggled.connect(self._on_mode_toggled)
        self.cond_radio.toggled.connect(self._on_mode_toggled)

    def set_target_label(self, label):
        self._target_label = (label or '').strip() or 'this item'
        self._refresh_summary()

    def _on_mode_toggled(self, *_):
        conditional = self.cond_radio.isChecked() and bool(self._available)
        if conditional and not self._rows:
            self._add_row()
        self.clauses_panel.setVisible(conditional)
        self._refresh_summary()
        self.changed.emit()

    def _add_row(self, pred=None):
        if not self._available or len(self._rows) >= MAX_CONDITION_CLAUSES:
            return
        row = _ConditionClauseRow(self._available, self.clauses_panel)
        row.changed.connect(self._refresh_summary)
        row.changed.connect(self.changed.emit)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self.clauses_box.addWidget(row)
        if pred is not None:
            row.set_predicate(pred)
        self._sync_row_controls()
        self._refresh_summary()

    def _remove_row(self, row):
        if row in self._rows and len(self._rows) > 1:
            self._rows.remove(row)
            self.clauses_box.removeWidget(row)
            row.deleteLater()
            self._sync_row_controls()
            self._refresh_summary()
            self.changed.emit()

    def _sync_row_controls(self):
        multi = len(self._rows) > 1
        for row in self._rows:
            row.set_removable(multi)
        self.add_clause_button.setEnabled(len(self._rows) < MAX_CONDITION_CLAUSES)

    def _refresh_summary(self):
        if not self.cond_radio.isChecked() or not self._rows:
            self.summary_label.setText('')
            return
        try:
            cond = self.condition()
            prose = summarize_condition(cond, self._params_by_id)
            self.summary_label.setText(f'{self._verb} {self._target_label} when {prose}.')
        except RecipeError as exc:
            self.summary_label.setText(str(exc))

    def set_condition(self, cond):
        for row in list(self._rows):
            self.clauses_box.removeWidget(row)
            row.hide()
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self.always_radio.blockSignals(True)
        self.cond_radio.blockSignals(True)
        try:
            if cond is None or not self._available:
                self.always_radio.setChecked(True)
                self.clauses_panel.setVisible(False)
                self._refresh_summary()
                return
            self.cond_radio.setChecked(True)
        finally:
            self.always_radio.blockSignals(False)
            self.cond_radio.blockSignals(False)
        preds = cond['all'] if 'all' in cond else [cond]
        for pred in preds:
            self._add_row(pred)
        self.clauses_panel.setVisible(True)
        self._refresh_summary()

    def condition(self):
        if not self.cond_radio.isChecked():
            return None
        if not self._rows:
            raise RecipeError('Add at least one condition.')
        preds = [row.predicate() for row in self._rows]
        return preds[0] if len(preds) == 1 else {'all': preds}


class ParameterEditorDialog(QDialog):
    """Native dialog to create or edit one authored Recipe question/parameter."""

    def __init__(
        self,
        *,
        param=None,
        existing_ids=(),
        earlier_params=(),
        locked_type=False,
        references=None,
        recipe=None,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self._editing = param is not None and 'id' in param
        self._fixed_id = param['id'] if self._editing else None
        self._existing_ids = set(existing_ids or ())
        self._earlier_params = list(earlier_params or ())
        self._locked_type = bool(locked_type)
        self._references = list(references) if references is not None else None
        self._recipe = recipe
        self._validate_callback = validate_callback
        self.result_param = None
        self._default_widget = None
        self._loading = False

        self.setWindowTitle(
            'KIMng - Edit Parameter' if self._editing else 'KIMng - Add Parameter'
        )
        self.setMinimumWidth(520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        host_layout = QVBoxLayout(self._host)
        host_layout.setContentsMargins(2, 2, 6, 2)
        host_layout.setSpacing(10)

        # --- Basic section ---
        self._form = QFormLayout()
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        self._form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._form.setHorizontalSpacing(12)
        self._form.setVerticalSpacing(8)

        q_box = QWidget(self._host)
        q_layout = QVBoxLayout(q_box)
        q_layout.setContentsMargins(0, 0, 0, 0)
        q_layout.setSpacing(2)
        self.label_edit = QLineEdit(q_box)
        self.label_edit.setPlaceholderText('e.g. Client or project name')
        self.label_edit.setMaxLength(120)
        q_layout.addWidget(self.label_edit)
        q_hint = QLabel('This is the question displayed when running the Recipe.', q_box)
        q_hint.setTextFormat(Qt.PlainText)
        q_hint.setWordWrap(True)
        _apply_muted_palette(q_hint, smaller=True)
        q_layout.addWidget(q_hint)
        self._form.addRow('Question to ask:', q_box)

        self.type_combo = QComboBox(self._host)
        for idx, (ptype, title) in enumerate(PARAMETER_TYPE_LABELS):
            self.type_combo.addItem(title, ptype)
            tip = PARAMETER_TYPE_EXAMPLES.get(ptype, '')
            if tip:
                self.type_combo.setItemData(idx, tip, Qt.ToolTipRole)
        if self._locked_type:
            self.type_combo.setEnabled(False)
            self.type_combo.setToolTip(
                'Answer type cannot be changed while this question is used by an operation, condition, or template.'
            )
        else:
            self.type_combo.setToolTip(
                'Choose what kind of value the person running this Recipe will enter.'
            )
        self._form.addRow('Answer type:', self.type_combo)

        # Choices editor (visible in basic section when Answer type is Choice).
        self.choices_panel = QWidget(self._host)
        choices_layout = QVBoxLayout(self.choices_panel)
        choices_layout.setContentsMargins(0, 0, 0, 0)
        choices_layout.setSpacing(4)
        self.choices_table = QTableWidget(0, 2, self.choices_panel)
        self.choices_table.setHorizontalHeaderLabels(['Display label', 'Stored value'])
        self.choices_table.verticalHeader().setVisible(False)
        self.choices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.choices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.choices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.choices_table.setMaximumHeight(120)
        choices_layout.addWidget(self.choices_table)

        c_bar = QHBoxLayout()
        c_bar.setContentsMargins(0, 0, 0, 0)
        add_c = QPushButton(QIcon.fromTheme('list-add'), 'Add choice', self.choices_panel)
        rem_c = QPushButton(QIcon.fromTheme('list-remove'), 'Remove', self.choices_panel)
        up_c = QPushButton('Up', self.choices_panel)
        dn_c = QPushButton('Down', self.choices_panel)
        add_c.clicked.connect(self._add_choice_row)
        rem_c.clicked.connect(self._remove_choice_row)
        up_c.clicked.connect(lambda: self._move_choice_row(-1))
        dn_c.clicked.connect(lambda: self._move_choice_row(1))
        for btn in (add_c, rem_c, up_c, dn_c):
            c_bar.addWidget(btn)
        c_bar.addStretch(1)
        choices_layout.addLayout(c_bar)
        self._form.addRow('Choices:', self.choices_panel)

        # Default answer radios with immediate inline control.
        default_box = QWidget(self._host)
        default_layout = QVBoxLayout(default_box)
        default_layout.setContentsMargins(0, 0, 0, 0)
        default_layout.setSpacing(4)

        self._default_group = QButtonGroup(self)
        self.default_ask_radio = QRadioButton('Ask each time', default_box)
        self.default_literal_radio = QRadioButton('Start with this answer', default_box)
        self.default_settings_radio = QRadioButton('Use application Settings', default_box)
        self.default_settings_radio.setToolTip(
            'Obtains a configured value from KIMng Settings, such as your saved copyright notice or Web Export quality.'
        )
        self._default_group.addButton(self.default_ask_radio)
        self._default_group.addButton(self.default_literal_radio)
        self._default_group.addButton(self.default_settings_radio)
        self.default_ask_radio.setChecked(True)

        default_layout.addWidget(self.default_ask_radio)
        default_layout.addWidget(self.default_literal_radio)

        self.default_value_host = QWidget(default_box)
        self.default_value_layout = QHBoxLayout(self.default_value_host)
        self.default_value_layout.setContentsMargins(22, 0, 0, 2)
        self.default_value_layout.setSpacing(6)
        default_layout.addWidget(self.default_value_host)

        default_layout.addWidget(self.default_settings_radio)

        self.default_source_host = QWidget(default_box)
        source_layout = QHBoxLayout(self.default_source_host)
        source_layout.setContentsMargins(22, 0, 0, 2)
        self.default_source_combo = QComboBox(self.default_source_host)
        source_layout.addWidget(self.default_source_combo, 1)
        default_layout.addWidget(self.default_source_host)

        self._form.addRow('Default answer:', default_box)

        # Required & remember options.
        opts_box = QWidget(self._host)
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setContentsMargins(0, 0, 0, 0)
        opts_layout.setSpacing(3)
        self.required_check = QCheckBox('Require an answer', opts_box)
        opts_layout.addWidget(self.required_check)

        self.remember_check = QCheckBox('Remember the last answer', opts_box)
        self.remember_check.setToolTip(
            'Remember this answer after a successful run and prefill it next time.'
        )
        opts_layout.addWidget(self.remember_check)
        self._form.addRow('', opts_box)

        host_layout.addLayout(self._form)

        # --- What this answer controls (shown when editing a saved/existing parameter) ---
        if self._editing or self._references is not None:
            self.controls_group = QGroupBox('This answer controls', self._host)
            controls_outer = QVBoxLayout(self.controls_group)
            controls_outer.setContentsMargins(10, 6, 10, 6)
            controls_outer.setSpacing(2)
            ref_lines = _format_reference_lines(self._references or (), recipe=self._recipe)
            if ref_lines:
                self.controls_label = QLabel('\n'.join(f'• {line}' for line in ref_lines), self.controls_group)
                self.controls_label.setTextFormat(Qt.PlainText)
                self.controls_label.setWordWrap(True)
            else:
                self.controls_label = QLabel(
                    'Not used yet. Connect this question to an operation or destination setting to use its answer.',
                    self.controls_group,
                )
                self.controls_label.setTextFormat(Qt.PlainText)
                self.controls_label.setWordWrap(True)
                _apply_muted_palette(self.controls_label, smaller=False)
            controls_outer.addWidget(self.controls_label)
            host_layout.addWidget(self.controls_group)
        else:
            self.controls_group = None
            self.controls_label = None

        # --- Live Runner appearance example ---
        self.preview_group = QGroupBox('How it will appear when running', self._host)
        preview_outer = QVBoxLayout(self.preview_group)
        preview_outer.setContentsMargins(10, 8, 10, 8)
        preview_outer.setSpacing(4)
        self.preview_note = QLabel(
            'Example preview only (does not change the saved default above).',
            self.preview_group,
        )
        self.preview_note.setTextFormat(Qt.PlainText)
        self.preview_note.setWordWrap(True)
        _apply_muted_palette(self.preview_note, smaller=True)
        preview_outer.addWidget(self.preview_note)
        self._preview_form = QFormLayout()
        self._preview_form.setContentsMargins(0, 0, 0, 0)
        self._preview_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._preview_form.setHorizontalSpacing(10)
        self._preview_form.setVerticalSpacing(2)
        preview_outer.addLayout(self._preview_form)
        self.preview_help_label = QLabel('', self.preview_group)
        self.preview_help_label.setTextFormat(Qt.PlainText)
        self.preview_help_label.setWordWrap(True)
        _apply_muted_palette(self.preview_help_label, smaller=True)
        self.preview_help_label.hide()
        preview_outer.addWidget(self.preview_help_label)
        self._preview_caption = None
        self._preview_control = None
        host_layout.addWidget(self.preview_group)

        # --- Collapsible Advanced settings ---
        self.advanced_toggle = QToolButton(self._host)
        self.advanced_toggle.setText('Advanced settings')
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setAutoRaise(True)
        host_layout.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)

        self.advanced_panel = QWidget(self._host)
        self._adv_form = QFormLayout(self.advanced_panel)
        self._adv_form.setContentsMargins(12, 2, 0, 4)
        self._adv_form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        self._adv_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._adv_form.setHorizontalSpacing(12)
        self._adv_form.setVerticalSpacing(8)

        self.help_edit = QPlainTextEdit(self.advanced_panel)
        self.help_edit.setPlaceholderText('Optional short guidance shown beneath the control')
        self.help_edit.setTabChangesFocus(True)
        self.help_edit.setMinimumHeight(48)
        self.help_edit.setMaximumHeight(72)
        self._adv_form.addRow('Help text (optional):', self.help_edit)

        self.max_length_spin = QSpinBox(self.advanced_panel)
        self.max_length_spin.setRange(0, MAX_TEXT_LIMIT)
        self.max_length_spin.setSpecialValueText('Default limit')
        self.max_length_spin.setMaximumWidth(150)
        self._adv_form.addRow('Maximum answer length:', self.max_length_spin)

        self.bounds_row = QWidget(self.advanced_panel)
        bounds_layout = QHBoxLayout(self.bounds_row)
        bounds_layout.setContentsMargins(0, 0, 0, 0)
        bounds_layout.setSpacing(6)
        self.min_edit = QLineEdit(self.bounds_row)
        self.min_edit.setPlaceholderText('Minimum')
        self.min_edit.setMaximumWidth(120)
        self.max_edit = QLineEdit(self.bounds_row)
        self.max_edit.setPlaceholderText('Maximum')
        self.max_edit.setMaximumWidth(120)
        bounds_layout.addWidget(self.min_edit)
        bounds_layout.addWidget(QLabel('to', self.bounds_row))
        bounds_layout.addWidget(self.max_edit)
        bounds_layout.addStretch(1)
        self._adv_form.addRow('Allowed range:', self.bounds_row)

        self.condition_editor = ConditionEditorWidget(
            self._earlier_params,
            verb='Show',
            target_label=(param.get('label') if param else 'this question'),
            always_label='Always',
            conditional_label='Only when a condition is met',
            parent=self.advanced_panel,
        )
        self._adv_form.addRow('Show this question:', self.condition_editor)

        self.advanced_display_check = QCheckBox(
            'Show this question under Advanced settings when running',
            self.advanced_panel,
        )
        self.advanced_display_check.setToolTip(
            'Keep less frequently changed settings out of the main Recipe form.'
        )
        self._adv_form.addRow('', self.advanced_display_check)

        self.advanced_panel.hide()
        host_layout.addWidget(self.advanced_panel)

        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self.error_label = QLabel('', self)
        self.error_label.setTextFormat(Qt.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #b3261e;')
        self.error_label.hide()
        outer.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        style_button_box(self.buttons)
        self.buttons.accepted.connect(self._try_accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)

        self.label_edit.textChanged.connect(self._on_label_changed)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        for radio in (
            self.default_ask_radio,
            self.default_literal_radio,
            self.default_settings_radio,
        ):
            radio.toggled.connect(self._sync_default_visibility)
        self.default_source_combo.currentIndexChanged.connect(self._refresh_runner_preview)
        self.required_check.toggled.connect(self._refresh_runner_preview)
        self.help_edit.textChanged.connect(self._refresh_runner_preview)
        self.choices_table.itemChanged.connect(self._refresh_choice_default_options)
        self.advanced_toggle.toggled.connect(self._set_advanced_expanded)

        self._load_initial(param)
        self._sync_dialog_size()

    def _on_label_changed(self, text):
        self.condition_editor.set_target_label(text or 'this question')
        self._refresh_runner_preview()

    def _default_mode(self):
        if self.default_settings_radio.isChecked() and self.default_settings_radio.isVisibleTo(self):
            return 'settings'
        if self.default_literal_radio.isChecked():
            return 'literal'
        return 'none'

    def _set_default_mode(self, mode):
        for radio in (
            self.default_ask_radio,
            self.default_literal_radio,
            self.default_settings_radio,
        ):
            radio.blockSignals(True)
        try:
            if mode == 'settings' and self.default_source_combo.count() > 0:
                self.default_settings_radio.setChecked(True)
            elif mode == 'literal':
                self.default_literal_radio.setChecked(True)
            else:
                self.default_ask_radio.setChecked(True)
        finally:
            for radio in (
                self.default_ask_radio,
                self.default_literal_radio,
                self.default_settings_radio,
            ):
                radio.blockSignals(False)
        self._sync_default_visibility()

    def _set_advanced_expanded(self, expanded):
        expanded = bool(expanded)
        self.advanced_toggle.blockSignals(True)
        self.advanced_toggle.setChecked(expanded)
        self.advanced_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.advanced_toggle.blockSignals(False)
        self.advanced_panel.setVisible(expanded)
        self._sync_dialog_size()

    def is_advanced_expanded(self):
        return self.advanced_toggle.isChecked()

    def _sync_dialog_size(self):
        if self._host.layout() is not None:
            self._host.layout().activate()
        self._host.adjustSize()
        content_h = self._host.sizeHint().height()
        extra = self.buttons.sizeHint().height() + 56
        if self.error_label.isVisible():
            extra += self.error_label.sizeHint().height() + 8
        target_h = min(max(content_h + extra, 300), 650)
        target_w = max(self.width(), 560)
        self.resize(target_w, target_h)

    def _load_initial(self, param):
        self._loading = True
        try:
            if param is None:
                self._on_type_changed()
                self._set_default_mode('none')
                return
            self.label_edit.setText(param.get('label', ''))
            self.label_edit.setCursorPosition(0)
            idx = self.type_combo.findData(param.get('type', 'text'))
            if idx >= 0:
                self.type_combo.blockSignals(True)
                self.type_combo.setCurrentIndex(idx)
                self.type_combo.blockSignals(False)
            self.help_edit.setPlainText(param.get('help', ''))
            self.required_check.setChecked(bool(param.get('required', False)))
            self.remember_check.setChecked(bool(param.get('remember', False)))
            self.advanced_display_check.setChecked(bool(param.get('advanced', False)))

            if param.get('type') == 'text' and 'max_length' in param:
                self.max_length_spin.setValue(int(param['max_length']))
            if param.get('type') in ('integer', 'number'):
                if 'minimum' in param:
                    self.min_edit.setText(str(param['minimum']))
                if 'maximum' in param:
                    self.max_edit.setText(str(param['maximum']))
            if param.get('type') == 'choice':
                self.choices_table.blockSignals(True)
                for val, label in _choice_pairs(param):
                    r = self.choices_table.rowCount()
                    self.choices_table.insertRow(r)
                    self.choices_table.setItem(r, 0, QTableWidgetItem(label))
                    self.choices_table.setItem(r, 1, QTableWidgetItem(val))
                self.choices_table.blockSignals(False)

            self._on_type_changed()

            if 'default_source' in param:
                s_idx = self.default_source_combo.findData(param['default_source'])
                if s_idx >= 0:
                    self.default_source_combo.setCurrentIndex(s_idx)
                self._set_default_mode('settings')
            elif 'default' in param:
                self._set_default_mode('literal')
                self._set_default_widget_value(param['default'])
            else:
                self._set_default_mode('none')

            self.condition_editor.set_condition(param.get('visible_when'))
        finally:
            self._loading = False
        self._refresh_runner_preview()

    def _current_type(self):
        return self.type_combo.currentData()

    def _on_type_changed(self, *_):
        ptype = self._current_type()

        # Populate allowed Settings sources for this type.
        self.default_source_combo.blockSignals(True)
        self.default_source_combo.clear()
        for key, (expected_type, _) in SETTINGS_SOURCES.items():
            if expected_type == ptype:
                self.default_source_combo.addItem(
                    SETTINGS_SOURCE_LABELS.get(key, key), key
                )
        self.default_source_combo.blockSignals(False)
        has_settings = self.default_source_combo.count() > 0
        self.default_settings_radio.setVisible(has_settings)
        self.default_settings_radio.setEnabled(has_settings)
        if not has_settings and self.default_settings_radio.isChecked():
            self.default_ask_radio.setChecked(True)

        self._adv_form.setRowVisible(self.max_length_spin, ptype == 'text')
        self._adv_form.setRowVisible(self.bounds_row, ptype in ('integer', 'number'))
        self._form.setRowVisible(self.choices_panel, ptype == 'choice')

        if ptype == 'choice' and self.choices_table.rowCount() == 0:
            self._add_choice_row('Option 1', 'option_1')
            self._add_choice_row('Option 2', 'option_2')

        self._rebuild_default_widget()
        self._sync_default_visibility()
        if not self._loading:
            self._sync_dialog_size()

    def _rebuild_default_widget(self):
        while self.default_value_layout.count():
            item = self.default_value_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._default_widget = None
        ptype = self._current_type()

        if ptype == 'text':
            w = QLineEdit(self.default_value_host)
            w.setPlaceholderText('e.g. Marathon')
            w.textChanged.connect(self._refresh_runner_preview)
        elif ptype in ('integer', 'number'):
            w = QLineEdit(self.default_value_host)
            w.setPlaceholderText('e.g. 1600' if ptype == 'integer' else 'e.g. 1.5')
            w.setMaximumWidth(140)
            w.textChanged.connect(self._refresh_runner_preview)
        elif ptype == 'boolean':
            w = QComboBox(self.default_value_host)
            w.addItem('Yes', True)
            w.addItem('No', False)
            w.currentIndexChanged.connect(self._refresh_runner_preview)
        elif ptype == 'choice':
            w = QComboBox(self.default_value_host)
            self._populate_choice_combo(w)
            w.currentIndexChanged.connect(self._refresh_runner_preview)
        else:
            w = CaptureDateInput('', self.default_value_host)
            w.changed.connect(self._refresh_runner_preview)

        self._default_widget = w
        self.default_value_layout.addWidget(w)
        if ptype in ('integer', 'number', 'boolean'):
            self.default_value_layout.addStretch(1)

    def _populate_choice_combo(self, combo):
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for r in range(self.choices_table.rowCount()):
            label_item = self.choices_table.item(r, 0)
            val_item = self.choices_table.item(r, 1)
            label = (label_item.text() if label_item else '').strip()
            val = (val_item.text() if val_item else '').strip() or self._slug_value(label, r)
            if label or val:
                combo.addItem(label or val, val)
        if current is not None:
            found = combo.findData(current)
            if found >= 0:
                combo.setCurrentIndex(found)
        combo.blockSignals(False)

    def _refresh_choice_default_options(self, *_):
        if self._current_type() == 'choice' and isinstance(self._default_widget, QComboBox):
            self._populate_choice_combo(self._default_widget)
        self._refresh_runner_preview()

    def _set_default_widget_value(self, value):
        w = self._default_widget
        if isinstance(w, QLineEdit):
            w.setText(str(value))
        elif isinstance(w, QComboBox):
            found = w.findData(value)
            if found >= 0:
                w.setCurrentIndex(found)
        elif isinstance(w, CaptureDateInput) and isinstance(value, str) and value:
            from PySide6.QtCore import QDate, QTime
            parts = value.replace('T', ' ').split(' ', 1)
            if len(parts) == 2:
                w.date.setDate(QDate.fromString(parts[0], 'yyyy-MM-dd'))
                clock = QTime.fromString(parts[1].split('.', 1)[0], 'HH:mm:ss')
                if clock.isValid():
                    w.time.setTime(clock)

    def _sync_default_visibility(self, *_):
        mode = self._default_mode()
        self.default_value_host.setVisible(mode == 'literal')
        self.default_source_host.setVisible(
            mode == 'settings' and self.default_source_combo.count() > 0
        )
        self._refresh_runner_preview()
        if not self._loading:
            self._sync_dialog_size()

    def _refresh_runner_preview(self, *_):
        """Update the read-only example showing how the question appears in the Runner."""
        while self._preview_form.rowCount():
            self._preview_form.removeRow(0)
        self._preview_caption = None
        self._preview_control = None

        raw_q = self.label_edit.text().strip()
        question = raw_q or 'Client or project name'
        ptype = self._current_type()
        mode = self._default_mode()
        has_default = mode in ('literal', 'settings')
        required = self.required_check.isChecked()

        caption_text = question.rstrip(':')
        if not required and not has_default:
            caption_text += ' (optional)'
        caption_text += ':'

        if ptype == 'boolean' and has_default:
            cb = QCheckBox(question, self.preview_group)
            cb.setEnabled(False)
            cb.setFocusPolicy(Qt.NoFocus)
            if mode == 'literal' and isinstance(self._default_widget, QComboBox):
                cb.setChecked(bool(self._default_widget.currentData()))
            self._preview_control = cb
            self._preview_form.addRow('', cb)
        elif ptype in ('boolean', 'choice'):
            combo = QComboBox(self.preview_group)
            combo.setEnabled(False)
            combo.setFocusPolicy(Qt.NoFocus)
            if mode == 'literal' and isinstance(self._default_widget, QComboBox):
                text = self._default_widget.currentText() or ('Yes' if ptype == 'boolean' else 'Option 1')
                combo.addItem(text)
            elif mode == 'settings':
                combo.addItem(self.default_source_combo.currentText() or 'From Settings')
            else:
                combo.addItem('Choose…' if required else 'Not set')
            self._preview_caption = QLabel(caption_text, self.preview_group)
            self._preview_caption.setTextFormat(Qt.PlainText)
            self._preview_control = combo
            self._preview_form.addRow(self._preview_caption, combo)
        else:
            edit = QLineEdit(self.preview_group)
            edit.setReadOnly(True)
            edit.setFocusPolicy(Qt.NoFocus)
            if mode == 'settings':
                src_label = self.default_source_combo.currentText() or 'application Settings'
                edit.setPlaceholderText(f'Default from {src_label}')
            elif mode == 'literal':
                if isinstance(self._default_widget, QLineEdit):
                    val = self._default_widget.text()
                    if val:
                        edit.setText(val)
                    else:
                        edit.setPlaceholderText('Empty default')
                elif isinstance(self._default_widget, CaptureDateInput):
                    val = self._default_widget.value()
                    if val:
                        edit.setText(val)
                    else:
                        edit.setPlaceholderText('YYYY-MM-DD HH:MM:SS')
            else:
                if ptype == 'text':
                    q_low = question.rstrip(':').casefold()
                    edit.setPlaceholderText(
                        'Optional' if not required
                        else 'Enter a name' if q_low.endswith('name')
                        else 'Enter a value'
                    )
                elif ptype == 'integer':
                    edit.setPlaceholderText('Not set')
                elif ptype == 'number':
                    edit.setPlaceholderText('Enter a number')
                else:
                    edit.setPlaceholderText('YYYY-MM-DD HH:MM:SS')
            if not raw_q:
                _apply_muted_palette(edit, smaller=False)
            self._preview_caption = QLabel(caption_text, self.preview_group)
            self._preview_caption.setTextFormat(Qt.PlainText)
            if not raw_q:
                _apply_muted_palette(self._preview_caption, smaller=False)
            self._preview_control = edit
            self._preview_form.addRow(self._preview_caption, edit)

        help_text = self.help_edit.toPlainText().strip()
        self.preview_help_label.setText(help_text)
        self.preview_help_label.setVisible(bool(help_text))

    @staticmethod
    def _slug_value(label, row_idx):
        slug = re.sub(r'[^a-z0-9]+', '_', (label or '').casefold()).strip('_')
        return slug or f'choice_{row_idx + 1}'

    def _add_choice_row(self, label='', value=''):
        if self.choices_table.rowCount() >= MAX_CHOICES:
            return
        r = self.choices_table.rowCount()
        self.choices_table.blockSignals(True)
        self.choices_table.insertRow(r)
        if not isinstance(label, str):
            label = ''
        if not isinstance(value, str):
            value = ''
        self.choices_table.setItem(r, 0, QTableWidgetItem(label or f'Option {r + 1}'))
        self.choices_table.setItem(r, 1, QTableWidgetItem(value or f'option_{r + 1}'))
        self.choices_table.blockSignals(False)
        self._refresh_choice_default_options()

    def _remove_choice_row(self):
        row = self.choices_table.currentRow()
        if row >= 0:
            self.choices_table.removeRow(row)
            self._refresh_choice_default_options()

    def _move_choice_row(self, delta):
        row = self.choices_table.currentRow()
        target = row + delta
        if not (0 <= row < self.choices_table.rowCount() and 0 <= target < self.choices_table.rowCount()):
            return
        self.choices_table.blockSignals(True)
        for col in (0, 1):
            a = self.choices_table.item(row, col)
            b = self.choices_table.item(target, col)
            a_text = a.text() if a else ''
            b_text = b.text() if b else ''
            self.choices_table.setItem(row, col, QTableWidgetItem(b_text))
            self.choices_table.setItem(target, col, QTableWidgetItem(a_text))
        self.choices_table.blockSignals(False)
        self.choices_table.selectRow(target)
        self._refresh_choice_default_options()

    def build_parameter(self):
        label = self.label_edit.text().strip()
        if not label:
            raise RecipeError('Enter a question to ask when running this Recipe.')
        ptype = self._current_type()
        pid = self._fixed_id or generate_parameter_id(label, self._existing_ids)
        param = {'id': pid, 'label': label, 'type': ptype}

        help_text = self.help_edit.toPlainText().strip()
        if help_text:
            param['help'] = help_text
        if self.required_check.isChecked():
            param['required'] = True
        if self.remember_check.isChecked():
            param['remember'] = True
        if self.advanced_display_check.isChecked():
            param['advanced'] = True

        if ptype == 'text' and self.max_length_spin.value() > 0:
            param['max_length'] = int(self.max_length_spin.value())

        if ptype in ('integer', 'number'):
            for key, edit in (('minimum', self.min_edit), ('maximum', self.max_edit)):
                raw = edit.text().strip()
                if not raw:
                    continue
                try:
                    val = int(raw) if ptype == 'integer' else float(raw)
                except ValueError as exc:
                    raise RecipeError(
                        f"{key.capitalize()} must be {'a whole number' if ptype == 'integer' else 'a valid number'}."
                    ) from exc
                if ptype == 'number' and not math.isfinite(val):
                    raise RecipeError(f'{key.capitalize()} must be a finite number.')
                param[key] = val

        if ptype == 'choice':
            choices = []
            seen_vals = set()
            for r in range(self.choices_table.rowCount()):
                l_item = self.choices_table.item(r, 0)
                v_item = self.choices_table.item(r, 1)
                c_label = (l_item.text() if l_item else '').strip()
                c_val = (v_item.text() if v_item else '').strip() or self._slug_value(c_label, r)
                if not c_label and not c_val:
                    continue
                if c_val in seen_vals:
                    raise RecipeError(f"Duplicate choice value '{c_val}'.")
                seen_vals.add(c_val)
                choices.append({'value': c_val, 'label': c_label or c_val})
            if not choices:
                raise RecipeError('Add at least one choice option.')
            param['choices'] = choices

        mode = self._default_mode()
        if mode == 'settings':
            src = self.default_source_combo.currentData()
            if not src:
                raise RecipeError('Choose a KIMng Settings source.')
            param['default_source'] = src
        elif mode == 'literal':
            w = self._default_widget
            if ptype == 'text':
                param['default'] = w.text()
            elif ptype == 'integer':
                raw = w.text().strip()
                if not raw:
                    raise RecipeError('Enter a default whole number or choose Ask each time.')
                try:
                    param['default'] = int(raw)
                except ValueError as exc:
                    raise RecipeError('Default answer must be a whole number.') from exc
            elif ptype == 'number':
                raw = w.text().strip()
                if not raw:
                    raise RecipeError('Enter a default number or choose Ask each time.')
                try:
                    val = float(raw)
                except ValueError as exc:
                    raise RecipeError('Default answer must be a valid number.') from exc
                if not math.isfinite(val):
                    raise RecipeError('Default answer must be a finite number.')
                param['default'] = val
            elif ptype == 'boolean':
                param['default'] = bool(w.currentData())
            elif ptype == 'choice':
                if w.count() == 0:
                    raise RecipeError('Add a choice before selecting a default.')
                param['default'] = w.currentData()
            elif ptype == 'capture_datetime':
                val = w.value()
                if not val:
                    raise RecipeError('Enter a default date and time or choose Ask each time.')
                param['default'] = val

        cond = self.condition_editor.condition()
        if cond is not None:
            param['visible_when'] = cond

        return param

    def _is_advanced_error(self, message):
        low = message.casefold()
        return any(
            token in low
            for token in (
                'minimum',
                'maximum',
                'max_length',
                'length',
                'condition',
                'visible_when',
                'help',
                'earlier parameter',
            )
        )

    def _try_accept(self):
        try:
            built = self.build_parameter()
            if callable(self._validate_callback):
                self._validate_callback(built)
        except (RecipeError, ValueError) as exc:
            msg = str(exc)
            if self._is_advanced_error(msg) and not self.is_advanced_expanded():
                self._set_advanced_expanded(True)
            self.error_label.setText(msg)
            self.error_label.show()
            self._sync_dialog_size()
            return
        self.error_label.hide()
        self.result_param = built
        self.accept()


class StepActivationDialog(QDialog):
    """Dialog to configure Always, Never, or Conditional operation execution."""

    def __init__(
        self,
        *,
        step_label,
        enabled,
        enabled_when,
        available_params,
        validate_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self._validate_callback = validate_callback
        self.result_enabled = True
        self.result_enabled_when = None

        self.setWindowTitle('KIMng - Operation Condition')
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        heading = QLabel(f'Choose when “{step_label}” runs:', self)
        heading.setTextFormat(Qt.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self.always_radio = QRadioButton('Always', self)
        self.disabled_radio = QRadioButton('Never', self)
        self.cond_radio = QRadioButton('Only when a condition is met', self)
        layout.addWidget(self.always_radio)
        layout.addWidget(self.disabled_radio)
        layout.addWidget(self.cond_radio)

        self.condition_editor = ConditionEditorWidget(
            available_params,
            verb='Run',
            target_label=step_label,
            always_label='Always',
            conditional_label='Only when a condition is met',
            parent=self,
        )
        # Hide ConditionEditorWidget's own top radio row since this dialog owns the 3-way mode.
        self.condition_editor.always_radio.hide()
        self.condition_editor.cond_radio.hide()
        layout.addWidget(self.condition_editor)

        has_params = bool(self.condition_editor._available)
        self.cond_radio.setEnabled(has_params)

        if enabled is False:
            self.disabled_radio.setChecked(True)
        elif enabled_when is not None and has_params:
            self.cond_radio.setChecked(True)
            self.condition_editor.set_condition(enabled_when)
        else:
            self.always_radio.setChecked(True)

        self.error_label = QLabel('', self)
        self.error_label.setTextFormat(Qt.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #b3261e;')
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        style_button_box(buttons)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for radio in (self.always_radio, self.disabled_radio, self.cond_radio):
            radio.toggled.connect(self._sync_mode)
        self._sync_mode()
        self.adjustSize()

    def _sync_mode(self, *_):
        cond_active = self.cond_radio.isChecked()
        self.condition_editor.cond_radio.setChecked(cond_active)
        if not cond_active:
            self.condition_editor.always_radio.setChecked(True)
        self.condition_editor.setVisible(cond_active or not self.condition_editor._available)
        self.condition_editor.clauses_panel.setVisible(cond_active)

    def _try_accept(self):
        try:
            if self.disabled_radio.isChecked():
                enabled = False
                enabled_when = None
            elif self.cond_radio.isChecked():
                enabled = True
                enabled_when = self.condition_editor.condition()
                if enabled_when is None:
                    raise RecipeError('Choose a condition for this operation.')
            else:
                enabled = True
                enabled_when = None
            if callable(self._validate_callback):
                self._validate_callback(enabled, enabled_when)
        except (RecipeError, ValueError) as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.error_label.hide()
        self.result_enabled = enabled
        self.result_enabled_when = enabled_when
        self.accept()


class ParametersSectionWidget(QWidget):
    """Central Parameters management view hosted inside the Editor's Parameters tab."""

    add_requested = Signal()
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    move_requested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._immutable = False
        self._param_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.intro_label = QLabel(
            'Parameters let you ask questions whose answers control Recipe settings.',
            self,
        )
        self.intro_label.setTextFormat(Qt.PlainText)
        self.intro_label.setWordWrap(True)
        layout.addWidget(self.intro_label)

        # Neutral empty state for fixed-value Recipes without questions.
        self.empty_panel = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.setContentsMargins(20, 24, 20, 24)
        empty_layout.setSpacing(8)
        empty_layout.addStretch(1)

        self.empty_heading = QLabel('Let your Recipe ask questions', self.empty_panel)
        self.empty_heading.setTextFormat(Qt.PlainText)
        self.empty_heading.setWordWrap(True)
        self.empty_heading.setAlignment(Qt.AlignCenter)
        heading_font = self.empty_heading.font()
        heading_font.setBold(True)
        if heading_font.pointSize() > 0:
            heading_font.setPointSize(heading_font.pointSize() + 1)
        self.empty_heading.setFont(heading_font)
        empty_layout.addWidget(self.empty_heading)

        self.empty_label = QLabel(
            'Ask for settings such as JPEG quality, image dimensions or a project name when running this Recipe.',
            self.empty_panel,
        )
        self.empty_label.setTextFormat(Qt.PlainText)
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_label)

        self.empty_add_button = QPushButton(
            QIcon.fromTheme('list-add'),
            'Add question…',
            self.empty_panel,
        )
        self.empty_add_button.clicked.connect(self.add_requested.emit)
        empty_layout.addWidget(self.empty_add_button, 0, Qt.AlignCenter)

        self.empty_guidance = QLabel(
            "Choose Ask when running in an operation's settings to create a question.",
            self.empty_panel,
        )
        self.empty_guidance.setTextFormat(Qt.PlainText)
        self.empty_guidance.setWordWrap(True)
        self.empty_guidance.setAlignment(Qt.AlignCenter)
        _apply_muted_palette(self.empty_guidance, smaller=True)
        empty_layout.addWidget(self.empty_guidance)
        empty_layout.addStretch(1)
        layout.addWidget(self.empty_panel, 1)

        # Full-width 3-column table + actions when questions exist.
        self.table_panel = QWidget(self)
        table_layout = QVBoxLayout(self.table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        self.tree = QTreeWidget(self.table_panel)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(['Question', 'Default answer', 'Used in'])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setAccessibleName('Recipe questions')
        hdr = self.tree.header()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.setColumnWidth(0, 260)
        self.tree.currentItemChanged.connect(self._sync_buttons)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        table_layout.addWidget(self.tree, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self.add_button = QPushButton(QIcon.fromTheme('list-add'), 'Add question…', self.table_panel)
        self.edit_button = QPushButton('Edit…', self.table_panel)
        self.remove_button = QPushButton(QIcon.fromTheme('list-remove'), 'Remove', self.table_panel)
        self.up_button = QToolButton(self.table_panel)
        self.down_button = QToolButton(self.table_panel)
        for btn, icon_name, arrow, tip in (
            (self.up_button, 'go-up', Qt.UpArrow, 'Move question up'),
            (self.down_button, 'go-down', Qt.DownArrow, 'Move question down'),
        ):
            ic = QIcon.fromTheme(icon_name)
            if ic.isNull():
                btn.setArrowType(arrow)
            else:
                btn.setIcon(ic)
            btn.setToolTip(tip)
            btn.setAccessibleName(tip)

        self.add_button.clicked.connect(self.add_requested.emit)
        self.edit_button.clicked.connect(self._emit_edit)
        self.remove_button.clicked.connect(self._emit_remove)
        self.up_button.clicked.connect(lambda: self._emit_move(-1))
        self.down_button.clicked.connect(lambda: self._emit_move(1))

        for widget in (
            self.add_button,
            self.edit_button,
            self.remove_button,
            self.up_button,
            self.down_button,
        ):
            bar.addWidget(widget)
        bar.addStretch(1)
        table_layout.addLayout(bar)

        self.table_panel.hide()
        layout.addWidget(self.table_panel, 1)

    def parameter_count(self):
        return self._param_count

    def selected_parameter_id(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def set_recipe(self, recipe, *, immutable=False, definitions=None, select_id=None):
        self._immutable = bool(immutable)
        params = list((recipe or {}).get('parameters', ()))
        self._param_count = len(params)

        previous = select_id or self.selected_parameter_id()
        params_by_id = {p['id']: p for p in params}

        self.tree.blockSignals(True)
        self.tree.clear()
        select_item = None
        for param in params:
            pid = param['id']
            refs = parameter_references(recipe, pid, definitions=definitions)
            unit = _infer_unit(recipe, pid) if isinstance(recipe, dict) else ''
            type_display = PARAMETER_TYPE_DISPLAY.get(param['type'], param['type'])
            item = QTreeWidgetItem([
                param['label'],
                _format_default_summary(param, unit=unit),
                _format_usage_summary(refs, recipe=recipe),
            ])
            item.setData(0, Qt.UserRole, pid)
            if param.get('advanced', False):
                adv_icon = QIcon.fromTheme('configure')
                if not adv_icon.isNull():
                    item.setIcon(0, adv_icon)
            tip_lines = [
                f"Question: {param['label']}",
                f'Answer type: {type_display}',
            ]
            if param.get('advanced', False):
                tip_lines.append('Shown under Advanced settings when running.')
            if param.get('remember', False):
                tip_lines.append('Remembers the last answer after a successful run.')
            if param.get('required', False) and 'default' not in param and 'default_source' not in param:
                tip_lines.append('Required answer each time this Recipe runs.')
            if param.get('help'):
                tip_lines.append(param['help'])
            if param.get('visible_when') is not None:
                tip_lines.append(
                    'Shown when ' + summarize_condition(param['visible_when'], params_by_id)
                )
            if refs:
                tip_lines.append('Used in: ' + ', '.join(r['description'] for r in refs))
            else:
                tip_lines.append('Not used yet. Connect this question to an operation or destination setting to use its answer.')
                muted = self.tree.palette().color(QPalette.Disabled, QPalette.WindowText)
                item.setForeground(2, muted)
            tip = '\n'.join(tip_lines)
            for col in range(3):
                item.setToolTip(col, tip)
            self.tree.addTopLevelItem(item)
            if pid == previous:
                select_item = item
        if select_item is not None:
            self.tree.setCurrentItem(select_item)
        elif self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.blockSignals(False)

        has_params = bool(params)
        self.intro_label.setVisible(has_params)
        self.table_panel.setVisible(has_params)
        self.empty_panel.setVisible(not has_params)
        if not has_params:
            self.empty_heading.setText('Let your Recipe ask questions')
            self.empty_label.setText(
                'Ask for settings such as JPEG quality, image dimensions or a project name when running this Recipe.'
            )
            if self._immutable:
                self.empty_guidance.setText(
                    'Choose Selected Recipe > Duplicate Recipe to create an editable copy.'
                )
            else:
                self.empty_guidance.setText(
                    "Choose Ask when running in an operation's settings to create a question."
                )
        self._sync_buttons()

    def _sync_buttons(self, *_):
        editable = not self._immutable
        item = self.tree.currentItem()
        row = self.tree.indexOfTopLevelItem(item) if item is not None else -1
        count = self.tree.topLevelItemCount()
        self.empty_add_button.setEnabled(editable)
        self.empty_add_button.setVisible(editable)
        self.add_button.setEnabled(editable)
        self.edit_button.setEnabled(editable and row >= 0)
        self.remove_button.setEnabled(editable and row >= 0)
        self.up_button.setEnabled(editable and row > 0)
        self.down_button.setEnabled(editable and 0 <= row < count - 1)

    def _on_double_click(self, item, _column):
        if not self._immutable and item is not None:
            pid = item.data(0, Qt.UserRole)
            if pid:
                self.edit_requested.emit(pid)

    def _emit_edit(self):
        pid = self.selected_parameter_id()
        if pid:
            self.edit_requested.emit(pid)

    def _emit_remove(self):
        pid = self.selected_parameter_id()
        if pid:
            self.remove_requested.emit(pid)

    def _emit_move(self, delta):
        pid = self.selected_parameter_id()
        if pid:
            self.move_requested.emit(pid, delta)


def make_field_source_button(bound_label=None, parent=None):
    """Compact adjacent value-source popup button for an operation field."""
    btn = QToolButton(parent)
    btn.setPopupMode(QToolButton.InstantPopup)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setText('Ask' if bound_label else 'Fixed')
    btn.setToolTip(
        f'Ask when running: {bound_label}'
        if bound_label
        else 'Use a fixed value, ask when running, or reuse an existing question'
    )
    btn.setMinimumWidth(58)
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return btn


def make_insert_variable_button(parent=None):
    """Compact Insert variable popup button for filename and subfolder templates."""
    btn = QToolButton(parent)
    btn.setPopupMode(QToolButton.InstantPopup)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setText('Insert variable')
    btn.setToolTip('Insert an image property or a Recipe question into this pattern')
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return btn
