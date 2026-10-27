#!/usr/bin/env bash
#
# Remove the five KIM6 Dolphin menus and known KIM6 runtime files.
#
# Usage: ./uninstall.sh [--prefix SERVICEMENU_DIRECTORY] [--no_message]
#
# The default is the current user's ${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus.
# When run as root, the first ${XDG_DATA_DIRS} entry (default /usr/local/share)
# is used. --prefix names the service-menu directory itself. The script also
# accepts --no_message for older callers; it suppresses the completion line.
#
# KIM6 menus are identified by their managed-menu line or known KIM dispatcher
# and legacy command entries. The runtime is recognized by its kim_all header,
# an older KIM6 marker, or a recognized KIM menu. Only named KIM6 files are
# removed. Unknown files and directories are left in place; empty known runtime
# directories are removed with rmdir. Uninstall is not transactional, so rerun
# it after correcting any reported filesystem error.
#
# Bash and standard Unix file tools are required. kbuildsycoca6 is optional.
# Early KIM work is credited to Charles Bouveyron and Tomáš Hnyk; see ABOUT
# and LICENSE.md for project credits and licensing.
# Exit status: 0 complete/no installation, 2 invalid arguments, 1 unsafe path.
set -euo pipefail

PREFIX=''
quiet=false

# Use the same default service-menu directory as install.sh.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] || { echo "uninstall.sh: --prefix needs a directory" >&2; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --no_message) quiet=true; shift ;;
    -h|--help)
      echo "Usage: uninstall.sh [--prefix SERVICEMENU_DIRECTORY] [--no_message]"
      exit 0
      ;;
    *)
      echo "uninstall.sh: unknown option: $1" >&2
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
  echo "uninstall.sh: prefix contains a newline" >&2
  exit 2
}
if [ -L "$PREFIX" ]; then
  echo "uninstall.sh: refusing symlinked prefix: $PREFIX" >&2
  exit 1
fi
if [ ! -d "$PREFIX" ]; then
  [ "$quiet" = true ] || printf 'No KIM6 service-menu directory found at %s.\n' "$PREFIX"
  exit 0
fi
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kim6"
runtime_known=false

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
  docs/index.html docs/work.css "${manual_files[@]}" .kim6-owned .kim6-manifest)
die() { echo "uninstall.sh: $*" >&2; exit 1; }
check_dir() {
  [[ ! -L "$1" && ( ! -e "$1" || -d "$1" ) ]] || die "refusing unsafe directory: $1"
}
check_file() {
  [[ ! -L "$1" && ( ! -e "$1" || -f "$1" ) ]] || die "refusing unsafe file: $1"
}

# Menu contents, rather than a separately installed ownership database, identify
# KIM6. These names include both the unified menus and their legacy commands.
menu_is_kim6() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Eq '^X-KIM6-Managed=true$|^Exec=.*(kim_all|kim_(album|compress|convert|flipflop|galery|multiburst|other|pelemele|print|rename|resize|resizeandsend|rotate|rotatewithexif|sortbydate|stripmeta|treatment|video|webexport))(["[:space:]]|$)' "$1"
}
dispatcher_is_kim6() {
  [ -f "$1" ] && [ ! -L "$1" ] && grep -Fq '# One entrypoint for KIM actions' "$1"
}

has_kim_menu=false
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if [ -L "$path" ] || { [ -e "$path" ] && [ ! -f "$path" ]; }; then
    echo "uninstall.sh: refusing unsafe menu path: $path" >&2
    exit 1
  fi
  if menu_is_kim6 "$path"; then has_kim_menu=true; fi
done

# Refuse unsafe known paths before removing any menu. Unknown entries in the
# runtime are never traversed or deleted, and can keep their parent directory.
if [ -L "$RUNTIME" ] || { [ -e "$RUNTIME" ] && [ ! -d "$RUNTIME" ]; }; then
  echo "uninstall.sh: refusing unsafe runtime path: $RUNTIME" >&2
  exit 1
fi
if [ -d "$RUNTIME" ]; then
  for directory in "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference" "$RUNTIME/locale"; do
    check_dir "$directory"
  done
  for relative in "${runtime_files[@]}"; do
    check_file "$RUNTIME/$relative"
  done
  if [ -e "$RUNTIME/bin/kim_all" ] && ! dispatcher_is_kim6 "$RUNTIME/bin/kim_all"; then
    echo "uninstall.sh: refusing to remove an unrecognized dispatcher file: $RUNTIME/bin/kim_all" >&2
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

  # Menus alone do not establish ownership of a separate runtime folder.
  # Also recognize genuine legacy KIM scripts when upgrading old layouts.
  legacy_runtime_known=false
  if [ "$has_kim_menu" = true ]; then
    for name in "${legacy_names[@]}"; do
      path="$RUNTIME/bin/$name"
      if [ -f "$path" ] && [ ! -L "$path" ] &&
         grep -Eq 'SOURCE_TRANSLATION_TTT|Copyright.*Charles Bouveyron' "$path"; then
        legacy_runtime_known=true
        break
      fi
    done
  fi
  runtime_known=false
  if dispatcher_is_kim6 "$RUNTIME/bin/kim_all" ||
     { [ -f "$RUNTIME/.kim6-owned" ] && [ ! -L "$RUNTIME/.kim6-owned" ]; } ||
     [ "$legacy_runtime_known" = true ]; then
    runtime_known=true
  fi
  if [ "$runtime_known" = false ] && [ -n "$(find "$RUNTIME" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "uninstall.sh: leaving unrecognized runtime directory untouched: $RUNTIME" >&2
  fi
fi

# Delete only the five known menus when their contents identify them as KIM6.
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if menu_is_kim6 "$path"; then rm -f -- "$path"; fi
done

if [ -d "$RUNTIME" ] && [ "$runtime_known" = true ]; then
  for relative in "${runtime_files[@]}"; do
    path="$RUNTIME/$relative"
    if [ -f "$path" ]; then rm -f -- "$path"; fi
  done
  for name in "${legacy_names[@]}"; do
    path="$RUNTIME/bin/$name"
    if [ -f "$path" ]; then rm -f -- "$path"; fi
  done
  for language in "${languages[@]}"; do
    path="$RUNTIME/locale/$language/LC_MESSAGES/kim6.mo"
    if [ -f "$path" ]; then rm -f -- "$path"; fi
    rmdir -- "$RUNTIME/locale/$language/LC_MESSAGES" "$RUNTIME/locale/$language" 2>/dev/null || true
  done
  rmdir -- "$RUNTIME/docs/images" "$RUNTIME/docs/reference" 2>/dev/null || true
    rmdir -- "$RUNTIME/docs" "$RUNTIME/locale" "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME" 2>/dev/null || true
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
[ "$quiet" = true ] || printf 'Removed recognized KIM6 files from %s.\n' "$PREFIX"
