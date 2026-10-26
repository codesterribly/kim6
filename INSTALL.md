# Install KIM6

KIM6 targets KDE Plasma 6, KIO 6, and Dolphin service menus. It installs one processing executable (`kim_all`), five `.desktop` service-menu data files, translations when compiled, the gallery templates, and resources for About, License, and Manual. It does not install the historical standalone `kim_*` programs as active commands.

## Runtime dependencies

The exact requirements depend on the actions you use:

- **KDE Plasma 6, KIO, Dolphin, KDialog, and `qdbus`** provide the service-menu and graphical progress/cancellation interface.
- **ImageMagick 7**, with `magick` and `identify`, powers image operations and some PDF/TIFF/GIF workflows.
- **ExifTool** is needed for metadata operations, EXIF-date renaming, and image workflows that inspect metadata or profiles.
- **FFmpeg and ffprobe** are required for video workflows and APNG conversion. Slideshow creation requires FFmpeg’s `libx264` encoder.
- **Optional ImageMagick delegates and ICC profiles** enable formats and color transforms such as WebP, AVIF, HEIC/HEIF, JPEG XL, JPEG 2000, and sRGB conversion.
- **`xdg-open`** opens the installed manual/license and generated galleries. **`xdg-email`, KMail, or Thunderbird** can receive prepared email attachments.
- **`intltool-merge`** is required to render service menus during installation. `msgfmt` is optional; without it, menu text remains untranslated. `kreadconfig6` is optional and reads the KConfig settings file; without it, configured KConfig values are unavailable and defaults apply.
- `setsid` is used to monitor and stop slideshow image-preparation processes safely.

KIM6 checks required tools for the selected action and probes optional encoders at runtime. A missing codec/delegate fails that operation; KIM6 does not silently substitute another format or video codec. Consult [FORMATS.md](docs/FORMATS.md) for format-specific requirements.

## Install from a checkout

Clone the repository and install the per-user service menus:

```sh
git clone https://github.com/KIM-6/kim6.git
cd kim6
./install.sh
```

The default user prefix is `${XDG_DATA_HOME:-$HOME/.local/share}/kio/servicemenus`.

To install into another service-menu directory, pass that directory—not its parent—as the prefix:

```sh
./install.sh --prefix "$HOME/.local/share/kio/servicemenus"
```

The supported installer option is `--prefix SERVICEMENU_DIRECTORY`. When run as root without an explicit prefix, the installer chooses the first directory in `${XDG_DATA_DIRS:-/usr/local/share:/usr/share}` and appends `/kio/servicemenus`. For a system install, use a deliberate prefix and run with appropriate privileges, for example:

```sh
sudo ./install.sh --prefix /usr/local/share/kio/servicemenus
```

Do not run system installation commands against an unfamiliar prefix. The installer creates a missing destination directory.

## Upgrade and reinstall

Run the same `./install.sh` command and prefix used for the existing installation. Repeating installation is supported. The installer prepares the runtime and rendered menus before swapping active files, checks menu references, records a manifest, and restores the prior installation if the replacement phase fails.

The migration recognizes only the five named KIM service menus and the `kim6` runtime directory. It refuses ambiguous same-name menu ownership, runtime symlinks, and runtime trees containing symlinks. It removes known old executables only when it can establish ownership from an identical repository copy; customized legacy commands are preserved in a non-executable recovery location inside the new runtime. Unknown runtime files are retained. Customized managed resources are backed up rather than silently overwritten.

KIM6 does not delete broad `kim*` globs or unrelated files in the service-menu directory. Do not manually remove files to “clean up” an upgrade.

## Verify installation

Check that these files exist under the chosen service-menu prefix:

```text
kim6/bin/kim_all
kim_compress.desktop
kim_compressandresize.desktop
kim_convertandrotate.desktop
kim_compressandresizevideo.desktop
kim_publication.desktop
```

The dispatcher must be executable. The `.desktop` files are data files and are installed with mode `0644`; do not make them executable. Their `Exec` lines use the installed dispatcher’s absolute path, so it does not need to be in `PATH`.

The installer runs an isolated KDE cache validation when `kbuildsycoca6` is available and refreshes the live cache best-effort. Restart Dolphin or rebuild its service-menu cache if entries do not appear. The development desktop uses KDE Frameworks/KIO 6.29, which has a known upstream `X-KDE-Submenu` regression. KIM6 retains its submenus; wait for the KDE fix or test on another supported Plasma 6 system rather than removing submenu declarations.

You can also check dispatcher help without Dolphin:

```sh
/path/to/kio/servicemenus/kim6/bin/kim_all --help
```

For a real processing smoke test, use a disposable image copy and a create-mode command from [CLI.md](docs/CLI.md). Do not test destructive overwrite behavior on personal media.

## Uninstall

Use the matching prefix. A per-user install can usually be removed with:

```sh
./uninstall.sh
```

For a custom or system prefix:

```sh
./uninstall.sh --prefix "$HOME/.local/share/kio/servicemenus"
sudo ./uninstall.sh --prefix /usr/local/share/kio/servicemenus
```

`uninstall.sh` also accepts `--no_message`. It removes a menu only when its ownership marker/manifest or a recognized previous KIM command establishes ownership. Manifest-managed runtime files are removed only when their contents still match the recorded digest. Unrelated files and user changes are retained. An unsafe runtime symlink causes uninstall to stop rather than follow it. Empty KIM-owned directories are removed when possible.

## Troubleshooting

- **Installer says `intltool-merge` is missing:** install the distribution package providing `intltool` and rerun the same command.
- **A format action is unavailable:** check the local ImageMagick coder list and relevant FFmpeg encoder; see [FORMATS.md](docs/FORMATS.md). Optional support varies by build.
- **Progress or cancellation does not work:** verify KDialog and `qdbus` are installed and that Dolphin runs in a KDE graphical D-Bus session.
- **The menu is missing:** confirm the files are under the active user/system `kio/servicemenus` directory, restart Dolphin, and check the KDE cache. Keep the submenu declaration; the 6.29 regression is external to KIM6.
- **Installation failed during replacement:** the script attempts rollback and reports an error. Inspect the exact prefix and preserved runtime before retrying; do not remove unrelated files.

For reproducible reports, include the KIM6 commit, Plasma/KIO version, action and exact arguments, relevant dependency versions/coder output, and whether the issue reproduces on disposable test files.

More detail: [configuration](docs/CONFIGURATION.md), [safety behavior](docs/SAFETY.md), and [feature inventory](docs/ACTIONS.md).
