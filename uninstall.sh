#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREFIX=''
quiet=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) [ "$#" -ge 2 ] || { echo "uninstall.sh: --prefix needs a directory" >&2; exit 2; }; PREFIX="$2"; shift 2 ;;
    --no_message) quiet=true; shift ;;
    -h|--help) echo "Usage: uninstall.sh [--prefix SERVICEMENU_DIRECTORY] [--no_message]"; exit 0 ;;
    *) echo "uninstall.sh: unknown option: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$PREFIX" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    data_dirs="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
    PREFIX="${data_dirs%%:*}/kio/servicemenus"
  else
    PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus"
  fi
fi
[[ "$PREFIX" != *$'\n'* && "$PREFIX" != *$'\r'* ]] || { echo "uninstall.sh: invalid prefix" >&2; exit 2; }
[ -d "$PREFIX" ] || { [ "$quiet" = true ] && exit 0; echo "KIM6 service-menu directory not found: $PREFIX"; exit 1; }
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"

menu_names=(kim_compress.desktop kim_compressandresize.desktop kim_convertandrotate.desktop kim_compressandresizevideo.desktop kim_publication.desktop)
RUNTIME="$PREFIX/kim6"
if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  [ -d "$RUNTIME" ] && [ ! -L "$RUNTIME" ] || { echo "uninstall.sh: refusing unsafe runtime path: $RUNTIME" >&2; exit 1; }
  if find "$RUNTIME" -type l -print -quit | grep -q .; then
    echo "uninstall.sh: refusing to remove resources from a runtime tree containing symlinks: $RUNTIME" >&2
    exit 1
  fi
fi
owned_digest() {
  local relative="$1"
  [ -f "$RUNTIME/.kim6-manifest" ] || return 1
  awk -F '\t' -v path="$relative" '$2 == path { print $1; found=1 } END { if (!found) exit 1 }' "$RUNTIME/.kim6-manifest"
}
file_digest() {
  local value
  [ -f "$1" ] && [ ! -L "$1" ] || return 1
  value="$(sha256sum -- "$1")" || return 1
  printf '%s\n' "${value%% *}"
}
for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"
  [ -f "$path" ] && [ ! -L "$path" ] || continue
  expected="$(owned_digest "@menu:$name" 2>/dev/null || true)"
  if [ -n "$expected" ]; then
    actual="$(file_digest "$path" 2>/dev/null || true)"
    [ "$actual" != "$expected" ] || rm -f -- "$path"
  elif grep -Eq '^X-KIM6-Managed=true$|^Exec=.*kim_(compress|convert|rotate|resize|video|galery|pelemele|other|album|print|rename|sortbydate|stripmeta|multiburst|treatment|resizeandsend|flipflop|webexport)\b|^Exec=(magick|convert|montage)\b' "$path"; then
    # Recognize the specific pre-unification KIM command contract.
    rm -f -- "$path"
  fi
done

if [ -d "$RUNTIME" ]; then
  if [ -f "$RUNTIME/.kim6-manifest" ]; then
    while IFS=$'\t' read -r expected relative; do
      [ -n "$relative" ] || continue
      case "$relative" in @menu:*) continue ;; esac
      path="$RUNTIME/$relative"
      actual="$(file_digest "$path" 2>/dev/null || true)"
      if [ -n "$expected" ] && [ "$actual" = "$expected" ]; then
        rm -f -- "$path"
        case "$relative" in locale/*/LC_MESSAGES/kim6.mo)
          messages_dir="${path%/*}"
          language_dir="${messages_dir%/*}"
          rmdir -- "$messages_dir" "$language_dir" "$RUNTIME/locale" 2>/dev/null || true ;;
        esac
      fi
    done < "$RUNTIME/.kim6-manifest"
    rm -f -- "$RUNTIME/.kim6-manifest" "$RUNTIME/.kim6-owned"
  else
    # Legacy resource ownership is ambiguous. Remove only dispatcher code that
    # exactly matches the current repository source; leave customized files.
    if [ -f "$RUNTIME/bin/kim_all" ] && cmp -s -- "$RUNTIME/bin/kim_all" "$SOURCE_DIR/src/bin/kim_all"; then
      rm -f -- "$RUNTIME/bin/kim_all"
    fi
  fi
  rmdir -- "$RUNTIME/docs" "$RUNTIME/locale" "$RUNTIME/bin" "$RUNTIME/gallery" 2>/dev/null || true
  rmdir -- "$RUNTIME" 2>/dev/null || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then kbuildsycoca6 --noincremental >/dev/null 2>&1 || true; fi
[ "$quiet" = true ] || echo "KIM6-owned dispatcher resources and service menus removed."
