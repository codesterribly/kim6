#!/usr/bin/env bash
#
# Install the unified KIM6 Dolphin integration from this checkout.
#
# Usage: ./install.sh [--prefix SERVICEMENU_DIRECTORY]
#
# The default is the current user's ${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus.
# A root invocation without --prefix uses the first ${XDG_DATA_DIRS} entry
# (default /usr/local/share) and appends /kio/servicemenus. --prefix names the
# service-menu directory itself and supports isolated or custom installations.
#
# The owned inventory is kim6/bin/kim_all, two gallery fragments, ABOUT,
# LICENSE.md, INSTALL.md, docs/index.html, docs/work.css, compiled kim6
# translations when msgfmt is available, and five named service menus. The
# .kim6-owned marker identifies the runtime directory; menu files identify
# themselves with X-KIM6-Managed=true. Known unmodified legacy KIM commands
# are removed during upgrade. Unknown files are left alone.
#
# Upgrades replace the listed KIM resources and menus in place. Files are
# replaced one at a time through a same-directory temporary file, so an
# individual file is never left half-written. The install is not a transaction:
# interruption can leave a mixture of old and new files. Rerun this command to
# complete the update. Customized contents at identified KIM paths are replaced;
# preserve personal edits yourself before upgrading. Uninstall removes the
# listed inventory and leaves unknown files in place.
#
# External tools: Bash, standard Unix file utilities, intltool-merge (required),
# and optionally msgfmt and kbuildsycoca6. Runtime
# processing dependencies are checked by kim_all, not installed here.
#
# Exit status: 0 means installation completed; 2 means invalid arguments; 1
# means a required tool, ownership check, resource preparation, or file update
# failed. A failed or interrupted run may be incomplete; rerun after correcting
# the reported problem. KDE cache refresh is best-effort after installation.
#
# Historical attribution: early KIM installation work is credited to Tomáš
# Hnyk in repository history. KIM6 consolidation and later maintenance are in
# Git history. See LICENSE.md for the applicable license.
set -euo pipefail

# ---- Arguments and destination ------------------------------------------------
SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREFIX=''
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
    PREFIX="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    PREFIX="${PREFIX%%:*}/kio/servicemenus"
  else
    PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus"
  fi
fi
[[ "$PREFIX" != *$'\n'* && "$PREFIX" != *$'\r'* ]] || { echo "install.sh: prefix contains a newline" >&2; exit 2; }
command -v intltool-merge >/dev/null 2>&1 || { echo "install.sh: intltool-merge is required to render Dolphin menus" >&2; exit 1; }
mkdir -p -- "$PREFIX"
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"

# ---- Explicit KIM6 inventory --------------------------------------------------
RUNTIME="$PREFIX/kim6"
menu_names=(kim_compress.desktop kim_compressandresize.desktop kim_convertandrotate.desktop kim_compressandresizevideo.desktop kim_publication.desktop)
resource_paths=(bin/kim_all gallery/index.part1 gallery/index.part2 ABOUT LICENSE.md INSTALL.md docs/index.html docs/work.css)
languages=(de es fr hu it nl zh_TW)
legacy_names=(kim_album kim_compress kim_convert kim_flipflop kim_galery kim_multiburst kim_other kim_pelemele kim_print kim_rename kim_resize kim_resizeandsend kim_rotate kim_rotatewithexif kim_sortbydate kim_stripmeta kim_treatment kim_video kim_webexport)
TEMP_FILE=''

# Remove only the one temporary file this process created. A hard kill can leave
# a hidden sibling behind; it is harmless and deliberately not glob-deleted.
cleanup_temp() {
  if [ -n "$TEMP_FILE" ]; then rm -f -- "$TEMP_FILE"; fi
}
trap cleanup_temp EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The marker identifies an existing runtime. An empty directory can be adopted
# safely after an interruption before the marker was written; other unmarked
# contents make ownership ambiguous.
runtime_is_owned() {
  [ -d "$RUNTIME" ] && [ ! -L "$RUNTIME" ] || return 1
  if [ -f "$RUNTIME/.kim6-owned" ] && [ ! -L "$RUNTIME/.kim6-owned" ]; then
    return 0
  fi
  [ -z "$(find "$RUNTIME" -mindepth 1 -maxdepth 1 -print -quit)" ]
}

# A same-name menu may be replaced only when its marker or a recognized
# historical KIM command identifies it. The filename alone is not ownership.
menu_is_owned() {
  local path="$1"
  [ -f "$path" ] && [ ! -L "$path" ] || return 1
  grep -Eq '^X-KIM6-Managed=true$|^Exec=.*\bkim_(compress|convert|rotate|resize|video|galery|pelemele|other|album|print|rename|sortbydate|stripmeta|multiburst|treatment|resizeandsend|flipflop|webexport)\b|^Exec=(magick|convert|montage)\b' "$path"
}

# Check every conflict before touching the runtime or any menu. No backup tree
# is made: marked KIM paths are updateable; unidentified collisions fail closed.
if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  [ -d "$RUNTIME" ] && [ ! -L "$RUNTIME" ] || { echo "install.sh: refusing unsafe runtime path: $RUNTIME" >&2; exit 1; }
  if find "$RUNTIME" -type l -print -quit | grep -q .; then
    echo "install.sh: refusing runtime tree containing symlinks: $RUNTIME" >&2
    exit 1
  fi
  runtime_is_owned || { echo "install.sh: runtime is not identified as KIM6-owned or empty: $RUNTIME" >&2; exit 1; }
  for relative in "${resource_paths[@]}" .kim6-owned .kim6-manifest; do
    path="$RUNTIME/$relative"
    if [ -e "$path" ] && [ ! -f "$path" ]; then
      echo "install.sh: expected a regular KIM6 file at $path" >&2
      exit 1
    fi
  done
  for directory in bin gallery docs locale; do
    path="$RUNTIME/$directory"
    if [ -e "$path" ] && [ ! -d "$path" ]; then
      echo "install.sh: expected a KIM6 directory at $path" >&2
      exit 1
    fi
  done
  if command -v msgfmt >/dev/null 2>&1; then
    for language in "${languages[@]}"; do
      directory="$RUNTIME/locale/$language/LC_MESSAGES"
      path="$directory/kim6.mo"
      if [ -e "$directory" ] && [ ! -d "$directory" ]; then
        echo "install.sh: expected a translation directory at $directory" >&2
        exit 1
      fi
      if [ -e "$path" ] && [ ! -f "$path" ]; then
        echo "install.sh: expected a translation file at $path" >&2
        exit 1
      fi
    done
  fi
  for name in "${legacy_names[@]}"; do
    path="$RUNTIME/bin/$name"
    if [ -e "$path" ]; then
      source="$SOURCE_DIR/src/bin/$name"
      if [ ! -f "$source" ] || ! cmp -s -- "$path" "$source"; then
        echo "install.sh: refusing to remove modified legacy command: $path; move it aside, then rerun" >&2
        exit 1
      fi
    fi
  done
fi
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if [ -e "$path" ] || [ -L "$path" ]; then
    [ ! -L "$path" ] || { echo "install.sh: refusing symlinked menu path: $path" >&2; exit 1; }
    menu_is_owned "$path" || { echo "install.sh: menu is not recognized as KIM6-owned: $path" >&2; exit 1; }
  fi
done
required_sources=(src/bin/kim_all src/gallery/index.part1 src/gallery/index.part2 ABOUT LICENSE.md INSTALL.md docs/index.html docs/work.css)
for relative in "${required_sources[@]}"; do
  if [ ! -f "$SOURCE_DIR/$relative" ]; then
    echo "install.sh: required resource is missing: $SOURCE_DIR/$relative" >&2
    exit 1
  fi
done
for name in "${menu_names[@]}"; do
  if [ ! -f "$SOURCE_DIR/src/$name.in" ]; then
    echo "install.sh: required menu template is missing: $SOURCE_DIR/src/$name.in" >&2
    exit 1
  fi
done

# Replace one file atomically. TEMP_FILE is in the destination directory, so
# mv cannot cross filesystems and ordinary interruption leaves old or new bytes.
replace_file() {
  local source="$1" destination="$2" mode="$3"
  mkdir -p -- "${destination%/*}"
  TEMP_FILE="$(mktemp "${destination}.kim6-tmp.XXXXXX")" || {
    echo "install.sh: cannot stage $destination" >&2
    return 1
  }
  if ! install -m "$mode" -- "$source" "$TEMP_FILE"; then
    echo "install.sh: cannot prepare $destination from $source" >&2
    return 1
  fi
  if ! mv -f -- "$TEMP_FILE" "$destination"; then
    echo "install.sh: cannot update $destination" >&2
    return 1
  fi
  TEMP_FILE=''
}
# Compile one gettext catalog beside its destination, then rename it into place.
# TEMP_FILE cleanup removes an incomplete catalog if msgfmt or mv fails.
compile_translation() {
  local language="$1" source="$SOURCE_DIR/po/$1.po" destination="$RUNTIME/locale/$1/LC_MESSAGES/kim6.mo"
  mkdir -p -- "${destination%/*}"
  TEMP_FILE="$(mktemp "${destination}.kim6-tmp.XXXXXX")" || {
    echo "install.sh: cannot stage translation $language" >&2
    return 1
  }
  if ! msgfmt -o "$TEMP_FILE" "$source"; then
    echo "install.sh: cannot compile translation $source" >&2
    return 1
  fi
  chmod 0644 -- "$TEMP_FILE"
  if ! mv -f -- "$TEMP_FILE" "$destination"; then
    echo "install.sh: cannot update translation $destination" >&2
    return 1
  fi
  TEMP_FILE=''
}

# First write the ownership marker. It makes subsequent partial installs
# recognizable and safe to finish by rerunning the installer.
mkdir -p -- "$RUNTIME"
if [ ! -e "$RUNTIME/.kim6-owned" ]; then
  touch -- "$RUNTIME/.kim6-owned"
  chmod 0644 -- "$RUNTIME/.kim6-owned"
fi

# Install the small fixed runtime inventory. Unknown files already in kim6/ are
# not copied, renamed, or removed. The old manifest is deleted by its exact name.
replace_file "$SOURCE_DIR/src/bin/kim_all" "$RUNTIME/bin/kim_all" 0755
replace_file "$SOURCE_DIR/src/gallery/index.part1" "$RUNTIME/gallery/index.part1" 0644
replace_file "$SOURCE_DIR/src/gallery/index.part2" "$RUNTIME/gallery/index.part2" 0644
replace_file "$SOURCE_DIR/ABOUT" "$RUNTIME/ABOUT" 0644
replace_file "$SOURCE_DIR/LICENSE.md" "$RUNTIME/LICENSE.md" 0644
replace_file "$SOURCE_DIR/INSTALL.md" "$RUNTIME/INSTALL.md" 0644
replace_file "$SOURCE_DIR/docs/index.html" "$RUNTIME/docs/index.html" 0644
replace_file "$SOURCE_DIR/docs/work.css" "$RUNTIME/docs/work.css" 0644
if command -v msgfmt >/dev/null 2>&1; then
  for language in "${languages[@]}"; do
    if [ -f "$SOURCE_DIR/po/$language.po" ]; then compile_translation "$language"; fi
  done
fi
if [ -f "$RUNTIME/.kim6-manifest" ]; then rm -f -- "$RUNTIME/.kim6-manifest"; fi

# Render and replace each menu independently. If a later menu fails, rerunning
# this script updates every entry; already replaced files remain valid.
for name in "${menu_names[@]}"; do
  template="$SOURCE_DIR/src/$name.in"
  destination="$PREFIX/$name"
  TEMP_FILE="$(mktemp "$PREFIX/.kim6-menu.XXXXXX")"
  if ! intltool-merge --desktop-style "$SOURCE_DIR/po" "$template" "$TEMP_FILE" >/dev/null; then
    echo "install.sh: cannot render menu from $template" >&2
    exit 1
  fi
  exec_path="$RUNTIME/bin/kim_all"
  exec_path="${exec_path//\\/\\\\}"
  exec_path="${exec_path//\"/\\\"}"
  exec_path="${exec_path//&/\\&}"
  exec_path="${exec_path//#/\\#}"
  sed -i "s#^Exec=kim_all\([[:space:]]\|$\)#Exec=\"$exec_path\"\\1#" "$TEMP_FILE"
  chmod 0644 -- "$TEMP_FILE"
  grep -Eq '^Exec=".*kim6/bin/kim_all"( |$)' "$TEMP_FILE" || {
    echo "install.sh: rendered menu does not use the installed dispatcher: $template" >&2
    exit 1
  }
  if ! mv -f -- "$TEMP_FILE" "$destination"; then
    echo "install.sh: cannot update menu $destination" >&2
    exit 1
  fi
  TEMP_FILE=''
done

# Retire known legacy commands only after every menu replacement succeeded.
# An interrupted menu pass therefore leaves old entry points available until
# a rerun completes the migration.
for name in "${legacy_names[@]}"; do
  path="$RUNTIME/bin/$name"
  if [ -f "$path" ]; then rm -f -- "$path"; fi
done

# KDE cache rebuilding is outside the file update: failure here must not turn
# a successful installation into a rollback-like state.
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
printf 'KIM6 installed in %s.\n' "$PREFIX"
