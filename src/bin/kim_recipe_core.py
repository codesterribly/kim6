"""Declarative recipes, storage, planning and create-only batch publication."""
from kim_psd_source import source_session, parse_header as psd_header, PSDError
import argparse
import contextlib
import copy
import errno
import json
import os
from pathlib import Path
import re
import stat
import string
import sys
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field


if __name__ == '__main__':
    sys.modules['kim_recipe_core'] = sys.modules[__name__]


CONCRETE_SCHEMA = 3
AUTHORED_SCHEMA = 4
LIBRARY_SCHEMA = 5
REMEMBERED_SCHEMA = 1
REMEMBERED_LIMIT = 256 * 1024


def _validate_persisted_recipe(recipe):
    """Validate one persisted authored Recipe definition (fixed or parameterized)."""
    from kim_recipe_params import validate_authored
    return validate_authored(recipe)


class RecipeError(ValueError):
    pass


class OutputFormatRequired(RecipeError):
    # A planner diagnosis, not a guess based on a filename or message text.
    repair = 'add_convert_format'


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RecipeError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(RecipeError('Invalid number')))
    except (ValueError, TypeError) as exc:
        raise RecipeError(str(exc)) from exc


def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise RecipeError('Unexpected or missing fields: ' + str(required))


def text(value, limit=500):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise RecipeError('Invalid text')
    return value


def component(value):
    text(value, 180)
    if not value or value in ('.', '..') or '/' in value or '\\' in value:
        raise RecipeError('Expected one safe filename component')
    return value


SUBFOLDER_DATE_TOKENS = ('year', 'capture_date')


def subfolder_parts(value, *, allow_date_tokens=False):
    """Validate a relative single- or multi-component subfolder path."""
    text(value, 500)
    if not value or value.startswith('/') or value.endswith('/') or '\\' in value:
        raise RecipeError('Expected a safe relative subfolder path')
    parts = value.split('/')
    if not 1 <= len(parts) <= 8:
        raise RecipeError('Subfolder path must have 1 to 8 directory levels')
    for part in parts:
        if not part or part in ('.', '..'):
            raise RecipeError('Expected a safe relative subfolder path')
        if allow_date_tokens and ('{year}' in part or '{capture_date}' in part):
            sample = part.replace('{year}', '2026').replace('{capture_date}', '2026-11-20')
            component(sample)
        else:
            component(part)
    return tuple(parts)


def pattern(value):
    text(value, 180)
    try:
        for _, name, spec, conversion in string.Formatter().parse(value):
            if name is not None and (name not in ('filename', 'stem', 'date', 'index') or spec or conversion):
                raise RecipeError('Naming allows only {filename}, {date}, {index}')
        component(format_output_pattern(value,'vacation','20000101_120000',1))
    except (ValueError, KeyError) as exc:
        raise RecipeError('Invalid output template') from exc


def format_output_pattern(value, filename, date='', index=1):
    # {stem} remains a storage-compatible alias. Both names mean the original
    # filename without its extension, including during pinned-source execution.
    return value.format(filename=filename,stem=filename,date=date,index=index)


def display_output_pattern(value):
    """Show the approved token without rewriting a saved legacy definition.

    Re-escape literal braces so a literal {{stem}} is never changed into a
    token or a different literal filename when the user edits the field.
    """
    try:
        parts=[]
        for literal,name,spec,conversion in string.Formatter().parse(value):
            parts.append(literal.replace('{','{{').replace('}','}}'))
            if name is not None:
                parts.append('{'+('filename' if name=='stem' else name)+
                             ('!'+conversion if conversion else '')+(':'+spec if spec else '')+'}')
        return ''.join(parts)
    except ValueError:
        return value


def handler(media):
    if isinstance(media, str) and media == 'image':
        from kim_recipe_image import ImageHandler
        return ImageHandler()
    raise RecipeError('Unsupported media handler: ' + str(media))


def enabled_steps(steps):
    return [step for step in steps if step.get('enabled', True)]


def validate(recipe):
    keys(recipe, ('schema', 'id', 'name', 'description', 'media', 'steps', 'destination'), ('folder', 'dolphin_shortcut'))
    if 'dolphin_shortcut' in recipe and type(recipe['dolphin_shortcut']) is not bool:
        raise RecipeError('Dolphin shortcut must be boolean')
    if type(recipe['schema']) is not int or recipe['schema'] != 3:
        raise RecipeError('Unsupported recipe schema')
    if not isinstance(recipe['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['id']):
        raise RecipeError('Invalid recipe id')
    if 'folder' in recipe and (not isinstance(recipe['folder'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['folder'])):
        raise RecipeError('Invalid recipe folder id')
    if not text(recipe['name'], 100).strip():
        raise RecipeError('Recipe name is empty')
    description = recipe['description']
    if (
        not isinstance(description, str)
        or len(description) > 5000
        or any(
            ord(character) < 32 and ord(character) not in (9, 10, 13)
            for character in description
        )
    ):
        raise RecipeError(
            'Recipe description must be text of at most 5000 characters'
        )
    destination = recipe['destination']
    keys(destination, ('mode',), ('folder', 'path', 'ask'))
    mode = destination['mode']
    if mode == 'beside':
        keys(destination, ('mode',))
    elif mode == 'subfolder':
        keys(destination, ('mode', 'folder'))
        subfolder_parts(destination['folder'], allow_date_tokens=True)
    elif mode == 'directory':
        keys(destination, ('mode', 'ask'), ('path',))
        if type(destination['ask']) is not bool:
            raise RecipeError('ask must be boolean')
        if 'path' in destination:
            text(destination['path'], 4096)
            if not Path(destination['path']).is_absolute():
                raise RecipeError('Destination path must be absolute')
        if not destination['ask'] and not destination.get('path'):
            raise RecipeError('Destination directory required')
    else:
        raise RecipeError('Unknown destination mode')
    steps = recipe['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= 50:
        raise RecipeError('Expected 1–50 ordered steps')
    media_handler = handler(recipe['media'])
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get('op'), str):
            raise RecipeError('Invalid step')
        if type(step.get('enabled', True)) is not bool:
            raise RecipeError('Step enabled must be boolean')
        if step.get('op') == 'file.rename_output':
            keys(step, ('op', 'pattern'), ('enabled',))
            pattern(step['pattern'])
        elif step.get('op') in ('file.sync_date','file.preserve_date'):
            keys(step, ('op',), ('enabled',))
        else:
            media_handler.validate_step(step)
    media_handler.validate_order(enabled_steps(steps))
    return copy.deepcopy(recipe)



def read_portable_recipe(path):
    """Read a bounded, validated individual authored Recipe (schema 4)."""
    fd = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RecipeError('Recipe import requires a regular file')
        payload = stream.read(131073)

    if len(payload) > 131072:
        raise RecipeError('Recipe file exceeds 128 KiB')

    try:
        decoded = payload.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise RecipeError('Recipe file is not UTF-8') from exc

    recipe = strict_json(decoded)
    if not isinstance(recipe, dict):
        raise RecipeError('Expected one Recipe JSON object')
    if 'folder' in recipe or 'dolphin_shortcut' in recipe:
        raise RecipeError(
            'Individual Recipe files cannot assign local library settings'
        )
    return _validate_persisted_recipe(recipe)


def write_portable_recipe(recipe, path):
    """Export one authored Recipe without overwriting an existing file."""
    portable = _validate_persisted_recipe(copy.deepcopy(recipe))
    portable.pop('folder', None)
    portable.pop('dolphin_shortcut', None)

    data = (
        json.dumps(portable, indent=2, ensure_ascii=False) + '\n'
    ).encode('utf-8')

    if len(data) > 131072:
        raise RecipeError('Recipe file exceeds 128 KiB')

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)

    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # Only remove our newly created, incomplete output.
        try:
            os.unlink(path)
        except OSError:
            pass
        raise



BUNDLE_KIND = 'kimng-recipe-bundle'
BUNDLE_LIMIT = 2 * 1024 * 1024


def validate_recipe_bundle(data):
    keys(data, ('schema', 'kind', 'recipes', 'folders'))
    if type(data['schema']) is not int or data['schema'] != LIBRARY_SCHEMA:
        raise RecipeError('Unsupported Recipe bundle schema')
    if data['kind'] != BUNDLE_KIND:
        raise RecipeError('Not a KIMng Recipe bundle')

    library = validate_library({
        'schema': LIBRARY_SCHEMA,
        'recipes': data['recipes'],
        'folders': data['folders'],
    })
    if not library.recipes:
        raise RecipeError('Recipe bundle contains no Recipes')
    return library


def read_recipe_bundle(path):
    """Read and fully validate one bounded Recipe library bundle."""
    fd = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RecipeError('Bundle must be a regular file')
        payload = stream.read(BUNDLE_LIMIT + 1)

    if len(payload) > BUNDLE_LIMIT:
        raise RecipeError('Recipe bundle exceeds 2 MiB')

    try:
        decoded = payload.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise RecipeError('Bundle must be UTF-8 JSON') from exc

    return validate_recipe_bundle(strict_json(decoded))


def write_recipe_bundle(library, path):
    """Export the saved user library without overwriting any file."""
    contents = {
        'schema': LIBRARY_SCHEMA,
        'kind': BUNDLE_KIND,
        'folders': copy.deepcopy(library.folders),
        'recipes': copy.deepcopy(library.recipes),
    }
    for recipe in contents['recipes']:
        recipe['dolphin_shortcut'] = False
    validate_recipe_bundle(contents)

    payload = (
        json.dumps(contents, ensure_ascii=False, indent=2) + '\n'
    ).encode('utf-8')

    if len(payload) > BUNDLE_LIMIT:
        raise RecipeError('Recipe bundle exceeds 2 MiB')

    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def merge_recipe_bundle(existing, imported, shipped=()):
    """Return a new validated library without changing existing data."""
    existing = validate_library({
        'schema': LIBRARY_SCHEMA,
        'recipes': existing.recipes,
        'folders': existing.folders,
    })
    imported = validate_library({
        'schema': LIBRARY_SCHEMA,
        'recipes': imported.recipes,
        'folders': imported.folders,
    })

    result = copy.deepcopy(existing)
    folder_map = {
        folder['id']: 'folder-' + uuid.uuid4().hex
        for folder in imported.folders
    }

    # Reconstruct imported hierarchy using new local identities.
    # Same-named sibling folders receive an imported suffix.
    for folder in imported.folders:
        parent_id = folder_map.get(folder['parent_id'])
        candidate = folder['name']
        number = 1

        while any(
            f['parent_id'] == parent_id
            and name_key(f['name']) == name_key(candidate)
            for f in result.folders
        ):
            suffix = (
                ' (imported)' if number == 1
                else f' (imported {number})'
            )
            candidate = folder['name'][:60-len(suffix)] + suffix
            number += 1

        result.folders.append({
            'id': folder_map[folder['id']],
            'name': candidate,
            'parent_id': parent_id,
        })


    occupied_names = {
        name_key(recipe['name'])
        for recipe in result.recipes + list(shipped)
    }
    imported_ids = []

    for recipe in imported.recipes:
        item = copy.deepcopy(recipe)
        original_name = item['name']
        candidate = original_name
        number = 1

        while name_key(candidate) in occupied_names:
            suffix = (
                ' (imported)' if number == 1
                else f' (imported {number})'
            )
            candidate = original_name[:100 - len(suffix)] + suffix
            number += 1

        item['name'] = candidate
        occupied_names.add(name_key(candidate))

        # Imported IDs must never collide with existing or built-in IDs.
        item['id'] = 'user-' + uuid.uuid4().hex
        imported_ids.append(item['id'])

        original_folder = item.get('folder')
        if original_folder is not None:
            item['folder'] = folder_map[original_folder]
        item['dolphin_shortcut'] = False

        result.recipes.append(_validate_persisted_recipe(item))

    result = validate_library({
        'schema': LIBRARY_SCHEMA,
        'recipes': result.recipes,
        'folders': result.folders,
    })
    return result, imported_ids


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'kimng' / 'recipes.json'


def remembered_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'kimng' / 'recipe_remembered.json'


def _read_remembered_store(path=None):
    target = Path(path or remembered_path())
    if not os.path.lexists(target):
        return {}
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return {}
            payload = stream.read(REMEMBERED_LIMIT + 1)
    except OSError:
        return {}
    if len(payload) > REMEMBERED_LIMIT:
        return {}
    try:
        data = strict_json(payload)
    except RecipeError:
        return {}
    if (
        not isinstance(data, dict)
        or data.get('schema') != REMEMBERED_SCHEMA
        or not isinstance(data.get('recipes'), dict)
    ):
        return {}
    cleaned = {}
    for rid, mapping in data['recipes'].items():
        if isinstance(rid, str) and isinstance(mapping, dict):
            cleaned[rid] = {
                pid: copy.deepcopy(val)
                for pid, val in mapping.items()
                if isinstance(pid, str) and val is not None
            }
    return cleaned


def _write_remembered_store(store, path=None):
    target = Path(path or remembered_path())
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.resolve() != target.parent.absolute() or (
        os.path.lexists(target)
        and (target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1)
    ):
        raise RecipeError('Unsafe remembered-answers storage')
    data = {
        'schema': REMEMBERED_SCHEMA,
        'recipes': {
            rid: mapping for rid, mapping in store.items()
            if isinstance(rid, str) and isinstance(mapping, dict) and mapping
        },
    }
    encoded = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if len(encoded) > REMEMBERED_LIMIT:
        raise RecipeError('Remembered-answers storage exceeds size limit')
    with tempfile.NamedTemporaryFile(
        mode='wb', dir=target.parent, prefix='.recipe-remembered-', delete=False
    ) as stream:
        stage = Path(stream.name)
        try:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(stage, target)
        finally:
            stage.unlink(missing_ok=True)


def load_remembered_values(recipe_id, path=None):
    """Load local remembered answers for one saved Recipe ID (never raises on missing)."""
    if not isinstance(recipe_id, str) or not recipe_id:
        return {}
    store = _read_remembered_store(path=path)
    return copy.deepcopy(store.get(recipe_id, {}))


def save_remembered_values(recipe_id, values, path=None):
    """Atomically save remembered answers for one saved Recipe ID with 0600 permissions."""
    if not isinstance(recipe_id, str) or not recipe_id:
        return
    store = _read_remembered_store(path=path)
    cleaned = {
        pid: copy.deepcopy(val)
        for pid, val in (values or {}).items()
        if isinstance(pid, str) and val is not None
    }
    if cleaned:
        store[recipe_id] = cleaned
    else:
        store.pop(recipe_id, None)
    _write_remembered_store(store, path=path)


def clear_remembered_values(recipe_id, param_ids=None, path=None):
    """Remove remembered answers for one Recipe ID (or specific parameter IDs)."""
    if not isinstance(recipe_id, str) or not recipe_id:
        return
    target = Path(path or remembered_path())
    if not os.path.lexists(target):
        return
    store = _read_remembered_store(path=target)
    if recipe_id not in store:
        return
    if param_ids is None:
        store.pop(recipe_id, None)
    else:
        entry = store[recipe_id]
        changed = False
        for pid in param_ids:
            if pid in entry:
                entry.pop(pid, None)
                changed = True
        if not changed:
            return
        if not entry:
            store.pop(recipe_id, None)
    _write_remembered_store(store, path=target)


def folder_name(value):
    component(value)
    if len(value) > 60 or value != value.strip() or any(unicodedata.category(c).startswith('C') for c in value):
        raise RecipeError('Folder names must be 1–60 characters, without controls or surrounding spaces')
    if name_key(value) in (
        'root', 'unfiled', 'built-in', 'built-ins', 'user'
    ):
        raise RecipeError('This folder name is reserved for a library presentation group')
    return value


def name_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


@dataclass
class RecipeLibrary:
    recipes: list = field(default_factory=list)
    folders: list = field(default_factory=list)

    def find_folder(self, folder_id):
        for folder in self.folders:
            if folder['id'] == folder_id:
                return folder
        raise RecipeError('Unknown Recipe folder')

    def check_folder_name(self, name, parent_id, exclude=None):
        name = folder_name(name)
        if parent_id is not None:
            self.find_folder(parent_id)
        if any(
            f['id'] != exclude
            and f['parent_id'] == parent_id
            and name_key(f['name']) == name_key(name)
            for f in self.folders
        ):
            raise RecipeError('A sibling folder already uses this name')
        return name

    def create_folder(self, name, parent_id=None):
        name = self.check_folder_name(name, parent_id)
        folder = {
            'id': 'folder-' + uuid.uuid4().hex,
            'name': name,
            'parent_id': parent_id,
        }
        self.folders.append(folder)
        return folder['id']

    def rename_folder(self, folder_id, name):
        folder = self.find_folder(folder_id)
        folder['name'] = self.check_folder_name(
            name, folder['parent_id'], exclude=folder_id
        )

    def descendants(self, folder_id):
        self.find_folder(folder_id)
        result = {folder_id}
        while True:
            children = {
                f['id'] for f in self.folders
                if f['parent_id'] in result
            }
            expanded = result | children
            if expanded == result:
                return result
            result = expanded

    def move_folder(self, folder_id, parent_id=None):
        folder = self.find_folder(folder_id)
        if parent_id in self.descendants(folder_id):
            raise RecipeError('A folder cannot contain itself')
        self.check_folder_name(
            folder['name'], parent_id, exclude=folder_id
        )
        folder['parent_id'] = parent_id

    def delete_folder(self, folder_id):
        removed = self.descendants(folder_id)
        self.folders = [
            f for f in self.folders if f['id'] not in removed
        ]
        for recipe in self.recipes:
            if recipe.get('folder') in removed:
                recipe.pop('folder', None)

    def move_recipe(self, recipe_id, folder_id=None):
        if folder_id is not None:
            self.find_folder(folder_id)
        for recipe in self.recipes:
            if recipe['id'] == recipe_id:
                if folder_id is None:
                    recipe.pop('folder', None)
                else:
                    recipe['folder'] = folder_id
                return
        raise RecipeError('Unknown user Recipe')


def validate_library(data):
    keys(data, ('schema', 'recipes', 'folders'))

    if type(data['schema']) is not int or data['schema'] != LIBRARY_SCHEMA:
        raise RecipeError('Unsupported Recipe library schema')

    if not isinstance(data['recipes'], list) or len(data['recipes']) > 500:
        raise RecipeError('Invalid Recipe collection')

    if not isinstance(data['folders'], list) or len(data['folders']) > 100:
        raise RecipeError('Invalid Recipe folders')

    folders = copy.deepcopy(data['folders'])

    for folder in folders:
        keys(folder, ('id', 'name', 'parent_id'))

        if not isinstance(folder['id'], str) or not re.fullmatch(
            r'[a-z0-9][a-z0-9-]{0,79}', folder['id']
        ):
            raise RecipeError('Invalid folder ID')

        if folder['parent_id'] is not None and not isinstance(
            folder['parent_id'], str
        ):
            raise RecipeError('Invalid folder parent ID')

        folder_name(folder['name'])

    by_id = {f['id']: f for f in folders}

    if len(by_id) != len(folders):
        raise RecipeError('Duplicate folder ID')

    siblings = {
        (f['parent_id'], name_key(f['name'])) for f in folders
    }

    if len(siblings) != len(folders):
        raise RecipeError('Duplicate sibling folder name')

    for folder in folders:
        seen = {folder['id']}
        parent_id = folder['parent_id']

        while parent_id is not None:
            if parent_id not in by_id:
                raise RecipeError('Folder references a missing parent')
            if parent_id in seen:
                raise RecipeError('Circular folder hierarchy')
            seen.add(parent_id)
            parent_id = by_id[parent_id]['parent_id']

    recipes = [_validate_persisted_recipe(item) for item in data['recipes']]

    if len({r['id'] for r in recipes}) != len(recipes):
        raise RecipeError('Duplicate Recipe ID')

    for recipe in recipes:
        if type(recipe.get('dolphin_shortcut')) is not bool:
            raise RecipeError('User Recipe requires explicit shortcut membership')

        if 'folder' in recipe and recipe['folder'] not in by_id:
            raise RecipeError('Recipe references a missing folder')

    return RecipeLibrary(recipes, folders)


def read_library(path, missing=False):
    if missing and not os.path.lexists(path):
        return RecipeLibrary()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding='utf-8') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RecipeError('Recipe storage must be a regular file')
        payload = stream.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise RecipeError('Recipe library exceeds size limit')
    return validate_library(strict_json(payload))


def read_recipes(path, missing=False):
    return read_library(path, missing).recipes


BUILTIN_CATEGORIES = (
    'Common',
    'Adventure',
    'Asset Management',
)


def builtin_catalog():
    path = Path(__file__).resolve().parent.parent / 'recipes' / 'builtins.json'
    data = strict_json(path.read_text(encoding='utf-8'))

    if not isinstance(data, list):
        raise RecipeError('Invalid built-in Recipe collection')

    entries = []
    seen = set()

    for item in data:
        if not isinstance(item, dict):
            raise RecipeError('Invalid built-in Recipe entry')

        definition = copy.deepcopy(item)
        category = definition.pop('category', None)

        if category not in BUILTIN_CATEGORIES:
            raise RecipeError('Invalid built-in Recipe category')

        recipe = _validate_persisted_recipe(definition)

        if 'folder' in recipe or 'dolphin_shortcut' in recipe:
            raise RecipeError('Built-in recipes must remain unfiled')

        if recipe['id'] in seen:
            raise RecipeError('Duplicate built-in Recipe id')

        seen.add(recipe['id'])
        entries.append((category, recipe))

    return entries


def builtins():
    return [recipe for _, recipe in builtin_catalog()]


def load_library():
    library = read_library(config_path(), missing=True)
    if {r['id'] for r in library.recipes} & {r['id'] for r in builtins()}:
        raise RecipeError('User recipe uses a reserved built-in id')
    return library


def load_users():
    return load_library().recipes


def lookup_recipe(recipe_id):
    if not isinstance(recipe_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe_id):
        raise RecipeError('Invalid recipe id')
    for recipe in builtins() + load_users():
        if recipe['id'] == recipe_id:
            return copy.deepcopy(recipe)
    raise RecipeError('Unknown saved recipe id: ' + recipe_id)


def folder_label(folder):
    return folder['name']


def folder_path(folder_id, folders):
    by_id = {folder['id']: folder for folder in folders}
    names = []
    seen = set()

    while folder_id is not None:
        if folder_id in seen or folder_id not in by_id:
            raise RecipeError('Invalid folder hierarchy')
        seen.add(folder_id)
        folder = by_id[folder_id]
        names.append(folder['name'])
        folder_id = folder['parent_id']

    return ' / '.join(reversed(names))


def builtin_category(recipe):
    for category, definition in builtin_catalog():
        if definition['id'] == recipe['id']:
            return category
    raise RecipeError('Unknown built-in Recipe category')


def recipe_title(recipe, folders=()):
    if recipe.get('folder'):
        return 'User / ' + folder_path(
            recipe['folder'], folders
        ) + ' / ' + recipe['name']

    if 'dolphin_shortcut' not in recipe:
        return 'Built-ins / ' + builtin_category(
            recipe
        ) + ' / ' + recipe['name']

    return 'User / Unfiled / ' + recipe['name']


def library_groups(library, shipped=None):
    ordered = lambda recipes: sorted(
        recipes, key=lambda r: (r['name'].casefold(), r['id'])
    )

    catalog = builtin_catalog()
    categories = {
        recipe['id']: category
        for category, recipe in catalog
    }
    shipped = (
        [recipe for _, recipe in catalog]
        if shipped is None else shipped
    )
    groups = []

    for category in BUILTIN_CATEGORIES:
        groups.append((
            None,
            'Built-ins / ' + category,
            ordered([
                r for r in shipped
                if categories.get(r['id']) == category
            ]),
        ))

    groups.append((
        '',
        'User / Unfiled',
        ordered([
            r for r in library.recipes if 'folder' not in r
        ]),
    ))

    for folder in sorted(
        library.folders,
        key=lambda f: folder_path(
            f['id'], library.folders
        ).casefold(),
    ):
        groups.append((
            folder['id'],
            'User / ' + folder_path(folder['id'], library.folders),
            ordered([
                r for r in library.recipes
                if r.get('folder') == folder['id']
            ]),
        ))

    return groups


def save_library(library, path=None):
    path = Path(path or config_path())
    data = {'schema': LIBRARY_SCHEMA, 'recipes': library.recipes, 'folders': library.folders}
    validated = validate_library(data)
    if {r['id'] for r in validated.recipes} & {r['id'] for r in builtins()}:
        raise RecipeError('Duplicate or reserved recipe id')
    def shortcuts(items):
        return sorted((r['id'], r['name']) for r in items if r['dolphin_shortcut'])
    previous = read_library(path, missing=True)
    shortcuts_changed = shortcuts(previous.recipes) != shortcuts(validated.recipes)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.resolve() != path.parent.absolute() or (os.path.lexists(path) and (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1)):
        raise RecipeError('Unsafe recipe storage')
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.recipes-', delete=False) as stream:
        stage = Path(stream.name)
        try:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(stage, path)
        finally:
            stage.unlink(missing_ok=True)
    if path == config_path() and shortcuts_changed:
        try:
            from kim_recipe_menu import sync_menu
            sync_menu()
        except (OSError, RecipeError) as exc:
            return 'Recipe saved, but shortcuts could not be updated: ' + str(exc) + '\nRetry: kim_all recipe --sync-menu (from the active installation), or reinstall KIMng to a writable user prefix.'
    return None


def save_users(recipes, path=None):
    destination = Path(path or config_path())
    if os.path.lexists(destination) and (destination.is_symlink() or not destination.is_file() or destination.stat().st_nlink != 1):
        raise RecipeError('Unsafe recipe storage')
    folders = read_library(destination, missing=True).folders
    return save_library(RecipeLibrary(recipes, folders), destination)


@dataclass
class PreviewRow:
    source: str
    output: str = ''
    media: str = ''
    format: str = 'unknown'
    properties: dict = field(default_factory=dict)
    metadata: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    certainty: str = 'This exact output path is binding. A collision blocks publication; review again to change it.'
    warnings: list = field(default_factory=list)
    identity: tuple | None = None
    approved: 'ApprovedOutput | None' = None


@dataclass(frozen=True)
class ApprovedOutput:
    """Value snapshot of one reviewed source, destination and operation plan.

    JSON keeps nested recipe/state dictionaries immutable too. Each execution
    receives its own decoded state; it never consults the planner for a new name.
    """
    source: str
    identity: tuple
    output: str
    destination: tuple
    recipe_json: str
    state_json: str


def source_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def directory_binding(directory):
    """Bind every path component without following symlinks, including ancestors.

    Only the final component may be absent (a new approved directory). Its
    existing parent is still bound and mkdir must subsequently create it anew.
    """
    directory = Path(directory)
    fd = os.open(directory.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identities = [source_identity(os.fstat(fd))[:2]]
    try:
        for index, part in enumerate(directory.parts[1:], 1):
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                for remaining in directory.parts[index:]:
                    component(remaining)
                    identities.append(None)
                break
            os.close(fd)
            fd = child
            identities.append(source_identity(os.fstat(fd))[:2])
    finally:
        os.close(fd)
    return tuple(identities)


def output_key(item):
    path = Path(item.output)
    dest = item.destination
    deepest = next((i for i in range(len(dest) - 1, -1, -1) if dest[i] is not None), 0)
    return (dest[deepest], tuple(path.parts[deepest + 1:]))


def block_output_collisions(rows):
    """Mark all duplicate destination entries, including aliased directory paths."""
    outputs = {}
    for row in rows:
        if row.approved is None: continue
        outputs.setdefault(output_key(row.approved), []).append(row)
    for duplicates in outputs.values():
        if len(duplicates) > 1:
            for row in duplicates:
                issue = 'Output collision: multiple selected sources target ' + row.output
                if issue not in row.problems: row.problems.append(issue)


def approve_rows(recipe, sources, rows, chosen=None):
    """Freeze precisely the rows shown by Review Changes, without re-planning."""
    recipe = validate(recipe)
    rows = list(rows)
    block_output_collisions(rows)
    if len(rows) != len(sources) or not rows:
        raise RecipeError('Review every selected source before applying')
    approved = []
    for source, row in zip(sources, rows):
        item = row.approved
        if row.problems:
            raise RecipeError('Publication blocked: ' + '; '.join(row.problems))
        item_state = json.loads(item.state_json) if item is not None else None
        directory = destination_for(recipe, Path(os.path.abspath(source)), chosen, state=item_state)
        if directory is None:
            raise RecipeError('Choose a destination directory before applying')
        if (item is None or item.source != os.path.abspath(source)
                or row.output != item.output or row.identity != item.identity
                or json.loads(item.recipe_json) != recipe):
            raise RecipeError('Review changed: source, output or operations no longer match the inspected plan')
        if directory != Path(item.output).parent:
            raise RecipeError('Review changed: destination no longer matches the inspected plan')
        approved.append(item)
    return tuple(approved)


@dataclass
class Plan:
    recipe: dict
    source: Path
    directory: Path | None
    name: str
    state: object
    row: PreviewRow


def destination_for(recipe, source, chosen=None, create=False, *, state=None):
    dest = recipe['destination']
    if dest['mode'] == 'beside':
        directory = source.parent
    elif dest['mode'] == 'subfolder':
        parts = subfolder_parts(dest['folder'], allow_date_tokens=True)
        resolved_parts = []
        for part in parts:
            if '{year}' in part or '{capture_date}' in part:
                if state is None or not state.get('capture_year') or not state.get('capture_date_iso'):
                    detail = (state or {}).get('capture_problem') or 'no usable embedded capture date was found'
                    raise RecipeError(
                        'Capture date metadata is missing or invalid ('
                        + str(detail)
                        + '). Organize by Capture Date requires a reliable embedded capture date and never substitutes file modification time.'
                    )
                part = part.replace('{year}', state['capture_year']).replace('{capture_date}', state['capture_date_iso'])
            resolved_parts.append(component(part))
        if chosen:
            root = Path(chosen)
            if not root.is_absolute():
                raise RecipeError('Choose a destination directory')
        else:
            root = source.parent
        directory = root
        for part in resolved_parts:
            directory = directory / part
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                raise RecipeError('Subfolder destination is a symlink' if directory.is_symlink() else 'Unsafe destination directory')
            if create and not directory.exists():
                directory.mkdir(mode=0o700)
    else:
        if dest['ask'] and not chosen and not create:
            return None
        directory = Path(chosen or ('' if dest['ask'] else dest.get('path', '')))
        if not directory.is_absolute():
            raise RecipeError('Choose a destination directory')
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise RecipeError('Unsafe destination directory')
    if not directory.exists():
        if create:
            raise RecipeError('Destination directory does not exist')
        if dest['mode'] != 'subfolder' and not directory.parent.is_dir():
            raise RecipeError('Destination directory does not exist')
    check = directory
    while not check.exists() and check != check.parent:
        if check.is_symlink():
            raise RecipeError('Unsafe destination directory')
        check = check.parent
    if check.is_symlink() or not check.is_dir():
        raise RecipeError('Unsafe destination directory')
    if not os.access(check, os.W_OK | os.X_OK):
        raise RecipeError('Destination is not writable')
    return directory.absolute()


def plan(recipe, source, index=1, chosen=None, create=False):
    recipe = validate(recipe)
    source = Path(os.path.abspath(source))
    if source.is_symlink() or not source.is_file():
        raise RecipeError('Source must be a regular file, not a symlink')
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise RecipeError('Source must be a regular file, not a symlink')
    state = handler(recipe['media']).plan(source, recipe['steps'], index)
    after = source.lstat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise RecipeError('Source changed during inspection; try again')
    directory = destination_for(recipe, source, chosen, create, state=state)
    binding = directory_binding(directory) if directory is not None else None
    from kim_process import stage as job_stage
    job_stage('Planning output filename')
    name = component(state['name']) + '.' + state['extension']
    proposed = str(directory / name) if directory is not None else '<choose directory at run>/' + name
    row = PreviewRow(str(source), proposed, recipe['media'], state['format'],
                     state['properties'], state['metadata'])
    row.identity = source_identity(before)
    row.warnings.extend(state.get('warnings', []))
    row.properties['_proposed_output'] = proposed
    if directory is not None:
        if directory_binding(directory) != binding:
            raise RecipeError('Destination directory changed during inspection; review again')
        row.approved = ApprovedOutput(str(source), row.identity, proposed,
                                      binding, json.dumps(recipe), json.dumps(state))
        if os.path.lexists(directory / name):
            row.problems.append('Output collision: approved filename already exists: ' + proposed)
    return Plan(recipe, source, directory, name, state, row)


@contextlib.contextmanager
def recipe_inspections():
    from kim_image_ops import logo_inspections
    with logo_inspections(): yield


def number_review_outputs(rows):
    """Choose collision-free names before approval, never during publication.

    This is a planning-only operation. Output publication remains atomic
    and no-replace, using the exact reviewed target.
    """
    reserved = set()

    for row in rows:
        item = row.approved
        if item is None:
            continue

        original = Path(item.output)
        candidate = original
        number = 0

        def reserved_key(path):
            return output_key(
                ApprovedOutput(
                    item.source,
                    item.identity,
                    str(path),
                    item.destination,
                    item.recipe_json,
                    item.state_json,
                )
            )

        while os.path.lexists(candidate) or reserved_key(candidate) in reserved:
            number += 1
            if number > 10000:
                row.problems.append(
                    "Unable to find a free numbered output filename"
                )
                break
            candidate = original.with_name(
                f"{original.stem}_{number}{original.suffix}"
            )

        if number > 10000:
            continue

        reserved.add(reserved_key(candidate))

        if candidate != original:
            row.output = str(candidate)
            row.approved = ApprovedOutput(
                item.source,
                item.identity,
                str(candidate),
                item.destination,
                item.recipe_json,
                item.state_json,
            )
            row.problems = [
                problem for problem in row.problems
                if not problem.startswith(
                    "Output collision: approved filename already exists:"
                )
            ]
            row.certainty = (
                "Existing filename collision resolved during review. "
                "The numbered filename is binding; a later collision "
                "requires another review."
            )

    return rows


@recipe_inspections()
def preview(recipe, sources, chosen=None, start_index=1,
            number_collisions=False):
    rows = []
    for index, source in enumerate(sources, start_index):
        with source_session():
            try:
                rows.append(plan(recipe, source, index, chosen).row)
            except (OSError, RecipeError, UnicodeError) as exc:
                row = PreviewRow(str(source), problems=[str(exc)])
                try:
                    from kim_process import cancelled
                    if not cancelled() and Path(source).is_file() and not Path(source).is_symlink():
                        row.properties = handler(recipe['media']).source_properties(Path(source))
                except (OSError, RecipeError, KeyError):
                    pass
                if getattr(exc,'repair',None): row.properties['_repair'] = exc.repair
                rows.append(row)
    if number_collisions:
        number_review_outputs(rows)
    block_output_collisions(rows)
    return rows


def publish(stage, directory_fd, name):
    """Publish a completed file with one atomic no-replace link; never renumber.

    The private stage remains until caller cleanup. After linking, failures must
    never remove the final entry: it is already a successfully published output.
    """
    component(name)
    stage_fd = os.open(stage, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(stage_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0 or info.st_nlink != 1:
            raise RecipeError('Missing or invalid staged output')
        if info.st_dev != os.fstat(directory_fd).st_dev:
            raise RecipeError('Unsupported destination filesystem: staging must be on the destination filesystem')
        try:
            os.fsync(stage_fd)
            # Check directory fsync support before making anything visible.
            os.fsync(directory_fd)
        except OSError as exc:
            if exc.errno in (errno.EINVAL, errno.EOPNOTSUPP, errno.ENOSYS):
                raise RecipeError('Unsupported destination filesystem: completed-file durability synchronization unavailable: ' + str(exc)) from exc
            raise
        if source_identity(os.stat(stage, follow_symlinks=False)) != source_identity(info):
            raise RecipeError('Staged output changed before publication')
        from kim_process import checkpoint
        checkpoint()
    finally:
        os.close(stage_fd)
    # All writers and the synchronization descriptor are closed before linking.
    try:
        os.link(stage, name, dst_dir_fd=directory_fd, follow_symlinks=False)
    except FileExistsError as exc:
        raise RecipeError('Output collision: approved filename already exists: ' + name) from exc
    except OSError as exc:
        if exc.errno in (errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS, errno.EXDEV, errno.EINVAL):
            raise RecipeError('Unsupported destination filesystem: atomic no-replace hard-link publication unavailable: ' + str(exc)) from exc
        raise
    return name


def verify_directory_binding(directory, binding):
    try:
        if directory_binding(directory) == binding: return
    except OSError:
        pass
    raise RecipeError('Destination directory changed since review; review again')


def open_approved_directory(item, cache, stack):
    directory = Path(item.output).parent
    key = str(directory)
    created_map = cache.setdefault('_created', {})
    if key in cache:
        fd, binding, reviewed = cache[key]
        if reviewed != item.destination:
            raise RecipeError('Destination directory changed between reviewed sources')
    else:
        expected = item.destination
        deepest = next((i for i in range(len(expected) - 1, -1, -1) if expected[i] is not None), 0)
        parts = directory.parts
        # Build effective expected prefix, accepting directories created by THIS batch only.
        effective_expected = list(expected)
        cur_path = Path(parts[0])
        for i in range(1, len(parts)):
            cur_path = cur_path / parts[i]
            if i > deepest and str(cur_path) in created_map:
                effective_expected[i] = created_map[str(cur_path)]
        verify_directory_binding(directory, tuple(effective_expected))

        # Walk from deepest existing/batch-created ancestor to target, creating missing levels safely.
        cur_fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            cur_path = Path(parts[0])
            for i in range(1, len(parts)):
                part = parts[i]
                cur_path = cur_path / part
                exp_id = effective_expected[i]
                if exp_id is None:
                    # Must not exist yet (any independent creation fails closed).
                    os.mkdir(part, mode=0o700, dir_fd=cur_fd)
                    os.fsync(cur_fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=cur_fd)
                os.close(cur_fd)
                cur_fd = child
                actual_id = source_identity(os.fstat(cur_fd))[:2]
                if exp_id is not None and actual_id != exp_id:
                    raise RecipeError('Destination directory changed since review')
                if exp_id is None:
                    created_map[str(cur_path)] = actual_id
            fd = cur_fd
            cur_fd = None
        finally:
            if cur_fd is not None:
                os.close(cur_fd)

        stack.callback(os.close, fd)
        binding = directory_binding(directory)
        if binding[:deepest + 1] != expected[:deepest + 1] or source_identity(os.fstat(fd))[:2] != binding[-1]:
            raise RecipeError('Destination directory changed since review')
        cache[key] = fd, binding, item.destination
    verify_directory_binding(directory, binding)
    return fd, binding


@recipe_inspections()
def execute(recipe, sources, chosen=None, progress=None, start_index=1,
            approved_plan=None, started=None, stop_on_error=False):
    """Execute immutable reviewed outputs, or bind a direct/CLI batch once.

    GUI callers must supply their review snapshot. Direct callers retain their
    existing interface, with one complete preflight before any publication.
    """
    recipe = validate(recipe)
    sources = list(sources)
    from kim_process import open_inspection_fd, cancelled, checkpoint, stage as job_stage, ProcessError
    try:
        if approved_plan is None:
            approved_plan = approve_rows(recipe, sources,
                preview(recipe, sources, chosen, start_index), chosen)
        approved_plan = tuple(approved_plan)
        if len(approved_plan) != len(sources):
            raise RecipeError('Approved plan does not match the selected sources')
        outputs = set()
        for source, item in zip(sources, approved_plan):
            if (not isinstance(item, ApprovedOutput) or item.source != os.path.abspath(source)
                    or json.loads(item.recipe_json) != recipe):
                raise RecipeError('Approved plan changed; review the source and operations again')
            item_state = json.loads(item.state_json)
            directory = destination_for(recipe, Path(item.source), chosen, state=item_state)
            if directory is None or directory != Path(item.output).parent:
                raise RecipeError('Approved destination changed; review again')
            key = output_key(item)
            if key in outputs: raise RecipeError('Output collision in approved batch')
            outputs.add(key)
    except (OSError, RecipeError, PSDError, ProcessError) as exc:
        results = [{'source': str(source), 'ok': False, 'error': str(exc),
                    'cancelled': cancelled()} for source in sources]
        if progress:
            for index, result in enumerate(results, start_index):
                progress(result, index, len(sources))
        return results
    results = []
    directories = {}
    with contextlib.ExitStack() as stack:
        for index, (source, item) in enumerate(zip(sources, approved_plan), start_index):
            if cancelled(): break
            if started: started(str(source), index)
            result = None
            try:
                with source_session():
                    checkpoint()
                    job_stage('Checking approved source')
                    source_path = Path(item.source)
                    before_path = os.stat(source_path, follow_symlinks=False)
                    if not stat.S_ISREG(before_path.st_mode) or source_identity(before_path) != item.identity:
                        raise RecipeError('Source changed since review; review again')
                    directory = Path(item.output).parent
                    fd, binding = open_approved_directory(item, directories, stack)
                    pinned = Path(f'/proc/{os.getpid()}/fd/{fd}')
                    with tempfile.TemporaryDirectory(prefix='.kimng-stage.', dir=pinned) as tmp:
                        original = Path(tmp) / 'input'
                        srcfd = open_inspection_fd(source_path)
                        with os.fdopen(srcfd, 'rb') as inp, original.open('xb') as out:
                            before = os.fstat(inp.fileno())
                            if not stat.S_ISREG(before.st_mode) or source_identity(before) != item.identity:
                                raise RecipeError('Source changed before copying; review again')
                            try: psd_header(os.pread(inp.fileno(), 26, 0))
                            except PSDError as exc: raise RecipeError(str(exc)) from exc
                            while block := inp.read(1024*1024):
                                checkpoint(); out.write(block)
                            if source_identity(os.fstat(inp.fileno())) != item.identity:
                                raise RecipeError('Source changed while copying; review again')
                        os.utime(original, ns=(before.st_atime_ns,before.st_mtime_ns))
                        media_handler = handler(recipe['media'])
                        state = json.loads(item.state_json)
                        # JSON arrays preserve all state values; overlay identities
                        # use tuples when compared with fresh filesystem identities.
                        for overlay in state.get('overlays', []):
                            if overlay.get('identity') is not None:
                                overlay['identity'] = tuple(overlay['identity'])
                        if state.get('_source_stem') is None:
                            state['_source_stem'] = source_path.stem
                        output = Path(tmp) / ('output.' + state['extension'])
                        media_handler.execute(original, output, enabled_steps(recipe['steps']), state)
                        if not output.is_file() or output.is_symlink() or output.stat().st_size == 0:
                            raise RecipeError('Missing or invalid staged output')
                        media_handler.verify(output, state)
                        verify_directory_binding(directory, binding)
                        current = os.stat(source_path, follow_symlinks=False)
                        if not stat.S_ISREG(current.st_mode) or source_identity(current) != item.identity:
                            raise RecipeError('Source changed during execution; review again')
                        job_stage('Writing / publishing output')
                        checkpoint()
                        publish(output, fd, Path(item.output).name)
                        # Publication has succeeded. A later durability or cleanup
                        # failure is an advisory, never a false unpublished result.
                        result = {'source': str(source), 'output': item.output, 'ok': True,
                                  'warning': state.get('optional_metadata_warning', '')}
                        try: os.fsync(fd)
                        except OSError as exc:
                            result['warning'] = (result['warning'] + '\nOutput published; directory durability sync failed: ' + str(exc)).strip()
            except (OSError, RecipeError, PSDError, ProcessError) as exc:
                if result is not None and result.get('ok'):
                    result['warning'] = (result.get('warning', '') + '\nOutput published; stage cleanup failed: ' + str(exc)).strip()
                else:
                    result = {'source': str(source), 'error': str(exc), 'ok': False, 'cancelled': cancelled()}
            results.append(result)
            if progress: progress(result, index, len(sources))
            if cancelled() or (stop_on_error and not result['ok']): break
    return results


def main():
    parser = argparse.ArgumentParser(description='KIMng create-only media recipes')
    parser.add_argument('--recipe', help='Recipe id or JSON file containing one recipe')
    parser.add_argument('--destination')
    parser.add_argument('--sync-menu', action='store_true', help='Rebuild installed Root shortcuts from the saved library')
    parser.add_argument('--editor', action='store_true')
    parser.add_argument('--run-id', help='Open read-only confirmation for a saved recipe id')
    parser.add_argument('--choose', action='store_true', help='Open Run a Recipe with no recipe selected')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    try:
        if args.sync_menu:
            from kim_recipe_menu import sync_menu
            sync_menu(); return 0
        if args.run_id or args.choose:
            from kim_recipe_run import launch_run
            return launch_run(args.run_id, args.files)
        recipes = builtins() + load_users()
        if args.list:
            print(json.dumps(recipes, indent=2)); return 0
        if args.editor or not args.recipe:
            from kim_recipe_dialog import launch
            return launch(args.files)
        recipe = next((r for r in recipes if r['id'] == args.recipe), None)
        if recipe is None:
            recipe = _validate_persisted_recipe(strict_json(Path(args.recipe).read_text()))
        from kim_recipe_params import is_parameterized, resolve_recipe
        if is_parameterized(recipe):
            raise RecipeError(
                'This Recipe asks for settings when running and cannot run noninteractively. '
                'Open it with --run-id or Run a Recipe.'
            )
        concrete = resolve_recipe(recipe, validated=True)
        if not args.files:
            raise RecipeError('Select at least one input')
        if args.preview:
            from dataclasses import asdict
            result = [asdict(row) for row in preview(concrete, args.files, args.destination)]
            for row in result: row.pop('approved', None)
            print(json.dumps(result, indent=2)); return int(any(r['problems'] for r in result))
        result = execute(concrete, args.files, args.destination)
        print(json.dumps(result, indent=2))
        return int(any(not r['ok'] for r in result))
    except (OSError, RecipeError, ImportError) as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
