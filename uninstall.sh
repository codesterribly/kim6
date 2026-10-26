#!/usr/bin/env bash
#
# Remove the explicit KIM6 runtime and Dolphin menu inventory.
#
# Usage: ./uninstall.sh [--prefix SERVICEMENU_DIRECTORY] [--no_message]
#
# Without --prefix, the user service-menu directory is
# ${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus; root uses the first
# ${XDG_DATA_DIRS} entry (default /usr/local/share). --prefix names the menu
# directory itself. The script removes five named menus identified by the KIM6
# marker or a recognized previous KIM command, plus listed runtime resources
# below kim6/ only when the .kim6-owned marker is present.
# Known legacy executables are removed only when they exactly match their
# historical repository copies; edited copies are left for their owner.
#
# Unknown files and directories are never selected for deletion. The ownership
# marker stays behind when unknown runtime data remains, so uninstall can be
# rerun. A customized file at a listed KIM path is still considered part of the
# marked runtime and is removed. Symlinks in the runtime or at a known menu path
# stop the operation before removals begin.
#
# This is not a transaction: removals already completed remain completed if a
# later filesystem operation fails. Run the command again after fixing the
# reported problem. Empty known directories are removed with rmdir only.
# KDE cache refresh is best-effort and does not restore removed files.
#
# External tools: Bash and standard Unix utilities; kbuildsycoca6 is optional.
# --no_message suppresses the final success line and treats an absent prefix as
# a successful no-op. Exit status is 0 on completion, 2 for invalid arguments,
# and nonzero for an unsafe or failed operation.
#
# Historical attribution: early KIM installation work is credited to Tomáš
# Hnyk in repository history. KIM6 consolidation and later maintenance are in
# Git history. See LICENSE.md for the applicable license.
set -euo pipefail

# ---- Arguments and destination ------------------------------------------------
SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREFIX=''
quiet=false
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
    PREFIX="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    PREFIX="${PREFIX%%:*}/kio/servicemenus"
  else
    PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus"
  fi
fi
[[ "$PREFIX" != *$'\n'* && "$PREFIX" != *$'\r'* ]] || { echo "uninstall.sh: prefix contains a newline" >&2; exit 2; }
if [ ! -d "$PREFIX" ]; then
  if [ "$quiet" = true ]; then exit 0; fi
  echo "uninstall.sh: service-menu directory not found: $PREFIX" >&2
  exit 1
fi
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kim6"
menu_names=(kim_compress.desktop kim_compressandresize.desktop kim_convertandrotate.desktop kim_compressandresizevideo.desktop kim_publication.desktop)
languages=(de es fr hu it nl zh_TW)
legacy_names=(kim_album kim_compress kim_convert kim_flipflop kim_galery kim_multiburst kim_other kim_pelemele kim_print kim_rename kim_resize kim_resizeandsend kim_rotate kim_rotatewithexif kim_sortbydate kim_stripmeta kim_treatment kim_video kim_webexport)
legacy_pattern='^X-KIM6-Managed=true$|^Exec=.*\bkim_(compress|convert|rotate|resize|video|galery|pelemele|other|album|print|rename|sortbydate|stripmeta|multiburst|treatment|resizeandsend|flipflop|webexport)\b|^Exec=(magick|convert|montage)\b'

# The persistent marker is the ownership proof for runtime removal. A matching
# dispatcher alone is not sufficient because its presence cannot establish
# ownership of the other files in the directory.
runtime_is_owned() {
  [ -f "$RUNTIME/.kim6-owned" ] && [ ! -L "$RUNTIME/.kim6-owned" ]
}
# Accept a known menu only when its contents carry the marker or a recognized
# previous KIM Exec contract; an unrelated same-name file is left untouched.
menu_is_owned() {
  [ -f "$1" ] && [ ! -L "$1" ] && grep -Eq "$legacy_pattern" "$1"
}

# Validate the entire known inventory before deleting anything. Refusing a
# symlink or wrong-type collision avoids following paths or partially removing
# menus before discovering an unsafe runtime tree.
if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  [ -d "$RUNTIME" ] && [ ! -L "$RUNTIME" ] || { echo "uninstall.sh: refusing unsafe runtime path: $RUNTIME" >&2; exit 1; }
  if find "$RUNTIME" -type l -print -quit | grep -q .; then
    echo "uninstall.sh: refusing runtime tree containing symlinks: $RUNTIME" >&2
    exit 1
  fi
  runtime_is_owned || { echo "uninstall.sh: runtime is not identified as KIM6-owned: $RUNTIME" >&2; exit 1; }
  for relative in bin/kim_all gallery/index.part1 gallery/index.part2 ABOUT LICENSE.md INSTALL.md \
      docs/index.html docs/work.css .kim6-owned .kim6-manifest; do
    path="$RUNTIME/$relative"
    if [ -e "$path" ] && [ ! -f "$path" ]; then
      echo "uninstall.sh: expected a regular owned file at $path" >&2
      exit 1
    fi
  done
  for name in "${legacy_names[@]}"; do
    path="$RUNTIME/bin/$name"
    if [ -e "$path" ] && [ ! -f "$path" ]; then
      echo "uninstall.sh: expected a regular legacy command at $path" >&2
      exit 1
    fi
  done
fi
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if [ -L "$path" ]; then
    echo "uninstall.sh: refusing symlinked menu path: $path" >&2
    exit 1
  fi
  if [ -e "$path" ] && [ ! -f "$path" ]; then
    echo "uninstall.sh: expected a regular menu file at $path" >&2
    exit 1
  fi
done

# Remove only recognized KIM menus. Unrecognized same-name files are left for
# their owner; this intentionally favors preservation over aggressive cleanup.
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if menu_is_owned "$path"; then rm -f -- "$path"; fi
done

# Delete only the runtime paths KIM installs, including the old manifest as a
# one-time compatibility file. Files added by users are not enumerated here.
if [ -d "$RUNTIME" ]; then
  for relative in bin/kim_all gallery/index.part1 gallery/index.part2 ABOUT LICENSE.md INSTALL.md \
      docs/index.html docs/work.css .kim6-manifest; do
    path="$RUNTIME/$relative"
    if [ -f "$path" ]; then rm -f -- "$path"; fi
  done
  for name in "${legacy_names[@]}"; do
    path="$RUNTIME/bin/$name"
    source="$SOURCE_DIR/src/bin/$name"
    if [ -f "$path" ] && [ -f "$source" ] && cmp -s -- "$path" "$source"; then
      rm -f -- "$path"
    fi
  done
  for language in "${languages[@]}"; do
    path="$RUNTIME/locale/$language/LC_MESSAGES/kim6.mo"
    if [ -f "$path" ]; then rm -f -- "$path"; fi
    rmdir -- "$RUNTIME/locale/$language/LC_MESSAGES" "$RUNTIME/locale/$language" 2>/dev/null || true
  done
  rmdir -- "$RUNTIME/docs" "$RUNTIME/locale" "$RUNTIME/bin" "$RUNTIME/gallery" 2>/dev/null || true

  # Keep the marker if unknown data remains, allowing a later uninstall to
  # recognize the runtime. Remove the marker only when the known tree is empty.
  if [ -z "$(find "$RUNTIME" -mindepth 1 ! -name .kim6-owned -print -quit)" ]; then
    rm -f -- "$RUNTIME/.kim6-owned"
    rmdir -- "$RUNTIME" 2>/dev/null || true
  fi
fi

# Menu/runtime files are already removed; cache refresh is informational only.
if command -v kbuildsycoca6 >/dev/null 2>&1; then kbuildsycoca6 --noincremental >/dev/null 2>&1 || true; fi
[ "$quiet" = true ] || printf 'Removed recognized KIM6 resources from %s.\n' "$PREFIX"
