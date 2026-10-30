
# Install KIM6

KIM6 adds ten image and video service-menu files to KDE Dolphin. This version is a substantial rewrite of the original project and is designed for KDE Plasma 6.

## Install through Dolphin

Dolphin can install service menus from its online catalog. Open **Settings → Configure Dolphin → Services**, then choose **Download New Services** and search for KIM6.

The rewritten KIM6 may not yet be available through that catalog. The KDE Store may still offer an earlier version; check the release information if you specifically want this rewrite.

## Install this rewrite manually

KIM6 requires KDE Plasma 6 and Dolphin.

To install from a source checkout, you need `intltool-merge`, Python 3, and PySide6 Qt Widgets (and Git if you are cloning the source). The installer uses `msgfmt` to compile translations when available; without it, the menus can still be installed in English.

KIM6 uses several common tools to process images and videos:

- **ImageMagick 7:** Image resizing, compression, conversion, galleries, and other image operations.
- **ExifTool:** Metadata management, photo dates, and copyright information.
- **FFmpeg and ffprobe:** Video conversion, audio extraction, animations, and slideshows.
- **KDialog and qdbus:** Dialogs, progress reporting, and interaction with KDE.
- **Email application (optional):** Required only to open a draft automatically. KIM6 can still prepare attachment files and report their location for manual attachment.

Some image formats and video codecs require additional system support. See [Formats and codecs](docs/FORMATS.md). A declared extension is not proof that the installed encoder or delegate can process a file. Animated APNG conversion uses FFmpeg; Resize and Web Export refuse animated APNG to prevent silent frame loss.

**Output policy:** In Dolphin, open **Actions → KIM6 — Settings/About → Settings** to choose whether supported actions automatically create separate files or prompt you to choose. Overwriting originals still requires explicit approval and a second warning. Rotation, EXIF auto-orientation, flip and flop support both modes; derived-only actions keep sources intact. Advanced environment overrides are described in [Configuration and Defaults](docs/commandconfig.md#configuration-and-defaults).

Download or clone the KIM6 source code, then open a terminal in the project directory and run:

```sh
./install.sh
```

If you downloaded a source archive, extract it first and run the installer from the extracted folder.

The installer adds KIM6's program files and ten service-menu definitions to your user installation directory. Restart Dolphin, then right-click an image or video to see the KIM6 actions available for that file type.

The `kim_all` program is installed with the menus and does not need to be added to your shell's `PATH`.


## What `install.sh` does

The installer prepares KIM6 for Dolphin, checks the installation
environment, and verifies the installed components. It does not install
system packages, change KDE settings, or modify your photographs and videos.

### Dependency checks

The installer detects the Linux distribution and package manager, then
reports installed and missing dependencies. It recognizes APT, DNF,
Pacman, and Zypper and suggests appropriate package installation commands
when dependencies are missing. Package availability may vary by distribution.

Python 3 with PySide6 Qt Widgets and `intltool-merge` are mandatory for
installation. Missing image-processing or video tools are reported as
warnings rather than automatically installed. Individual KIM6 actions
check for the tools they need when invoked.

Optional tools include `msgfmt` for compiled translations, Pandoc for
generating HTML documentation, and `kbuildsycoca6` for refreshing KDE's
service cache.

### Filesystem and source validation

Before installing application files, `install.sh`:

- Checks that the destination service-menu directory is usable and not
  a symbolic link.
- Identifies existing KIM6 program files and service menus before
  replacing them.
- Rejects unsafe symbolic links, conflicting service-menu files, and
  unrecognized runtime directories.
- Checks the source checkout for required executables, graphical dialog
  helpers, resources, documentation, and menu templates.
- Protects unrelated files from replacement.

A conflict or missing mandatory source file stops installation rather
than proceeding with an unsafe or incomplete installation.

### Installing KIM6 components

The installer places the unified `kim_all` dispatcher and its supporting
files in a `kim6` directory beneath the selected service-menu directory.

The installed components include:

- The image and video command dispatcher.
- Seven Python graphical dialog and application helper files.
- Metadata processing and format-verification helpers.
- Gallery generation resources.
- Ten Dolphin service-menu definitions.
- Available compiled translation catalogs.
- The offline HTML manual, illustrations, stylesheet, and reference pages.

The installer generates the Dolphin service-menu entries using
`intltool-merge` and replaces their command references with the absolute
path to the installed dispatcher. No manual shell `PATH` changes are needed.

### Safe file replacement

Each installed file is written to a temporary file beside its destination
and then moved into place. This prevents an interrupted copy from leaving
that individual destination file partially written.

Installation is not a whole-tree transaction. An interruption can leave
different installed files at different revision levels. Rerunning
`./install.sh` completes or repairs the installation.

The installer replaces recognized KIM6 program and menu files. Save any
personal modifications to those files before upgrading.

### Post-installation verification

After copying files, the installer:

- Confirms that all ten installed Dolphin menus exist, carry KIM6's
  identification marker, and reference the installed dispatcher.
- Confirms that the seven required Python helper files are present,
  are not symbolic links, and have valid Python syntax.
- Refreshes the KDE service cache with `kbuildsycoca6` when available.
- Prints the verified menu and helper inventories, installation path,
  and completion message.

Successful installation confirms that the installed components are
present and structurally valid. It does not guarantee that every optional
media encoder or format delegate is available, or that Dolphin is free
of KDE menu-display problems.

For additional implementation details, see
[Installer safety and recovery](docs/DEVELOPMENT.md#installer-safety-and-recovery).


To check the installed program without opening Dolphin:

```sh
"${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus/kim6/bin/kim_all" --help
```

If the menus do not appear, restart Dolphin and verify that KIM6 was installed in a service-menu directory recognized by KDE.

**KDE Frameworks 6.29 issue:** Frameworks 6.29 introduced a regression that prevented some Dolphin service submenus from appearing. This was fixed in Frameworks 6.30. If you are using the affected version, update KDE Frameworks when a fixed package is available for your distribution.

KIM6 retains its normal submenu structure; you do not need to modify the service-menu files to work around this issue.

## Upgrade or reinstall

Use the newer source checkout and run `./install.sh` again. Installation is performed one file at a time. If it is interrupted, run the installer again to finish.

Known KIM6 files are replaced, while unrelated files in the installation folder are left alone. If you modified a KIM6 menu or program file yourself, save a copy before upgrading because the installer replaces it. Installation updates are per-file, not a whole-tree transaction; rerun the installer after an interruption. The new output-policy confirmation applies to KIM6 image/video actions, not to the installer's replacement of its own known program files.

## Uninstall

From the source directory, run:

```sh
./uninstall.sh
```

The uninstaller removes the ten recognized KIM6 menus and the known KIM6 program files. It leaves unrelated files in place. Restart Dolphin after removal.

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

The installer creates the chosen folder if needed. It does not install system packages, change KDE settings, or modify your photographs and videos.

## Installation and Removal Troubleshooting

### Dolphin does not show an action

First verify that all ten KIM6 service-menu files were installed to a KDE service-menu directory and that the installed menu files contain the expected `kim_all` command. Confirm that the action’s MIME filter matches the selected local file. KDE may require a logout/login or menu-cache refresh. KDE Frameworks 6.29 can prevent Dolphin service submenus from appearing. KIM6 keeps its normal submenu structure rather than modifying the menu files to work around this issue. Installation can be verified without relying on submenu display; see the installation instructions above.

### Installation or removal reports a conflict
The installer identifies existing KIM6 installations from recognized program
and service-menu files. It also accepts an empty runtime directory left by
an interrupted installation. Unrelated files and unsafe symlinked paths
are protected from replacement or removal.

Installation and removal operate one file at a time, not as a single
transaction. If installation is interrupted, rerun `./install.sh`.
There is no automatic rollback.

Upgrades replace known KIM6 program and menu files. Save any customizations
before upgrading. Unknown files are preserved and may prevent their
containing directory from being removed.

For installer safeguards and recovery procedures, see
[Installer safety and recovery](docs/DEVELOPMENT.md#installer-safety-and-recovery).

## Offline manual and documentation updates

KIM6 installs a complete offline user manual, including its stylesheet,
illustrations, and HTML reference pages. The manual is available through
the KIM6 User Manual action in Dolphin.

When Python 3 and Pandoc are installed, running `./install.sh` from a
writable, non-root development checkout automatically regenerates the
HTML references from the project's Markdown documentation.

For root installations or checkouts where the reference directory is
not writable, the installer verifies the generated HTML rather than
modifying the source files, provided both tools are available. If the
generated pages are outdated, installation stops.

Python 3 and Pandoc are not required to view the manual. If either
build tool is unavailable during installation, KIM6 uses the prebuilt
HTML pages supplied with the repository.

Contributors should commit regenerated HTML reference pages alongside
their Markdown changes. The illustrated landing page is maintained
separately and is not automatically generated.
