"""Declarative recipes, storage, planning and create-only batch publication."""
from kim_psd_source import source_session, header as psd_header, PSDError
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


ROOT_FOLDER = "@kimng-root"  # Virtual assignment; impossible as an ordinary folder ID.


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
    keys(recipe, ('schema', 'id', 'name', 'description', 'media', 'steps', 'destination'), ('folder',))
    if type(recipe['schema']) is not int or recipe['schema'] != 3:
        raise RecipeError('Unsupported recipe schema')
    if not isinstance(recipe['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['id']):
        raise RecipeError('Invalid recipe id')
    if 'folder' in recipe and recipe['folder'] != ROOT_FOLDER and (not isinstance(recipe['folder'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['folder'])):
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
        component(destination['folder'])
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
    """Read a bounded, validated individual schema 3 Recipe."""
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
    if 'folder' in recipe:
        raise RecipeError(
            'Individual Recipe files cannot assign a library folder'
        )
    return validate(recipe)


def write_portable_recipe(recipe, path):
    """Export one Recipe without overwriting an existing file."""
    portable = validate(copy.deepcopy(recipe))
    portable.pop('folder', None)

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
    if type(data['schema']) is not int or data['schema'] != 3:
        raise RecipeError('Unsupported Recipe bundle schema')
    if data['kind'] != BUNDLE_KIND:
        raise RecipeError('Not a KIMng Recipe bundle')

    library = validate_library({
        'schema': 3,
        'recipes': data['recipes'],
        'folders': data['folders'],
    })
    if not library.recipes:
        raise RecipeError('Recipe bundle contains no Recipes')
    return library


def read_recipe_bundle(path):
    """Read and fully validate one bounded schema 3 JSON bundle."""
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
        'schema': 3,
        'kind': BUNDLE_KIND,
        'folders': copy.deepcopy(library.folders),
        'recipes': copy.deepcopy(library.recipes),
    }
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
        'schema': 3,
        'recipes': existing.recipes,
        'folders': existing.folders,
    })
    imported = validate_library({
        'schema': 3,
        'recipes': imported.recipes,
        'folders': imported.folders,
    })

    result = copy.deepcopy(existing)
    folder_map = {}
    existing_folders = {
        name_key(folder['name']): folder['id']
        for folder in result.folders
    }

    # Matching folder names reuse the destination library's folder.
    # Other folders receive fresh IDs.
    for folder in imported.folders:
        normalized = name_key(folder['name'])
        if normalized in existing_folders:
            destination_id = existing_folders[normalized]
        else:
            destination_id = 'folder-' + uuid.uuid4().hex
            result.folders.append({
                'id': destination_id,
                'name': folder['name'],
            })
            existing_folders[normalized] = destination_id
        folder_map[folder['id']] = destination_id

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
        if original_folder not in (None, ROOT_FOLDER):
            item['folder'] = folder_map[original_folder]

        result.recipes.append(validate(item))

    result = validate_library({
        'schema': 3,
        'recipes': result.recipes,
        'folders': result.folders,
    })
    return result, imported_ids


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'kimng' / 'recipes.json'


def folder_name(value, existing=False):
    component(value)
    if len(value) > 60 or value != value.strip() or any(unicodedata.category(c).startswith('C') for c in value):
        raise RecipeError('Folder names must be 1–60 characters, without controls or surrounding spaces')
    if not existing and name_key(value) in ('root', 'unfiled', 'built-in'):
        raise RecipeError('This folder name is reserved for a library presentation group')
    return value


def name_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


@dataclass
class RecipeLibrary:
    recipes: list = field(default_factory=list)
    folders: list = field(default_factory=list)

    def create_folder(self, name):
        name = folder_name(name)
        if any(name_key(f['name']) == name_key(name) for f in self.folders):
            raise RecipeError('A folder with this name already exists')
        folder = {'id': 'folder-' + uuid.uuid4().hex, 'name': name}
        self.folders.append(folder)
        return folder['id']

    def rename_folder(self, folder_id, name):
        name = folder_name(name)
        if any(f['id'] != folder_id and name_key(f['name']) == name_key(name) for f in self.folders):
            raise RecipeError('A folder with this name already exists')
        self.find_folder(folder_id)['name'] = name

    def find_folder(self, folder_id):
        for folder in self.folders:
            if folder['id'] == folder_id:
                return folder
        raise RecipeError('Unknown recipe folder id')

    def delete_folder(self, folder_id):
        self.find_folder(folder_id)
        self.folders = [f for f in self.folders if f['id'] != folder_id]
        for recipe in self.recipes:
            if recipe.get('folder') == folder_id:
                recipe.pop('folder')

    def move_recipe(self, recipe_id, folder_id=None):
        if folder_id is not None and folder_id != ROOT_FOLDER:
            self.find_folder(folder_id)
        for recipe in self.recipes:
            if recipe['id'] == recipe_id:
                if folder_id is None:
                    recipe.pop('folder', None)
                else:
                    recipe['folder'] = folder_id
                return
        raise RecipeError('Unknown user recipe id')


def validate_library(data):
    if isinstance(data, list):
        data = {'schema': 3, 'recipes': data, 'folders': []}
    keys(data, ('schema', 'recipes', 'folders'))
    if type(data['schema']) is not int or data['schema'] != 3:
        raise RecipeError('Unsupported recipe library schema')
    if not isinstance(data['recipes'], list) or len(data['recipes']) > 500:
        raise RecipeError('Invalid recipe collection')
    if not isinstance(data['folders'], list) or len(data['folders']) > 100:
        raise RecipeError('Invalid recipe folders')
    folders = copy.deepcopy(data['folders'])
    for folder in folders:
        keys(folder, ('id', 'name'))
        if not isinstance(folder['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', folder['id']):
            raise RecipeError('Invalid folder id')
        folder_name(folder['name'], existing=True)
    if len({f['id'] for f in folders}) != len(folders) or len({name_key(f['name']) for f in folders}) != len(folders):
        raise RecipeError('Duplicate recipe folder')
    recipes = [validate(item) for item in data['recipes']]
    if len({r['id'] for r in recipes}) != len(recipes):
        raise RecipeError('Duplicate recipe id')
    ids = {f['id'] for f in folders} | {ROOT_FOLDER}
    if any('folder' in r and r['folder'] not in ids for r in recipes):
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


def builtins():
    recipes = read_recipes(Path(__file__).resolve().parent.parent / 'recipes' / 'builtins.json')
    if any('folder' in r for r in recipes):
        raise RecipeError('Built-in recipes must remain unfiled')
    return recipes


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
    return folder['name'] + (' (existing user folder)' if name_key(folder['name']) in ('root', 'built-in', 'unfiled') else '')


def recipe_title(recipe, folders=()):
    folder = 'Root' if recipe.get('folder') == ROOT_FOLDER else next((folder_label(f) for f in folders if f['id'] == recipe.get('folder')), None)
    return (folder + ' / ' if folder else '') + recipe['name']


def library_groups(library, shipped=None):
    """Presentation only: portable IDs, schemas, overrides and enabled states stay intact.

    Future collections belong to users; only shipped definitions enter Built-In.
    """
    ordered = lambda recipes: sorted(recipes, key=lambda r: (r['name'].casefold(), r['id']))
    return [(None, 'Built-In', ordered(builtins() if shipped is None else shipped)),
            (ROOT_FOLDER, 'Root', ordered([r for r in library.recipes if r.get('folder') == ROOT_FOLDER]))] + [
        (f['id'], folder_label(f), ordered([r for r in library.recipes if r.get('folder') == f['id']]))
        for f in sorted(library.folders, key=lambda f: (f['name'].casefold(), f['id']))
    ] + [('', 'Unfiled', ordered([r for r in library.recipes if 'folder' not in r]))]


def save_library(library, path=None):
    path = Path(path or config_path())
    data = {'schema': 3, 'recipes': library.recipes, 'folders': library.folders}
    validated = validate_library(data)
    if {r['id'] for r in validated.recipes} & {r['id'] for r in builtins()}:
        raise RecipeError('Duplicate or reserved recipe id')
    def shortcuts(items):
        return sorted((r['id'], r['name']) for r in items if r.get('folder') == ROOT_FOLDER)
    previous = read_library(path, missing=True)
    root_changed = shortcuts(previous.recipes) != shortcuts(validated.recipes)
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
    if path == config_path() and root_changed:
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
                if index != len(directory.parts) - 1: raise
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
    identity = item.destination[-1]
    return ((identity, path.name) if identity is not None
            else (item.destination[-2], path.parent.name, path.name))


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
        directory = destination_for(recipe, Path(os.path.abspath(source)), chosen)
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


def destination_for(recipe, source, chosen=None, create=False):
    dest = recipe['destination']
    if dest['mode'] == 'beside':
        directory = source.parent
    elif dest['mode'] == 'subfolder':
        directory = source.parent / dest['folder']
        if directory.is_symlink():
            raise RecipeError('Subfolder destination is a symlink')
        if create:
            directory.mkdir(exist_ok=True, mode=0o700)
    else:
        if dest['ask'] and not chosen and not create:
            return None
        directory = Path(chosen or ('' if dest['ask'] else dest.get('path', '')))
        if not directory.is_absolute():
            raise RecipeError('Choose a destination directory')
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise RecipeError('Unsafe destination directory')
    if not directory.exists():
        if create or not directory.parent.is_dir():
            raise RecipeError('Destination directory does not exist')
    check = directory if directory.exists() else directory.parent
    if not os.access(check, os.W_OK | os.X_OK):
        raise RecipeError('Destination is not writable')
    return directory.absolute()


def plan(recipe, source, index=1, chosen=None, create=False):
    recipe = validate(recipe)
    source = Path(os.path.abspath(source))
    if source.is_symlink() or not source.is_file():
        raise RecipeError('Source must be a regular file, not a symlink')
    directory = destination_for(recipe, source, chosen, create)
    binding = directory_binding(directory) if directory is not None else None
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise RecipeError('Source must be a regular file, not a symlink')
    state = handler(recipe['media']).plan(source, recipe['steps'], index)
    after = source.lstat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise RecipeError('Source changed during inspection; try again')
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
    if key in cache:
        fd, binding, reviewed = cache[key]
        if reviewed != item.destination:
            raise RecipeError('Destination directory changed between reviewed sources')
    else:
        verify_directory_binding(directory, item.destination)
        if item.destination[-1] is None:
            parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if (directory_binding(directory.parent) != item.destination[:-1]
                        or source_identity(os.fstat(parent_fd))[:2] != item.destination[-2]):
                    raise RecipeError('Destination directory changed since review')
                # An independently created entry requires renewed review.
                os.mkdir(directory.name, mode=0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        binding = directory_binding(directory)
        expected = item.destination
        if ((binding[:-1] != expected[:-1])
                or (expected[-1] is not None and binding[-1] != expected[-1])
                or source_identity(os.fstat(fd))[:2] != binding[-1]):
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
    from kim_process import cancelled, checkpoint, stage as job_stage, ProcessError
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
            directory = destination_for(recipe, Path(item.source), chosen)
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
                        srcfd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(srcfd, 'rb') as inp, original.open('xb') as out:
                            before = os.fstat(inp.fileno())
                            if not stat.S_ISREG(before.st_mode) or source_identity(before) != item.identity:
                                raise RecipeError('Source changed before copying; review again')
                            try: psd_header(Path(f'/proc/{os.getpid()}/fd/{inp.fileno()}'))
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
            recipe = validate(strict_json(Path(args.recipe).read_text()))
        if not args.files:
            raise RecipeError('Select at least one input')
        if args.preview:
            from dataclasses import asdict
            result = [asdict(row) for row in preview(recipe, args.files, args.destination)]
            for row in result: row.pop('approved', None)
            print(json.dumps(result, indent=2)); return int(any(r['problems'] for r in result))
        result = execute(recipe, args.files, args.destination)
        print(json.dumps(result, indent=2))
        return int(any(not r['ok'] for r in result))
    except (OSError, RecipeError, ImportError) as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
