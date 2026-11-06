#!/usr/bin/env bash
#
# Install KIM6's unified dispatcher, resources, translations, and twelve menus.
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
# Validate before creating directories or replacing any installed files.
python3 -B "$SOURCE_DIR/src/bin/kim_desktop_exec.py" "$PREFIX" >/dev/null || {
  echo "install.sh: prefix cannot be represented in a Desktop Entry" >&2
  exit 2
}
# Display required and optional dependencies without installing packages.
# Distribution-specific package names are suggestions, not guarantees.
kim6_report_dependencies() {
  local os_name='Linux' os_id='' os_like='' manager=''
  local tool label purpose path package group entry
  local -a installed=() missing=() optional=() packages=()
  local -a optional_packages=()
  local -A seen_packages=() seen_optional_packages=()

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
    *suse*) manager=zypper ;;
  esac

  kim6_suggest_package() {
    local name="$1"
    case "$manager:$name" in
      apt:magick) echo imagemagick-7.q16 ;;
      apt:exiftool) echo libimage-exiftool-perl ;;
      apt:qdbus) echo qdbus-qt6 ;;
      apt:xdg-open) echo xdg-utils ;;
      apt:qtwidgets) echo python3-pyside6.qtwidgets ;;
      apt:qtnetwork) echo python3-pyside6.qtnetwork ;;
      apt:intltool-merge) echo intltool ;;
      apt:msgfmt) echo gettext ;;
      apt:kbuildsycoca6) echo libkf6service-bin ;;

      dnf:magick) echo ImageMagick ;;
      dnf:exiftool) echo perl-Image-ExifTool ;;
      dnf:qdbus) echo qt6-qttools ;;
      dnf:xdg-open) echo xdg-utils ;;
      dnf:qtwidgets) echo python3-pyside6 ;;
      dnf:qtnetwork) echo python3-pyside6 ;;
      dnf:intltool-merge) echo intltool ;;
      dnf:msgfmt) echo gettext ;;
      dnf:kbuildsycoca6) echo kf6-kservice ;;

      pacman:magick) echo imagemagick ;;
      pacman:exiftool) echo perl-image-exiftool ;;
      pacman:qdbus) echo qt6-tools ;;
      pacman:xdg-open) echo xdg-utils ;;
      pacman:qtwidgets) echo pyside6 ;;
      pacman:qtnetwork) echo pyside6 ;;
      pacman:intltool-merge) echo intltool ;;
      pacman:msgfmt) echo gettext ;;
      pacman:kbuildsycoca6) echo kservice ;;

      zypper:magick) echo ImageMagick ;;
      zypper:exiftool) echo perl-Image-ExifTool ;;
      zypper:qdbus) echo libqt6-qttools ;;
      zypper:xdg-open) echo xdg-utils ;;
      zypper:qtwidgets) echo python3-PySide6 ;;
      zypper:qtnetwork) echo python3-PySide6 ;;
      zypper:intltool-merge) echo intltool ;;
      zypper:msgfmt) echo gettext-tools ;;
      zypper:kbuildsycoca6) echo kf6-kservice ;;

      *) echo "$name" ;;
    esac
  }

  echo
  echo "======================================================================"
  echo " KIM6 DEPENDENCY CHECK"
  echo "======================================================================"
  printf 'System: %s\n' "$os_name"
  printf 'Package manager: %s\n' "${manager:-unknown}"

  while IFS='|' read -r group tool label purpose; do
    [ -n "$tool" ] || continue
    path=''

    case "$tool" in
      qdbus)
        path="$(type -P qdbus 2>/dev/null || true)"
        [ -n "$path" ] || path="$(type -P qdbus6 2>/dev/null || true)"
        if [ -z "$path" ] && [ -x /usr/lib/qt6/bin/qdbus ]; then
          path=/usr/lib/qt6/bin/qdbus
        fi
        ;;
      qtwidgets)
        if python3 -c 'from PySide6.QtWidgets import QApplication, QDialog' \
             >/dev/null 2>&1; then
          path="$(command -v python3)"
          path="$path (PySide6)"
        fi
        ;;
      qtnetwork)
        if python3 -B "$SOURCE_DIR/src/bin/kim_location_map.py" --check >/dev/null 2>&1; then
          path="$(command -v python3) (QtNetwork, TLS, PNG, platform plugin files)"
        fi
        ;;
      *)
        path="$(command -v "$tool" 2>/dev/null || true)"
        ;;
    esac

    if [ -n "$path" ]; then
      if [ "$group" = required ]; then
        installed+=("$label|$path|$purpose")
      else
        optional+=("installed|$label|$path|$purpose")
      fi
    else
      package="$(kim6_suggest_package "$tool")"
      if [ "$group" = required ]; then
        missing+=("$label|$package|$purpose")
        if [ -z "${seen_packages[$package]+yes}" ]; then
          packages+=("$package")
          seen_packages["$package"]=1
        fi
      else
        optional+=("missing|$label|$package|$purpose")
      fi
    fi
  done <<'KIM6_DEPENDENCIES'
required|magick|ImageMagick|Image conversion, resize and compression
required|exiftool|ExifTool|EXIF and metadata operations
required|kdialog|KDialog|KDE dialogs and progress
required|qdbus|QtDBus|KDE desktop integration
required|ffmpeg|FFmpeg|Video and animation processing
required|ffprobe|FFprobe|Video and audio inspection
required|python3|Python 3|Application helpers
required|qtwidgets|PySide6 Qt Widgets|Graphical configuration dialogs
required|qtnetwork|D1 map capabilities|Qt Network, TLS, PNG decoding and platform plugin files
required|xdg-open|xdg-open|Opening generated output
required|intltool-merge|intltool|Dolphin menu generation
optional|pandoc|Pandoc|HTML manual generation
optional|msgfmt|gettext tools|Translation catalog compilation
optional|kbuildsycoca6|KDE service cache|Desktop service cache refresh
KIM6_DEPENDENCIES

  echo
  echo "Installed"
  echo "---------"
  for entry in "${installed[@]}"; do
    IFS='|' read -r label path purpose <<< "$entry"
    printf '  %-21s %-30s %s\n' "$label" "$path" "$purpose"
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    echo
    echo "Missing Required"
    echo "----------------"
    for entry in "${missing[@]}"; do
      IFS='|' read -r label package purpose <<< "$entry"
      printf '  %-21s %-30s %s\n' "$label" "Package: $package" "$purpose"
    done

    echo
    echo "Suggested installation:"
    case "$manager" in
      apt) printf '  sudo apt install' ;;
      dnf) printf '  sudo dnf install' ;;
      pacman) printf '  sudo pacman -S' ;;
      zypper) printf '  sudo zypper install' ;;
      *) printf '  Use your distribution package manager for:' ;;
    esac
    printf ' %s' "${packages[@]}"
    printf '\n'
    echo "Package availability and names may vary by distribution release."
  fi

  echo
  echo "Optional"
  echo "--------"
  for entry in "${optional[@]}"; do
    IFS='|' read -r group label path purpose <<< "$entry"
    if [ "$group" = installed ]; then
      printf '  %-21s %-30s %s\n' "$label" "$path" "$purpose"
    else
      printf '  %-21s %-30s %s\n' "$label" "Not installed" "$purpose"

      case "$label" in
        Pandoc) tool=pandoc ;;
        "gettext tools") tool=msgfmt ;;
        "KDE service cache") tool=kbuildsycoca6 ;;
        *) continue ;;
      esac

      package="$(kim6_suggest_package "$tool")"

      if [ -z "${seen_optional_packages[$package]+yes}" ]; then
        optional_packages+=("$package")
        seen_optional_packages["$package"]=1
      fi
    fi
  done

  if [ "${#optional_packages[@]}" -gt 0 ]; then
    echo
    printf 'Suggested optional packages for %s:\n' "$os_name"

    case "$manager" in
      apt) printf '  sudo apt install' ;;
      dnf) printf '  sudo dnf install' ;;
      pacman) printf '  sudo pacman -S' ;;
      zypper) printf '  sudo zypper install' ;;
      *) printf '  Packages:' ;;
    esac

    printf ' %s' "${optional_packages[@]}"
    printf '\n'
  fi

  if [ "${#missing[@]}" -eq 0 ]; then
    echo
    echo "PASS: All required dependencies available."
  else
    echo
    echo "WARNING: Some required dependencies are unavailable."
  fi

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
if ! python3 -B "$SOURCE_DIR/src/bin/kim_location_map.py" --check; then
  echo "install.sh: D1 map dependencies are incomplete; installation stopped." >&2
  echo "Use the package-manager command above for system Python. For pip-managed Python," >&2
  echo "use its interpreter with the matching-version PySide6-Essentials repair command reported by the probe." >&2
  exit 1
fi
echo "D1 display connection, remote X11 authorization, network and map-provider availability must be checked at runtime."



command -v intltool-merge >/dev/null 2>&1 || {
  echo "install.sh: install intltool-merge to render translated Dolphin menus" >&2
  exit 1
}
[[ ! -L "$PREFIX" ]] || { echo "install.sh: refusing symlinked prefix: $PREFIX" >&2; exit 1; }
mkdir -p -- "$PREFIX"
PREFIX="$(cd -P -- "$PREFIX" && pwd -P)"
RUNTIME="$PREFIX/kim6"

# shellcheck source=install_inventory.sh
source "$SOURCE_DIR/install_inventory.sh"
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
    grep -Eq '^X-KIM6-Managed=true$|^Exec=.*(kim_all|kim_(album|compress|convert|flipflop|galery|multiburst|other|collage|print|rename|resize|resizeandsend|rotate|rotatewithexif|sortbydate|stripmeta|treatment|video|webexport))(["[:space:]]|$)' "$1"
}
runtime_is_empty() {
  # Empty folders can be leftovers from interruption before the first copy.
  [ -z "$(find "$RUNTIME" -mindepth 1 ! -type d -print -quit)" ]
}
has_kim_menu() {
  local name
# shellcheck disable=SC2154
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
# shellcheck disable=SC2154
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
for directory in "$RUNTIME" "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/recipes" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference" "$RUNTIME/locale"; do
  check_dir "$directory"
done
# shellcheck disable=SC2154
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
# shellcheck disable=SC2154
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

mkdir -p -- "$RUNTIME/bin" "$RUNTIME/gallery" "$RUNTIME/recipes" "$RUNTIME/docs" "$RUNTIME/docs/images" "$RUNTIME/docs/reference"
# Retain ownership from the first file write, including interruptions.
temporary="$(mktemp "$RUNTIME/.kim6-owned.tmp.XXXXXX")"
printf 'KIM6 runtime\n' > "$temporary"
chmod 0644 -- "$temporary"
mv -f -- "$temporary" "$RUNTIME/.kim6-owned"
temporary=''
for index in "${!runtime_files[@]}"; do
# shellcheck disable=SC2154
  install_file "$SOURCE_DIR/${runtime_sources[$index]}" "$RUNTIME/${runtime_files[$index]}" "${runtime_modes[$index]}"
done

if command -v msgfmt >/dev/null 2>&1; then
  for language in "${languages[@]}"; do
    if [ -f "$SOURCE_DIR/po/$language.po" ]; then compile_translation "$language"; fi
  done
else
  echo "install.sh: msgfmt is unavailable; menu translations will still be installed, compiled message catalogs were skipped." >&2
fi

# Use the same Desktop Entry encoder as Recipe rendering and ownership checks.
exec_path="$(python3 -B "$RUNTIME/bin/kim_desktop_exec.py" "$RUNTIME/bin/kim_all")"
for name in "${menu_names[@]}"; do
  destination="$PREFIX/$name"
  temporary="$(mktemp "$PREFIX/.${name}.tmp.XXXXXX")"
  intltool-merge --desktop-style "$SOURCE_DIR/po" "$SOURCE_DIR/src/$name.in" "$temporary" >/dev/null
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
  if ! grep -Fq "kim6/bin/kim_all" "$temporary"; then
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

# Retire only the known KIM legacy command names after the new menus are in place.
for name in "${legacy_names[@]}"; do
  path="$RUNTIME/bin/$name"
  if [ -f "$path" ]; then rm -f -- "$path"; fi
done
rm -f -- "$RUNTIME/.kim6-manifest"


# Retire verified obsolete KIM6 menus, regardless of filename.
# Never follow symlinks or remove unrelated desktop entries.
kim6_retire_obsolete_menus() {
  local path name expected current

  for path in "$PREFIX"/kim*.desktop; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    [ ! -L "$path" ] || continue
    [ -f "$path" ] || continue

    name="${path##*/}"
    current=false

    for expected in "${menu_names[@]}"; do
      if [ "$name" = "$expected" ]; then
        current=true
        break
      fi
    done

    [ "$current" = false ] || continue

    if menu_is_kim6 "$path"; then
      rm -f -- "$path" || return 1
      echo "install.sh: retired obsolete KIM6 menu: $name"
    fi
  done
}

kim6_retire_obsolete_menus

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
     ! grep -Fxq 'X-KIM6-Managed=true' "$menu" ||
     ! grep -Fq 'kim6/bin/kim_all' "$menu"; then
    die "installed menu is missing or invalid: $menu"
  fi

  printf '  %s\n' "$name"
  ((menu_count += 1))
done

[ "$menu_count" -eq "${#menu_names[@]}" ] ||
  die "expected ${#menu_names[@]} desktop menus, found $menu_count"

# A successful installation must not leave obsolete KIM6 menus behind.
for path in "$PREFIX"/kim*.desktop; do
  [ -f "$path" ] && [ ! -L "$path" ] || continue

  name="${path##*/}"
  current=false

  for expected in "${menu_names[@]}"; do
    if [ "$name" = "$expected" ]; then
      current=true
      break
    fi
  done

  if [ "$current" = false ] && menu_is_kim6 "$path"; then
    die "obsolete KIM6 menu remains: $path"
  fi
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
echo "Bundled KIM6 User Guide installed."

echo
echo "======================================================================"
echo " KIM6 INSTALLATION COMPLETE"
echo "======================================================================"
echo
printf 'Installed to: %s\n' "$PREFIX"
echo
echo "Please restart Dolphin to see the KIM6 menus."
