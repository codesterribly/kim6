
# Install KIMng

KIMng adds image, recipe, and video service-menu actions to KDE Dolphin. This version is a substantial rewrite of the original project and is designed for KDE Plasma 6.

## Install through Dolphin

Dolphin can install service menus from its online catalog. Open **Settings → Configure Dolphin → Services**, then choose **Download New Services** and search for KIMng. The existing catalog listing may still use the former KIM6 name.

The KIMng rewrite may not yet be available through that catalog. The KDE Store may still offer an earlier version; check the release information if you specifically want this rewrite.

## Embedded HTML User Guide prerequisite

KIMng includes an illustrated HTML User Guide in the
**Settings/About > User Guide** tab. Rendering that guide
inside the application requires the Python binding
`PySide6.QtWebEngineWidgets`, not just the Qt WebEngine runtime
libraries.

On Ubuntu or Debian, install the binding with:

```bash
sudo apt install python3-pyside6.qtwebenginewidgets
```

Verify that the same system Python interpreter used by KIMng can
import it:

```bash
python3 -c 'from PySide6.QtWebEngineWidgets import QWebEngineView; print("WebEngine available")'
```

The installer reports this dependency separately from required
image-processing tools. It does not automatically install system
packages. Without the binding, KIMng can still operate and its guide
can be opened in an external browser, but the embedded tab uses a
limited Markdown fallback.

The installed HTML guide and its local images must remain together
under the KIMng runtime `docs/` directory. Qt WebEngine uses those
local files to display the guide offline.

## Install this rewrite manually

KIMng requires KDE Plasma 6 and Dolphin.

To install from a source checkout, you need Python 3 and PySide6 Qt Widgets (and Git if cloning the source). KIMng currently ships with an English interface. Older translation catalogs have been retired, and translated catalogs are not required for installation. The installer checks the required processing tools before installing.

KIMng uses several common tools to process images and videos:

- **ImageMagick 7:** Image resizing, compression, conversion, galleries, and other image operations.
- **ExifTool:** Metadata management, photo dates, and copyright information.
- **FFmpeg and ffprobe:** Video conversion, audio extraction, animations, and slideshows.
- **KDialog and qdbus:** Dialogs, progress reporting, and interaction with KDE.
- **Email application (optional):** Required for the Send via email workflow. If no supported mail client is available, KIMng blocks attachment preparation.

Some image formats and video codecs require additional system support. See [Formats and codecs](docs/FORMATS.md). A declared extension is not proof that the installed encoder or delegate can process a file. APNG has operation-specific processing paths and restrictions. Resize and Web Export refuse animated APNG to prevent silent frame loss. Backend availability does not imply that every APNG workflow is enabled in the graphical interface.

**Output policy:** In Dolphin, open **Actions → KIMng - Settings/About → Settings** to choose whether supported actions automatically create separate files or prompt you to choose. Overwriting originals still requires explicit approval and a second warning. Rotation and EXIF auto-orientation can support authorized replacement, while horizontal and vertical Flip always publish separate reviewed copies. Other derived-only actions keep sources intact. Advanced environment overrides are described in [Configuration and Defaults](docs/commandconfig.md#configuration-and-defaults).

Download or clone the KIMng source code, then open a terminal in the project directory and run:

```sh
./install.sh
```

If you downloaded a source archive, extract it first and run the installer from the extracted folder.

The installer adds KIMng's program files and service-menu definitions to your user installation directory. By default this is `${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus`, with application files under its `kimng` subdirectory. Restart Dolphin, then right-click an image or video to see the KIMng actions available for that file type.

The `kim_all` program is installed with the menus and does not need to be added to your shell's `PATH`.


## Dependency packages by distribution

The dependency report runs on the machine executing `install.sh`.
Its hostname and operating system identify where any suggested
installation command applies. Suggested packages appear after
the dependency table **only when a dependency is missing**.
KIMng does not install system packages automatically.

The following table describes the package mappings for Ubuntu,
Fedora, and Arch used by the installer. Package availability
may depend on the distribution release and enabled repositories.

| Component | Ubuntu (apt) | Fedora (dnf) | Arch (pacman) |
|---|---|---|---|
| ImageMagick (`magick` and `identify`) | `imagemagick-7.q16` | `ImageMagick` | `imagemagick` |
| ExifTool | `libimage-exiftool-perl` | `perl-Image-ExifTool` | `perl-image-exiftool` |
| KDialog | `kdialog` | `kdialog` | `kdialog` |
| QtDBus | `qdbus-qt6` | `qt6-qttools` | `qt6-tools` |
| FFmpeg and FFprobe | `ffmpeg` | `ffmpeg` | `ffmpeg` |
| Poppler PDF rendering (optional) | `poppler-utils` | `poppler-utils` | `poppler` |
| Python | `python3` | `python3` | `python` |
| PySide6 Widgets | `python3-pyside6.qtwidgets` | `python3-pyside6` | `pyside6` |
| PySide6 Network | `python3-pyside6.qtnetwork` | `python3-pyside6` | `pyside6` |
| PySide6 WebEngine (optional) | `python3-pyside6.qtwebenginewidgets` | `python3-pyside6` + `qt6-qtwebengine` | `pyside6` + `qt6-webengine` |
| xdg-open | `xdg-utils` | `xdg-utils` | `xdg-utils` |
| Pandoc (optional) | `pandoc` | `pandoc` | `pandoc` |
| KDE service cache (optional) | `libkf6service-bin` | `kf6-kservice` | `kservice` |

The optional Qt WebEngine Python binding enables the full
illustrated HTML User Guide within KIMng. The standalone guide
uses an HTML viewer and offers an external-browser fallback
when WebEngine is unavailable.

Installed KDE service-menu `.desktop` files intentionally
have mode `0755`. Do not change them to `0644`, which can
produce Dolphin execution-authorization errors.

After installation, open **Settings/About → Settings…** in Dolphin to configure KIMng's output preferences.

[View KIMng Settings](docs/images/screenshots/10-settings-menu.png)

## What `install.sh` does

The installer prepares KIMng for Dolphin, checks the installation
environment, and verifies the installed components. It does not install
system packages, change KDE settings, or modify your images and videos.

### Dependency checks

The installer detects the Linux distribution and package manager, then
reports installed and missing dependencies. It recognizes APT, DNF, and Pacman and suggests appropriate package installation commands
when dependencies are missing. Package availability may vary by distribution.

Python 3 with PySide6 Qt Widgets and QtNetwork map support is mandatory for
installation. The installer runs `python3 src/bin/kim_location_map.py --check` and stops if the map dependency check fails. ImageMagick's `magick` and `identify` executables are checked separately. Missing image-processing or video tools are reported as
warnings rather than automatically installed. Individual KIMng actions
check for the tools they need when invoked.

Optional tools include Poppler for PDF source operations, Pandoc for generating HTML documentation, and `kbuildsycoca6` for refreshing KDE's service cache. PDF page rendering requires `pdfinfo` and `pdftoppm`; embedded-image extraction requires `pdfimages`. The installer reports the Poppler rendering probe separately from action-specific capability checks.

### Filesystem and source validation

Before installing application files, `install.sh`:

- Checks that the destination service-menu directory is usable and not
  a symbolic link.
- Identifies existing KIMng program files and service menus before
  replacing them.
- Rejects unsafe symbolic links, conflicting service-menu files, and
  unrecognized runtime directories.
- Checks the source checkout for required executables, graphical dialog
  helpers, resources, documentation, and menu templates.
- Protects unrelated files from replacement.

A conflict or missing mandatory source file stops installation rather
than proceeding with an unsafe or incomplete installation.

### Installing KIMng components

The installer places the unified `kim_all` dispatcher and its supporting
files in a `kimng` directory beneath the selected service-menu directory.

The installed components include:

- The image and video command dispatcher.
- A complete inventory of 111 runtime files, including program modules, resources and offline documentation.
- 62 installed Python dialog, processing, and application helper modules, as enumerated in `install_inventory.sh`.
- Metadata processing and format-verification helpers.
- Gallery generation resources.
- 12 Dolphin service-menu definitions, including the Recipes submenu.
- The English source interface (no translated language catalogs currently ship).
- The offline HTML User Guide, illustrations, stylesheet, and reference pages.

The installer renders the English values of the menu templates using its own Python renderer (without an `intltool-merge` dependency) and replaces their command references with the absolute
path to the installed dispatcher. No manual shell `PATH` changes are needed.

### Safe file replacement

Each installed file is written to a temporary file beside its destination
and then moved into place. This prevents an interrupted copy from leaving
that individual destination file partially written.

Installation is not a whole-tree transaction. An interruption can leave
different installed files at different revision levels. Rerunning
`./install.sh` completes or repairs the installation.

The installer replaces recognized existing program and menu files. Save any
personal modifications to those files before upgrading.

### Post-installation verification

After copying files, the installer:

- Confirms that all 12 installed Dolphin menus exist, carry KIMng's
  identification marker, and reference the installed dispatcher.
- Confirms that all 62 installed Python helper files are present,
  are not symbolic links, and have valid Python syntax.
- Refreshes the KDE service cache with `kbuildsycoca6` when available.
- Prints verified menu and helper counts, installation paths,
  and a completion summary. Use `--verbose` to list individual
  installed files and verified helpers.

Successful installation confirms that the installed components are
present and structurally valid. It does not guarantee that every optional
media encoder or format delegate is available, or that Dolphin is free
of KDE menu-display problems.

For additional implementation details, see
[Installer safety and recovery](docs/DEVELOPMENT.md#installer-safety-and-recovery).


To check the installed program without opening Dolphin:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus/kimng/bin/kim_all" --help
```

If the menus do not appear, restart Dolphin and verify that KIMng was installed in a service-menu directory recognized by KDE.

**KDE Frameworks 6.29 issue:** Frameworks 6.29 introduced a regression that prevented some Dolphin service submenus from appearing. This was fixed in Frameworks 6.30. If you are using the affected version, update KDE Frameworks when a fixed package is available for your distribution.

KIMng retains its normal submenu structure; you do not need to modify the service-menu files to work around this issue.

## Upgrade or reinstall

Use the newer source checkout and run `./install.sh` again. Installation is performed one file at a time. If it is interrupted, run the installer again to finish.

Known KIMng files are replaced. Explicitly retired documentation files from earlier KIMng installations are removed from verified KIMng runtime directories. Unrelated files are left alone. If you modified a KIMng menu or program file yourself, save a copy before upgrading because the installer replaces it. Installation updates are per-file, not a whole-tree transaction; rerun the installer after an interruption. The new output-policy confirmation applies to KIMng image/video actions, not to the installer's replacement of its own known program files.

## Uninstall

From the source directory, run:

```sh
./uninstall.sh
```

The uninstaller removes the 12 recognized KIMng menus and the known KIMng program files. It leaves unrelated files in place. Use `--prefix DIR` for a specific service-menu directory, `--no_message` to suppress normal completion output, `--verbose` for individual removed-file details, or `-h`/`--help` for usage. Restart Dolphin after removal.

## Advanced installation locations

To choose a service-menu folder explicitly, use `--prefix`:

```sh
./install.sh --prefix "$HOME/.local/share/kio/servicemenus"
```

For a system-wide installation, first check which service-menu directories KDE recognizes:

```sh
qtpaths6 --locate-dirs GenericDataLocation kio/servicemenus
```

Choose a system-wide directory from the output, then install with administrator privileges. For example, if your system uses `/usr/share/kio/servicemenus`:

```sh
sudo ./install.sh --prefix /usr/share/kio/servicemenus
```

To uninstall a system-wide installation, use the same directory:

```sh
sudo ./uninstall.sh --prefix /usr/share/kio/servicemenus
```

The installer creates the chosen folder if needed. It does not install system packages, change KDE settings, or modify your images and videos.

## Installation and Removal Troubleshooting

### Dolphin does not show an action

First verify that all 12 KIMng service-menu files were installed to a KDE service-menu directory and that the installed menu files contain the expected `kim_all` command. Confirm that the action’s MIME filter matches the selected local file. KDE may require a logout/login or menu-cache refresh. KDE Frameworks 6.29 can prevent Dolphin service submenus from appearing. KIMng keeps its normal submenu structure rather than modifying the menu files to work around this issue. Installation can be verified without relying on submenu display; see the installation instructions above.

### Installation or removal reports a conflict
The installer identifies existing KIMng installations using its ownership
marker and recognized program files. It also accepts an empty runtime
directory left by an interrupted installation. An owned runtime with a
missing dispatcher can be repaired by rerunning the installer. An
unfamiliar dispatcher, unsafe symbolic link or unrecognized runtime
directory still blocks installation. Unrelated files are protected.

Installation and removal operate one file at a time, not as a single
transaction. If installation is interrupted, rerun `./install.sh`.
There is no automatic rollback.

Upgrades replace known KIMng program and menu files. Save any customizations
before upgrading. Unknown files are preserved and may prevent their
containing directory from being removed. The message `unknown runtime content preserved` indicates that the uninstaller retained content outside its managed inventory. Do not delete that content merely to make the directory disappear. A recognized owned runtime can be reinstalled while retaining those unrelated files.

For installer safeguards and recovery procedures, see
[Installer safety and recovery](docs/DEVELOPMENT.md#installer-safety-and-recovery).

## Offline User Guide and documentation updates

The installed User Guide includes a dedicated Recipes reference describing the Recipes submenu, editor, preview, and protected output behavior.

KIMng installs a complete offline User Guide, including its stylesheet,
illustrations, and HTML reference pages. The User Guide is available through
the User Guide action in Dolphin.

When Python 3 and Pandoc are installed, running `./install.sh` from a
writable, non-root development checkout automatically regenerates the
HTML references from the project's Markdown documentation.

For root installations or checkouts where the reference directory is
not writable, the installer verifies the generated HTML rather than
modifying the source files, provided both tools are available. If the
generated pages are outdated, installation stops.

The prebuilt User Guide can be viewed in a web browser without Python
or Pandoc. Python 3 remains a mandatory KIMng runtime dependency.
If Pandoc is unavailable during installation, KIMng uses the prebuilt
HTML pages supplied with the repository.

Contributors should commit regenerated HTML reference pages alongside
their Markdown changes. The illustrated landing page is maintained
separately and is not automatically generated.

## Detailed installer output

The installer and uninstaller normally display a compact summary.
Use `--verbose` to list individual installed or removed runtime files.

    bash install.sh --verbose
    bash uninstall.sh --verbose

Interactive terminals display colored dependency statuses and installation
progress. Redirected output uses plain text. Set `NO_COLOR=1` to disable
terminal colors and animated progress.

    NO_COLOR=1 bash install.sh

Presentation options do not change installation destinations, dependency
requirements, ownership checks, overwrite protections or removal behavior.
