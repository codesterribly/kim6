"""Headless authored-Recipe parameter validation and concrete snapshot resolution.

Pure Python (no Qt). Compiles an authored parameterized Recipe plus run-time
inputs into a plain concrete Recipe snapshot compatible with kim_recipe_core's
existing planning, approval, verification and atomic publication pipeline.
"""
import copy
import math
from pathlib import Path
import re
import string

from kim_recipe_core import (
    AUTHORED_SCHEMA,
    CONCRETE_SCHEMA,
    SUBFOLDER_DATE_TOKENS,
    RecipeError,
    component,
    format_output_pattern,
    handler,
    keys,
    pattern as validate_output_pattern,
    subfolder_parts,
    text,
    validate as validate_concrete,
)

MAX_PARAMETERS = 32
MAX_CHOICES = 50
MAX_CONDITION_CLAUSES = 8
MAX_TEXT_LIMIT = 500
COMPONENT_TEXT_LIMIT = 180

PARAM_ID_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
PARAMETER_TYPES = (
    'text',
    'integer',
    'number',
    'boolean',
    'choice',
    'capture_datetime',
    'watermark_image',
)
TEMPLATE_PARAM_TYPES = ('text', 'integer', 'choice')
SOURCE_TOKENS = ('filename', 'stem', 'date', 'index')

# Allow-listed KIMng Settings default sources: source_key -> (param_type, field)
SETTINGS_SOURCES = {
    'copyright.creator': ('text', 'creator'),
    'copyright.notice': ('text', 'notice'),
    'copyright.rights': ('text', 'rights'),
    'web.quality.jpeg': ('integer', 'jpeg'),
    'web.quality.webp': ('integer', 'webp'),
    'web.quality.avif': ('integer', 'avif'),
}

# Explicit non-bindable operation keys (structural/internal or template-only).
UNBINDABLE_FIELDS = {
    'image.crop': {'version'},
    'image.overlay': {
        'version', 'text_fields', 'camera_fields', 'kind', 'source',
    },
    'file.rename_output': {'pattern'},
}

# Metadata fields where an empty string safely means "do not write/modify",
# never "clear existing metadata" and never "inherit from Settings".
OPTIONAL_EMPTY_METADATA_FIELDS = {
    ('metadata.copyright', 'creator'),
    ('metadata.copyright', 'notice'),
    ('metadata.copyright', 'rights'),
    ('metadata.copyright', 'year'),
    ('metadata.creator', 'value'),
    ('metadata.copyright_notice', 'value'),
    ('metadata.usage_rights', 'value'),
    ('metadata.set_description', 'value'),
    ('metadata.set_keywords', 'keywords'),
}

OPTIONAL_EMPTY_TEXT_FIELDS = OPTIONAL_EMPTY_METADATA_FIELDS | {
    ('file.name_transform', 'value'),
    ('file.name_transform', 'replacement'),
}

# Text operation fields with tighter limits than kim_recipe_core.text() (500).
BOUND_TEXT_LIMITS = {
    ('file.name_transform', 'value'): COMPONENT_TEXT_LIMIT,
    ('file.name_transform', 'replacement'): COMPONENT_TEXT_LIMIT,
    ('image.overlay', 'font'): 200,
}

_MISSING = object()


def _is_finite_number(value):
    """True for finite int/float, rejecting bool and avoiding OverflowError."""
    if type(value) is bool or type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _scalar_equals(left, right):
    """Compare scalar values without Python's bool/int equality overlap."""
    if (type(left) is bool) != (type(right) is bool):
        return False
    return left == right


def _choice_values(param):
    return tuple(
        item['value'] if isinstance(item, dict) else item
        for item in param['choices']
    )


def _validate_param_value(
    param, value, *, constraints=None, allow_empty_datetime=True
):
    """Validate one concrete value against declaration and effective constraints."""
    if value is None:
        raise RecipeError(f"Parameter '{param['label']}' cannot be null.")
    eff = constraints if constraints is not None else param
    ptype = param['type']

    if ptype == 'text':
        limit = eff.get('max_length', param.get('max_length', MAX_TEXT_LIMIT))
        return text(value, limit)
    if ptype == 'integer':
        if type(value) is not int:
            raise RecipeError(
                f"Parameter '{param['label']}' must be an integer."
            )
        low = eff.get('minimum', param.get('minimum'))
        high = eff.get('maximum', param.get('maximum'))
        if low is not None and value < low:
            raise RecipeError(
                f"Parameter '{param['label']}' must be at least {low}."
            )
        if high is not None and value > high:
            raise RecipeError(
                f"Parameter '{param['label']}' must be at most {high}."
            )
        return value
    if ptype == 'number':
        if not _is_finite_number(value):
            raise RecipeError(
                f"Parameter '{param['label']}' must be a finite number."
            )
        low = eff.get('minimum', param.get('minimum'))
        high = eff.get('maximum', param.get('maximum'))
        if low is not None and value < low:
            raise RecipeError(
                f"Parameter '{param['label']}' must be at least {low}."
            )
        if high is not None and value > high:
            raise RecipeError(
                f"Parameter '{param['label']}' must be at most {high}."
            )
        return value
    if ptype == 'boolean':
        if type(value) is not bool:
            raise RecipeError(
                f"Parameter '{param['label']}' must be true or false."
            )
        return value
    if ptype == 'choice':
        allowed = (
            constraints['choices']
            if constraints is not None and 'choices' in constraints
            else _choice_values(param)
        )
        if not isinstance(value, str) or value not in allowed:
            raise RecipeError(
                f"Parameter '{param['label']}' must be one of its declared choices."
            )
        return value
    if ptype == 'capture_datetime':
        if not isinstance(value, str):
            raise RecipeError(
                f"Parameter '{param['label']}' must be a capture date and time string."
            )
        if value == '':
            if allow_empty_datetime and not param.get('required', False):
                return ''
            raise RecipeError(
                f"Parameter '{param['label']}' requires an image capture date and time."
            )
        from kim_recipe_dates import specific
        specific(value, 'unknown')
        return value
    if ptype == 'watermark_image':
        if (
            not isinstance(value, str)
            or len(value) > 4096
            or any(ord(c) < 32 for c in value)
            or '\x7f' in value
        ):
            raise RecipeError(
                f"Parameter '{param['label']}' must be a valid local watermark image path."
            )
        if value == '':
            if allow_empty_datetime:
                return ''
            raise RecipeError(
                f"Parameter '{param['label']}' requires a local watermark image file."
            )
        if not Path(value).is_absolute():
            raise RecipeError(
                f"Parameter '{param['label']}' must be an absolute local file path."
            )
        return value
    raise RecipeError('Unsupported parameter type: ' + str(ptype))


def _validate_single_condition(cond, allowed_params):
    if not isinstance(cond, dict):
        raise RecipeError('Condition must be an object.')
    keys(cond, ('param',), ('equals', 'in'))
    if ('equals' in cond) == ('in' in cond):
        raise RecipeError(
            'Condition must specify exactly one of equals or in.'
        )
    pid = cond['param']
    if not isinstance(pid, str) or pid not in allowed_params:
        raise RecipeError(
            'Condition references unknown or unavailable parameter: ' + str(pid)
        )
    target = allowed_params[pid]
    if target['type'] == 'watermark_image':
        raise RecipeError('Watermark image parameters cannot be used in conditions.')
    if 'equals' in cond:
        _validate_param_value(target, cond['equals'], allow_empty_datetime=False)
    else:
        options = cond['in']
        if not isinstance(options, list) or not 1 <= len(options) <= MAX_CHOICES:
            raise RecipeError(
                f'Condition membership list must contain 1–{MAX_CHOICES} values.'
            )
        for option in options:
            _validate_param_value(target, option, allow_empty_datetime=False)


def _validate_condition(cond, allowed_params):
    if not isinstance(cond, dict):
        raise RecipeError('Condition must be an object.')
    if 'all' in cond:
        keys(cond, ('all',))
        clauses = cond['all']
        if not isinstance(clauses, list) or not 1 <= len(clauses) <= MAX_CONDITION_CLAUSES:
            raise RecipeError(
                f'Condition all-list must contain 1–{MAX_CONDITION_CLAUSES} predicates.'
            )
        for clause in clauses:
            _validate_single_condition(clause, allowed_params)
    else:
        _validate_single_condition(cond, allowed_params)


def _condition_predicates(cond):
    if cond is None:
        return ()
    return tuple(cond['all']) if 'all' in cond else (cond,)


def _predicate_values(pred):
    return (pred['equals'],) if 'equals' in pred else tuple(pred['in'])


def _intersect_allowed(existing, incoming):
    return tuple(
        item for item in existing
        if any(_scalar_equals(item, other) for other in incoming)
    )


def _effective_clauses(cond, params_by_id):
    """Expand a condition together with ancestor parameter visibility guards.

    Returns dict[param_id, tuple[allowed_values]], or None if unsatisfiable.
    """
    if cond is None:
        return {}
    constraints = {}
    queue = list(_condition_predicates(cond))
    visited_params = set()
    while queue:
        pred = queue.pop(0)
        pid = pred['param']
        allowed = _predicate_values(pred)
        if pid in constraints:
            merged = _intersect_allowed(constraints[pid], allowed)
            if not merged:
                return None
            constraints[pid] = merged
        else:
            constraints[pid] = allowed
        if pid not in visited_params:
            visited_params.add(pid)
            parent_cond = params_by_id[pid].get('visible_when')
            if parent_cond is not None:
                queue.extend(_condition_predicates(parent_cond))
    return constraints


def _conditions_disjoint(clauses_a, clauses_b):
    if clauses_a is None or clauses_b is None:
        return True
    for pid, allowed_a in clauses_a.items():
        if pid in clauses_b and not _intersect_allowed(allowed_a, clauses_b[pid]):
            return True
    return False


def _clauses_imply(stronger, weaker):
    if not weaker or stronger is None:
        return True
    for pid, allowed_weak in weaker.items():
        if pid not in stronger:
            return False
        for value in stronger[pid]:
            if not any(_scalar_equals(value, target) for target in allowed_weak):
                return False
    return True


def _validate_numeric_bound(pid, ptype, bound, value):
    if ptype == 'integer':
        if type(value) is not int:
            raise RecipeError(f"Parameter '{pid}' {bound} must be an integer.")
    else:
        if not _is_finite_number(value):
            raise RecipeError(f"Parameter '{pid}' {bound} must be a finite number.")


def _validate_parameter(item, prior_params):
    if not isinstance(item, dict):
        raise RecipeError('Parameter declaration must be an object.')
    keys(
        item,
        ('id', 'label', 'type'),
        (
            'help', 'required', 'default', 'default_source',
            'minimum', 'maximum', 'max_length', 'choices',
            'visible_when', 'remember', 'advanced',
        ),
    )
    pid = item['id']
    if not isinstance(pid, str) or not PARAM_ID_RE.fullmatch(pid):
        raise RecipeError('Invalid parameter id: ' + str(pid))
    if pid in prior_params:
        raise RecipeError('Duplicate parameter id: ' + pid)
    if not text(item['label'], 100).strip():
        raise RecipeError(f"Parameter '{pid}' requires a non-empty label.")
    if 'help' in item:
        text(item['help'], MAX_TEXT_LIMIT)

    ptype = item['type']
    if not isinstance(ptype, str) or ptype not in PARAMETER_TYPES:
        raise RecipeError(f"Unsupported parameter type for '{pid}': {ptype}")

    for flag in ('required', 'remember', 'advanced'):
        if flag in item and type(item[flag]) is not bool:
            raise RecipeError(f"Parameter '{pid}' {flag} must be boolean.")

    if 'default' in item and 'default_source' in item:
        raise RecipeError(
            f"Parameter '{pid}' cannot specify both default and default_source."
        )

    if 'max_length' in item:
        if ptype != 'text':
            raise RecipeError(f"Parameter '{pid}' max_length is only valid for text.")
        if type(item['max_length']) is not int or not 1 <= item['max_length'] <= MAX_TEXT_LIMIT:
            raise RecipeError(
                f"Parameter '{pid}' max_length must be an integer 1–{MAX_TEXT_LIMIT}."
            )

    if 'minimum' in item or 'maximum' in item:
        if ptype not in ('integer', 'number'):
            raise RecipeError(
                f"Parameter '{pid}' minimum/maximum are only valid for numeric types."
            )
        for bound in ('minimum', 'maximum'):
            if bound in item:
                _validate_numeric_bound(pid, ptype, bound, item[bound])
        if 'minimum' in item and 'maximum' in item and item['minimum'] > item['maximum']:
            raise RecipeError(
                f"Parameter '{pid}' minimum cannot exceed maximum."
            )

    if ptype == 'choice':
        if 'choices' not in item:
            raise RecipeError(f"Choice parameter '{pid}' requires a choices list.")
        choices = item['choices']
        if not isinstance(choices, list) or not 1 <= len(choices) <= MAX_CHOICES:
            raise RecipeError(
                f"Choice parameter '{pid}' must declare 1–{MAX_CHOICES} choices."
            )
        seen_choices = set()
        for choice in choices:
            if isinstance(choice, str):
                value = text(choice, COMPONENT_TEXT_LIMIT)
                if not value:
                    raise RecipeError(f"Choice parameter '{pid}' cannot have an empty choice.")
            elif isinstance(choice, dict):
                keys(choice, ('value', 'label'))
                value = text(choice['value'], COMPONENT_TEXT_LIMIT)
                label = text(choice['label'], COMPONENT_TEXT_LIMIT)
                if not value or not label.strip():
                    raise RecipeError(
                        f"Choice parameter '{pid}' entries require non-empty value and label."
                    )
            else:
                raise RecipeError(f"Invalid choice entry in parameter '{pid}'.")
            if value in seen_choices:
                raise RecipeError(f"Duplicate choice '{value}' in parameter '{pid}'.")
            seen_choices.add(value)
    elif 'choices' in item:
        raise RecipeError(f"Parameter '{pid}' choices is only valid for choice type.")

    if 'default_source' in item:
        source = item['default_source']
        if not isinstance(source, str) or source not in SETTINGS_SOURCES:
            raise RecipeError(
                f"Parameter '{pid}' references unsupported Settings source: {source}"
            )
        expected_type, _ = SETTINGS_SOURCES[source]
        if ptype != expected_type:
            raise RecipeError(
                f"Parameter '{pid}' type '{ptype}' is incompatible with Settings source '{source}'."
            )
        if expected_type == 'integer':
            low = item.get('minimum', 1)
            high = item.get('maximum', 100)
            if low > 100 or high < 1:
                raise RecipeError(
                    f"Parameter '{pid}' bounds cannot accept Settings quality 1–100."
                )

    if 'default' in item:
        _validate_param_value(item, item['default'])
        if (
            item.get('required', False)
            and ptype in ('text', 'capture_datetime')
            and not item['default'].strip()
        ):
            raise RecipeError(
                f"Required parameter '{pid}' cannot use an empty default."
            )
        if ptype == 'watermark_image' and item['default'] != '':
            raise RecipeError(
                f"Watermark image parameter '{pid}' cannot store a hardcoded default path."
            )

    if 'visible_when' in item:
        _validate_condition(item['visible_when'], prior_params)
        if _effective_clauses(item['visible_when'], prior_params) is None:
            raise RecipeError(
                f"Parameter '{pid}' has an unsatisfiable visibility condition."
            )


def parse_template(value, *, allow_source_tokens, allow_date_tokens=False):
    """Parse a filename or subfolder template into literal, source, date, and param tokens.

    Rejects arbitrary Python format specs, conversions, attribute access, and
    indexing. Only {param:<id>}, (when allowed) {filename}/{stem}/{date}/{index},
    and (when allowed) {year}/{capture_date} are accepted.
    """
    text(value, MAX_TEXT_LIMIT)
    tokens = []
    try:
        parsed = list(string.Formatter().parse(value))
    except ValueError as exc:
        raise RecipeError('Invalid template syntax.') from exc

    for literal_text, field_name, format_spec, conversion in parsed:
        if literal_text:
            tokens.append(('literal', literal_text))
        if field_name is None:
            continue
        if conversion is not None:
            raise RecipeError('Template conversions are not allowed.')
        if field_name == 'param':
            if not format_spec or not PARAM_ID_RE.fullmatch(format_spec):
                raise RecipeError(
                    'Invalid parameter template reference: {param:' + str(format_spec) + '}'
                )
            tokens.append(('param', format_spec))
        elif allow_source_tokens and field_name in SOURCE_TOKENS:
            if format_spec:
                raise RecipeError(
                    'Template format specifiers are not allowed on {' + field_name + '}.'
                )
            tokens.append(('source', field_name))
        elif allow_date_tokens and field_name in SUBFOLDER_DATE_TOKENS:
            if format_spec:
                raise RecipeError(
                    'Template format specifiers are not allowed on {' + field_name + '}.'
                )
            tokens.append(('date', field_name))
        else:
            raise RecipeError('Unsupported template token: {' + str(field_name) + '}')
    return tokens


def has_parameter_references(value):
    """Return True if a string contains a {param:...} template reference."""
    return isinstance(value, str) and '{param:' in value


def _format_template_value(param, value):
    if value is _MISSING:
        return ''
    return str(value) if param['type'] == 'integer' else value


def _check_template_piece(value, label):
    if '/' in value or '\\' in value or any(ord(c) < 32 for c in value):
        raise RecipeError(
            f"Parameter '{label}' cannot contain path separators or control characters."
        )


def _render_template(template, params_by_id, resolved_values, *, allow_source_tokens):
    """Render {param:<id>} references once, escaping braces for filename patterns."""
    tokens = parse_template(template, allow_source_tokens=allow_source_tokens)
    parts = []
    for kind, content in tokens:
        if kind == 'literal':
            parts.append(
                content.replace('{', '{{').replace('}', '}}')
                if allow_source_tokens else content
            )
        elif kind == 'source':
            parts.append('{' + content + '}')
        else:
            param = params_by_id[content]
            piece = _format_template_value(param, resolved_values[content])
            _check_template_piece(piece, param['label'])
            parts.append(
                piece.replace('{', '{{').replace('}', '}}')
                if allow_source_tokens else piece
            )
    rendered = ''.join(parts)
    if allow_source_tokens:
        validate_output_pattern(rendered)
        return rendered
    return component(rendered)


def _render_subfolder_template(template, params_by_id, resolved_values):
    """Render a single- or multi-component relative subfolder template safely.

    Optional segments consisting solely of {param:<id>} are omitted when empty/unset.
    Every parameter value is checked to prevent path separators, traversal, or control chars.
    """
    text(template, MAX_TEXT_LIMIT)
    if not template or template.startswith('/') or template.endswith('/') or '\\' in template:
        raise RecipeError('Expected a safe relative subfolder path')
    raw_segments = template.split('/')
    if not 1 <= len(raw_segments) <= 8:
        raise RecipeError('Subfolder path must have 1 to 8 directory levels')
    rendered_segments = []
    for seg in raw_segments:
        if not seg or seg in ('.', '..'):
            raise RecipeError('Expected a safe relative subfolder path')
        tokens = parse_template(seg, allow_source_tokens=False, allow_date_tokens=True)
        if len(tokens) == 1 and tokens[0][0] == 'param':
            pid = tokens[0][1]
            param = params_by_id[pid]
            val = resolved_values.get(pid, _MISSING)
            if (val is _MISSING or val == '') and not param.get('required', False):
                continue
        parts = []
        for kind, content in tokens:
            if kind == 'literal':
                parts.append(content)
            elif kind == 'date':
                parts.append('{' + content + '}')
            else:
                param = params_by_id[content]
                piece = _format_template_value(param, resolved_values.get(content, _MISSING))
                _check_template_piece(piece, param['label'])
                parts.append(piece)
        rendered_segments.append(''.join(parts))
    if not rendered_segments:
        raise RecipeError('Expected a safe relative subfolder path')
    result = '/'.join(rendered_segments)
    subfolder_parts(result, allow_date_tokens=True)
    return result


def _validate_template_refs(
    template,
    params_by_id,
    param_clauses,
    *,
    allow_source_tokens,
    allow_date_tokens=False,
    context_label,
    step_clauses=None,
    statically_disabled=False,
):
    """Validate parameter references inside a filename or subfolder template."""
    tokens = parse_template(
        template,
        allow_source_tokens=allow_source_tokens,
        allow_date_tokens=allow_date_tokens,
    )
    referenced = []
    for kind, content in tokens:
        if kind != 'param':
            continue
        if content not in params_by_id:
            raise RecipeError(
                f'{context_label} references unknown parameter: {content}'
            )
        param = params_by_id[content]
        if param['type'] not in TEMPLATE_PARAM_TYPES:
            raise RecipeError(
                f"{context_label} parameter '{content}' must be text, integer, or choice."
            )
        if not statically_disabled and param.get('visible_when') is not None:
            if step_clauses is None or not _clauses_imply(step_clauses, param_clauses[content]):
                raise RecipeError(
                    f"{context_label} cannot reference conditional parameter '{content}'"
                    + ('' if step_clauses is None else ' without a matching enabled_when condition')
                    + '.'
                )
        referenced.append(content)
    return referenced


def _template_probe_value(param, eff):
    """Derive a minimal template probe value from declared/effective constraints."""
    if 'default' in param:
        return param['default']
    ptype = param['type']
    if ptype == 'choice':
        return eff['choices'][0]
    if ptype == 'integer':
        low = eff.get('minimum')
        high = eff.get('maximum')
        if low is not None:
            return low
        if high is not None:
            return min(1, high)
        return 1
    return 'a'


def _check_field_compatibility(op, field, spec, param, step):
    """Validate parameter type/bounds compatibility against operation_definitions()."""
    ptype = param['type']
    stype = spec['type']

    if op == 'image.overlay' and field == 'logo':
        if step.get('kind') != 'image':
            raise RecipeError(
                "Binding 'logo' on 'image.overlay' requires kind='image'."
            )
        if ptype != 'watermark_image':
            raise RecipeError(
                "Field 'image.overlay.logo' requires a watermark_image parameter, not "
                + repr(ptype) + '.'
            )
        return
    if ptype == 'watermark_image':
        raise RecipeError(
            "Watermark image parameters can only bind to 'image.overlay.logo'."
        )

    if op == 'image.overlay' and field == 'value':
        kind = step.get('kind')
        if kind == 'text':
            if step.get('text_fields') is None and step.get('source') != 'custom':
                raise RecipeError(
                    "Binding 'value' on a text overlay requires custom text or text_fields."
                )
        elif kind == 'caption':
            if step.get('source') != 'custom':
                raise RecipeError(
                    "Binding 'value' on a caption overlay requires source='custom'."
                )
        else:
            raise RecipeError(
                f"Operation 'image.overlay' with kind='{kind}' does not support binding 'value'."
            )

    if stype == 'boolean':
        if ptype != 'boolean':
            raise RecipeError(
                f"Field '{op}.{field}' requires a boolean parameter, not '{ptype}'."
            )
    elif stype in ('integer', 'number'):
        allowed_types = ('integer',) if stype == 'integer' else ('number', 'integer')
        if ptype not in allowed_types:
            expected = 'an integer' if stype == 'integer' else 'a numeric'
            raise RecipeError(
                f"Field '{op}.{field}' requires {expected} parameter, not '{ptype}'."
            )
        if 'minimum' in param and 'minimum' in spec and param['minimum'] < spec['minimum']:
            raise RecipeError(
                f"Parameter '{param['id']}' minimum {param['minimum']} is below "
                f"'{op}.{field}' minimum {spec['minimum']}."
            )
        if 'maximum' in param and 'maximum' in spec and param['maximum'] > spec['maximum']:
            raise RecipeError(
                f"Parameter '{param['id']}' maximum {param['maximum']} exceeds "
                f"'{op}.{field}' maximum {spec['maximum']}."
            )
    elif stype == 'capture_datetime':
        if ptype != 'capture_datetime':
            raise RecipeError(
                f"Field '{op}.{field}' requires a capture_datetime parameter, not '{ptype}'."
            )
    elif stype == 'text':
        if 'choices' in spec:
            if op == 'metadata.set_capture' and field == 'timezone':
                if ptype not in ('choice', 'text'):
                    raise RecipeError(
                        f"Field '{op}.{field}' requires a choice or text parameter, not '{ptype}'."
                    )
            else:
                if ptype != 'choice':
                    raise RecipeError(
                        f"Field '{op}.{field}' requires a choice parameter, not '{ptype}'."
                    )
                allowed = set(spec['choices'])
                bad = [c for c in _choice_values(param) if c not in allowed]
                if bad:
                    raise RecipeError(
                        f"Parameter '{param['id']}' choice '{bad[0]}' is invalid for '{op}.{field}'."
                    )
        elif ptype not in ('text', 'choice'):
            raise RecipeError(
                f"Field '{op}.{field}' requires a text or choice parameter, not '{ptype}'."
            )
    else:
        raise RecipeError(f"Unsupported operation field type '{stype}' on '{op}.{field}'.")


def _apply_step_field(step, field, value):
    if (
        step['op'] == 'image.overlay'
        and field == 'value'
        and step.get('kind') == 'text'
        and step.get('text_fields') is not None
    ):
        step['text_fields']['custom'] = {
            'selected': bool(value.strip()),
            'value': value,
        }
        step['value'] = value
    else:
        step[field] = value


def _compute_effective_constraints(authored, definitions):
    """Derive effective constraints per parameter from declaration + bound fields."""
    params = authored.get('parameters', [])
    result = {}
    for param in params:
        pid = param['id']
        ptype = param['type']
        eff = {'type': ptype}
        if ptype in ('integer', 'number'):
            if 'minimum' in param:
                eff['minimum'] = param['minimum']
            if 'maximum' in param:
                eff['maximum'] = param['maximum']
        elif ptype == 'text':
            eff['max_length'] = param.get('max_length', MAX_TEXT_LIMIT)
        elif ptype == 'choice':
            eff['choices'] = _choice_values(param)
        result[pid] = eff

    def tighten_numeric(pid, low, high):
        eff = result[pid]
        if low is not None:
            eff['minimum'] = max(eff['minimum'], low) if 'minimum' in eff else low
        if high is not None:
            eff['maximum'] = min(eff['maximum'], high) if 'maximum' in eff else high
        if 'minimum' in eff and 'maximum' in eff and eff['minimum'] > eff['maximum']:
            raise RecipeError(
                f"Parameter '{pid}' has incompatible bound constraints "
                f"(minimum {eff['minimum']} exceeds maximum {eff['maximum']})."
            )

    def tighten_text(pid, limit, *, single_component=False):
        eff = result[pid]
        if eff['type'] == 'text':
            eff['max_length'] = min(eff['max_length'], limit)
        if single_component:
            eff['single_component'] = True

    def tighten_choices(pid, allowed_choices):
        eff = result[pid]
        if eff['type'] != 'choice':
            return
        allowed = set(allowed_choices)
        narrowed = tuple(c for c in eff['choices'] if c in allowed)
        if not narrowed or len(narrowed) != len(eff['choices']):
            raise RecipeError(
                f"Parameter '{pid}' choices are incompatible with its bound operations."
            )
        eff['choices'] = narrowed

    for step in authored.get('steps', ()):
        if step.get('enabled', True) is False:
            continue
        op = step['op']
        op_params = definitions[op]['parameters']
        bindings = step.get('bindings')
        if bindings:
            for field, pid in bindings.items():
                spec = op_params[field]
                stype = spec['type']
                if stype in ('integer', 'number'):
                    tighten_numeric(pid, spec.get('minimum'), spec.get('maximum'))
                elif stype == 'text':
                    if 'choices' in spec and not (op == 'metadata.set_capture' and field == 'timezone'):
                        tighten_choices(pid, spec['choices'])
                    if (op, field) in BOUND_TEXT_LIMITS:
                        tighten_text(pid, BOUND_TEXT_LIMITS[(op, field)])
        if op == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
            for kind, content in parse_template(step['pattern'], allow_source_tokens=True):
                if kind == 'param':
                    tighten_text(content, COMPONENT_TEXT_LIMIT, single_component=True)

    dest = authored.get('destination', {})
    if dest.get('mode') == 'subfolder' and has_parameter_references(dest.get('folder', '')):
        for kind, content in parse_template(dest['folder'], allow_source_tokens=False, allow_date_tokens=True):
            if kind == 'param':
                tighten_text(content, COMPONENT_TEXT_LIMIT, single_component=True)

    # Verify explicit defaults & Settings sources against intersected constraints.
    for param in params:
        pid = param['id']
        eff = result[pid]
        if 'default' in param:
            _validate_param_value(param, param['default'], constraints=eff)
        if 'default_source' in param:
            expected_type, _ = SETTINGS_SOURCES[param['default_source']]
            if expected_type == 'integer':
                low = eff.get('minimum', 1)
                high = eff.get('maximum', 100)
                if low > 100 or high < 1:
                    raise RecipeError(
                        f"Parameter '{pid}' effective bounds ({low}–{high}) "
                        'cannot accept Settings quality 1–100.'
                    )

    return result


def effective_constraints(recipe, *, validated=False):
    """Return effective constraints for each declared parameter without mutating recipe.

    Combines each parameter's declaration with constraints inherited and
    intersected across all active operation bindings via operation_definitions().
    """
    authored = recipe if validated else validate_authored(recipe)
    if not authored.get('parameters'):
        return {}
    definitions = handler(authored['media']).operation_definitions()
    return _compute_effective_constraints(authored, definitions)


def is_parameterized(recipe):
    """Return True if an authored Recipe uses parameters, bindings, conditions, or param templates."""
    if not isinstance(recipe, dict):
        return False
    if 'parameters' in recipe:
        raw_params = recipe['parameters']
        if not isinstance(raw_params, list) or raw_params:
            return True
    dest = recipe.get('destination')
    if isinstance(dest, dict) and dest.get('mode') == 'subfolder':
        if has_parameter_references(dest.get('folder', '')):
            return True
    steps = recipe.get('steps')
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            if 'bindings' in step or 'enabled_when' in step:
                return True
            if step.get('op') == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
                return True
    return False


def validate_authored(recipe):
    """Validate an authored Recipe definition (concrete or parameterized).

    Returns a validated deep copy without mutating the caller's input.
    """
    if not isinstance(recipe, dict):
        raise RecipeError('Recipe must be a JSON object.')
    authored = copy.deepcopy(recipe)
    if type(authored.get('schema')) is not int or authored['schema'] != AUTHORED_SCHEMA:
        raise RecipeError('Unsupported recipe schema')
    if not is_parameterized(authored) and 'parameters' not in authored:
        probe = copy.deepcopy(authored)
        probe['schema'] = CONCRETE_SCHEMA
        validate_concrete(probe)
        return authored

    keys(
        authored,
        ('schema', 'id', 'name', 'description', 'media', 'steps', 'destination'),
        ('folder', 'dolphin_shortcut', 'parameters'),
    )
    if 'parameters' in authored:
        raw_params = authored['parameters']
        if not isinstance(raw_params, list) or len(raw_params) > MAX_PARAMETERS:
            raise RecipeError(
                f'Parameters must be a list of at most {MAX_PARAMETERS} declarations.'
            )
    else:
        raw_params = []

    params_by_id = {}
    param_clauses = {}
    for item in raw_params:
        _validate_parameter(item, params_by_id)
        params_by_id[item['id']] = item
        param_clauses[item['id']] = _effective_clauses(
            item.get('visible_when'), params_by_id
        )

    steps = authored.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 50:
        raise RecipeError('Expected 1–50 ordered steps')

    media_handler = handler(authored.get('media'))
    definitions = media_handler.operation_definitions()

    destination = authored.get('destination')
    if not isinstance(destination, dict):
        raise RecipeError('Invalid destination')

    # Validate destination parameter references only when {param:...} is present,
    # preserving ordinary literal subfolder names that may contain braces.
    dest_param_refs = []
    if (
        destination.get('mode') == 'subfolder'
        and has_parameter_references(destination.get('folder'))
    ):
        dest_param_refs = _validate_template_refs(
            destination['folder'],
            params_by_id,
            param_clauses,
            allow_source_tokens=False,
            allow_date_tokens=True,
            context_label='Destination folder',
        )

    step_literals = []
    step_bindings_list = []
    step_effective_clauses = []
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get('op'), str):
            raise RecipeError('Invalid step')
        op = step['op']
        if op not in definitions:
            raise RecipeError('Unknown operation: ' + str(op))
        if type(step.get('enabled', True)) is not bool:
            raise RecipeError('Step enabled must be boolean')

        literal_step = copy.deepcopy(step)
        has_enabled_when = 'enabled_when' in literal_step
        enabled_when = literal_step.pop('enabled_when', None)
        has_bindings = 'bindings' in literal_step
        bindings = literal_step.pop('bindings', None)

        if has_enabled_when:
            if enabled_when is None:
                raise RecipeError(f"Operation '{op}' enabled_when cannot be null.")
            _validate_condition(enabled_when, params_by_id)
            clauses = _effective_clauses(enabled_when, params_by_id)
            if clauses is None:
                raise RecipeError(
                    f"Operation '{op}' has an unsatisfiable enabled_when condition."
                )
        else:
            clauses = {}

        statically_disabled = step.get('enabled', True) is False

        if has_bindings:
            if not isinstance(bindings, dict) or not bindings:
                raise RecipeError(
                    f"Operation '{op}' bindings must be a non-empty object."
                )
            op_params = definitions[op]['parameters']
            blocked = UNBINDABLE_FIELDS.get(op, set())
            for field, pid in bindings.items():
                if (
                    not isinstance(field, str)
                    or '.' in field
                    or '[' in field
                    or field not in op_params
                    or field in blocked
                ):
                    raise RecipeError(
                        f"Unsupported binding field '{field}' on operation '{op}'."
                    )
                if not isinstance(pid, str) or pid not in params_by_id:
                    raise RecipeError(
                        f"Operation '{op}' binds unknown parameter '{pid}'."
                    )
                param = params_by_id[pid]
                _check_field_compatibility(op, field, op_params[field], param, literal_step)
                if not statically_disabled and param.get('visible_when') is not None:
                    if not _clauses_imply(clauses, param_clauses[pid]):
                        raise RecipeError(
                            f"Active operation '{op}' cannot bind conditional parameter '{pid}' "
                            'without a matching enabled_when condition.'
                        )

        # Always validate the step's actual literal fallback fields first so
        # malformed literal values (including on disabled steps) are never concealed.
        if op == 'file.rename_output':
            keys(literal_step, ('op', 'pattern'), ('enabled',))
            if not isinstance(literal_step['pattern'], str):
                raise RecipeError('Rename Output File requires a pattern.')
            if has_parameter_references(literal_step['pattern']):
                _validate_template_refs(
                    literal_step['pattern'],
                    params_by_id,
                    param_clauses,
                    allow_source_tokens=True,
                    context_label='Filename template',
                    step_clauses=clauses,
                    statically_disabled=statically_disabled,
                )
            else:
                validate_output_pattern(literal_step['pattern'])
        elif op in ('file.sync_date', 'file.preserve_date'):
            keys(literal_step, ('op',), ('enabled',))
        elif (
            op == 'image.overlay'
            and literal_step.get('kind') == 'image'
            and has_bindings
            and 'logo' in bindings
            and literal_step.get('logo') == ''
        ):
            probe_step = copy.deepcopy(literal_step)
            probe_step['enabled'] = False
            media_handler.validate_step(probe_step)
        else:
            media_handler.validate_step(literal_step)

        step_literals.append(literal_step)
        step_bindings_list.append(bindings if has_bindings else None)
        step_effective_clauses.append(None if statically_disabled else clauses)

    # Compute and verify intersected effective constraints across active bindings.
    eff_constraints = _compute_effective_constraints(authored, definitions)

    # Validate explicit defaults and declared choices against bound step validators
    # without overwriting literal fallbacks with fabricated samples.
    for literal_step, bindings in zip(step_literals, step_bindings_list):
        op = literal_step['op']
        if op == 'file.rename_output' and has_parameter_references(literal_step['pattern']):
            probe_values = {
                pid: _template_probe_value(params_by_id[pid], eff_constraints[pid])
                for pid in params_by_id
            }
            _render_template(
                literal_step['pattern'],
                params_by_id,
                probe_values,
                allow_source_tokens=True,
            )
            continue
        if not bindings:
            continue
        # Test explicit parameter defaults together on the step.
        default_variant = copy.deepcopy(literal_step)
        applied_default = False
        for field, pid in bindings.items():
            param = params_by_id[pid]
            if 'default' in param:
                _apply_step_field(default_variant, field, copy.deepcopy(param['default']))
                applied_default = True
        if applied_default:
            if (
                op == 'image.overlay'
                and default_variant.get('kind') == 'image'
                and 'logo' in bindings
                and default_variant.get('logo') == ''
            ):
                default_variant['enabled'] = False
            media_handler.validate_step(default_variant)
        # Test every declared choice option on choice-bound fields.
        for field, pid in bindings.items():
            param = params_by_id[pid]
            if param['type'] == 'choice':
                for choice_val in _choice_values(param):
                    variant = copy.deepcopy(literal_step)
                    _apply_step_field(variant, field, choice_val)
                    if (
                        op == 'image.overlay'
                        and variant.get('kind') == 'image'
                        and 'logo' in bindings
                        and variant.get('logo') == ''
                    ):
                        variant['enabled'] = False
                    media_handler.validate_step(variant)

    # Validate destination (rendering probe only if subfolder uses {param:...}).
    probe_destination = copy.deepcopy(destination)
    if dest_param_refs:
        probe_values = {
            pid: _template_probe_value(params_by_id[pid], eff_constraints[pid])
            for pid in dest_param_refs
        }
        probe_destination['folder'] = _render_subfolder_template(
            destination['folder'],
            params_by_id,
            probe_values,
        )

    # Reuse existing concrete validator for top-level header & destination rules.
    header_probe = {
        key: value for key, value in authored.items()
        if key not in ('parameters', 'steps', 'destination')
    }
    header_probe['schema'] = CONCRETE_SCHEMA
    header_probe['destination'] = probe_destination
    header_probe['steps'] = [{'op': 'file.preserve_date'}]
    validate_concrete(header_probe)

    # Pairwise O(S^2) static conflict check using existing validate_order().
    for i in range(len(step_literals)):
        clauses_i = step_effective_clauses[i]
        if clauses_i is None:
            continue
        for j in range(i + 1, len(step_literals)):
            clauses_j = step_effective_clauses[j]
            if clauses_j is None or _conditions_disjoint(clauses_i, clauses_j):
                continue
            media_handler.validate_order([
                dict(step_literals[i], enabled=True),
                dict(step_literals[j], enabled=True),
            ])

    return authored


def _evaluate_condition(cond, resolved_values, active_ids):
    if cond is None:
        return True
    for pred in _condition_predicates(cond):
        pid = pred['param']
        if pid not in active_ids:
            return False
        val = resolved_values.get(pid, _MISSING)
        if val is _MISSING:
            return False
        if 'equals' in pred:
            if not _scalar_equals(val, pred['equals']):
                return False
        elif not any(_scalar_equals(val, option) for option in pred['in']):
            return False
    return True


def _read_settings_source(source_key, cache):
    if source_key in cache:
        return cache[source_key]
    from kim_recipe_image import copyright_settings, inherited_quality
    expected_type, field = SETTINGS_SOURCES[source_key]
    if expected_type == 'text':
        if '_copyright' not in cache:
            cache['_copyright'] = copyright_settings()
        value = cache['_copyright'][field]
    else:
        value = inherited_quality(field)
    cache[source_key] = value
    return value


def _validate_supplied_mapping(supplied, declared_ids):
    if supplied is None:
        return {}
    if not isinstance(supplied, dict):
        raise RecipeError('Parameter values must be a mapping.')
    for key in supplied:
        if not isinstance(key, str):
            raise RecipeError('Parameter names must be strings.')
    unknown = sorted(key for key in supplied if key not in declared_ids)
    if unknown:
        raise RecipeError('Unknown parameter value(s): ' + ', '.join(unknown))
    return supplied


def _evaluate_parameters(authored, values, *, strict, eff_constraints):
    """Single shared parameter evaluator for interactive forms and strict resolution."""
    params = authored.get('parameters', [])
    declared_ids = {p['id'] for p in params}
    supplied = _validate_supplied_mapping(values, declared_ids)

    active = []
    active_ids = set()
    resolved = {}
    errors = {}
    settings_cache = {}

    for param in params:
        pid = param['id']
        if 'visible_when' in param and not _evaluate_condition(
            param['visible_when'], resolved, active_ids
        ):
            # Inactive parameters never consume caller values or defaults.
            continue

        active.append(copy.deepcopy(param))
        active_ids.add(pid)
        eff = eff_constraints.get(pid, {})

        raw = _MISSING
        read_error = None
        if pid in supplied:
            raw = supplied[pid]
            if raw is None:
                read_error = f"Parameter '{param['label']}' cannot be null."
        elif 'default' in param:
            raw = copy.deepcopy(param['default'])
        elif 'default_source' in param:
            try:
                raw = _read_settings_source(param['default_source'], settings_cache)
            except (OSError, RecipeError) as exc:
                read_error = str(exc)

        if read_error is not None:
            if strict:
                raise RecipeError(read_error)
            errors[pid] = read_error
            resolved[pid] = _MISSING
            continue

        if raw is _MISSING:
            if param.get('required', False):
                msg = f"Parameter '{param['label']}' requires a value."
                if strict:
                    raise RecipeError(msg)
                errors[pid] = msg
            resolved[pid] = _MISSING
            continue

        try:
            validated = _validate_param_value(param, raw, constraints=eff)
            if (
                param.get('required', False)
                and param['type'] in ('text', 'capture_datetime', 'watermark_image')
                and not validated.strip()
            ):
                if param['type'] == 'watermark_image':
                    raise RecipeError('Choose a watermark image file.')
                raise RecipeError(
                    f"Parameter '{param['label']}' requires a non-empty value."
                )
        except RecipeError as exc:
            if strict:
                raise
            errors[pid] = str(exc)
            resolved[pid] = _MISSING
            continue

        if (
            not param.get('required', False)
            and param['type'] == 'capture_datetime'
            and validated == ''
        ):
            resolved[pid] = _MISSING
        else:
            resolved[pid] = validated

    return active, active_ids, resolved, errors


def evaluate_parameters(recipe, values=None, *, validated=False, constraints=None):
    """Evaluate active parameters, effective values, constraints, and errors.

    Intended for interactive Settings forms: incomplete required values stay
    active with field errors, and invalid/missing controlling values never
    activate dependent parameters. Pass validated=True (and optionally
    precomputed effective_constraints()) when recipe was already validated by
    validate_authored() to avoid repeating static validation on each input edit.
    """
    authored = recipe if validated else validate_authored(recipe)
    eff = (
        constraints
        if validated and constraints is not None
        else effective_constraints(authored, validated=True)
    )
    active, active_ids, resolved, errors = _evaluate_parameters(
        authored, values, strict=False, eff_constraints=eff
    )
    return {
        'active': active,
        'values': {
            pid: copy.deepcopy(val)
            for pid, val in resolved.items()
            if val is not _MISSING
        },
        'errors': errors,
        'constraints': {
            pid: copy.deepcopy(eff[pid])
            for pid in active_ids
            if pid in eff
        },
    }


def active_parameters(recipe, values=None, *, validated=False, constraints=None):
    """Return active parameter declarations in order without mutating inputs."""
    return evaluate_parameters(
        recipe, values, validated=validated, constraints=constraints
    )['active']


def materialize_settings(
    snapshot, media_handler=None, *, strict=True, include_disabled=False
):
    """Materialize unbound KIMng Settings references on steps once before review.

    - Preserves active image.compress precedence over inherited image.convert.quality.
    - When strict=True (parameterized compilation): raises on any enabled-step
      Settings error; skips disabled steps unless include_disabled=True.
    - When strict=False (ordinary concrete confirmation_snapshot): continues
      resolving remaining fields (including disabled steps for presentation when
      include_disabled=True), returning the first enabled-step error (or None).
    """
    media = media_handler or handler(snapshot['media'])
    definitions = media.operation_definitions()
    compress_active = any(
        s['op'] == 'image.compress' and s.get('enabled', True)
        for s in snapshot['steps']
    )
    copyright_loaded = False
    copyright_values = None
    copyright_error = None
    first_error = None

    def record_error(step, exc):
        nonlocal first_error
        if step.get('enabled', True):
            if strict:
                raise exc
            if first_error is None:
                first_error = str(exc)

    def get_copyright():
        nonlocal copyright_loaded, copyright_values, copyright_error
        if not copyright_loaded:
            copyright_loaded = True
            try:
                from kim_recipe_image import copyright_settings
                copyright_values = copyright_settings()
            except (OSError, RecipeError) as exc:
                copyright_error = exc
        if copyright_error is not None:
            raise copyright_error
        return copyright_values

    for step in snapshot['steps']:
        if not include_disabled and not step.get('enabled', True):
            continue
        if step['op'] == 'image.overlay' and step.get('kind') == 'text':
            try:
                from kim_image_ops import resolved_watermark_fields
                step['text_fields'] = resolved_watermark_fields(step)
            except (OSError, RecipeError) as exc:
                record_error(step, exc)
        for key, spec in definitions[step['op']]['parameters'].items():
            if key == 'quality' and step['op'] == 'image.convert' and compress_active:
                continue
            if spec.get('settings_key') and step.get(key) is None:
                try:
                    if step['op'] == 'image.convert' and key == 'quality':
                        step[key] = media.parameter_value(step, key)
                    else:
                        step[key] = media.parameter_value(step, key, get_copyright())
                except (OSError, RecipeError) as exc:
                    record_error(step, exc)
    return first_error


def initial_remembered_values(recipe, raw_remembered, *, validated=False, constraints=None):
    """Filter and validate persisted remembered answers against an authored Recipe.

    Evaluates in declaration order so valid remembered values on controlling
    questions can activate dependent questions, while invalid, disabled, or
    inactive remembered values are discarded and never affect visibility.
    """
    if not isinstance(raw_remembered, dict) or not raw_remembered:
        return {}
    authored = recipe if validated else validate_authored(recipe)
    params = authored.get('parameters', [])
    if not params:
        return {}
    eff_all = (
        constraints
        if validated and constraints is not None
        else effective_constraints(authored, validated=True)
    )

    accepted = {}
    active_ids = set()
    resolved = {}
    settings_cache = {}

    for param in params:
        pid = param['id']
        if 'visible_when' in param and not _evaluate_condition(
            param['visible_when'], resolved, active_ids
        ):
            continue
        active_ids.add(pid)
        eff = eff_all.get(pid, {})

        used_remembered = False
        if param.get('remember', False) and pid in raw_remembered:
            candidate = raw_remembered[pid]
            try:
                val = _validate_param_value(param, candidate, constraints=eff)
                if (
                    param.get('required', False)
                    and param['type'] in ('text', 'capture_datetime', 'watermark_image')
                    and not val.strip()
                ):
                    raise RecipeError('Empty required remembered value')
                if eff.get('single_component') and isinstance(val, str) and val:
                    component(val)
                accepted[pid] = copy.deepcopy(val)
                resolved[pid] = val
                used_remembered = True
            except RecipeError:
                used_remembered = False

        if not used_remembered:
            if 'default' in param:
                resolved[pid] = copy.deepcopy(param['default'])
            elif 'default_source' in param:
                try:
                    resolved[pid] = _read_settings_source(param['default_source'], settings_cache)
                except (OSError, RecipeError):
                    resolved[pid] = _MISSING
            else:
                resolved[pid] = _MISSING

    return accepted


def resolve_recipe(recipe, values=None, *, validated=False):
    """Compile an authored Recipe + run-time values into a concrete Recipe snapshot.

    Never mutates recipe, values, or application preferences. Raises RecipeError
    on any validation, missing-required, inactive-reference, or ordering problem.
    """
    authored = copy.deepcopy(recipe) if validated else validate_authored(recipe)
    media_handler = handler(authored['media'])
    definitions = media_handler.operation_definitions()
    eff = _compute_effective_constraints(authored, definitions) if authored.get('parameters') else {}

    params = authored.get('parameters', [])
    params_by_id = {p['id']: p for p in params}

    # Stage 1: Strict parameter evaluation via shared evaluator.
    _, active_ids, resolved, _ = _evaluate_parameters(
        authored, values, strict=True, eff_constraints=eff
    )

    concrete = copy.deepcopy(authored)
    concrete['schema'] = CONCRETE_SCHEMA
    concrete.pop('parameters', None)

    # Stage 2: Resolve conditional operation activation BEFORE field bindings
    # and Settings materialization.
    step_bindings = []
    for step in concrete['steps']:
        enabled_when = step.pop('enabled_when', None)
        bindings = step.pop('bindings', None)
        step_bindings.append(bindings)
        if step.get('enabled', True) is False:
            continue
        if enabled_when is not None:
            step['enabled'] = _evaluate_condition(enabled_when, resolved, active_ids)

    # Stage 3: Apply bindings & filename templates to enabled steps; neutralize
    # unresolved template references on disabled steps without reading inactive values.
    for step, bindings in zip(concrete['steps'], step_bindings):
        op = step['op']
        if not step.get('enabled', True):
            if op == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
                step['pattern'] = '{filename}_recipe'
            continue

        if bindings:
            op_label = definitions[op]['label']
            for field, pid in bindings.items():
                if pid not in active_ids:
                    raise RecipeError(
                        f"Active operation '{op_label}' cannot consume inactive parameter '{pid}'."
                    )
                val = resolved[pid]
                if val is _MISSING:
                    if (op, field) in OPTIONAL_EMPTY_TEXT_FIELDS:
                        step[field] = ''
                    elif (
                        op == 'image.overlay'
                        and field == 'value'
                        and step.get('kind') == 'text'
                        and step.get('text_fields') is not None
                    ):
                        step['text_fields']['custom'] = {
                            'selected': False,
                            'value': '',
                        }
                    else:
                        raise RecipeError(
                            f"Parameter '{params_by_id[pid]['label']}' requires a value "
                            f"for active operation '{op_label}'."
                        )
                else:
                    _apply_step_field(step, field, val)

        if op == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
            tokens = parse_template(step['pattern'], allow_source_tokens=True)
            for kind, content in tokens:
                if kind == 'param' and content not in active_ids:
                    raise RecipeError(
                        f"Active Rename Output File cannot consume inactive parameter '{content}'."
                    )
            step['pattern'] = _render_template(
                step['pattern'], params_by_id, resolved, allow_source_tokens=True
            )

    # Stage 4: Resolve subfolder destination template (single- or multi-component)
    # when {param:...} references are present (ordinary literal folder names untouched).
    dest = concrete['destination']
    if dest['mode'] == 'subfolder' and has_parameter_references(dest.get('folder', '')):
        tokens = parse_template(dest['folder'], allow_source_tokens=False, allow_date_tokens=True)
        for kind, content in tokens:
            if kind == 'param' and content not in active_ids:
                raise RecipeError(
                    f"Destination folder cannot consume inactive parameter '{content}'."
                )
        dest['folder'] = _render_subfolder_template(
            dest['folder'], params_by_id, resolved
        )

    # Stage 5: Validate context and strictly materialize Settings before review.
    media_handler.validate_context(concrete['steps'])
    materialize_settings(concrete, media_handler, strict=True)

    # Stage 6: Final strict concrete validation (includes validate_step & validate_order).
    return validate_concrete(concrete)


def has_parameterized_output_templates(recipe):
    """Return True if a parameterized Recipe has parameterized filename or destination templates."""
    if not is_parameterized(recipe):
        return False
    dest = recipe.get('destination') or {}
    if dest.get('mode') == 'subfolder' and has_parameter_references(dest.get('folder', '')):
        return True
    for step in recipe.get('steps', ()):
        if not isinstance(step, dict) or step.get('enabled', True) is False:
            continue
        op = step.get('op')
        if op == 'file.rename_output' and (
            has_parameter_references(step.get('pattern', ''))
            or step.get('enabled_when') is not None
        ):
            return True
        if op == 'file.name_transform' and (
            step.get('bindings') or step.get('enabled_when') is not None
        ):
            return True
    return False


def preview_output_example(
    recipe,
    values=None,
    source_name=None,
    *,
    validated=False,
    constraints=None,
    invalid_ids=None,
):
    """Compute a lightweight, pure-Python example filename and subfolder.

    Never executes preflight, ImageMagick, ExifTool, image decoding, directory
    creation, or filesystem checks. Never invents missing capture dates or
    displays raw {param:...} syntax.
    """
    authored = recipe if validated else validate_authored(recipe)
    if not has_parameterized_output_templates(authored):
        return {
            'available': False,
            'complete': False,
            'filename': None,
            'subfolder': None,
            'prompt': '',
            'note': '',
        }

    eff = (
        constraints
        if validated and constraints is not None
        else effective_constraints(authored, validated=True)
    )
    _, active_ids, resolved, errors = _evaluate_parameters(
        authored, values, strict=False, eff_constraints=eff
    )
    params_by_id = {p['id']: p for p in authored.get('parameters', [])}
    invalid_set = set(invalid_ids or ())
    for pid in invalid_set:
        if pid in resolved:
            resolved[pid] = _MISSING

    def is_invalid_value(pid):
        if pid in invalid_set:
            return True
        if pid not in errors:
            return False
        err = errors[pid]
        return not (
            err.endswith('requires a value.')
            or err.endswith('requires a non-empty value.')
        )

    def incomplete(reason='missing'):
        prompt = (
            'Enter valid settings above to preview an example output.'
            if reason == 'invalid'
            else 'Complete the required settings above to preview an example output.'
        )
        return {
            'available': True,
            'complete': False,
            'filename': None,
            'subfolder': None,
            'prompt': prompt,
            'note': '',
        }

    sample = Path(str(source_name)).name if source_name else 'photo.jpg'
    if not sample:
        sample = 'photo.jpg'
    source_stem = Path(sample).stem or 'photo'
    source_ext = Path(sample).suffix.lstrip('.').lower() or 'jpg'

    # Destination subfolder (if applicable).
    dest = authored['destination']
    subfolder = None
    if dest['mode'] == 'subfolder':
        folder_tpl = dest['folder']
        if has_parameter_references(folder_tpl):
            tokens = parse_template(folder_tpl, allow_source_tokens=False, allow_date_tokens=True)
            for kind, content in tokens:
                if kind == 'param':
                    if is_invalid_value(content):
                        return incomplete('invalid')
                    if content not in active_ids:
                        return incomplete('missing')
                    if resolved.get(content, _MISSING) is _MISSING and params_by_id[content].get('required', False):
                        return incomplete('missing')
            try:
                subfolder = _render_subfolder_template(
                    folder_tpl, params_by_id, resolved
                )
            except RecipeError:
                return incomplete('invalid')
        else:
            subfolder = folder_tpl
        if subfolder and ('{year}' in subfolder or '{capture_date}' in subfolder):
            subfolder = subfolder.replace('{year}', '2026').replace('{capture_date}', '2026-11-20')

    from kim_recipe_image import FORMATS

    current_stem = source_stem
    current_ext = source_ext
    needs_capture_date = False

    for step in authored['steps']:
        if step.get('enabled', True) is False:
            continue
        op = step['op']
        affects_output = op in ('image.convert', 'file.rename_output', 'file.name_transform')
        enabled_when = step.get('enabled_when')
        if enabled_when is not None:
            if affects_output:
                for pred in _condition_predicates(enabled_when):
                    pid = pred['param']
                    if pid in active_ids and resolved.get(pid, _MISSING) is _MISSING:
                        return incomplete('invalid' if is_invalid_value(pid) else 'missing')
            if not _evaluate_condition(enabled_when, resolved, active_ids):
                continue

        if op == 'image.convert':
            bindings = step.get('bindings') or {}
            if 'format' in bindings:
                pid = bindings['format']
                if pid not in active_ids or resolved.get(pid, _MISSING) is _MISSING:
                    return incomplete('invalid' if is_invalid_value(pid) else 'missing')
                fmt = resolved[pid]
            else:
                fmt = step.get('format')
            if fmt in FORMATS:
                current_ext = FORMATS[fmt]

        elif op == 'file.rename_output':
            pat = step['pattern']
            if has_parameter_references(pat):
                tokens = parse_template(pat, allow_source_tokens=True)
                for kind, content in tokens:
                    if kind == 'param':
                        if content not in active_ids or resolved.get(content, _MISSING) is _MISSING:
                            return incomplete('invalid' if is_invalid_value(content) else 'missing')
                try:
                    rendered_pat = _render_template(
                        pat, params_by_id, resolved, allow_source_tokens=True
                    )
                except RecipeError:
                    return incomplete('invalid')
            else:
                rendered_pat = pat

            if any(field == 'date' for _, field, _, _ in string.Formatter().parse(rendered_pat)):
                needs_capture_date = True
            else:
                try:
                    current_stem = component(
                        format_output_pattern(rendered_pat, source_stem, date='', index=1)
                    )
                except (ValueError, KeyError, RecipeError):
                    return incomplete('invalid')

        elif op == 'file.name_transform':
            step_copy = copy.deepcopy(step)
            bindings = step_copy.pop('bindings', None) or {}
            step_copy.pop('enabled_when', None)
            for field, pid in bindings.items():
                if pid not in active_ids:
                    return incomplete('missing')
                val = resolved.get(pid, _MISSING)
                if val is _MISSING:
                    if (op, field) in OPTIONAL_EMPTY_TEXT_FIELDS and not is_invalid_value(pid):
                        val = ''
                    else:
                        return incomplete('invalid' if is_invalid_value(pid) else 'missing')
                step_copy[field] = val
            if step_copy.get('method') == 'capture_date':
                needs_capture_date = True
            elif not needs_capture_date:
                from kim_filename import transform
                try:
                    current_stem = component(
                        transform(current_stem, step_copy, index=1, capture=None)
                    )
                except (ValueError, RecipeError):
                    return incomplete('invalid')

    if needs_capture_date:
        return {
            'available': True,
            'complete': True,
            'filename': None,
            'subfolder': subfolder,
            'prompt': '',
            'note': (
                "Exact filename uses each image's capture date and is confirmed "
                'during Review Changes.'
            ),
        }

    return {
        'available': True,
        'complete': True,
        'filename': f'{current_stem}.{current_ext}',
        'subfolder': subfolder,
        'prompt': '',
        'note': '',
    }


SETTINGS_SOURCE_LABELS = {
    'copyright.creator': 'Creator / Artist (KIMng Settings)',
    'copyright.notice': 'Copyright notice (KIMng Settings)',
    'copyright.rights': 'Usage rights (KIMng Settings)',
    'web.quality.jpeg': 'JPEG quality (KIMng Settings)',
    'web.quality.webp': 'WebP quality (KIMng Settings)',
    'web.quality.avif': 'AVIF quality (KIMng Settings)',
}


def generate_parameter_id(label, existing_ids=()):
    """Generate a stable, unique PARAM_ID_RE identifier from a display label."""
    existing = set(existing_ids or ())
    slug = re.sub(r'[^a-z0-9]+', '_', str(label or '').casefold()).strip('_')
    if not slug:
        slug = 'param'
    elif not slug[0].isalpha():
        slug = 'p_' + slug
    slug = slug[:40].rstrip('_') or 'param'
    if slug not in existing and PARAM_ID_RE.fullmatch(slug):
        return slug
    suffix = 2
    while True:
        tail = f'_{suffix}'
        candidate = (slug[: 40 - len(tail)].rstrip('_') or 'p') + tail
        if candidate not in existing and PARAM_ID_RE.fullmatch(candidate):
            return candidate
        suffix += 1


def is_bindable_field(op, field, step, definitions):
    """Return True when (op, field) is an approved binding destination."""
    op_def = definitions.get(op)
    if not op_def or field not in op_def['parameters']:
        return False
    if field in UNBINDABLE_FIELDS.get(op, ()):
        return False
    if op == 'image.overlay' and field == 'logo':
        return step.get('kind') == 'image'
    if op == 'image.overlay' and field == 'value':
        kind = step.get('kind')
        if kind == 'text':
            return step.get('text_fields') is not None or step.get('source') == 'custom'
        if kind == 'caption':
            return step.get('source') == 'custom'
        return False
    return True


def settings_source_for_field(op, field, step=None):
    """Return matching allow-listed SETTINGS_SOURCES key for a field, if any."""
    if op == 'metadata.copyright' and field in ('creator', 'notice', 'rights'):
        return 'copyright.' + field
    if op == 'metadata.creator' and field == 'value':
        return 'copyright.creator'
    if op == 'metadata.copyright_notice' and field == 'value':
        return 'copyright.notice'
    if op == 'metadata.usage_rights' and field == 'value':
        return 'copyright.rights'
    if op == 'image.convert' and field == 'quality':
        fmt = (step or {}).get('format', 'jpeg')
        key = 'web.quality.' + str(fmt)
        return key if key in SETTINGS_SOURCES else None
    return None


def parameter_references(recipe, pid, definitions=None):
    """Return every binding, condition and template reference to pid in recipe."""
    if not isinstance(recipe, dict):
        return []
    if definitions is None:
        try:
            definitions = handler(recipe['media']).operation_definitions()
        except RecipeError:
            definitions = {}

    refs = []
    for param in recipe.get('parameters', ()):
        cond = param.get('visible_when')
        if cond is not None and any(pred.get('param') == pid for pred in _condition_predicates(cond)):
            refs.append({
                'kind': 'visible_when',
                'param_id': param['id'],
                'param_label': param.get('label', param['id']),
                'description': f"Visibility condition of '{param.get('label', param['id'])}'",
            })

    for idx, step in enumerate(recipe.get('steps', ())):
        op = step.get('op', '')
        op_def = definitions.get(op, {})
        op_label = op_def.get('label', op)
        op_params = op_def.get('parameters', {})

        cond = step.get('enabled_when')
        if cond is not None and any(pred.get('param') == pid for pred in _condition_predicates(cond)):
            refs.append({
                'kind': 'enabled_when',
                'step_index': idx,
                'op': op,
                'op_label': op_label,
                'description': f"Activation condition of Step {idx + 1} ({op_label})",
            })

        for field, bound_id in (step.get('bindings') or {}).items():
            if bound_id == pid:
                field_label = op_params.get(field, {}).get('label', field)
                refs.append({
                    'kind': 'binding',
                    'step_index': idx,
                    'op': op,
                    'op_label': op_label,
                    'field': field,
                    'field_label': field_label,
                    'description': f"Step {idx + 1} ({op_label}) field '{field_label}'",
                })

        if op == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
            try:
                tokens = parse_template(step['pattern'], allow_source_tokens=True)
            except RecipeError:
                tokens = ()
            if any(kind == 'param' and content == pid for kind, content in tokens):
                refs.append({
                    'kind': 'filename_template',
                    'step_index': idx,
                    'op': op,
                    'op_label': op_label,
                    'description': f"Filename pattern in Step {idx + 1} ({op_label})",
                })

    dest = recipe.get('destination') or {}
    if dest.get('mode') == 'subfolder' and has_parameter_references(dest.get('folder', '')):
        try:
            tokens = parse_template(dest['folder'], allow_source_tokens=False, allow_date_tokens=True)
        except RecipeError:
            tokens = ()
        if any(kind == 'param' and content == pid for kind, content in tokens):
            refs.append({
                'kind': 'destination_template',
                'description': 'Destination subfolder template',
            })

    return refs


def _format_condition_value(param, value):
    if param is None:
        return str(value)
    ptype = param.get('type')
    if ptype == 'boolean':
        return 'Yes' if value else 'No'
    if ptype == 'choice':
        for item in param.get('choices', ()):
            if isinstance(item, dict) and item.get('value') == value:
                return item.get('label', str(value))
    return str(value)


def summarize_condition(cond, params_by_id):
    """Format a resolver condition into readable prose using display labels."""
    if cond is None:
        return ''
    clauses = []
    for pred in _condition_predicates(cond):
        pid = pred['param']
        param = params_by_id.get(pid)
        label = param['label'] if param else pid
        if 'equals' in pred:
            val_text = _format_condition_value(param, pred['equals'])
            clauses.append(f'{label} is {val_text}')
        else:
            options = [_format_condition_value(param, opt) for opt in pred['in']]
            if len(options) == 1:
                clauses.append(f'{label} is {options[0]}')
            elif len(options) == 2:
                clauses.append(f'{label} is {options[0]} or {options[1]}')
            else:
                clauses.append(
                    f"{label} is {', '.join(options[:-1])}, or {options[-1]}"
                )
    return ' and '.join(clauses)


def compatible_parameters_for_field(recipe, step_index, field, definitions=None):
    """Return declared parameters that can validly bind (step_index, field)."""
    if not isinstance(recipe, dict) or not 0 <= step_index < len(recipe.get('steps', ())):
        return []
    params = recipe.get('parameters') or []
    if not params:
        return []
    if definitions is None:
        definitions = handler(recipe['media']).operation_definitions()
    step = recipe['steps'][step_index]
    op = step['op']
    if not is_bindable_field(op, field, step, definitions):
        return []

    spec = definitions[op]['parameters'][field]
    literal_step = {k: v for k, v in step.items() if k not in ('enabled_when', 'bindings')}
    compatible = []
    for param in params:
        try:
            _check_field_compatibility(op, field, spec, param, literal_step)
        except RecipeError:
            continue
        probe = copy.deepcopy(recipe)
        probe_step = probe['steps'][step_index]
        bindings = dict(probe_step.get('bindings') or {})
        bindings[field] = param['id']
        probe_step['bindings'] = bindings
        try:
            validate_authored(probe)
        except RecipeError:
            continue
        compatible.append(copy.deepcopy(param))
    return compatible


def compatible_parameters_for_template(recipe, *, allow_source_tokens=True, step_index=None):
    """Return declared parameters that can validly appear in a filename or subfolder template."""
    if not isinstance(recipe, dict):
        return []
    params = recipe.get('parameters') or []
    if not params:
        return []
    params_by_id = {p['id']: p for p in params}
    param_clauses = {}
    for param in params:
        clauses = _effective_clauses(param.get('visible_when'), params_by_id)
        if clauses is None:
            return []
        param_clauses[param['id']] = clauses

    step_clauses = None
    statically_disabled = False
    if step_index is not None and 0 <= step_index < len(recipe.get('steps', ())):
        step = recipe['steps'][step_index]
        statically_disabled = step.get('enabled', True) is False
        step_clauses = _effective_clauses(step.get('enabled_when'), params_by_id)
        if step_clauses is None:
            statically_disabled = True

    compatible = []
    for param in params:
        pid = param['id']
        if param.get('type') not in TEMPLATE_PARAM_TYPES:
            continue
        if not statically_disabled and param.get('visible_when') is not None:
            if step_clauses is None or not _clauses_imply(step_clauses, param_clauses[pid]):
                continue
        compatible.append(copy.deepcopy(param))
    return compatible


def parameter_from_field(recipe, step_index, field, definitions=None):
    """Build a sensible initial parameter declaration derived from an operation field."""
    if definitions is None:
        definitions = handler(recipe['media']).operation_definitions()
    step = recipe['steps'][step_index]
    op = step['op']
    spec = definitions[op]['parameters'][field]
    existing_ids = {p['id'] for p in recipe.get('parameters', ())}

    label = spec.get('label', field.replace('_', ' ').capitalize())
    pid = generate_parameter_id(label, existing_ids)
    stype = spec['type']

    param = {'id': pid, 'label': label}
    if stype == 'boolean':
        param['type'] = 'boolean'
        val = step.get(field, spec.get('default', False))
        param['default'] = bool(val)
    elif stype in ('integer', 'number'):
        param['type'] = stype
        if 'minimum' in spec:
            param['minimum'] = spec['minimum']
        if 'maximum' in spec:
            param['maximum'] = spec['maximum']
        src_key = settings_source_for_field(op, field, step)
        if step.get(field) is None and src_key:
            param['default_source'] = src_key
        else:
            val = step.get(field, spec.get('default'))
            if val is not None:
                param['default'] = val
    elif stype == 'capture_datetime':
        param['type'] = 'capture_datetime'
        val = step.get(field, '')
        if isinstance(val, str) and val.strip():
            param['default'] = val
        else:
            param['required'] = True
    elif 'choices' in spec and not (op == 'metadata.set_capture' and field == 'timezone'):
        param['type'] = 'choice'
        param['choices'] = [
            {
                'value': choice,
                'label': (
                    'JPEG' if choice == 'jpeg' else
                    'PNG' if choice == 'png' else
                    'WebP' if choice == 'webp' else
                    'AVIF' if choice == 'avif' else
                    'TIFF' if choice == 'tiff' else
                    'sRGB' if choice == 'srgb' else
                    str(choice).replace('_', ' ').capitalize()
                ),
            }
            for choice in spec['choices']
        ]
        val = step.get(field, spec.get('default'))
        if val in spec['choices']:
            param['default'] = val
    else:
        param['type'] = 'text'
        if (op, field) in BOUND_TEXT_LIMITS:
            param['max_length'] = BOUND_TEXT_LIMITS[(op, field)]
        src_key = settings_source_for_field(op, field, step)
        if step.get(field) is None and src_key:
            param['default_source'] = src_key
        else:
            val = step.get(field, spec.get('default', ''))
            if isinstance(val, str) and val:
                param['default'] = val
            elif (op, field) not in OPTIONAL_EMPTY_TEXT_FIELDS:
                param['required'] = True

    # If the step itself has enabled_when, mirror it into visible_when so the
    # newly created parameter immediately satisfies conditional binding rules.
    if step.get('enabled_when') is not None:
        param['visible_when'] = copy.deepcopy(step['enabled_when'])

    return param


def can_reorder_parameter(recipe, index, delta):
    """Check whether moving parameters[index] by delta preserves valid dependency order."""
    params = recipe.get('parameters') or []
    target = index + delta
    if not (0 <= index < len(params) and 0 <= target < len(params)):
        return False, 'Cannot move parameter further in that direction.'

    moving = params[index]
    swapped = params[target]
    probe = copy.deepcopy(recipe)
    probe_params = probe['parameters']
    probe_params[index], probe_params[target] = probe_params[target], probe_params[index]
    try:
        validate_authored(probe)
        return True, ''
    except RecipeError:
        if delta > 0:
            return (
                False,
                f"Cannot move '{moving['label']}' down because '{swapped['label']}' "
                'depends on an earlier parameter for visibility.',
            )
        return (
            False,
            f"Cannot move '{moving['label']}' up because its visibility condition "
            f"depends on '{swapped['label']}'.",
        )
