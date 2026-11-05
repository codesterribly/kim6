"""Declarative recipes, storage, planning and create-only batch publication."""
from kim_psd_source import source_session, header as psd_header, PSDError
import argparse
import contextlib
import copy
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


ROOT_FOLDER = "@kim6-root"  # Virtual assignment; impossible as an ordinary folder ID.


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
    keys(recipe, ('schema', 'id', 'name', 'media', 'steps', 'destination'), ('folder',))
    if type(recipe['schema']) is not int or recipe['schema'] != 1:
        raise RecipeError('Unsupported recipe schema')
    if not isinstance(recipe['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['id']):
        raise RecipeError('Invalid recipe id')
    if 'folder' in recipe and recipe['folder'] != ROOT_FOLDER and (not isinstance(recipe['folder'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', recipe['folder'])):
        raise RecipeError('Invalid recipe folder id')
    if not text(recipe['name'], 100).strip():
        raise RecipeError('Recipe name is empty')
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


def config_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'kim6' / 'recipes.json'


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
        data = {'schema': 1, 'recipes': data, 'folders': []}
    keys(data, ('schema', 'recipes', 'folders'))
    if type(data['schema']) is not int or data['schema'] != 1:
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
    data = {'schema': 1, 'recipes': library.recipes, 'folders': library.folders}
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
            return 'Recipe saved, but shortcuts could not be updated: ' + str(exc) + '\nRetry: kim_all recipe --sync-menu (from the active installation), or reinstall KIM6 to a writable user prefix.'
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
    certainty: str = 'The filename is checked again when saving and may change if another file appears.'
    warnings: list = field(default_factory=list)
    identity: tuple | None = None


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
    if not directory.exists() and not (dest['mode'] == 'subfolder' and not create):
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
    before = source.stat()
    state = handler(recipe['media']).plan(source, recipe['steps'], index)
    after = source.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise RecipeError('Source changed during inspection; try again')
    from kim_psd_source import stage as job_stage
    job_stage('Planning output filename')
    name = component(state['name']) + '.' + state['extension']
    proposed = str(directory / name) if directory is not None else '<choose directory at run>/' + name
    row = PreviewRow(str(source), proposed, recipe['media'], state['format'],
                     state['properties'], state['metadata'])
    row.identity = (before.st_dev, before.st_ino)
    row.warnings.extend(state.get('warnings', []))
    row.properties['_proposed_output'] = proposed
    if directory is not None and os.path.lexists(directory / name):
        candidate = directory / name; number = 0
        while os.path.lexists(candidate):
            number += 1
            candidate = (directory / name).with_name(f'{Path(name).stem}_{number}{Path(name).suffix}')
        row.output = str(candidate)
        row.certainty = 'That filename already exists. KIM6 plans to save this file as ' + candidate.name + '. The name is checked again when saving.'
    return Plan(recipe, source, directory, name, state, row)


@contextlib.contextmanager
def recipe_inspections():
    from kim_image_ops import logo_inspections
    with logo_inspections(): yield


@recipe_inspections()
def preview(recipe, sources, chosen=None, start_index=1):
    rows = []
    for index, source in enumerate(sources, start_index):
        with source_session():
            try:
                rows.append(plan(recipe, source, index, chosen).row)
            except (OSError, RecipeError, UnicodeError) as exc:
                row = PreviewRow(str(source), problems=[str(exc)])
                try:
                    from kim_psd_source import cancelled
                    if not cancelled() and Path(source).is_file() and not Path(source).is_symlink():
                        row.properties = handler(recipe['media']).source_properties(Path(source))
                except (OSError, RecipeError, KeyError):
                    pass
                if getattr(exc,'repair',None): row.properties['_repair'] = exc.repair
                rows.append(row)
    return rows


def publish(stage, directory_fd, name):
    """link(2) is the sole publication primitive: every occupied entry is protected."""
    stem, extension = os.path.splitext(name)
    for number in range(10000):
        candidate = name if number == 0 else f'{stem}_{number}{extension}'
        try:
            os.link(stage, candidate, dst_dir_fd=directory_fd, follow_symlinks=False)
            return candidate
        except FileExistsError:
            continue
    raise RecipeError('Too many output filename collisions')


@recipe_inspections()
def execute(recipe, sources, chosen=None, progress=None, start_index=1):
    recipe = validate(recipe)
    from kim_image_ops import has_image_operations, preflight_batch
    if len(sources) > 1 and has_image_operations(recipe):
        try:
            preflight_batch(recipe, sources, chosen, start_index)
        except (OSError, RecipeError, PSDError) as exc:
            from kim_psd_source import cancelled
            return [{'source': str(source), 'ok': False, 'error': str(exc), 'cancelled': cancelled()} for source in sources]
    results = []
    for index, source in enumerate(sources, start_index):
        from kim_psd_source import cancelled, checkpoint, stage as job_stage
        if cancelled(): break
        with source_session():
            try:
                checkpoint()
                job_stage('Inspecting source')
                source_path = Path(os.path.abspath(source))
                if source_path.is_symlink() or not source_path.is_file():
                    raise RecipeError('Source must be a regular file, not a symlink')
                directory = destination_for(recipe, source_path, chosen, create=True)
                # Pin the destination directory; stages and link publication use that inode.
                fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    pinned = Path(f'/proc/{os.getpid()}/fd/{fd}')
                    with tempfile.TemporaryDirectory(prefix='.kim6-stage.', dir=pinned) as tmp:
                        original = Path(tmp) / 'input'
                        srcfd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(srcfd, 'rb') as inp, original.open('xb') as out:
                            if not stat.S_ISREG(os.fstat(inp.fileno()).st_mode):
                                raise RecipeError('Source changed type')
                            import shutil
                            before = os.fstat(inp.fileno())
                            # Retain PSD header/resource rejection before copying
                            # without performing the old duplicate full decode.
                            try: psd_header(Path(f'/proc/{os.getpid()}/fd/{inp.fileno()}'))
                            except PSDError as exc: raise RecipeError(str(exc)) from exc
                            # Check between chunks so a large source copy can be
                            # cancelled before decoding or destination publication.
                            while block := inp.read(1024*1024):
                                checkpoint(); out.write(block)
                            after = os.fstat(inp.fileno())
                            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                                raise RecipeError('Source changed while copying; try again')
                        os.utime(original, ns=(before.st_atime_ns,before.st_mtime_ns))
                        # Inspect the private snapshot again so processing and planning agree.
                        media_handler = handler(recipe['media'])
                        state = media_handler.plan(original, recipe['steps'], index, stem=source_path.stem)
                        output = Path(tmp) / ('output.' + state['extension'])
                        media_handler.execute(original, output, enabled_steps(recipe['steps']), state)
                        if not output.is_file() or output.is_symlink() or output.stat().st_size == 0:
                            raise RecipeError('Missing or invalid staged output')
                        media_handler.verify(output, state)
                        current = os.stat(directory, follow_symlinks=False)
                        pinned_stat = os.fstat(fd)
                        if (current.st_dev, current.st_ino) != (pinned_stat.st_dev, pinned_stat.st_ino):
                            raise RecipeError('Destination directory changed during execution')
                        name = component(state['name']) + '.' + state['extension']
                        job_stage('Writing / publishing output')
                        checkpoint()
                        published = publish(output, fd, name)
                        results.append({'source': str(source), 'output': str(directory / published), 'ok': True})
                finally:
                    os.close(fd)
            except (OSError, RecipeError, PSDError) as exc:
                results.append({'source': str(source), 'error': str(exc), 'ok': False, 'cancelled': cancelled()})
        if progress:
            progress(results[-1], index, len(sources))
    return results


def main():
    parser = argparse.ArgumentParser(description='KIM6 create-only media recipes')
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
            print(json.dumps(result, indent=2)); return int(any(r['problems'] for r in result))
        result = execute(recipe, args.files, args.destination)
        print(json.dumps(result, indent=2))
        return int(any(not r['ok'] for r in result))
    except (OSError, RecipeError, ImportError) as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
