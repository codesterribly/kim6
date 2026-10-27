#!/usr/bin/env bash
#
# Install KIM6's unified dispatcher, resources, translations, and five menus.
# Usage: ./install.sh [--prefix SERVICEMENU_DIRECTORY]. The default user path
# is ${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus; root uses the first
# XDG_DATA_DIRS entry (default /usr/local/share). --prefix names that directory.
# Rerun to upgrade. Files are replaced individually through same-directory
# temporary files; a partial install is completed by rerunning this script.
# KIM6 files are identified by the dispatcher or menu contents. Unknown files,
# unrelated menu collisions, and symlinks are preserved or refused. Changes to
# known KIM6 files are replaced on upgrade. intltool-merge is required; msgfmt
# and kbuildsycoca6 are optional. kim_all checks media tools when needed.
# Early KIM work is credited to Charles Bouveyron and Tomáš Hnyk; see ABOUT and
# LICENSE.md. Exit status: 0 success, 2 invalid arguments, 1 other failure.
set -euo pipefail

SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREFIX=''

# Choose the normal user location, or the first system data directory for root.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] || { echo "install.sh: --prefix needs a directory" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: install.sh [--prefix SERVICEMENU_DIRECTORY]"
      exit 0
      ;;
    *)
      echo "install.sh: unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$PREFIX" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    data_root="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    PREFIX="${data_root%%:*}/kio/servicemenus"
  else
    PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus"
  fi
fi
[[ "$PREFIX" != *$'\n'* && "$PREFIX" != *$'\r'* ]] || {
  echo "install.sh: prefix contains a newline" >&2
  exit 2
}
command -v intltool-merge >/dev/null 2>&1 || {
  echo "install.sh: install intltool-merge to render translated Dolphin menus" >&2
  exit 1
}
[[ ! -L "$PREFIX" ]] || { echo "install.sh: refusing symlinked prefix: $PREFIX" >&2; exit 1; }
mkdir -p -- "$PREFIX"
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kim6"

menu_names=(kim_compress.desktop kim_compressandresize.desktop kim_convertandrotate.desktop
  kim_compressandresizevideo.desktop kim_publication.desktop)
languages=(de es fr hu it nl zh_TW)
legacy_names=(kim_album kim_compress kim_convert kim_flipflop kim_galery kim_multiburst
  kim_other kim_pelemele kim_print kim_rename kim_resize kim_resizeandsend kim_rotate
  kim_rotatewithexif kim_sortbydate kim_stripmeta kim_treatment kim_video kim_webexport)
manual_files=(
  docs/reference/ABOUT.html
  docs/reference/ACTIONS.html
  docs/reference/commandconfig.html
  docs/reference/DEVELOPMENT.html
  docs/reference/FORMATS.html
  docs/reference/INSTALL.html
  docs/reference/LICENSE.html
  docs/reference/README.html
  docs/images/kim6-context-menu-illustration.png
  docs/images/kim6-metadata-illustration.png
  docs/images/kim6-web-export-illustration.png
)
runtime_files=(bin/kim_all gallery/index.part1 gallery/index.part2 ABOUT LICENSE.md INSTALL.md
  docs/index.html docs/work.css "${manual_files[@]}")
temporary=''
die() { echo "install.sh: $*" >&2; exit 1; }
check_dir() { [[ ! -L "$1" && ( ! -e "$1" || -d "$1" ) ]] || die "refusing unsafe directory: $1"; }
check_file() { [[ ! -L "$1" && ( ! -e "$1" || -f "$1" ) ]] || die "refusing unsafe file: $1"; }

trap '[ -z "$temporary" ] || rm -f -- "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The dispatcher header is the simple runtime identity. The old marker and
# recognized menus allow upgrades from earlier KIM6 installations.
dispatcher_is_kim6() {
  [ -f "$1" ] && [ ! -L "$1" ] && grep -Fq '# One entrypoint for KIM actions' "$1"
}
menu_is_kim6() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Eq '^X-KIM6-Managed=true$|^Exec=.*(kim_all|kim_(album|compress|convert|flipflop|galery|multiburst|other|pelemele|print|rename|resize|resizeandsend|rotate|rotatewithexif|sortbydate|stripmeta|treatment|video|webexport))(["[:space:]]|$)' "$1"
}
runtime_is_empty() {
  # Empty folders can be leftovers from interruption before the first copy.
  [ -z "$(find "$RUNTIME" -mindepth 1 ! -type d -print -quit)" ]
}
has_kim_menu() {
  local name
  for name in "${menu_names[@]}"; do
    if menu_is_kim6 "$PREFIX/$name"; then return 0; fi
  done
  return 1
}
# A matching menu is not proof that an unrelated directory named "kim6"
# belongs to us. The legacy exception requires an identifiable KIM script.
legacy_runtime_is_kim6() {
  local name path
  has_kim_menu || return 1
  for name in "${legacy_names[@]}"; do
    path="$RUNTIME/bin/$name"
    if [ -f "$path" ] && [ ! -L "$path" ] &&
       grep -Eq 'SOURCE_TRANSLATION_TTT|Copyright.*Charles Bouveyron' "$path"; then
      return 0
    fi
  done
  return 1
}
runtime_is_kim6() {
  dispatcher_is_kim6 "$RUNTIME/bin/kim_all" ||
    { [ -f "$RUNTIME/.kim6-owned" ] && [ ! -L "$RUNTIME/.kim6-owned" ]; } ||
    legacy_runtime_is_kim6
}

# Refuse an unrelated populated kim6 directory, but allow a new empty directory.
if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  check_dir "$RUNTIME"
  if [ -e "$RUNTIME/bin/kim_all" ] && ! dispatcher_is_kim6 "$RUNTIME/bin/kim_all"; then
    die "refusing to replace an unrecognized dispatcher: $RUNTIME/bin/kim_all"
  fi
  runtime_is_kim6 || runtime_is_empty || die "refusing to replace an unrecognized runtime directory: $RUNTIME"
fi

# Check every path we will touch before copying. Unknown files elsewhere in the
# runtime stay in place; known destinations must be ordinary files/directories.
for directory in "$RUNTIME" "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference" "$RUNTIME/locale"; do
  check_dir "$directory"
done
for relative in "${runtime_files[@]}" .kim6-owned .kim6-manifest; do
  check_file "$RUNTIME/$relative"
done
if [ -e "$RUNTIME/bin/kim_all" ] && ! dispatcher_is_kim6 "$RUNTIME/bin/kim_all"; then
  echo "install.sh: refusing to replace an unrecognized dispatcher file: $RUNTIME/bin/kim_all" >&2
  exit 1
fi
for name in "${legacy_names[@]}"; do
  check_file "$RUNTIME/bin/$name"
done
for language in "${languages[@]}"; do
  check_dir "$RUNTIME/locale/$language"
  check_dir "$RUNTIME/locale/$language/LC_MESSAGES"
  check_file "$RUNTIME/locale/$language/LC_MESSAGES/kim6.mo"
done
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if [ -L "$path" ] || { [ -e "$path" ] && { [ ! -f "$path" ] || ! menu_is_kim6 "$path"; }; }; then
    echo "install.sh: refusing unrelated or unsafe menu file: $path" >&2
    exit 1
  fi
done

# Keep the offline HTML manual synchronized with its Markdown sources.
# A writable, non-root development checkout regenerates reference pages
# automatically. System installations verify rather than modify source files.
# Pandoc and Python are optional for users installing prebuilt HTML.
if [ -f "$SOURCE_DIR/tools/build_manual.py" ]; then
  if command -v python3 >/dev/null 2>&1 &&
     command -v pandoc >/dev/null 2>&1; then
    if [ "$(id -u)" -ne 0 ] &&
       [ -w "$SOURCE_DIR/docs/reference" ]; then
      echo "install.sh: updating offline HTML documentation..."
      python3 "$SOURCE_DIR/tools/build_manual.py" ||
        die "could not regenerate HTML documentation"
    else
      python3 "$SOURCE_DIR/tools/build_manual.py" --check ||
        die "HTML documentation is stale; regenerate it before installing"
    fi
  else
    echo "install.sh: using bundled HTML documentation (Pandoc/Python unavailable)." >&2
  fi
fi

# Check the source checkout before creating or replacing runtime files.
for relative in src/bin/kim_all src/gallery/index.part1 src/gallery/index.part2 ABOUT LICENSE.md \
    INSTALL.md docs/index.html docs/work.css "${manual_files[@]}"; do
  [[ -f "$SOURCE_DIR/$relative" && ! -L "$SOURCE_DIR/$relative" ]] || die "required file is missing: $SOURCE_DIR/$relative"
done
for name in "${menu_names[@]}"; do
  [[ -f "$SOURCE_DIR/src/$name.in" && ! -L "$SOURCE_DIR/src/$name.in" ]] || die "menu template is missing: $SOURCE_DIR/src/$name.in"
done

# Write one file beside its destination, then rename it into place. This keeps
# individual files intact if copying or compiling is interrupted.
install_file() {
  local source="$1" destination="$2" mode="$3"
  check_file "$destination"
  mkdir -p -- "${destination%/*}"
  temporary="$(mktemp "${destination}.tmp.XXXXXX")"
  install -m "$mode" -- "$source" "$temporary"
  if ! mv -f -- "$temporary" "$destination"; then
    echo "install.sh: could not update $destination" >&2
    return 1
  fi
  temporary=''
}

compile_translation() {
  local language="$1" destination="$RUNTIME/locale/$1/LC_MESSAGES/kim6.mo"
  mkdir -p -- "${destination%/*}"
  temporary="$(mktemp "${destination}.tmp.XXXXXX")"
  msgfmt -o "$temporary" "$SOURCE_DIR/po/$language.po"
  chmod 0644 -- "$temporary"
  if ! mv -f -- "$temporary" "$destination"; then
    echo "install.sh: could not install translation $destination" >&2
    return 1
  fi
  temporary=''
}

mkdir -p -- "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference"
install_file "$SOURCE_DIR/src/bin/kim_all" "$RUNTIME/bin/kim_all" 0755
install_file "$SOURCE_DIR/src/gallery/index.part1" "$RUNTIME/gallery/index.part1" 0644
install_file "$SOURCE_DIR/src/gallery/index.part2" "$RUNTIME/gallery/index.part2" 0644
install_file "$SOURCE_DIR/ABOUT" "$RUNTIME/ABOUT" 0644
install_file "$SOURCE_DIR/LICENSE.md" "$RUNTIME/LICENSE.md" 0644
install_file "$SOURCE_DIR/INSTALL.md" "$RUNTIME/INSTALL.md" 0644
install_file "$SOURCE_DIR/docs/index.html" "$RUNTIME/docs/index.html" 0644
install_file "$SOURCE_DIR/docs/work.css" "$RUNTIME/docs/work.css" 0644
for relative in "${manual_files[@]}"; do
  install_file "$SOURCE_DIR/$relative" "$RUNTIME/$relative" 0644
done

if command -v msgfmt >/dev/null 2>&1; then
  for language in "${languages[@]}"; do
    if [ -f "$SOURCE_DIR/po/$language.po" ]; then compile_translation "$language"; fi
  done
else
  echo "install.sh: msgfmt is unavailable; menu translations will still be installed, compiled message catalogs were skipped." >&2
fi

# Escape the installed executable path for a quoted KDE Exec argument and for
# sed's replacement syntax. Paths containing newlines were rejected above.
exec_path="$RUNTIME/bin/kim_all"
exec_path="${exec_path//\\/\\\\}"
exec_path="${exec_path//\"/\\\"}"
exec_path="${exec_path//%/%%}"
exec_path="${exec_path//&/\\&}"
exec_path="${exec_path//#/\\#}"
for name in "${menu_names[@]}"; do
  destination="$PREFIX/$name"
  temporary="$(mktemp "$PREFIX/.${name}.tmp.XXXXXX")"
  intltool-merge --desktop-style "$SOURCE_DIR/po" "$SOURCE_DIR/src/$name.in" "$temporary" >/dev/null
  sed -i "s#^Exec=kim_all\\([[:space:]]\\|$\\)#Exec=\"$exec_path\"\\1#" "$temporary"
  if ! grep -Fq "kim6/bin/kim_all" "$temporary"; then
    echo "install.sh: rendered menu does not reference the installed dispatcher: $name" >&2
    exit 1
  fi
  chmod 0644 -- "$temporary"
  if ! mv -f -- "$temporary" "$destination"; then
    echo "install.sh: could not install menu $destination" >&2
    exit 1
  fi
  temporary=''
done

# Retire only the known KIM legacy command names after the new menus are in place.
for name in "${legacy_names[@]}"; do
  path="$RUNTIME/bin/$name"
  if [ -f "$path" ]; then rm -f -- "$path"; fi
done
rm -f -- "$RUNTIME/.kim6-owned" "$RUNTIME/.kim6-manifest"

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
printf 'KIM6 installed in %s. Restart Dolphin if the menus are not visible.\n' "$PREFIX"
