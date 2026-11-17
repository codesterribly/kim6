#!/usr/bin/env bash
#
# Uninstall only verified KIMng-owned runtime files and Dolphin menus.
# Usage: ./uninstall.sh [--prefix SERVICEMENU_DIRECTORY] [--no_message]
# Unknown files, unrelated menus, and symlinks are never deleted.
#
set -euo pipefail

PREFIX=''
quiet=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      [ "$#" -ge 2 ] || {
        echo "uninstall.sh: --prefix needs a directory" >&2
        exit 2
      }
      PREFIX="$2"
      shift 2
      ;;
    --no_message)
      quiet=true
      shift
      ;;
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

[ ! -L "$PREFIX" ] || {
  echo "uninstall.sh: refusing symlinked prefix" >&2
  exit 1
}

if [ ! -d "$PREFIX" ]; then
  [ "$quiet" = true ] ||
    printf 'No KIMng installation at %s\n' "$PREFIX"
  exit 0
fi

PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kimng"

SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=install_inventory.sh
source "$SOURCE_DIR/install_inventory.sh"

die() {
  echo "uninstall.sh: $*" >&2
  exit 1
}

check_dir() {
  [[ ! -L "$1" && ( ! -e "$1" || -d "$1" ) ]] ||
    die "refusing unsafe directory: $1"
}

check_file() {
  [[ ! -L "$1" && ( ! -e "$1" || -f "$1" ) ]] ||
    die "refusing unsafe file: $1"
}

dispatcher_is_kimng() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Fq '# KIMng runtime dispatcher' "$1"
}

menu_is_kimng() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Fxq 'X-KIMng-Managed=true' "$1" &&
    grep -Eq '^Exec=.*kimng/bin/kim_all(["[:space:]]|$)' "$1"
}

# Preflight every known menu before deleting anything.
# Never interpret an unrelated service menu as a KIMng installation.
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  check_file "$path"

  if [ -f "$path" ] && ! menu_is_kimng "$path"; then
    die "refusing unrelated service menu: $path"
  fi
done

check_dir "$RUNTIME"
runtime_owned=false

if [ -d "$RUNTIME" ]; then
  marker="$RUNTIME/.kimng-owned"

  # A KIMng marker is required. Preserve any unrecognized runtime.
  check_file "$marker"

  if [ -f "$marker" ] &&
     [ "$(< "$marker")" = 'KIMng runtime' ]; then
    runtime_owned=true
  fi

  # Never delete a runtime with an unfamiliar dispatcher.
  if [ -e "$RUNTIME/bin/kim_all" ] ||
     [ -L "$RUNTIME/bin/kim_all" ]; then
    dispatcher_is_kimng "$RUNTIME/bin/kim_all" ||
      die "refusing unrecognized dispatcher: $RUNTIME/bin/kim_all"
  fi

  if [ "$runtime_owned" = true ]; then
    for directory in \
      "$RUNTIME/bin" \
      "$RUNTIME/gallery" \
      "$RUNTIME/recipes" \
      "$RUNTIME/docs" \
      "$RUNTIME/docs/images" \
      "$RUNTIME/docs/reference"; do
      check_dir "$directory"
    done

    for relative in "${runtime_files[@]}"; do
      check_file "$RUNTIME/$relative"
    done

    check_file "$RUNTIME/.kimng-manifest"

    cache="$RUNTIME/bin/__pycache__"
    check_dir "$cache"

    if [ -d "$cache" ]; then
      for relative in "${runtime_files[@]}"; do
        case "$relative" in
          bin/*.py) ;;
          *) continue ;;
        esac

        module="${relative##*/}"
        module="${module%.py}"

        for compiled in "$cache/$module".cpython-*.pyc; do
          check_file "$compiled"
        done
      done
    fi
  elif [ -n "$(find "$RUNTIME" -mindepth 1 -print -quit)" ]; then
    die "refusing unrecognized runtime directory: $RUNTIME"
  fi
fi

# All relevant paths have now passed preflight.
# Remove only individually identified, KIMng-owned menus.
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  if [ -f "$path" ] && menu_is_kimng "$path"; then
    rm -f -- "$path"
  fi
done

if [ "$runtime_owned" = true ]; then
  # Keep the marker until cleanup completes, allowing a retry
  # after interruption.

  for relative in "${runtime_files[@]}"; do
    path="$RUNTIME/$relative"
    if [ -f "$path" ]; then
      rm -f -- "$path"
    fi
  done

  # Remove only bytecode derived from the installed Python modules.
  cache="$RUNTIME/bin/__pycache__"
  if [ -d "$cache" ]; then
    for relative in "${runtime_files[@]}"; do
      case "$relative" in
        bin/*.py) ;;
        *) continue ;;
      esac

      module="${relative##*/}"
      module="${module%.py}"

      for compiled in "$cache/$module".cpython-*.pyc; do
        if [ -f "$compiled" ]; then
          rm -f -- "$compiled"
        fi
      done
    done

    rmdir -- "$cache" 2>/dev/null || true
  fi

  rmdir -- \
    "$RUNTIME/docs/images" \
    "$RUNTIME/docs/reference" \
    "$RUNTIME/docs" \
    "$RUNTIME/bin" \
    "$RUNTIME/gallery" \
    "$RUNTIME/recipes" 2>/dev/null || true

  # Remove the ownership marker only when all other content is gone.
  if [ -z "$(find "$RUNTIME" -mindepth 1 -maxdepth 1 \
    ! -name '.kimng-owned' ! -name '.kimng-manifest' \
    -print -quit)" ]; then
    rm -f -- \
      "$RUNTIME/.kimng-owned" \
      "$RUNTIME/.kimng-manifest"
    rmdir -- "$RUNTIME" 2>/dev/null || true
  else
    echo "uninstall.sh: unknown runtime content preserved" >&2
  fi
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

[ "$quiet" = true ] ||
  printf 'Removed verified KIMng files from %s\n' "$PREFIX"
