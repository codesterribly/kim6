"""Reusable Qt parameter form and contextual Runner Settings page.

Shared by RunRecipeDialog's contextual Settings page and the forthcoming
Recipe Editor Preview Settings action. Delegates all parameter validation,
visibility, default resolution and constraint rules to kim_recipe_params.
"""
import copy
import math
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kim_recipe_params import (
    effective_constraints,
    evaluate_parameters,
    has_parameterized_output_templates,
    preview_output_example,
    validate_authored,
)
from kim_ui import CaptureDateInput, HELP

_UNSET = object()

_SPINBOX_MIN_LIMIT = -2_000_000_000
_SPINBOX_MAX_LIMIT = 2_000_000_000

_FIELD_UNITS = {
    ('image.resize', 'max_width'): 'px',
    ('image.resize', 'max_height'): 'px',
    ('image.resize_exact', 'width'): 'px',
    ('image.resize_exact', 'height'): 'px',
    ('image.resize_long_edge', 'pixels'): 'px',
    ('image.crop', 'crop_width'): 'px',
    ('image.crop', 'crop_height'): 'px',
    ('image.crop', 'target_width'): 'px',
    ('image.crop', 'target_height'): 'px',
    ('image.resize_percent', 'percent'): '%',
    ('image.overlay', 'opacity'): '%',
    ('image.overlay', 'size'): '%',
    ('image.overlay', 'margin'): '%',
    ('image.rotate', 'degrees'): '°',
    ('metadata.shift_capture', 'seconds'): 's',
}


def _infer_unit(authored, pid):
    """Infer a single consistent display unit from bound operation fields."""
    units = set()
    for step in authored.get('steps', ()):
        if step.get('enabled', True) is False:
            continue
        bindings = step.get('bindings') or {}
        op = step.get('op')
        for field, bound_id in bindings.items():
            if bound_id == pid:
                unit = _FIELD_UNITS.get((op, field))
                if unit:
                    units.add(unit)
    return next(iter(units)) if len(units) == 1 else ''


def _format_unit_suffix(unit):
    if not unit:
        return ''
    return unit if unit in ('%', '°') else ' ' + unit


def _choice_entries(param):
    entries = []
    for item in param['choices']:
        if isinstance(item, dict):
            entries.append((item['label'], item['value']))
        else:
            entries.append((str(item), item))
    return entries


def _can_use_spinbox(param, eff):
    if param['type'] != 'integer':
        return False
    low = eff.get('minimum')
    high = eff.get('maximum')
    return (
        low is not None
        and high is not None
        and low > _SPINBOX_MIN_LIMIT
        and high < _SPINBOX_MAX_LIMIT
    )


def _range_hint(eff, unit=''):
    low = eff.get('minimum')
    high = eff.get('maximum')
    suffix = _format_unit_suffix(unit)
    if low is not None and high is not None:
        return f'{low} to {high}{suffix}'
    if low is not None:
        return f'At least {low}{suffix}'
    if high is not None:
        return f'At most {high}{suffix}'
    return ''


def _field_caption(param, has_default):
    base = param['label'].strip().rstrip(':')
    if not param.get('required', False) and not has_default:
        base += ' (optional)'
    return base + ':'


def _text_placeholder(param):
    if not param.get('required', False):
        return 'Optional'
    label = param['label'].strip().rstrip(':').casefold()
    if label.endswith('name'):
        return 'Enter a name'
    return 'Enter a value'


def _condition_param_ids(cond):
    if not isinstance(cond, dict):
        return ()
    if 'all' in cond:
        return tuple(c['param'] for c in cond['all'] if isinstance(c, dict) and 'param' in c)
    if 'param' in cond:
        return (cond['param'],)
    return ()


def _visibility_depth(param, params_by_id, seen=None):
    cond = param.get('visible_when')
    if cond is None:
        return 0
    seen = set() if seen is None else seen
    pid = param['id']
    if pid in seen:
        return 0
    seen.add(pid)
    depths = [
        _visibility_depth(params_by_id[parent_id], params_by_id, seen)
        for parent_id in _condition_param_ids(cond)
        if parent_id in params_by_id
    ]
    return 1 + (max(depths) if depths else 0)


def _build_tooltip(authored, param, eff, unit):
    """Derive helpful native tooltips from bindings and numeric constraints."""
    pid = param['id']
    parts = []
    bound_pairs = set()
    controls_ops = set()
    for step in authored.get('steps', ()):
        if step.get('enabled', True) is False:
            continue
        op = step.get('op')
        for field, bound_id in (step.get('bindings') or {}).items():
            if bound_id == pid:
                bound_pairs.add((op, field))
        if pid in _condition_param_ids(step.get('enabled_when')):
            controls_ops.add(op)

    if ('image.convert', 'quality') in bound_pairs or ('image.compress', 'quality') in bound_pairs:
        parts.append(HELP['quality'][1])
    elif param['type'] == 'boolean' and 'metadata.strip_gps' in controls_ops and not param.get('help'):
        parts.append('Removes embedded GPS coordinates from the saved copies.')

    if param['type'] in ('integer', 'number'):
        hint = _range_hint(eff, unit)
        if hint:
            parts.append('Allowed range: ' + hint + '.')

    return ' '.join(parts)


def _apply_muted_style(label, *, smaller=True):
    """Style secondary guidance using the active Qt palette (light & dark safe)."""
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


def _check_single_component_text(value):
    if '/' in value or '\\' in value:
        return 'Cannot contain path separators (/ or \\).'
    if value in ('.', '..'):
        return 'Enter a valid folder or filename.'
    return ''


def _format_inline_error(param, raw_error, *, eff, unit):
    """Translate resolver/validation messages into clear, natural inline errors."""
    if not raw_error:
        return ''
    ptype = param['type']
    suffix = _format_unit_suffix(unit)

    if ptype in ('integer', 'number'):
        low = eff.get('minimum')
        high = eff.get('maximum')
        if 'must be at least' in raw_error or 'must be at most' in raw_error:
            if low is not None and high is not None:
                return f'Enter a value between {low} and {high}{suffix}.'
            if low is not None:
                return f'Enter a value of at least {low}{suffix}.'
            if high is not None:
                return f'Enter a value of at most {high}{suffix}.'
        if 'must be an integer' in raw_error:
            return 'Enter a whole number.'
        if 'must be a finite number' in raw_error:
            return 'Enter a valid number.'

    if ptype == 'text':
        if 'at most' in raw_error and 'characters' in raw_error:
            limit = eff.get('max_length')
            if limit is not None:
                return f'Enter at most {limit} characters.'
        if 'control characters' in raw_error or 'unsupported characters' in raw_error.casefold():
            return 'Remove unsupported control characters.'
        if 'requires a non-empty value' in raw_error:
            return 'Enter a value, not just spaces.'

    if ptype == 'capture_datetime':
        return 'Enter a valid date and time (YYYY-MM-DD HH:MM:SS).'

    if ptype == 'watermark_image':
        return 'Choose a local watermark image file.'

    if ptype == 'choice':
        return 'Choose one of the available options.'

    if ptype == 'boolean':
        return 'Choose Yes or No.'

    return raw_error


def _is_missing_required_error(raw_error):
    return bool(
        raw_error
        and (
            raw_error.endswith('requires a value.')
            or raw_error.endswith('requires a non-empty value.')
            or raw_error.endswith('requires an image capture date and time.')
            or raw_error == 'Choose a watermark image file.'
            or raw_error.endswith('requires a local watermark image file.')
        )
    )


class WatermarkImageChooser(QWidget):
    """Read-only path display with a native file chooser for watermark image assets."""

    changed = Signal(str)

    _FILE_FILTER = (
        'Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp *.gif '
        '*.heic *.heif *.avif *.jxl *.jp2 *.psd);;All files (*)'
    )

    def __init__(self, initial='', parent=None):
        super().__init__(parent)
        self._path = ''
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.display = QLineEdit(self)
        self.display.setReadOnly(True)
        self.display.setPlaceholderText('No watermark image selected')
        self.display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.choose_button = QPushButton('Choose image…', self)
        self.choose_button.clicked.connect(self._choose_file)
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(lambda: self.set_path('', emit=True))
        layout.addWidget(self.display, 1)
        layout.addWidget(self.choose_button)
        layout.addWidget(self.clear_button)
        self.set_path(initial or '', emit=False)

    def value(self):
        return self._path

    def set_path(self, path, *, emit=True):
        cleaned = path if isinstance(path, str) else ''
        if cleaned == self._path and emit:
            return
        self._path = cleaned
        if cleaned:
            self.display.setText(Path(cleaned).name)
            self.display.setToolTip(cleaned)
            self.clear_button.setEnabled(True)
        else:
            self.display.clear()
            self.display.setToolTip('')
            self.clear_button.setEnabled(False)
        if emit:
            self.changed.emit(self._path)

    def _choose_file(self):
        start_dir = str(Path(self._path).parent) if self._path else str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(
            self, 'Choose watermark image', start_dir, self._FILE_FILTER
        )
        if chosen:
            self.set_path(chosen, emit=True)


class _WrappedLabel(QLabel):
    """Word-wrapped plain-text label whose height tracks its allocated width."""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(True)
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self):
        return True

    def minimumSizeHint(self):
        width = self.width()
        if width > 0 and self.text():
            return QSize(0, self.heightForWidth(width))
        return super().minimumSizeHint()

    def sizeHint(self):
        width = self.width()
        if width > 0 and self.text():
            return QSize(width, self.heightForWidth(width))
        return super().sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()


class ParameterFormWidget(QWidget):
    """Declarative Qt parameter form driven by kim_recipe_params."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._authored = None
        self._constraints = {}
        self._params = []
        self._params_by_id = {}
        self._entered = {}
        self._parse_errors = {}
        self._rows = {}
        self._default_state = {}
        self._evaluation = {
            'active': [],
            'values': {},
            'errors': {},
            'constraints': {},
        }
        self._populating = False
        self._user_expanded_advanced = False

        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(8)

        self._main_host = QWidget(self)
        main_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        main_policy.setHeightForWidth(True)
        self._main_host.setSizePolicy(main_policy)
        self._form = QFormLayout(self._main_host)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        self._form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._form.setHorizontalSpacing(12)
        self._form.setVerticalSpacing(8)
        self._outer.addWidget(self._main_host)

        self._advanced_toggle = QToolButton(self)
        self._advanced_toggle.setText('Advanced settings')
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setChecked(False)
        self._advanced_toggle.setArrowType(Qt.RightArrow)
        self._advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._advanced_toggle.setAutoRaise(True)
        self._advanced_toggle.clicked.connect(self._on_advanced_toggle_clicked)
        self._advanced_toggle.hide()
        self._outer.addWidget(self._advanced_toggle, 0, Qt.AlignLeft)

        self._advanced_panel = QWidget(self)
        adv_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        adv_policy.setHeightForWidth(True)
        self._advanced_panel.setSizePolicy(adv_policy)
        self._advanced_form = QFormLayout(self._advanced_panel)
        self._advanced_form.setContentsMargins(12, 2, 0, 2)
        self._advanced_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self._advanced_form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self._advanced_form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        self._advanced_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._advanced_form.setHorizontalSpacing(12)
        self._advanced_form.setVerticalSpacing(8)
        self._advanced_panel.hide()
        self._outer.addWidget(self._advanced_panel)

    def _on_advanced_toggle_clicked(self, checked):
        self._user_expanded_advanced = bool(checked)
        self.set_advanced_expanded(bool(checked), user=True)

    def set_advanced_expanded(self, expanded, *, user=True):
        expanded = bool(expanded)
        if user:
            self._user_expanded_advanced = expanded
        self._advanced_toggle.blockSignals(True)
        self._advanced_toggle.setChecked(expanded)
        self._advanced_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._advanced_toggle.blockSignals(False)
        show_panel = expanded and self._advanced_toggle.isVisibleTo(self)
        self._advanced_panel.setVisible(show_panel)
        self._invalidate_wrapped_layouts()

    def is_advanced_expanded(self):
        return self._advanced_toggle.isChecked() and self._advanced_panel.isVisibleTo(self)

    def has_active_advanced(self):
        return self._advanced_toggle.isVisibleTo(self)

    def clear(self):
        self._populating = True
        try:
            while self._form.rowCount():
                self._form.removeRow(0)
            while self._advanced_form.rowCount():
                self._advanced_form.removeRow(0)
            self._authored = None
            self._constraints = {}
            self._params = []
            self._params_by_id = {}
            self._entered = {}
            self._parse_errors = {}
            self._rows = {}
            self._default_state = {}
            self._user_expanded_advanced = False
            self._advanced_toggle.blockSignals(True)
            self._advanced_toggle.setChecked(False)
            self._advanced_toggle.setArrowType(Qt.RightArrow)
            self._advanced_toggle.blockSignals(False)
            self._advanced_toggle.hide()
            self._advanced_panel.hide()
            self._evaluation = {
                'active': [],
                'values': {},
                'errors': {},
                'constraints': {},
            }
        finally:
            self._populating = False

    def set_recipe(self, recipe, entered_values=None):
        """Build widgets once for a validated authored Recipe and evaluate state."""
        authored = validate_authored(recipe)
        eff = effective_constraints(authored, validated=True)

        self.clear()
        self._populating = True
        try:
            self._authored = authored
            self._constraints = eff
            self._params = list(authored.get('parameters', []))
            self._params_by_id = {p['id']: p for p in self._params}
            self._entered = {}
            self._parse_errors = {}

            # Compute canonical default state (used to enable/disable Reset to defaults).
            defaults_state = evaluate_parameters(
                self._authored,
                {},
                validated=True,
                constraints=self._constraints,
            )
            self._default_state = self._compute_default_widget_state(
                defaults_state['values']
            )

            # Seed initial entered values only for declared parameter IDs.
            if isinstance(entered_values, dict):
                for pid, val in entered_values.items():
                    if pid in self._params_by_id and val is not None:
                        self._entered[pid] = copy.deepcopy(val)

            initial_state = evaluate_parameters(
                self._authored,
                self._entered,
                validated=True,
                constraints=self._constraints,
            )

            for param in self._params:
                self._build_row(param, initial_state['values'])
        finally:
            self._populating = False

        self._refresh_evaluation(emit=False)

    def _compute_default_widget_state(self, default_values):
        state = {}
        for param in self._params:
            pid = param['id']
            eff = self._constraints.get(pid, {})
            if pid in default_values:
                val = default_values[pid]
            elif 'default' in param:
                val = param['default']
            else:
                val = _UNSET

            ptype = param['type']
            if ptype == 'text':
                state[pid] = val if isinstance(val, str) else ''
            elif _can_use_spinbox(param, eff):
                low = eff['minimum']
                high = eff['maximum']
                if val is not _UNSET and type(val) is int and low <= val <= high:
                    state[pid] = val
                else:
                    state[pid] = _UNSET
            elif ptype in ('integer', 'number'):
                state[pid] = '' if val is _UNSET else str(val)
            elif ptype == 'boolean':
                has_default = 'default' in param or 'default_source' in param
                if has_default:
                    state[pid] = bool(val) if val is not _UNSET else False
                else:
                    state[pid] = val if type(val) is bool else _UNSET
            elif ptype == 'choice':
                state[pid] = val if val is not _UNSET else _UNSET
            elif ptype == 'capture_datetime':
                state[pid] = val if isinstance(val, str) else ''
            elif ptype == 'watermark_image':
                state[pid] = val if isinstance(val, str) else ''
        return state

    def _current_widget_state(self):
        state = {}
        for pid, meta in self._rows.items():
            widget = meta['widget']
            kind = meta['kind']
            if kind == 'text':
                state[pid] = widget.text()
            elif kind == 'spinbox':
                val = widget.value()
                state[pid] = _UNSET if val == meta['unset_sentinel'] else int(val)
            elif kind == 'numeric_text':
                state[pid] = widget.text().strip()
            elif kind == 'checkbox':
                state[pid] = bool(widget.isChecked())
            elif kind in ('bool_combo', 'choice'):
                data = widget.currentData()
                state[pid] = _UNSET if data is _UNSET else data
            elif kind in ('capture_datetime', 'watermark_image'):
                state[pid] = widget.value()
        return state

    def is_at_defaults(self):
        """Return True when all controls match the Recipe's original default state."""
        if self._authored is None:
            return True
        if self._parse_errors:
            return False
        current = self._current_widget_state()
        for pid, expected in self._default_state.items():
            actual = current.get(pid, _UNSET)
            if (actual is _UNSET) != (expected is _UNSET):
                return False
            if actual is _UNSET:
                continue
            if (type(actual) is bool) != (type(expected) is bool):
                return False
            if actual != expected:
                return False
        return True

    def _compact_numeric_width(self, widget, sample_text, *, is_spinbox):
        fm = widget.fontMetrics()
        chrome = 54 if is_spinbox else 28
        width = max(116, fm.horizontalAdvance(sample_text) + chrome)
        return min(max(width, 116), 200)

    def _build_row(self, param, initial_values):
        pid = param['id']
        ptype = param['type']
        eff = self._constraints.get(pid, {})
        unit = _infer_unit(self._authored, pid)
        has_default = 'default' in param or 'default_source' in param
        if pid in self._entered:
            initial = self._entered[pid]
        elif pid in initial_values:
            initial = initial_values[pid]
        elif 'default' in param:
            initial = param['default']
        else:
            initial = _UNSET

        depth = _visibility_depth(param, self._params_by_id)
        indent = 20 * depth

        is_advanced = bool(param.get('advanced', False))
        parent_host = self._advanced_panel if is_advanced else self._main_host
        target_form = self._advanced_form if is_advanced else self._form

        container = QWidget(parent_host)
        c_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        c_policy.setHeightForWidth(True)
        container.setSizePolicy(c_policy)
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(indent, 0, 0, 0)
        vbox.setSpacing(2)

        meta = {
            'type': ptype,
            'eff': eff,
            'unit': unit,
            'container': container,
            'depth': depth,
            'advanced': is_advanced,
            'form_layout': target_form,
        }

        if ptype == 'text':
            widget = QLineEdit(container)
            widget.setClearButtonEnabled(True)
            widget.setMaxLength(eff.get('max_length', 500))
            widget.setPlaceholderText(_text_placeholder(param))
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if initial is not _UNSET and isinstance(initial, str):
                widget.setText(initial)
            widget.setAccessibleName(param['label'])
            widget.textChanged.connect(
                lambda text, p=pid: self._on_text_changed(p, text)
            )
            meta['kind'] = 'text'
            vbox.addWidget(widget)

        elif _can_use_spinbox(param, eff):
            low = eff['minimum']
            high = eff['maximum']
            unset_sentinel = low - 1
            widget = QSpinBox(container)
            widget.setRange(unset_sentinel, high)
            widget.setSpecialValueText('Not set')
            suffix = _format_unit_suffix(unit)
            if suffix:
                widget.setSuffix(suffix)
            sample_num = max((str(low), str(high), 'Not set'), key=len)
            compact_w = self._compact_numeric_width(
                widget, sample_num + suffix, is_spinbox=True
            )
            widget.setMinimumWidth(compact_w)
            widget.setMaximumWidth(max(compact_w + 12, 136))
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if initial is not _UNSET and type(initial) is int and low <= initial <= high:
                widget.setValue(initial)
            else:
                widget.setValue(unset_sentinel)
            widget.setAccessibleName(param['label'])
            widget.valueChanged.connect(
                lambda val, p=pid, s=unset_sentinel: self._on_spin_changed(p, val, s)
            )
            meta['kind'] = 'spinbox'
            meta['unset_sentinel'] = unset_sentinel
            row_box = QHBoxLayout()
            row_box.setContentsMargins(0, 0, 0, 0)
            row_box.setSpacing(6)
            row_box.addWidget(widget)
            row_box.addStretch(1)
            vbox.addLayout(row_box)

        elif ptype in ('integer', 'number'):
            widget = QLineEdit(container)
            widget.setClearButtonEnabled(True)
            widget.setPlaceholderText(
                'Enter a number' if ptype == 'number' else 'Enter a value'
            )
            compact_w = self._compact_numeric_width(
                widget, '-100000.00', is_spinbox=False
            )
            widget.setMinimumWidth(compact_w)
            widget.setMaximumWidth(max(compact_w + 16, 140))
            widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            if initial is not _UNSET:
                widget.setText(str(initial))
            widget.setAccessibleName(param['label'])
            widget.textChanged.connect(
                lambda text, p=pid: self._on_numeric_text_changed(p, text)
            )
            meta['kind'] = 'numeric_text'
            row_box = QHBoxLayout()
            row_box.setContentsMargins(0, 0, 0, 0)
            row_box.setSpacing(6)
            row_box.addWidget(widget)
            if unit:
                unit_lbl = QLabel(unit, container)
                unit_lbl.setTextFormat(Qt.PlainText)
                row_box.addWidget(unit_lbl)
            row_box.addStretch(1)
            vbox.addLayout(row_box)

        elif ptype == 'boolean':
            if has_default:
                widget = QCheckBox(param['label'], container)
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                widget.setChecked(bool(initial) if initial is not _UNSET else False)
                widget.setAccessibleName(param['label'])
                widget.toggled.connect(
                    lambda checked, p=pid: self._on_bool_changed(p, checked)
                )
                meta['kind'] = 'checkbox'
                vbox.addWidget(widget)
            else:
                widget = QComboBox(container)
                widget.addItem(
                    'Choose…' if param.get('required', False) else 'Not set',
                    _UNSET,
                )
                widget.addItem('Yes', True)
                widget.addItem('No', False)
                if initial is True:
                    widget.setCurrentIndex(1)
                elif initial is False:
                    widget.setCurrentIndex(2)
                else:
                    widget.setCurrentIndex(0)
                widget.setMinimumWidth(max(130, widget.sizeHint().width() + 12))
                widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                widget.setAccessibleName(param['label'])
                widget.currentIndexChanged.connect(
                    lambda idx, p=pid, w=widget: self._on_combo_changed(p, w.itemData(idx))
                )
                meta['kind'] = 'bool_combo'
                row_box = QHBoxLayout()
                row_box.setContentsMargins(0, 0, 0, 0)
                row_box.addWidget(widget)
                row_box.addStretch(1)
                vbox.addLayout(row_box)

        elif ptype == 'choice':
            widget = QComboBox(container)
            if not has_default:
                widget.addItem(
                    'Choose…' if param.get('required', False) else 'Not set',
                    _UNSET,
                )
            for label, value in _choice_entries(param):
                widget.addItem(label, value)
            if initial is not _UNSET:
                found = widget.findData(initial)
                if found >= 0:
                    widget.setCurrentIndex(found)
            widget.setMinimumWidth(max(150, widget.sizeHint().width() + 16))
            widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            widget.setAccessibleName(param['label'])
            widget.currentIndexChanged.connect(
                lambda idx, p=pid, w=widget: self._on_combo_changed(p, w.itemData(idx))
            )
            meta['kind'] = 'choice'
            row_box = QHBoxLayout()
            row_box.setContentsMargins(0, 0, 0, 0)
            row_box.addWidget(widget)
            row_box.addStretch(1)
            vbox.addLayout(row_box)

        elif ptype == 'capture_datetime':
            initial_str = initial if isinstance(initial, str) else ''
            widget = CaptureDateInput(initial_str, container)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.changed.connect(
                lambda value, p=pid: self._on_datetime_changed(p, value)
            )
            meta['kind'] = 'capture_datetime'
            vbox.addWidget(widget)

        elif ptype == 'watermark_image':
            initial_str = initial if isinstance(initial, str) else ''
            widget = WatermarkImageChooser(initial_str, container)
            widget.setAccessibleName(param['label'])
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.changed.connect(
                lambda value, p=pid: self._on_text_changed(p, value)
            )
            meta['kind'] = 'watermark_image'
            vbox.addWidget(widget)

        else:
            raise ValueError('Unsupported parameter type: ' + str(ptype))

        meta['widget'] = widget

        tooltip = _build_tooltip(self._authored, param, eff, unit)
        if tooltip:
            widget.setToolTip(tooltip)

        help_text = (param.get('help') or '').strip()
        if help_text:
            help_label = _WrappedLabel(help_text, container)
            help_label.setContentsMargins(0, 1, 0, 2)
            _apply_muted_style(help_label, smaller=True)
            vbox.addWidget(help_label)
            meta['help_label'] = help_label

        error_label = _WrappedLabel('', container)
        error_label.setStyleSheet('color: #b3261e;')
        error_label.hide()
        vbox.addWidget(error_label)
        meta['error_label'] = error_label

        if meta['kind'] == 'checkbox':
            label_widget = QLabel('', parent_host)
        else:
            label_widget = QLabel(_field_caption(param, has_default), parent_host)
            label_widget.setTextFormat(Qt.PlainText)
            label_widget.setAlignment(Qt.AlignRight | Qt.AlignTop)
            label_widget.setContentsMargins(0, 4, 0, 0)
            label_widget.setBuddy(widget)
            if tooltip:
                label_widget.setToolTip(tooltip)
        meta['label_widget'] = label_widget

        target_form.addRow(label_widget, container)
        self._rows[pid] = meta

    def _on_text_changed(self, pid, value):
        if self._populating:
            return
        param = self._params_by_id[pid]
        has_default = 'default' in param or 'default_source' in param
        if value == '' and not has_default:
            self._entered.pop(pid, None)
        else:
            self._entered[pid] = value
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _on_spin_changed(self, pid, value, unset_sentinel):
        if self._populating:
            return
        if value == unset_sentinel:
            self._entered.pop(pid, None)
        else:
            self._entered[pid] = int(value)
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _on_numeric_text_changed(self, pid, raw_text):
        if self._populating:
            return
        stripped = raw_text.strip()
        if not stripped:
            self._entered.pop(pid, None)
            self._parse_errors.pop(pid, None)
            self._refresh_evaluation(emit=True)
            return
        param = self._params_by_id[pid]
        if param['type'] == 'integer':
            try:
                parsed = int(stripped)
            except ValueError:
                self._entered.pop(pid, None)
                self._parse_errors[pid] = 'Enter a whole number.'
                self._refresh_evaluation(emit=True)
                return
        else:
            try:
                parsed = float(stripped)
            except ValueError:
                self._entered.pop(pid, None)
                self._parse_errors[pid] = 'Enter a valid number.'
                self._refresh_evaluation(emit=True)
                return
            if not math.isfinite(parsed):
                self._entered.pop(pid, None)
                self._parse_errors[pid] = 'Enter a valid number.'
                self._refresh_evaluation(emit=True)
                return
        self._entered[pid] = parsed
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _on_bool_changed(self, pid, checked):
        if self._populating:
            return
        self._entered[pid] = bool(checked)
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _on_combo_changed(self, pid, data):
        if self._populating:
            return
        if data is _UNSET:
            self._entered.pop(pid, None)
        else:
            self._entered[pid] = data
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _on_datetime_changed(self, pid, value):
        if self._populating:
            return
        if not value:
            self._entered.pop(pid, None)
        else:
            self._entered[pid] = value
        self._parse_errors.pop(pid, None)
        self._refresh_evaluation(emit=True)

    def _widget_is_empty(self, meta):
        widget = meta['widget']
        kind = meta['kind']
        if kind == 'text':
            return widget.text() == ''
        if kind == 'spinbox':
            return widget.value() == meta['unset_sentinel']
        if kind == 'numeric_text':
            return widget.text().strip() == ''
        if kind in ('bool_combo', 'choice'):
            return widget.currentData() is _UNSET
        if kind == 'capture_datetime':
            return widget.date.edit.text().strip() == ''
        if kind == 'watermark_image':
            return widget.value().strip() == ''
        return False

    def _refresh_evaluation(self, *, emit):
        if self._authored is None:
            return
        state = evaluate_parameters(
            self._authored,
            self._entered,
            validated=True,
            constraints=self._constraints,
        )
        active_ids = {p['id'] for p in state['active']}
        merged_errors = dict(state['errors'])
        component_errors = {}

        for pid, err in self._parse_errors.items():
            if pid in active_ids:
                merged_errors[pid] = err

        for pid in active_ids:
            eff = self._constraints.get(pid, {})
            if eff.get('single_component') and pid not in merged_errors:
                val = state['values'].get(pid)
                if isinstance(val, str) and val:
                    comp_err = _check_single_component_text(val)
                    if comp_err:
                        merged_errors[pid] = comp_err
                        component_errors[pid] = comp_err

        state['errors'] = merged_errors
        self._evaluation = state

        for pid, meta in self._rows.items():
            visible = pid in active_ids
            if (
                visible
                and pid not in self._entered
                and pid not in self._parse_errors
                and pid in state['values']
            ):
                self._sync_default_widget(pid, meta, state['values'][pid])
            meta['form_layout'].setRowVisible(meta['container'], visible)

            visible_err = ''
            if visible and pid in merged_errors:
                raw_err = merged_errors[pid]
                if pid in self._parse_errors or pid in component_errors:
                    visible_err = raw_err
                elif self._widget_is_empty(meta) and _is_missing_required_error(raw_err):
                    # Untouched or cleared-to-empty required fields remain neutral.
                    visible_err = ''
                else:
                    visible_err = _format_inline_error(
                        self._params_by_id[pid],
                        raw_err,
                        eff=meta['eff'],
                        unit=meta['unit'],
                    )
            meta['error_label'].setText(visible_err)
            meta['error_label'].setVisible(bool(visible_err))

        has_main = any(not p.get('advanced', False) for p in state['active'])
        self._main_host.setVisible(has_main)

        active_adv_ids = [p['id'] for p in state['active'] if p.get('advanced', False)]
        has_adv = bool(active_adv_ids)
        self._advanced_toggle.setVisible(has_adv)
        if not has_adv:
            self._advanced_panel.setVisible(False)
        else:
            adv_needs_attention = any(pid in merged_errors for pid in active_adv_ids)
            if adv_needs_attention:
                self._advanced_toggle.blockSignals(True)
                self._advanced_toggle.setChecked(True)
                self._advanced_toggle.setArrowType(Qt.DownArrow)
                self._advanced_toggle.blockSignals(False)
                self._advanced_panel.setVisible(True)
            else:
                expanded = self._user_expanded_advanced
                self._advanced_toggle.blockSignals(True)
                self._advanced_toggle.setChecked(expanded)
                self._advanced_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
                self._advanced_toggle.blockSignals(False)
                self._advanced_panel.setVisible(expanded)

        self._invalidate_wrapped_layouts()

        if emit:
            self.changed.emit()

    def _invalidate_wrapped_layouts(self):
        for meta in self._rows.values():
            for key in ('help_label', 'error_label'):
                lbl = meta.get(key)
                if lbl is not None:
                    lbl.updateGeometry()
            meta['container'].updateGeometry()
        self._form.invalidate()
        self._advanced_form.invalidate()
        self._main_host.updateGeometry()
        self._advanced_panel.updateGeometry()
        self._outer.invalidate()
        self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._invalidate_wrapped_layouts()

    def _sync_default_widget(self, pid, meta, val):
        """Sync an untouched widget to a newly resolved Settings/default value."""
        widget = meta['widget']
        kind = meta['kind']
        self._populating = True
        try:
            if kind == 'text' and not widget.text() and isinstance(val, str) and val:
                widget.setText(val)
            elif kind == 'spinbox' and widget.value() == meta['unset_sentinel'] and type(val) is int:
                widget.setValue(val)
            elif kind == 'numeric_text' and not widget.text():
                widget.setText(str(val))
            elif kind == 'checkbox' and widget.isChecked() != bool(val):
                widget.setChecked(bool(val))
            elif kind in ('bool_combo', 'choice') and widget.currentData() is _UNSET:
                found = widget.findData(val)
                if found >= 0:
                    widget.setCurrentIndex(found)
        finally:
            self._populating = False

    def entered_values(self):
        """Return a copy of all user-entered values (including hidden fields)."""
        return copy.deepcopy(self._entered)

    def active_values(self):
        """Return only currently active, user-entered values for strict compilation."""
        active_ids = {p['id'] for p in self._evaluation['active']}
        return {
            pid: copy.deepcopy(val)
            for pid, val in self._entered.items()
            if pid in active_ids and pid not in self._parse_errors
        }

    def invalid_input_ids(self):
        """Return parameter IDs that currently have unparseable text input."""
        return set(self._parse_errors)

    def evaluation(self):
        """Return the latest interactive evaluation dict."""
        return copy.deepcopy(self._evaluation)

    def has_errors(self):
        return bool(self._evaluation.get('errors'))

    def has_visible_errors(self):
        return any(
            bool(meta['error_label'].text())
            for meta in self._rows.values()
            if meta['container'].isVisibleTo(self)
        )

    def field_widget(self, pid):
        """Return the underlying Qt control for a parameter id."""
        return self._rows[pid]['widget']

    def field_label(self, pid):
        """Return the left-column label widget for a parameter id."""
        return self._rows[pid]['label_widget']

    def row_visible(self, pid):
        meta = self._rows[pid]
        if meta.get('advanced'):
            return meta['container'].isVisibleTo(self._advanced_panel) and self._advanced_panel.isVisibleTo(self)
        return meta['container'].isVisibleTo(self._main_host) and self._main_host.isVisibleTo(self)

    def field_error(self, pid):
        return self._rows[pid]['error_label'].text()

    def _focus_meta(self, meta):
        widget = meta['widget']
        if meta['kind'] == 'capture_datetime':
            widget.date.edit.setFocus()
            return widget.date.edit
        if meta['kind'] == 'watermark_image':
            widget.choose_button.setFocus()
            return widget.choose_button
        widget.setFocus()
        return widget

    def focus_first_required(self):
        """Focus the first active required parameter without a value, if any."""
        values = self._evaluation.get('values', {})
        for param in self._evaluation.get('active', ()):
            pid = param['id']
            if param.get('required', False) and pid not in values:
                meta = self._rows.get(pid)
                if meta is not None:
                    if meta.get('advanced') and not self.is_advanced_expanded():
                        self.set_advanced_expanded(True, user=False)
                    return self._focus_meta(meta)
        return None

    def focus_first_control(self):
        """Focus the first active control (fallback when returning via Back)."""
        for param in self._evaluation.get('active', ()):
            meta = self._rows.get(param['id'])
            if meta is not None:
                return self._focus_meta(meta)
        return None

    def reset_to_defaults(self):
        """Clear user overrides and restore declared/Settings defaults."""
        if self._authored is None:
            return
        self._entered = {}
        self._parse_errors = {}
        defaults_state = evaluate_parameters(
            self._authored,
            {},
            validated=True,
            constraints=self._constraints,
        )
        defaults = defaults_state['values']

        self._populating = True
        try:
            for pid, meta in self._rows.items():
                widget = meta['widget']
                kind = meta['kind']
                param = self._params_by_id[pid]
                if pid in defaults:
                    val = defaults[pid]
                elif 'default' in param:
                    val = param['default']
                else:
                    val = _UNSET
                if kind == 'text':
                    widget.setText(val if isinstance(val, str) else '')
                elif kind == 'spinbox':
                    if val is not _UNSET and type(val) is int:
                        widget.setValue(val)
                    else:
                        widget.setValue(meta['unset_sentinel'])
                elif kind == 'numeric_text':
                    widget.setText('' if val is _UNSET else str(val))
                elif kind == 'checkbox':
                    widget.setChecked(bool(val) if val is not _UNSET else False)
                elif kind in ('bool_combo', 'choice'):
                    if val is _UNSET:
                        widget.setCurrentIndex(0)
                    else:
                        found = widget.findData(val)
                        widget.setCurrentIndex(found if found >= 0 else 0)
                elif kind == 'capture_datetime':
                    if isinstance(val, str) and val:
                        parts = val.replace('T', ' ').split(' ', 1)
                        if len(parts) == 2:
                            from PySide6.QtCore import QDate, QTime
                            widget.date.setDate(QDate.fromString(parts[0], 'yyyy-MM-dd'))
                            clock = QTime.fromString(parts[1].split('.', 1)[0], 'HH:mm:ss')
                            if clock.isValid():
                                widget.time.setTime(clock)
                    else:
                        widget.date.clear()
                elif kind == 'watermark_image':
                    widget.set_path(val if isinstance(val, str) else '', emit=False)
        finally:
            self._populating = False

        self._refresh_evaluation(emit=True)


class RecipeSettingsPage(QWidget):
    """Scrollable contextual Settings page hosted in RunRecipeDialog.review_stack."""

    changed = Signal()
    clear_remembered_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._example_source = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel('Recipe settings', self)
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch(1)

        self.clear_remembered_button = QPushButton(
            QIcon.fromTheme('edit-clear'),
            'Clear remembered',
            self,
        )
        self.clear_remembered_button.setToolTip(
            'Clear remembered answers saved for this Recipe and restore defaults'
        )
        self.clear_remembered_button.hide()
        self.clear_remembered_button.clicked.connect(self.clear_remembered_requested.emit)
        header.addWidget(self.clear_remembered_button)

        self.reset_button = QPushButton(
            QIcon.fromTheme('edit-undo'),
            'Reset to defaults',
            self,
        )
        self.reset_button.setToolTip(
            'Reset these run settings to their authored defaults'
        )
        self.reset_button.setEnabled(False)
        header.addWidget(self.reset_button)
        layout.addLayout(header)

        subtitle = QLabel(
            'Adjust the settings for this run. Your saved Recipe will not change.',
            self,
        )
        subtitle.setWordWrap(True)
        subtitle.setTextFormat(Qt.PlainText)
        layout.addWidget(subtitle)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        scroll_host = QWidget()
        host_layout = QVBoxLayout(scroll_host)
        host_layout.setContentsMargins(0, 4, 6, 4)
        host_layout.setSpacing(12)

        self.form = ParameterFormWidget(scroll_host)
        host_layout.addWidget(self.form)

        self.example_group = QGroupBox('Example output', scroll_host)
        self.example_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        ex_layout = QVBoxLayout(self.example_group)
        ex_layout.setContentsMargins(10, 8, 10, 8)
        ex_layout.setSpacing(4)

        self.example_prompt = QLabel('', self.example_group)
        self.example_prompt.setTextFormat(Qt.PlainText)
        self.example_prompt.setWordWrap(True)
        _apply_muted_style(self.example_prompt, smaller=False)
        ex_layout.addWidget(self.example_prompt)

        self.example_fields_widget = QWidget(self.example_group)
        self.example_fields = QFormLayout(self.example_fields_widget)
        self.example_fields.setContentsMargins(0, 0, 0, 0)
        self.example_fields.setHorizontalSpacing(10)
        self.example_fields.setVerticalSpacing(3)
        self.example_fields.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)

        self.example_filename = QLabel('', self.example_fields_widget)
        self.example_filename.setTextFormat(Qt.PlainText)
        self.example_filename.setWordWrap(True)
        self.example_filename.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.example_fields.addRow('Filename:', self.example_filename)

        self.example_subfolder = QLabel('', self.example_fields_widget)
        self.example_subfolder.setTextFormat(Qt.PlainText)
        self.example_subfolder.setWordWrap(True)
        self.example_subfolder.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.example_fields.addRow('Output subfolder:', self.example_subfolder)
        ex_layout.addWidget(self.example_fields_widget)

        self.example_qualification = QLabel(
            'Example only. Exact output paths are confirmed during Review Changes.',
            self.example_group,
        )
        self.example_qualification.setTextFormat(Qt.PlainText)
        self.example_qualification.setWordWrap(True)
        _apply_muted_style(self.example_qualification, smaller=True)
        ex_layout.addWidget(self.example_qualification)

        self.example_group.hide()
        host_layout.addWidget(self.example_group)
        host_layout.addStretch(1)

        self.scroll.setWidget(scroll_host)
        layout.addWidget(self.scroll, 1)

        self.diagnostic = QLabel('', self)
        self.diagnostic.setTextFormat(Qt.PlainText)
        self.diagnostic.setWordWrap(True)
        self.diagnostic.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.diagnostic.setStyleSheet('color: #b3261e;')
        self.diagnostic.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Maximum
        )
        self.diagnostic.hide()
        layout.addWidget(self.diagnostic)

        self.reset_button.clicked.connect(self.form.reset_to_defaults)
        self.form.changed.connect(self._on_form_changed)

    def _sync_reset_state(self):
        self.reset_button.setEnabled(not self.form.is_at_defaults())

    def _refresh_example_output(self):
        authored = self.form._authored
        if authored is None or not has_parameterized_output_templates(authored):
            self.example_group.hide()
            return

        result = preview_output_example(
            authored,
            self.form.entered_values(),
            source_name=self._example_source,
            validated=True,
            constraints=self.form._constraints,
            invalid_ids=self.form.invalid_input_ids(),
        )
        if not result['available']:
            self.example_group.hide()
            return

        self.example_group.show()
        if not result['complete']:
            self.example_fields_widget.hide()
            self.example_filename.setText('')
            self.example_subfolder.setText('')
            self.example_prompt.setText(result['prompt'])
            self.example_prompt.show()
            return

        has_filename = bool(result['filename'])
        has_subfolder = result['subfolder'] is not None
        self.example_filename.setText(result['filename'] or '')
        self.example_subfolder.setText(result['subfolder'] or '')
        self.example_fields.setRowVisible(self.example_filename, has_filename)
        self.example_fields.setRowVisible(self.example_subfolder, has_subfolder)
        self.example_fields_widget.setVisible(has_filename or has_subfolder)

        note = result['note']
        self.example_prompt.setText(note)
        self.example_prompt.setVisible(bool(note))

    def _on_form_changed(self):
        self.set_diagnostic('')
        self._sync_reset_state()
        self._refresh_example_output()
        self.changed.emit()

    def set_recipe(self, recipe, entered_values=None):
        self.set_diagnostic('')
        self.form.set_recipe(recipe, entered_values=entered_values)
        self._sync_reset_state()
        self._refresh_example_output()

    def set_example_source(self, source_name):
        """Update the example filename using the currently selected queue image."""
        self._example_source = source_name
        self._refresh_example_output()

    def set_has_remembered(self, has_remembered):
        self.clear_remembered_button.setVisible(bool(has_remembered))

    def set_diagnostic(self, message):
        text = str(message or '').strip()
        self.diagnostic.setText(text)
        self.diagnostic.setVisible(bool(text))

    def focus_first_required(self):
        return self.form.focus_first_required()

    def focus_first_control(self):
        return self.form.focus_first_control()

    def entered_values(self):
        return self.form.entered_values()

    def active_values(self):
        return self.form.active_values()

    def has_errors(self):
        return self.form.has_errors()


class PreviewSettingsDialog(QDialog):
    """Modal Preview Settings dialog reusing ParameterFormWidget in Recipe Editor."""

    def __init__(self, recipe, entered_values=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('KIMng - Preview Settings')
        self.resize(560, 460)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel('Preview settings', self)
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch(1)

        self.reset_button = QPushButton(
            QIcon.fromTheme('edit-undo'),
            'Reset to defaults',
            self,
        )
        self.reset_button.setToolTip(
            'Reset preview answers to the Recipe defaults'
        )
        header.addWidget(self.reset_button)
        layout.addLayout(header)

        intro = _WrappedLabel(
            'Try example answers to see what this Recipe will produce. '
            'Authored defaults and the saved Recipe are not changed.',
            self,
        )
        layout.addWidget(intro)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        scroll_host = QWidget()
        host_layout = QVBoxLayout(scroll_host)
        host_layout.setContentsMargins(0, 4, 6, 4)
        self.form = ParameterFormWidget(scroll_host)
        host_layout.addWidget(self.form)
        host_layout.addStretch(1)
        self.scroll.setWidget(scroll_host)
        layout.addWidget(self.scroll, 1)

        self.status_label = _WrappedLabel('', self)
        _apply_muted_style(self.status_label, smaller=True)
        layout.addWidget(self.status_label)

        from kim_dialog_buttons import style_button_box
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        style_button_box(self.buttons)
        self.apply_button = self.buttons.button(QDialogButtonBox.Ok)
        self.apply_button.setText('Update Preview')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.reset_button.clicked.connect(self.form.reset_to_defaults)
        self.form.changed.connect(self._sync_state)

        self.form.set_recipe(recipe, entered_values=entered_values)
        self._sync_state()
        QTimer.singleShot(0, self.form.focus_first_required)

    def _sync_state(self):
        self.reset_button.setEnabled(not self.form.is_at_defaults())
        has_bad = self.form.has_visible_errors()
        self.apply_button.setEnabled(not has_bad)
        if has_bad:
            self.status_label.setText('Correct the highlighted example value to continue.')
        elif self.form.has_errors():
            self.status_label.setText(
                'Some required example values are still empty. Complete them to generate a live preview.'
            )
        else:
            self.status_label.setText('All required example values are complete.')

    def entered_values(self):
        return self.form.entered_values()

    def active_values(self):
        return self.form.active_values()
