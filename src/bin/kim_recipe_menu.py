"""Render one owned Recipes service menu, from committed library state only."""
import configparser
import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from kim_recipe_core import ROOT_FOLDER, RecipeError, load_library


def value(text):
    # KConfig string values, not string lists; semicolon and equals are literal.
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise RecipeError('Control character in menu value')
    return text.replace('\\', '\\\\').replace(' ', '\\s')


def exec_argument(text):
    # Desktop Entry: Exec quoting is decoded after the string escape layer.
    if any(ord(c) < 32 for c in text):
        raise RecipeError('Control character in dispatcher path')
    quoted = '"' + ''.join('\\' + c if c in '\\"`$' else c for c in text.replace('%', '%%')) + '"'
    return quoted.replace('\\', '\\\\')


def render(library, dispatcher):
    from kim_recipe_core import validate_library
    library = validate_library({'schema': 1, 'recipes': library.recipes, 'folders': library.folders})
    recipes = sorted((r for r in library.recipes if r.get('folder') == ROOT_FOLDER),
                     key=lambda r: (r['name'].casefold(), r['id']))
    actions = ['KIMRoot-' + r['id'] for r in recipes]
    if recipes: actions.append('_SEPARATOR_')
    actions += ['KIMRecipe0Run', 'KIMRecipe1Editor']
    command = exec_argument(str(dispatcher)) + ' recipe '
    lines = ['[Desktop Entry]', 'Type=Service', 'Icon=view-list-details', 'Name=KIM6',
             'X-KDE-ServiceTypes=KonqPopupMenu/Plugin', 'MimeType=image/*;image/vnd.adobe.photoshop;application/x-photoshop;', 'X-KDE-Protocol=file',
             'X-KDE-Submenu=KIM6 — Recipes', 'X-KIM6-Managed=true',
             'Actions=' + ';'.join(actions) + ';']
    for r in recipes:
        duplicate = sum(x['name'].casefold() == r['name'].casefold() for x in recipes) > 1
        label = r['name'] + (' [' + r['id'] + ']' if duplicate else '')
        lines += ['', '[Desktop Action KIMRoot-' + r['id'] + ']', 'Name=' + value(label),
                  'Exec=' + command + '--run-id ' + r['id'] + ' -- %F']
    if recipes: lines += ['', '[Desktop Action _SEPARATOR_]', 'Name=Separator']
    lines += ['', '[Desktop Action KIMRecipe0Run]', 'Name=Choose Saved Recipe…',
              'Icon=view-list-details', 'Exec=' + command + '--choose -- %F',
              '', '[Desktop Action KIMRecipe1Editor]', 'Name=Recipe Editor…',
              'Icon=document-edit', 'Exec=' + command + '--editor', '']
    result = '\n'.join(lines)
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(result)
    return result


def installed_paths():
    runtime = Path(__file__).absolute().parent.parent
    if runtime.name != 'kim6' or runtime.resolve() != runtime:
        raise RecipeError('No active installed KIM6 runtime; run sync from an installed dispatcher')
    return runtime.parent / 'kim_recipes.desktop', runtime / 'bin' / 'kim_all'


def sync_menu():
    menu, dispatcher = installed_paths()
    # Lock the directory inode: no persistent lock file, no symlink-following lock.
    fd = os.open(menu.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        info = menu.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise RecipeError('Recipes menu is not a user-owned regular file')
        previous = menu.read_text(encoding='utf-8')
        if 'X-KIM6-Managed=true' not in previous.splitlines() or exec_argument(str(dispatcher)) not in previous:
            raise RecipeError('Recipes menu belongs to another installation')
        content = render(load_library(), dispatcher)
        if content == previous and stat.S_IMODE(info.st_mode) == 0o755: return False
        stage = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=menu.parent, prefix='.kim-recipes-', delete=False) as stream:
                stage = Path(stream.name)
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
                os.fchmod(stream.fileno(), 0o755)
            current = menu.lstat()
            if (current.st_ino, current.st_dev, current.st_mtime_ns, current.st_ctime_ns) != (info.st_ino, info.st_dev, info.st_mtime_ns, info.st_ctime_ns):
                raise RecipeError('Recipes menu changed during synchronization; retry')
            os.replace(stage, menu)
        finally:
            if stage is not None: stage.unlink(missing_ok=True)
    finally:
        os.close(fd)
    cache = shutil.which('kbuildsycoca6')
    if cache:
        # Detached cache refresh never holds up the editor.
        subprocess.Popen([cache, '--noincremental'], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True
