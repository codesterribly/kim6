#!/usr/bin/env bash
#
# Install KIMng's unified dispatcher, resources, and twelve menus.
# Usage: ./install.sh [--prefix SERVICEMENU_DIRECTORY]. The default user path
# is ${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus; root uses the first
# XDG_DATA_DIRS entry (default /usr/local/share). --prefix names that directory.
# Rerun to upgrade. Files are replaced individually through same-directory
# temporary files; a partial install is completed by rerunning this script.
# KIMng files are identified by the dispatcher or menu contents. Unknown files,
# unrelated menu collisions, and symlinks are preserved or refused. Changes to
# known application files are replaced on reinstall. kbuildsycoca6 is
# optional. kim_all checks media tools when needed.
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
# Validate before creating directories or replacing any installed files.
python3 -B "$SOURCE_DIR/src/bin/kim_desktop_exec.py" "$PREFIX" >/dev/null || {
  echo "install.sh: prefix cannot be represented in a Desktop Entry" >&2
  exit 2
}
# Display required and optional dependencies without installing packages.
# Distribution-specific package names are suggestions, not guarantees.
kim6_report_dependencies() {
  local os_name='Linux' os_id='' os_like='' manager='' host_name=''
  local group tool label purpose found package row status
  local required_ok=0 required_missing=0 optional_ok=0 optional_missing=0
  local -a missing_required=() missing_optional=()
  local -a required_rows=() optional_rows=()
  local -a required_packages=() optional_packages=() words=()
  local -A seen_required=() seen_optional=()

  if [ -r /etc/os-release ]; then
    . /etc/os-release
    os_name="${PRETTY_NAME:-Linux}"
    os_id="${ID:-}"
    os_like="${ID_LIKE:-}"
  fi

  case " $os_id $os_like " in
    *ubuntu*|*debian*) manager=apt ;;
    *fedora*|*rhel*|*centos*) manager=dnf ;;
    *arch*|*manjaro*) manager=pacman ;;
    *) manager=unknown ;;
  esac

  # Verified distribution package mappings.
  # A mapping may contain multiple packages when a module is split.
  # FFprobe is supplied by the FFmpeg package.
  kim6_suggest_package() {
    case "$manager:$1" in
      apt:magick) echo imagemagick-7.q16 ;;
      apt:exiftool) echo libimage-exiftool-perl ;;
      apt:kdialog) echo kdialog ;;
      apt:qdbus) echo qdbus-qt6 ;;
      apt:ffmpeg|apt:ffprobe) echo ffmpeg ;;
      apt:python3) echo python3 ;;
      apt:qtwidgets) echo python3-pyside6.qtwidgets ;;
      apt:qtnetwork) echo python3-pyside6.qtnetwork ;;
      apt:qtwebenginewidgets) echo python3-pyside6.qtwebenginewidgets ;;
      apt:xdg-open) echo xdg-utils ;;
      apt:pandoc) echo pandoc ;;
      apt:kbuildsycoca6) echo libkf6service-bin ;;

      dnf:magick) echo ImageMagick ;;
      dnf:exiftool) echo perl-Image-ExifTool ;;
      dnf:kdialog) echo kdialog ;;
      dnf:qdbus) echo qt6-qttools ;;
      dnf:ffmpeg|dnf:ffprobe) echo ffmpeg ;;
      dnf:python3) echo python3 ;;
      dnf:qtwidgets|dnf:qtnetwork) echo python3-pyside6 ;;
      dnf:qtwebenginewidgets) echo 'python3-pyside6 qt6-qtwebengine' ;;
      dnf:xdg-open) echo xdg-utils ;;
      dnf:pandoc) echo pandoc ;;
      dnf:kbuildsycoca6) echo kf6-kservice ;;

      pacman:magick) echo imagemagick ;;
      pacman:exiftool) echo perl-image-exiftool ;;
      pacman:kdialog) echo kdialog ;;
      pacman:qdbus) echo qt6-tools ;;
      pacman:ffmpeg|pacman:ffprobe) echo ffmpeg ;;
      pacman:python3) echo python ;;
      pacman:qtwidgets|pacman:qtnetwork) echo pyside6 ;;
      pacman:qtwebenginewidgets) echo 'pyside6 qt6-webengine' ;;
      pacman:xdg-open) echo xdg-utils ;;
      pacman:pandoc) echo pandoc ;;
      pacman:kbuildsycoca6) echo kservice ;;

      *) echo '' ;;
    esac
  }

  echo
  host_name="$(hostname -s 2>/dev/null || hostname)"
  echo 'KIMng | Dependency check'
  printf 'Host: %s\n' "$host_name"
  printf 'OS: %s\n' "$os_name"
  printf 'Package manager: %s\n' "$manager"

  while IFS='|' read -r group tool label purpose; do
    [ -n "$tool" ] || continue

    found=''

    case "$tool" in
      qdbus)
        found="$(type -P qdbus 2>/dev/null || true)"
        [ -n "$found" ] ||
          found="$(type -P qdbus6 2>/dev/null || true)"
        if [ -z "$found" ] && [ -x /usr/lib/qt6/bin/qdbus ]; then
          found=/usr/lib/qt6/bin/qdbus
        fi
        ;;
      qtwidgets)
        if python3 -c 'from PySide6.QtWidgets import QApplication, QDialog' \
          >/dev/null 2>&1; then
          found=available
        fi
        ;;
      qtwebenginewidgets)
        if python3 -c 'from PySide6.QtWebEngineWidgets import QWebEngineView' \
          >/dev/null 2>&1; then
          found=available
        fi
        ;;
      qtnetwork)
        if python3 -B "$SOURCE_DIR/src/bin/kim_location_map.py" --check \
          >/dev/null 2>&1; then
          found=available
        fi
        ;;
      *)
        found="$(command -v "$tool" 2>/dev/null || true)"
        ;;
    esac

    if [ -n "$found" ]; then
      status=OK
      if [ "$group" = required ]; then
        required_ok=$((required_ok + 1))
      else
        optional_ok=$((optional_ok + 1))
      fi
    else
      status=MISSING
      if [ "$group" = required ]; then
        required_missing=$((required_missing + 1))
        missing_required+=("$tool|$label")
      else
        optional_missing=$((optional_missing + 1))
        missing_optional+=("$tool|$label")
      fi
    fi

    # Store results for two clean sections, regardless of manifest order.
    if [ "$group" = required ]; then
      required_rows+=("$label|$purpose|$status")
    else
      optional_rows+=("$label|$purpose|$status")
    fi
  done <<'KIM6_DEPENDENCIES'
required|magick|ImageMagick|Image processing
required|exiftool|ExifTool|Metadata
required|kdialog|KDialog|KDE dialogs
required|qdbus|QtDBus|Desktop integration
required|ffmpeg|FFmpeg|Video processing
required|ffprobe|FFprobe|Video inspection
required|python3|Python 3|Application runtime
required|qtwidgets|PySide6 Qt Widgets|Graphical dialogs
required|qtnetwork|Qt map support|Maps and networking
required|xdg-open|xdg-open|Open output files
optional|qtwebenginewidgets|PySide6 WebEngine|Embedded HTML guide
optional|pandoc|Pandoc|HTML documentation
optional|kbuildsycoca6|KDE service cache|Menu cache refresh
KIM6_DEPENDENCIES

  # The table is displayed in two groups, independent of check order.
  printf '\n%-23s %-26s %s\n' 'REQUIRED DEPENDENCIES' 'PURPOSE' 'STATUS'
  printf '%s\n' '------------------------------------------------------------'
  for row in "${required_rows[@]}"; do
    IFS='|' read -r label purpose status <<< "$row"
    printf '%-23s %-26s %s\n' "$label" "$purpose" "$status"
  done

  printf '\n%-23s %-26s %s\n' 'OPTIONAL DEPENDENCIES' 'PURPOSE' 'STATUS'
  printf '%s\n' '------------------------------------------------------------'
  for row in "${optional_rows[@]}"; do
    IFS='|' read -r label purpose status <<< "$row"
    printf '%-23s %-26s %s\n' "$label" "$purpose" "$status"
  done

  printf '\n%s\n' '------------------------------------------------------------'

  if [ "$required_missing" -eq 0 ]; then
    printf 'PASS  %d/%d required dependencies available.\n' "$required_ok" "$required_ok"
  else
    printf 'WARN  %d/%d required dependencies missing.\n' "$required_missing" "$((required_ok + required_missing))"
  fi

  if [ "$optional_missing" -eq 0 ]; then
    printf 'PASS  %d/%d optional dependencies available.\n' "$optional_ok" "$optional_ok"
  else
    printf 'INFO  %d/%d optional dependencies available.\n' "$optional_ok" "$((optional_ok + optional_missing))"
  fi

  # Suggestions appear after the prerequisite table, only when needed.
  for entry in "${missing_required[@]}"; do
    IFS='|' read -r tool label <<< "$entry"
    package="$(kim6_suggest_package "$tool")"
    if [ -z "$package" ]; then
      printf 'No verified package mapping for: %s\n' "$label"
      continue
    fi
    read -r -a words <<< "$package"
    for package in "${words[@]}"; do
      if [ -z "${seen_required[$package]+yes}" ]; then
        required_packages+=("$package")
        seen_required["$package"]=1
      fi
    done
  done

  for entry in "${missing_optional[@]}"; do
    IFS='|' read -r tool label <<< "$entry"
    package="$(kim6_suggest_package "$tool")"
    if [ -z "$package" ]; then
      printf 'No verified package mapping for: %s\n' "$label"
      continue
    fi
    read -r -a words <<< "$package"
    for package in "${words[@]}"; do
      if [ -z "${seen_required[$package]+yes}" ] &&
         [ -z "${seen_optional[$package]+yes}" ]; then
        optional_packages+=("$package")
        seen_optional["$package"]=1
      fi
    done
  done

  if [ "${#required_packages[@]}" -gt 0 ] ||
     [ "${#optional_packages[@]}" -gt 0 ]; then
    echo
    echo 'MISSING DEPENDENCY PACKAGES'
    printf '%s\n' '------------------------------------------------------------'
    printf 'Target host: %s (%s)\n' "$host_name" "$os_name"

    local install_command=''
    case "$manager" in
      apt) install_command='sudo apt install' ;;
      dnf) install_command='sudo dnf install' ;;
      pacman) install_command='sudo pacman -S' ;;
    esac

    if [ "${#required_packages[@]}" -gt 0 ]; then
      printf 'Required packages for %s:\n' "$host_name"
      printf '  %s' "$install_command"
      printf ' %s' "${required_packages[@]}"
      printf '\n'
    fi

    if [ "${#optional_packages[@]}" -gt 0 ]; then
      printf 'Optional packages for %s:\n' "$host_name"
      printf '  %s' "$install_command"
      printf ' %s' "${optional_packages[@]}"
      printf '\n'
    fi

    echo
    echo 'Package availability depends on enabled distribution repositories.'
    echo 'Commands are suggestions only; KIMng does not install packages.'
  fi

  echo
}
kim6_report_dependencies

# Both graphical configuration dialogs require PySide6 Qt Widgets.
if ! python3 -c 'from PySide6.QtWidgets import QApplication, QDialog' >/dev/null 2>&1; then
  echo "install.sh: missing Python Qt 6 Widgets dependency." >&2
  echo "Affected: Settings, Collage, Contact Sheet, PDF Album," >&2
  echo "          Animated GIF, HTML Gallery, and D1 Location Tools dialogs." >&2
  echo "Install: sudo apt install python3-pyside6.qtwidgets" >&2
  exit 1
fi

# D1 uses software Qt painting, QtNetwork HTTPS and Qt's PNG decoder. This
# read-only probe creates no application/window and makes no network requests.
# Missing modules and local runtime/plugin defects must not look like readiness.
map_probe_output=''
if ! map_probe_output="$(python3 -B "$SOURCE_DIR/src/bin/kim_location_map.py" --check 2>&1)"; then
  printf '%s\n' "$map_probe_output" >&2
  echo "install.sh: D1 map dependencies are incomplete; installation stopped." >&2
  echo "Check the missing components reported above." >&2
  exit 1
fi
echo "PASS  Qt map modules, TLS, PNG and platform files available."
echo "      Display authorization and network access are checked at runtime."



[[ ! -L "$PREFIX" ]] || { echo "install.sh: refusing symlinked prefix: $PREFIX" >&2; exit 1; }
mkdir -p -- "$PREFIX"
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kimng"

# shellcheck source=install_inventory.sh
source "$SOURCE_DIR/install_inventory.sh"
temporary=''
die() { echo "install.sh: $*" >&2; exit 1; }
check_dir() { [[ ! -L "$1" && ( ! -e "$1" || -d "$1" ) ]] || die "refusing unsafe directory: $1"; }
check_file() { [[ ! -L "$1" && ( ! -e "$1" || -f "$1" ) ]] || die "refusing unsafe file: $1"; }

trap '[ -z "$temporary" ] || rm -f -- "$temporary"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Recognize only KIMng-owned installations.
# A populated runtime requires both its ownership marker and dispatcher.
dispatcher_is_kimng() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Fq '# KIMng runtime dispatcher' "$1"
}

menu_is_kimng() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    grep -Fxq 'X-KIMng-Managed=true' "$1" &&
    grep -Fq 'kimng/bin/kim_all' "$1"
}

runtime_is_empty() {
  [ -z "$(find "$RUNTIME" -mindepth 1 -print -quit)" ]
}

runtime_is_kimng() {
  [ -f "$RUNTIME/.kimng-owned" ] &&
    [ ! -L "$RUNTIME/.kimng-owned" ] &&
    [ "$(< "$RUNTIME/.kimng-owned")" = 'KIMng runtime' ] &&
    dispatcher_is_kimng "$RUNTIME/bin/kim_all"
}

if [ -e "$RUNTIME" ] || [ -L "$RUNTIME" ]; then
  check_dir "$RUNTIME"
  runtime_is_kimng || runtime_is_empty ||
    die "refusing to replace an unrecognized runtime directory: $RUNTIME"
fi

# Validate all installation destinations before modifying any files.
for directory in "$RUNTIME" "$RUNTIME/bin" "$RUNTIME/gallery" \
  "$RUNTIME/recipes" "$RUNTIME/docs" "$RUNTIME/docs/images" \
  "$RUNTIME/docs/reference"; do
  check_dir "$directory"
done

for relative in "${runtime_files[@]}" .kimng-owned .kimng-manifest; do
  check_file "$RUNTIME/$relative"
done

if [ -e "$RUNTIME/bin/kim_all" ] &&
   ! dispatcher_is_kimng "$RUNTIME/bin/kim_all"; then
  die "refusing to replace an unrecognized dispatcher: $RUNTIME/bin/kim_all"
fi

for name in "${menu_names[@]}"; do
  path="$PREFIX/$name"

  if [ -L "$path" ] ||
     { [ -e "$path" ] &&
       { [ ! -f "$path" ] || ! menu_is_kimng "$path"; }; }; then
    die "refusing unrelated or unsafe menu file: $path"
  fi
done

# Preflight the same complete inventory that will be copied. Nothing installed
# is replaced until every required source and menu template is present.
# shellcheck disable=SC2154
for relative in "${runtime_sources[@]}"; do
  [[ -f "$SOURCE_DIR/$relative" && ! -L "$SOURCE_DIR/$relative" ]] || die "required file is missing: $SOURCE_DIR/$relative"
done
for name in "${menu_names[@]}"; do
  [[ -f "$SOURCE_DIR/src/$name.in" && ! -L "$SOURCE_DIR/src/$name.in" ]] || die "menu template is missing: $SOURCE_DIR/src/$name.in"
done

# Keep the offline HTML User Guide synchronized with its Markdown sources.
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
  fi
fi

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

mkdir -p -- "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/recipes" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference"
# Retain ownership from the first file write, including interruptions.
temporary="$(mktemp "$RUNTIME/.kimng-owned.tmp.XXXXXX")"
printf 'KIMng runtime\n' > "$temporary"
chmod 0644 -- "$temporary"
mv -f -- "$temporary" "$RUNTIME/.kimng-owned"
temporary=''
for index in "${!runtime_files[@]}"; do
# shellcheck disable=SC2154
  install_file "$SOURCE_DIR/${runtime_sources[$index]}" "$RUNTIME/${runtime_files[$index]}" "${runtime_modes[$index]}"
done

# Use the same Desktop Entry encoder as Recipe rendering and ownership checks.
exec_path="$(python3 -B "$RUNTIME/bin/kim_desktop_exec.py" "$RUNTIME/bin/kim_all")"
for name in "${menu_names[@]}"; do
  destination="$PREFIX/$name"
  temporary="$(mktemp "$PREFIX/.${name}.tmp.XXXXXX")"
  python3 - "$SOURCE_DIR/src/$name.in" "$temporary" <<'KIMNG_MENU_RENDER'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])

content = source.read_text(encoding="utf-8")

# The templates use intltool's leading underscore to mark
# translatable Desktop Entry keys. Render their English values
# as ordinary Desktop Entry keys.
content = re.sub(
    r"^_([A-Za-z][A-Za-z0-9-]*)=",
    r"\1=",
    content,
    flags=re.MULTILINE,
)

if re.search(r"^_[A-Za-z][A-Za-z0-9-]*=", content, re.MULTILINE):
    raise SystemExit("Unrendered translation key")

if "[Desktop Entry]" not in content:
    raise SystemExit("Invalid Desktop Entry template")

target.write_text(content, encoding="utf-8")
KIMNG_MENU_RENDER
chmod 0755 -- "$temporary"
  # Pass data as arguments; a callable replacement adds no sed/regex escaping.
  python3 - "$exec_path" "$temporary" <<'KIM6_EXEC_REPLACE'
from pathlib import Path
import re
import sys

path = Path(sys.argv[2])
content = re.sub(r'^Exec=kim_all(?=[ \t]|$)', lambda _: 'Exec=' + sys.argv[1],
                 path.read_text(encoding='utf-8'), flags=re.MULTILINE)
path.write_text(content, encoding='utf-8')
KIM6_EXEC_REPLACE
  if [ "$name" = kim_location.desktop ]; then
    # Replacing the complete managed artifact removes the old Copy action too.
    if grep -Eq '^\[Desktop Action 02Copy\]$|^Exec=.*[[:space:]]location-copy[[:space:]]' "$temporary" ||
       [ "$(grep -c '^Exec=.*[[:space:]]location-apply -- %F$' "$temporary")" -ne 1 ]; then
      die "location menu must contain one Apply GPS entry and no redundant Copy GPS action"
    fi
  fi
  if ! grep -Fq "kimng/bin/kim_all" "$temporary"; then
    echo "install.sh: rendered menu does not reference the installed dispatcher: $name" >&2
    exit 1
  fi
  chmod 0755 -- "$temporary"
  if ! mv -f -- "$temporary" "$destination"; then
    echo "install.sh: could not install menu $destination" >&2
    exit 1
  fi
  temporary=''
done

python3 "$RUNTIME/bin/kim_recipe_core.py" --sync-menu || { echo "install.sh: Recipes shortcuts were not synchronized; retry using the installed dispatcher recipe --sync-menu" >&2; }

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

# Installation is incomplete if any required Qt helper is absent.
for relative in "${runtime_files[@]}"; do
  [[ "$relative" == bin/*.py ]] || continue
  helper="${relative#bin/}"
  helper_path="$RUNTIME/bin/$helper"

  if [ ! -f "$helper_path" ] || [ -L "$helper_path" ]; then
    echo "install.sh: required GUI helper was not installed: $helper_path" >&2
    exit 1
  fi

  if ! python3 - "$helper_path" <<'KIM6_PY_CHECK'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
compile(path.read_bytes(), str(path), "exec")
KIM6_PY_CHECK
  then
    echo "install.sh: invalid installed GUI helper: $helper_path" >&2
    exit 1
  fi
done

echo
echo
echo "======================================================================"
echo
echo "VERIFIED DESKTOP MENUS"
echo "----------------------"

menu_count=0
for name in "${menu_names[@]}"; do
  menu="$PREFIX/$name"

  if [ ! -f "$menu" ] || [ -L "$menu" ] ||
     ! grep -Fxq 'X-KIMng-Managed=true' "$menu" ||
     ! grep -Fq 'kimng/bin/kim_all' "$menu"; then
    die "installed menu is missing or invalid: $menu"
  fi

  printf '  %s\n' "$name"
  ((menu_count += 1))
done

[ "$menu_count" -eq "${#menu_names[@]}" ] ||
  die "expected ${#menu_names[@]} desktop menus, found $menu_count"

# Reject unexpected KIMng-owned menus.
for path in "$PREFIX"/kim*.desktop; do
  [ -f "$path" ] && [ ! -L "$path" ] || continue
  grep -Fxq 'X-KIMng-Managed=true' "$path" || continue

  name="${path##*/}"
  expected=false

  for candidate in "${menu_names[@]}"; do
    if [ "$name" = "$candidate" ]; then
      expected=true
      break
    fi
  done

  [ "$expected" = true ] ||
    die "unexpected KIMng-owned menu: $path"
done

echo
echo "VERIFIED QT HELPERS"
echo "-------------------"

for relative in "${runtime_files[@]}"; do
  [[ "$relative" == bin/*.py ]] || continue
  helper="${relative#bin/}"

  helper_path="$RUNTIME/bin/$helper"
  [ -f "$helper_path" ] && [ ! -L "$helper_path" ] ||
    die "required Qt helper is missing: $helper_path"

  printf '  %s\n' "$helper"
done

echo
echo "Bundled KIMng User Guide installed."

echo
echo "======================================================================"
echo " KIMng INSTALLATION COMPLETE"
echo "======================================================================"
echo
printf 'Installed to: %s\n' "$PREFIX"
echo
echo "Please restart Dolphin to see the KIMng menus."
