#!/usr/bin/env bash
set -euo pipefail

# Install the unified KIM6 dispatcher and its owned Dolphin service menus.
SOURCE_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREFIX=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) [ "$#" -ge 2 ] || { echo "install.sh: --prefix needs a directory" >&2; exit 2; }; PREFIX="$2"; shift 2 ;;
    -h|--help) echo "Usage: install.sh [--prefix SERVICEMENU_DIRECTORY]"; exit 0 ;;
    *) echo "install.sh: unknown option: $1" >&2; exit 2 ;;
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
[[ "$PREFIX" != *$'\n'* && "$PREFIX" != *$'\r'* ]] || { echo "install.sh: invalid prefix" >&2; exit 2; }
command -v intltool-merge >/dev/null 2>&1 || { echo "install.sh: intltool-merge is required to render translated service menus" >&2; exit 1; }
mkdir -p -- "$PREFIX"
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"

STAGE="$(mktemp -d "$PREFIX/.kim6-stage.XXXXXXXX")"
BACKUP="$STAGE/backup"
NEW_RUNTIME="$STAGE/runtime"
NEW_MENUS="$STAGE/menus"
RUNTIME="$PREFIX/kim6"
USER_BACKUP=''
manifest_digest() {
  local file="$1" digest
  [ -f "$file" ] && [ ! -L "$file" ] || return 1
  digest="$(sha256sum -- "$file")" || return 1
  printf '%s\n' "${digest%% *}"
}
previous_manifest_digest() {
  local relative="$1"
  [ -f "$RUNTIME/.kim6-manifest" ] || return 1
  awk -F '\t' -v path="$relative" '$2 == path { print $1; found=1 } END { if (!found) exit 1 }' "$RUNTIME/.kim6-manifest"
}
preserve_if_custom() {
  local relative="$1" current expected backup
  [ -e "$RUNTIME/$relative" ] || return 0
  current="$(manifest_digest "$RUNTIME/$relative")" || { echo "install.sh: refusing unsafe managed resource: $relative" >&2; return 1; }
  expected="$(previous_manifest_digest "$relative" 2>/dev/null || true)"
  [ -n "$expected" ] && [ "$current" = "$expected" ] && return 0
  if [ -z "$USER_BACKUP" ]; then
    USER_BACKUP="$(mktemp -d "$NEW_RUNTIME/.kim6-preserved.XXXXXXXX")" || return 1
  fi
  backup="$USER_BACKUP/$relative"
  mkdir -p -- "${backup%/*}"
  cp -a -- "$RUNTIME/$relative" "$backup"
}
installed_runtime=false
declare -a installed_menus=() backed_menus=()
backed_runtime=false
rollback() {
  local i name
  for ((i=${#installed_menus[@]}-1; i>=0; i--)); do rm -f -- "$PREFIX/${installed_menus[i]}"; done
  if [ "$backed_runtime" = true ]; then
    rm -rf -- "$RUNTIME"
    mv -- "$BACKUP/runtime" "$RUNTIME" || true
  elif [ "$installed_runtime" = true ]; then
    rm -rf -- "$RUNTIME"
  fi
  for ((i=${#backed_menus[@]}-1; i>=0; i--)); do
    name="${backed_menus[i]}"
    [ -e "$BACKUP/menus/$name" ] && mv -- "$BACKUP/menus/$name" "$PREFIX/$name" || true
  done
  rm -rf -- "$STAGE"
}
on_exit() {
  local status=$?
  if [ "$status" -ne 0 ]; then rollback; else rm -rf -- "$STAGE"; fi
}
trap on_exit EXIT
mkdir -p -- "$NEW_RUNTIME/bin" "$NEW_MENUS" "$BACKUP/menus"

# Keep unknown files in the previous KIM-owned runtime tree. Known legacy
# commands are removed only when they are byte-identical to their repository
# reference, which establishes ownership without a broad glob deletion.
if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  [ -d "$RUNTIME" ] && [ ! -L "$RUNTIME" ] || { echo "install.sh: refusing unsafe runtime path: $RUNTIME" >&2; exit 1; }
  if find "$RUNTIME" -type l -print -quit | grep -q .; then
    echo "install.sh: refusing to migrate a runtime tree containing symlinks: $RUNTIME" >&2
    exit 1
  fi
  cp -a -- "$RUNTIME/." "$NEW_RUNTIME/"
fi
preserve_if_custom bin/kim_all
preserve_if_custom gallery/index.part1
preserve_if_custom gallery/index.part2
preserve_if_custom ABOUT
preserve_if_custom LICENSE.md
preserve_if_custom docs/index.html
preserve_if_custom docs/work.css
preserve_if_custom INSTALL.md
install -m 0755 -- "$SOURCE_DIR/src/bin/kim_all" "$NEW_RUNTIME/bin/kim_all"
mkdir -p -- "$NEW_RUNTIME/gallery"
cp -a -- "$SOURCE_DIR/src/gallery/." "$NEW_RUNTIME/gallery/"
install -m 0644 -- "$SOURCE_DIR/ABOUT" "$NEW_RUNTIME/ABOUT"
install -m 0644 -- "$SOURCE_DIR/LICENSE.md" "$NEW_RUNTIME/LICENSE.md"
install -m 0644 -- "$SOURCE_DIR/INSTALL.md" "$NEW_RUNTIME/INSTALL.md"
[ ! -d "$SOURCE_DIR/docs" ] || cp -a -- "$SOURCE_DIR/docs" "$NEW_RUNTIME/docs"
rm -f -- "$NEW_RUNTIME/.kim6-owned"
touch "$NEW_RUNTIME/.kim6-owned"

# The dispatcher loads translations from resources beside the installed copy.
if command -v msgfmt >/dev/null 2>&1; then
  for po in "$SOURCE_DIR"/po/*.po; do
    [ -f "$po" ] || continue
    lang="$(basename -- "$po" .po)"
    mkdir -p -- "$NEW_RUNTIME/locale/$lang/LC_MESSAGES"
    preserve_if_custom "locale/$lang/LC_MESSAGES/kim6.mo"
    msgfmt -o "$NEW_RUNTIME/locale/$lang/LC_MESSAGES/kim6.mo" "$po"
  done
fi
bash -n "$NEW_RUNTIME/bin/kim_all"

legacy_names=(kim_album kim_compress kim_convert kim_flipflop kim_galery kim_multiburst kim_other kim_pelemele kim_print kim_rename kim_resize kim_resizeandsend kim_rotate kim_rotatewithexif kim_sortbydate kim_stripmeta kim_treatment kim_video kim_webexport)
for name in "${legacy_names[@]}"; do
  old="$NEW_RUNTIME/bin/$name"
  source="$SOURCE_DIR/src/bin/$name"
  if [ -f "$old" ] && [ ! -L "$old" ]; then
    if [ -f "$source" ] && cmp -s -- "$old" "$source"; then
      rm -- "$old"
    else
      # The known legacy executable path establishes KIM ownership, but a
      # modified file may contain user edits. Keep a recovery copy outside bin.
      if [ -z "$USER_BACKUP" ]; then USER_BACKUP="$(mktemp -d "$NEW_RUNTIME/.kim6-preserved.XXXXXXXX")"; fi
      mkdir -p -- "$USER_BACKUP/legacy/bin"
      cp -a -- "$old" "$USER_BACKUP/legacy/bin/$name"
      chmod a-x -- "$USER_BACKUP/legacy/bin/$name"
      rm -- "$old"
    fi
  fi
done

menu_names=(kim_compress.desktop kim_compressandresize.desktop kim_convertandrotate.desktop kim_compressandresizevideo.desktop kim_publication.desktop)
for template in "$SOURCE_DIR"/src/kim_*.desktop.in; do
  name="$(basename -- "${template%.in}")"
  output="$NEW_MENUS/$name"
  intltool-merge --desktop-style "$SOURCE_DIR/po" "$template" "$output" >/dev/null
  chmod 0644 -- "$output"
  # Quote an absolute executable path using Desktop Entry Exec quoting rules.
  exec_path="$RUNTIME/bin/kim_all"
  exec_path="${exec_path//\\/\\\\}"
  exec_path="${exec_path//\"/\\\"}"
  exec_path="${exec_path//&/\\&}"
  exec_path="${exec_path//#/\\#}"
  sed -i "s#^Exec=kim_all\([[:space:]]\|$\)#Exec=\"$exec_path\"\\1#" "$output"
  if command -v desktop-file-validate >/dev/null 2>&1; then
    # This generic validator supports Application entries, not KDE's Type=Service
    # action groups. KDE's own cache builder is used below when available.
    if ! grep -q '^Type=Service$' "$output"; then
      desktop-file-validate "$output"
    fi
  fi
done
for name in "${menu_names[@]}"; do
  [ -f "$NEW_MENUS/$name" ] || { echo "install.sh: required menu missing: $name" >&2; exit 1; }
done

# Verify every installed Exec points at the staged dispatcher before touching
# the active installation. No source template or target menu is modified yet.
for menu in "$NEW_MENUS"/*.desktop; do
  if grep -Eq '^Exec=.*kim_(compress|convert|rotate|resize|video|galery|pelemele|other|album|print|rename|sortbydate|stripmeta|multiburst|treatment|resizeandsend|flipflop|webexport)\b|^Exec=(magick|convert|montage|ffmpeg|kdialog)\b' "$menu"; then
    echo "install.sh: legacy or direct processing Exec found in $menu" >&2; exit 1;
  fi
  grep -Eq '^Exec=".*kim6/bin/kim_all"( |$)' "$menu" || {
    echo "install.sh: menu does not target the installed dispatcher: $menu" >&2; exit 1;
  }
done

# Existing service-menu files are replaceable only when they carry our marker
# or match recognizable previous KIM Exec contracts. Customized unrelated
# files at the same names are left untouched and cause a safe preflight stop.
for name in "${menu_names[@]}"; do
  existing="$PREFIX/$name"
  if [ -e "$existing" ] || [ -L "$existing" ]; then
    [ ! -L "$existing" ] || { echo "install.sh: refusing to replace a symlinked menu: $existing" >&2; exit 1; }
    if ! grep -Eq '^X-KIM6-Managed=true$|^Exec=.*kim_(compress|convert|rotate|resize|video|galery|pelemele|other|album|print|rename|sortbydate|stripmeta|multiburst|treatment|resizeandsend|flipflop|webexport)\b|^Exec=(magick|convert|montage)\b' "$existing"; then
      echo "install.sh: refusing to replace an unrecognized customized menu: $existing" >&2
      exit 1
    fi
  fi
done

# When KDE's cache builder is present, validate staged Type=Service menus in
# an isolated XDG data/cache area before replacing the active installation.
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  check_data="$STAGE/check-data"
  check_cache="$STAGE/check-cache"
  mkdir -p -- "$check_data/kio/servicemenus" "$check_cache"
  cp -a -- "$NEW_MENUS/." "$check_data/kio/servicemenus/"
  XDG_DATA_HOME="$check_data" XDG_CACHE_HOME="$check_cache" \
    XDG_CONFIG_HOME="$STAGE/check-config" kbuildsycoca6 --noincremental >/dev/null 2>&1 || {
      echo "install.sh: KDE rejected the staged service-menu definitions" >&2
      exit 1
    }
fi

# Preserve customized prior menus and fingerprint every installed asset. This
# lets uninstall leave user edits untouched and lets a later upgrade back them up.
for name in "${menu_names[@]}"; do
  if [ -e "$PREFIX/$name" ]; then
    current="$(manifest_digest "$PREFIX/$name" 2>/dev/null || true)"
    expected="$(previous_manifest_digest "@menu:$name" 2>/dev/null || true)"
    if [ -z "$expected" ] || [ "$current" != "$expected" ]; then
      if [ -z "$USER_BACKUP" ]; then USER_BACKUP="$(mktemp -d "$NEW_RUNTIME/.kim6-preserved.XXXXXXXX")"; fi
      mkdir -p -- "$USER_BACKUP/menus"
      cp -a -- "$PREFIX/$name" "$USER_BACKUP/menus/$name"
    fi
  fi
done
rm -f -- "$NEW_RUNTIME/.kim6-manifest"
: > "$NEW_RUNTIME/.kim6-manifest"
manifest_paths=(bin/kim_all gallery/index.part1 gallery/index.part2 ABOUT LICENSE.md INSTALL.md docs/index.html docs/work.css)
for relative in "${manifest_paths[@]}"; do
  resource="$NEW_RUNTIME/$relative"
  [ -f "$resource" ] || continue
  digest="$(manifest_digest "$resource")" || { echo "install.sh: cannot fingerprint $relative" >&2; exit 1; }
  printf '%s\t%s\n' "$digest" "$relative" >> "$NEW_RUNTIME/.kim6-manifest"
done
if [ -d "$NEW_RUNTIME/locale" ]; then
  while IFS= read -r -d '' resource; do
    relative="${resource#"$NEW_RUNTIME/"}"
    digest="$(manifest_digest "$resource")" || { echo "install.sh: cannot fingerprint $relative" >&2; exit 1; }
    printf '%s\t%s\n' "$digest" "$relative" >> "$NEW_RUNTIME/.kim6-manifest"
  done < <(find "$NEW_RUNTIME/locale" -type f -name kim6.mo -print0)
fi
for name in "${menu_names[@]}"; do
  digest="$(manifest_digest "$NEW_MENUS/$name")"
  printf '%s\t@menu:%s\n' "$digest" "$name" >> "$NEW_RUNTIME/.kim6-manifest"
done

# Swap the fully prepared runtime tree, then replace only the five owned menu
# paths. Backups remain in the same filesystem until all replacements succeed.
if [ -e "$RUNTIME" ]; then mv -- "$RUNTIME" "$BACKUP/runtime"; backed_runtime=true; fi
mv -- "$NEW_RUNTIME" "$RUNTIME"
installed_runtime=true
for name in "${menu_names[@]}"; do
  if [ -e "$PREFIX/$name" ] || [ -L "$PREFIX/$name" ]; then
    mv -- "$PREFIX/$name" "$BACKUP/menus/$name"
    backed_menus+=("$name")
  fi
  mv -- "$NEW_MENUS/$name" "$PREFIX/$name"
  installed_menus+=("$name")
done

trap - EXIT
rm -rf -- "$STAGE"
if command -v kbuildsycoca6 >/dev/null 2>&1; then kbuildsycoca6 --noincremental >/dev/null 2>&1 || true; fi
echo "KIM6 unified dispatcher installed in $PREFIX."
[ -z "$USER_BACKUP" ] || echo "Customized pre-existing KIM resources were preserved under $RUNTIME/${USER_BACKUP##*/}."
for dependency in kdialog qdbus magick identify exiftool ffmpeg ffprobe xdg-email xdg-open; do
  command -v "$dependency" >/dev/null 2>&1 || echo "Optional/runtime dependency missing: $dependency"
done
